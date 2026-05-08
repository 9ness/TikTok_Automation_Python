"""Veo3 director — devuelve un único string con prompt de 100 palabras max
listo para pegar en Gemini chat con las fotos del producto.
"""

from __future__ import annotations

import json

from src.tiktok_shop.api.gemini import generate_text, is_configured, load_system_prompt


def generate_veo3_prompt(
    strategy: dict,
    *,
    style: str = "cinematic_commercial",
) -> str:
    if not is_configured():
        return (
            "[CAMERA]: slow push-in. [SUBJECT]: product hero shot. "
            "[STYLE]: cinematic commercial. [NEGATIVE]: text artifacts, faces. "
            "9:16 vertical format, 8 seconds, single continuous shot. "
            "(modo mock — define GOOGLE_AI_API_KEY para generación real)"
        )

    system = load_system_prompt("veo3_director.md")
    user_msg = (
        f"Style preference: {style}\n"
        f"Strategy (JSON):\n{json.dumps(strategy, ensure_ascii=False)}\n\n"
        f"Return ONLY the prompt string. No JSON, no preamble."
    )
    text = generate_text(system, user_msg, temperature=0.8, expect_json=False)
    return text.strip()
