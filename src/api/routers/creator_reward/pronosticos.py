"""Endpoints del nicho 📊 Pronósticos Diarios.

3 endpoints:
- GET /versions?date=
- GET /latest-date
- POST /enqueue
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from src.api.dependencies import get_current_user, get_queue
from src.api.exceptions import (
    APIError,
    PronosticosVersionNotFoundError,
    ValidationError,
)
from src.api.schemas.creator_reward.pronosticos import (
    PronosticosBatchEnqueueResponse,
    PronosticosEnqueueRequest,
    PronosticosLatestDateResponse,
    PronosticosVersionItem,
    PronosticosVersionsResponse,
)
from src.queue.manager import JobQueue
from src.queue.models import JobMode, JobStatus


router = APIRouter(
    prefix="/api/v1/creator-reward/pronosticos",
    tags=["creator-reward · pronosticos"],
    dependencies=[Depends(get_current_user)],
)


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
# GET /versions
# ---------------------------------------------------------------------------
@router.get("/versions", response_model=PronosticosVersionsResponse)
def list_versions_for_date(
    date: str = Query(..., description="YYYY-MM-DD"),
) -> PronosticosVersionsResponse:
    """Devuelve las versiones de guion disponibles en Redis para una fecha.
    Si no hay payload → `payload_exists=false, versions=[]`."""
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        raise ValidationError(
            f"Fecha debe estar en formato YYYY-MM-DD: '{date}'",
            details={"date": date},
        )
    from src.pronosticos.data_loader import (
        get_picks,
        list_versions,
        load_raw_payload,
    )

    payload = load_raw_payload(date)
    if payload is None:
        return PronosticosVersionsResponse(
            date=date,
            payload_exists=False,
            versions=[],
            selected_version_id=None,
        )

    raw_versions = list_versions(payload)
    items: list[PronosticosVersionItem] = []
    for v in raw_versions:
        items.append(
            PronosticosVersionItem(
                id=str(v.get("id", "")),
                trigger=v.get("trigger"),
                mode=v.get("mode"),
                word_count=v.get("word_count"),
                estimated_duration_s=v.get("estimated_duration_s"),
                picks_count=len(get_picks(v)),
                script=v.get("script", ""),
                title=v.get("title"),
                competition_focus=v.get("competition_focus"),
                is_selected=bool(v.get("is_selected", False)),
            )
        )
    return PronosticosVersionsResponse(
        date=date,
        payload_exists=True,
        versions=items,
        selected_version_id=(
            str(payload.get("selected_version_id"))
            if payload.get("selected_version_id") is not None else None
        ),
    )


# ---------------------------------------------------------------------------
# GET /latest-date
# ---------------------------------------------------------------------------
@router.get("/latest-date", response_model=PronosticosLatestDateResponse)
def get_latest_date(
    max_lookback_days: int = Query(default=14, ge=1, le=60),
) -> PronosticosLatestDateResponse:
    from src.pronosticos.data_loader import find_latest_available_date
    return PronosticosLatestDateResponse(
        latest_date=find_latest_available_date(max_lookback_days=max_lookback_days),
    )


# ---------------------------------------------------------------------------
# POST /enqueue
# ---------------------------------------------------------------------------
@router.post(
    "/enqueue",
    response_model=PronosticosBatchEnqueueResponse,
    status_code=status.HTTP_201_CREATED,
)
def enqueue_pronosticos(
    payload: PronosticosEnqueueRequest,
    queue: Annotated[JobQueue, Depends(get_queue)],
) -> PronosticosBatchEnqueueResponse:
    """Encola N versiones de Pronósticos. Valida que las versiones
    existen en el payload de Redis para la fecha dada."""
    try:
        from src.utils import load_config
        cfg = load_config()
    except Exception as e:
        raise APIError(
            f"No se pudo cargar config/config.json: {e}",
            details={"hint": "Verifica TIKTOK_ROOT_PATH."},
        )

    # Validar que las versiones existen
    from src.pronosticos.data_loader import list_versions, load_raw_payload
    raw_payload = load_raw_payload(payload.target_date)
    if raw_payload is None:
        raise PronosticosVersionNotFoundError(
            f"No hay payload de pronósticos para {payload.target_date} en Redis.",
            details={"date": payload.target_date},
        )
    available_ids = {str(v.get("id")) for v in list_versions(raw_payload)}
    missing = [vid for vid in payload.version_ids if vid not in available_ids]
    if missing:
        raise PronosticosVersionNotFoundError(
            f"Versiones inexistentes para {payload.target_date}: {missing}",
            details={
                "date": payload.target_date,
                "missing": missing,
                "available": sorted(available_ids),
            },
        )

    # Safety: dimensiones pares
    w_safe = payload.video_size[0] if payload.video_size[0] % 2 == 0 else payload.video_size[0] - 1
    h_safe = payload.video_size[1] if payload.video_size[1] % 2 == 0 else payload.video_size[1] - 1

    output_folder = cfg["paths"]["output_folder"]

    jobs_info: list[dict[str, Any]] = []
    for vid in payload.version_ids:
        # `legacy` se persiste como version_id=None en el runner
        version_id_param = None if vid == "legacy" else vid
        script_override = payload.script_overrides.get(vid)
        title = (
            f"{payload.target_date} · v{vid}"
            + (" · ✏️ editado" if script_override else "")
        )
        params: dict[str, Any] = {
            "target_date": payload.target_date,
            "output_folder": output_folder,
            "video_size": (w_safe, h_safe),
            "voice_id_override": (payload.voice_id_override or None),
            "publish_to_redis": payload.publish_to_redis,
            "add_subtitles": payload.audio.add_subtitles,
            "use_intro_folder": payload.overlays.use_intro_folder,
            "add_money_sfx": payload.audio.add_money_sfx,
            "sfx_volume": payload.audio.sfx_volume,
            "add_clink_sfx": payload.audio.add_clink_sfx,
            "clink_volume": payload.audio.clink_volume,
            "add_camera_sfx": payload.audio.add_camera_sfx,
            "camera_volume": payload.audio.camera_volume,
            "add_league_overlay": payload.overlays.add_league_overlay,
            "league_overlay_duration": payload.overlays.league_overlay_duration,
            "saturation": payload.overlays.saturation,
            "show_pick_carousel": payload.overlays.show_pick_carousel,
            "video_style": payload.overlays.video_style,
            "photo_overrides": payload.overlays.photo_overrides or None,
            # Posiciones configurables vía preview drag (UI)
            "subtitle_y_pct": payload.overlays.subtitle_y_pct,
            "league_overlay_y_pct": payload.overlays.league_overlay_y_pct,
            "league_logo_height_pct": payload.overlays.league_logo_height_pct,
            "team_shield_y_pct": payload.overlays.team_shield_y_pct,
            "team_shield_height_pct": payload.overlays.team_shield_height_pct,
            "team_shield_x_inset_pct": payload.overlays.team_shield_x_inset_pct,
            "profile_cta_y_pct": payload.overlays.profile_cta_y_pct,
            "profile_cta_height_pct": payload.overlays.profile_cta_height_pct,
            "version_id": version_id_param,
            "script_override": script_override,
            "add_background_music": payload.audio.add_background_music,
            "bgm_volume": payload.audio.bgm_volume,
            "voice_speed": payload.audio.voice_speed,
        }
        job = queue.enqueue(JobMode.PRONOSTICOS, title=title, params=params)
        jobs_info.append({
            "job_id": job.id,
            "title": title,
            "position_in_queue": _position_in_queue(queue, job.id),
            "version_id": vid,
        })

    return PronosticosBatchEnqueueResponse(
        jobs=jobs_info,
        total_enqueued=len(jobs_info),
    )
