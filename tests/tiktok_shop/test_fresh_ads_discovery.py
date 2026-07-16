"""El score debe premiar el EQUILIBRIO, no el tamaño.

Casos calcados de datos reales de ES (probados en vivo 2026-07-15) para que
la calibración no se vaya con un refactor: el perfume de 488 creadores tiene
que perder contra el GEOMAR de 29 aunque venda 85 veces más.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.tiktok_shop.models.discovery import DiscoveredProduct  # noqa: E402
from src.tiktok_shop.services.fresh_ads_discovery import (  # noqa: E402
    FreshAdsFilters,
    _product_ids,
    commission_eur,
    score_fresh_ad_product,
    views_per_video,
)


def _p(**kw) -> DiscoveredProduct:
    base = dict(product_id="1", name="x", commission_pct=10.0)
    base.update(kw)
    return DiscoveredProduct(**base)


# ── Datos REALES de ES ───────────────────────────────────────────────
GEOMAR = _p(  # 29 creadores, 2 activos, 10% com, 501€ → el punto dulce
    product_id="geomar", name="Kit Anticelulitis", ad_videos_fresh=1,
    newest_ad_video_days=1.1, influencer_count=29, influencers_7d=2,
    video_count=66, video_count_7d=2, views_7d=4, units_sold=160,
    commission_pct=10.0, min_price=501.0,
)
MAQUILLAJE = _p(  # el ganador real del primer escaneo: 23 creadores, 3 activos
    product_id="maq", name="Set maquillaje brillo labios", ad_videos_fresh=1,
    newest_ad_video_days=1.1, influencer_count=23, influencers_7d=3,
    video_count=40, video_count_7d=3, views_7d=831, units_sold=2489,
    commission_pct=12.0, min_price=10.0,
)
PERFUME = _p(  # 488 creadores, 1144 vídeos → saturado pese a 13.647 ventas
    product_id="perfume", name="Set 2 botellas perfume", ad_videos_fresh=1,
    newest_ad_video_days=1.1, influencer_count=488, influencers_7d=11,
    video_count=1144, video_count_7d=16, views_7d=132_400, units_sold=13_647,
    commission_pct=13.0, min_price=15.0,
)
ROBOT = _p(  # 65 creadores pero 27 activos y 77 vídeos/semana → pelea viva
    product_id="robot", name="EVERCROSS robot", ad_videos_fresh=1,
    newest_ad_video_days=1.1, influencer_count=65, influencers_7d=27,
    video_count=282, video_count_7d=77, views_7d=50_000, units_sold=1,
    commission_pct=0.0, min_price=164.0,
)


def test_pocos_creadores_gana_a_muchas_ventas() -> None:
    """La tesis del operador: repartir el pastel entre menos gente."""
    g = score_fresh_ad_product(GEOMAR)
    p = score_fresh_ad_product(PERFUME)
    assert g.total > p.total, (
        f"GEOMAR (29 creadores) {g.total} debería ganar a PERFUME "
        f"(488 creadores) {p.total} pese a vender 85x menos"
    )
    assert g.low_competition > p.low_competition


def test_el_veto_de_saturacion_tumba_al_perfume() -> None:
    """Honestidad: en tracción por vídeo el perfume (8.275) GANA al GEOMAR (2).
    Sin veto por saturación puntuaría 54.0 vs 52.5 y lideraría el ranking pese
    a repartir el pastel entre 488 creadores. El multiplicador lo hunde."""
    assert views_per_video(PERFUME) > views_per_video(GEOMAR)   # es verdad
    assert score_fresh_ad_product(PERFUME).total < score_fresh_ad_product(GEOMAR).total


def test_muchas_views_repartidas_entre_muchos_videos_no_valen() -> None:
    """El robot tiene 50k views pero entre 77 vídeos → 649 por vídeo."""
    assert views_per_video(ROBOT) < 1_000
    assert views_per_video(ROBOT) < views_per_video(PERFUME)


def test_el_ganador_real_del_escaneo_lidera() -> None:
    """El 'Set de maquillaje' fue el #1 del primer escaneo real de ES.
    Debe seguir ganando a un saturado y a uno sin tracción."""
    m = score_fresh_ad_product(MAQUILLAJE).total
    assert m > score_fresh_ad_product(PERFUME).total
    assert m > score_fresh_ad_product(ROBOT).total


def test_traccion_cero_sin_videos_recientes() -> None:
    """Sin vídeos en 7d no se puede dividir → 0, no una división por cero."""
    assert views_per_video(_p(views_7d=5_000, video_count_7d=0)) == 0.0


def test_competencia_viva_pesa_mas_que_la_historica() -> None:
    """65 creadores históricos con 27 activos es PEOR que 29 con 2 activos."""
    assert score_fresh_ad_product(GEOMAR).low_competition > \
        score_fresh_ad_product(ROBOT).low_competition


def test_sin_inyeccion_no_puntua_ads() -> None:
    sin = _p(ad_videos_fresh=0, influencer_count=10, influencers_7d=1)
    con = _p(ad_videos_fresh=3, influencer_count=10, influencers_7d=1)
    assert score_fresh_ad_product(sin).ads_injection == 0.0
    assert score_fresh_ad_product(con).ads_injection == 100.0
    assert score_fresh_ad_product(con).total > score_fresh_ad_product(sin).total


def test_mas_inyeccion_mas_score() -> None:
    uno = _p(ad_videos_fresh=1, influencer_count=20, influencers_7d=2)
    tres = _p(ad_videos_fresh=3, influencer_count=20, influencers_7d=2)
    assert score_fresh_ad_product(tres).total > score_fresh_ad_product(uno).total


def test_filtro_descarta_comision_cero() -> None:
    """El robot tiene 0% → no ganas nada aunque esté inyectando."""
    ROBOT.score = score_fresh_ad_product(ROBOT)
    ok, why = FreshAdsFilters().passes(ROBOT)
    assert not ok and "comisión" in why


def test_filtro_descarta_saturados() -> None:
    PERFUME.score = score_fresh_ad_product(PERFUME)
    ok, why = FreshAdsFilters(max_influencers=250).passes(PERFUME)
    assert not ok and "488" in why


def test_geomar_pasa_los_filtros() -> None:
    GEOMAR.score = score_fresh_ad_product(GEOMAR)
    ok, why = FreshAdsFilters().passes(GEOMAR)
    assert ok, f"el candidato bueno no debería filtrarse: {why}"


def test_product_ids_parsea_el_string_json() -> None:
    """`video_products` llega como '[1729645572555316107]' (string)."""
    assert _product_ids({"video_products": '[1729645572555316107]'}) == ["1729645572555316107"]
    assert _product_ids({"video_products": '[1,2]'}) == ["1", "2"]
    assert _product_ids({"video_products": "[]"}) == []
    assert _product_ids({"video_products": None}) == []
    assert _product_ids({"video_products": "basura{"}) == []
    assert _product_ids({"video_products": [1, 2]}) == ["1", "2"]


# ── Comisión en EUROS, no en porcentaje ──────────────────────────────
POCO = _p(  # REAL: 5 creadores, 2/5 vídeos con AD... y **1 venta en total**
    product_id="poco", name="POCO F8 Ultra", ad_videos_fresh=1,
    influencer_count=5, influencers_7d=2, video_count=5, video_count_7d=2,
    views_7d=1688, units_sold=1, commission_pct=2.0, min_price=831.0,
)
RECORTADORA = _p(  # REAL: 3.304 ventas — demanda probada de sobra
    product_id="rec", name="Recortadora eléctrica", ad_videos_fresh=1,
    influencer_count=72, influencers_7d=13, video_count=282, video_count_7d=30,
    views_7d=19_830, units_sold=3304, commission_pct=8.0, min_price=8.6,
)


def test_sin_ventas_no_es_un_hueco_es_un_cementerio() -> None:
    """EL BUG que invirtió el ranking: el POCO tenía 1 venta en toda su vida y
    salía 95/100 (pocos creadores + 2/5 con etiqueta AD), mientras la
    recortadora de 3.304 ventas caía al 7º. 'Pocos creadores' tiene dos causas
    opuestas: nadie lo ha encontrado (oportunidad) o NADIE LO QUIERE (muerto).
    Sin ventas no se distinguen — el suelo de demanda es lo que las separa."""
    POCO.score = score_fresh_ad_product(POCO)
    ok, why = FreshAdsFilters().passes(POCO)
    assert not ok, f"un producto con 1 venta NO puede pasar (score {POCO.score.total})"
    assert "venta" in why


def test_la_demanda_puntua() -> None:
    """A igualdad de lo demás, el que vende más puntúa más."""
    poco_v = _p(units_sold=5, influencer_count=20, influencers_7d=2, ad_videos_fresh=1)
    mucho_v = _p(units_sold=500, influencer_count=20, influencers_7d=2, ad_videos_fresh=1)
    assert score_fresh_ad_product(mucho_v).demand > score_fresh_ad_product(poco_v).demand
    assert score_fresh_ad_product(mucho_v).total > score_fresh_ad_product(poco_v).total


def test_la_recortadora_pasa_el_suelo_de_demanda() -> None:
    RECORTADORA.score = score_fresh_ad_product(RECORTADORA)
    ok, why = FreshAdsFilters().passes(RECORTADORA)
    assert ok, f"3.304 ventas deberían pasar: {why}"


def test_comision_se_mide_en_euros_no_en_porcentaje() -> None:
    """El del 12% (maquillaje, 10€) paga 1,20€. El del 2% (POCO, 831€) paga
    16,62€. El del 10% (GEOMAR, 501€) paga 50€. Puntuar el % los ordena al
    revés de como se cobra."""
    assert round(commission_eur(MAQUILLAJE), 2) == 1.20
    assert round(commission_eur(POCO), 2) == 16.62
    assert round(commission_eur(GEOMAR), 2) == 50.10
    # ...y el score debe seguir al euro, no al %
    assert score_fresh_ad_product(GEOMAR).commission > score_fresh_ad_product(POCO).commission
    assert score_fresh_ad_product(POCO).commission > score_fresh_ad_product(MAQUILLAJE).commission


def test_comision_eur_sin_precio_no_revienta() -> None:
    assert commission_eur(_p(commission_pct=10.0, min_price=0.0, max_price=0.0)) == 0.0
    # sin min_price cae a max_price
    assert commission_eur(_p(commission_pct=10.0, min_price=0.0, max_price=50.0)) == 5.0


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ✅ {name}")
            except AssertionError as e:
                fails += 1
                print(f"  ❌ {name}: {e}")
    print(f"\n{'todos OK' if not fails else f'{fails} FALLOS'}")
    sys.exit(1 if fails else 0)
