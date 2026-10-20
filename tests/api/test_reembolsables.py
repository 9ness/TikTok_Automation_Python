"""Muestras reembolsables de «Muestras productos» y «Productos físicos»
(`services/reembolsables.py`)."""

from __future__ import annotations

from datetime import date

import pytest

from src.nicho_pov_bof import config
from src.nicho_pov_bof.repos import product_repo
from src.nicho_pov_bof.services import reembolsables

HOY = date(2026, 10, 20)
AHORA = 1_800_000_000.0
DIA = 86400


class _FakeRedis:
    def __init__(self):
        self.data: dict = {}

    def is_available(self):
        return True

    def get_json(self, key):
        return self.data.get(key)

    def set_json(self, key, value, **kw):
        import copy

        self.data[key] = copy.deepcopy(value)
        return True

    def mget_json(self, keys):
        return [self.data.get(k) for k in keys]

    def set_nx(self, key, value, ttl_s=0):
        if key in self.data:
            return False
        self.data[key] = value
        return True

    def delete(self, key):
        self.data.pop(key, None)
        return True


@pytest.fixture
def fake(monkeypatch):
    r = _FakeRedis()
    monkeypatch.setattr(product_repo, "get_nicho_pov_bof_redis", lambda: r)
    monkeypatch.setattr(reembolsables, "hoy", lambda: HOY)
    monkeypatch.setattr(reembolsables, "_ahora", lambda: AHORA)
    monkeypatch.setattr(
        reembolsables, "_existe", lambda folder, producto, source="": producto != "99",
    )
    # Para que tenga título en el listado.
    r.data["folder:mis_productos:Mis Productos 1"] = {
        "productos": {"1": {"titulo": "Lámpara"}, "2": {"titulo": "Taza"}, "3": {}},
    }
    return r


def test_marcar_guarda_fecha_y_derivados(fake):
    item = reembolsables.marcar("Mis Productos 1", "1", 3, 45, 1, " ojo ")
    r = item["reembolso"]
    assert item["titulo"] == "Lámpara"
    assert r["fecha_limite"] == "2026-12-04"
    assert r["dias_restantes"] == 45
    assert r["ventas"] == 1 and r["ventas_objetivo"] == 3
    assert r["estado"] == "en_curso" and r["toca_revisar"] is False
    assert r["notas"] == "ojo"
    guardado = fake.data["folder:mis_productos:Mis Productos 1"]["productos"]["1"]
    assert guardado["titulo"] == "Lámpara"  # no pisa lo demás
    assert "dias_restantes" not in guardado["reembolso"]  # los derivados no se guardan


def test_derivados_estado_y_revisar():
    base = {"activo": True, "ventas_objetivo": 2, "ventas": 0, "revisado_at": AHORA}
    assert reembolsables.info(None) is None
    assert reembolsables.info({**base, "activo": False}) is None
    # Cumplido aunque la fecha haya pasado.
    r = reembolsables.info({**base, "ventas": 2, "fecha_limite": "2000-01-01"}, ahora=AHORA)
    assert r["estado"] == "cumplido" and not r["toca_revisar"]
    r = reembolsables.info({**base, "fecha_limite": "2000-01-01"}, ahora=AHORA)
    assert r["estado"] == "vencido" and r["dias_restantes"] < 0 and not r["toca_revisar"]
    lejos = "2999-01-01"
    r = reembolsables.info({**base, "fecha_limite": lejos}, ahora=AHORA + DIA)
    assert r["estado"] == "en_curso" and not r["toca_revisar"]
    r = reembolsables.info(
        {**base, "fecha_limite": lejos}, ahora=AHORA + config.REVISAR_CADA_DIAS * DIA,
    )
    assert r["toca_revisar"]


def test_actualizar_ventas_dias_y_revisado(fake, monkeypatch):
    reembolsables.marcar("Mis Productos 1", "1", 3, 45)
    monkeypatch.setattr(reembolsables, "_ahora", lambda: AHORA + 5 * DIA)
    r = reembolsables.listar(["Mis Productos 1"])
    assert r["toca_revisar"] == 1
    item = reembolsables.actualizar("Mis Productos 1", "1", sumar_ventas=1)
    assert item["reembolso"]["ventas"] == 1
    assert item["reembolso"]["revisado_at"] == AHORA + 5 * DIA
    assert item["reembolso"]["toca_revisar"] is False
    item = reembolsables.actualizar("Mis Productos 1", "1", ventas=3, dias=10)
    assert item["reembolso"]["estado"] == "cumplido"
    assert item["reembolso"]["fecha_limite"] == "2026-10-30"
    item = reembolsables.actualizar("Mis Productos 1", "1", ventas_objetivo=5, notas="x")
    assert item["reembolso"]["estado"] == "en_curso"
    assert item["reembolso"]["notas"] == "x"


def test_desmarcar_y_listado(fake):
    reembolsables.marcar("Mis Productos 1", "1", 3, 45)
    reembolsables.marcar("Mis Productos 1", "2", 1, 10)
    item = reembolsables.desmarcar("Mis Productos 1", "1")
    assert item["reembolso"] is None
    guardado = fake.data["folder:mis_productos:Mis Productos 1"]["productos"]["1"]
    assert guardado["reembolso"]["activo"] is False
    r = reembolsables.listar(["Mis Productos 1"])
    assert [i["producto"] for i in r["items"]] == ["2"]
    # Desmarcar uno que no lo es no rompe.
    assert reembolsables.desmarcar("Mis Productos 1", "3")["reembolso"] is None


def test_orden_revisar_primero_luego_dias(fake, monkeypatch):
    fake.data["folder:mis_productos:Mis Productos 2"] = {"productos": {
        "1": {"reembolso": {"activo": True, "ventas_objetivo": 2, "ventas": 0,
                            "fecha_limite": "2026-12-30", "revisado_at": AHORA}},
        "2": {"reembolso": {"activo": True, "ventas_objetivo": 2, "ventas": 0,
                            "fecha_limite": "2026-11-01", "revisado_at": AHORA}},
        "3": {"reembolso": {"activo": True, "ventas_objetivo": 2, "ventas": 0,
                            "fecha_limite": "2027-03-01", "revisado_at": 0}},
        "4": {"reembolso": {"activo": True, "ventas_objetivo": 1, "ventas": 1,
                            "fecha_limite": "2026-10-21", "revisado_at": 0}},
        "5": {"reembolso": {"activo": True, "ventas_objetivo": 2, "ventas": 0,
                            "fecha_limite": "2026-10-01", "revisado_at": 0}},
        "6": {"titulo": "normal"},
    }}
    r = reembolsables.listar(["Mis Productos 1", "Mis Productos 2"])
    assert [i["producto"] for i in r["items"]] == ["3", "2", "1", "5", "4"]
    assert (r["total"], r["en_curso"], r["cumplidos"], r["vencidos"], r["toca_revisar"]) == (
        5, 3, 1, 1, 1,
    )


@pytest.mark.parametrize("kw", [
    {"ventas_objetivo": 0, "dias": 10},
    {"ventas_objetivo": 2, "dias": -1},
    {"ventas_objetivo": "dos", "dias": 10},
    {"ventas_objetivo": 2, "dias": 10, "ventas": -1},
])
def test_validaciones(fake, kw):
    with pytest.raises(ValueError):
        reembolsables.marcar("Mis Productos 1", "1", **kw)


def test_producto_que_no_existe(fake):
    with pytest.raises(ValueError, match="No hay producto"):
        reembolsables.marcar("Mis Productos 1", "99", 1, 10)


def test_actualizar_sin_marcar(fake):
    with pytest.raises(ValueError, match="no está marcado"):
        reembolsables.actualizar("Mis Productos 1", "2", ventas=1)


def test_productos_fisicos(fake, monkeypatch):
    from src.nicho_pov_bof.services import mis_productos

    monkeypatch.setattr(mis_productos, "carpetas", lambda source="": {
        "mis_productos": ["Mis Productos 1"],
        "productos_fisicos": ["Productos Fisicos 1"],
    }.get(source, []))
    fake.data["folder:productos_fisicos:Productos Fisicos 1"] = {
        "productos": {"1": {"titulo": "Freidora"}},
    }
    item = reembolsables.marcar(
        "Productos Fisicos 1", "1", 2, 30, source="productos_fisicos",
    )
    assert item["source"] == "productos_fisicos"
    assert item["catalogo"] == config.SOURCES["productos_fisicos"]["label"]
    guardado = fake.data["folder:productos_fisicos:Productos Fisicos 1"]["productos"]["1"]
    assert guardado["reembolso"]["ventas_objetivo"] == 2
    # No toca el de Muestras con el mismo número.
    assert "reembolso" not in fake.data["folder:mis_productos:Mis Productos 1"]["productos"]["1"]
    item = reembolsables.actualizar(
        "Productos Fisicos 1", "1", sumar_ventas=1, source="productos_fisicos",
    )
    assert item["reembolso"]["ventas"] == 1
    reembolsables.marcar("Mis Productos 1", "2", 1, 10)
    # Listado con varias fuentes: cada item con la suya.
    r = reembolsables.listar(fuentes=["mis_productos", "productos_fisicos"])
    assert {(i["source"], i["producto"]) for i in r["items"]} == {
        ("mis_productos", "2"), ("productos_fisicos", "1"),
    }
    r = reembolsables.listar(["Productos Fisicos 1"], source="productos_fisicos")
    assert [i["producto"] for i in r["items"]] == ["1"]
    item = reembolsables.desmarcar(
        "Productos Fisicos 1", "1", source="productos_fisicos",
    )
    assert item["reembolso"] is None
    # La de Ana también vale.
    item = reembolsables.marcar(
        "Productos Fisicos 1", "3", 1, 5, source="productos_fisicos_ana",
    )
    assert item["source"] == "productos_fisicos_ana"


@pytest.mark.parametrize("source", ["tareas_productos", "aleatorios_1", "temporada_q4"])
def test_rechaza_otra_fuente(fake, source):
    with pytest.raises(ValueError, match="Muestras productos"):
        reembolsables.marcar("Mis Productos 1", "1", 1, 10, source=source)
    with pytest.raises(ValueError):
        reembolsables.actualizar("Mis Productos 1", "1", ventas=1, source=source)
    with pytest.raises(ValueError):
        reembolsables.desmarcar("Mis Productos 1", "1", source=source)



def test_endpoints(app_client, fake, monkeypatch):
    from src.nicho_pov_bof.services import mis_productos

    monkeypatch.setattr(mis_productos, "carpetas", lambda source="": ["Mis Productos 1"])
    base = "/api/v1/nicho-pov-bof"
    r = app_client.post(f"{base}/reembolsable/marcar", json={
        "folder": "Mis Productos 1", "producto": "2", "ventas_objetivo": 2, "dias": 30,
    })
    assert r.status_code == 200, r.text
    assert r.json()["reembolso"]["ventas_objetivo"] == 2
    r = app_client.post(f"{base}/reembolsable/actualizar", json={
        "folder": "Mis Productos 1", "producto": "2", "sumar_ventas": 1,
    })
    assert r.json()["reembolso"]["ventas"] == 1
    r = app_client.post(f"{base}/reembolsable/marcar", json={
        "source": "tareas_productos", "folder": "Mis Productos 1", "producto": "2",
        "ventas_objetivo": 2, "dias": 30,
    })
    assert r.status_code == 400
    r = app_client.post(f"{base}/reembolsable/marcar", json={
        "source": "productos_fisicos", "folder": "Mis Productos 1", "producto": "1",
        "ventas_objetivo": 1, "dias": 5,
    })
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "productos_fisicos" and r.json()["catalogo"]
    r = app_client.post(f"{base}/reembolsable/actualizar", json={
        "source": "inventario_general", "folder": "Mis Productos 1", "producto": "1",
    })
    assert r.status_code == 400
    r = app_client.get(f"{base}/reembolsables")
    assert r.status_code == 200 and r.json()["total"] == 2
    assert {i["source"] for i in r.json()["items"]} == {"mis_productos", "productos_fisicos"}
    r = app_client.get(f"{base}/reembolsables?source=productos_fisicos")
    assert r.status_code == 200 and r.json()["total"] == 1
    r = app_client.get(f"{base}/reembolsables?source=tareas_productos")
    assert r.status_code == 400
    r = app_client.post(f"{base}/reembolsable/desmarcar", json={
        "folder": "Mis Productos 1", "producto": "2",
    })
    assert r.json()["reembolso"] is None
