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
    fruit_mode: bool = False,
    fruit_hint: str = "",
    narrative_angle: str = "",
) -> str:
    if not is_configured():
        return (
            "[CAMERA]: slow push-in. [SUBJECT]: product hero shot. "
            "[STYLE]: cinematic commercial. [NEGATIVE]: text artifacts, faces. "
            "9:16 vertical format, 8 seconds, single continuous shot. "
            "(modo mock — define GOOGLE_AI_API_KEY para generación real)"
        )

    system = load_system_prompt("veo3_director.md")

    if fruit_mode:
        fruit_line = (
            f"Fruta forzada para el/la protagonista: {fruit_hint.strip()}. "
            "Úsala obligatoriamente (respeta tono/color que pide la guía).\n"
            if fruit_hint.strip()
            else "Casting de fruta: ELIGE TÚ la fruta que mejor encaje con el producto "
            "por COLOR y SEMÁNTICA según la sección MODE (p.ej. bronceador → fruta de "
            "tonos cálidos/morenos; fitness → fruta musculosa verde).\n"
        )
        angle_line = (
            f"Enfoque narrativo (forzado): {narrative_angle.strip()}.\n"
            if narrative_angle.strip()
            else "Enfoque narrativo: ELIGE TÚ el más enganchante (dramático / chismoso / "
            "cómico-burla / aspiracional) según el producto y la research.\n"
        )
        user_msg = (
            "MODE: fruit_character — escribe una MINI-HISTORIA viral de 8s con "
            "personajes de cabeza de fruta. Sigue la sección 'MODE: fruit_character' "
            "del system prompt al pie de la letra (arco narrativo + diálogo corto + "
            "CTA al carrito naranja).\n"
            f"{fruit_line}{angle_line}"
            f"Strategy (JSON):\n{json.dumps(strategy, ensure_ascii=False)}\n\n"
            "Return ONLY the prompt string. No JSON, no preamble."
        )
        text = generate_text(system, user_msg, temperature=0.95, expect_json=False)
        return text.strip()

    user_msg = (
        f"Style preference: {style}\n"
        f"Strategy (JSON):\n{json.dumps(strategy, ensure_ascii=False)}\n\n"
        f"Return ONLY the prompt string. No JSON, no preamble."
    )
    text = generate_text(system, user_msg, temperature=0.8, expect_json=False)
    return text.strip()
