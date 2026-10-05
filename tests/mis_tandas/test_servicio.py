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


def fila(id_, nicho="pov", uploaded=False, uploaded_at=0.0, orden_at=0.0, sin_stock=False,
         titulo=None, carpeta="c"):
    return fuentes._fila(id=id_, nicho=nicho, uploaded=uploaded, uploaded_at=uploaded_at,
                         orden_at=orden_at, sin_stock=sin_stock, carpeta=carpeta,
                         titulo=id_ if titulo is None else titulo)


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


def test_ocultos_salen_y_el_siguiente_ocupa_su_hueco(redis, monkeypatch):
    lista = [fila(f"pov|src|c|{i}", orden_at=i) for i in range(12)]
    monkeypatch.setattr(servicio, "filas", lambda u, fresco=False: lista)
    monkeypatch.setattr(servicio, "_precalentar", lambda u, l: None)
    servicio.ocultar("ness", "pov|src|c|3")
    d = servicio.tandas("ness", ver_ocultos=True)
    ids = [x["id"] for x in d["tandas"][0]["items"]]
    assert "pov|src|c|3" not in ids and ids[-1] == "pov|src|c|10"
    assert d["ocultos"] == 1 and d["ocultos_items"][0]["id"] == "pov|src|c|3"
    servicio.ocultar("ness", "pov|src|c|3", False)
    assert servicio.tandas("ness")["ocultos"] == 0
    with pytest.raises(servicio.ErrorTanda):
        servicio.ocultar("ness", "pov|x|y|1")


def _sin_precalentar(monkeypatch, lista):
    monkeypatch.setattr(servicio, "filas", lambda u, fresco=False: lista)
    monkeypatch.setattr(servicio, "_precalentar", lambda u, l: None)


def test_sin_stock_sale_aparte_y_no_ocupa_sitio(redis, monkeypatch):
    lista = [fila(f"pov|s|c|{i}", sin_stock=i < 3, orden_at=i) for i in range(13)]
    _sin_precalentar(monkeypatch, lista)
    d = servicio.tandas("mauro")
    assert len(d["esperando_stock"]) == 3
    assert [len(t["items"]) for t in d["tandas"]] == [10]


def test_fecha_minima_espera_sin_bloquear(redis, monkeypatch):
    hoy = dt.datetime.now(servicio._TZ).date()
    lista = [fila(f"largo|s|Q4|{i}|", "largo", orden_at=i) for i in range(3)]
    lista += [fila(f"pov|s|c|{i}", orden_at=10 + i) for i in range(12)]
    _sin_precalentar(monkeypatch, lista)
    monkeypatch.setattr(servicio, "_desde", lambda f: hoy + dt.timedelta(days=5) if "Q4" in f["id"] else None)
    d = servicio.tandas("mauro")
    q4 = [t for t in d["tandas"] if any("Q4" in i["id"] for i in t["items"])]
    assert q4 and all(t["fecha"] >= (hoy + dt.timedelta(days=5)).isoformat() for t in q4)
    assert d["tandas"][0]["fecha"] == hoy.isoformat() and len(d["tandas"][0]["items"]) == 10


def test_mismo_producto_separado(redis, monkeypatch):
    from src.mis_tandas import config

    lista = [fila("largo|s|c|1|", "largo", titulo="Lámpara", orden_at=1),
             fila("largo|s|c|1|dolor", "largo", titulo="Lámpara", orden_at=2)]
    lista += [fila(f"pov|s|c|{i}", orden_at=10 + i) for i in range(30)]
    _sin_precalentar(monkeypatch, lista)
    d = servicio.tandas("mauro")
    fechas = [t["fecha"] for t in d["tandas"] for i in t["items"] if i["titulo"] == "Lámpara"]
    a, b = (dt.date.fromisoformat(x) for x in fechas)
    assert (b - a).days >= config.SEPARACION_MISMO_PRODUCTO


def test_aleatorios_se_intercalan_sin_tocar_las_primeras_tandas():
    from src.mis_tandas import config, servicio

    def f(i, up=False):
        return {"id": i, "uploaded": up}

    # 5 subidos + 40 pendientes del multimodo; 4 de Aleatorios nuevos.
    ids = [f"s{i}" for i in range(5)] + [f"p{i}" for i in range(40)]
    por_id = {i: f(i, up=i.startswith("s")) for i in ids}
    nuevos = ["a1", "a2", "a3", "a4"]
    salida = servicio._intercalar(ids, por_id, nuevos)
    assert sorted(salida) == sorted(ids + nuevos)
    saltar = config.ALEA_SIN_TOCAR * config.POR_TANDA
    # Nada nuevo dentro de las primeras tandas abiertas.
    primeros = [i for i in salida if not i.startswith("s")][:saltar]
    assert not any(i.startswith("a") for i in primeros)
    # Después, uno cada ALEA_CADA pendientes.
    pos = [salida.index(a) for a in nuevos]
    assert all(b - a == config.ALEA_CADA + 1 for a, b in zip(pos, pos[1:]))


def test_tanda_fijada_no_se_mueve_al_marcar(redis, monkeypatch):
    """Marcar sin stock o subido NO mete un vídeo de la tanda siguiente."""
    lista = [fila(f"pov|s|c|{i}", orden_at=i) for i in range(25)]
    _sin_precalentar(monkeypatch, lista)
    antes = servicio.tandas("ness")
    primera = [x["id"] for x in antes["tandas"][0]["items"]]
    segunda = [x["id"] for x in antes["tandas"][1]["items"]]
    lista[2]["sin_stock"] = True
    lista[5]["uploaded"], lista[5]["uploaded_at"] = True, 1.0
    despues = servicio.tandas("ness")
    assert [x["id"] for x in despues["tandas"][0]["items"]] == primera
    assert [x["id"] for x in despues["tandas"][1]["items"]] == segunda
    assert despues["tandas"][0]["sin_stock"] == 1 and despues["esperando_stock"] == []
    assert despues["abiertas"] == 3
    # Un vídeo nuevo va detrás de las fijas, no dentro.
    lista.append(fila("pov|s|c|99", orden_at=99))
    otra = servicio.tandas("ness")
    assert "pov|s|c|99" not in primera + [x["id"] for x in otra["tandas"][1]["items"]]


def test_completar_cierra_sin_marcar_subido(redis, monkeypatch):
    lista = [fila(f"pov|s|c|{i}", orden_at=i) for i in range(20)]
    _sin_precalentar(monkeypatch, lista)
    d = servicio.tandas("ness")
    ids = [x["id"] for x in d["tandas"][0]["items"]]
    lista[0]["uploaded"], lista[0]["uploaded_at"] = True, 1.0
    r = servicio.completar("ness", ids)
    assert r["sin_subir"] == 9
    assert not any(f["uploaded"] for f in lista[1:])  # nada marcado
    d2 = servicio.tandas("ness")
    assert d2["cerradas"] == 1 and d2["tandas"][0]["items"][0]["id"] == "pov|s|c|10"
    todas = servicio.tandas("ness", todas=True)["tandas"]
    assert [x["id"] for x in todas[0]["items"]] == ids  # lo no subido sigue en su tanda


def test_toda_subida_sigue_a_la_vista_hasta_completarla(redis, monkeypatch):
    lista = [fila(f"pov|s|c|{i}", orden_at=i) for i in range(10)]
    _sin_precalentar(monkeypatch, lista)
    servicio.tandas("ness")
    for f in lista:
        f["uploaded"], f["uploaded_at"] = True, 1.0
    d = servicio.tandas("ness")
    assert d["abiertas"] == 1 and len(d["tandas"][0]["items"]) == 10
    servicio.completar("ness", [f["id"] for f in lista])
    assert servicio.tandas("ness")["abiertas"] == 0


def test_rehecho_pasa_a_una_tanda_nueva(redis, monkeypatch):
    lista = [fila(f"pov|s|c|{i}", orden_at=i) for i in range(15)]
    for f in lista:
        f["video_listo_at"] = 100.0
    _sin_precalentar(monkeypatch, lista)
    servicio.tandas("ness")
    lista[4]["rehacer"] = True  # marcado: sigue en su tanda
    d = servicio.tandas("ness")
    assert "pov|s|c|4" in [x["id"] for x in d["tandas"][0]["items"]]
    lista[4]["rehacer"], lista[4]["video_listo_at"] = False, 500.0  # rehecho
    d = servicio.tandas("ness")
    assert "pov|s|c|4" not in [x["id"] for x in d["tandas"][0]["items"]]
    assert len(d["tandas"][0]["items"]) == 9
    assert "pov|s|c|4" in [x["id"] for t in d["tandas"][1:] for x in t["items"]]
