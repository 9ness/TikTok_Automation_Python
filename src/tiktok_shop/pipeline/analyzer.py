"""Product analyzer — Gemini Vision lee fotos del producto y devuelve JSON
con tipo, categoría, audiencias sugeridas, selling points, etc.

Si Gemini no está configurado, devuelve un dict mock para permitir avanzar
en la UI sin gastar API.
"""

from __future__ import annotations

from src.tiktok_shop.api.gemini import generate_json, is_configured, load_system_prompt


def analyze_product(
    photo_paths: list[str],
    *,
    extra_context: str = "",
    language: str = "es",
) -> dict:
    """Devuelve dict con shape definido en `prompts/product_analyst.md`.

    Args:
        photo_paths: rutas a las fotos del producto (jpg/png).
        extra_context: descripción libre o URL del producto en TikTok Shop.
        language: idioma para `suggested_audiences`.

    Returns:
        dict con product_type/category/key_features/has_complex_packaging_text/
        best_camera_angles/suggested_audiences/selling_points/warnings.
    """
    if not is_configured():
        return _mock_analysis(photo_paths)

    if not photo_paths:
        raise ValueError("analyze_product requiere al menos 1 foto")

    system = load_system_prompt("product_analyst.md")
    user_msg = (
        f"Analyze the attached product photos. Output language for `suggested_audiences` "
        f"and `selling_points`: {language}.\n\n"
        f"Extra context: {extra_context or '(none)'}\n\n"
        f"Return strict JSON only."
    )
    return generate_json(system, user_msg, images=photo_paths, temperature=0.5)


def _mock_analysis(photo_paths: list[str]) -> dict:
    return {
        "product_type": "producto desconocido",
        "category": "otros",
        "subcategory": None,
        "key_features": ["(Gemini no configurado — analiza manualmente)"],
        "materials_visual": [],
        "has_complex_packaging_text": False,
        "best_camera_angles": ["packshot", "in_use", "detail"],
        "suggested_audiences": [
            "Audiencia A (manual)",
            "Audiencia B (manual)",
            "Audiencia C (manual)",
            "Audiencia D (manual)",
            "Audiencia E (manual)",
        ],
        "selling_points": [],
        "warnings": [
            "Gemini no configurado — define GOOGLE_AI_API_KEY o GOOGLE_GEMINI_KEY en .env",
            f"{len(photo_paths)} fotos ignoradas en modo mock",
        ],
    }
