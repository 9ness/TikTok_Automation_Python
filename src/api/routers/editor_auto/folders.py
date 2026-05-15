"""CRUD de las 4 carpetas del usuario Editor Auto (entrada / cola /
recuperacion / salida). Permite al admin gestionar el ciclo de vida de
los vídeos sin tocar Drive manualmente.

Endpoints:
    GET  /users/{id}/folders                 — todo en un payload
    GET  /users/{id}/folders/counts          — solo los 4 conteos (badges)
    GET  /folders/counts                     — agregado de todos los users
    POST /users/{id}/folders/move            — mover entre carpetas
    DELETE /users/{id}/folders/file          — borrar (irreversible)
    POST /users/{id}/folders/enqueue         — encolar desde `entrada/`
                                               (mueve a `cola/` + crea job)
    GET  /users/{id}/folders/file/preview    — servir el MP4 para preview
                                               (auth dual header/query)

Auth: header `X-API-Key` (dependencia del router). El endpoint
`/preview` permite también `?api_key=` query porque `<video src=>` no
admite headers custom (mismo patrón que fonts/stickers).
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.config import APISettings, get_settings
from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import UnauthorizedError, ValidationError
from src.editor_auto.config import USER_FOLDERS, user_subfolder
from src.editor_auto.repos import UserRepo
from src.editor_auto.services import folder_manager
from src.queue.manager import JobQueue
from src.queue.models import JobMode


router = APIRouter(
    prefix="/api/v1/editor-auto",
    tags=["editor-auto · folders"],
)


_VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".m4v": "video/x-m4v",
}


def _user_or_raise(user_id: str):
    repo = UserRepo()
    u = repo.get(user_id)
    if u is None or u.deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Usuario no encontrado o eliminado: {user_id}",
        )
    return u


# ---------------------------------------------------------------------------
# Listados (auth normal — header)
# ---------------------------------------------------------------------------
@router.get(
    "/users/{user_id}/folders",
    dependencies=[Depends(get_current_user)],
)
def list_user_folders(user_id: str) -> dict[str, Any]:
    """Listado completo de las 4 carpetas del usuario con metadatos por
    archivo. La UI lo consume para pintar los 4 tabs de una vez."""
    u = _user_or_raise(user_id)
    by_folder: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int] = {}
    for folder in USER_FOLDERS:
        items = folder_manager.list_files(u.name, folder)
        by_folder[folder] = items
        counts[folder] = len(items)
    return {
        "user_id": u.id,
        "user_name": u.name,
        "folders": by_folder,
        "counts": counts,
    }


@router.get(
    "/users/{user_id}/folders/counts",
    dependencies=[Depends(get_current_user)],
)
def user_folder_counts(user_id: str) -> dict[str, Any]:
    """Solo los 4 conteos, sin metadatos por archivo. Diseñado para el
    badge de la lista de usuarios (refresca cada 20–30s)."""
    u = _user_or_raise(user_id)
    return {
        "user_id": u.id,
        "user_name": u.name,
        "counts": folder_manager.count_files(u.name),
    }


# Cache módulo para `/folders/counts`. El badge global de la sidebar
# llama a este endpoint cada 30s desde cada cliente — y cada call hace
# `listdir` + `stat` sobre las 4 carpetas de Drive de CADA usuario, lo
# que en Drive Desktop / rclone puede tardar varios segundos. Cachear
# 15s evita golpear el FS en cada navegación SPA sin perder reactividad
# (al subir un vídeo, el badge tarda como mucho 15s en actualizarse).
_GLOBAL_COUNTS_TTL = 15.0
_global_counts_cache: dict[str, tuple[float, dict[str, Any]]] = {}


@router.get(
    "/folders/counts",
    dependencies=[Depends(get_current_user)],
)
def global_folder_counts() -> dict[str, Any]:
    """Conteos agregados de TODOS los usuarios activos. Lo consume el
    badge global de la sidebar (un número total de pendientes en
    `entrada/` para que el admin vea cuántos hay sin entrar a cada user).

    Returns:
        {
            "totals": {"entrada": N, "cola": N, "recuperacion": N, "salida": N},
            "by_user": [{"user_id", "user_name", "counts": {...}}, ...]
        }
    """
    now = time.time()
    cached = _global_counts_cache.get("data")
    if cached and now - cached[0] < _GLOBAL_COUNTS_TTL:
        return cached[1]

    repo = UserRepo()
    users = repo.list_all(include_deleted=False)

    # Paralelizar el conteo por usuario: cada `count_files` hace 4 listdir
    # + stat sobre Drive Desktop (que en Windows es lento por sync). Para
    # N usuarios secuencial sería N × ~0.5-1s; en paralelo ≈ max() ~1s.
    def _count_one(u) -> tuple[Any, dict[str, int]]:
        try:
            return u, folder_manager.count_files(u.name)
        except Exception:
            return u, {f: 0 for f in USER_FOLDERS}

    totals = {f: 0 for f in USER_FOLDERS}
    by_user: list[dict[str, Any]] = []
    if users:
        with ThreadPoolExecutor(max_workers=min(8, len(users))) as ex:
            for u, counts in ex.map(_count_one, users):
                for k, v in counts.items():
                    totals[k] = totals.get(k, 0) + v
                by_user.append({
                    "user_id": u.id,
                    "user_name": u.name,
                    "counts": counts,
                })
    result = {"totals": totals, "by_user": by_user}
    _global_counts_cache["data"] = (now, result)
    return result


# ---------------------------------------------------------------------------
# Acciones (auth normal — header)
# ---------------------------------------------------------------------------
@router.post(
    "/users/{user_id}/folders/move",
    dependencies=[Depends(get_current_user)],
)
def move_user_file(
    user_id: str,
    payload: Annotated[dict, Body(...)],
) -> dict[str, Any]:
    """Mueve un archivo entre carpetas del usuario. Body:
    `{src_folder, dst_folder, filename}`. Si el destino ya tiene un
    archivo con ese nombre, se renombra con sufijo `_2`/`_3`/…"""
    u = _user_or_raise(user_id)
    src = (payload.get("src_folder") or "").strip()
    dst = (payload.get("dst_folder") or "").strip()
    filename = (payload.get("filename") or "").strip()
    try:
        result = folder_manager.move_file(u.name, src, dst, filename)
    except (folder_manager.FolderError, ValueError) as e:
        raise ValidationError(str(e))
    return result


@router.delete(
    "/users/{user_id}/folders/file",
    dependencies=[Depends(get_current_user)],
)
def delete_user_file(
    user_id: str,
    folder: Annotated[str, Query(...)],
    filename: Annotated[str, Query(...)],
) -> dict[str, Any]:
    """Borra un archivo del filesystem. IRREVERSIBLE."""
    u = _user_or_raise(user_id)
    try:
        folder_manager.delete_file(u.name, folder, filename)
    except (folder_manager.FolderError, ValueError) as e:
        raise ValidationError(str(e))
    return {"ok": True, "user_id": u.id, "folder": folder, "filename": filename}


@router.post(
    "/users/{user_id}/folders/enqueue",
    dependencies=[Depends(get_current_user)],
)
def enqueue_from_entrada(
    user_id: str,
    payload: Annotated[dict, Body(...)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict[str, Any]:
    """Encola un vídeo que ya está en `entrada/` del usuario.

    Pasos:
        1. Valida que existe en `entrada/`.
        2. MUEVE entrada/<file> → cola/<file> (lock visual: el cliente
           no debe tocar archivos en procesamiento).
        3. Crea el job con `input_path` apuntando a cola/<file>.
        4. Job ejecuta. Tras éxito el pipeline mueve cola → recuperacion.
           Tras fallo el runner mueve cola → entrada (auto-retry manual).

    Body: `{filename, script?}` (script obligatorio si flow tiene
    silence_cutter_scripted).
    """
    u = _user_or_raise(user_id)
    filename = (payload.get("filename") or "").strip()
    script_from_body = (payload.get("script") or "").strip()

    enabled = [s for s in u.tool_flow if s.enabled]
    if not enabled:
        raise ValidationError(
            f"El usuario '{u.name}' no tiene herramientas habilitadas."
        )
    needs_script = any(s.tool_id == "silence_cutter_scripted" for s in enabled)

    # Resolución del guion (prioridad: body > companion .txt en entrada/).
    # Para flows scripted, si el cliente subió `<stem>.txt` junto al
    # vídeo en entrada/, lo leemos automáticamente — el operador no tiene
    # que copiar/pegar nada.
    script: str = ""
    if script_from_body:
        script = script_from_body
    elif needs_script:
        try:
            companion = folder_manager.read_script_companion(
                u.name, "entrada", filename,
            )
        except (folder_manager.FolderError, ValueError) as e:
            raise ValidationError(str(e))
        if companion:
            script = companion

    if needs_script and not script:
        raise ValidationError(
            f"El usuario '{u.name}' tiene 'silence_cutter_scripted' en su "
            f"flow — necesita un guión. Sube un archivo `.txt` con el "
            f"mismo nombre base que el vídeo (ej: `{os.path.splitext(filename)[0]}.txt`) "
            f"a la carpeta `entrada/`, o pasa el guión en el body."
        )

    # 1+2. mover entrada → cola (incluye companion .txt si existe)
    try:
        move_result = folder_manager.move_file(
            u.name, "entrada", "cola", filename,
        )
    except (folder_manager.FolderError, ValueError) as e:
        raise ValidationError(str(e))

    # 3. crear job apuntando al path real en cola/
    final_filename = move_result["filename_new"]
    input_path = os.path.join(user_subfolder(u.name, "cola"), final_filename)

    try:
        from src.utils import load_config
        cfg = load_config()
        temp_folder = cfg["paths"]["temp_folder"]
    except Exception:
        temp_folder = "./temp_work"

    tools_used = [s.tool_id for s in enabled]
    title = f"{u.name} · {final_filename} · {len(enabled)} tool(s)"
    params: dict[str, Any] = {
        "user_id": u.id,
        "user_name": u.name,
        "input_path": input_path,
        "temp_folder": temp_folder,
        "tool_count": len(enabled),
        "tools_used": tools_used,
        "script": script if needs_script else None,
        # Flag para el runner: gestiona el ciclo cola→recuperacion (OK)
        # o cola→entrada (fallo). Sin este flag (caso upload directo),
        # el runner deja los temps como antes.
        "source": "entrada",
        "source_filename": final_filename,
    }
    job = queue.enqueue(JobMode.EDITOR_AUTO, title=title, params=params)
    return {
        "job_id": job.id,
        "title": title,
        "filename": final_filename,
        "moved": move_result,
    }


# ---------------------------------------------------------------------------
# Preview de archivo — auth dual header + query (necesario para <video src>)
# ---------------------------------------------------------------------------
def _auth_or_raise(
    settings: APISettings, header: str | None, query: str | None
) -> None:
    if not settings.api_key:
        return
    provided = header or query
    if not provided or provided != settings.api_key:
        raise UnauthorizedError("API key inválida o ausente.")


@router.get("/users/{user_id}/folders/file/preview")
def preview_user_file(
    user_id: str,
    folder: Annotated[str, Query(...)],
    filename: Annotated[str, Query(...)],
    settings: Annotated[APISettings, Depends(get_settings)],
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> FileResponse:
    """Sirve el MP4 para preview en `<video>`. Auth dual."""
    _auth_or_raise(settings, x_api_key, api_key)
    u = _user_or_raise(user_id)
    try:
        path = folder_manager.resolve_file(u.name, folder, filename)
    except (folder_manager.FolderError, ValueError) as e:
        raise ValidationError(str(e))
    ext = os.path.splitext(filename)[1].lower()
    return FileResponse(
        path,
        media_type=_VIDEO_MIME.get(ext, "application/octet-stream"),
        filename=os.path.basename(filename),
    )
