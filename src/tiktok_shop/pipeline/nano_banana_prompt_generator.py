"""Nano Banana 2 prompt generator.

A diferencia de los otros pipelines, NO renderiza nada. Devuelve un string
listo para pegar en Gemini chat con Nano Banana 2 + las fotos source. El
usuario sube manualmente las fotos generadas que vuelven a entrar en
`photos_generated` del producto.
"""

from __future__ import annotations

from src.tiktok_shop.api.gemini import generate_text, is_configured, load_system_prompt


def generate_nano_banana_prompt(
    *,
    product_name: str,
    product_description: str = "",
    use_cases: list[str] | None = None,
    n_angles: int = 5,
    photo_paths: list[str] | None = None,
) -> str:
    """Devuelve un único prompt string listo para Gemini chat con Nano Banana 2.

    Args:
        product_name: nombre comercial del producto.
        product_description: descripción libre + selling points concatenados.
        use_cases: lista de estilos deseados (asmr_macro, lifestyle...).
        n_angles: número de fotos a pedir (4-8 recomendado).
        photo_paths: fotos source para que Gemini se base en ellas. Opcional.
    """
    n_angles = max(4, min(8, n_angles))
    use_cases = use_cases or ["packshot", "lifestyle", "macro"]

    if not is_configured():
        return _mock_prompt(product_name, n_angles, use_cases)

    system = load_system_prompt("nano_banana_director.md")
    user_msg = (
        f"Product name: {product_name}\n"
        f"Product description: {product_description or '(none)'}\n"
        f"Desired use cases / styles: {', '.join(use_cases)}\n"
        f"Number of distinct angles to request: {n_angles}\n\n"
        f"Return ONLY the prompt string. No JSON, no preamble, no markdown."
    )
    text = generate_text(
        system, user_msg,
        temperature=0.6, expect_json=False, images=photo_paths or None,
    )
    return text.strip()


def _mock_prompt(product_name: str, n_angles: int, use_cases: list[str]) -> str:
    angles_lines = "\n".join(
        f"{i+1}. {use_cases[i % len(use_cases)].replace('_', ' ').title()} angle"
        for i in range(n_angles)
    )
    return (
        f"Generate professional product photography of {product_name} from the "
        f"attached reference images:\n\n"
        f"{angles_lines}\n\n"
        f"CRITICAL: Maintain EXACT product appearance across all images — same "
        f"colors, same labels, same proportions. Only angle and context vary.\n"
        f"9:16 vertical format. Ultra high quality. Photorealistic. No watermarks.\n"
        f"-- (modo mock — define GOOGLE_AI_API_KEY o GOOGLE_GEMINI_KEY para "
        f"prompt real generado por Gemini)"
    )
