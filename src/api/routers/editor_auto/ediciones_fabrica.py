"""Ediciones del Editor Auto mandadas «para» un usuario de la fábrica.

Las lee el MCP (`ediciones_editor`) para saber qué vídeos se editaron para ese
usuario y registrarlos en Mis tandas. Los agentes también MANDAN a editar con
`POST .../enviar` (MCP `editar_en_editor`). Ver `src/editor_auto/services/ediciones_fabrica.py`.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from src.api import users
from src.api.dependencies import get_current_user, get_queue, get_web_user
from src.api.exceptions import APIError, UserNotFoundError, ValidationError
from src.editor_auto.services import ediciones_fabrica as ef
from src.queue.manager import JobQueue

router = APIRouter(
    prefix="/api/v1/editor-auto/ediciones-fabrica",
    tags=["editor-auto · ediciones para la fábrica"],
    dependencies=[Depends(get_current_user)],
)


def _quien(web_user: str, usuario: str) -> str:
    """Tu propio usuario; otro solo si eres admin."""
    if usuario and usuario != web_user:
        if not users.es_admin(web_user):
            raise APIError("Solo un admin puede ver las ediciones de otro usuario.", status_code=403)
        if usuario not in ef.usuarios_validos():
            raise APIError(f"Usuario de fábrica desconocido: {usuario}", status_code=404)
        return usuario
    if not web_user:
        raise APIError("Sin sesión de usuario.", status_code=401)
    return web_user


@router.get("")
def listar(
    queue: Annotated[JobQueue, Depends(get_queue)],
    web_user: Annotated[str, Depends(get_web_user)] = "",
    usuario: Annotated[str, Query()] = "",
    limite: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    u = _quien(web_user, usuario)
    return {"usuario": u, "ediciones": ef.listar(u, queue, limite=limite)}


@router.get("/{job_id}/mp4")
def mp4(
    job_id: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
    web_user: Annotated[str, Depends(get_web_user)] = "",
    usuario: Annotated[str, Query()] = "",
) -> FileResponse:
    u = _quien(web_user, usuario)
    ruta = ef.ruta_mp4(u, job_id, queue)
    if not ruta:
        raise UserNotFoundError("Esa edición no existe o aún no está lista.", details={"job_id": job_id})
    return FileResponse(ruta, media_type="video/mp4", filename=f"edicion_{job_id}.mp4")


_EXT_VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
_MAX_MB = 500


def _cuenta_agentes():
    """EditorUser de la cuenta del editor que hace los trabajos de agentes."""
    email = os.getenv("EDITOR_CUENTA_AGENTES_EMAIL", "").strip()
    if not email:
        raise APIError("Falta EDITOR_CUENTA_AGENTES_EMAIL en el servidor (cuenta del editor "
                       "que edita para los agentes).", status_code=503)
    from src.editor_auto.services.provision_service import provision_from_web

    user = provision_from_web(email)
    if user is None or user.deleted:
        raise APIError("La cuenta del editor de EDITOR_CUENTA_AGENTES_EMAIL no existe.", status_code=503)
    return user


def _json_opcional(valor: str, campo: str, tipo: type):
    if not (valor or "").strip():
        return None
    try:
        v = json.loads(valor)
    except ValueError as e:
        raise ValidationError(f"`{campo}` no es JSON válido.", details={campo: valor[:200]}) from e
    if not isinstance(v, tipo):
        raise ValidationError(f"`{campo}` tiene que ser {'una lista' if tipo is list else 'un objeto'}.")
    return v


@router.post("/enviar")
def enviar(
    queue: Annotated[JobQueue, Depends(get_queue)],
    web_user: Annotated[str, Depends(get_web_user)] = "",
    file: Annotated[UploadFile | None, File()] = None,
    ruta_bandeja: Annotated[str, Form()] = "",
    para: Annotated[str, Form()] = "",
    estilo: Annotated[str, Form()] = "vip",
    pasos: Annotated[str, Form()] = "",
    config_vip: Annotated[str, Form()] = "",
    dia: Annotated[str, Form()] = "",
) -> dict:
    """Un agente manda UN vídeo a editar (multipart `file` o `ruta_bandeja` de
    su bandeja). `estilo`: vip | normal | pasos; `pasos` y `config_vip` en
    JSON. El flujo va en el trabajo, no en la cuenta. Se recoge con
    `GET /ediciones-fabrica` y `/{job_id}/mp4`."""
    from src.api.routers.editor_auto.web_upload import encolar_para_agente
    from src.editor_auto.config import is_valid_day

    u = _quien(web_user, (para or "").strip())
    dia = (dia or "").strip() or datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d")
    if not is_valid_day(dia):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"dia": dia})
    if (file is not None) == bool((ruta_bandeja or "").strip()):
        raise ValidationError("Manda UNA fuente: `file` o `ruta_bandeja`.")
    lista_pasos = _json_opcional(pasos, "pasos", list)
    cfg_vip = _json_opcional(config_vip, "config_vip", dict)
    editor_user = _cuenta_agentes()
    estilo = (estilo or "vip").strip().lower()
    style_config = None
    if estilo == "normal":
        from src.editor_auto.repos.web_account_repo import get_web_account_repo

        style_config = (get_web_account_repo().get(editor_user.account_email) or {}).get("styleConfig")
    try:
        flujo = ef.flujo_para(estilo, style_config=style_config, pasos=lista_pasos, config_vip=cfg_vip)
    except ValueError as e:
        raise ValidationError(str(e)) from e

    temporal: str | None = None
    try:
        if file is not None:
            ext = Path(file.filename or "").suffix.lower()
            if ext not in _EXT_VIDEO:
                raise ValidationError(f"Formato no admitido ({ext or 'sin extensión'}).")
            temporal = tempfile.mkdtemp(prefix="ed_agente_")
            origen = Path(temporal) / (Path(file.filename or "").name or f"video{ext}")
            tope, total = _MAX_MB * 1024 * 1024, 0
            with open(origen, "wb") as out:
                while trozo := file.file.read(1024 * 1024):
                    total += len(trozo)
                    if total > tope:
                        raise ValidationError(f"El vídeo pasa de {_MAX_MB} MB.")
                    out.write(trozo)
        else:
            from src.replicar_viral import video as rv_video

            try:
                origen = rv_video.ruta_bandeja(web_user, ruta_bandeja)
            except Exception as e:  # noqa: BLE001 — ErrorReplica u OSError
                raise ValidationError(str(e)) from e
            if not origen.is_file():
                raise ValidationError(f"No existe {ruta_bandeja!r} en tu bandeja (¿aún sincronizando el Drive?).")
        return encolar_para_agente(queue, editor_user, origen, day=dia, para=u,
                                   tool_flow=flujo, estilo=estilo)
    finally:
        if temporal is not None:
            shutil.rmtree(temporal, ignore_errors=True)
