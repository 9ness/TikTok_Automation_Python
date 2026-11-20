"""Si las fotos de apoyo no ponen nada: se avisa del motivo y se devuelve lo cobrado por el extra."""
from src.editor_auto.rapido import servicio as svc
from src.editor_auto.rapido import extras as ex


def test_devolver_extra_una_vez(monkeypatch):
    ficha = {"id": "v1", "email": "a@b.c", "cobrado": True, "creditos": 5, "cobrado_fecha": "2026-11-20"}
    guardada = dict(ficha)
    movs = []
    monkeypatch.setattr(svc, "cargar_ficha", lambda vid: dict(guardada))
    monkeypatch.setattr(svc, "guardar_ficha", lambda f: guardada.update(f))
    monkeypatch.setattr(svc, "ajustar_creditos", lambda e, n: movs.append(n))
    monkeypatch.setattr(svc, "descontar_historial", lambda *a: None)
    monkeypatch.setattr(svc, "registrar_evento", lambda *a, **k: None)
    p = ex.precio(["fotos"])
    txt = svc.devolver_extra(ficha, "fotos", "auto")
    assert "devuelto" in txt and movs == [p]
    assert guardada["creditos"] == svc.cr(5 - p) and guardada["extras_devueltos"] == ["fotos"]
    svc.devolver_extra(ficha, "fotos", "auto")  # segunda vez: nada
    assert movs == [p]


def test_retoque_no_devuelve(monkeypatch):
    monkeypatch.setattr(svc, "ajustar_creditos", lambda *a: (_ for _ in ()).throw(AssertionError))
    assert svc.devolver_extra({"id": "v", "email": "x"}, "fotos", "estilo") == ""
