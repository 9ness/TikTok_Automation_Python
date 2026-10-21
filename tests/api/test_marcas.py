"""Marcas de producto (físico, necesita contenido, Q4, clips reales) y la
lista de prioridades (`services/marcas.py`)."""

from __future__ import annotations

import pytest

from src.nicho_pov_bof.repos import product_repo
from src.nicho_pov_bof.services import marcas, mis_productos, reembolsables
from tests.api.test_reembolsables import AHORA, HOY, _FakeRedis

CARPETA = "Mis Productos 1"
KEY = f"folder:mis_productos:{CARPETA}"


@pytest.fixture
def fake(monkeypatch):
    r = _FakeRedis()
    monkeypatch.setattr(product_repo, "get_nicho_pov_bof_redis", lambda: r)
    monkeypatch.setattr(reembolsables, "hoy", lambda: HOY)
    monkeypatch.setattr(reembolsables, "_ahora", lambda: AHORA)
    monkeypatch.setattr(marcas, "_ahora", lambda: AHORA)
    monkeypatch.setattr(reembolsables, "_existe", lambda folder, producto, source="": producto != "99")
    monkeypatch.setattr(
        mis_productos, "carpetas",
        lambda source="mis_productos": [CARPETA] if source == "mis_productos" else [],
    )
    r.data[KEY] = {"productos": {str(i): {"titulo": f"P{i}"} for i in range(1, 7)}}
    return r


def test_marcar_varias_y_no_tocar_lo_demas(fake):
    item = marcas.marcar(CARPETA, "1", source="mis_productos", fisico=True, contenido_videos=3,
                         clips_reales=" Drive/clips/bici ")
    m = item["marcas"]
    assert m["fisico"] and not m["q4"] and m["clips_reales"] == "Drive/clips/bici"
    assert m["contenido"]["videos"] == 3 and m["contenido"]["pendientes"] == 3
    item = marcas.marcar(CARPETA, "1", source="mis_productos", q4=True)
    assert item["marcas"]["fisico"] and item["marcas"]["q4"]
    assert item["marcas"]["contenido"]["videos"] == 3
    assert fake.data[KEY]["productos"]["1"]["titulo"] == "P1"
    with pytest.raises(ValueError):
        marcas.marcar(CARPETA, "99", source="mis_productos", fisico=True)
    with pytest.raises(ValueError):
        marcas.marcar(CARPETA, "1", source="inventario_general", fisico=True)
    with pytest.raises(ValueError):
        marcas.marcar(CARPETA, "1", source="mis_productos")


def test_fisico_por_catalogo():
    assert marcas.info("productos_fisicos", {})["fisico"] is True
    assert marcas.info("mis_productos", {})["fisico"] is False


def test_subidos_descuentan_sin_duplicar(fake):
    marcas.marcar(CARPETA, "2", source="mis_productos", contenido_videos=2)
    c = marcas.registrar_subido("mis_productos", CARPETA, "2", "ness|pov|a", True)
    assert c["pendientes"] == 1
    c = marcas.registrar_subido("mis_productos", CARPETA, "2", "ness|pov|a", True)
    assert c["pendientes"] == 1  # el mismo vídeo no cuenta dos veces
    c = marcas.registrar_subido("mis_productos", CARPETA, "2", "ness|largo|b", True)
    assert c["hecho"] and c["pendientes"] == 0
    c = marcas.registrar_subido("mis_productos", CARPETA, "2", "ness|largo|b", False)
    assert c["pendientes"] == 1
    # Subir más vídeos cambia lo que pide sin perder lo ya subido.
    item = marcas.marcar(CARPETA, "2", source="mis_productos", contenido_videos=3)
    assert item["marcas"]["contenido"]["subidos"] == 1
    # Sin la marca no hace nada.
    assert marcas.registrar_subido("mis_productos", CARPETA, "3", "x", True) is None
    item = marcas.marcar(CARPETA, "2", source="mis_productos", contenido=False)
    assert item["marcas"]["contenido"] is None


def test_orden_de_prioridades(fake):
    marcas.marcar(CARPETA, "1", source="mis_productos", contenido_videos=3)
    marcas.marcar(CARPETA, "2", source="mis_productos", contenido_videos=1)
    reembolsables.marcar(CARPETA, "3", 2, 45, importe=0.3)
    reembolsables.marcar(CARPETA, "4", 2, 10, importe=12)
    marcas.marcar(CARPETA, "5", source="mis_productos", q4=True)
    # Uno con el contenido ya hecho baja al resto.
    marcas.marcar(CARPETA, "6", source="mis_productos", contenido_videos=1)
    marcas.registrar_subido("mis_productos", CARPETA, "6", "v", True)
    r = marcas.prioridades(incluir_resto=True)
    assert [i["producto"] for i in r["items"]][:5] == ["2", "1", "4", "3", "5"]
    assert r["contenido"] == 2 and r["reembolso"] == 2
    assert r["items"][0]["grupo"] == "contenido" and "faltan 1 de 1" in r["items"][0]["motivo"]
    corto = marcas.prioridades()
    assert corto["total"] == 4 and corto["items"][-1]["producto"] == "3"


def test_reembolsables_por_dinero(fake):
    reembolsables.marcar(CARPETA, "3", 2, 5, importe=0.3)
    reembolsables.marcar(CARPETA, "4", 2, 40, importe="12,5")
    items = reembolsables.listar()["items"]
    assert [i["producto"] for i in items] == ["4", "3"]
    assert items[0]["reembolso"]["importe"] == 12.5
    item = reembolsables.actualizar(CARPETA, "3", importe=20)
    assert item["reembolso"]["importe"] == 20
    with pytest.raises(ValueError):
        reembolsables.marcar(CARPETA, "3", 2, 5, importe=-1)


def test_mis_tandas_descuenta(fake, monkeypatch):
    from src.mis_tandas import servicio

    marcas.marcar(CARPETA, "2", source="mis_productos", contenido_videos=1)
    servicio._contenido("mis_productos", CARPETA, "2", "ness", "pov|mis_productos|x|2", True)
    assert fake.data[KEY]["productos"]["2"]["contenido"]["subidos"] == ["ness|pov|mis_productos|x|2"]


def test_endpoints(app_client, fake):
    base = "/api/v1/nicho-pov-bof"
    r = app_client.post(f"{base}/marcas", json={
        "folder": CARPETA, "producto": "2", "fisico": True, "contenido_videos": 2,
    })
    assert r.status_code == 200, r.text
    assert r.json()["marcas"]["contenido"]["pendientes"] == 2
    r = app_client.post(f"{base}/marcas", json={"folder": CARPETA, "producto": "2"})
    assert r.status_code == 400
    r = app_client.post(f"{base}/reembolsable/marcar", json={
        "folder": CARPETA, "producto": "3", "ventas_objetivo": 1, "dias": 9, "importe": 4.5,
    })
    assert r.json()["reembolso"]["importe"] == 4.5
    r = app_client.get(f"{base}/prioridades?source=mis_productos")
    assert r.status_code == 200, r.text
    assert [i["producto"] for i in r.json()["items"]] == ["2", "3"]
    r = app_client.get(f"{base}/prioridades?solo_fisicos=true")
    assert [i["producto"] for i in r.json()["items"]] == ["2"]
    r = app_client.get(f"{base}/prioridades?source=inventario_general")
    assert r.status_code == 400
