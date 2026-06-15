"""Scoring de "producto ganador" + detección de inyección de ADS.

Replica la estrategia del operador de 100€/día (capturas Telegram):
  «selecciona productos que reciban inyección de ADS y que tengan POCOS
   creadores — esa es la clave». En Kalodata él mira la etiqueta lila "AD"
   en la pestaña Creators. Aquí lo inferimos con datos de EchoTik:

  1. Nivel producto (barato, sin requests extra) — `score_product()`:
       demanda (GMV) · pocos creadores · momentum (7d vs 30d) · comisión
       + proxy de ads (vídeos por creador alto = boosting).

  2. Nivel vídeo (1 request EchoTik/producto) — `ads_injection_signal()`:
       analiza los vídeos del producto. Un vídeo con muchas views y poco
       engagement es tráfico pagado (mismo proxy que
       `research_service._split_paid_organic`). Si además VENDE, es señal de
       que GMV Max está inyectando ads y convirtiendo → el producto ideal.

Todo es lógica pura y testeable sin red. Las llamadas a EchoTik las hace el
`discovery_service`; aquí solo recibimos dicts ya normalizados.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.tiktok_shop.models.discovery import AdsSignal, WinnerScore


# ═════════════════════════════════════════════════════════════════════
# Parámetros (umbrales) — ajustables desde la UI del Radar
# ═════════════════════════════════════════════════════════════════════
@dataclass
class ScoreParams:
    """Umbrales que definen qué es un "ganador". Defaults calibrados a la
    estrategia de las capturas (pocos creadores <200, demanda real)."""
    # Demanda: GMV (30d si está, si no total) que da puntuación plena.
    demand_full_gmv_eur: float = 30_000.0
    # Pocos creadores: score pleno por debajo de `comp_full_below`, cae a 0
    # en `comp_zero_above`. El operador busca <200 creadores.
    comp_full_below: int = 50
    comp_zero_above: int = 300
    # Comisión: % que da score pleno (afiliado quiere alta comisión).
    commission_full_pct: float = 25.0
    # Proxy de ads sin mirar vídeos: vídeos por creador. >1 creador publica
    # varios o hay boosting. `vpc_full` da score pleno.
    vpc_zero_at: float = 1.0
    vpc_full_at: float = 4.0

    # Pesos de cada componente en el total (suman 1.0). ads_injection y
    # low_competition pesan más porque son "la clave" según el operador.
    w_ads: float = 0.30
    w_competition: float = 0.25
    w_demand: float = 0.20
    w_momentum: float = 0.15
    w_commission: float = 0.10


@dataclass
class AdsParams:
    """Umbrales de la deducción "impulsado con GMV Max" a nivel vídeo."""
    # Un vídeo es "ad-like" si engagement_rate < paid_max_eng_pct y tiene
    # al menos min_views_paid views (descarta vídeos pequeños sin señal).
    paid_max_eng_pct: float = 1.0
    min_views_paid: int = 3_000
    # Mínimo de vídeos para fiarnos de la deducción.
    min_videos: int = 3
    # Cortes de likelihood (0-100) → verdict + decisión.
    boosted_threshold: float = 50.0   # >= → probable_boosted = True
    strong_threshold: float = 66.0    # verdict "fuerte"
    medium_threshold: float = 40.0    # verdict "media"


# ═════════════════════════════════════════════════════════════════════
# Helpers de escala
# ═════════════════════════════════════════════════════════════════════
def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _ramp_down(value: float, full_below: float, zero_above: float) -> float:
    """100 si value<=full_below, 0 si value>=zero_above, lineal entre medias.
    'Menos es mejor' (ej. nº de creadores)."""
    if zero_above <= full_below:
        return 100.0 if value <= full_below else 0.0
    if value <= full_below:
        return 100.0
    if value >= zero_above:
        return 0.0
    frac = (value - full_below) / (zero_above - full_below)
    return _clamp(100.0 * (1.0 - frac))


def _ramp_up(value: float, full_at: float) -> float:
    """0 en 0, 100 en `full_at`, lineal. 'Más es mejor' saturando arriba."""
    if full_at <= 0:
        return 0.0
    return _clamp(value / full_at * 100.0)


# ═════════════════════════════════════════════════════════════════════
# Nivel producto — score barato (sin requests extra)
# ═════════════════════════════════════════════════════════════════════
def score_product(
    p: dict,
    *,
    params: ScoreParams | None = None,
    ads: AdsSignal | None = None,
) -> WinnerScore:
    """Calcula el `WinnerScore` de un producto EchoTik normalizado.

    `ads`: si se pasa un `AdsSignal.checked=True`, la componente de inyección
    de ADS usa la señal real de vídeos; si no, cae al proxy vídeos/creador.
    """
    pa = params or ScoreParams()

    units_7d = int(p.get("units_sold_7d") or 0)
    units_30d = int(p.get("units_sold_30d") or 0)
    gmv_30d = float(p.get("gmv_30d") or 0.0)
    gmv_total = float(p.get("gmv") or 0.0)
    influencers = int(p.get("influencer_count") or 0)
    video_count = int(p.get("video_count") or 0)
    commission = float(p.get("commission_pct") or 0.0)

    reasons: list[str] = []

    # --- Demanda (GMV) ---
    gmv_used = gmv_30d if gmv_30d > 0 else gmv_total
    demand = _ramp_up(gmv_used, pa.demand_full_gmv_eur)
    if gmv_used > 0:
        reasons.append(f"💶 GMV ~€{gmv_used:,.0f}")

    # --- Pocos creadores ---
    low_comp = _ramp_down(influencers, pa.comp_full_below, pa.comp_zero_above)
    if influencers:
        tag = "pocos" if influencers < pa.comp_zero_above else "muchos"
        reasons.append(f"👥 {influencers} creadores ({tag})")

    # --- Inyección de ADS ---
    if ads is not None and ads.checked:
        ads_score = _clamp(ads.gmv_max_likelihood)
        label = f" · {ads.ad_labeled_videos} con etiqueta AD" if ads.ad_labels_available else ""
        reasons.append(
            f"📢 GMV Max {ads.verdict} ({ads.gmv_max_likelihood:.0f}/100){label}"
        )
    else:
        # Proxy barato: vídeos por creador. >1 sugiere que se publican
        # varios vídeos por creador o hay boosting (señal débil de ads).
        vpc = video_count / influencers if influencers > 0 else 0.0
        span = max(0.01, pa.vpc_full_at - pa.vpc_zero_at)
        ads_score = _clamp((vpc - pa.vpc_zero_at) / span * 100.0) if vpc > 0 else 0.0
        if vpc > 0:
            reasons.append(f"📢 ADS (estimado): {vpc:.1f} vídeos/creador")

    # --- Momentum (ventas acelerando) ---
    momentum = 50.0  # neutro si no hay datos 7d/30d
    if units_30d > 0 and units_7d > 0:
        daily_recent = units_7d / 7.0
        daily_avg = units_30d / 30.0
        ratio = daily_recent / daily_avg if daily_avg > 0 else 0.0
        momentum = _clamp(ratio * 50.0)  # ratio 2x = 100
        if ratio >= 1.2:
            reasons.append(f"📈 acelerando (x{ratio:.1f} vs media 30d)")
        elif ratio <= 0.7:
            reasons.append(f"📉 enfriando (x{ratio:.1f} vs media 30d)")

    # --- Comisión ---
    commission_score = _ramp_up(commission, pa.commission_full_pct)
    if commission:
        reasons.append(f"💰 comisión {commission:.0f}%")

    total = (
        pa.w_ads * ads_score
        + pa.w_competition * low_comp
        + pa.w_demand * demand
        + pa.w_momentum * momentum
        + pa.w_commission * commission_score
    )

    return WinnerScore(
        total=round(total, 1),
        demand=round(demand, 1),
        low_competition=round(low_comp, 1),
        ads_injection=round(ads_score, 1),
        momentum=round(momentum, 1),
        commission=round(commission_score, 1),
        reasons=reasons,
    )


# ═════════════════════════════════════════════════════════════════════
# Nivel vídeo — señal de inyección de ADS real
# ═════════════════════════════════════════════════════════════════════
def ads_injection_signal(
    videos: list[dict],
    *,
    params: AdsParams | None = None,
) -> AdsSignal:
    """Deduce si un producto está IMPULSADO con GMV Max combinando varias
    señales de sus vídeos. No es 100%, pero acierta más que una sola pista.

    Cada vídeo (dict) puede traer: `views`, `likes`, `comments`, `shares`,
    `units_sold` (EchoTik), `gmv` (EchoTik), `ad_flag` (etiqueta AD real de
    TikTok vía Apify, bool|None).

    Señales que combinamos en `gmv_max_likelihood` (0-100):
      A. Etiqueta AD real (Apify) — la más fuerte si está disponible.
      B. Vídeos ad-like que VENDEN (EchoTik) — tráfico pagado que convierte.
      C. % de views que vienen de vídeos ad-like (reach comprado).
      D. Engagement bajo en los vídeos de más views (views no orgánicas).
      E. Concentración de views en pocos vídeos (GMV Max empuja ganadores).
    """
    ap = params or AdsParams()

    rows: list[dict[str, Any]] = []
    total_views = 0
    total_gmv = 0.0
    has_sales = False
    has_labels = False
    for v in videos:
        views = int(v.get("views") or 0)
        if views <= 0:
            continue
        eng = (
            int(v.get("likes") or 0)
            + int(v.get("comments") or 0)
            + int(v.get("shares") or 0)
        )
        er = eng / views * 100.0
        units = int(v.get("units_sold") or 0)
        gmv = float(v.get("gmv") or 0.0)
        ad_flag = v.get("ad_flag", None)
        if units > 0:
            has_sales = True
        if isinstance(ad_flag, bool):
            has_labels = True
        rows.append({"views": views, "er": er, "units": units,
                     "gmv": gmv, "ad_flag": ad_flag})
        total_views += views
        total_gmv += gmv

    analyzed = len(rows)
    if analyzed == 0:
        return AdsSignal(checked=True, videos_analyzed=0, verdict="desconocida",
                         reasons=["sin vídeos legibles para deducir ADS"])

    ad_like = [r for r in rows if r["er"] < ap.paid_max_eng_pct and r["views"] >= ap.min_views_paid]
    ad_like_sales = [r for r in ad_like if r["units"] > 0]
    ads_ratio = len(ad_like) / analyzed
    selling_ratio = len(ad_like_sales) / analyzed

    top_views = max(r["views"] for r in rows)
    view_conc = top_views / total_views if total_views > 0 else 0.0
    gmv_conc = (max(r["gmv"] for r in rows) / total_gmv) if total_gmv > 0 else 0.0
    paid_views = sum(r["views"] for r in ad_like)
    paid_view_share = paid_views / total_views if total_views > 0 else 0.0

    top_by_views = sorted(rows, key=lambda r: r["views"], reverse=True)[:5]
    top_er = sum(r["er"] for r in top_by_views) / len(top_by_views)

    labeled = [r for r in rows if isinstance(r["ad_flag"], bool)]
    ad_labeled = sum(1 for r in labeled if r["ad_flag"])
    label_ratio = ad_labeled / len(labeled) if labeled else 0.0

    # ── Likelihood: blend ponderado de las señales disponibles ──
    low_eng_score = _clamp((3.0 - top_er) / 3.0 * 100.0)  # er 0%→100, 3%→0
    comps: list[tuple[float, float]] = [
        (_clamp(paid_view_share * 100.0), 0.25),
        (low_eng_score, 0.15),
        (_clamp(view_conc * 100.0), 0.10),
    ]
    if has_labels:
        comps.append((_clamp(label_ratio * 100.0 * 1.5), 0.40))  # 67% etiquetados → 100
    if has_sales:
        comps.append((_clamp(selling_ratio * 100.0 * 2.5), 0.30))  # 40% → 100
    wsum = sum(w for _, w in comps)
    likelihood = sum(s * w for s, w in comps) / wsum if wsum else 0.0

    if analyzed < ap.min_videos:
        likelihood *= 0.6  # poca muestra → baja la confianza

    if likelihood >= ap.strong_threshold:
        verdict = "fuerte"
    elif likelihood >= ap.medium_threshold:
        verdict = "media"
    elif likelihood > 0:
        verdict = "baja"
    else:
        verdict = "desconocida"
    probable = likelihood >= ap.boosted_threshold and analyzed >= ap.min_videos

    reasons: list[str] = []
    if has_labels:
        reasons.append(f"🏷️ {ad_labeled}/{len(labeled)} vídeos con etiqueta AD real")
    if has_sales and ad_like_sales:
        reasons.append(f"💸 {len(ad_like_sales)} vídeos pagados (views↑/eng↓) que VENDEN")
    if paid_view_share >= 0.3:
        reasons.append(f"📊 {paid_view_share*100:.0f}% de las views parecen pagadas")
    if view_conc >= 0.5:
        reasons.append(f"🎯 1 vídeo concentra {view_conc*100:.0f}% de las views")
    if top_er < ap.paid_max_eng_pct:
        reasons.append(f"📉 engagement {top_er:.1f}% en los vídeos de más views (bajo)")
    if analyzed < ap.min_videos:
        reasons.append(f"⚠️ solo {analyzed} vídeos — confianza reducida")

    return AdsSignal(
        checked=True,
        videos_analyzed=analyzed,
        ad_like_videos=len(ad_like),
        ad_like_with_sales=len(ad_like_sales),
        ads_ratio=round(ads_ratio, 3),
        selling_ads_ratio=round(selling_ratio, 3),
        view_concentration=round(view_conc, 3),
        gmv_concentration=round(gmv_conc, 3),
        top_views_engagement=round(top_er, 2),
        ad_labels_available=has_labels,
        ad_labeled_videos=ad_labeled,
        gmv_max_likelihood=round(likelihood, 1),
        probable_boosted=probable,
        verdict=verdict,
        reasons=reasons,
    )


# ═════════════════════════════════════════════════════════════════════
# Filtros de descubrimiento
# ═════════════════════════════════════════════════════════════════════
@dataclass
class DiscoveryFilters:
    """Filtros que aplica el Radar antes de mostrar un candidato."""
    max_influencers: int = 250       # "pocos creadores" — descarta saturados
    min_gmv_eur: float = 1_000.0     # demanda mínima para que valga la pena
    min_commission_pct: float = 0.0  # 0 = sin filtro de comisión
    min_score: float = 40.0          # score total mínimo para entrar al Radar
    require_ads_signal: bool = False  # si True, exige ads.probable_boosted
    excluded_verdicts: list[str] = field(default_factory=list)

    def passes(self, units_filter_ctx: dict, score: WinnerScore, ads: AdsSignal) -> bool:
        influencers = int(units_filter_ctx.get("influencer_count") or 0)
        gmv = float(units_filter_ctx.get("gmv_30d") or units_filter_ctx.get("gmv") or 0.0)
        commission = float(units_filter_ctx.get("commission_pct") or 0.0)
        if influencers and influencers > self.max_influencers:
            return False
        if gmv < self.min_gmv_eur:
            return False
        if commission < self.min_commission_pct:
            return False
        if score.total < self.min_score:
            return False
        if self.require_ads_signal and not ads.probable_boosted:
            return False
        if ads.verdict in self.excluded_verdicts:
            return False
        return True
