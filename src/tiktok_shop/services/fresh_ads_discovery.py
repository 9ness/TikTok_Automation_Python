"""Radar v2 — descubrimiento INVERTIDO: de la inyección de ADS al producto.

## Por qué al revés

El flujo antiguo (`discovery_service`) imitaba a Kalodata: buscar productos
por keyword → abrir cada uno → deducir si tenía ADS. Tres problemas:
  1. Solo encuentras lo que se te ocurre buscar (EchoTik no tiene feed "top
     de todo"; el descubrimiento es por keyword/categoría).
  2. La señal de ADS era un PROXY inventado (engagement bajo + views altas).
  3. Las ventas por ventana (`total_sale_7d/30d`) vienen a 0 en ES → el
     "crecimiento" salía -100% para casi todo.

Aquí se pregunta al revés: **"¿qué vídeos con inyección de ADS se han
publicado en España en las últimas 24-48 h?"** → cada vídeo trae su producto
(`video_products`) → de la inyección fresca al producto. No hace falta
adivinar keywords: los anunciantes te dicen dónde están poniendo el dinero.

## La estrategia (equilibrio, no maximizar)

No buscamos el producto con MÁS ventas — buscamos el punto dulce:

    inyección de ADS reciente  +  POCOS creadores/vídeos  +  tracción

El razonamiento del operador: cuantos más creadores compiten por un producto,
más se reparte la inyección de GMV Max y menos te toca. Un producto con 488
creadores reparte el pastel entre 488. Uno con 29 (y solo 2 activos esta
semana) que ADEMÁS está recibiendo ads → ahí es más fácil que TikTok te
empuje a ti.

## Datos (verificados en vivo, ES, 2026-07-15)

  `echotik/video/list` con `video_sort_field=2` (create_time) + `sort_type=1`
  (desc) + `is_ad=1` + `sales_flag=1` → vídeos con ADS de hace ~1 día.
  OJO: sin ese sort, el orden por defecto devuelve vídeos de 400-1200 días —
  el "crawl viejo" que creíamos tener era esto, no el dato.

  `echotik/product/detail?product_ids=a,b,...` → 10 productos por request,
  con `total_ifl_cnt`, `total_ifl_video_7d_cnt`, `total_video_cnt`,
  `total_video_7d_cnt`, `total_views_7d_cnt`, comisión y precio. Poblados.

  MUERTO en ES: `total_sale_7d_cnt` / `total_sale_30d_cnt` = 0 siempre →
  el crecimiento se mide con `views_7d`.

Coste: ~18 requests por escaneo (10 páginas de vídeos + lotes de detalle).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable

from src.tiktok_shop.api import echotik_cloud
from src.tiktok_shop.models.discovery import AdsSignal, DiscoveredProduct, WinnerScore
from src.tiktok_shop.repos.discovery_repo import DiscoveryRepo

LogCallback = Callable[[str], None]


def _noop(_msg: str) -> None: ...


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _ramp_up(v: float, lo: float, hi: float) -> float:
    """lo o menos → 0 · hi o más → 100. Lineal entre medias."""
    if hi <= lo:
        return 0.0
    return _clamp((v - lo) / (hi - lo) * 100.0)


def _ramp_down(v: float, lo: float, hi: float) -> float:
    """lo o menos → 100 · hi o más → 0. Para métricas donde MENOS es mejor."""
    if hi <= lo:
        return 0.0
    return _clamp((hi - v) / (hi - lo) * 100.0)


# ═════════════════════════════════════════════════════════════════════
# Parámetros — calibrados a España (mercado pequeño, ver learnings:192)
# ═════════════════════════════════════════════════════════════════════
@dataclass
class FreshAdsParams:
    """Umbrales del score. Los defaults salen de datos reales de ES."""

    # ── Inyección de ADS ──
    # Dos modos, según si se hizo el deep-check:
    #   (a) sin deep: cuántos vídeos con ADS cayeron en el barrido. Señal
    #       pobre — barriendo 60 vídeos casi todo sale con 1 → no ordena.
    #   (b) CON deep: proporción de vídeos del producto con etiqueta AD.
    #       Es el "5 de 10 llevan la etiqueta lila" que el operador cuenta a
    #       mano en Kalodata. Esta sí discrimina.
    ads_full_at: int = 3            # (a) 3+ vídeos en la ventana → 100
    ad_ratio_full_at: float = 0.4   # (b) 40% de los vídeos con AD → 100

    # ── Demanda: ¿ALGUIEN lo compra? ──
    # El eje que faltaba, y su ausencia invirtió el ranking: el POCO F8 salía
    # 95/100 con **1 venta en toda su vida** mientras la recortadora de 3.304
    # ventas caía al 7º. "Pocos creadores" tiene DOS causas opuestas —
    # (a) nadie lo ha encontrado aún = oportunidad, (b) NADIE LO QUIERE = muerto —
    # y sin ventas es imposible distinguirlas. Que un vendedor esté inyectando
    # ADS en un producto que no vende solo significa que está quemando dinero.
    # `total_sale_cnt` es all-time (los campos 7d/30d vienen a 0 en ES).
    units_full_at: int = 500

    # ── Competencia: MENOS es mejor (el eje clave del operador) ──
    # OJO: estos umbrales van contra `real_influencers()` (creadores REALES,
    # los de la ficha de TikTok), NO contra el crudo de EchoTik. Antes iban
    # contra el crudo y, como EchoTik infravalora 2.6x, `zero_above=200`
    # estaba dejando pasar productos con ~520 creadores reales.
    # Regla del operador (Jonny): «siempre menos de 200 creadores».
    ifl_ideal_below: int = 30     # 30 reales o menos → 100
    ifl_zero_above: int = 200     # 200+ reales → 0
    # Creadores ACTIVOS esta semana: mide la competencia VIVA, no la histórica.
    ifl7d_ideal_below: int = 3    # 3 o menos activos → 100
    ifl7d_zero_above: int = 30    # 30+ → 0
    # Vídeos publicados en 7d — mismo espíritu.
    vid7d_ideal_below: int = 5
    vid7d_zero_above: int = 60

    # ── Tracción: views POR VÍDEO reciente, NO views totales ──
    # Las ventas 7d están a 0 en ES, así que el crecimiento sale de views.
    # PERO views totales premiaría la saturación (488 creadores → muchas
    # views *porque* hay 488 creadores). Lo que decide si merece la pena
    # entrar es cuánto empuje recibe CADA vídeo — que es lo que se llevaría
    # el tuyo.
    # Calibrado con datos REALES de ES (17 productos, 2026-07-15): el rango
    # observado va de 2 a ~850 views/vídeo, NO decenas de miles. Ojo:
    # `total_views_7d_cnt` es un INCREMENTO de 7 días (最近7日增量), no un
    # acumulado, y en productos con crawl viejo se queda cerca de 0.
    views_per_video_full_at: int = 800

    # ── Comisión: EUROS por venta, no porcentaje ──
    # El % engaña: 12% de un pintalabios de 10€ son 1,20€; 2% de un móvil de
    # 831€ son 16,60€; 10% del GEOMAR de 501€ son 50€. Lo que se ingresa es
    # el euro, así que se puntúa el euro. (Y encima el precio alto correlaciona
    # con menos creadores — learnings:209 ya usaba el precio como proxy.)
    commission_eur_full_at: float = 25.0
    # El % se mantiene solo como suelo mínimo en los filtros, no en el score.

    # ── Pesos (suman 1.0) ──
    # El grueso va al equilibrio demanda+competencia: producto que SE VENDE
    # con POCA gente vendiéndolo. Sin demanda, "pocos creadores" no es un
    # hueco: es un cementerio.
    w_ads: float = 0.25
    w_competition: float = 0.30   # "repartir el pastel entre menos"
    w_demand: float = 0.20        # ¿lo compra alguien? (faltaba)
    w_traction: float = 0.10
    w_commission: float = 0.15


@dataclass
class FreshAdsFilters:
    """Descartes duros. `None` = sin límite."""
    # En creadores REALES (ver real_influencers): EchoTik infravalora 2.6x,
    # así que un 250 sobre su número crudo dejaba pasar ~650 reales.
    max_influencers: int | None = 250        # pastel demasiado repartido
    max_influencers_7d: int | None = None    # competencia viva
    max_videos_7d: int | None = None
    # SUELO DE DEMANDA — el filtro que faltaba. Un producto con ~0 ventas no
    # es un hueco de mercado, es un producto que nadie quiere; da igual que
    # tenga pocos creadores y ADS. Real ES: el POCO F8 tenía 1 venta y salía
    # primero con 95/100. Referencia: 160 (GEOMAR) · 766 · 1.010 · 3.304.
    min_units_sold: int = 30
    min_commission_pct: float = 0.0
    min_views_7d: int = 0
    min_score: float = 30.0
    exclude_zero_commission: bool = True     # 0% → no ganas nada

    def passes(self, c: DiscoveredProduct) -> tuple[bool, str]:
        if self.exclude_zero_commission and c.commission_pct <= 0:
            return False, "comisión 0%"
        if c.units_sold < self.min_units_sold:
            return False, f"solo {c.units_sold} ventas (<{self.min_units_sold}) — nadie lo compra"
        ifl = real_influencers(c)
        if self.max_influencers is not None and ifl > self.max_influencers:
            return False, f"~{ifl} creadores reales (>{self.max_influencers})"
        if self.max_influencers_7d is not None and c.influencers_7d > self.max_influencers_7d:
            return False, f"{c.influencers_7d} creadores activos 7d"
        if self.max_videos_7d is not None and c.video_count_7d > self.max_videos_7d:
            return False, f"{c.video_count_7d} vídeos en 7d"
        if c.commission_pct < self.min_commission_pct:
            return False, f"comisión {c.commission_pct:.0f}%"
        if c.views_7d < self.min_views_7d:
            return False, f"{c.views_7d} views 7d"
        if c.score.total < self.min_score:
            return False, f"score {c.score.total:.0f}"
        return True, ""


# ═════════════════════════════════════════════════════════════════════
# SCORE
# ═════════════════════════════════════════════════════════════════════
# ── Corrección del recuento de creadores de EchoTik ──────────────────
# EchoTik INFRAVALORA los creadores de forma SISTEMÁTICA. Contrastado contra
# la ficha del Creator Center (la fuente de verdad de TikTok):
#
#     GLAIRIS   EchoTik 126 → real 330   = 2.62x
#     ARMONIAS  EchoTik  47 → real 122   = 2.60x
#
# Que las dos razones salgan casi idénticas dice que no es ruido: es una
# diferencia de definición (EchoTik solo cuenta los creadores que tiene
# rastreados). Por eso se corrige con una constante en vez de obligar al
# operador a verificar producto por producto — que es trabajo manual que
# mata la automatización entera.
#
# Para ORDENAR daría igual (un factor constante no cambia el orden); lo que
# rompía eran los UMBRALES: `max_influencers=250` sobre el número de EchoTik
# dejaba pasar productos con ~650 creadores reales.
#
# ⚠️ n=2. Es una calibración de dos puntos, no una ley. Conviene re-medirla
# de vez en cuando abriendo UNA ficha y comparando (no todas).
ECHOTIK_INFLUENCER_FACTOR = 2.6


def real_influencers(c: DiscoveredProduct) -> int:
    """Creadores REALES estimados (los de la ficha de TikTok).

    `c.influencer_count` guarda el dato crudo de EchoTik sin tocar; esto es
    la estimación derivada. Todos los umbrales del score y los filtros van
    contra ESTE número, que es el que ve el operador en el Creator Center.
    """
    return int(round(c.influencer_count * ECHOTIK_INFLUENCER_FACTOR))


def views_per_video(c: DiscoveredProduct) -> float:
    """Vistas medias que se lleva CADA vídeo reciente del producto.

    La métrica que importa al afiliado: tú vas a ser un vídeo más, así que lo
    relevante no es cuánto ve el producto entero (eso sube con el nº de
    creadores y premiaría la saturación) sino cuánto empuje recibe un vídeo.
    """
    if c.video_count_7d > 0 and c.views_7d > 0:
        return c.views_7d / c.video_count_7d
    return 0.0


def commission_eur(c: DiscoveredProduct) -> float:
    """Lo que te llevas por venta, en euros. Es lo que de verdad ingresas.

    Real ES: GEOMAR 501€ × 10% = 50,10€ · POCO 831€ × 2% = 16,62€ ·
    maquillaje 10€ × 12% = 1,20€. El del 12% es el que menos paga.
    """
    price = c.min_price or c.max_price or 0.0
    return price * c.commission_pct / 100.0


def score_fresh_ad_product(
    c: DiscoveredProduct, *, params: FreshAdsParams | None = None,
) -> WinnerScore:
    """Puntúa el EQUILIBRIO, no el tamaño.

    Un producto con 13.647 ventas y 488 creadores puntúa BAJO a propósito:
    vende mucho pero el pastel va a 488 personas. Uno con inyección fresca y
    29 creadores puntúa alto aunque venda menos.
    """
    p = params or FreshAdsParams()

    # Si hicimos el deep-check, usamos la PROPORCIÓN de vídeos con etiqueta
    # AD (el "5 de 10" de Kalodata). Si no, caemos al conteo del barrido.
    if c.ads.checked and c.ads.videos_analyzed >= 3:
        ratio = c.ads.ad_labeled_videos / c.ads.videos_analyzed
        ads = _ramp_up(ratio, 0.0, p.ad_ratio_full_at)
    else:
        ads = _ramp_up(c.ad_videos_fresh, 0, p.ads_full_at)

    # Competencia: combinamos histórica (¿está saturado?) con viva (¿me estoy
    # metiendo en una pelea AHORA?). La viva pesa más: un producto con 500
    # creadores históricos pero 2 activos está abandonado = oportunidad.
    comp_total = _ramp_down(real_influencers(c), p.ifl_ideal_below, p.ifl_zero_above)
    comp_7d = _ramp_down(c.influencers_7d, p.ifl7d_ideal_below, p.ifl7d_zero_above)
    comp_vid7d = _ramp_down(c.video_count_7d, p.vid7d_ideal_below, p.vid7d_zero_above)
    # comp_total manda: es el "reparto del pastel" del que habla el operador
    # (Jonny: «siempre elige productos con menos de 200 creadores»). Sin este
    # peso, un producto con 488 creadores pero pocos activos esta semana se
    # colaba arriba.
    competition = comp_total * 0.45 + comp_7d * 0.35 + comp_vid7d * 0.20

    demand = _ramp_up(c.units_sold, 0, p.units_full_at)
    traction = _ramp_up(views_per_video(c), 0, p.views_per_video_full_at)
    commission = _ramp_up(commission_eur(c), 0, p.commission_eur_full_at)

    base = (
        ads * p.w_ads
        + competition * p.w_competition
        + demand * p.w_demand
        + traction * p.w_traction
        + commission * p.w_commission
    )

    # ── Veto por saturación ──────────────────────────────────────────
    # La regla del operador no es "muchos creadores restan un poco", es
    # «siempre elige productos con menos de 200». Como componente lineal no
    # basta: con datos reales de ES el perfume (488 creadores, 13.647 uds)
    # ganaba 54.0 a 52.5 al GEOMAR (29 creadores) porque su tracción por
    # vídeo es mayor — cierto, pero irrelevante si el pastel va a 488. Un
    # multiplicador hace que la saturación TUMBE el score en vez de matizarlo,
    # y mantiene el ranking honesto aunque se aflojen los filtros.
    gate = 0.4 + 0.6 * (_ramp_down(c.influencer_count, p.ifl_zero_above,
                                   p.ifl_zero_above * 3) / 100.0)
    total = base * gate

    reasons: list[str] = []
    if c.ads.checked and c.ads.videos_analyzed >= 3:
        reasons.append(
            f"🏷️ {c.ads.ad_labeled_videos} de {c.ads.videos_analyzed} vídeos "
            f"llevan etiqueta AD ({c.ads.ad_labeled_videos / c.ads.videos_analyzed * 100:.0f}%)"
        )
    if c.ad_videos_fresh:
        edad = f" (el más nuevo, hace {c.newest_ad_video_days:.1f}d)" if c.newest_ad_video_days is not None else ""
        reasons.append(f"📢 {c.ad_videos_fresh} vídeo(s) con ADS recién publicados{edad}")
    if c.influencers_7d <= p.ifl7d_ideal_below:
        reasons.append(f"🎯 solo {c.influencers_7d} creadores activos esta semana — pastel poco repartido")
    elif c.influencers_7d >= p.ifl7d_zero_above:
        reasons.append(f"⚠️ {c.influencers_7d} creadores activos — mucha competencia por la inyección")
    ifl = real_influencers(c)
    if ifl >= p.ifl_zero_above:
        reasons.append(f"🥵 ~{ifl} creadores en total — saturado")
    elif ifl <= p.ifl_ideal_below:
        reasons.append(f"✨ ~{ifl} creadores en total — hueco libre")
    if c.units_sold:
        reasons.append(f"🛒 {c.units_sold:,} ventas — demanda probada")
    vpv = views_per_video(c)
    if vpv:
        reasons.append(f"📈 {vpv:,.0f} views por vídeo esta semana — lo que se llevaría el tuyo")
    eur = commission_eur(c)
    if eur:
        reasons.append(f"💰 {eur:.2f}€ por venta ({c.commission_pct:.0f}% de {c.min_price:.0f}€)")
    if c.min_price >= 40:
        reasons.append(f"💸 ticket alto ({c.min_price:.0f}€) — menos creadores lo tocan")

    return WinnerScore(
        total=round(total, 1),
        demand=round(demand, 1),            # ventas reales
        low_competition=round(competition, 1),
        ads_injection=round(ads, 1),
        momentum=round(traction, 1),        # views/vídeo = tracción reciente
        commission=round(commission, 1),
        reasons=reasons,
    )


# ═════════════════════════════════════════════════════════════════════
# SCAN
# ═════════════════════════════════════════════════════════════════════
@dataclass
class _Agg:
    """Acumulador por producto mientras barremos vídeos."""
    ad_videos: int = 0
    seen: int = 0
    newest_ts: int = 0
    views: int = 0
    descs: list[str] = field(default_factory=list)


def discover_fresh_ad_products(
    *,
    region: str = "ES",
    days: float = 2.0,
    video_pages: int = 10,
    max_products: int = 40,
    deep_ads_top_n: int = 10,
    params: FreshAdsParams | None = None,
    filters: FreshAdsFilters | None = None,
    persist: bool = True,
    log_callback: LogCallback = _noop,
) -> list[DiscoveredProduct]:
    """Barre la inyección de ADS fresca de `region` y devuelve candidatos.

    Args:
        days: ventana de frescura. 2 = "lo que se está inyectando ahora".
        video_pages: páginas de 10 vídeos a barrer (1 request cada una).
        max_products: tope de productos a detallar (lotes de 10 = 1 request).
        deep_ads_top_n: a los N finalistas se les mira la PROPORCIÓN real de
            vídeos con etiqueta AD (1 request c/u). Es el "5 de 10 llevan la
            lila" de Kalodata. 0 lo desactiva.

    Nunca lanza: si EchoTik falla o no hay cuota, loguea y devuelve [].
    """
    if not echotik_cloud.echotik_is_configured():
        log_callback("⚠️ EchoTik no configurado — el Radar no puede descubrir.")
        return []

    p = params or FreshAdsParams()
    f = filters or FreshAdsFilters()
    now = int(time.time())
    cutoff = now - int(days * 86400)

    # ── 1. Barrer vídeos con ADS, del más nuevo al más viejo ─────────
    log_callback(f"📡 Buscando inyección de ADS en {region} (últimos {days:g} días)…")
    agg: dict[str, _Agg] = {}
    stopped_early = False
    pages_done = 0

    for page in range(1, max(1, video_pages) + 1):
        rows = echotik_cloud.get_fresh_ad_videos(
            region=region, page=page, page_size=10, log_callback=None,
        )
        pages_done = page
        if not rows:
            break
        oldest_in_page = None
        for r in rows:
            ts = _ts(r.get("create_time"))
            oldest_in_page = ts if oldest_in_page is None else min(oldest_in_page, ts)
            if ts and ts < cutoff:
                continue  # fuera de ventana (seguimos: el orden puede no ser perfecto)
            for pid in _product_ids(r):
                a = agg.setdefault(pid, _Agg())
                a.seen += 1
                a.ad_videos += 1
                a.views += int(r.get("total_views_cnt") or 0)
                a.newest_ts = max(a.newest_ts, ts)
                d = str(r.get("video_desc") or "").strip()
                if d and len(a.descs) < 3:
                    a.descs.append(d)
        # Orden = create_time desc → si la página entera es más vieja que la
        # ventana, las siguientes también. Parar ahorra requests.
        if oldest_in_page and oldest_in_page < cutoff:
            stopped_early = True
            break

    if not agg:
        log_callback("  ∅ Sin vídeos con ADS en la ventana.")
        return []
    log_callback(
        f"  ✓ {pages_done} páginas · {sum(a.ad_videos for a in agg.values())} vídeos con ADS"
        f" → {len(agg)} productos únicos" + (" (corte por fecha)" if stopped_early else "")
    )

    # ── 2. Detallar los productos con más inyección (lotes de 10) ────
    ranked = sorted(agg.items(), key=lambda kv: (kv[1].ad_videos, kv[1].newest_ts), reverse=True)
    pids = [pid for pid, _ in ranked[:max_products]]
    log_callback(f"🔍 Métricas de {len(pids)} productos ({(len(pids) + 9) // 10} requests)…")

    details = echotik_cloud.get_products_detail(pids, log_callback=log_callback)
    if not details:
        log_callback("  ⚠️ product/detail no devolvió nada.")
        return []

    # ── 3. Montar candidatos + score ─────────────────────────────────
    candidates: list[DiscoveredProduct] = []
    for pid in pids:
        d = details.get(pid)
        if not d:
            continue  # EchoTik no lo tiene fichado (~40% de los IDs)
        a = agg[pid]
        c = _to_candidate(pid, d, a, region=region, now=now)
        c.score = score_fresh_ad_product(c, params=p)
        candidates.append(c)

    candidates.sort(key=lambda c: c.score.total, reverse=True)

    # ── 3b. Nombre de la tienda (1 request por cada 10) ──────────────
    # No es cosmético: la URL canónica del producto está muerta, así que el
    # operador lo busca por NOMBRE en el Centro de Afiliados y varias tiendas
    # pueden vender lo mismo. La tienda es lo que identifica cuál es.
    sids = list({c.seller_id for c in candidates if c.seller_id})
    if sids:
        names = echotik_cloud.get_seller_names(sids, log_callback=None)
        for c in candidates:
            c.seller_name = names.get(c.seller_id, "")
        log_callback(f"🏪 {len(names)} tiendas identificadas")

    # ── 4. Filtrar ───────────────────────────────────────────────────
    kept: list[DiscoveredProduct] = []
    for c in candidates:
        ok, why = f.passes(c)
        if ok:
            kept.append(c)
        else:
            log_callback(f"  ✗ {c.name[:38]!r}: {why}")
    log_callback(f"🎯 {len(kept)}/{len(candidates)} pasan filtros.")

    # ── 4b. DEEP: proporción real de vídeos con etiqueta AD ──────────
    # Solo a los finalistas (1 request c/u). Barrer 60 vídeos hace que casi
    # todo salga con ad_videos_fresh=1 → ese eje no ordena nada. Aquí sí:
    # miramos SUS vídeos y contamos cuántos llevan la etiqueta, igual que el
    # operador en Kalodata.
    if deep_ads_top_n > 0 and kept:
        top = kept[:deep_ads_top_n]
        log_callback(f"🏷️ Etiqueta AD real de los {len(top)} finalistas ({len(top)} requests)…")
        for c in top:
            vids = echotik_cloud.get_product_ad_videos(
                c.product_id, region=region, limit=10, log_callback=None,
            )
            known = [v for v in vids if isinstance(v.get("ad_flag"), bool)]
            if len(known) < 3:
                continue  # muestra insuficiente → nos quedamos con el conteo
            flagged = sum(1 for v in known if v["ad_flag"])
            c.ads.videos_analyzed = len(known)
            c.ads.ad_labeled_videos = flagged
            c.ads.ads_ratio = round(flagged / len(known), 3)
            c.ads.gmv_max_likelihood = round(flagged / len(known) * 100, 1)
            c.ads.probable_boosted = flagged > 0
            c.ads.verdict = ("fuerte" if flagged / len(known) >= 0.4
                             else "media" if flagged / len(known) >= 0.2 else "baja")
            c.ads.reasons = [f"{flagged}/{len(known)} vídeos con etiqueta AD real (is_ad)"]
            c.score = score_fresh_ad_product(c, params=p)
        kept.sort(key=lambda c: c.score.total, reverse=True)

    # ── 5. Persistir ─────────────────────────────────────────────────
    if persist and kept:
        repo = DiscoveryRepo()
        for c in kept:
            repo.upsert_scored(c)
        log_callback(f"💾 {len(kept)} candidatos guardados en el Radar.")

    return kept


# ── helpers ──────────────────────────────────────────────────────────
def _ts(raw) -> int:
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _product_ids(row: dict) -> list[str]:
    """`video_products` viene como string JSON: '[1729645572555316107]'."""
    raw = row.get("video_products")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    try:
        return [str(x) for x in json.loads(raw) if x]
    except (ValueError, TypeError):
        return []


def _to_candidate(
    pid: str, d: dict, a: _Agg, *, region: str, now: int,
) -> DiscoveredProduct:
    newest_days = ((now - a.newest_ts) / 86400.0) if a.newest_ts else None
    return DiscoveredProduct(
        product_id=pid,
        name=str(d.get("product_name") or ""),
        cover_url=echotik_cloud.first_cover_url(d.get("cover_url")),
        tiktok_url=f"https://www.tiktok.com/view/product/{pid}",
        region=region,
        category_id=str(d.get("category_id") or ""),
        category_label="ADS frescos",
        units_sold=int(d.get("total_sale_cnt") or 0),
        gmv=float(d.get("total_sale_gmv_amt") or 0),
        video_count=int(d.get("total_video_cnt") or 0),
        influencer_count=int(d.get("total_ifl_cnt") or 0),
        rating=float(d.get("product_rating") or 0),
        review_count=int(d.get("review_count") or 0),
        seller_id=str(d.get("seller_id") or ""),
        min_price=float(d.get("min_price") or 0),
        max_price=float(d.get("max_price") or 0),
        commission_pct=echotik_cloud.to_pct(d.get("product_commission_rate")),
        # Señales frescas
        ad_videos_fresh=a.ad_videos,
        ad_videos_total_seen=a.seen,
        newest_ad_video_days=round(newest_days, 2) if newest_days is not None else None,
        influencers_7d=int(d.get("total_ifl_video_7d_cnt") or 0),
        video_count_7d=int(d.get("total_video_7d_cnt") or 0),
        views_7d=int(d.get("total_views_7d_cnt") or 0),
        # La señal de ADS ya no se infiere: la etiqueta es real.
        ads=AdsSignal(
            checked=True,
            videos_analyzed=a.seen,
            ad_labels_available=True,
            ad_labeled_videos=a.ad_videos,
            gmv_max_likelihood=100.0,
            probable_boosted=True,
            verdict="fuerte",
            reasons=[f"etiqueta is_ad real de EchoTik en {a.ad_videos} vídeo(s) de la ventana"],
        ),
    )
