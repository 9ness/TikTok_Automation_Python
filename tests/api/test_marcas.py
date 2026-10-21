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


def test_formato_de_clasifica():
    assert marcas.formato_de("pov", "") == "ia"
    assert marcas.formato_de("mm", "x") == "ia"
    assert marcas.formato_de("alea", "x") == "ia"
    assert marcas.formato_de("largo", "dolor") == "ia"
    assert marcas.formato_de("largo", "viral") == "viral"
    assert marcas.formato_de("rv", "con_ia") == "viral"
    assert marcas.formato_de("rv", "sin_ia") == "fisico"
    assert marcas.formato_de("rv", "") is None


def test_formatos_cuentan_idempotente_y_sin_contenido(fake):
    marcas.registrar_subido("mis_productos", CARPETA, "3", "ness|a", True, formato="ia")
    marcas.registrar_subido("mis_productos", CARPETA, "3", "ness|a", True, formato="ia")
    marcas.registrar_subido("mis_productos", CARPETA, "3", "ness|b", True, formato="viral")
    f = marcas.info("mis_productos", fake.data[KEY]["productos"]["3"])["formatos"]
    assert f["ia"] == {"subidos": 1, "objetivo": 5, "hecho": False}
    assert f["viral"] == {"subidos": 1, "objetivo": 1, "hecho": True}
    assert f["fisico"] == {"subidos": 0, "objetivo": 0, "hecho": False}
    marcas.registrar_subido("mis_productos", CARPETA, "3", "ness|a", False, formato="ia")
    f = marcas.info("mis_productos", fake.data[KEY]["productos"]["3"])["formatos"]
    assert f["ia"]["subidos"] == 0
    assert "contenido" not in fake.data[KEY]["productos"]["3"]


def test_formato_y_contenido_a_la_vez(fake):
    marcas.marcar(CARPETA, "4", source="mis_productos", contenido_videos=2)
    c = marcas.registrar_subido("mis_productos", CARPETA, "4", "ness|a", True, formato="ia")
    assert c["pendientes"] == 1
    prod = fake.data[KEY]["productos"]["4"]
    assert prod["formatos"]["ia"] == ["ness|a"]


def test_objetivos_editables(fake):
    item = marcas.marcar(CARPETA, "5", source="mis_productos", objetivo_ia=2, objetivo_fisico=3)
    f = item["marcas"]["formatos"]
    assert f["ia"]["objetivo"] == 2 and f["fisico"]["objetivo"] == 3 and f["viral"]["objetivo"] == 1
    marcas.registrar_subido("mis_productos", CARPETA, "5", "ness|a", True, formato="ia")
    marcas.registrar_subido("mis_productos", CARPETA, "5", "ness|b", True, formato="ia")
    f = marcas.info("mis_productos", fake.data[KEY]["productos"]["5"])["formatos"]
    assert f["ia"]["hecho"] is True
    with pytest.raises(ValueError):
        marcas.marcar(CARPETA, "5", source="mis_productos", objetivo_ia=21)


def test_rv_atada_cuenta_en_su_formato(fake, monkeypatch):
    from src.mis_tandas import servicio
    from src.replicar_viral import video as rv_video

    assert rv_video.catalogo_ref() is None
    with pytest.raises(Exception):
        rv_video.catalogo_ref("mis_productos", CARPETA, "")
    with pytest.raises(Exception):
        rv_video.catalogo_ref("inventario_general", CARPETA, "3")
    ref = rv_video.catalogo_ref("mis_productos", CARPETA, "3")
    doc = {"id": "abc123abc123", "modo": "sin_ia", "catalogo_ref": ref}
    monkeypatch.setattr(rv_video, "ver", lambda u, i: doc)
    assert servicio._ref_rv("ness", "abc123abc123") == ("mis_productos", CARPETA, "3", "sin_ia")
    r = servicio._ref_rv("ness", "abc123abc123")
    servicio._contenido(r[0], r[1], r[2], "ness", "rv|abc123abc123", True, "rv", r[3])
    f = marcas.info("mis_productos", fake.data[KEY]["productos"]["3"])["formatos"]
    assert f["fisico"]["subidos"] == 1
