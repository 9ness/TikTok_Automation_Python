"""«Mis tandas»: orden fijo, mezcla con el multimodo, tandas y fecha."""

from __future__ import annotations

import datetime as dt

import pytest

from src.mis_tandas import fuentes, servicio


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict = {}

    def is_available(self) -> bool:
        return True

    def get_json(self, k):
        return self.data.get(k)

    def set_json(self, k, v):
        self.data[k] = v
        return True


def fila(id_, nicho="pov", uploaded=False, uploaded_at=0.0, orden_at=0.0, sin_stock=False):
    return fuentes._fila(id=id_, nicho=nicho, uploaded=uploaded, uploaded_at=uploaded_at,
                         orden_at=orden_at, sin_stock=sin_stock)


@pytest.fixture()
def redis(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(servicio, "_redis", lambda: r)
    servicio._cache.clear()
    return r


def test_partes_folder_respeta_espacios():
    assert fuentes._partes_folder("folder:aleatorios_1:27 Pront Flow ") == ("aleatorios_1", "27 Pront Flow ")


def test_ids_validos_y_basura():
    assert servicio._partes("pov|a|b|1")[0] == "pov"
    assert servicio._partes("largo|a|b|1|")[4] == ""
    assert servicio._partes("mm|mujer_web__Carpeta 7|3")[1] == "mujer_web__Carpeta 7"
    for malo in ("", "basura", "pov|a|b", "mm|a|b|c"):
        with pytest.raises(servicio.ErrorTanda):
            servicio._partes(malo)


def test_orden_subidos_delante_y_lo_nuevo_al_final(redis):
    pov = [fila("p1", orden_at=30), fila("p2", uploaded=True, uploaded_at=50, orden_at=10), fila("p3", orden_at=20)]
    primera = [f["id"] for f in servicio._ordenar("ana", pov, [])]
    assert primera == ["p2", "p3", "p1"]
    # Subir uno NO lo mueve; un vídeo nuevo entra al final aunque sea más viejo.
    pov[0]["uploaded"] = True
    pov.append(fila("p0", orden_at=1))
    assert [f["id"] for f in servicio._ordenar("ana", pov, [])] == ["p2", "p3", "p1", "p0"]


def test_multimodo_conserva_su_orden_interno(redis):
    mm = [fila("m_b", "mm", orden_at=40), fila("m_a", "mm", orden_at=5)]  # su orden NO es cronológico
    pov = [fila("p", orden_at=20)]
    ids = [f["id"] for f in servicio._ordenar("ana", pov, mm)]
    assert ids.index("m_b") < ids.index("m_a")


def test_tandas_fecha_y_cerradas(redis, monkeypatch):
    lista = [fila(f"v{i}", uploaded=i < 10, uploaded_at=1.0, orden_at=i) for i in range(25)]
    monkeypatch.setattr(servicio, "filas", lambda u, fresco=False: lista)
    monkeypatch.setattr(servicio, "_precalentar", lambda u, l: None)
    d = servicio.tandas("mauro")
    assert d["cerradas"] == 1 and d["abiertas"] == 2
    assert [t["numero"] for t in d["tandas"]] == [2, 3]
    hoy = dt.datetime.now(servicio._TZ).date()
    assert d["tandas"][0]["fecha"] == hoy.isoformat()
    assert d["tandas"][1]["fecha"] == (hoy + dt.timedelta(days=1)).isoformat()
    assert "video_path" not in d["tandas"][0]["items"][0]
    assert len(servicio.tandas("mauro", todas=True)["tandas"]) == 3


def test_sin_stock_cierra_la_tanda(redis, monkeypatch):
    lista = [fila(f"v{i}", uploaded=i < 8, uploaded_at=1.0, sin_stock=i >= 8) for i in range(10)]
    monkeypatch.setattr(servicio, "filas", lambda u, fresco=False: lista)
    monkeypatch.setattr(servicio, "_precalentar", lambda u, l: None)
    assert servicio.tandas("ana")["abiertas"] == 0
