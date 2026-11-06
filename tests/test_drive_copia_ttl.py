"""Lo que se sirve de la copia no se relista cada 5 minutos."""
import time

import pytest

from src.nicho_pov_bof import config
from src.nicho_pov_bof.services import drive_client as dc

COPIA = [{"id": "a", "name": "1.png", "desde_copia": True}]
NORMAL = [{"id": "b", "name": "1.png"}]


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    dc._CACHE.clear()
    dc._ULTIMO.clear()
    monkeypatch.setattr(dc, "_redis_cache_put", lambda *a, **k: None)
    refrescos = []
    monkeypatch.setattr(dc, "_refrescar_en_segundo_plano", lambda k, c: refrescos.append(k))
    yield refrescos
    dc._CACHE.clear()
    dc._ULTIMO.clear()


def _vigencia(key):
    return dc._CACHE[key][0] - time.monotonic()


def _con_redis(monkeypatch, payload, edad):
    monkeypatch.setattr(dc, "_redis_cache_get", lambda k: (payload, edad))


def test_ttl_segun_origen():
    assert dc._ttl_de("photos:s:f", COPIA) == dc._TTL_COPIA_S
    assert dc._ttl_de("backup-photos:s:f", NORMAL) == dc._TTL_COPIA_S
    assert dc._ttl_de("photos:s:f", NORMAL) == config.LISTING_TTL_S
    assert dc._ttl_de("photos:s:f", []) == config.LISTING_TTL_S
    assert dc._ttl_de("carpetas", {"desde_copia": True}) == config.LISTING_TTL_S


def test_copia_en_redis_no_refresca_antes_de_6h(monkeypatch, limpio):
    _con_redis(monkeypatch, COPIA, 3600)
    assert dc._listar_cacheado("photos:s:f", lambda: 1 / 0, refresh=False) == COPIA
    assert limpio == []
    # Memoria y Redis no suman plazos: quedan las 5 h que le faltaban.
    assert _vigencia("photos:s:f") == pytest.approx(dc._TTL_COPIA_S - 3600, abs=5)


def test_copia_vencida_se_sirve_y_refresca(monkeypatch, limpio):
    _con_redis(monkeypatch, COPIA, dc._TTL_COPIA_S + 1)
    assert dc._listar_cacheado("photos:s:f", lambda: 1 / 0, refresh=False) == COPIA
    assert limpio == ["photos:s:f"]
    assert _vigencia("photos:s:f") == pytest.approx(config.LISTING_TTL_S, abs=5)


def test_listado_normal_sigue_a_5_minutos(monkeypatch, limpio):
    _con_redis(monkeypatch, NORMAL, config.LISTING_TTL_S + 1)
    assert dc._listar_cacheado("photos:s:f", lambda: 1 / 0, refresh=False) == NORMAL
    assert limpio == ["photos:s:f"]
    assert _vigencia("photos:s:f") == pytest.approx(config.LISTING_TTL_S, abs=5)


def test_refresh_manual_ignora_las_6h(monkeypatch):
    _con_redis(monkeypatch, COPIA, 60)
    dc._listar_cacheado("photos:s:f", lambda: COPIA, refresh=False)
    assert dc._listar_cacheado("photos:s:f", lambda: NORMAL, refresh=True) == NORMAL
    assert _vigencia("photos:s:f") == pytest.approx(config.LISTING_TTL_S, abs=5)
