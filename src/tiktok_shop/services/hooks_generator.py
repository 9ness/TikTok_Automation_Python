"""Generador de hooks: variantes de hooks existentes + hooks orientados
a un tema/contexto.

Usado por la pestaña /tiktok-shop/hooks del frontend. Funciones:

- `generate_hook_variants(product, hook, n, context=None)`:
  Devuelve N variantes del hook manteniendo el ángulo. Útil cuando
  un hook ha funcionado bien y quieres iteraciones.

- `generate_themed_hooks(product, theme, n)`:
  Devuelve N hooks nuevos orientados al `theme` (ej. "verano",
  "para regalar"). Mezcla ángulos.

Ambas funciones usan Gemini Flash 2.5 (rápido, barato ~$0.002/call) y
leen el `research_context` del producto si está disponible para usar
dolores/beneficios reales.
"""

from __future__ import annotations

from typing import Any

from src.tiktok_shop.api import gemini
from src.tiktok_shop.api.gemini import load_system_prompt
from src.tiktok_shop.models import Product
from src.tiktok_shop.pipeline.preset_generator import (
    _fmt_price,
    _language_block,
    _research_block,
)


def _product_context_block(product: Product) -> str:
    """Bloque común con info del producto para inyectar en el user_prompt
    de Gemini."""
    return (
        f"Producto: {product.name}\n"
        f"Marca: {product.brand or '(sin marca)'}\n"
        f"Categoría: {product.category}"
        f"{' / ' + product.subcategory if product.subcategory else ''}\n"
        f"Precio: {_fmt_price(product)}\n"
        f"Audiencia: {', '.join(product.target_audience) or '(genérico)'}\n"
        f"Key features: {', '.join(product.key_features) or '(sin definir)'}\n"
        f"Selling points: {', '.join(product.selling_points) or '(sin definir)'}\n"
    )


def generate_hook_variants(
    product: Product,
    *,
    hook: str,
    n: int = 5,
    context: str | None = None,
    angle_hint: str | None = None,
) -> dict[str, Any]:
    """Genera N variantes del `hook` manteniendo el mismo ángulo.

    Args:
        product: para inyectar contexto (precio, audiencia, research).
        hook: el hook original a variar.
        n: cuántas variantes generar (1-15 típico).
        context: contexto opcional ("el original es de un vídeo que vendió X",
            "quiero más dramáticas", etc).
        angle_hint: si el user sabe el ángulo, fuérzalo. Si None,
            Gemini detecta automáticamente.

    Returns:
        dict con `angle_detected: str` y `variants: list[{text, rationale}]`.
    """
    n = max(1, min(15, int(n)))
    system = load_system_prompt("hooks_variants.md")
    research = _research_block(product)
    angle_block = f"\nÁNGULO objetivo (forzado por user): {angle_hint}\n" if angle_hint else ""
    ctx_block = f"\nContexto extra del user: {context}\n" if context else ""

    user_prompt = (
        f"{_product_context_block(product)}\n"
        f"{_language_block(product)}\n"
        f"{research}\n"
        f"HOOK ORIGINAL a variar:\n"
        f"  \"{hook.strip()}\"\n"
        f"{angle_block}{ctx_block}"
        f"\nGenera EXACTAMENTE {n} variantes manteniendo el mismo ángulo "
        f"psicológico. Devuelve JSON con `angle_detected` y `variants`."
    )

    result = gemini.generate_text(
        system_prompt=system,
        user_prompt=user_prompt,
        model="gemini-2.5-flash",
        expect_json=True,
        temperature=0.85,
    )
    import json
    try:
        data = json.loads(result) if isinstance(result, str) else result
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    variants_raw = data.get("variants") or []
    variants = []
    for v in variants_raw[:n]:
        if not isinstance(v, dict):
            continue
        text = str(v.get("text", "")).strip()
        if not text:
            continue
        variants.append({
            "text": text[:200],
            "rationale": str(v.get("rationale", ""))[:200],
        })

    return {
        "angle_detected": str(data.get("angle_detected", ""))[:50],
        "variants": variants,
    }


def generate_themed_hooks(
    product: Product,
    *,
    theme: str,
    n: int = 10,
) -> dict[str, Any]:
    """Genera N hooks NUEVOS orientados al `theme` específico.

    Args:
        product: para inyectar contexto.
        theme: tema/contexto libre ("verano", "para regalar", "edad >40",
            "antes de viajar", etc).
        n: cuántos hooks generar (3-20 típico).

    Returns:
        dict con `theme_interpretation: str` y `hooks: list[{text, angle, rationale}]`.
    """
    theme = (theme or "").strip()
    if not theme:
        return {
            "theme_interpretation": "(tema vacío)",
            "hooks": [],
        }
    n = max(1, min(20, int(n)))
    system = load_system_prompt("hooks_themed.md")
    research = _research_block(product)

    user_prompt = (
        f"{_product_context_block(product)}\n"
        f"{_language_block(product)}\n"
        f"{research}\n"
        f"TEMA / CONTEXTO objetivo:\n"
        f"  \"{theme}\"\n"
        f"\nGenera EXACTAMENTE {n} hooks orientados a este tema. "
        f"Mezcla ángulos psicológicos. Devuelve JSON con `theme_interpretation` "
        f"y `hooks`."
    )

    result = gemini.generate_text(
        system_prompt=system,
        user_prompt=user_prompt,
        model="gemini-2.5-flash",
        expect_json=True,
        temperature=0.85,
    )
    import json
    try:
        data = json.loads(result) if isinstance(result, str) else result
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    hooks_raw = data.get("hooks") or []
    hooks = []
    for h in hooks_raw[:n]:
        if not isinstance(h, dict):
            continue
        text = str(h.get("text", "")).strip()
        if not text:
            continue
        hooks.append({
            "text": text[:200],
            "angle": str(h.get("angle", ""))[:50],
            "rationale": str(h.get("rationale", ""))[:200],
        })

    return {
        "theme_interpretation": str(data.get("theme_interpretation", ""))[:300],
        "hooks": hooks,
    }
