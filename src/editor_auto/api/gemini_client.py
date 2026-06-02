"""Wrapper Gemini para análisis de transcript con cost tracking.

Reutiliza el cliente dual-key de TikTok Shop (`src/tiktok_shop/api/gemini.py`)
pero añade el registro de coste vía `cost_tracking.record_custom` para que
las llamadas desde editor_auto aparezcan en /costs.

Rates de Gemini 2.5 Pro (enero 2026):
  - $1.25 por 1M input tokens
  - $5.00 por 1M output tokens

NOTA: Gemini no expone el conteo exacto de tokens en la respuesta de
`generate_text` actual. Estimamos por chars: ~4 chars = 1 token (heurística
estándar). Si se necesita precisión exacta, migrar a `model.count_tokens()`.
"""

from __future__ import annotations

import json
from typing import Any

from src import cost_tracking


GEMINI_2_5_PRO_INPUT_PER_1M = 1.25
GEMINI_2_5_PRO_OUTPUT_PER_1M = 5.00
GEMINI_2_5_FLASH_INPUT_PER_1M = 0.30
GEMINI_2_5_FLASH_OUTPUT_PER_1M = 2.50

# Estimación tokens/chars (heurística estándar — Google docs sugieren 1
# token ≈ 4 chars en inglés, ~3 en español).
_CHARS_PER_TOKEN = 3.5


def is_configured() -> bool:
    """True si hay alguna API key de Gemini definida en el entorno."""
    from src.tiktok_shop.api.gemini import is_configured as shop_is_configured
    return shop_is_configured()


def analyze_transcript_json(
    *,
    system_prompt: str,
    user_payload: dict,
    model: str = "gemini-2.5-pro",
    temperature: float = 0.0,
    max_output_tokens: int = 32768,
) -> Any:
    """Llama a Gemini con el system prompt + payload JSON, espera un JSON
    estructurado de vuelta. Registra coste estimado vía cost_tracking.

    Devuelve el JSON parseado o lanza ValueError si Gemini no devuelve JSON.
    """
    from src.tiktok_shop.api.gemini import generate_text

    user_prompt = json.dumps(user_payload, ensure_ascii=False)

    # Llamada cruda — el wrapper de shop ya maneja dual-key + retry.
    raw = generate_text(
        system_prompt,
        user_prompt,
        model=model,
        expect_json=True,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    # Cost tracking — estimación por chars/token. Gemini no devuelve usage
    # directamente en el wrapper, así que usamos heurística.
    in_chars = len(system_prompt) + len(user_prompt)
    out_chars = len(raw)
    in_tokens = int(in_chars / _CHARS_PER_TOKEN)
    out_tokens = int(out_chars / _CHARS_PER_TOKEN)

    rates = _resolve_rates(model)
    cost = (
        (in_tokens / 1_000_000) * rates[0]
        + (out_tokens / 1_000_000) * rates[1]
    )
    cost_tracking.record_custom(
        kind="gemini_chat",
        units=in_tokens + out_tokens,
        unit_label="tokens",
        cost_usd=cost,
        detail=f"editor_auto.{model} ({in_tokens}+{out_tokens})",
    )

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Gemini devolvió JSON inválido: {e}\nRespuesta: {raw[:500]}"
        )


def _resolve_rates(model: str) -> tuple[float, float]:
    """Devuelve (input_per_1M, output_per_1M) para el modelo Gemini.
    Match por prefix más largo; modelos desconocidos caen a 2.5 Flash.
    """
    if model.startswith("gemini-2.5-pro"):
        return GEMINI_2_5_PRO_INPUT_PER_1M, GEMINI_2_5_PRO_OUTPUT_PER_1M
    if model.startswith("gemini-2.5-flash"):
        return GEMINI_2_5_FLASH_INPUT_PER_1M, GEMINI_2_5_FLASH_OUTPUT_PER_1M
    return GEMINI_2_5_FLASH_INPUT_PER_1M, GEMINI_2_5_FLASH_OUTPUT_PER_1M
