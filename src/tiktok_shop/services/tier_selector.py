"""Recomendación de tier por producto.

⚠️ STUB. La heurística real (basada en `performance_history`) requiere datos
agregados que aún no tenemos. Hasta que haya histórico real, devolvemos el
`default_tier` configurado en el producto.

Cuando haya datos: si `total_orders_generated >= N` → recomendar subir un
tier. Si tras X vídeos no hay órdenes → quedarse en standard. Etc.
"""

from __future__ import annotations

from src.tiktok_shop.models import Product


def recommend_tier(product: Product) -> str:
    """Devuelve el tier recomendado para este producto.

    Implementación actual: devuelve `product.video_config.default_tier`
    (sin lógica adicional).
    """
    return product.video_config.default_tier
