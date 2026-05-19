"""Endpoints del nicho 🏗️ Construcción POV.

1 endpoint POST /enqueue (multipart con vídeo + form params del estilo
de subtítulos + voice_id seleccionada).
"""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from fastapi.responses import Response

from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import (
    APIError,
    InvalidEnqueueRequestError,
    PresetNotFoundError,
    ValidationError,
)
from src.api.schemas.creator_reward.construccion_pov import (
    ConstruccionPovEnqueueResponse,
    ConstruccionPovGenerateScriptResponse,
    ConstruccionPovPresetListResponse,
    ConstruccionPovPresetResponse,
)
from src.construccion_pov.preflight import PreflightFailure, run_preflight
from src.api.temp_storage import resolve_relative, to_relative, upload_subdir
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus


router = APIRouter(
    prefix="/api/v1/creator-reward/construccion-pov",
    tags=["creator-reward · construccion-pov"],
    dependencies=[Depends(get_current_user)],
)


_ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}
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


async def _accept_video_upload(
    file: UploadFile,
) -> tuple[bytes, str]:
    """Valida ext + tamaño y devuelve `(bytes, ext)`."""
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
    return contents, ext


def _resolve_or_save_upload(
    contents: bytes | None,
    ext: str | None,
    input_path_relative: str | None,
):
    """Devuelve `Path` absoluto + `str` rel_path. Acepta una de dos vías:
      - file (bytes ya leídos): guarda en temp_work/api_uploads/construccion_pov/
      - input_path_relative: lo resuelve y valida que existe (reuso post
        /generate-script para no resubir el archivo).
    """
    from pathlib import Path
    if input_path_relative:
        try:
            abs_path = resolve_relative(input_path_relative)
        except ValueError as e:
            raise ValidationError(
                f"input_path_relative inválido: {e}",
                details={"input_path_relative": input_path_relative},
            )
        if not abs_path.exists():
            raise ValidationError(
                "El archivo referenciado por input_path_relative no existe (¿expirado?).",
                details={"input_path_relative": input_path_relative},
            )
        return abs_path, to_relative(abs_path)
    if contents is None or not ext:
        raise ValidationError(
            "Debes enviar 'file' (multipart) o 'input_path_relative' (string).",
        )
    folder = upload_subdir("construccion_pov")
    dest = folder / f"pov_in_{int(time.time())}{ext}"
    try:
        dest.write_bytes(contents)
    except OSError as e:
        raise APIError(
            f"No se pudo escribir el archivo en disco: {e}",
            details={"path": str(dest)},
        )
    return dest, to_relative(dest)


# ---------------------------------------------------------------------------
# POST /generate-script — paso 1 del flujo semi-automático
# ---------------------------------------------------------------------------
@router.post(
    "/generate-script",
    response_model=ConstruccionPovGenerateScriptResponse,
)
async def generate_script_step(
    file: Annotated[UploadFile | None, File()] = None,
    input_path_relative: Annotated[str | None, Form()] = None,
    gemini_model: Annotated[str, Form()] = "gemini-2.5-pro",
) -> ConstruccionPovGenerateScriptResponse:
    """Sube el vídeo (o reusa upload previo via `input_path_relative`),
    valida env Gemini, calcula duración real y devuelve el guion candidato.

    NO encola nada. NO llama a MiniMax. Coste = solo Gemini (~$0.005 Flash
    o ~$0.08 Pro). El cliente lo muestra al usuario para que acepte / edite
    / regenere antes de pagar TTS + render.
    """
    # Validar env Gemini antes de tocar archivos (early fail).
    import os
    if not (
        os.getenv("GOOGLE_GEMINI_KEY_FREE")
        or os.getenv("GOOGLE_GEMINI_KEY_PAID")
        or os.getenv("GOOGLE_AI_API_KEY")
        or os.getenv("GOOGLE_GEMINI_KEY")
    ):
        raise InvalidEnqueueRequestError(
            "Sin API key de Gemini — define GOOGLE_GEMINI_KEY_FREE/PAID en .env.",
            details={"field": "env.GOOGLE_GEMINI_KEY_*"},
        )

    contents: bytes | None = None
    ext: str | None = None
    if file is not None and (file.filename or ""):
        contents, ext = await _accept_video_upload(file)
    abs_path, rel_path = _resolve_or_save_upload(
        contents, ext, input_path_relative,
    )

    # ffprobe duración real
    from src.construccion_pov.pipeline import _probe_duration_seconds
    try:
        duration = _probe_duration_seconds(str(abs_path))
    except Exception as e:
        raise InvalidEnqueueRequestError(
            f"ffprobe no pudo leer la duración: {e}",
            details={"field": "file"},
        )
    if duration < 1.0 or duration > 180.0:
        raise InvalidEnqueueRequestError(
            f"Duración fuera de rango ({duration:.1f}s). Min 1s, max 180s.",
            details={"duration_seconds": duration},
        )

    # Gemini → guion
    from src.construccion_pov.script_generator import (
        estimate_target_chars,
        generate_script,
    )
    target_chars, _ = estimate_target_chars(duration)
    try:
        script_text = generate_script(
            str(abs_path),
            video_duration_s=duration,
            model=gemini_model,
        )
    except Exception as e:
        raise APIError(
            f"Gemini falló al generar el guion: {e}",
            details={"model": gemini_model},
        )

    return ConstruccionPovGenerateScriptResponse(
        script=script_text,
        target_chars=target_chars,
        duration_seconds=duration,
        input_path_relative=rel_path,
        gemini_model=gemini_model,
    )


@router.post(
    "/enqueue",
    response_model=ConstruccionPovEnqueueResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enqueue_construccion_pov(
    queue: Annotated[JobQueue, Depends(get_queue)],
    voice_id: Annotated[str, Form(..., min_length=1)],
    font_path: Annotated[str, Form(..., min_length=1)],
    file: Annotated[UploadFile | None, File()] = None,
    input_path_relative: Annotated[str | None, Form()] = None,
    highlight_mode: Annotated[str, Form()] = "pill",
    highlight_color: Annotated[str, Form()] = "#FDD002",
    text_color: Annotated[str, Form()] = "#FFFFFF",
    stroke_color: Annotated[str, Form()] = "#000000",
    stroke_width: Annotated[int, Form()] = 4,
    case_mode: Annotated[str, Form()] = "UPPERCASE",
    font_scale: Annotated[float, Form()] = 0.085,
    max_words: Annotated[int, Form()] = 3,
    y_position: Annotated[float, Form()] = 0.78,
    pill_enabled: Annotated[bool, Form()] = True,
    max_width: Annotated[float, Form()] = 0.85,
    sync_offset: Annotated[int, Form()] = 0,
    upscale_1080p: Annotated[bool, Form()] = False,
    saturation: Annotated[float, Form()] = 1.25,
    pulse_zoom: Annotated[bool, Form()] = True,
    mirror: Annotated[bool, Form()] = False,
    whisper_model_size: Annotated[str, Form()] = "small",
    quality_label: Annotated[str, Form()] = "1080p (Lento)",
    gemini_model: Annotated[str, Form()] = "gemini-2.5-pro",
    manual_script: Annotated[str | None, Form()] = None,
) -> ConstruccionPovEnqueueResponse:
    """Encola el job. Acepta `file` (multipart) o `input_path_relative`
    (reusa el upload del paso /generate-script).

    Si `manual_script` viene relleno, el runner se salta Gemini → coste
    = solo MiniMax TTS (~$0.05) + Whisper local + ffmpeg.
    """
    contents: bytes | None = None
    ext: str | None = None
    if file is not None and (file.filename or ""):
        contents, ext = await _accept_video_upload(file)
    dest, rel_path = _resolve_or_save_upload(
        contents, ext, input_path_relative,
    )

    try:
        from src.utils import load_config
        cfg = load_config()
    except Exception as e:
        raise APIError(
            f"No se pudo cargar config/config.json: {e}",
            details={"hint": "Verifica TIKTOK_ROOT_PATH."},
        )

    # -----------------------------------------------------------------
    # Pre-flight checks: ANTES de encolar y ANTES de gastar dinero.
    # Falla aquí → 422 invalid_enqueue_request → cliente lo ve sin que
    # se haya invocado Gemini ni MiniMax. Si cualquier check pasa, se
    # devuelve además el `minimax_voice_id` resuelto (sin el prefijo
    # `preset_*`) para que el runner llame a MiniMax con el id correcto.
    # -----------------------------------------------------------------
    try:
        preflight = run_preflight(
            input_path=dest,
            voice_id=voice_id,
            font_path=font_path,
        )
    except PreflightFailure as e:
        # Limpiar el archivo subido para no ocupar disco con uploads
        # que nunca llegan a la cola.
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        raise InvalidEnqueueRequestError(e.message, details=e.details)
    resolved_voice_id = preflight["minimax_voice_id"]

    # Proyectamos el N del archivo de salida `Construccion_<N>.mp4` para
    # que el título de la cola coincida con el filename final. N =
    # existing files en el folder + jobs POV pendientes/running + 1.
    # El runner usa este mismo N para escribir el archivo (con fallback
    # a timestamp si por race condition ya existe).
    import os as _os
    out_dir = _os.path.join(cfg["paths"]["output_folder"], "CONSTRUCCION_POV")
    existing_n = 0
    if _os.path.isdir(out_dir):
        existing_n = sum(
            1 for fn in _os.listdir(out_dir)
            if fn.startswith("Construccion_") and fn.endswith(".mp4")
        )
    pending_pov = sum(
        1 for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
        and j.mode == JobMode.CONSTRUCCION_POV
    )
    projected_n = existing_n + pending_pov + 1
    output_name = f"Construccion_{projected_n}.mp4"

    mode_suffix = " · ✏️ guion manual" if manual_script and manual_script.strip() else ""
    title = f"{output_name} · Construcción POV{mode_suffix}"

    params: dict[str, Any] = {
        "input_path": str(dest),
        "config": cfg,
        "voice_id": resolved_voice_id,
        "gemini_model": gemini_model,
        "manual_script": manual_script,
        "font_path": font_path,
        "highlight_mode": highlight_mode,
        "highlight_color": highlight_color,
        "text_color": text_color,
        "stroke_color": stroke_color,
        "stroke_width": stroke_width,
        "case_mode": case_mode,
        "font_scale": font_scale,
        "max_words": max_words,
        "y_position": y_position,
        "pill_enabled": pill_enabled,
        "max_width": max_width,
        "sync_offset": sync_offset,
        "upscale_1080p": upscale_1080p,
        "saturation": saturation,
        "pulse_zoom": pulse_zoom,
        "mirror": mirror,
        "whisper_model_size": whisper_model_size,
        "quality_label": quality_label,
        "output_name": output_name,
    }
    job = queue.enqueue(JobMode.CONSTRUCCION_POV, title=title, params=params)

    return ConstruccionPovEnqueueResponse(
        job_id=job.id,
        title=title,
        position_in_queue=_position_in_queue(queue, job.id),
        input_path_relative=rel_path,
    )


# ---------------------------------------------------------------------------
# GET /preview-prompt — devuelve el prompt completo de Gemini calibrado a
# una duración dada, listo para pegar en un Gem custom de Gemini y obtener
# el guion sin pagar nuestra cuota de Gemini API.
# ---------------------------------------------------------------------------
@router.get("/preview-prompt")
def preview_prompt(duration_seconds: float = 60.0) -> dict:
    """Devuelve el system prompt + target_chars/target_seconds calibrados
    a `duration_seconds`. La UI lo muestra en un modal con botón 'copiar'."""
    if duration_seconds < 5 or duration_seconds > 600:
        raise ValidationError(
            "duration_seconds debe estar entre 5 y 600.",
            details={"value": duration_seconds},
        )
    from src.construccion_pov.script_generator import (
        build_system_prompt,
        estimate_target_chars,
    )
    target_chars, target_seconds = estimate_target_chars(duration_seconds)
    return {
        "system_prompt": build_system_prompt(duration_seconds),
        "target_chars": target_chars,
        "target_seconds": target_seconds,
    }


# ---------------------------------------------------------------------------
# Presets — favoritos persistentes (namespace "pov" sobre `configs_store`)
# ---------------------------------------------------------------------------
_NS = "pov"


@router.get("/presets", response_model=ConstruccionPovPresetListResponse)
def list_pov_presets() -> ConstruccionPovPresetListResponse:
    from src.configs_store import is_available, list_configs
    if not is_available():
        return ConstruccionPovPresetListResponse(items=[], total=0)
    names = list_configs(namespace=_NS)
    return ConstruccionPovPresetListResponse(items=names, total=len(names))


@router.get("/presets/{name}", response_model=ConstruccionPovPresetResponse)
def get_pov_preset(name: str) -> ConstruccionPovPresetResponse:
    from src.configs_store import load_config
    config = load_config(name, namespace=_NS)
    if config is None:
        raise PresetNotFoundError(
            f"Preset POV '{name}' no encontrado.",
            details={"name": name},
        )
    return ConstruccionPovPresetResponse(name=name, config=config)


@router.put("/presets/{name}", response_model=ConstruccionPovPresetResponse)
def save_pov_preset(
    name: str,
    config: dict[str, Any],
) -> ConstruccionPovPresetResponse:
    if not name.strip():
        raise ValidationError("El nombre del preset no puede estar vacío.")
    from src.configs_store import is_available, save_config
    if not is_available():
        raise APIError(
            "Upstash Redis no configurado — no se pueden guardar presets.",
            details={"hint": "Define UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN."},
        )
    if not save_config(name, config, namespace=_NS):
        raise APIError(
            f"Fallo al guardar preset POV '{name}'.",
            details={"name": name},
        )
    return ConstruccionPovPresetResponse(name=name, config=config)


@router.delete("/presets/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pov_preset(name: str) -> Response:
    from src.configs_store import delete_config, is_available, load_config
    if not is_available():
        raise APIError("Upstash Redis no configurado.")
    if load_config(name, namespace=_NS) is None:
        raise PresetNotFoundError(
            f"Preset POV '{name}' no encontrado.",
            details={"name": name},
        )
    delete_config(name, namespace=_NS)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
