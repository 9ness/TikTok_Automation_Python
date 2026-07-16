"""Modelos del Radar de Productos — descubrimiento automático de productos
ganadores con inyección de ADS (estrategia del operador de 100€/día).

Un `DiscoveredProduct` es un candidato salido de EchoTik (ranklist/keyword)
al que el `ads_signal` service le calcula:
  - `WinnerScore`: puntuación 0-100 ponderada (demanda, pocos creadores,
    inyección de ADS, momentum, comisión) → ordena la lista del Radar.
  - `AdsSignal`: señal de inyección de ADS inferida de los vídeos del
    producto (proxy engagement: muchas views + poco engagement + ventas =
    GMV Max inyectando ads). Réplica del truco de mirar la etiqueta "AD"
    lila en Kalodata, pero con datos de EchoTik.

Persistencia: Redis prefijo `tiktok_shop:` (ver `repos/discovery_repo.py`).
Importar un candidato crea un `Product` real (Redis + carpeta Drive).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WinnerScore(BaseModel):
    """Puntuación de "producto ganador" (0-100) con desglose explicable.

    Cada componente es 0-100; `total` es la media ponderada (pesos en
    `discovery_service.SCORE_WEIGHTS`). `reasons` son frases legibles para
    que el operador entienda por qué un producto puntúa alto/bajo sin mirar
    los números crudos."""
    total: float = 0.0
    demand: float = 0.0             # GMV / ventas → hay demanda real
    low_competition: float = 0.0    # pocos creadores → menos competencia
    ads_injection: float = 0.0      # señal de inyección de ADS (GMV Max)
    momentum: float = 0.0           # ventas acelerando (7d vs 30d)
    commission: float = 0.0         # % comisión del afiliado
    reasons: list[str] = Field(default_factory=list)


class AdsSignal(BaseModel):
    """Señal de inyección de ADS inferida de los vídeos del producto.

    `checked=False` → no se consultaron los vídeos (score usa el proxy
    barato vídeos/creador). `checked=True` → se analizaron `videos_analyzed`
    vídeos vía EchoTik `get_product_videos`.

    Deducción de "impulsado con GMV Max" (no 100%, pero combinamos varias
    señales para acertar más):
      1. Vídeos "ad-like" (muchas views + engagement bajo) que ADEMÁS venden
         → tráfico pagado que convierte (núcleo de la señal).
      2. Concentración de views/GMV en pocos vídeos → GMV Max empuja ganadores.
      3. Engagement bajo en los vídeos de más views → views compradas, no
         orgánicas.
    `gmv_max_likelihood` (0-100) resume la confianza; `probable_boosted` es
    el booleano de decisión; `reasons` explica por qué."""
    checked: bool = False
    videos_analyzed: int = 0
    ad_like_videos: int = 0          # views altas + engagement bajo
    ad_like_with_sales: int = 0      # de esos, los que además venden
    ads_ratio: float = 0.0           # ad_like / analyzed (0-1)
    selling_ads_ratio: float = 0.0   # ad_like_with_sales / analyzed (0-1)
    view_concentration: float = 0.0  # views del top vídeo / views totales (0-1)
    gmv_concentration: float = 0.0   # GMV del top vídeo / GMV total (0-1)
    top_views_engagement: float = 0.0  # engagement % medio de los vídeos top-views
    # Etiqueta "AD" real de TikTok (branded content / paid partnership),
    # leída de los vídeos vía Apify. Es la señal que el operador mira a ojo
    # en Kalodata, aquí automatizada.
    ad_labels_available: bool = False  # ¿pudimos leer la etiqueta AD?
    ad_labeled_videos: int = 0         # cuántos vídeos llevan la etiqueta AD
    gmv_max_likelihood: float = 0.0  # 0-100 confianza de "impulsado con GMV Max"
    probable_boosted: bool = False   # decisión: ¿probablemente impulsado?
    verdict: str = "desconocida"     # fuerte | media | baja | desconocida
    reasons: list[str] = Field(default_factory=list)


class DiscoveredProduct(BaseModel):
    """Candidato de producto descubierto por el Radar.

    Mezcla las métricas crudas de EchoTik con el score calculado. Se
    persiste para que el Radar sobreviva entre sesiones y se marque
    `imported=True` cuando el operador lo convierte en `Product` real."""
    product_id: str
    name: str = ""
    cover_url: str = ""
    tiktok_url: str = ""
    region: str = "ES"
    category_id: str = ""
    category_label: str = ""         # etiqueta legible de la categoría escaneada

    # Métricas EchoTik (crudas)
    units_sold: int = 0
    units_sold_7d: int = 0
    units_sold_30d: int = 0
    units_sold_60d: int = 0
    units_sold_90d: int = 0
    gmv: float = 0.0
    gmv_30d: float = 0.0
    video_count: int = 0
    video_sale_count: int = 0
    live_sale_count: int = 0
    influencer_count: int = 0
    # Computados a partir de las ventanas de ventas:
    growth_pct: float | None = None    # crecimiento reciente % (None = sin datos)
    video_sales_ratio: float = 1.0     # 1.0 = todo vídeo, 0 = todo directo (live)
    rating: float = 0.0
    review_count: int = 0
    # Tienda — imprescindible para IDENTIFICAR el producto: la URL canónica
    # `tiktok.com/view/product/<id>` está muerta (Security Check en web Y en
    # la app), así que el operador busca por NOMBRE en el Centro de Afiliados
    # y varias tiendas pueden vender lo mismo. El nombre de la tienda es lo
    # que desambigua.
    seller_id: str = ""
    seller_name: str = ""
    min_price: float = 0.0
    max_price: float = 0.0
    commission_pct: float = 0.0

    # ── Señales de inyección FRESCA (EchoTik v3 `is_ad`) ─────────────
    # Las rellena `fresh_ads_discovery`. Son los 4 ejes de la estrategia:
    # inyección reciente + POCOS creadores/vídeos + tracción.
    # Verificado en ES (2026-07-15): todos vienen poblados salvo las ventas
    # por ventana (total_sale_7d/30d = 0 siempre) → el crecimiento se mide
    # con `views_7d`, NO con ventas.
    ad_videos_fresh: int = 0             # vídeos con is_ad=1 dentro de la ventana
    ad_videos_total_seen: int = 0        # vídeos del producto vistos en el barrido
    newest_ad_video_days: float | None = None  # edad del vídeo con ADS más nuevo
    influencers_7d: int = 0              # creadores que publicaron en 7d (competencia VIVA)
    video_count_7d: int = 0              # vídeos publicados en 7d
    views_7d: int = 0                    # vistas en 7d → proxy de crecimiento

    # Computados
    score: WinnerScore = Field(default_factory=WinnerScore)
    ads: AdsSignal = Field(default_factory=AdsSignal)

    # Estado de importación
    imported: bool = False
    imported_product_id: str | None = None

    discovered_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def touch(self) -> None:
        self.updated_at = _now_iso()
