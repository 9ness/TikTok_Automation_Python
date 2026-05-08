"""Reconstrucción de `params` para re-encolar un VideoGeneration (FUNC 2).

Centraliza la lógica de "Regenerar idéntico" / "Regenerar con cambios" para
que sea testeable sin Streamlit.

Decisiones:
- Las fotos NO se regeneran exactas a partir del histórico (`photos_used` son
  filenames; el catálogo del producto puede haber cambiado desde la generación
  original — fotos eliminadas, añadidas, soft-deleted). En "regenerar idéntico"
  dejamos `clip_photo_overrides=None` para que el director auto-asigne con
  las fotos disponibles AHORA.
- Si el usuario quiere control total sobre fotos, debe usar "Regenerar con
  cambios" y elegir manualmente.
- `temp_folder` se fija a `./temp_work` (default global del proyecto).
"""

from __future__ import annotations

from typing import Any

from src.tiktok_shop.models import TikTokUser, Product, VideoGeneration


def build_regen_params(
    gen: VideoGeneration,
    user: TikTokUser,
    product: Product,
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construye el `params` dict para encolar una regeneración.

    Args:
        gen: VideoGeneration original a regenerar.
        user: TikTokUser actual de `gen.user_id` (para `language` consistente).
        product: Product actual de `gen.product_id`.
        overrides: dict opcional con cambios que se aplican encima del idéntico.
            Keys aceptables: `tier`, `duration`, `resolution`, `hook_category`,
            `hook_text`, `audience`, `voice_id`, `with_voice`, `is_shoppable`,
            `clip_photo_overrides`, `pro_ref_photo_overrides`.

    Returns:
        Dict con la misma forma que el `params` que arma `tab_generator.py`
        cuando el usuario hace click en "Encolar generación".
    """
    from src.tiktok_shop.config import DEFAULT_VIDEO_STRATEGY

    base: dict[str, Any] = {
        "user_id": user.id,
        "product_id": product.id,
        "tier": gen.tier_used,
        "duration": gen.duration_seconds,
        "resolution": gen.resolution,
        "hook_category": gen.hook.category if gen.hook else "general",
        "hook_text": gen.hook.text if gen.hook else "",
        "audience": user.niche or "Generalista",  # no se persiste en gen
        "voice_id": gen.voice_used.voice_id if gen.voice_used else "Spanish_EnergeticBoy",
        "with_voice": True,  # no se persiste en gen — asumimos voz ON por defecto
        "language": gen.language or user.default_language or "es",
        "is_shoppable": gen.video_type == "shoppable",
        "ai_disclosure": gen.ai_disclosure,
        "temp_folder": "./temp_work",
        # Por defecto NO reusamos asignaciones de foto (catálogo puede haber
        # cambiado). El director auto-asigna con las fotos disponibles ahora.
        "clip_photo_overrides": None,
        "pro_ref_photo_overrides": None,
        # FUNC 5: la estrategia no se persiste en VideoGeneration aún;
        # regenerar mantiene el default global (dynamic). Si el usuario
        # quiere otra, debe usar "regenerar con cambios" y pasarla en overrides.
        "strategy": DEFAULT_VIDEO_STRATEGY,
        # Trazabilidad: marcamos de qué generación viene
        "regenerated_from": gen.id,
    }
    if overrides:
        base.update(overrides)
    return base


def build_regen_title(
    gen: VideoGeneration,
    user: TikTokUser,
    product: Product,
    *,
    tier_label: str,
    is_with_changes: bool = False,
) -> str:
    """Título visual del job en la cola — añade marca de regeneración +
    prefijo corto del `gen.id` original para trazabilidad visual."""
    suffix = "🔁 regen+" if is_with_changes else "🔁 regen"
    return f"{user.username} · {product.name} · {tier_label} · {suffix} {gen.id[:6]}"
