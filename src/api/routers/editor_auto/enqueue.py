"""POST /api/v1/editor-auto/enqueue — sube vídeo y encola el job."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import APIError, ValidationError
from src.api.schemas.editor_auto import EditorAutoEnqueueResponse
from src.api.temp_storage import to_relative, upload_subdir
from src.editor_auto.config import TOOL_SILENCE_CUTTER_SCRIPTED
from src.editor_auto.repos import UserRepo
from src.editor_auto.services import quota_service
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus


router = APIRouter(
    prefix="/api/v1/editor-auto",
    tags=["editor-auto · enqueue"],
    dependencies=[Depends(get_current_user)],
)


_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
_MAX_VIDEO_BYTES = 500 * 1024 * 1024  # 500 MB


def _position_in_queue(queue: JobQueue, job_id: str) -> int:
    pending_or_running = [
        j for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    for i, j in enumerate(pending_or_running):
        if j.id == job_id:
            return i
    return 0


@router.post(
    "/enqueue",
    response_model=EditorAutoEnqueueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enqueue_editor_auto(
    queue: Annotated[JobQueue, Depends(get_queue)],
    file: Annotated[UploadFile, File(...)],
    user_id: Annotated[str, Form(...)],
    script: Annotated[str, Form()] = "",
) -> EditorAutoEnqueueResponse:
    """Sube un vídeo + indica `user_id` del EditorUser que define el flujo.

    El runner cargará el usuario, reordenará sus herramientas habilitadas
    por `position_weight` y las ejecutará secuencialmente. Output final
    en `TIKTOK_EDITOR/Usuarios/<user>/salida/`.

    Si el flujo contiene `silence_cutter_scripted`, el campo `script` es
    OBLIGATORIO — el orchestrator lo inyecta en la config de esa tool.
    """
    repo = UserRepo()
    user = repo.get(user_id)
    if user is None or user.deleted:
        raise ValidationError(
            f"Usuario Editor Auto no encontrado o eliminado: {user_id}",
            details={"user_id": user_id},
        )
    enabled = [s for s in user.tool_flow if s.enabled]
    if not enabled:
        raise ValidationError(
            f"El usuario '{user.name}' no tiene herramientas habilitadas en "
            f"su flujo. Configura al menos una antes de generar.",
            details={"user_id": user_id, "user_name": user.name},
        )
    script_clean = (script or "").strip()
    needs_script = any(s.tool_id == TOOL_SILENCE_CUTTER_SCRIPTED for s in enabled)
    if needs_script and not script_clean:
        raise ValidationError(
            f"El usuario '{user.name}' tiene 'silence_cutter_scripted' en su "
            f"flujo — el guión es obligatorio para generar.",
            details={"user_id": user_id, "user_name": user.name},
        )

    filename = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_VIDEO_EXTS if filename.endswith(e)), "")
    if not ext:
        raise ValidationError(
            f"Formato no soportado: '{file.filename}'. "
            f"Acepta: {', '.join(sorted(_ALLOWED_VIDEO_EXTS))}.",
            details={"filename": file.filename},
        )

    contents = await file.read()
    if not contents:
        raise ValidationError("Archivo vacío.", details={"filename": file.filename})
    if len(contents) > _MAX_VIDEO_BYTES:
        raise ValidationError(
            f"El vídeo pesa {len(contents) / 1024 / 1024:.1f} MB, máximo "
            f"{_MAX_VIDEO_BYTES / 1024 / 1024:.0f} MB.",
            details={"size_bytes": len(contents)},
        )

    folder = upload_subdir("editor_auto")
    dest = folder / f"editor_in_{user.name}_{int(time.time())}{ext}"
    try:
        dest.write_bytes(contents)
    except OSError as e:
        raise APIError(
            f"No se pudo escribir el archivo en disco: {e}",
            details={"path": str(dest)},
        )

    # Temp folder para que el runner pase archivos intermedios entre tools.
    try:
        from src.utils import load_config
        cfg = load_config()
        temp_folder = cfg["paths"]["temp_folder"]
    except Exception:
        temp_folder = "./temp_work"

    enabled_steps = [s for s in user.tool_flow if s.enabled]
    tools_used = [s.tool_id for s in enabled_steps]
    tool_count = len(enabled_steps)
    title = f"{user.name} · {Path(file.filename or 'video').name} · {tool_count} tool(s)"

    # Check de cuota / plan / ventana horaria. Test users (sin subscription)
    # pasan siempre. Para users con plan, se valida límite diario, ventana
    # horaria, espaciado y tools permitidas. Si el plan no permite alguna
    # tool del flow, devolvemos 402 (Payment Required) para que el frontend
    # invite a upgrade.
    decision = quota_service.check_can_enqueue(user, tool_ids=tools_used)
    if not decision.ok:
        # Mapeamos kind → status HTTP coherente
        sc_map = {
            "no_subscription": 402,
            "inactive_subscription": 402,
            "tool_not_allowed": 402,
            "daily_limit": 429,
            "monthly_limit": 429,
            "outside_window": 425,    # Too Early
            "spacing": 425,
            "promo_exhausted": 402,
        }
        sc = sc_map.get(decision.kind, 429)
        raise APIError(
            decision.message,
            status_code=sc,
            details={
                "kind": decision.kind,
                "retry_after_seconds": decision.retry_after_seconds,
            },
        )

    params: dict[str, Any] = {
        "user_id": user.id,
        "user_name": user.name,
        "input_path": str(dest),
        "temp_folder": temp_folder,
        "tool_count": tool_count,
        # `tools_used` se lee en `dispatch_job` para llenar `cost_tracking.meta`
        # con `tools` + `tools_key` (combo ordenado para agrupar en /costs).
        "tools_used": tools_used,
        # Guion opcional — solo lo consume `silence_cutter_scripted`. Lo
        # inyecta el orchestrator dentro de `config["script"]` para esa
        # tool. Cualquier otra tool lo ignora.
        "script": script_clean,
    }
    job = queue.enqueue(JobMode.EDITOR_AUTO, title=title, params=params)

    # Incrementar cuota tras encolar exitosamente. Si falla persistir
    # (Redis caído), el job ya está en cola — no rollback porque el
    # vídeo ya se procesará y la siguiente cuota check leerá contadores
    # un poco desactualizados (mejor que perder el vídeo).
    try:
        quota_service.register_enqueue(user)
    except Exception:
        pass

    return EditorAutoEnqueueResponse(
        job_id=job.id,
        title=title,
        position_in_queue=_position_in_queue(queue, job.id),
        input_path_relative=to_relative(dest),
        user_name=user.name,
        tool_count=tool_count,
    )
