"""Endpoints del nicho 🏛️ Presidentes Top 5.

5 endpoints:
- POST /enqueue
- GET / PUT / DELETE /presets/{name}
- GET /presets
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status

from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import APIError, PresetNotFoundError, ValidationError
from src.api.schemas.creator_reward.presidents import (
    PresidentsBatchEnqueueResponse,
    PresidentsEnqueueRequest,
    PresidentsPresetListResponse,
    PresidentsPresetResponse,
)
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus


router = APIRouter(
    prefix="/api/v1/creator-reward/presidents",
    tags=["creator-reward · presidents"],
    dependencies=[Depends(get_current_user)],
)


# Defaults legacy. La lookup REAL pasa por el registry universal de fuentes
# (`fonts_registry.list_fonts()`), que incluye estas y todas las bundled
# que el usuario haya subido. Esto se mantiene como fallback si el registry
# está vacío o el nombre solicitado no aparece.
_SUBS_FONT_PATHS: dict[str, str] = {
    "Impact":              r"C:\Windows\Fonts\impact.ttf",
    "Rubik Bold (CapCut)": "Rubik-Bold.ttf",
    "Arial Bold":          r"C:\Windows\Fonts\arialbd.ttf",
}


def _resolve_font_choice(name: str) -> str:
    """Devuelve el path absoluto de la fuente. Mira primero en el registry
    universal por `name` (case-insensitive); si no la encuentra, cae a
    `_SUBS_FONT_PATHS`. Finalmente Impact como último recurso."""
    from src.fonts_registry import list_fonts

    if name:
        target = name.strip().lower()
        for f in list_fonts():
            if f["name"].lower() == target:
                return f["path"]
    if name in _SUBS_FONT_PATHS:
        return _SUBS_FONT_PATHS[name]
    return _SUBS_FONT_PATHS["Impact"]

_RESOLUTION_TO_PIXELS: dict[str, list[int]] = {
    "1080p (Lento)":       [1080, 1920],
    "720p (Medio)":        [720, 1280],
    "480p (Rápido)":       [480, 854],
    "240p (Ultra Rápido)": [240, 426],
}


def _position_in_queue(queue: JobQueue, job_id: str) -> int:
    """0 = es el siguiente en correr (o ya está running). 1 = hay 1 antes. Etc."""
    pending_or_running = [
        j for j in queue.get_all()
        if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
    ]
    for i, j in enumerate(pending_or_running):
        if j.id == job_id:
            return i
    return 0


def _safe_resolution(label: str) -> list[int]:
    res = _RESOLUTION_TO_PIXELS.get(label, [1080, 1920])
    w = res[0] if res[0] % 2 == 0 else res[0] - 1
    h = res[1] if res[1] % 2 == 0 else res[1] - 1
    return [w, h]


# ---------------------------------------------------------------------------
# POST /enqueue
# ---------------------------------------------------------------------------
@router.post(
    "/enqueue",
    response_model=PresidentsBatchEnqueueResponse,
    status_code=status.HTTP_201_CREATED,
)
def enqueue_presidents(
    payload: PresidentsEnqueueRequest,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> PresidentsBatchEnqueueResponse:
    """Encola N vídeos de Presidentes en un solo lote (replica el flow
    Streamlit con `cantidad` items en el form)."""
    try:
        from src.utils import load_config
        cfg = load_config()
    except Exception as e:
        raise APIError(
            f"No se pudo cargar config/config.json: {e}",
            details={"hint": "Verifica que TIKTOK_ROOT_PATH apunta a una carpeta válida."},
        )

    cfg.setdefault("video_settings", {})["resolution"] = _safe_resolution(payload.resolution)

    subs_font_path = _resolve_font_choice(payload.subs.font_choice)

    jobs_info: list[dict[str, Any]] = []
    for item in payload.items:
        topic = (item.topic or "").strip() or None
        title_prefix = f"{item.prefix} {item.top_count}"
        topic_display = topic or "🎲 Aleatorio"
        title = f"{title_prefix} · {topic_display} · top {item.top_count}"

        params: dict[str, Any] = {
            "config": cfg,
            "topic": topic,
            "creative_mode": payload.creative_mode,
            "title_prefix": title_prefix,
            "top_count": item.top_count,
            "include_history": item.include_history,
            "include_hook": item.include_hook,
            "engine_version": payload.engine_version,
            # Subs
            "subs_enabled": payload.subs.enabled,
            "subs_font_path": subs_font_path,
            "subs_highlight_color": payload.subs.highlight_color,
            "subs_text_color": payload.subs.text_color,
            "subs_stroke_color": payload.subs.stroke_color,
            "subs_stroke_width": payload.subs.stroke_width,
            "subs_case": payload.subs.case_mode,
            "subs_font_scale": payload.subs.font_scale,
            "subs_max_words": payload.subs.max_words,
            "subs_y_position": payload.subs.y_position,
            "subs_shadow_enabled": payload.subs.shadow_enabled,
            "subs_highlight_mode": payload.subs.highlight_mode,
            "subs_max_width": payload.subs.max_width,
            # Hook box
            "hook_enabled": payload.hook.enabled,
            "hook_duration": payload.hook.duration,
            "hook_animation": payload.hook.animation,
            "hook_y_position": payload.hook.y_position,
            "hook_shadow_color": payload.hook.shadow_color,
            "hook_box_color": payload.hook.box_color,
            "hook_text_color": payload.hook.text_color,
            "hook_font_scale": payload.hook.font_scale,
        }
        job = queue.enqueue(JobMode.PRESIDENTS, title=title, params=params)
        jobs_info.append({
            "job_id": job.id,
            "title": title,
            "position_in_queue": _position_in_queue(queue, job.id),
        })

    return PresidentsBatchEnqueueResponse(
        jobs=jobs_info,
        total_enqueued=len(jobs_info),
    )


# ---------------------------------------------------------------------------
# Presets — CRUD sobre configs_store
# ---------------------------------------------------------------------------
@router.get("/presets", response_model=PresidentsPresetListResponse)
def list_presets() -> PresidentsPresetListResponse:
    from src.configs_store import is_available, list_configs
    if not is_available():
        return PresidentsPresetListResponse(items=[], total=0)
    names = list_configs()
    return PresidentsPresetListResponse(items=names, total=len(names))


@router.get("/presets/{name}", response_model=PresidentsPresetResponse)
def get_preset(name: str) -> PresidentsPresetResponse:
    from src.configs_store import load_config as load_preset
    config = load_preset(name)
    if config is None:
        raise PresetNotFoundError(
            f"Preset '{name}' no encontrado.",
            details={"name": name},
        )
    return PresidentsPresetResponse(name=name, config=config)


@router.put("/presets/{name}", response_model=PresidentsPresetResponse)
def save_preset(name: str, config: dict[str, Any]) -> PresidentsPresetResponse:
    if not name.strip():
        raise ValidationError("El nombre del preset no puede estar vacío.")
    from src.configs_store import is_available, save_config
    if not is_available():
        raise APIError(
            "Upstash Redis no configurado — no se pueden guardar presets.",
            details={"hint": "Define UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN."},
        )
    if not save_config(name, config):
        raise APIError(
            f"Fallo al guardar preset '{name}' en Redis.",
            details={"name": name},
        )
    return PresidentsPresetResponse(name=name, config=config)


@router.delete("/presets/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preset(name: str) -> Response:
    from src.configs_store import delete_config, is_available, load_config as load_preset
    if not is_available():
        raise APIError(
            "Upstash Redis no configurado.",
            details={"hint": "Define UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN."},
        )
    if load_preset(name) is None:
        raise PresetNotFoundError(
            f"Preset '{name}' no encontrado.",
            details={"name": name},
        )
    delete_config(name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
