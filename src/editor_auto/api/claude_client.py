"""Cliente Claude del Editor Auto (análisis de transcripts del cortador).

Mismo contrato que `openai_client.analyze_transcript_json`: system prompt +
payload JSON → JSON parseado. `openai_client` lo llama primero y, si Claude
falla (sin clave, cuota, red, rechazo, JSON roto), sigue con OpenAI: cambiar
de proveedor nunca deja un vídeo sin cortar.

Interruptor: `EDITOR_AUTO_LLM=openai` vuelve a OpenAI sin tocar código. La
clave es `ANTHROPIC_API_KEY_EDITOR_AUTO` (una por parte de la app, para ver
su gasto aparte en la Console).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from src import cost_tracking

# El modelo va aquí y solo aquí: al salir otro se cambia esta línea.
# `EDITOR_AUTO_CLAUDE_MODEL` lo cambia sin desplegar (para comparar).
# A/B del corpus de regresión (23/10/2026, 4 grabaciones, Whisper base):
# OpenAI 100/87/100/100 · Haiku 92/87/92/100 · Sonnet bajo 92/82/92/100.
# Lo que restaba a los dos Claude era quitar un «qué pasa bro pasa pasa…»
# de fondo; Haiku cuesta ~0,006 $ el vídeo (OpenAI ~0,12, Sonnet ~0,10).
MODELO = "claude-haiku-5-5"
ESFUERZO = "low"  # solo si se pone un modelo con pensamiento (Sonnet/Opus)

_ENV_CLAVE = "ANTHROPIC_API_KEY_EDITOR_AUTO"
_MAX_TOKENS = 32000
_PIDE_JSON = (
    "\n\nResponde SOLO con un objeto JSON válido: sin texto antes ni después y "
    "sin bloques ```."
)

_cliente = None


def modelo() -> str:
    return os.getenv("EDITOR_AUTO_CLAUDE_MODEL") or MODELO


def activo() -> bool:
    return bool(os.getenv(_ENV_CLAVE)) and os.getenv("EDITOR_AUTO_LLM", "claude").lower() != "openai"


def _client():
    global _cliente
    if _cliente is None:
        import anthropic

        _cliente = anthropic.Anthropic(api_key=os.getenv(_ENV_CLAVE), max_retries=2, timeout=600)
    return _cliente


def analyze_transcript_json(*, system_prompt: str, user_payload: dict) -> Any:
    """Llamada a Claude con el prompt del cortador. Lanza si algo falla."""
    m = modelo()
    kwargs: dict[str, Any] = {
        "model": m,
        "max_tokens": _MAX_TOKENS,
        # Caché del system: las pasadas del mismo vídeo repiten prompt y
        # lecciones, y la relectura cuesta una décima parte.
        "system": [{"type": "text", "text": (system_prompt or "") + _PIDE_JSON,
                    "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user",
                      "content": json.dumps(user_payload, ensure_ascii=False)}],
    }
    if m.startswith("claude-haiku"):
        kwargs["thinking"] = {"type": "disabled"}
    else:
        kwargs["output_config"] = {"effort": ESFUERZO}

    with _client().messages.stream(**kwargs) as stream:
        resp = stream.get_final_message()

    try:
        u = resp.usage
        cost_tracking.record_claude(
            input_tokens=int(u.input_tokens or 0),
            output_tokens=int(u.output_tokens or 0),
            cache_write_tokens=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
            cache_read_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
            model=m,
            detail=f"editor_auto.silence_cutter ({m})",
        )
    except Exception:  # noqa: BLE001 — el coste nunca rompe la llamada
        pass

    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Claude rechazó la petición ({getattr(resp, 'stop_details', None)})")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Claude cortó la respuesta por max_tokens")
    raw = "".join(b.text for b in resp.content if b.type == "text").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
    if raw[:1] not in "{[":
        i = raw.find("{")
        raw = raw[i:] if i >= 0 else raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude devolvió JSON inválido: {e}\nRespuesta: {raw[:500]}")
