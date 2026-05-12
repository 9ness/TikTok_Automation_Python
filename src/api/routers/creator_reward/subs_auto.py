"""Endpoints del nicho 🎬 Subs sobre Vídeo.

2 endpoints:
- POST /transcribe (multipart con file → Whisper síncrono → words[])
- POST /enqueue (body con paths relativos + style)
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse

from src.api.config import APISettings, get_settings
from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import (
    APIError,
    InvalidTempPathError,
    UnauthorizedError,
    ValidationError,
)
from src.api.schemas.creator_reward.subs_auto import (
    AudioType,
    QualityLabel,
    SubsAutoEnqueueRequest,
    SubsAutoEnqueueResponse,
    WhisperModelSize,
)
from src.api.temp_storage import resolve_relative, to_relative, upload_subdir
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus


router = APIRouter(
    prefix="/api/v1/creator-reward/subs-auto",
    tags=["creator-reward · subs-auto"],
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


# ---------------------------------------------------------------------------
# POST /transcribe — streaming NDJSON
# ---------------------------------------------------------------------------
# Devuelve un stream `application/x-ndjson` con eventos:
#   {"type":"progress","frac":0.42,"msg":"🎙️ Transcribiendo… 42% · ~1m restantes"}
#   ... (varios)
#   {"type":"result", ...SubsAutoTranscribeResponse}        ← último, en éxito
#   {"type":"error","message":"..."}                         ← último, en error
#
# El cliente lee línea-a-línea con fetch+ReadableStream y va actualizando la
# UI con el progreso. El payload final tiene el mismo shape que tenía la
# respuesta JSON anterior, así que el resto del flow no cambia.
@router.post("/transcribe", status_code=status.HTTP_200_OK)
async def transcribe_video(
    file: Annotated[UploadFile, File(...)],
    model_size: Annotated[WhisperModelSize, Form()] = "small",
    language: Annotated[str | None, Form()] = None,
    audio_type: Annotated[AudioType, Form()] = "speech",
    reference_text: Annotated[str | None, Form()] = None,
    quality_label: Annotated[QualityLabel, Form()] = "1080p (Lento)",
):
    """Sube un vídeo y corre Whisper en streaming NDJSON. La parte síncrona
    (validación, escritura del fichero) se hace antes de empezar el stream
    para poder devolver errores como 422 estándar."""
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

    folder = upload_subdir("subs_auto")
    ts = int(time.time())
    in_dest = folder / f"subs_in_{ts}{ext}"
    out_dest = folder / f"subs_out_{ts}.mp4"
    try:
        in_dest.write_bytes(contents)
    except OSError as e:
        raise APIError(
            f"No se pudo escribir el vídeo en disco: {e}",
            details={"path": str(in_dest)},
        )

    try:
        from src.subtitles_only import (
            extract_audio_from_video,
            transcribe_with_reference,
        )
    except Exception as e:
        raise APIError(
            f"No se pudo importar el módulo Whisper: {e}",
            details={"hint": "Verifica que faster-whisper está instalado."},
        )

    tmp_audio = folder / f"subs_audio_{ts}.mp3"

    async def event_stream():
        import asyncio
        import json
        import threading

        loop = asyncio.get_running_loop()
        events: asyncio.Queue = asyncio.Queue()

        def push(ev: dict) -> None:
            loop.call_soon_threadsafe(events.put_nowait, ev)

        def worker() -> None:
            try:
                push({"type": "progress", "frac": 0.0, "msg": "🔊 Extrayendo audio…"})
                extract_audio_from_video(str(in_dest), str(tmp_audio))
                push({"type": "progress", "frac": 0.05, "msg": "✅ Audio extraído · arrancando Whisper…"})

                def on_progress(frac: float, msg: str) -> None:
                    # Mapear [0..1] de whisper a [0.05..0.98] del stream global.
                    push({"type": "progress", "frac": 0.05 + frac * 0.93, "msg": msg})

                words_raw = transcribe_with_reference(
                    str(tmp_audio),
                    reference_script=(reference_text.strip() if reference_text and reference_text.strip() else None),
                    model_size=model_size,
                    language=language or None,
                    audio_type=audio_type,
                    progress_callback=on_progress,
                )
                if not words_raw:
                    push({
                        "type": "error",
                        "message": "Whisper no detectó palabras. Prueba un modelo más grande o cambia audio_type.",
                    })
                    return
                payload = {
                    "type": "result",
                    "input_path_relative": to_relative(in_dest),
                    "out_path_relative": to_relative(out_dest),
                    "words": words_raw,
                    "quality_label": quality_label,
                    "model_size": model_size,
                    "language": language,
                    "audio_type": audio_type,
                }
                push({"type": "progress", "frac": 1.0, "msg": "✅ Transcripción completa"})
                push(payload)
            except Exception as e:
                push({"type": "error", "message": f"Whisper falló al transcribir: {e}"})
            finally:
                try:
                    os.remove(tmp_audio)
                except OSError:
                    pass
                push({"type": "__done__"})

        threading.Thread(target=worker, daemon=True).start()

        # Drenar la cola hasta sentinel
        while True:
            ev = await events.get()
            if ev.get("type") == "__done__":
                break
            yield (json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8")

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# POST /enqueue
# ---------------------------------------------------------------------------
@router.post(
    "/enqueue",
    response_model=SubsAutoEnqueueResponse,
    status_code=status.HTTP_201_CREATED,
)
def enqueue_subs_auto(
    payload: SubsAutoEnqueueRequest,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> SubsAutoEnqueueResponse:
    """Encola el render con el texto editado (si hay) y la config de estilo."""
    try:
        input_abs = resolve_relative(payload.input_path)
        out_abs = resolve_relative(payload.out_path)
    except ValueError as e:
        raise InvalidTempPathError(str(e), details={"input_path": payload.input_path})

    if not input_abs.exists():
        raise InvalidTempPathError(
            f"El archivo de entrada no existe: {payload.input_path}",
            details={"input_path": payload.input_path},
        )

    try:
        from src.utils import load_config
        cfg = load_config()
    except Exception as e:
        raise APIError(
            f"No se pudo cargar config/config.json: {e}",
            details={"hint": "Verifica TIKTOK_ROOT_PATH."},
        )

    title = f"{Path(input_abs).name}" + (
        " · ✏️ editado" if payload.edited_text and payload.edited_text.strip() else ""
    )
    style = payload.style
    params: dict[str, Any] = {
        "input_path": str(input_abs),
        "out_path": str(out_abs),
        "config": cfg,
        "quality_label": payload.quality_label,
        "model_size": payload.model_size,
        "language": payload.language,
        "audio_type": payload.audio_type,
        "reference_text": payload.reference_text,
        "edited_text": payload.edited_text,
        "font_path": style.font_path,
        "highlight_mode": style.highlight_mode,
        "highlight_color": style.highlight_color,
        "text_color": style.text_color,
        "stroke_color": style.stroke_color,
        "stroke_width": style.stroke_width,
        "case_mode": style.case_mode,
        "font_scale": style.font_scale,
        "max_words": style.max_words,
        "y_position": style.y_position,
        "pill_enabled": style.pill_enabled,
        "max_width": style.max_width,
        "sync_offset": style.sync_offset,
    }
    job = queue.enqueue(JobMode.SUBS_AUTO, title=title, params=params)

    return SubsAutoEnqueueResponse(
        job_id=job.id,
        title=title,
        position_in_queue=_position_in_queue(queue, job.id),
    )


# ---------------------------------------------------------------------------
# Metadata endpoints — presets, fonts, highlight modes
# ---------------------------------------------------------------------------
@router.get("/presets")
def list_subs_auto_presets() -> dict:
    """Devuelve los 9 STYLE_PRESETS del Streamlit listos para la UI.

    Cada preset trae name + config completa. La UI los puede mostrar como
    galería rápida y aplicar uno con click.
    """
    from src.subtitles_only import STYLE_PRESETS

    items = []
    for name, cfg in STYLE_PRESETS.items():
        items.append({
            "name": name,
            "config": {
                "font_path": cfg["font_path"],
                "highlight_mode": cfg["highlight_mode"],
                "highlight_color": cfg["highlight_color"],
                "text_color": cfg["text_color"],
                "stroke_color": cfg["stroke_color"],
                "stroke_width": cfg["stroke_width"],
                "case_mode": cfg["case_mode"],
                "font_scale": cfg["font_scale"],
                "max_words": cfg.get("max_words_per_chunk", 3),
                "y_position": cfg["y_position_pct"],
                "pill_enabled": cfg.get("pill_enabled", True),
                "max_width": cfg.get("max_width_pct", 0.85),
                "sync_offset": 0,
            },
        })
    return {"items": items}


@router.get("/fonts")
def list_subs_auto_fonts() -> dict:
    """Lista de fuentes disponibles — delega en el registry universal del
    proyecto. Devuelve la misma shape `{label, path}` que antes para no
    romper a clientes existentes; la fuente real puede ser bundled o de
    sistema, indistinguible para el selector."""
    from src.fonts_registry import list_fonts

    return {
        "items": [
            {"label": f["name"], "path": f["path"]}
            for f in list_fonts()
        ]
    }


@router.get("/highlight-modes")
def list_subs_auto_highlight_modes() -> dict:
    """Modos de resaltar la palabra activa. UI selector → mando el `value`."""
    from src.subtitles_only import HIGHLIGHT_MODES

    return {
        "items": [
            {"label": label, "value": value}
            for label, value in HIGHLIGHT_MODES.items()
        ]
    }


# ---------------------------------------------------------------------------
# Video frame — para preview WYSIWYG
# Router separado sin auth global (necesario para <img src> que no manda
# headers). Acepta ?api_key= query como fallback.
# ---------------------------------------------------------------------------
frame_router = APIRouter(
    prefix="/api/v1/creator-reward/subs-auto",
    tags=["creator-reward · subs-auto"],
)


def _auth_or_raise(
    settings: APISettings, header: str | None, query: str | None
) -> None:
    if not settings.api_key:
        return
    provided = header or query
    if not provided or provided != settings.api_key:
        raise UnauthorizedError("API key inválida o ausente.")


@frame_router.get("/frame")
def get_video_frame(
    settings: Annotated[APISettings, Depends(get_settings)],
    input_path: Annotated[str, Query(..., description="Path relativo devuelto por /transcribe")],
    second: Annotated[float, Query(ge=0.0, le=600.0)] = 1.0,
    api_key: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> FileResponse:
    """Extrae 1 frame del vídeo subido como JPG (background del preview).

    Se cachea en disco al lado del input (`<input>.frame_<sec>.jpg`) para
    no rehacer el extract en cada cambio de slider.
    """
    _auth_or_raise(settings, x_api_key, api_key)
    try:
        in_abs = resolve_relative(input_path)
    except ValueError as e:
        raise InvalidTempPathError(str(e), details={"input_path": input_path})
    if not in_abs.exists():
        raise InvalidTempPathError(
            f"El archivo de entrada no existe: {input_path}",
            details={"input_path": input_path},
        )

    cache_path = in_abs.parent / f"{in_abs.stem}.frame_{second:.2f}.jpg"
    if not cache_path.exists():
        try:
            import subprocess
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", f"{second:.2f}",
                    "-i", str(in_abs),
                    "-vframes", "1", "-q:v", "3",
                    str(cache_path),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except Exception as e:
            raise APIError(
                f"ffmpeg falló al extraer frame: {e}",
                details={"input_path": input_path, "second": second},
            )

    return FileResponse(
        path=str(cache_path),
        media_type="image/jpeg",
        filename=cache_path.name,
    )
