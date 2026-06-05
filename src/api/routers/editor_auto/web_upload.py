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

from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import APIError, UserNotFoundError, ValidationError
from src.api.web_ticket import TicketClaims, require_web_ticket, verify_ticket
from src.editor_auto.config import (
    TOOL_SILENCE_CUTTER_SCRIPTED,
    day_send_open,
    is_valid_day,
    send_cutoff_hour,
    send_cutoff_minute,
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

_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}

# ─── Límites anti-abuso (servidor privado) ───
_MAX_FILES_PER_DAY = 50              # tope duro de vídeos por día/usuario
_RATE_MAX = 60                       # nº máx de URLs de subida emitidas…
_RATE_WINDOW_S = 300                 # …por ventana (5 min) y usuario

_SENT_DAYS_KEY = "webdays_sent:"
_JOBS_KEY = "webday_jobs:"
_RATE_KEY = "webrate:"
_APPROVED_KEY = "webday_approved:"      # set de out-filenames aprobados por user/día
_SENT_INDEX_KEY = "web_sent_index"       # set global de "{user_id}:{day}" (para el admin)
_NOTIFIED_KEY = "webday_notified:"       # flag "ya enviado email de listos" por user/día
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
    r = get_editor_redis()
    r.sadd(f"{_SENT_DAYS_KEY}{user_id}", day)
    # Índice global para que el panel admin liste días con salida pendiente.
    r.sadd(_SENT_INDEX_KEY, f"{user_id}:{day}")


def _approved_set(user_id: str, day: str) -> set[str]:
    try:
        return set(get_editor_redis().smembers(f"{_APPROVED_KEY}{user_id}:{day}") or [])
    except Exception:
        return set()


def _approve_output(user_id: str, day: str, out_name: str) -> None:
    get_editor_redis().sadd(f"{_APPROVED_KEY}{user_id}:{day}", out_name)


def _unapprove_output(user_id: str, day: str, out_name: str) -> None:
    get_editor_redis().srem(f"{_APPROVED_KEY}{user_id}:{day}", out_name)


def _maybe_notify_ready(user: EditorUser, day: str, queue: JobQueue) -> None:
    """Si el cliente activó el aviso por email y el día YA está completo para él
    (todos los vídeos resueltos: aprobados o caídos, ninguno pendiente), envía
    el email 'tus vídeos están listos' una sola vez. Nunca lanza."""
    try:
        from src.editor_auto.config import manual_approval_enabled
        from src.editor_auto.repos.web_account_repo import get_web_account_repo
        from src.editor_auto.services import email_notify

        r = get_editor_redis()
        notified_key = f"{_NOTIFIED_KEY}{user.id}:{day}"
        if r.get_str(notified_key):
            return  # ya avisado
        acc = get_web_account_repo().get(user.account_email) or {}
        if not acc.get("notifyEmail"):
            return
        email = (acc.get("email") or user.account_email or "").strip()
        if not email or not email_notify.is_configured():
            return

        gate = manual_approval_enabled()
        approved = _approved_set(user.id, day)
        by_id = {j.id: j for j in queue.get_all()}
        terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
        jobs_meta = _get_day_jobs(user.id, day)
        ready = 0
        for m in jobs_meta:
            job = by_id.get(m.get("job_id"))
            if not (job and job.status in terminal):
                return  # aún hay trabajos en curso → no avisar
            out_name = os.path.basename(job.result_path) if job.result_path else None
            score = _job_score(job) if job.status == JobStatus.COMPLETED else None
            passed = bool(job.status == JobStatus.COMPLETED and out_name and (score is None or score >= _MIN_SCORE))
            is_approved = (not gate) or (out_name in approved if out_name else False)
            if passed and not is_approved:
                return  # hay vídeos buenos pendientes de aprobar → aún no
            if passed and is_approved:
                ready += 1
        if ready <= 0:
            return
        name = acc.get("username") or acc.get("name") or user.name
        res = email_notify.send_videos_ready(
            to=[email], client_name=name, count=ready,
            folder_link=os.getenv("EDITOR_WEB_PANEL_URL", "https://nebulabsmedia.com/panel"),
        )
        if res.get("ok"):
            r.set_str(notified_key, "1")
    except Exception:
        pass


def _user_has_plan(user: EditorUser) -> bool:
    """True si la cuenta web vinculada tiene un plan (no solo prueba)."""
    try:
        from src.editor_auto.repos.web_account_repo import get_web_account_repo
        acc = get_web_account_repo().get(user.account_email) or {}
        return bool(acc.get("planId"))
    except Exception:
        return False


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
    if not day_send_open(day):
        raise APIError(
            f"El cierre para este día fue a las {send_cutoff_hour()}:{send_cutoff_minute():02d}. "
            f"Programa para otro día.",
            status_code=409,
        )

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
    if not day_send_open(day):
        raise APIError(
            f"El cierre para este día fue a las {send_cutoff_hour()}:{send_cutoff_minute():02d}. "
            f"Programa para otro día.",
            status_code=409,
        )

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
    from src.editor_auto.config import manual_approval_enabled

    user = _resolve_user(claims)
    jobs_meta = _get_day_jobs(user.id, day)
    all_jobs = queue.get_all()
    by_id = {j.id: j for j in all_jobs}
    terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}

    # Posición en cola: solo para clientes con PLAN (en prueba lo controla el
    # admin). Rank entre los PENDING en orden de encolado (1 = el siguiente).
    show_queue_pos = _user_has_plan(user)
    pos_map: dict[str, int] = {}
    if show_queue_pos:
        pending = [j for j in all_jobs if j.status == JobStatus.PENDING]
        pos_map = {j.id: i + 1 for i, j in enumerate(pending)}

    gate = manual_approval_enabled()
    approved = _approved_set(user.id, day)

    videos: list[dict] = []
    ready = 0
    review = 0
    done = 0
    for m in jobs_meta:
        job = by_id.get(m.get("job_id"))
        st = job.status if job else None
        score = _job_score(job) if (job and job.status == JobStatus.COMPLETED) else None
        if job and job.status in terminal:
            done += 1
        out_name = os.path.basename(job.result_path) if (job and job.result_path) else None
        passed = bool(
            job and job.status == JobStatus.COMPLETED and out_name
            and (score is None or score >= _MIN_SCORE)
        )
        # Con gate ON, el vídeo solo es visible al cliente si el admin lo aprobó.
        is_approved = (not gate) or (out_name in approved if out_name else False)
        is_ready = passed and is_approved
        if is_ready:
            ready += 1
        elif passed and not is_approved:
            review += 1  # listo pero pendiente de revisión del equipo

        running = bool(job and job.status == JobStatus.RUNNING)
        queue_pos = pos_map.get(m.get("job_id")) if (job and job.status == JobStatus.PENDING) else None

        videos.append({
            "source": m.get("filename"),
            "filename": out_name if is_ready else None,
            "score": score,
            "ready": is_ready,
            "in_review": bool(passed and not is_approved),
            "running": running,
            "queue_position": queue_pos,
            "status": st.value if st else "unknown",
        })

    # all_done para el cliente = todos terminados Y (sin gate o todos resueltos:
    # aprobados o caídos). Con gate, si hay pendientes de revisión, no es "listo".
    all_terminal = bool(jobs_meta) and done == len(jobs_meta)
    all_done = all_terminal and review == 0
    # Fallback de aviso por email para el caso gate-OFF (sin paso de aprobación):
    # cuando el día queda completo. Idempotente (flag webday_notified).
    if all_done and ready > 0:
        _maybe_notify_ready(user, day, queue)
    return {
        "day": day,
        "total": len(jobs_meta),
        "ready": ready,
        "review": review,
        "all_done": all_done,
        "videos": videos,
    }


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


# ═══════════════════════ ADMIN — aprobación manual (API key) ═══════════════════════

class ApproveRequest(BaseModel):
    user_id: str
    day: str
    filename: str
    approve: bool = True


@router.get("/admin/pending")
def web_admin_pending(
    _: Annotated[str, Depends(get_current_user)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    """Lista los vídeos TERMINADOS y ≥90 que esperan tu aprobación (gate ON).
    El admin los revisa con el reproductor y los aprueba uno a uno."""
    r = get_editor_redis()
    by_id = {j.id: j for j in queue.get_all()}
    repo = UserRepo()
    items: list[dict] = []
    for entry in (r.smembers(_SENT_INDEX_KEY) or []):
        try:
            uid, day = entry.rsplit(":", 1)
        except ValueError:
            continue
        if not is_valid_day(day):
            continue
        user = repo.get(uid)
        uname = user.name if user else uid
        approved = _approved_set(uid, day)
        for m in _get_day_jobs(uid, day):
            job = by_id.get(m.get("job_id"))
            if not (job and job.status == JobStatus.COMPLETED and job.result_path):
                continue
            out_name = os.path.basename(job.result_path)
            score = _job_score(job)
            if score is not None and score < _MIN_SCORE:
                continue  # los <90 no se ofrecen al cliente (irán a reedición)
            if out_name in approved:
                continue
            items.append({
                "user_id": uid,
                "user_name": uname,
                "day": day,
                "source": m.get("filename"),
                "filename": out_name,
                "score": score,
            })
    return {"pending": items, "count": len(items)}


@router.post("/admin/approve")
def web_admin_approve(
    _: Annotated[str, Depends(get_current_user)],
    payload: ApproveRequest,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    """Aprueba (o revoca) un vídeo para que el cliente lo vea. Al aprobar, si el
    día queda completo y el cliente activó el aviso, le manda el email."""
    if not is_valid_day(payload.day):
        raise ValidationError("Día inválido.", details={"day": payload.day})
    out = _safe_name(payload.filename)
    if payload.approve:
        _approve_output(payload.user_id, payload.day, out)
        user = UserRepo().get(payload.user_id)
        if user is not None:
            _maybe_notify_ready(user, payload.day, queue)
    else:
        _unapprove_output(payload.user_id, payload.day, out)
    return {"ok": True, "approved": payload.approve}


@router.get("/admin/stream")
def web_admin_stream(
    user_id: str,
    day: str,
    file: str,
    key: Annotated[str | None, Query()] = None,
) -> FileResponse:
    """Stream del vídeo de salida para el reproductor del panel admin. Auth por
    query `key` (un <video src> no puede mandar headers) validada contra API_KEY."""
    from src.api.config import get_settings as _get_api_settings
    api_key = _get_api_settings().api_key
    if api_key and key != api_key:
        from src.api.exceptions import UnauthorizedError
        raise UnauthorizedError("API key inválida o ausente.")
    if not is_valid_day(day):
        raise ValidationError("Día inválido.", details={"day": day})
    user = UserRepo().get(user_id)
    if user is None:
        raise UserNotFoundError("Usuario no encontrado.", details={"user_id": user_id})
    path = os.path.join(user_output_day_folder(user.name, day), _safe_name(file))
    if not os.path.exists(path):
        raise UserNotFoundError("Vídeo no encontrado.", details={"file": file})
    return FileResponse(path, media_type="video/mp4", filename=_safe_name(file))
