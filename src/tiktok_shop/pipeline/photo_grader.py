"""Evalúa la calidad de una foto candidata como referencia visual para
generación de vídeos AI (Seedance/Nano Banana/Veo 3).

Devuelve:
  - score 0-10
  - tipo detectado (packshot/lifestyle/detail/in_use/macro)
  - is_same_product (¿es el mismo SKU que las fotos de referencia?)
  - flags útiles (texto overlay, watermark, collage, marca)
  - razón corta

Si recibe `reference_image_paths`, las pasa a Gemini como ground truth
del producto real y le pide comparar — esto evita el problema de
"productos parecidos" cuando el usuario pega URLs (ej. variante sabor,
versión vieja del packaging, otra marca con bote similar). Si la
candidata NO es el mismo producto, el score se penaliza a max 3.

Pensado para usarse en la importación de fotos por URL: el user pega N
URLs, descargamos cada una a temp, llamamos `grade_photo()` con las
fotos source actuales como referencia y devolvemos los scores al
frontend. El user marca cuáles guardar.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.tiktok_shop.api.gemini import (
    DEFAULT_MODEL,
    generate_json,
    is_configured,
    load_system_prompt,
)

logger = logging.getLogger("tiktok_shop.photo_grader")


# Default que devuelve `grade_photo` si Gemini no está disponible.
# Score conservador 5 para que la UI las muestre todas pero sin sesgar.
_FALLBACK_GRADE: dict[str, Any] = {
    "score": 5,
    "type": "other",
    "is_same_product": True,            # sin Gemini no podemos descartar
    "same_product_confidence": "no_reference",
    "is_duplicate_of_reference": False,
    "is_branded": False,
    "has_text_overlay": False,
    "has_watermark": False,
    "is_collage": False,
    "shows_product_clearly": True,
    "reasons": "Gemini no configurado — score neutral por defecto.",
}

# Limitamos cuántas fotos de referencia mandamos para no inflar el cost
# (cada imagen son ~250 tokens). 2 packshots son suficientes para que
# Gemini infiera el producto real.
_MAX_REFERENCE_IMAGES = 2


def grade_photo(
    image_path: str,
    *,
    product_name: str = "",
    product_brand: str = "",
    product_category: str = "",
    reference_image_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Devuelve dict con score 0-10 + tipo + flags + same_product + razones.

    Si `reference_image_paths` viene relleno, Gemini compara la candidata
    con esas referencias y marca `is_same_product=false` si no parece el
    mismo SKU (regla del prompt: en ese caso score max = 3).

    Nunca lanza: si Gemini falla devuelve el fallback neutral con un
    warning en `reasons`. El caller decide si descarta o no.
    """
    if not is_configured():
        return dict(_FALLBACK_GRADE)

    try:
        system_prompt = load_system_prompt("photo_grader.md")
    except Exception as e:
        logger.warning("[photo_grader] prompt load falló: %s", e)
        return dict(_FALLBACK_GRADE, reasons=f"Prompt load falló: {e}")

    context_parts = []
    if product_name:
        context_parts.append(f"Producto: {product_name}")
    if product_brand:
        context_parts.append(f"Marca: {product_brand}")
    if product_category:
        context_parts.append(f"Categoría: {product_category}")
    context = "\n".join(context_parts) or "Sin contexto adicional."

    # Construimos la lista de imágenes — referencias PRIMERO, candidata
    # AL FINAL. El prompt deja claro que "la última imagen" es la que
    # hay que evaluar y el resto son ground truth.
    refs = _filter_existing(reference_image_paths or [])[:_MAX_REFERENCE_IMAGES]
    images = [*refs, image_path]

    if refs:
        ref_count = len(refs)
        user_prompt = (
            f"Contexto del producto:\n{context}\n\n"
            f"Adjunto {ref_count} foto(s) de REFERENCIA del producto real "
            f"(verificadas) y al final la foto CANDIDATA a evaluar.\n\n"
            "Compara y decide si la candidata es el MISMO producto. Si no "
            "lo es, marca is_same_product=false y limita el score a 3. "
            "Devuelve solo JSON."
        )
    else:
        user_prompt = (
            f"Contexto del producto:\n{context}\n\n"
            "No hay fotos de referencia previas. Evalúa la candidata "
            "(única imagen adjunta) por contexto textual.\n"
            "Marca is_same_product=true y same_product_confidence="
            "\"no_reference\". Devuelve solo JSON."
        )

    try:
        result = generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            images=images,
            model=DEFAULT_MODEL,
            temperature=0.2,  # determinístico para grading
        )
    except Exception as e:
        logger.warning("[photo_grader] Gemini falló: %s", e)
        return dict(_FALLBACK_GRADE, reasons=f"Gemini falló: {e}")

    if not isinstance(result, dict):
        return dict(_FALLBACK_GRADE, reasons="Respuesta Gemini inválida.")

    is_same = bool(result.get("is_same_product", True))
    is_duplicate = bool(result.get("is_duplicate_of_reference", False))
    raw_score = _clamp_int(result.get("score"), 0, 10, default=5)
    # Failsafe: aunque Gemini decida que no es el mismo producto, a veces
    # devuelve scores altos por inercia. Forzamos la regla del prompt.
    if not is_same:
        raw_score = min(raw_score, 3)
    # Penalización por duplicado (mismo plano que la referencia). Failsafe
    # en código por si Gemini la pasa por alto. -3 puntos.
    if is_duplicate and refs:
        raw_score = max(0, raw_score - 3)

    return {
        "score": raw_score,
        "type": _safe_str(
            result.get("type"),
            allowed={"packshot", "lifestyle", "detail", "in_use", "macro", "other"},
            default="other",
        ),
        "is_same_product": is_same,
        "same_product_confidence": _safe_str(
            result.get("same_product_confidence"),
            allowed={"high", "medium", "low", "no_reference"},
            default="no_reference" if not refs else "medium",
        ),
        "is_duplicate_of_reference": is_duplicate,
        "is_branded": bool(result.get("is_branded", False)),
        "has_text_overlay": bool(result.get("has_text_overlay", False)),
        "has_watermark": bool(result.get("has_watermark", False)),
        "is_collage": bool(result.get("is_collage", False)),
        "shows_product_clearly": bool(result.get("shows_product_clearly", True)),
        "reasons": str(result.get("reasons", ""))[:500],
    }


def _filter_existing(paths: list[str]) -> list[str]:
    return [p for p in paths if p and os.path.exists(p)]


def _clamp_int(val: Any, lo: int, hi: int, *, default: int) -> int:
    try:
        v = int(val)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _safe_str(val: Any, *, allowed: set[str], default: str) -> str:
    if isinstance(val, str) and val in allowed:
        return val
    return default
