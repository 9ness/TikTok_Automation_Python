"""Wrapper de las llamadas de texto del Editor Auto, con cost tracking.

Centraliza las llamadas de IA del programa Editor Auto. Único uso actual:
análisis de transcripts para detectar frases sucias en `silence_cutter`.
Desde oct 2026 va PRIMERO a Claude (`claude_client`, clave
`ANTHROPIC_API_KEY_EDITOR_AUTO`) y OpenAI queda de respaldo si Claude falla.
El `model` que pasan los callers (gpt-4o / gpt-5.4) solo vale para OpenAI.
"""

from __future__ import annotations

import json
import os
from typing import Any

from src import cost_tracking
from src.editor_auto.api import claude_client


DEFAULT_MODEL = "gpt-4o"


def is_configured() -> bool:
    return claude_client.activo() or bool(os.getenv("OPENAI_API_KEY"))


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
    if claude_client.activo():
        try:
            return claude_client.analyze_transcript_json(
                system_prompt=system_prompt, user_payload=user_payload,
            )
        except Exception as e:  # noqa: BLE001
            if not os.getenv("OPENAI_API_KEY"):
                raise
            print(f"[editor_auto] Claude falló → respaldo OpenAI: {str(e)[:200]}")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "Ni ANTHROPIC_API_KEY_EDITOR_AUTO ni OPENAI_API_KEY configuradas — "
            "silence_cutter requiere una IA."
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
