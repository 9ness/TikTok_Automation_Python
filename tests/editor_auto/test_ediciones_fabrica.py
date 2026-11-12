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


def test_vip_solo_rotulos_con_whisper_small():
    flujo = ef.flujo_para("vip", config_vip={"whisper_model_size": "large-v3",
                                             "fotos_internet": True, "max_fotos": 2}, solo_rotulos=True)
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
    assert [s["tool_id"] for s in params["tool_flow"]] == ["vip_overlays", "sticker_arrow", "subs_auto"]
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


# ─── Vídeo de referencia (copiar estilo + ritmo) y marca de agua ─────────────
from src.api.exceptions import ValidationError
from src.editor_auto.services import marca_agua, referencia_vip
from src.editor_auto.tools import vip_overlays as V


def test_ritmo_desde_json_sanea_y_pasa_a_config():
    r = referencia_vip.ritmo_desde_json(
        {"zooms": 6, "zoom_nivel": 1.5, "zoom_pct": 0.9, "rotulos": 5, "gancho_tipo": "Pregunta",
         "gancho_texto": "¿SABÍAS ESTO?", "gancho_clip": True}, 30.0, [1.0, 2.0, 3.0])
    assert r["zooms_min"] == 12.0 and r["zoom_nivel"] == 1.22 and r["zoom_pct"] == 0.5
    assert r["cortes_min"] == 6.0 and r["rotulos_min"] == 10.0 and r["gancho_tipo"] == "pregunta"
    cfg = referencia_vip.config_desde_ritmo(r)
    assert cfg["densidad_rotulos"] == "alta" and cfg["zooms"] and cfg["gancho_clip"]
    assert cfg["ritmo_ref"] is r
    sin = referencia_vip.config_desde_ritmo(referencia_vip.ritmo_desde_json({"gancho_tipo": "ninguno"}, 30, []))
    assert sin["zooms"] is False and sin["gancho"] is False and sin["densidad_rotulos"] == "baja"


def test_analizar_nunca_lanza(monkeypatch):
    import src.editor_auto.services.estilo_vip as ev

    monkeypatch.setattr(ev, "estilo_desde_video", lambda v: {"preset": "neon", "zooms": False})
    monkeypatch.setattr(referencia_vip, "ritmo_desde_video", lambda v: (_ for _ in ()).throw(RuntimeError("x")))
    logs = []
    assert referencia_vip.analizar("v.mp4", logs.append) == {"preset": "neon", "zooms": False}
    assert logs and "Ritmo" in logs[0]


def test_vision_cae_a_gemini(monkeypatch):
    monkeypatch.setattr(referencia_vip, "_vision_claude", lambda j, i: (_ for _ in ()).throw(RuntimeError("sin clave")))
    monkeypatch.setattr(referencia_vip, "_vision_gemini", lambda j, i: {"zooms": 2})
    assert referencia_vip._vision([b"x"], "p") == {"zooms": 2}


def test_vip_usa_el_ritmo_de_la_referencia():
    ref = {"zooms_min": 4.0, "zoom_nivel": 1.18, "zoom_pct": 0.2, "rotulos_min": 12.0,
           "gancho_tipo": "dato", "gancho_texto": "110 dB", "notas": "zoom en cada dato"}
    cfg = {**V.VipOverlaysTool().default_config(), "ritmo_ref": ref}
    assert V._max_rotulos(30.0, cfg) == 6  # 12/min en 30 s
    assert "110 dB" in V._nota_referencia(cfg, 30.0)
    plan = {"zooms": [{"t0": t, "t1": t + 2.0} for t in (1, 5, 9, 13, 17)]}
    zs = V._sanitize(plan, 30.0, cfg)["zooms"]
    # 4/min en 30 s → máx 3; y como mucho el 30 % (20 % + margen) del vídeo con zoom.
    assert len(zs) == 3 and all(z["nivel"] == 1.18 for z in zs)
    assert V._max_rotulos(30.0, V.VipOverlaysTool().default_config()) == 4  # sin referencia: densidad media


def test_vip_run_analiza_la_referencia_y_gana_lo_explicito(monkeypatch, tmp_path):
    import src.editor_auto.services.referencia_vip as rv

    ref = tmp_path / "ref.mp4"
    ref.write_bytes(b"x")
    entrada = tmp_path / "in.mp4"
    entrada.write_bytes(b"v")
    monkeypatch.setattr(rv, "analizar", lambda v, log=None: {
        "preset": "neon", "densidad_rotulos": "alta", "ritmo_ref": {"zooms_min": 2.0}, "_flujo": {"x": 1}})
    monkeypatch.setattr(V, "_probe", lambda p: {"audio": True, "dur": 10.0, "w": 1080, "h": 1920})
    vistos = []
    monkeypatch.setattr(V, "_transcribe", lambda v, w, cfg, ctx: vistos.append(cfg) or [])
    ctx = SimpleNamespace(temp_folder=str(tmp_path), job_id="j", on_log=lambda m: None,
                          on_progress=lambda f, m: None, extras={})
    V.VipOverlaysTool().run(input_path=str(entrada), output_path=str(tmp_path / "out.mp4"),
                            config={"video_referencia": str(ref), "densidad_rotulos": "baja"}, ctx=ctx)
    cfg = vistos[0]
    assert cfg["preset"] == "neon" and cfg["ritmo_ref"] == {"zooms_min": 2.0}
    assert cfg["densidad_rotulos"] == "baja" and "_flujo" not in cfg


def test_enviar_con_referencia_url(monkeypatch, tmp_path):
    import src.editor_auto.services.referencia_vip as rv
    import src.replicar_viral.servicio as rs

    editor_user = EditorUser(name="nueveness")
    router_ef, r, _ = _montar_envio(monkeypatch, tmp_path, editor_user)
    bajados = []
    monkeypatch.setattr(rs, "descargar_tiktok", lambda url, d: bajados.append(url) or d.write_bytes(b"r") or {})
    monkeypatch.setattr(rv, "analizar", lambda v, log=None: {
        "preset": "neon", "zooms": True, "ritmo_ref": {"zooms_min": 3.0}, "_flujo": {"subs_auto": {}}})
    monkeypatch.setattr(marca_agua, "quitar", lambda o, d, m="auto": None)
    q = _QueueEnc()
    up = SimpleNamespace(filename="clip.mp4", file=io.BytesIO(b"video"))
    res = router_ef.enviar(q, web_user="ness", file=up, ruta_bandeja="", para="", estilo="vip",
                           pasos="", config_vip='{"zooms": false}', dia="2026-11-12",
                           referencia=None, referencia_url="https://www.tiktok.com/@x/video/1",
                           referencia_ruta_bandeja="", quitar_marca="auto")
    assert bajados == ["https://www.tiktok.com/@x/video/1"]
    assert res["referencia"]["ritmo_ref"] == {"zooms_min": 3.0} and res["marca_quitada"] is None
    cfg = q.jobs[0].params["tool_flow"][0]["config"]
    assert cfg["preset"] == "neon" and cfg["zooms"] is False and cfg["_flujo"] == {"subs_auto": {"y_position": 0.70}}  # lo explícito gana
    e = r.d["ediciones_fabrica:ness"][-1]
    assert e["estilo"] == "vip" and e["referencia"] == "https://www.tiktok.com/@x/video/1"
    with pytest.raises(ValidationError):  # referencia solo con vip
        router_ef.enviar(q, web_user="ness", file=SimpleNamespace(filename="c.mp4", file=io.BytesIO(b"v")),
                         ruta_bandeja="", para="", estilo="normal", pasos="", config_vip="", dia="2026-11-12",
                         referencia=None, referencia_url="https://t/1", referencia_ruta_bandeja="",
                         quitar_marca="auto")


def test_marca_agua_mismo_metodo_que_ai_pro(monkeypatch):
    from src.nicho_pov_bof import config as pov

    monkeypatch.setattr(pov, "es_clip_omni", lambda p: True)
    assert marca_agua.decidir("x.mp4", "auto") == (pov.ZOOM_MARCA_OMNI, pov.ESQUINA_MARCA_OMNI)
    monkeypatch.setattr(pov, "es_clip_omni", lambda p: False)
    assert marca_agua.decidir("x.mp4", "auto") is None
    assert marca_agua.decidir("x.mp4", "veo") == (pov.ZOOM_MARCA_AGUA, pov.ESQUINA_MARCA_AGUA)
    assert marca_agua.decidir("x.mp4", "no") is None
    with pytest.raises(ValueError):
        marca_agua.decidir("x.mp4", "raro")


def test_cuenta_de_agentes_sin_avisos(monkeypatch):
    import src.api.routers.editor_auto.web_upload as w

    monkeypatch.setenv("EDITOR_CUENTA_AGENTES_EMAIL", "Agentes@X.es")
    assert w._es_cuenta_agentes(SimpleNamespace(account_email="agentes@x.es"))
    assert not w._es_cuenta_agentes(SimpleNamespace(account_email="cliente@x.es"))
    monkeypatch.delenv("EDITOR_CUENTA_AGENTES_EMAIL")
    assert not w._es_cuenta_agentes(SimpleNamespace(account_email=""))


# --- Clips en crudo (12/11/2026) ---------------------------------------------

import subprocess

from src.editor_auto.services import unir_clips


def test_vip_completo_con_referencia_y_nombre():
    flujo = ef.flujo_para("vip", config_vip={"preset": "neon"},
                          flujo_ref={"subs_auto": {"font_size": 99, "model_size": "large-v3"}},
                          texto_voz="Hola mundo", nombre_producto="Bici X")
    ids = [s.tool_id for s in flujo]
    assert ids == ["vip_overlays", "sticker_arrow", "subs_auto"]  # sin título fijo arriba
    vip, flecha, subs = (s.config for s in flujo)
    assert subs["font_size"] == 99 and subs["model_size"] == "small"
    assert subs["reference_text"] == "Hola mundo" and subs["y_position"] == 0.70
    assert vip["_flujo"]["subs_auto"]["y_position"] == 0.70 and "Bici X" in vip["notas_estilo"]
    assert flecha["sticker_file"].endswith(".mov")
    sin_nombre = ef.flujo_para("vip", config_vip={})
    assert [s.tool_id for s in sin_nombre] == ["vip_overlays", "sticker_arrow", "subs_auto"]


def test_franja_reservada_vip():
    assert V._franja_reservada({"franja_reservada": [0.095, 0.15]}, 1920) == (182, 288)
    assert V._franja_reservada({}, 1920) is None


def _clip(ruta, seg, audio=True, size="720x1280"):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=25:duration={seg}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seg}"]
    subprocess.run([*cmd, "-shortest" if audio else "-an", str(ruta)], check=True)
    return ruta


def _dur(r):
    return unir_clips._probe(r)[0]


def test_unir_clips_en_orden_y_sin_audio(tmp_path):
    a = _clip(tmp_path / "a.mp4", 1)
    b = _clip(tmp_path / "b.mp4", 2, audio=False, size="1080x1080")
    out = unir_clips.unir([a, b], tmp_path / "o.mp4")
    dur, tipos = unir_clips._probe(out)
    assert abs(dur - 3) < 0.2 and tipos == {"video", "audio"}
    wh = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                         "stream=width,height", "-of", "csv=p=0", str(out)],
                        capture_output=True, text=True).stdout.strip()
    assert wh == "1080,1920"


def test_unir_clips_voz(tmp_path):
    a = _clip(tmp_path / "a.mp4", 2)
    voz = tmp_path / "v.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1", str(voz)], check=True)
    out = unir_clips.unir([a], tmp_path / "o.mp4", voz)
    assert abs(_dur(out) - 2) < 0.2
    larga = tmp_path / "l.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=4", str(larga)], check=True)
    with pytest.raises(unir_clips.ErrorClips):
        unir_clips.unir([a], tmp_path / "o2.mp4", larga)
    with pytest.raises(unir_clips.ErrorClips):
        unir_clips.unir([], tmp_path / "o3.mp4")


def test_enviar_clips_de_bandeja(monkeypatch, tmp_path):
    import src.replicar_viral.video as rvv

    editor_user = EditorUser(name="nueveness")
    router_ef, _r, _ = _montar_envio(monkeypatch, tmp_path, editor_user)
    band = tmp_path / "bandeja"
    band.mkdir()
    _clip(band / "c1.mp4", 1)
    _clip(band / "c2.mp4", 1)
    monkeypatch.setattr(rvv, "ruta_bandeja", lambda u, r: band / r)
    monkeypatch.setattr(marca_agua, "quitar", lambda o, d, m="auto": None)
    q = _QueueEnc()
    res = router_ef.enviar(q, web_user="ness", file=None, ruta_bandeja="", para="", estilo="vip",
                           pasos="", config_vip="", dia="2026-11-12", referencia=None, referencia_url="",
                           referencia_ruta_bandeja="", quitar_marca="omni", clips='["c1.mp4", "c2.mp4"]',
                           voz_ruta_bandeja="", texto_voz="hola", nombre_producto="Bici", solo_rotulos=False)
    assert res["marca_quitada"] == [None, None] and "c1_x2" in res["filename"]
    assert "Bici" in q.jobs[0].params["tool_flow"][0]["config"]["notas_estilo"]
    with pytest.raises(ValidationError):  # dos fuentes
        router_ef.enviar(q, web_user="ness", file=None, ruta_bandeja="c1.mp4", para="", estilo="vip",
                         pasos="", config_vip="", dia="2026-11-12", referencia=None, referencia_url="",
                         referencia_ruta_bandeja="", quitar_marca="auto", clips='["c1.mp4"]')
    with pytest.raises(ValidationError):  # no existe
        router_ef.enviar(q, web_user="ness", file=None, ruta_bandeja="", para="", estilo="vip",
                         pasos="", config_vip="", dia="2026-11-12", referencia=None, referencia_url="",
                         referencia_ruta_bandeja="", quitar_marca="auto", clips='["nada.mp4"]')


# ─── Gancho: literal con referencia y base de ganchos sin ella ──────────────
def test_gancho_literal_de_la_referencia():
    cfg = {**V.VipOverlaysTool().default_config(),
           "ritmo_ref": {"gancho_tipo": "pregunta", "gancho_texto": "¿POR QUÉ NADIE HABLA DE ESTO?"}}
    nota = V._nota_referencia(cfg, 20.0)
    assert "LITERAL" in nota and "¿POR QUÉ NADIE HABLA DE ESTO?" in nota
    cfg["ritmo_ref"] = {"gancho_tipo": "ninguno"}
    assert "no pongas gancho" in V._nota_referencia(cfg, 20.0)


def test_banco_ganchos_guarda_sin_repetir_y_varia_tipos(monkeypatch):
    from src.editor_auto.services import banco_ganchos as B
    r = _Redis()
    monkeypatch.setattr(B, "_redis", lambda: r)
    assert B.guardar({"gancho_texto": "ESTO NO LO SABÍAS", "gancho_tipo": "sorpresa"}, "a.mp4")
    assert not B.guardar({"gancho_texto": "esto no lo sabías", "gancho_tipo": "sorpresa"})
    assert not B.guardar({"gancho_texto": "", "gancho_tipo": "dato"})
    assert not B.guardar({"gancho_texto": "X", "gancho_tipo": "ninguno"})
    B.guardar({"gancho_texto": "OTRA SORPRESA", "gancho_tipo": "sorpresa"})
    B.guardar({"gancho_texto": "80 KM", "gancho_tipo": "dato"})
    tipos = [g["tipo"] for g in B.ejemplos(2)]
    assert sorted(tipos) == ["dato", "sorpresa"]
