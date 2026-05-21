"""Generador de variantes A/B de un VideoPreset usando Gemini.

Dado un preset base y una lista de dimensiones a variar, llama a Gemini
con `ab_variants_director.md` y devuelve N variantes — cada una con un
`patch` (campos modificados) + una `hypothesis` (qué se está testando).

El caller (endpoint) recibe la lista y aplica `_merge_patch_into_preset`
para construir N VideoPreset completos listos para encolar. NO se
persisten en `product.video_presets` — son one-shot para A/B.

Cost tracking: cada call a Gemini se loguea automáticamente vía el
record_gemini global. El caller debe envolver en start_job para
persistir el coste.
"""

from __future__ import annotations

import logging
from typing import Any

from src.tiktok_shop.api.gemini import (
    DEFAULT_MODEL,
    generate_json,
    is_configured,
    load_system_prompt,
)
from src.tiktok_shop.models import VideoPreset, make_preset_id

logger = logging.getLogger("tiktok_shop.variants_generator")


# Dimensiones soportadas. El frontend manda exactamente estos strings.
SUPPORTED_DIMENSIONS = [
    "text_overlay",
    "text_overlay_color",
    "text_overlay_position",
    "cta_arrow",
    "voice_tone",
    "voice_script",
    "music_mood",
    "shot_style",
    "hooks_alternatives",
    "subtitle_style",
]


def generate_variants(
    base: VideoPreset,
    *,
    count: int = 4,
    dimensions: list[str] | None = None,
) -> tuple[list[VideoPreset], list[dict[str, Any]]]:
    """Genera N variantes A/B del preset base.

    Devuelve `(variants, meta)` donde:
    - `variants`: list[VideoPreset] completos (no persistidos).
    - `meta`:   list[{variant_id, hypothesis, patch}] — útil para que el
      frontend muestre QUÉ cambió en cada variante.

    Si Gemini no está configurado o falla, devuelve listas vacías.
    """
    if not is_configured():
        return [], []

    count = max(2, min(8, int(count)))
    valid_dims = [d for d in (dimensions or []) if d in SUPPORTED_DIMENSIONS]
    if not valid_dims:
        # Default razonable: variar texto + colores + CTA.
        valid_dims = ["text_overlay", "text_overlay_color", "cta_arrow"]

    try:
        system_prompt = load_system_prompt("ab_variants_director.md")
    except Exception as e:
        logger.warning("[variants_gen] prompt load falló: %s", e)
        return [], []

    base_dump = base.model_dump()
    user_prompt = (
        f"PRESET BASE (NO modificar — solo aplicar patches):\n"
        f"```json\n{_dump_compact(base_dump)}\n```\n\n"
        f"DIMENSIONS a variar: {', '.join(valid_dims)}\n\n"
        f"Genera EXACTAMENTE {count} variantes A/B siguiendo el schema."
    )

    try:
        result = generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=DEFAULT_MODEL,
            temperature=0.85,
        )
    except Exception as e:
        logger.warning("[variants_gen] Gemini falló: %s", e)
        return [], []

    if not isinstance(result, dict):
        return [], []
    raw_variants = result.get("variants") or []
    variants: list[VideoPreset] = []
    meta: list[dict[str, Any]] = []
    for v in raw_variants:
        if not isinstance(v, dict):
            continue
        suffix = str(v.get("variant_suffix", "")).strip() or " · variant"
        hypothesis = str(v.get("hypothesis", ""))[:200]
        patch = v.get("patch", {})
        if not isinstance(patch, dict):
            patch = {}
        try:
            variant = _apply_patch(base, patch, suffix)
        except Exception as e:
            logger.warning("[variants_gen] patch inválido ignorado: %s", e)
            continue
        variants.append(variant)
        meta.append({
            "variant_id": variant.id,
            "hypothesis": hypothesis,
            "patch_keys": _flatten_patch_keys(patch),
        })

    return variants, meta


def _apply_patch(base: VideoPreset, patch: dict[str, Any], suffix: str) -> VideoPreset:
    """Crea un VideoPreset nuevo aplicando un patch parcial al base.
    El patch puede tocar campos top-level y sub-objetos (text_overlay_style,
    subtitle_style, cta_arrow_style, hooks_alternatives, etc.)."""
    base_dump = base.model_dump()
    merged = _deep_merge(base_dump, patch)
    # ID nuevo + nombre con sufijo + source variant
    merged["id"] = make_preset_id()
    merged["name"] = (base.name or "Variant") + suffix
    merged["source"] = "ab_variant"
    return VideoPreset(**merged)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge recursivo: claves de patch sobrescriben las de base. Para
    sub-dicts hace merge profundo. Para listas, REEMPLAZA (no concatena)."""
    out = dict(base)
    for k, v in patch.items():
        if (
            isinstance(v, dict)
            and isinstance(out.get(k), dict)
        ):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _flatten_patch_keys(patch: dict[str, Any], prefix: str = "") -> list[str]:
    """Aplana las claves del patch para que el frontend muestre qué cambió.
    Ej: {"text_overlay_style": {"color": "..."}} → ["text_overlay_style.color"]."""
    keys: list[str] = []
    for k, v in patch.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys.extend(_flatten_patch_keys(v, prefix=full))
        else:
            keys.append(full)
    return keys


def _dump_compact(obj: Any) -> str:
    """Dump JSON compacto para no quemar tokens del prompt con espacios."""
    import json
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
