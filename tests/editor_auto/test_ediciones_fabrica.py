"""Puente Editor Auto → usuario de la fábrica (ediciones_fabrica)."""

from types import SimpleNamespace

from src.editor_auto.services import ediciones_fabrica as ef
from src.queue.models import JobStatus


class _Redis:
    def __init__(self):
        self.d = {}

    def get_json(self, k):
        return self.d.get(k)

    def set_json(self, k, v):
        self.d[k] = v
        return True


class _Queue:
    def __init__(self, jobs):
        self.jobs = jobs

    def get_all(self):
        return self.jobs


def test_apuntar_listar_y_mp4(monkeypatch, tmp_path):
    r = _Redis()
    monkeypatch.setattr(ef, "get_editor_redis", lambda: r)
    editor = SimpleNamespace(name="nueveness", id="u1")
    ef.apuntar("ness", editor, "2026-11-12", [
        {"job_id": "j1", "filename": "a.mp4"}, {"job_id": "j2", "filename": "b.mp4"}])
    salida = tmp_path / "a_editado.mp4"
    salida.write_bytes(b"x")
    q = _Queue([
        SimpleNamespace(id="j1", status=JobStatus.COMPLETED, result_path=str(salida), error=None),
        SimpleNamespace(id="j2", status=JobStatus.RUNNING, result_path=None, error=None),
    ])
    lista = ef.listar("ness", q)
    assert [e["job_id"] for e in lista] == ["j2", "j1"]  # lo más nuevo primero
    assert lista[1]["listo"] and lista[1]["salida"] == "a_editado.mp4"
    assert not lista[0]["listo"] and lista[0]["estado"] == "running"
    assert ef.ruta_mp4("ness", "j1", q) == str(salida)
    assert ef.ruta_mp4("ness", "j2", q) is None
    assert ef.listar("ana", q) == []


def test_trabajo_purgado_busca_en_salida(monkeypatch, tmp_path):
    r = _Redis()
    monkeypatch.setattr(ef, "get_editor_redis", lambda: r)
    monkeypatch.setattr(ef, "user_output_day_folder", lambda u, d: str(tmp_path))
    (tmp_path / "123_clip_editado.mp4").write_bytes(b"x")
    ef.apuntar("ana", SimpleNamespace(name="nueveness", id="u1"), "2026-11-12",
               [{"job_id": "j9", "filename": "123_clip.mp4"}])
    e = ef.listar("ana", _Queue([]))[0]
    assert e["listo"] and e["estado"] == "completed" and e["salida"] == "123_clip_editado.mp4"
