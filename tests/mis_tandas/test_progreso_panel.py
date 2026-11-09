"""Progreso de la tarea «Subir vídeos» del panel al marcar subido en Mis tandas."""
from __future__ import annotations

import datetime as dt

from src.mis_tandas import progreso_panel as pp


def _env(monkeypatch):
    monkeypatch.setenv("PANEL_URL", "https://panel.test")
    monkeypatch.setenv("PANEL_TOKEN", "x")


def test_sin_config_no_hace_nada(monkeypatch):
    monkeypatch.delenv("PANEL_URL", raising=False)
    llamadas = []
    monkeypatch.setattr(pp, "_peticion", lambda *a, **k: llamadas.append(a))
    assert pp.actualizar("ness") is None and llamadas == []


def test_usuario_sin_plantilla(monkeypatch):
    _env(monkeypatch)
    llamadas = []
    monkeypatch.setattr(pp, "_peticion", lambda *a, **k: llamadas.append(a))
    assert pp.actualizar("nadie") is None and llamadas == []


def test_pone_total_de_hoy(monkeypatch):
    _env(monkeypatch)
    llamadas = []

    def pet(metodo, ruta, cuerpo=None):
        llamadas.append((metodo, ruta, cuerpo))
        if metodo == "GET":
            return [{"id": 9, "plantilla": 1}, {"id": 7, "plantilla": pp.PLANTILLA_VIDEOS["ness"], "progreso": 2}]
        return {"id": 7, "progreso": cuerpo["progreso"]}

    monkeypatch.setattr(pp, "_peticion", pet)
    monkeypatch.setattr(pp, "subidos_hoy", lambda u: 5)
    assert pp.actualizar("ness") == {"id": 7, "progreso": 5}
    assert llamadas[-1] == ("PATCH", "/api/tareas/7", {"progreso": 5})


def test_no_repite_si_ya_esta(monkeypatch):
    _env(monkeypatch)
    llamadas = []

    def pet(metodo, ruta, cuerpo=None):
        llamadas.append(metodo)
        return [{"id": 7, "plantilla": pp.PLANTILLA_VIDEOS["ness"], "progreso": 3}]

    monkeypatch.setattr(pp, "_peticion", pet)
    monkeypatch.setattr(pp, "subidos_hoy", lambda u: 3)
    pp.actualizar("ness")
    assert llamadas == ["GET"]


def test_subidos_hoy_cuenta_solo_hoy(monkeypatch):
    from src.mis_tandas import servicio

    ahora = dt.datetime.now(pp._TZ)
    ayer = ahora - dt.timedelta(days=1)
    filas = [
        {"uploaded": True, "uploaded_at": ahora.timestamp()},
        {"uploaded": True, "uploaded_at": ahora.timestamp()},
        {"uploaded": True, "uploaded_at": ayer.timestamp()},
        {"uploaded": False, "uploaded_at": ahora.timestamp()},
        {"uploaded": True, "uploaded_at": None},
    ]
    monkeypatch.setattr(servicio, "filas", lambda u: filas)
    assert pp.subidos_hoy("ness") == 2


def test_avisar_agrupa_y_no_tumba(monkeypatch):
    monkeypatch.setattr(pp, "_ESPERA", 0.05)
    hechas = []

    def falla(u):
        hechas.append(u)
        raise RuntimeError("panel caído")

    monkeypatch.setattr(pp, "actualizar", falla)
    for _ in range(5):
        pp.avisar("ness")
    pp.avisar("nadie")
    import time
    time.sleep(0.4)
    assert hechas == ["ness"]


def _marcar_pov(monkeypatch, **kw):
    from src.mis_tandas import fuentes, servicio
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    id_ = fuentes.SEP.join(["pov", "src", "carpeta", "prod"])
    monkeypatch.setattr(servicio, "_fila_de", lambda u, i: {"id": i})
    monkeypatch.setattr(servicio, "_cuota", lambda *a, **k: None)
    monkeypatch.setattr(servicio, "_contenido", lambda *a, **k: None)
    monkeypatch.setattr(pov_repo, "update_product", lambda *a, **k: {"uploaded_at": 123.0})
    monkeypatch.setattr(pov_repo, "save_extracted_texts", lambda *a, **k: None)
    avisos = []
    monkeypatch.setattr(pp, "avisar", avisos.append)
    out = servicio.marcar("ness", id_, **kw)
    return out, avisos


def test_marcar_subido_avisa_al_panel(monkeypatch):
    out, avisos = _marcar_pov(monkeypatch, uploaded=True)
    assert out["uploaded"] is True and out["uploaded_at"] == 123.0
    assert avisos == ["ness"]


def test_marcar_desmarcado_tambien_avisa(monkeypatch):
    _, avisos = _marcar_pov(monkeypatch, uploaded=False)
    assert avisos == ["ness"]


def test_marcar_sin_stock_no_avisa(monkeypatch):
    out, avisos = _marcar_pov(monkeypatch, sin_stock=True)
    assert out["sin_stock"] is True and avisos == []
