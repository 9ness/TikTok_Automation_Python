"""Wrapper OpenAI Chat Completions con cost tracking integrado.

Centraliza las llamadas a OpenAI del programa Editor Auto. Único uso
actual: análisis de transcripts para detectar frases sucias en
`silence_cutter`. Modelo por defecto = `gpt-4o` (más caro pero el mejor
para detección semántica fina en castellano).
"""

from __future__ import annotations

import json
import os
from typing import Any

from src import cost_tracking


DEFAULT_MODEL = "gpt-4o"


def is_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def analyze_transcript_json(
    *,
    system_prompt: str,
    user_payload: dict,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    seed: int | None = None,
) -> Any:
    """Llama a OpenAI Chat con `response_format=json_object` y devuelve el
    JSON parseado. Registra el coste vía `cost_tracking.record_openai_chat`.

    `seed` (opcional) → salida CASI determinista (mismo input + seed + temp 0
    = mismo resultado), clave para que el editor sea estable y repetible.

    Lanza `RuntimeError` si OpenAI no está configurada, `ValueError` si la
    respuesta no es JSON parseable.
    """
    if not is_configured():
        raise RuntimeError(
            "OPENAI_API_KEY no configurada — silence_cutter requiere OpenAI."
        )

    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    kwargs: dict[str, Any] = {}
    if seed is not None:
        kwargs["seed"] = int(seed)
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        **kwargs,
    )

    # Cost tracking — usa tokens reales del provider
    usage = getattr(response, "usage", None)
    if usage is not None:
        cost_tracking.record_openai_chat(
            input_tokens=int(usage.prompt_tokens or 0),
            output_tokens=int(usage.completion_tokens or 0),
            model=model,
            detail=f"editor_auto.silence_cutter ({model})",
        )

    raw = (response.choices[0].message.content or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"OpenAI devolvió JSON inválido: {e}\nRespuesta: {raw[:500]}"
        )
