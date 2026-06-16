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
_SENT_FILES_KEY = "webday_sentfiles:"   # set de filenames de ENTRADA ya encolados por user/día
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


def _sent_files(user_id: str, day: str) -> set[str]:
    """Filenames de entrada ya mandados a edición este día (no se re-encolan)."""
    try:
        return set(get_editor_redis().smembers(f"{_SENT_FILES_KEY}{user_id}:{day}") or [])
    except Exception:
        return set()


def _mark_files_sent(user_id: str, day: str, names: list[str]) -> None:
    r = get_editor_redis()
    for n in names:
        r.sadd(f"{_SENT_FILES_KEY}{user_id}:{day}", n)


_CARRIED_KEY = "webday_carried:"  # set de filenames movidos AQUÍ por el sweeper


def _carried_files(user_id: str, day: str) -> set[str]:
    """Borradores que el sweeper MOVIÓ a este día (para avisar al cliente)."""
    try:
        return set(get_editor_redis().smembers(f"{_CARRIED_KEY}{user_id}:{day}") or [])
    except Exception:
        return set()


def _clear_carried(user_id: str, day: str, names: list[str]) -> None:
    """Quita la marca de 'movido' (al enviarse o borrarse → ya no es aviso)."""
    r = get_editor_redis()
    for n in names:
        try:
            r.srem(f"{_CARRIED_KEY}{user_id}:{day}", n)
        except Exception:
            pass


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
            passed = bool(job.status == JobStatus.COMPLETED and out_name and _job_deliverable(job, score))
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


def _is_admin(user: EditorUser) -> bool:
    """True si la cuenta web vinculada tiene rol ADMIN. El admin no tiene el
    tope de 'mandar a edición una vez al día' ni el límite diario de vídeos:
    puede subir y mandar a editar tantas veces como quiera (testing/operación).
    El resto de planes mantienen el límite de 1 envío/día."""
    try:
        from src.editor_auto.repos.web_account_repo import get_web_account_repo
        acc = get_web_account_repo().get(user.account_email) or {}
        return (acc.get("role") or "").strip().lower() == "admin"
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


def _append_day_jobs(user_id: str, day: str, jobs: list[dict]) -> None:
    """Añade trabajos a los ya registrados del día (envíos incrementales)."""
    cur = _get_day_jobs(user_id, day)
    cur.extend(jobs)
    _save_day_jobs(user_id, day, cur)


def _user_plan(user: EditorUser):
    """Plan activo del usuario (o None si trial/sin plan)."""
    sub = user.subscription
    if sub and sub.status in ("active", "trial"):
        from src.editor_auto.repos import PlanRepo
        return PlanRepo().get(sub.plan_id)
    return None


def _effective_daily_limit(user: EditorUser, plan) -> int:
    """Límite de vídeos/día efectivo. 0 = ilimitado. El override por usuario
    gana al del plan."""
    if user.daily_video_limit_override is not None:
        return max(0, int(user.daily_video_limit_override))
    return int(plan.daily_video_limit) if plan else 0


def _day_processing_start(day: str, start_hour: int) -> float:
    """Epoch (UTC) en que ABRE la ventana de procesamiento de `day`. Los vídeos
    programados para un día futuro no se editan hasta este momento."""
    from datetime import datetime, timezone
    y, m, d = (int(x) for x in day.split("-"))
    return datetime(y, m, d, max(0, min(23, start_hour)), 0, 0, tzinfo=timezone.utc).timestamp()


def _get_day_jobs(user_id: str, day: str) -> list[dict]:
    data = get_editor_redis().get_json(f"{_JOBS_KEY}{user_id}:{day}")
    return data if isinstance(data, list) else []


def _read_audit(job) -> dict | None:
    """Lee el `audit` del diagnostic JSON del job (score, needs_requeue,
    fallos de palabra). None si no hay diagnostic."""
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
                return diag.get("audit") or {}
            except Exception:
                return None
    return None


def _job_score(job) -> int | None:
    audit = _read_audit(job)
    if not audit:
        return None
    score = audit.get("quality_score")
    return int(score) if score is not None else None


def _job_deliverable(job, score: int | None) -> bool:
    """El render es entregable al cliente si:
      · pasa el score mínimo (calidad acústica / pocos silencios), Y
      · NO tiene fallos de PALABRA marcados (needs_requeue): un sobrante o una
        palabra perdida RETIENE la entrega aunque el score quede ≥90 (un solo
        fallo deja 92 y antes se entregaba). Los silencios no marcan esto.
    Si no hay diagnostic (score None) no bloqueamos por audit."""
    if score is not None and score < _MIN_SCORE:
        return False
    audit = _read_audit(job)
    if audit and audit.get("needs_requeue"):
        return False
    # Tercer gate: COHERENCIA (que el vídeo tenga SENTIDO). Redundante con
    # needs_requeue (el juez ya lo marca) pero explícito → sobrevive a cambios
    # futuros que limpien needs_requeue. Un 100 solo se entrega si el sentido
    # también pasó.
    if (
        audit
        and audit.get("coherence_score") is not None
        and int(audit.get("coherence_score") or 0) < 100
        and audit.get("coherence_needs_requeue")
    ):
        return False
    return True


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
    # Envíos incrementales: el día ya NO se bloquea por completo al primer envío.
    # Listamos solo los BORRADORES (subidos pero aún no mandados a edición); los
    # ya enviados se siguen en /output. El día acepta más subidas mientras no
    # pase el cierre y no se alcance el tope diario.
    sent = _sent_files(user.id, day)
    has_jobs = bool(_get_day_jobs(user.id, day))
    # Admin puede seguir subiendo y mandando a editar tras el primer envío →
    # el día sigue "abierto" para él aunque ya tenga jobs.
    is_admin = _is_admin(user)
    # PERF: listar los borradores hace una llamada a la Drive API (lenta) y SOLO
    # importa cuando el día sigue ABIERTO para subir (sin envíos y antes del
    # cierre). Si ya se envió (has_jobs) o pasó el cierre, los borradores no se
    # muestran → nos saltamos Drive y el día carga casi al instante (era el
    # cuello de botella de "Obteniendo tus vídeos…" en días ya entregados).
    can_be_open = day_send_open(day) and (is_admin or not has_jobs)
    if can_be_open:
        all_files = drive_uploads.list_day_files(user.name, day)
        drafts = [v for v in all_files if v.get("filename") not in sent]
        draft_names = {v.get("filename") for v in drafts}
        carried = sorted(_carried_files(user.id, day) & draft_names)
        open_day = len(all_files) < _MAX_FILES_PER_DAY
    else:
        drafts = []
        carried = []
        open_day = False
    return {
        "day": day,
        "locked": not open_day,
        "open": open_day,
        "has_jobs": has_jobs,
        "videos": drafts,
        "carried": carried,
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
    name = _safe_name(payload.filename)
    # Solo se pueden borrar BORRADORES (no enviados). Los ya mandados a edición
    # están en proceso y no se tocan.
    if payload.filename in _sent_files(user.id, payload.day) or name in _sent_files(user.id, payload.day):
        raise APIError("Este vídeo ya se mandó a edición; no se puede borrar.", status_code=409)
    ok = drive_uploads.delete_day_file(user.name, payload.day, name)
    if not ok:
        raise UserNotFoundError("Vídeo no encontrado.", details={"filename": payload.filename})
    _clear_carried(user.id, payload.day, [name])
    sent = _sent_files(user.id, payload.day)
    drafts = [v for v in drive_uploads.list_day_files(user.name, payload.day) if v.get("filename") not in sent]
    return {"ok": True, "videos": drafts}


# ─────────────────────────── Mandar a edición ───────────────────────────

class SendToEditRequest(BaseModel):
    day: str


def _enqueue_video(
    queue: JobQueue, user: EditorUser, mount_path: Path, day: str,
    *, plan=None, scheduled_for: float | None = None, is_admin: bool = False,
) -> str:
    """Encola un vídeo leyéndolo DIRECTO del rclone-mount (input_path = ruta
    del mount). El runner lee on-demand al procesar — sin copia previa que
    descargue bytes durante el send-to-edit.

    `scheduled_for` (epoch UTC) difiere la edición hasta que abra la ventana del
    día programado: el worker ignora el job hasta esa hora y luego coge los del
    día por orden de llegada (FIFO). None = editar cuanto antes."""
    enabled = [s for s in user.tool_flow if s.enabled]
    if not enabled:
        raise APIError(
            "Tu cuenta aún no tiene un flujo de edición configurado. Configura tu estilo.",
            status_code=409,
        )
    if any(s.tool_id == TOOL_SILENCE_CUTTER_SCRIPTED for s in enabled):
        raise APIError("Tu flujo requiere guion; no compatible con subida web.", status_code=409)

    # Validación de acceso (la CUOTA por día la controla el caller con el
    # recuento de jobs del día; aquí solo subscripción + tools permitidas).
    if user.subscription and user.subscription.status not in ("active", "trial"):
        raise APIError("Tu suscripción no está activa.", status_code=402)
    tools_used = [s.tool_id for s in enabled]
    # ADMIN: sin filtro de plan por herramienta (usa todas las de su estilo).
    if plan and plan.allowed_tools and not is_admin:
        for tid in tools_used:
            if tid not in plan.allowed_tools:
                raise APIError(
                    f"Tu plan no incluye la herramienta '{tid}'.", status_code=402,
                )

    try:
        from src.utils import load_config
        temp_folder = load_config()["paths"]["temp_folder"]
    except Exception:
        temp_folder = "./temp_work"

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
    job = queue.enqueue(
        JobMode.EDITOR_AUTO, title=title, params=params, scheduled_for=scheduled_for,
    )
    # Solo contamos contra la cuota rolling "de hoy" cuando se edita YA (hoy);
    # los programados a futuro cuentan por su propio día (recuento de day_jobs).
    if scheduled_for is None:
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
    is_admin = _is_admin(user)
    # Tope de 1 envío/día — NO aplica a admin (puede mandar a editar varias veces).
    if _get_day_jobs(user.id, day) and not is_admin:
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
    plan = _user_plan(user)
    tool_flow = build_tool_flow((account or {}).get("styleConfig"))
    # El plan limita las herramientas: si el estilo del cliente incluye una tool
    # que su plan NO cubre (p.ej. sticker_arrow en Starter), la DESCARTAMOS en
    # silencio en vez de fallar el envío — el vídeo se edita con las permitidas.
    # ADMIN: sin filtro de plan → usa TODAS las tools de su estilo (la flecha CTA
    # incluida, aunque su plan sea Starter) — para testear/operar sin límites.
    if plan and plan.allowed_tools and not is_admin:
        tool_flow = [s for s in tool_flow if s.tool_id in plan.allowed_tools]
    user.tool_flow = tool_flow
    UserRepo().save(user)

    # Envíos incrementales: solo mandamos los borradores NUEVOS (no enviados
    # antes este día). Así el cliente puede mandar 1 ahora y el resto luego,
    # hasta agotar su cuota del plan o el cierre del día.
    sent = _sent_files(user.id, day)
    videos = [v for v in drive_uploads.list_day_files(user.name, day) if v.get("filename") not in sent]
    if not videos:
        raise ValidationError("No hay vídeos nuevos para mandar a edición.", details={"day": day})

    # Programación diferida: los vídeos de un día se editan cuando ABRE la
    # ventana de procesamiento de ese día (no al pulsar el botón). Si el día ya
    # está abierto (hoy, dentro de ventana), `scheduled_for=None` → se editan
    # cuanto antes, por orden de llegada (FIFO en la cola).
    start_hour = plan.processing_window_start_hour if plan else 0
    sched_epoch = _day_processing_start(day, start_hour)
    scheduled_for = sched_epoch if sched_epoch > time.time() else None

    # Cuota por DÍA del plan (cuenta los ya programados para ese día). Admin =
    # sin tope (0 = ilimitado), para poder mandar a editar tantas veces como
    # quiera el mismo día.
    eff_daily = 0 if is_admin else _effective_daily_limit(user, plan)
    already = len(_get_day_jobs(user.id, day))
    remaining = (eff_daily - already) if eff_daily > 0 else None

    enqueued: list[dict] = []
    errors: list[dict] = []
    for v in videos:
        if remaining is not None and len(enqueued) >= remaining:
            errors.append({
                "filename": v["filename"],
                "error": (
                    f"Has alcanzado tu límite de {eff_daily} vídeos para este día. "
                    f"Programa el resto para otro día."
                ),
            })
            break
        mount_path = Path(user_input_day_folder(user.name, day)) / v["filename"]
        try:
            job_id = _enqueue_video(queue, user, mount_path, day, plan=plan, scheduled_for=scheduled_for, is_admin=is_admin)
            enqueued.append({"filename": v["filename"], "job_id": job_id})
        except APIError as e:
            errors.append({"filename": v["filename"], "error": e.message})
            break

    if enqueued:
        _lock_day(user.id, day)  # indexa el día para el panel admin / summary
        _append_day_jobs(user.id, day, enqueued)
        names = [e["filename"] for e in enqueued]
        _mark_files_sent(user.id, day, names)
        _clear_carried(user.id, day, names)  # ya enviados → quitar aviso de movido
        # Descuenta los vídeos de prueba (solo clientes SIN plan). El contador
        # visible (web "Prueba · N" + panel config) vive en la cuenta web.
        if not (account or {}).get("planId"):
            try:
                repo = get_web_account_repo()
                cur = int((account or {}).get("trialVideos") or 0)
                repo.set_trial_videos(user.account_email, max(0, cur - len(enqueued)))
            except Exception:
                pass

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
            and _job_deliverable(job, score)
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
        # Programado a futuro: PENDING con scheduled_for que aún no llegó → se
        # editará cuando abra la ventana de su día (no está "en cola" todavía).
        sched = getattr(job, "scheduled_for", None) if job else None
        is_scheduled = bool(job and job.status == JobStatus.PENDING and sched and sched > time.time())

        videos.append({
            "source": m.get("filename"),
            "filename": out_name if is_ready else None,
            "score": score,
            "ready": is_ready,
            "in_review": bool(passed and not is_approved),
            "running": running,
            "queue_position": None if is_scheduled else queue_pos,
            "scheduled": is_scheduled,
            "status": st.value if st else "unknown",
        })

    # all_done para el cliente = todos terminados Y (sin gate o todos resueltos:
    # aprobados o caídos). Con gate, si hay pendientes de revisión, no es "listo".
    all_terminal = bool(jobs_meta) and done == len(jobs_meta)
    all_done = all_terminal and review == 0
    # ENTREGA TODO-O-NADA: no mostrar NINGÚN vídeo como listo/descargable hasta
    # que TODO el lote del día esté resuelto (con gate: todos aprobados; sin
    # gate: todos ≥90). Así el cliente nunca recibe 1 de 2 — ve el día completo
    # de golpe, junto con el email. Hasta entonces, los ya terminados se
    # muestran "en revisión" (no descargables).
    if not all_done:
        for v in videos:
            if v["ready"] or v["in_review"]:
                v["ready"] = False
                v["filename"] = None
                v["in_review"] = True
        ready = 0
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


@router.get("/days-summary")
def web_days_summary(
    claims: Annotated[TicketClaims, Depends(require_web_ticket)],
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    """Resumen de estado por día (para colorear el calendario del cliente):
    cada día enviado → {total, ready, review, in_progress, all_done}."""
    from src.editor_auto.config import manual_approval_enabled

    user = _resolve_user(claims)
    gate = manual_approval_enabled()
    by_id = {j.id: j for j in queue.get_all()}
    terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
    days: dict[str, dict] = {}
    for day in (get_editor_redis().smembers(f"{_SENT_DAYS_KEY}{user.id}") or []):
        if not is_valid_day(day):
            continue
        approved = _approved_set(user.id, day)
        jobs_meta = _get_day_jobs(user.id, day)
        total = len(jobs_meta)
        ready = review = done = 0
        for m in jobs_meta:
            job = by_id.get(m.get("job_id"))
            if job and job.status in terminal:
                done += 1
            out_name = os.path.basename(job.result_path) if (job and job.result_path) else None
            passed = bool(job and job.status == JobStatus.COMPLETED and out_name
                          and _job_deliverable(job, _job_score(job)))
            is_approved = (not gate) or (out_name in approved if out_name else False)
            if passed and is_approved:
                ready += 1
            elif passed and not is_approved:
                review += 1
        all_done = total > 0 and done == total and review == 0
        days[day] = {
            "total": total, "ready": ready, "review": review,
            "in_progress": total - done, "all_done": all_done,
        }
    return {"days": days}


@router.get("/download")
def web_download(
    day: str,
    file: str,
    ticket: Annotated[str, Query(...)],
    source: Annotated[bool, Query()] = False,
) -> FileResponse:
    """Sirve un vídeo del rclone-mount. Por defecto el editado de `salida/<día>/`;
    con `source=true`, el borrador subido de `entrada/<día>/` (para previsualizar
    lo que el cliente acaba de subir antes de mandarlo a edición)."""
    claims = verify_ticket(ticket)
    if not is_valid_day(day):
        raise ValidationError("Día inválido (YYYY-MM-DD).", details={"day": day})
    user = _resolve_user(claims)
    folder = user_input_day_folder(user.name, day) if source else user_output_day_folder(user.name, day)
    safe = _safe_name(file)
    path = os.path.join(folder, safe)
    if not os.path.exists(path):
        raise UserNotFoundError("Vídeo no encontrado.", details={"file": file})
    # Nombre de descarga limpio: quita el prefijo timestamp del upload
    # (1780695599_IMG_9750_editado.mp4 → IMG_9750_editado.mp4).
    nice = re.sub(r"^\d{8,}_", "", safe) or safe
    return FileResponse(path, media_type="video/mp4", filename=nice)


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
    from src.editor_auto.config import manual_approval_enabled

    # Con el gate INACTIVO no se retiene nada: los vídeos ya se entregan al
    # cliente solos, así que no hay "pendientes de aprobar". (Antes la lista
    # ignoraba el toggle y mostraba terminados-no-aprobados aunque ya estuvieran
    # entregados, lo que confundía.)
    if not manual_approval_enabled():
        return {"pending": [], "count": 0, "gate": False}

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
            if not _job_deliverable(job, score):
                continue  # <90 o con fallo de palabra → no se ofrece (irá a reedición)
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
    return {"pending": items, "count": len(items), "gate": True}


@router.get("/admin/user-pipeline")
def web_admin_user_pipeline(
    user_id: str,
    _: Annotated[str, Depends(get_current_user)],
    queue: Annotated[JobQueue, Depends(get_queue)],
    day: str | None = None,
) -> dict:
    """Estado de edición de un usuario WEB clasificado para el admin, acotado
    a UN día (por defecto HOY — Europe/Madrid):

      · `in_process` — mandados a edición pero AÚN NO disponibles al cliente:
        en cola, editándose, o terminados pendientes de aprobar (gate ON) /
        re-edición (score <90).
      · `ready` — entregados ese día (aprobados con gate, o ≥90 con gate OFF).

    Acotar a HOY tiene sentido para el admin: "qué pasa hoy con este usuario".
    El estado real del flujo web vive en la COLA (jobs), no en carpetas."""
    from datetime import datetime
    from src.editor_auto.config import manual_approval_enabled
    try:
        from zoneinfo import ZoneInfo
        _tz = ZoneInfo("Europe/Madrid")
    except Exception:
        _tz = None

    target_day = day if (day and is_valid_day(day)) else datetime.now(_tz).date().isoformat()
    r = get_editor_redis()
    by_id = {j.id: j for j in queue.get_all()}
    gate = manual_approval_enabled()
    terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
    in_process: list[dict] = []
    ready: list[dict] = []
    sent_days = set(r.smembers(f"{_SENT_DAYS_KEY}{user_id}") or [])
    for day in ([target_day] if target_day in sent_days else []):
        if not is_valid_day(day):
            continue
        approved = _approved_set(user_id, day)
        for m in _get_day_jobs(user_id, day):
            job = by_id.get(m.get("job_id"))
            src = m.get("filename")
            if job is None:
                continue
            out_name = os.path.basename(job.result_path) if job.result_path else None
            score = _job_score(job) if job.status == JobStatus.COMPLETED else None
            base = {"day": day, "source": src, "filename": out_name, "score": score}
            if job.status == JobStatus.RUNNING:
                in_process.append({**base, "state": "editing", "label": "Editándose"})
            elif job.status == JobStatus.PENDING:
                sched = getattr(job, "scheduled_for", None)
                if sched and sched > time.time():
                    in_process.append({**base, "state": "scheduled", "label": "Programado"})
                else:
                    in_process.append({**base, "state": "queued", "label": "En cola"})
            elif job.status == JobStatus.COMPLETED and out_name:
                passed = _job_deliverable(job, score)
                is_approved = (not gate) or (out_name in approved)
                if passed and is_approved:
                    ready.append({**base, "state": "delivered", "label": "Entregado"})
                elif passed and not is_approved:
                    in_process.append({**base, "state": "review", "label": "En revisión"})
                else:
                    in_process.append({**base, "state": "requeue", "label": "Re-edición (fallo)"})
            elif job.status in terminal:  # FAILED / CANCELLED
                in_process.append({**base, "state": "failed", "label": "Fallido"})
    return {
        "day": target_day,
        "in_process": in_process,
        "ready": ready,
        "n_in_process": len(in_process),
        "n_ready": len(ready),
        "gate": gate,
    }


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


class RequeueRequest(BaseModel):
    user_id: str
    day: str
    source: str
    filename: str | None = None


@router.post("/admin/requeue")
def web_admin_requeue(
    _: Annotated[str, Depends(get_current_user)],
    payload: RequeueRequest,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> dict:
    """Re-edita un vídeo del día (nuevo intento). Útil si el resultado no te
    convence: re-encola el original de entrada/<día>/ y el cliente lo ve
    'en cola/editando' otra vez. Quita su aprobación previa si la tenía."""
    if not is_valid_day(payload.day):
        raise ValidationError("Día inválido.", details={"day": payload.day})
    user = UserRepo().get(payload.user_id)
    if user is None:
        raise UserNotFoundError("Usuario no encontrado.", details={"user_id": payload.user_id})

    src = _safe_name(payload.source)
    mount_path = Path(user_input_day_folder(user.name, payload.day)) / src
    if not os.path.exists(mount_path):
        raise UserNotFoundError(
            "No encuentro el vídeo original para re-editar.",
            details={"source": payload.source},
        )
    try:
        job_id = _enqueue_video(queue, user, mount_path, payload.day)
    except APIError:
        raise

    # Apuntar la meta del día al NUEVO job para este source (web_output lo sigue).
    jobs = _get_day_jobs(user.id, payload.day)
    found = False
    for m in jobs:
        if m.get("filename") == src:
            m["job_id"] = job_id
            found = True
    if not found:
        jobs.append({"filename": src, "job_id": job_id})
    _save_day_jobs(user.id, payload.day, jobs)

    # El nuevo intento debe volver a "pendiente de aprobar": quita la aprobación
    # del output anterior (mismo nombre `<stem>_editado.mp4`).
    if payload.filename:
        _unapprove_output(user.id, payload.day, _safe_name(payload.filename))
    # Permite reenviar el email de "listos" cuando se vuelva a completar.
    try:
        get_editor_redis().delete(f"{_NOTIFIED_KEY}{user.id}:{payload.day}")
    except Exception:
        pass
    return {"ok": True, "job_id": job_id}


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
