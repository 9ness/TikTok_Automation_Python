"""Endpoints para la web de cliente (nebulabs-media) — subida directa al box.

El cliente sube vídeos desde su navegador DIRECTAMENTE a este box (los bytes
NO pasan por Vercel). Se autentica con un ticket firmado (HS256, secreto
compartido `WEB_UPLOAD_SECRET`) que emite la web. El box resuelve el
EditorUser por `account_email` y guarda en `entrada/<día>/`.

Flujo:
  1. POST /web/upload        — sube un vídeo al día elegido (borrador).
  2. GET  /web/day           — lista los vídeos del día + si está bloqueado.
  3. POST /web/send-to-edit  — encola TODOS los vídeos del día y lo bloquea.
  4. DELETE /web/file        — borra un vídeo del día (solo si no bloqueado).

Aislado de la auth X-API-Key existente: usa `require_web_ticket`. No toca el
watcher (los vídeos viven en subcarpeta `entrada/<día>/`, que el watcher no
escanea) — el encolado es manual al pulsar "Mandar a edición".
"""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from pydantic import BaseModel

from src.api.dependencies import get_queue
from src.api.exceptions import APIError, UserNotFoundError, ValidationError
from src.api.temp_storage import upload_subdir
from src.api.web_ticket import TicketClaims, require_web_ticket
from src.editor_auto.config import (
    TOOL_SILENCE_CUTTER_SCRIPTED,
    is_valid_day,
    user_input_day_folder,
)
from src.editor_auto.models import EditorUser
from src.editor_auto.repos import UserRepo
from src.editor_auto.repos.redis_base import get_editor_redis
from src.editor_auto.services import quota_service
from src.queue.manager import JobQueue
from src.queue.models import JobMode


router = APIRouter(prefix="/api/v1/editor-auto/web", tags=["editor-auto · web"])

_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
_MAX_VIDEO_BYTES = 500 * 1024 * 1024  # 500 MB
_VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")

_SENT_DAYS_KEY = "webdays_sent:"  # set por usuario de días ya mandados a edición


def _resolve_user(claims: TicketClaims) -> EditorUser:
    """EditorUser vinculado al email del ticket. 404 si no existe vínculo."""
    user = UserRepo().get_by_account_email(claims.email)
    if user is None or user.deleted:
        raise UserNotFoundError(
            "No hay una cuenta de edición vinculada a este email. Contacta con soporte.",
            details={"email": claims.email},
        )
    return user


def _safe_name(filename: str) -> str:
    base = os.path.basename(filename or "video.mp4")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("_") or "video.mp4"
    return base


def _day_locked(user_id: str, day: str) -> bool:
    return day in get_editor_redis().smembers(f"{_SENT_DAYS_KEY}{user_id}")


def _lock_day(user_id: str, day: str) -> None:
    get_editor_redis().sadd(f"{_SENT_DAYS_KEY}{user_id}", day)


def _list_day_videos(username: str, day: str) -> list[dict[str, Any]]:
    folder = user_input_day_folder(username, day)
    out: list[dict[str, Any]] = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for name in names:
        if os.path.splitext(name)[1].lower() not in _VIDEO_EXTS:
            continue
        p = os.path.join(folder, name)
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        out.append({"filename": name, "size_bytes": size})
    return out


# ─────────────────────────── Subir ───────────────────────────

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def web_upload(
    claims: Annotated[TicketClaims, Depends(require_web_ticket)],
    file: Annotated[UploadFile, File(...)],
    day: Annotated[str, Form(...)],
) -> dict:
    """Sube un vídeo del cliente al día indicado (`entrada/<día>/`)."""
    if not is_valid_day(day):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"day": day})
    # El ticket fija el día permitido — no se puede subir a otro.
    if claims.day and claims.day != day:
        raise ValidationError("El ticket no autoriza este día.", details={"day": day})

    user = _resolve_user(claims)
    if _day_locked(user.id, day):
        raise APIError("Este día ya se mandó a edición y está bloqueado.", status_code=409)

    filename = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if filename.endswith(e)), "")
    if not ext:
        raise ValidationError(
            f"Formato no soportado. Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}.",
            details={"filename": file.filename},
        )
    contents = await file.read()
    if not contents:
        raise ValidationError("Archivo vacío.")
    if len(contents) > _MAX_VIDEO_BYTES:
        raise ValidationError(
            f"El vídeo pesa {len(contents) / 1024 / 1024:.1f} MB, máximo "
            f"{_MAX_VIDEO_BYTES / 1024 / 1024:.0f} MB."
        )

    folder = user_input_day_folder(user.name, day)
    Path(folder).mkdir(parents=True, exist_ok=True)
    dest = Path(folder) / f"{int(time.time())}_{_safe_name(file.filename or 'video' + ext)}"
    try:
        dest.write_bytes(contents)
    except OSError as e:
        raise APIError(f"No se pudo guardar el archivo: {e}")

    return {"ok": True, "filename": dest.name, "videos": _list_day_videos(user.name, day)}


# ─────────────────────────── Estado del día ───────────────────────────

@router.get("/day")
def web_day(
    claims: Annotated[TicketClaims, Depends(require_web_ticket)],
    day: str,
) -> dict:
    """Lista los vídeos subidos para un día y si está bloqueado."""
    if not is_valid_day(day):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"day": day})
    user = _resolve_user(claims)
    return {
        "day": day,
        "locked": _day_locked(user.id, day),
        "videos": _list_day_videos(user.name, day),
    }


# ─────────────────────────── Borrar (borrador) ───────────────────────────

class DeleteFileRequest(BaseModel):
    day: str
    filename: str


@router.post("/delete-file")
def web_delete_file(
    claims: Annotated[TicketClaims, Depends(require_web_ticket)],
    payload: DeleteFileRequest,
) -> dict:
    """Borra un vídeo del día (solo si el día NO está bloqueado)."""
    if not is_valid_day(payload.day):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"day": payload.day})
    user = _resolve_user(claims)
    if _day_locked(user.id, payload.day):
        raise APIError("El día está bloqueado; no se pueden borrar vídeos.", status_code=409)
    folder = user_input_day_folder(user.name, payload.day)
    target = Path(folder) / _safe_name(payload.filename)
    if not target.exists():
        raise UserNotFoundError("Vídeo no encontrado.", details={"filename": payload.filename})
    try:
        target.unlink()
    except OSError as e:
        raise APIError(f"No se pudo borrar: {e}")
    return {"ok": True, "videos": _list_day_videos(user.name, payload.day)}


# ─────────────────────────── Mandar a edición ───────────────────────────

class SendToEditRequest(BaseModel):
    day: str


def _enqueue_video(queue: JobQueue, user: EditorUser, src_path: Path) -> str:
    """Copia el vídeo a temp y lo encola con el flujo del usuario. Devuelve job_id.

    Replica la lógica de `enqueue_editor_auto` (quota + params) para no tocar
    el original en Drive — el runner trabaja sobre la copia en temp_work.
    """
    enabled = [s for s in user.tool_flow if s.enabled]
    if not enabled:
        raise APIError(
            "Tu cuenta aún no tiene un flujo de edición configurado. Contacta con soporte.",
            status_code=409,
        )
    if any(s.tool_id == TOOL_SILENCE_CUTTER_SCRIPTED for s in enabled):
        # El modo guionizado no aplica a la subida web (no hay guion del cliente).
        raise APIError("Tu flujo requiere guion; no compatible con subida web.", status_code=409)

    decision = quota_service.check_can_enqueue(user, tool_ids=[s.tool_id for s in enabled])
    if not decision.ok:
        sc_map = {
            "no_subscription": 402, "inactive_subscription": 402, "tool_not_allowed": 402,
            "daily_limit": 429, "monthly_limit": 429, "outside_window": 425,
            "spacing": 425, "promo_exhausted": 402,
        }
        raise APIError(
            decision.message,
            status_code=sc_map.get(decision.kind, 429),
            details={"kind": decision.kind, "retry_after_seconds": decision.retry_after_seconds},
        )

    ext = src_path.suffix.lower()
    folder = upload_subdir("editor_auto")
    dest = folder / f"editor_web_{user.name}_{int(time.time()*1000)}{ext}"
    shutil.copyfile(src_path, dest)

    try:
        from src.utils import load_config
        temp_folder = load_config()["paths"]["temp_folder"]
    except Exception:
        temp_folder = "./temp_work"

    tools_used = [s.tool_id for s in enabled]
    title = f"{user.name} · {src_path.name} · {len(enabled)} tool(s)"
    params: dict[str, Any] = {
        "user_id": user.id,
        "user_name": user.name,
        "input_path": str(dest),
        "temp_folder": temp_folder,
        "tool_count": len(enabled),
        "tools_used": tools_used,
        "script": "",
    }
    job = queue.enqueue(JobMode.EDITOR_AUTO, title=title, params=params)
    try:
        quota_service.register_enqueue(user)
    except Exception:
        pass
    return job.id


@router.post("/send-to-edit")
def web_send_to_edit(
    claims: Annotated[TicketClaims, Depends(require_web_ticket)],
    payload: SendToEditRequest,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    """Encola TODOS los vídeos del día y bloquea ese día (ya no se toca)."""
    day = payload.day
    if not is_valid_day(day):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"day": day})
    user = _resolve_user(claims)
    if _day_locked(user.id, day):
        raise APIError("Este día ya se mandó a edición.", status_code=409)

    videos = _list_day_videos(user.name, day)
    if not videos:
        raise ValidationError("No hay vídeos para este día.", details={"day": day})

    folder = user_input_day_folder(user.name, day)
    enqueued: list[dict] = []
    errors: list[dict] = []
    for v in videos:
        src = Path(folder) / v["filename"]
        try:
            job_id = _enqueue_video(queue, user, src)
            enqueued.append({"filename": v["filename"], "job_id": job_id})
        except APIError as e:
            errors.append({"filename": v["filename"], "error": e.message})
            # Si falla por cuota, paramos (los siguientes también fallarán).
            break

    # Solo bloqueamos si se encoló algo. Si todo falló (cuota), el día sigue
    # editable para reintentar más tarde.
    if enqueued:
        _lock_day(user.id, day)

    return {"day": day, "enqueued": enqueued, "errors": errors, "locked": bool(enqueued)}
