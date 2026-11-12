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


# ─── Envíos de agentes (editar_en_editor) ───────────────────────────────────
import io

import pytest

from src.api.exceptions import APIError
from src.editor_auto.models import EditorUser
from src.editor_auto.models.editor_user import ToolStep


class _RedisSet(_Redis):
    def __init__(self):
        super().__init__()
        self.sets = {}

    def sadd(self, k, v):
        self.sets.setdefault(k, set()).add(v)

    def smembers(self, k):
        return self.sets.get(k, set())

    def is_available(self):
        return True


class _QueueEnc:
    def __init__(self):
        self.jobs = []

    def enqueue(self, mode, title="", params=None, scheduled_for=None):
        job = SimpleNamespace(id=f"j{len(self.jobs) + 1}", params=params, mode=mode)
        self.jobs.append(job)
        return job

    def get_all(self):
        return self.jobs


def test_vip_solo_vip_overlays_con_whisper_small():
    flujo = ef.flujo_para("vip", config_vip={"whisper_model_size": "large-v3",
                                             "fotos_internet": True, "max_fotos": 2})
    assert [s.tool_id for s in flujo] == ["vip_overlays"]
    cfg = flujo[0].config
    assert cfg["whisper_model_size"] == "small" and cfg["fotos_internet"] is False
    assert cfg["max_fotos"] == 2


def test_pasos_valida_y_rebaja_whisper_large():
    flujo = ef.flujo_para("pasos", pasos=[
        {"tool_id": "subs_auto", "config": {}},
        {"tool_id": "silence_cutter", "config": {"whisper_model_size": "medium"}},
    ])
    assert flujo[0].config["model_size"] == "small"          # su defecto es large-v3
    assert flujo[1].config["whisper_model_size"] == "medium"  # no es large: se respeta
    with pytest.raises(ValueError):
        ef.flujo_para("pasos", pasos=[{"tool_id": "no_existe"}])
    with pytest.raises(ValueError):
        ef.flujo_para("pasos", pasos=[{"tool_id": "silence_cutter_scripted"}])
    with pytest.raises(ValueError):
        ef.flujo_para("raro")


def _montar_envio(monkeypatch, tmp_path, editor_user):
    from src.api.routers.editor_auto import ediciones_fabrica as router_ef
    from src.api.routers.editor_auto import web_upload
    from src.editor_auto.services import provision_service

    r = _RedisSet()
    monkeypatch.setattr(ef, "get_editor_redis", lambda: r)
    monkeypatch.setattr(web_upload, "get_editor_redis", lambda: r)
    monkeypatch.setattr(web_upload, "user_input_day_folder", lambda u, d: str(tmp_path / "entrada" / d))
    monkeypatch.setattr(web_upload, "web_priority", lambda u, a=None: 0)
    monkeypatch.setattr(provision_service, "provision_from_web", lambda email: editor_user)
    monkeypatch.setenv("EDITOR_CUENTA_AGENTES_EMAIL", "agentes@ejemplo.com")
    guardados = []
    monkeypatch.setattr(web_upload.UserRepo, "save", lambda self, u: guardados.append(u))
    return router_ef, r, guardados


def test_enviar_flujo_en_el_job_sin_tocar_el_usuario(monkeypatch, tmp_path):
    flujo_guardado = [ToolStep(tool_id="subs_auto"), ToolStep(tool_id="sticker_arrow")]
    editor_user = EditorUser(name="nueveness", tool_flow=[s.model_copy() for s in flujo_guardado])
    router_ef, r, guardados = _montar_envio(monkeypatch, tmp_path, editor_user)
    q = _QueueEnc()
    up = SimpleNamespace(filename="clip.mp4", file=io.BytesIO(b"video"))
    res = router_ef.enviar(q, web_user="ness", file=up, ruta_bandeja="", para="", estilo="vip",
                           pasos="", config_vip='{"max_fotos": 1}', dia="2026-11-12")
    assert res["para"] == "ness" and res["estilo"] == "vip" and res["job_id"] == "j1"
    params = q.jobs[0].params
    assert [s["tool_id"] for s in params["tool_flow"]] == ["vip_overlays"]
    assert params["tool_flow"][0]["config"]["whisper_model_size"] == "small"
    assert (tmp_path / "entrada" / "2026-11-12" / res["filename"]).read_bytes() == b"video"
    # El flujo guardado de la cuenta no cambia ni se guarda.
    assert [s.tool_id for s in editor_user.tool_flow] == ["subs_auto", "sticker_arrow"]
    assert guardados == []
    # Queda apuntado para `ediciones_editor` y como enviado en el día.
    assert r.d["ediciones_fabrica:ness"][0]["job_id"] == "j1"
    assert res["filename"] in r.smembers(f"webday_sentfiles:{editor_user.id}:2026-11-12")


def test_enviar_para_otro_sin_admin_da_403(monkeypatch, tmp_path):
    from src.api import users

    router_ef, _r, _g = _montar_envio(monkeypatch, tmp_path, EditorUser(name="nueveness"))
    monkeypatch.setattr(users, "es_admin", lambda u: False)
    up = SimpleNamespace(filename="clip.mp4", file=io.BytesIO(b"video"))
    with pytest.raises(APIError) as e:
        router_ef.enviar(_QueueEnc(), web_user="ana", file=up, ruta_bandeja="", para="ness",
                         estilo="vip", pasos="", config_vip="", dia="2026-11-12")
    assert e.value.status_code == 403


def test_pipeline_usa_el_flujo_del_job(monkeypatch, tmp_path):
    from src.editor_auto.pipeline import run as run_mod

    user = EditorUser(name="nueveness", tool_flow=[ToolStep(tool_id="subs_auto")])
    monkeypatch.setattr(run_mod, "UserRepo", lambda: SimpleNamespace(get=lambda uid: user))
    vistos = []

    def _preflight(steps):
        vistos.extend(s.tool_id for s in steps)
        return ["parar aquí"], []

    monkeypatch.setattr(run_mod, "_preflight_check", _preflight)
    entrada = tmp_path / "in.mp4"
    entrada.write_bytes(b"x")
    with pytest.raises(RuntimeError):
        run_mod.run_editor_auto_pipeline(
            user_id=user.id, input_video_path=str(entrada), job_id="j1", temp_folder=str(tmp_path),
            on_log=lambda _m: None, on_progress=lambda *_a: None,
            tool_flow_override=[{"tool_id": "vip_overlays", "config": {"whisper_model_size": "small"}}],
        )
    assert vistos == ["vip_overlays"]
    assert [s.tool_id for s in user.tool_flow] == ["subs_auto"]  # el usuario no cambia
