"""Marca GMV Max (Black Friday 2026): por tienda, por id y por título."""

from __future__ import annotations

import pytest

from src.mis_tandas import fotos, gmv_max, servicio
from tests.mis_tandas.test_servicio import FakeRedis


def _f(i, titulo, tienda="Tienda Uno", url=""):
    return {"id": i, "titulo": titulo, "tienda": tienda, "product_url": url, "uploaded": False}


@pytest.fixture
def entorno(monkeypatch):
    r = FakeRedis()
    filas = {
        "a": _f("a", "Lámpara LED Navidad", url="https://shop.tiktok.com/view/product/1729384756123456789"),
        "b": _f("b", "Taza térmica", tienda="Otra Tienda"),
    }
    monkeypatch.setattr(servicio, "_redis", lambda: r)
    monkeypatch.setattr(servicio, "_fila_de", lambda u, i: filas[i])
    monkeypatch.setattr(servicio, "filas", lambda u, fresco=False: list(filas.values()))
    monkeypatch.setattr(fotos, "tandas", lambda u, todas=False: {"tandas": [{"items": [
        {"id": "c1", "titulo": "Taza térmica acero", "tienda": "Otra Tienda", "product_url": "", "subido": False}]}]})
    return filas


def test_id_producto():
    assert gmv_max.id_producto("https://x.com/view/product/1729384756123456789?u=1") == "1729384756123456789"
    assert gmv_max.id_producto("https://x.com/algo") == ""


def test_por_id_y_url(entorno):
    servicio.marcar_gmv_max("ana", id_="a", nota="social1")
    m = gmv_max.marcas()
    assert gmv_max.es_gmv_max(entorno["a"], m)
    # misma URL en otra cuenta con título distinto: casa por id de producto
    otro = _f("z", "Otro título", tienda="X", url="https://shop.tiktok.com/view/product/1729384756123456789")
    assert gmv_max.es_gmv_max(otro, m)
    assert not gmv_max.es_gmv_max(entorno["b"], m)
    servicio.marcar_gmv_max("ana", id_="a", si=False)
    assert not gmv_max.es_gmv_max(entorno["a"])


def test_por_tienda(entorno):
    servicio.marcar_gmv_max("ana", tienda="otra tienda")
    assert gmv_max.es_gmv_max(entorno["b"])
    assert not gmv_max.es_gmv_max(entorno["a"])


def test_por_producto_incluye_carrusel(entorno):
    r = servicio.marcar_gmv_max("ana", producto="taza termica")
    assert len(r["marcado"]) == 2
    assert gmv_max.es_gmv_max(entorno["b"])
    with pytest.raises(servicio.ErrorTanda):
        servicio.marcar_gmv_max("ana", producto="inexistente")
    with pytest.raises(servicio.ErrorTanda):
        servicio.marcar_gmv_max("ana")
    with pytest.raises(servicio.ErrorTanda):
        servicio.marcar_gmv_max("ana", id_="car|nada")
