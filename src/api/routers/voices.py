"""Endpoints de la biblioteca de voces.

La biblioteca incluye los presets MiniMax (`Spanish_*` / `English_*`) y
voces clonadas guardadas en Redis. Incluye también:
- POST /voices/clone   → sube un sample MP3 a MiniMax voice_clone API y
  guarda la voz resultante en Redis (persistida globalmente).
- GET /voices/{id}/sample  → devuelve un MP3 ~3-5s para audicionar la voz
  antes de seleccionarla (cacheado en disco para no quemar créditos).
"""

from __future__ import annotations

import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse

from src.api.dependencies import get_current_user, get_voice_repo
from src.api.exceptions import APIError, ValidationError, VoiceNotFoundError
from src.api.schemas.voice import VoiceListResponse, VoiceResponse
from src.api.temp_storage import upload_subdir
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
    presets MiniMax (`Boy`/`Girl`/`Lady`/`Queen`/`Warrior`...)."""
    g = gender.lower().strip()
    tags_lower = {t.lower() for t in voice.tags}
    aliases = {
        "male": {"male", "man", "boy", "masculino", "masculine"},
        "female": {"female", "woman", "girl", "femenino", "feminine"},
        "neutral": {"neutral", "neutro"},
    }.get(g, {g})

    if tags_lower & aliases:
        return True

    # Heurística por keywords del nombre (presets MiniMax). Female se
    # comprueba antes que male para que "Young Man" + "Lady" no colisionen
    # con "man" inicial (lady, girl, woman, queen).
    name_lower = voice.name.lower()
    female_kws = ("girl", "woman", "lady", "queen", "chica")
    male_kws = ("boy", "man", "warrior", "scholar", "debator", "comedian",
                "leader", "boss", "partner", "person", "storyteller",
                "youngman", "chico")
    if g == "female" and any(w in name_lower for w in female_kws):
        return True
    if g == "male":
        if any(w in name_lower for w in female_kws):
            return False  # evita falso positivo de "man" dentro de "woman"
        if any(w in name_lower for w in male_kws):
            return True
    if g == "neutral" and "character" in name_lower:
        return True
    return False


def _age_group(voice: VoiceClone) -> str:
    """Devuelve `"young" | "adult" | "mature"` heurístico por keywords.

    Orden de precedencia:
      1. tag explícito (`mature` / `young` / `adult`) → wins
      2. keyword `mature` / `wise` / `scholar` / `boss` → mature
      3. keyword `teen` / `boy` / `girl` / `young` / `anime` → young
      4. fallback → adult
    """
    tags_lower = {t.lower() for t in voice.tags}
    for tag in ("mature", "young", "adult"):
        if tag in tags_lower:
            return tag
    name_lower = voice.name.lower()
    if any(k in name_lower for k in ("mature", "wise", "scholar", "boss", "patient")):
        return "mature"
    if any(k in name_lower for k in ("teen", "young", "boy", "girl", "anime", "playful", "lovely", "delicate", "whimsical", "rude", "soft-spoken")):
        return "young"
    return "adult"


def _matches_age_group(voice: VoiceClone, age_group: str) -> bool:
    """Acepta español o inglés: niño/joven, adulto, mayor."""
    g = age_group.lower().strip()
    aliases = {
        "young": "young", "niño": "young", "nino": "young", "joven": "young", "teen": "young",
        "adult": "adult", "adulto": "adult",
        "mature": "mature", "mayor": "mature", "old": "mature", "senior": "mature",
    }
    target = aliases.get(g, g)
    return _age_group(voice) == target


# ---------------------------------------------------------------------------
# GET /voices
# ---------------------------------------------------------------------------
@router.get("", response_model=VoiceListResponse)
def list_voices(
    repo: Annotated[VoiceRepo, Depends(get_voice_repo)],
    language: str | None = Query(default=None),
    gender: str | None = Query(default=None, description="male | female | neutral"),
    age_group: str | None = Query(default=None, description="young | adult | mature (alias ES: joven/adulto/mayor)"),
    include_presets: bool = Query(default=True),
) -> VoiceListResponse:
    voices = repo.list_all(include_presets=include_presets)
    if language:
        voices = [v for v in voices if v.language == language]
    if gender:
        voices = [v for v in voices if _matches_gender(v, gender)]
    if age_group:
        voices = [v for v in voices if _matches_age_group(v, age_group)]
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


# ---------------------------------------------------------------------------
# POST /voices/sync — refresca el catálogo system MiniMax (cache 24h)
# ---------------------------------------------------------------------------
@router.post("/sync")
def sync_minimax_catalog() -> dict:
    """Llama a MiniMax `/v1/get_voice` con `voice_type=system` y cachea el
    resultado normalizado en Redis (`voice:minimax_system_catalog`).

    Tras el sync, `GET /voices` devuelve los voice_id reales de la cuenta
    en vez de los presets hardcoded (que podían contener IDs inventados).
    """
    try:
        from src.tiktok_shop.api.minimax_catalog import get_system_voices, get_cache_meta
        voices = get_system_voices(force_refresh=True)
    except Exception as e:
        raise APIError(
            f"MiniMax get_voice falló: {e}",
            details={"hint": "Verifica MINIMAX_API_KEY y conectividad."},
        )
    meta = get_cache_meta() or {}
    return {
        "synced": True,
        "count": len(voices),
        "cache_age_seconds": meta.get("age_seconds"),
    }


@router.get("/sync/status")
def sync_status() -> dict:
    """Devuelve metadata del cache (edad y nº de voces) — para mostrar
    en la UI cuándo se sincronizó por última vez."""
    from src.tiktok_shop.api.minimax_catalog import get_cache_meta
    meta = get_cache_meta()
    if meta is None:
        return {"cached": False}
    return {"cached": True, **meta}


# ---------------------------------------------------------------------------
# POST /voices/clone — sube un sample MP3, llama a MiniMax y persiste la voz
# ---------------------------------------------------------------------------
@router.post(
    "/clone",
    response_model=VoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def clone_voice(
    repo: Annotated[VoiceRepo, Depends(get_voice_repo)],
    file: Annotated[UploadFile, File(...)],
    name: Annotated[str, Form(..., min_length=1, max_length=80)],
    language: Annotated[Literal["en", "es"], Form()] = "en",
) -> VoiceResponse:
    """Clonar voz desde un MP3 (10-30s, voz limpia, sin música)."""
    filename = (file.filename or "").lower()
    if not filename.endswith((".mp3", ".wav", ".m4a")):
        raise ValidationError(
            f"Formato no soportado: '{file.filename}'. Acepta .mp3 / .wav / .m4a.",
            details={"filename": file.filename},
        )
    contents = await file.read()
    if not contents:
        raise ValidationError("Archivo vacío.", details={"filename": file.filename})
    if len(contents) > 20 * 1024 * 1024:
        raise ValidationError(
            f"El sample pesa {len(contents) / 1024 / 1024:.1f} MB, máximo 20 MB.",
            details={"size_bytes": len(contents)},
        )

    folder = upload_subdir("voice_clones")
    ts = int(time.time())
    ext = "." + filename.rsplit(".", 1)[-1]
    sample_path = folder / f"clone_in_{ts}{ext}"
    sample_path.write_bytes(contents)

    try:
        from src.tiktok_shop.api.minimax_clone import clone_voice as minimax_clone
        minimax_voice_id = minimax_clone(
            str(sample_path), name=name, language=language,
        )
    except Exception as e:
        raise APIError(
            f"MiniMax voice_clone falló: {e}",
            details={"hint": "Verifica MINIMAX_API_KEY y que el sample es voz limpia 10-30s."},
        )

    voice = VoiceClone(
        name=name,
        minimax_voice_id=minimax_voice_id,
        language=language,
        is_preset=False,
        tags=["clone", language],
        sample_local_path=str(sample_path),
    )
    repo.save(voice)
    return _to_response(voice)


# ---------------------------------------------------------------------------
# DELETE /voices/{id} — borra clone (presets bloqueados)
# ---------------------------------------------------------------------------
@router.delete("/{voice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_voice(
    voice_id: str,
    repo: Annotated[VoiceRepo, Depends(get_voice_repo)],
):
    if voice_id.startswith("preset_"):
        raise ValidationError("Los presets MiniMax no se pueden borrar.")
    ok = repo.delete(voice_id)
    if not ok:
        raise VoiceNotFoundError(
            f"Voz '{voice_id}' no encontrada.",
            details={"voice_id": voice_id},
        )


# ---------------------------------------------------------------------------
# Sample audio — router separado SIN auth (para <audio src>). Usa ?api_key=
# ---------------------------------------------------------------------------
sample_router = APIRouter(
    prefix="/api/v1/voices",
    tags=["voices"],
)


@sample_router.get("/{voice_id}/sample")
def get_voice_sample(
    voice_id: str,
    repo: Annotated[VoiceRepo, Depends(get_voice_repo)],
    text: str | None = Query(default=None, max_length=400),
) -> FileResponse:
    """Devuelve un MP3 ~3-5s con la voz hablando. Cachea en disco
    `temp_root/api_uploads/voice_samples/{voice_id}.mp3` para no quemar
    créditos en cada click."""
    # Resolver minimax_voice_id real (presets vs clones)
    if voice_id.startswith("preset_"):
        target = None
        for v in repo.list_all(include_presets=True):
            if v.id == voice_id:
                target = v
                break
        if target is None:
            raise VoiceNotFoundError(f"Voz '{voice_id}' no encontrada.")
        minimax_id = target.minimax_voice_id
        language = target.language
    else:
        v = repo.get(voice_id)
        if v is not None:
            minimax_id = v.minimax_voice_id
            language = v.language
        else:
            # Preset MiniMax pasado por su id CRUDO (ej. 'Spanish_Strong-WilledBoy',
            # como los favoritos de Pronósticos o un voice_id custom). No está en el
            # repo, pero el id ya ES el minimax_voice_id → lo usamos directo. Idioma
            # deducido del prefijo (Spanish_/English_).
            minimax_id = voice_id
            language = "en" if voice_id.lower().startswith("english_") else "es"

    sample_text = text or (
        "I lay the waterproof membrane and seal every joint. I install the "
        "frame and pour the concrete substrate."
        if language == "en"
        else "Esto es un ejemplo de mi voz para que la audiciones antes de elegirla."
    )

    folder = upload_subdir("voice_samples")
    out = folder / f"{voice_id}.mp3"
    if not out.exists():
        try:
            from src.locutor import generate_voice_sample
            generate_voice_sample(minimax_id, str(out), sample_text=sample_text)
        except Exception as e:
            raise APIError(
                f"No se pudo generar el sample: {e}",
                details={"voice_id": voice_id, "minimax_id": minimax_id},
            )
    return FileResponse(
        path=str(out),
        media_type="audio/mpeg",
        filename=out.name,
    )
