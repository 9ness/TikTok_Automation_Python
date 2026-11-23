"""Tareas de «Campañas de creadores» en Mis tandas."""

from __future__ import annotations

import time

import pytest

from src.mis_tandas import tareas
from tests.mis_tandas.test_servicio import FakeRedis

PID = "1729384756102938475"


@pytest.fixture()
def r(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(tareas, "_redis", lambda: r)
    return r


def _fila(id_, pid="", ref=("mis_productos", "c1", "3"), subido=False, at=0.0, sin_stock=False):
    return {"id": id_, "product_url": f"https://www.tiktok.com/view/product/{pid}" if pid else "",
            "source": ref[0], "carpeta": ref[1], "producto": ref[2],
            "uploaded": subido, "uploaded_at": at, "sin_stock": sin_stock}


def test_guardar_acepta_enlace_o_id_y_anade(r):
    t = tareas.guardar("ness", {"nombre": "Envío rápido 100 €", "videos_requeridos": 3,
                                "productos": [f"https://shop.tiktok.com/view/product/{PID}?x=1"]})
    assert t["id"] == "envio_rapido_100" and t["productos"] == [PID]
    t = tareas.guardar("ness", {"id": t["id"], "productos": ["1111111111111111111"], "anadir": True})
    assert t["productos"] == [PID, "1111111111111111111"] and t["videos_requeridos"] == 3
    with pytest.raises(tareas.ErrorTarea):
        tareas.guardar("ness", {"nombre": "x", "productos": ["no-es-un-id"]})


def test_casado_por_id_y_por_ref_y_progreso(r):
    t = tareas.guardar("ness", {"nombre": "Reto", "videos_requeridos": 2, "productos": [PID],
                                "refs": ["tareas_productos|c2|1"],
                                "fin": "2099-01-01T00:00"})
    antes = t["creada_at"] - 10
    filas = [
        _fila("a", PID, subido=True, at=time.time()),
        _fila("b", PID, subido=True, at=antes),            # subido antes de la tarea: no cuenta
        _fila("c", ref=("tareas_productos", "c2", "1")),   # por ref, pendiente
        _fila("d", "2222222222222222222"),                 # otra cosa
    ]
    for f in filas:
        f["tareas"] = tareas.de_fila(f, [t])
    assert [f["id"] for f in filas if f["tareas"]] == ["a", "b", "c"]
    (res,) = tareas.resumen([t], filas)
    assert res["subidos"] == 1 and res["pendientes"] == 1 and res["videos"] == 3 and res["faltan"] == 1
    assert res["productos_sin_video"] == [] and res["horas_restantes"] > 0


def test_vencida_desaparece_sola(r):
    t = tareas.guardar("ness", {"nombre": "Vieja", "fin": "2020-01-01T00:00"})
    tareas.guardar("ness", {"nombre": "Viva", "fin": "2099-01-01T00:00"})
    assert not tareas.activa(t) and tareas.resumen([t], []) == []
    # al leer se borra de Redis: no se acumulan tareas pasadas
    assert [x["id"] for x in tareas.listar("ness")] == ["viva"]
    assert [x["id"] for x in r.get_json(tareas.TAREAS_KEY.format(usuario="ness"))["tareas"]] == ["viva"]


def test_hashtag_exclusivo_y_duracion_minima(r, monkeypatch):
    """23/11: «Publica 5 vídeos» pide #7694275802761789461 en el caption y ≥ 20 s."""
    from src.mis_tandas import servicio

    t = tareas.guardar("ness", {"nombre": "Publica 5", "productos": [PID],
                                "hashtags": ["7694275802761789461", "#7694275802761789461"], "duracion_min": 20})
    assert t["hashtags"] == ["#7694275802761789461"] and t["duracion_min"] == 20
    otra = tareas.guardar("ness", {"nombre": "Otra", "productos": [PID], "hashtags": "#a, b", "duracion_min": 10})
    req = tareas.requisitos([t["id"], otra["id"]], [t, otra])
    assert req == {"hashtags": ["#7694275802761789461", "#a", "#b"], "duracion_min": 20}
    assert tareas.requisitos([], [t]) == {"hashtags": [], "duracion_min": 0}
    (res,) = tareas.resumen([t], [])
    assert res["hashtags"] == ["#7694275802761789461"] and res["duracion_min"] == 20

    verde = {"color": "verde", "motivo": "ok", "listo_at": 1}
    assert servicio._por_duracion(verde, 0) is verde
    assert servicio._por_duracion({**verde, "duracion": 24.0}, 20)["color"] == "verde"
    corto = servicio._por_duracion({**verde, "duracion": 16.1}, 20)
    assert corto["color"] == "ambar" and "16.1 s" in corto["motivo"]
    assert servicio._por_duracion(verde, 20)["color"] == "ambar"  # verde sin medir

    # Al poner verde se mide: corto → se guarda en ámbar.
    rs = FakeRedis()
    monkeypatch.setattr(servicio, "_redis", lambda: rs)
    monkeypatch.setattr(servicio, "_fila_de", lambda u, i: {"id": i, "video_listo_at": 5, "video_path": "/x.mp4"})
    monkeypatch.setattr(servicio, "_minimo_de_tareas", lambda u, f: 20)
    monkeypatch.setattr(servicio, "_duracion", lambda ruta: 16.0)
    s = servicio.poner_semaforo("ness", "pov|x", "verde", "bien")["semaforo"]
    assert s["color"] == "ambar" and s["duracion"] == 16.0 and "≥ 20 s" in s["motivo"]
    monkeypatch.setattr(servicio, "_duracion", lambda ruta: 23.9)
    s = servicio.poner_semaforo("ness", "pov|x", "verde", "bien")["semaforo"]
    assert s["color"] == "verde" and s["duracion"] == 23.9
