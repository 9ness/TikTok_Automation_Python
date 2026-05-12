"""Endpoints de la biblioteca de voces (read-only).

La biblioteca incluye los presets MiniMax (`Spanish_*`) y voces clonadas
guardadas en Redis. La creación / clonado vivirá en otro endpoint
(Fase 1D — voice cloning).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_current_user, get_voice_repo
from src.api.exceptions import VoiceNotFoundError
from src.api.schemas.voice import VoiceListResponse, VoiceResponse
from src.tiktok_shop.models import VoiceClone
from src.tiktok_shop.repos import VoiceRepo


router = APIRouter(
    prefix="/api/v1/voices",
    tags=["voices"],
    dependencies=[Depends(get_current_user)],
)


def _to_response(v: VoiceClone) -> VoiceResponse:
    return VoiceResponse.model_validate(v.model_dump())


def _matches_gender(voice: VoiceClone, gender: str) -> bool:
    """Match laxo por tags. Acepta `male`/`female`/`neutral` (en cualquier
    idioma común) y también palabras heurísticas presentes en `name` para
    presets MiniMax (`Boy`/`Girl`/`Warrior`...)."""
    g = gender.lower().strip()
    tags_lower = {t.lower() for t in voice.tags}
    aliases = {
        "male": {"male", "man", "boy", "masculino", "masculine"},
        "female": {"female", "woman", "girl", "femenino", "feminine"},
        "neutral": {"neutral", "neutro"},
    }.get(g, {g})

    if tags_lower & aliases:
        return True

    # Heurística adicional sobre el nombre (para presets MiniMax)
    name_lower = voice.name.lower()
    if g == "male" and any(w in name_lower for w in ("boy", "man", "warrior", "chico")):
        return True
    if g == "female" and any(w in name_lower for w in ("girl", "woman", "chica")):
        return True
    return False


# ---------------------------------------------------------------------------
# GET /voices
# ---------------------------------------------------------------------------
@router.get("", response_model=VoiceListResponse)
def list_voices(
    repo: Annotated[VoiceRepo, Depends(get_voice_repo)],
    language: str | None = Query(default=None),
    gender: str | None = Query(default=None),
    include_presets: bool = Query(default=True),
) -> VoiceListResponse:
    voices = repo.list_all(include_presets=include_presets)
    if language:
        voices = [v for v in voices if v.language == language]
    if gender:
        voices = [v for v in voices if _matches_gender(v, gender)]
    return VoiceListResponse(
        items=[_to_response(v) for v in voices],
        total=len(voices),
    )


# ---------------------------------------------------------------------------
# GET /voices/{voice_id}
# ---------------------------------------------------------------------------
@router.get("/{voice_id}", response_model=VoiceResponse)
def get_voice(
    voice_id: str,
    repo: Annotated[VoiceRepo, Depends(get_voice_repo)],
) -> VoiceResponse:
    # Los presets se construyen on-the-fly en `list_all`; buscarlos por id
    # requiere recorrer la lista enriquecida.
    if voice_id.startswith("preset_"):
        for v in repo.list_all(include_presets=True):
            if v.id == voice_id:
                return _to_response(v)
        raise VoiceNotFoundError(
            f"Voz preset '{voice_id}' no encontrada.",
            details={"voice_id": voice_id},
        )

    v = repo.get(voice_id)
    if v is None:
        raise VoiceNotFoundError(
            f"Voz '{voice_id}' no encontrada.",
            details={"voice_id": voice_id},
        )
    return _to_response(v)
