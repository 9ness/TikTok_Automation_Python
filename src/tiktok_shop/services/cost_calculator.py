"""Estimaciones y agregaciones de coste por generación.

Tarifas Atlas Cloud (per doc oficial, descuentos vigentes):
  standard ($0.018/seg) → $0.27 / 15s a 720p
  advanced ($0.047/seg) → $0.71 / 15s a 720p
  pro      ($0.072/seg) → $1.08 / 15s a 720p

Multiplicadores resolución:
  480p     0.7
  720p     1.0
  1080p-SR 1.5
  1440p-SR 2.0

Voz MiniMax speech-02-turbo:
  $0.06 / 1000 caracteres procesados.
"""

from __future__ import annotations

from src.tiktok_shop.config import RESOLUTION_COST_MULTIPLIER, VIDEO_MODELS


# Doc Atlas: speech-02-turbo cobra $0.06 por cada 1000 caracteres.
MINIMAX_TTS_USD_PER_1K_CHARS = 0.06
MINIMAX_TTS_USD_PER_CHAR = MINIMAX_TTS_USD_PER_1K_CHARS / 1000  # 0.00006


def estimate_video_cost(
    tier: str,
    duration: int,
    resolution: str = "720p",
) -> float:
    """Coste estimado de la generación de vídeo (sin voz)."""
    model = VIDEO_MODELS.get(tier)
    if not model:
        return 0.0
    rate = float(model.get("cost_per_second", 0.0))
    multiplier = RESOLUTION_COST_MULTIPLIER.get(resolution, 1.0)
    return round(rate * duration * multiplier, 4)


def estimate_voice_cost(script_text_or_chars: str | int) -> float:
    """Acepta el texto del guion o el nº de caracteres directamente."""
    chars = (
        len(script_text_or_chars or "")
        if isinstance(script_text_or_chars, str)
        else int(script_text_or_chars or 0)
    )
    return round(chars * MINIMAX_TTS_USD_PER_CHAR, 4)


def estimate_cost(
    *,
    tier: str,
    duration: int,
    resolution: str,
    voice_chars: int = 0,
    with_voice: bool = True,
) -> dict:
    """Devuelve `{video_generation, voice_tts, total}` para mostrar en UI.

    Si `with_voice=False`, voz cuenta como 0 (modo `generate_audio` nativo
    Atlas o testing sin voz).
    """
    video = estimate_video_cost(tier, duration, resolution)
    voice = estimate_voice_cost(voice_chars) if with_voice else 0.0
    return {
        "video_generation": video,
        "voice_tts": voice,
        "total": round(video + voice, 4),
    }


def actual_cost_from_response(
    *, tier: str, actual_duration: int, resolution: str, actual_voice_chars: int = 0,
) -> dict:
    """Recalcula coste con la duración/chars REALES tras completar.

    Atlas Cloud no devuelve coste explícito en el polling, así que recalculamos
    con los valores reales (`actual_duration` puede diferir si Atlas redondeó).
    """
    return estimate_cost(
        tier=tier, duration=actual_duration, resolution=resolution,
        voice_chars=actual_voice_chars, with_voice=actual_voice_chars > 0,
    )
