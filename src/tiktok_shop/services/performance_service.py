"""Servicio del feedback loop de rendimiento.

  - refresh_video_metrics: re-scrapea métricas TikTok de un vídeo publicado.
  - aggregate_performance: stats por ángulo / sonido para la UI.
  - winning_angles_block: bloque de texto con los ángulos ganadores del
    operador para inyectar en los prompts directores (preset_generator).

El criterio de "ganador" prioriza VENTAS (orders) si las hay; si el
operador aún no anota pedidos, cae a engagement (views + engagement_rate).
Así el motor aprende qué funciona DE VERDAD para este producto.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from src.tiktok_shop.api import apify_cloud
from src.tiktok_shop.models import PublishedVideo, parse_tiktok_video_id


LogCallback = Callable[[str], None]


def _noop(_msg: str) -> None: ...


def refresh_video_metrics(
    video: PublishedVideo, *, log_callback: LogCallback = _noop,
) -> PublishedVideo:
    """Refresca views/likes/comments/shares del vídeo desde Apify.
    Best-effort: si Apify no devuelve nada, deja las métricas como estaban.
    Registra el coste Apify en el job activo (si lo hay)."""
    if not video.tiktok_url:
        return video
    items = apify_cloud.fetch_videos_by_url(
        [video.tiktok_url], log_callback=log_callback,
    )
    try:
        from src.cost_tracking import record_apify_cloud
        record_apify_cloud(
            items_count=max(len(items), 1),
            queries_count=1,
            detail=f"refresh metrics {video.tiktok_url}",
        )
    except Exception:
        pass
    if not items:
        log_callback("  ⚠️ Apify no devolvió métricas — sin cambios")
        return video
    meta = apify_cloud.extract_video_metadata(items[0])
    video.views = int(meta.get("view_count") or video.views)
    video.likes = int(meta.get("like_count") or video.likes)
    video.comments = int(meta.get("comment_count") or video.comments)
    video.shares = int(meta.get("share_count") or video.shares)
    if not video.tiktok_id:
        video.tiktok_id = parse_tiktok_video_id(video.tiktok_url) or str(
            meta.get("tiktok_id") or ""
        )
    if not video.posted_at and meta.get("created_at"):
        video.posted_at = meta.get("created_at")
    video.metrics_updated_at = datetime.now(timezone.utc).isoformat()
    log_callback(
        f"  ✓ {video.views:,} views · {video.likes:,} likes · "
        f"{video.orders} pedidos"
    )
    return video


def aggregate_performance(videos: list[PublishedVideo]) -> dict[str, Any]:
    """Agrega stats para el dashboard de rendimiento de la UI."""
    if not videos:
        return {
            "total_videos": 0, "total_views": 0, "total_orders": 0,
            "total_revenue_eur": 0.0, "by_angle": [], "by_sound": [],
        }

    by_angle: dict[str, dict[str, float]] = {}
    by_sound: dict[str, dict[str, Any]] = {}
    total_views = total_orders = 0
    total_revenue = 0.0

    for v in videos:
        total_views += v.views
        total_orders += v.orders
        total_revenue += v.revenue_eur

        angle = v.angle or "(sin ángulo)"
        a = by_angle.setdefault(
            angle, {"count": 0, "views": 0, "orders": 0, "revenue": 0.0}
        )
        a["count"] += 1
        a["views"] += v.views
        a["orders"] += v.orders
        a["revenue"] += v.revenue_eur

        if v.sound_used:
            s = by_sound.setdefault(
                v.sound_used, {"count": 0, "views": 0}
            )
            s["count"] += 1
            s["views"] += v.views

    angle_rows = [
        {
            "angle": k,
            "count": int(v["count"]),
            "views": int(v["views"]),
            "orders": int(v["orders"]),
            "revenue_eur": round(v["revenue"], 2),
            "avg_views": int(v["views"] / v["count"]) if v["count"] else 0,
        }
        for k, v in by_angle.items()
    ]
    # Ranking: por pedidos primero, luego por views medias.
    angle_rows.sort(key=lambda r: (r["orders"], r["avg_views"]), reverse=True)

    sound_rows = [
        {"sound": k, "count": int(v["count"]), "views": int(v["views"])}
        for k, v in by_sound.items()
    ]
    sound_rows.sort(key=lambda r: (r["count"], r["views"]), reverse=True)

    return {
        "total_videos": len(videos),
        "total_views": total_views,
        "total_orders": total_orders,
        "total_revenue_eur": round(total_revenue, 2),
        "by_angle": angle_rows,
        "by_sound": sound_rows,
    }


def winning_angles_block(videos: list[PublishedVideo], *, min_videos: int = 2) -> str:
    """Devuelve un bloque de texto con los ángulos ganadores del operador
    para inyectar en los prompts directores. Vacío si no hay datos
    suficientes (< min_videos publicados con métricas).

    Esto cierra el feedback loop: los presets nuevos priorizan los ángulos
    que YA han demostrado vender/enganchar para este producto."""
    usable = [v for v in videos if v.views > 0 or v.orders > 0]
    if len(usable) < min_videos:
        return ""

    agg = aggregate_performance(usable)
    rows = agg["by_angle"]
    if not rows:
        return ""

    has_orders = agg["total_orders"] > 0
    lines: list[str] = []
    for r in rows[:5]:
        if has_orders:
            lines.append(
                f"  - {r['angle']}: {r['orders']} pedidos · "
                f"{r['avg_views']:,} views medias ({r['count']} vídeos)"
            )
        else:
            lines.append(
                f"  - {r['angle']}: {r['avg_views']:,} views medias "
                f"({r['count']} vídeos)"
            )

    metric = "ventas reales" if has_orders else "engagement real"
    best = rows[0]["angle"]
    return (
        "\n=== ÁNGULOS GANADORES (TUS DATOS REALES) ===\n"
        f"Estos ángulos ya han demostrado {metric} para ESTE producto en "
        "vídeos que el operador publicó. PRIORÍZALOS al generar — replica lo "
        "que funciona, no empieces de cero:\n"
        + "\n".join(lines)
        + f"\nEl ángulo nº1 ('{best}') debe tener MÁS presets que el resto.\n"
    )
