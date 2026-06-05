"""Endpoints para la web de cliente (nebulabs-media) — subida DIRECTA a Drive.

El cliente sube los vídeos DIRECTAMENTE a Google Drive (los bytes no pasan ni
por Vercel ni por el VPS): el box solo emite una URL de subida resumable con
la Service Account, y el navegador sube a Google con % de progreso. El
rclone-mount del box ve el archivo on-demand y el runner lo procesa solo al
editar — así se reserva la potencia del servidor para el procesamiento.

Auth con ticket firmado (HS256, secreto compartido `WEB_UPLOAD_SECRET`). El
box resuelve el EditorUser por `account_email`.

Flujo:
  1. POST /web/upload-url    — emite URL de subida directa a Drive (entrada/<día>/)
  2. GET  /web/day           — lista los vídeos del día (fuente de verdad: Drive)
  3. POST /web/delete-file   — borra un vídeo del día (si no bloqueado)
  4. POST /web/send-to-edit  — encola TODOS los vídeos del día y lo bloquea
  5. GET  /web/output        — estado de la edición + vídeos listos (score ≥ 90)
  6. GET  /web/download      — descarga un vídeo editado de salida/<día>/
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.dependencies import get_queue
from src.api.exceptions import APIError, UserNotFoundError, ValidationError
from src.api.web_ticket import TicketClaims, require_web_ticket, verify_ticket
from src.editor_auto.config import (
    TOOL_SILENCE_CUTTER_SCRIPTED,
    is_valid_day,
    user_input_day_folder,
    user_output_day_folder,
)
from src.editor_auto.models import EditorUser
from src.editor_auto.repos import UserRepo
from src.editor_auto.repos.redis_base import get_editor_redis
from src.editor_auto.services import drive_uploads, quota_service
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus


router = APIRouter(prefix="/api/v1/editor-auto/web", tags=["editor-auto · web"])

_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

# ─── Límites anti-abuso (servidor privado) ───
_MAX_FILES_PER_DAY = 50              # tope duro de vídeos por día/usuario
_RATE_MAX = 60                       # nº máx de URLs de subida emitidas…
_RATE_WINDOW_S = 300                 # …por ventana (5 min) y usuario

_SENT_DAYS_KEY = "webdays_sent:"
_JOBS_KEY = "webday_jobs:"
_RATE_KEY = "webrate:"
_MIN_SCORE = 90


def _resolve_user(claims: TicketClaims) -> EditorUser:
    # Auto-provisión: si aún no existe el EditorUser vinculado a este email,
    # se crea solo a partir de la cuenta web (idempotente). Así el cliente no
    # depende de que el admin pulse "Crear usuario" en el panel.
    from src.editor_auto.services.provision_service import provision_from_web
    user = provision_from_web(claims.email)
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


def _rate_check(email: str) -> None:
    r = get_editor_redis()
    if not r.is_available():
        return
    bucket = int(time.time()) // _RATE_WINDOW_S
    key = f"{_RATE_KEY}{email}:{bucket}"
    n = r.incr(key)
    if n == 1:
        r.expire(key, _RATE_WINDOW_S + 5)
    if n > _RATE_MAX:
        raise APIError(
            "Demasiadas subidas en poco tiempo. Espera unos minutos.",
            status_code=429,
            details={"retry_after_seconds": _RATE_WINDOW_S},
        )


def _require_drive() -> None:
    if not drive_uploads.is_configured():
        raise APIError(
            "La subida no está disponible (Drive no configurado en el servidor).",
            status_code=503,
        )


def _save_day_jobs(user_id: str, day: str, jobs: list[dict]) -> None:
    get_editor_redis().set_json(f"{_JOBS_KEY}{user_id}:{day}", jobs)


def _get_day_jobs(user_id: str, day: str) -> list[dict]:
    data = get_editor_redis().get_json(f"{_JOBS_KEY}{user_id}:{day}")
    return data if isinstance(data, list) else []


def _job_score(job) -> int | None:
    params = getattr(job, "params", None) or {}
    paths = []
    tf = params.get("temp_folder")
    if isinstance(tf, str):
        paths.append(os.path.join(tf, f"editor_diagnostic_{job.id}.json"))
    paths.append(os.path.join(os.getcwd(), "temp_work", f"editor_diagnostic_{job.id}.json"))
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    diag = json.load(f)
                score = (diag.get("audit") or {}).get("quality_score")
                return int(score) if score is not None else None
            except Exception:
                return None
    return None


# ─────────────────────────── Emitir URL de subida ───────────────────────────

class UploadUrlRequest(BaseModel):
    day: str
    filename: str


@router.post("/upload-url", status_code=status.HTTP_201_CREATED)
def web_upload_url(
    claims: Annotated[TicketClaims, Depends(require_web_ticket)],
    payload: UploadUrlRequest,
    request: Request,
) -> dict:
    """Devuelve una URL de subida resumable a Drive para `entrada/<día>/`.
    El navegador sube los bytes directamente a Google (no al VPS)."""
    _require_drive()
    day = payload.day
    if not is_valid_day(day):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"day": day})
    if claims.day and claims.day != day:
        raise ValidationError("El ticket no autoriza este día.", details={"day": day})

    user = _resolve_user(claims)
    if _day_locked(user.id, day):
        raise APIError("Este día ya se mandó a edición y está bloqueado.", status_code=409)

    _rate_check(claims.email)

    name = _safe_name(payload.filename)
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if name.lower().endswith(e)), "")
    if not ext:
        raise ValidationError(
            f"Formato no soportado. Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}.",
            details={"filename": payload.filename},
        )

    # Tope de nº de vídeos por día (cuenta en Drive).
    try:
        if len(drive_uploads.list_day_files(user.name, day)) >= _MAX_FILES_PER_DAY:
            raise APIError(f"Límite de {_MAX_FILES_PER_DAY} vídeos por día alcanzado.", status_code=409)
        folder_id = drive_uploads.ensure_day_folder(user.name, day)
        origin = request.headers.get("origin")
        final_name = f"{int(time.time())}_{name}"
        upload_url = drive_uploads.init_resumable_session(
            folder_id, final_name, mime="video/mp4", origin=origin,
        )
    except APIError:
        raise
    except Exception as e:
        raise APIError(f"No se pudo preparar la subida a Drive: {e}", status_code=502)

    return {"ok": True, "upload_url": upload_url, "filename": final_name}


# ─────────────────────────── Estado del día ───────────────────────────

@router.get("/day")
def web_day(
    claims: Annotated[TicketClaims, Depends(require_web_ticket)],
    day: str,
) -> dict:
    if not is_valid_day(day):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"day": day})
    _require_drive()
    user = _resolve_user(claims)
    return {
        "day": day,
        "locked": _day_locked(user.id, day),
        "videos": drive_uploads.list_day_files(user.name, day),
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
    if not is_valid_day(payload.day):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"day": payload.day})
    _require_drive()
    user = _resolve_user(claims)
    if _day_locked(user.id, payload.day):
        raise APIError("El día está bloqueado; no se pueden borrar vídeos.", status_code=409)
    ok = drive_uploads.delete_day_file(user.name, payload.day, _safe_name(payload.filename))
    if not ok:
        raise UserNotFoundError("Vídeo no encontrado.", details={"filename": payload.filename})
    return {"ok": True, "videos": drive_uploads.list_day_files(user.name, payload.day)}


# ─────────────────────────── Mandar a edición ───────────────────────────

class SendToEditRequest(BaseModel):
    day: str


def _enqueue_video(queue: JobQueue, user: EditorUser, mount_path: Path, day: str) -> str:
    """Encola un vídeo leyéndolo DIRECTO del rclone-mount (input_path = ruta
    del mount). El runner lee on-demand al procesar — sin copia previa que
    descargue bytes durante el send-to-edit."""
    enabled = [s for s in user.tool_flow if s.enabled]
    if not enabled:
        raise APIError(
            "Tu cuenta aún no tiene un flujo de edición configurado. Configura tu estilo.",
            status_code=409,
        )
    if any(s.tool_id == TOOL_SILENCE_CUTTER_SCRIPTED for s in enabled):
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

    try:
        from src.utils import load_config
        temp_folder = load_config()["paths"]["temp_folder"]
    except Exception:
        temp_folder = "./temp_work"

    tools_used = [s.tool_id for s in enabled]
    title = f"{user.name} · {mount_path.name} · {len(enabled)} tool(s)"
    params: dict[str, Any] = {
        "user_id": user.id,
        "user_name": user.name,
        "input_path": str(mount_path),
        "temp_folder": temp_folder,
        "tool_count": len(enabled),
        "tools_used": tools_used,
        "script": "",
        "output_subdir": day,
        "source_filename": mount_path.name,
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
    day = payload.day
    if not is_valid_day(day):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"day": day})
    _require_drive()
    user = _resolve_user(claims)
    if _day_locked(user.id, day):
        raise APIError("Este día ya se mandó a edición.", status_code=409)

    # Sincroniza el flujo de edición con el estilo ACTUAL del cliente (web).
    from src.editor_auto.repos.web_account_repo import get_web_account_repo
    from src.editor_auto.services.style_mapper import build_tool_flow
    account = get_web_account_repo().get(user.account_email)
    user.tool_flow = build_tool_flow((account or {}).get("styleConfig"))
    UserRepo().save(user)

    videos = drive_uploads.list_day_files(user.name, day)
    if not videos:
        raise ValidationError("No hay vídeos para este día.", details={"day": day})

    enqueued: list[dict] = []
    errors: list[dict] = []
    for v in videos:
        mount_path = Path(user_input_day_folder(user.name, day)) / v["filename"]
        try:
            job_id = _enqueue_video(queue, user, mount_path, day)
            enqueued.append({"filename": v["filename"], "job_id": job_id})
        except APIError as e:
            errors.append({"filename": v["filename"], "error": e.message})
            break

    if enqueued:
        _lock_day(user.id, day)
        _save_day_jobs(user.id, day, enqueued)

    return {"day": day, "enqueued": enqueued, "errors": errors, "locked": bool(enqueued)}


# ─────────────────────────── Salida (vídeos editados) ───────────────────────────

@router.get("/output")
def web_output(
    claims: Annotated[TicketClaims, Depends(require_web_ticket)],
    day: str,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    if not is_valid_day(day):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"day": day})
    user = _resolve_user(claims)
    jobs_meta = _get_day_jobs(user.id, day)
    by_id = {j.id: j for j in queue.get_all()}
    terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}

    videos: list[dict] = []
    ready = 0
    done = 0
    for m in jobs_meta:
        job = by_id.get(m.get("job_id"))
        st = job.status if job else None
        score = _job_score(job) if (job and job.status == JobStatus.COMPLETED) else None
        if job and job.status in terminal:
            done += 1
        out_name = os.path.basename(job.result_path) if (job and job.result_path) else None
        is_ready = bool(
            job and job.status == JobStatus.COMPLETED and out_name
            and (score is None or score >= _MIN_SCORE)
        )
        if is_ready:
            ready += 1
        videos.append({
            "source": m.get("filename"),
            "filename": out_name,
            "score": score,
            "ready": is_ready,
            "status": st.value if st else "unknown",
        })

    all_done = bool(jobs_meta) and done == len(jobs_meta)
    return {"day": day, "total": len(jobs_meta), "ready": ready, "all_done": all_done, "videos": videos}


@router.get("/download")
def web_download(
    day: str,
    file: str,
    ticket: Annotated[str, Query(...)],
) -> FileResponse:
    """Descarga un vídeo editado de `salida/<día>/` (lee del rclone-mount)."""
    claims = verify_ticket(ticket)
    if not is_valid_day(day):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"day": day})
    user = _resolve_user(claims)
    folder = user_output_day_folder(user.name, day)
    safe = _safe_name(file)
    path = os.path.join(folder, safe)
    if not os.path.exists(path):
        raise UserNotFoundError("Vídeo no encontrado.", details={"file": file})
    return FileResponse(path, media_type="video/mp4", filename=safe)
