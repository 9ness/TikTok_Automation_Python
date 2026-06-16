"""Carousel director — genera el guion de un carrusel TikTok (slides de
imagen + texto on-screen + caption) listo para que el operador genere las
imágenes en Nano Banana 2 / un image model y las suba.

Como Veo3/Nano Banana, es prompt-only: NO renderiza imágenes. Devuelve un
dict estructurado (ver `prompts/carousel_director.md`). Si Gemini no está
configurado, devuelve un mock para no bloquear la UI.

Reusa `research_context` del producto si existe (pains/objeciones/hooks
reales) para abrir con dolor real y neutralizar la objeción top.
"""

from __future__ import annotations

from typing import Any

from src.tiktok_shop.api.gemini import generate_json, is_configured, load_system_prompt
from src.tiktok_shop.models import Product


def generate_carousel(
    product: Product,
    *,
    n_slides: int = 6,
    angle: str = "",
    audience: str = "",
    language: str | None = None,
) -> dict[str, Any]:
    """Devuelve el dict del carrusel (concept, hook_caption, slides[], ...).

    Args:
        n_slides: nº de slides (hook + cuerpo + cta). Clamp 3-10.
        angle: ángulo opcional forzado por el operador (ej. "antes/después").
        audience: audiencia objetivo (si vacío, usa la del producto).
        language: "es" | "en" — idioma de los textos del carrusel. Si None,
            se deriva del `product.language` (es_* → es, en_* → en).
    """
    n_slides = max(3, min(10, n_slides))
    audience = audience or ", ".join(product.target_audience[:3])
    lang = _norm_lang(language or product.language)

    if not is_configured():
        data = _mock_carousel(product, n_slides)
        data["language"] = lang
        return data

    system = load_system_prompt("carousel_director.md")
    user_msg = _build_user_prompt(product, n_slides, angle, audience, lang)
    data = generate_json(system, user_msg, temperature=0.7)
    if not isinstance(data, dict):
        return _mock_carousel(product, n_slides)
    data.setdefault("slides", [])
    data.setdefault("language", lang)
    return data


def _norm_lang(raw: str | None) -> str:
    """Normaliza a 'es' | 'en'. Default 'es'."""
    s = (raw or "es").lower()
    return "en" if s.startswith("en") else "es"


def _build_user_prompt(
    product: Product, n_slides: int, angle: str, audience: str, lang: str = "es",
) -> str:
    lang_name = "Spanish (Spain)" if lang == "es" else "English"
    rc = product.research_context
    sp = ", ".join(product.selling_points[:6]) or "(none)"
    feats = ", ".join(product.key_features[:6]) or "(none)"

    lines = [
        f"Product: {product.name}",
        f"Brand: {product.brand or '—'}",
        f"Category: {product.category}",
        f"OUTPUT LANGUAGE: {lang} ({lang_name}) — write on_screen_text, hook_caption "
        f"and the text rendered in images in this language.",
        f"Target audience: {audience or '—'}",
        f"Selling points: {sp}",
        f"Key features: {feats}",
        f"Number of slides: {n_slides}",
    ]
    if angle:
        lines.append(f"Forced angle: {angle}")

    # Inyectar research context real si lo hay (mejor que inventar).
    if rc.customer_pains:
        lines.append(f"Real customer pains: {', '.join(rc.customer_pains[:5])}")
    if rc.objections:
        lines.append(f"Top objections to neutralize: {', '.join(rc.objections[:4])}")
    if rc.proven_hooks:
        lines.append(f"Proven hooks (adapt, don't copy): {', '.join(rc.proven_hooks[:5])}")
    if rc.viral_patterns:
        lines.append(f"Viral patterns in niche: {', '.join(rc.viral_patterns[:4])}")

    lines.append("\nReturn ONLY the strict JSON described in the system prompt.")
    return "\n".join(lines)


def _mock_carousel(product: Product, n_slides: int) -> dict[str, Any]:
    roles = ["hook", "problem", "proof", "feature", "objection", "cta"]
    slides = []
    for i in range(n_slides):
        role = roles[i] if i < len(roles) - 1 and i < n_slides - 1 else (
            "cta" if i == n_slides - 1 else roles[min(i, len(roles) - 1)]
        )
        slides.append({
            "slide_number": i + 1,
            "role": role,
            "on_screen_text": f"({role}) — texto manual",
            "image_prompt": (
                f"Professional 9:16 product photography of {product.name}, "
                f"clean background, studio lighting. Maintain exact product "
                f"appearance: same colors, labels, proportions."
            ),
            "keep_product_identical": True,
        })
    return {
        "concept": "(mock — define GOOGLE_GEMINI_KEY para carrusel real)",
        "hook_caption": f"{product.name} 🛒 #fyp #tiktokshop",
        "slides": slides,
        "image_style_guide": "Mismo producto, fondo y luz coherentes en todas.",
        "human_presence_note": "Añade manos sujetando el producto en 1 slide.",
    }
