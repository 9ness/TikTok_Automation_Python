"""Editor rápido: créditos, subida, cobro, cola, retoque y descarga."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from src.api.web_ticket import make_ticket
from src.editor_auto.rapido import servicio as svc
from src.queue.models import JobMode
from tests.tiktok_shop.conftest import FakeRedis

BASE = "/api/v1/editor-auto/rapido"
EMAIL = "ana@example.com"


@pytest.fixture
def rapido(app_client, fake_job_queue, tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_UPLOAD_SECRET", "x" * 40)
    monkeypatch.setenv("EDITOR_RAPIDO_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("EDITOR_RAPIDO_FREE_CREDITS", "150")
    monkeypatch.delenv("API_KEY", raising=False)
    redis = FakeRedis()
    redis.prefix = "editor_auto:"
    monkeypatch.setattr(svc, "get_editor_redis", lambda: redis)
    monkeypatch.setattr(svc, "duracion_video", lambda p: 95.0)  # 95 s → 1 crédito (1 vídeo)
    hdr = {"Authorization": "Bearer " + make_ticket(EMAIL, "", scope="rapido")}
    return app_client, fake_job_queue, hdr


def _subir(c, hdr, nombre="clip.mp4"):
    return c.post(f"{BASE}/videos", headers=hdr, files={"file": (nombre, io.BytesIO(b"datos"), "video/mp4")})


def test_sin_ticket_o_scope_malo(rapido):
    c, _, _ = rapido
    assert c.get(f"{BASE}/saldo").status_code == 401
    malo = {"Authorization": "Bearer " + make_ticket(EMAIL, "2026-11-14", scope="upload")}
    assert c.get(f"{BASE}/saldo", headers=malo).status_code == 401


def test_saldo_gratis_inicial_una_sola_vez(rapido):
    c, _, hdr = rapido
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 150
    svc.ajustar_creditos(EMAIL, -1)
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 149


def test_creditos_por_video_1_hasta_5_min_2_hasta_10():
    assert svc.creditos_de(0.2) == 1
    assert svc.creditos_de(47.9) == 1
    assert svc.creditos_de(300) == 1
    assert svc.creditos_de(300.5) == 2
    assert svc.creditos_de(600) == 2


def test_saldo_viejo_pasa_a_videos_una_vez(rapido):
    from src.editor_auto.rapido.servicio import _k_saldo
    r = svc.get_editor_redis()
    r.set_json(_k_saldo("min@x.com"), {"creditos": 105, "gratis_dados": 5})  # minutos
    r.set_json(_k_saldo("seg@x.com"), {"creditos": 10000, "gratis_dados": 300, "unidad": "s"})  # segundos
    assert svc.saldo("min@x.com")["creditos"] == 105
    assert svc.saldo("seg@x.com")["creditos"] == 167
    assert svc.saldo("seg@x.com")["creditos"] == 167  # no vuelve a dividir
    assert svc.saldo("seg@x.com")["gratis_dados"] == 5
    assert svc.saldo("nuevo@x.com")["creditos"] == svc.gratis_inicial() == 150


def test_creditos_no_caducan_por_ahora(rapido):
    import time as _t
    r = svc.get_editor_redis()
    viejo = _t.time() - 900 * 86400
    r.set_json(svc._k_saldo("nocad@x.com"), {"creditos": 7, "unidad": "v", "creado": viejo, "ultima_recarga": viejo})
    assert svc.saldo("nocad@x.com")["creditos"] == 7
    assert svc.caduca_en(svc.saldo("nocad@x.com")) is None


def test_creditos_caducan_si_se_activa(rapido, monkeypatch):
    import time as _t
    monkeypatch.setattr(svc, "CADUCIDAD_DIAS", 365)
    r = svc.get_editor_redis()
    viejo = _t.time() - 366 * 86400
    r.set_json(svc._k_saldo("cad@x.com"), {"creditos": 7, "unidad": "v", "creado": viejo, "ultima_recarga": viejo})
    s = svc.saldo("cad@x.com")
    assert s["creditos"] == 0 and s["caducados"] == 7
    svc.ajustar_creditos("cad@x.com", 25, recarga=True)
    s = svc.saldo("cad@x.com")
    assert s["creditos"] == 25 and svc.caduca_en(s) > _t.time() + 364 * 86400
    # sin fecha (cuenta antigua): cuenta desde hoy, no caduca de golpe
    r.set_json(svc._k_saldo("ant@x.com"), {"creditos": 5, "unidad": "v", "creado": viejo})
    assert svc.saldo("ant@x.com")["creditos"] == 5


def test_medios_creditos_cobro_y_devolucion(rapido):
    svc.ajustar_creditos("medio@x.com", 0)
    base = svc.saldo("medio@x.com")["creditos"]
    assert svc.cobrar("medio@x.com", 0.5)
    assert svc.saldo("medio@x.com")["creditos"] == base - 0.5
    svc.ajustar_creditos("medio@x.com", 0.5)
    assert svc.saldo("medio@x.com")["creditos"] == base
    assert isinstance(svc.saldo("medio@x.com")["creditos"], int)


def test_subir_rechaza_formato_y_no_cobra(rapido):
    c, _, hdr = rapido
    r = c.post(f"{BASE}/videos", headers=hdr, files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")})
    assert r.status_code == 422 or r.status_code == 400
    r = _subir(c, hdr)
    assert r.status_code == 201
    assert r.json()["creditos"] == 1 and r.json()["saldo"] == 150


def test_cortar_cobra_encola_y_progreso(rapido):
    c, q, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    r = c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr,
               json={"ritmo": "sin_pausas", "formato": "original", "idioma": "es"})
    assert r.status_code == 202 and r.json()["saldo"] == 149
    job = q.get_all()[0]
    assert job.mode == JobMode.EDITOR_RAPIDO and job.params["video_id"] == vid
    job.progress, job.progress_label = 0.4, "Whisper transcribiendo…"
    q.set_status(job.id, "running")
    v = c.get(f"{BASE}/videos/{vid}", headers=hdr).json()
    assert v["estado"] == "cola" and v["progreso"]["fase"] == "Whisper transcribiendo…"
    # no se puede cortar dos veces
    assert c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={}).status_code == 409


def test_sin_saldo_402(rapido):
    c, _, hdr = rapido
    svc.ajustar_creditos(EMAIL, -150)  # quedan 0
    vid = _subir(c, hdr).json()["id"]
    r = c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={})
    assert r.status_code == 402
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 0


def test_ajustes_invalidos(rapido):
    c, _, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    assert c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={"ritmo": "turbo"}).status_code in (400, 422)


def test_trabajo_fallido_devuelve_creditos_una_vez(rapido):
    c, q, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={})
    q.set_status(q.get_all()[0].id, "failed")
    v = c.get(f"{BASE}/videos/{vid}", headers=hdr).json()
    assert v["estado"] == "error"
    c.get(f"{BASE}/videos/{vid}", headers=hdr)
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 150  # devuelto una sola vez


def test_aislamiento_entre_usuarios(rapido):
    c, _, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    otro = {"Authorization": "Bearer " + make_ticket("otro@example.com", "", scope="rapido")}
    assert c.get(f"{BASE}/videos/{vid}", headers=otro).status_code == 404
    assert c.get(f"{BASE}/videos", headers=otro).json()["videos"] == []


def test_calcular_cortes_con_texto():
    proy = {
        "video_duration_s": 10.0,
        "keep_intervals": [[0.5, 3.0], [4.0, 9.0]],
        "words": [
            {"idx": 0, "word": "hola", "start": 1.0, "end": 1.4},
            {"idx": 1, "word": "eh", "start": 3.2, "end": 3.6},
            {"idx": 2, "word": "vale", "start": 5.0, "end": 5.4},
        ],
    }
    cortes = svc.calcular_cortes(proy)
    assert [(c["inicio"], c["fin"]) for c in cortes] == [(0.0, 0.5), (3.0, 4.0), (9.0, 10.0)]
    assert cortes[1]["texto"] == "eh" and cortes[1]["tipo"] == "palabras"
    assert cortes[0]["tipo"] == "silencio"
    # devolver el corte 1 → el tramo 3.0-4.0 vuelve
    keeps = svc.tramos_a_conservar(10.0, cortes, {1})
    assert keeps == [(0.5, 9.0)]


def test_cortes_sugeridos():
    proy = {
        "video_duration_s": 10.0,
        "keep_intervals": [[0.5, 3.0], [4.0, 9.0]],
        "words": [{"idx": 0, "word": "hola", "start": 1.0, "end": 1.4}],
        "sugeridos": [
            {"start": 5.0, "end": 6.0, "text": "chicas cómo son", "motivo": "ia"},
            {"start": 3.0, "end": 3.9, "text": "ya cortado", "motivo": "barrido"},  # ya quitado → fuera
            {"start": 5.0, "end": 6.0, "text": "chicas cómo son", "motivo": "barrido"},  # duplicado → fuera
        ],
    }
    cortes = svc.calcular_cortes(proy)
    sug = [c for c in cortes if c["tipo"] == "sugerido"]
    assert len(sug) == 1 and sug[0]["id"] == 3 and sug[0]["texto"] == "chicas cómo son"
    # sin aplicar: el sugerido se queda en el vídeo
    assert svc.tramos_a_conservar(10.0, cortes, set()) == [(0.5, 3.0), (4.0, 9.0)]
    # aplicado: se corta
    assert svc.tramos_a_conservar(10.0, cortes, set(), {3}) == [(0.5, 3.0), (4.0, 5.0), (6.0, 9.0)]
    assert len(svc.cortes_activos(cortes, {0}, {3})) == 3


def test_runner_auto_y_retoque_y_descarga(rapido, monkeypatch):
    c, q, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={"idioma": "auto"})
    job = q.get_all()[0]
    llamadas = []

    class FalsoCortador:
        def run(self, *, input_path, output_path, config, ctx):
            llamadas.append(config)
            open(output_path, "wb").write(b"mp4")
            if "manual_keep_intervals" not in config:
                (svc.carpeta(vid) / f"editproject_{ctx.job_id}.json").write_text(json.dumps({
                    "video_duration_s": 95.0, "keep_intervals": [[2.0, 60.0], [62.0, 95.0]],
                    "words": [{"word": "mmm", "start": 60.2, "end": 61.5}],
                }))
            ctx.on_progress(0.5, "Cortando…")
            return output_path

    import src.editor_auto.tools.silence_cutter as sc
    monkeypatch.setattr(sc, "SilenceCutterTool", FalsoCortador)
    monkeypatch.setattr(svc, "duracion_video", lambda p: 70.0)
    svc.ejecutar(job, lambda m: None, lambda f, m="": None)
    assert llamadas[0]["ai_language"] is None and llamadas[0]["ritmo"] == "natural"
    assert llamadas[0]["ai_clean_enabled"] is False and llamadas[0]["vad_enabled"] is True

    v = c.get(f"{BASE}/videos/{vid}", headers=hdr).json()
    assert v["estado"] == "listo" and v["duracion_final_s"] == 70.0
    textos = [x["texto"] for x in v["cortes"]]
    assert "mmm" in textos
    cid = next(x["id"] for x in v["cortes"] if x["texto"] == "mmm")

    # retoque: devolver ese corte
    assert c.post(f"{BASE}/videos/{vid}/retocar", headers=hdr, json={"devueltos": [999]}).status_code in (400, 422)
    assert c.post(f"{BASE}/videos/{vid}/retocar", headers=hdr, json={"devueltos": [cid]}).status_code == 202
    job2 = q.get_all()[-1]
    svc.ejecutar(job2, lambda m: None, lambda f, m="": None)
    keeps = llamadas[1]["manual_keep_intervals"]
    assert any(a <= 60.5 <= b for a, b in keeps)  # la zona devuelta está dentro de un tramo
    v = c.get(f"{BASE}/videos/{vid}", headers=hdr).json()
    assert [x["devuelto"] for x in v["cortes"] if x["id"] == cid] == [True]

    # descarga con ticket en query (para <video src>)
    t = hdr["Authorization"].split(" ", 1)[1]
    r = c.get(f"{BASE}/videos/{vid}/archivo?t={t}&descargar=1")
    assert r.status_code == 200 and r.content == b"mp4"
    assert "attachment" in r.headers["content-disposition"]
    # y se puede borrar
    assert c.delete(f"{BASE}/videos/{vid}", headers=hdr).status_code == 200
    assert c.get(f"{BASE}/videos", headers=hdr).json()["videos"] == []


def test_admin_creditos_exige_api_key(rapido, monkeypatch):
    c, _, hdr = rapido
    monkeypatch.setenv("API_KEY", "k")
    from src.api.config import get_settings
    get_settings.cache_clear()
    try:
        assert c.post(f"{BASE}/admin/creditos", json={"email": EMAIL, "delta": 5}).status_code == 401
        r = c.post(f"{BASE}/admin/creditos", json={"email": EMAIL, "delta": 5}, headers={"X-API-Key": "k"})
        assert r.json()["creditos"] == 155
    finally:
        get_settings.cache_clear()


def test_subida_por_trozos_reanudable(rapido):
    c, _, hdr = rapido
    r = c.post(f"{BASE}/subidas", headers=hdr, json={"nombre": "IMG_1.MOV", "bytes": 9})
    assert r.status_code == 201
    vid = r.json()["id"]
    assert c.put(f"{BASE}/subidas/{vid}?offset=0", headers=hdr, content=b"abcd").json()["recibidos"] == 4
    # reintento del mismo trozo → 409 con lo recibido (el cliente retoma desde ahí)
    dup = c.put(f"{BASE}/subidas/{vid}?offset=0", headers=hdr, content=b"abcd")
    assert dup.status_code == 409
    assert c.get(f"{BASE}/subidas/{vid}", headers=hdr).json()["recibidos"] == 4
    assert c.post(f"{BASE}/subidas/{vid}/fin", headers=hdr).status_code == 409  # faltan bytes
    c.put(f"{BASE}/subidas/{vid}?offset=4", headers=hdr, content=b"efghi")
    r = c.post(f"{BASE}/subidas/{vid}/fin", headers=hdr)
    assert r.status_code == 200 and r.json()["creditos"] == 1
    assert [v["id"] for v in c.get(f"{BASE}/videos", headers=hdr).json()["videos"]] == [vid]


def test_subida_trozos_formato_y_listado(rapido):
    c, _, hdr = rapido
    assert c.post(f"{BASE}/subidas", headers=hdr, json={"nombre": "a.txt", "bytes": 5}).status_code in (400, 422)
    vid = c.post(f"{BASE}/subidas", headers=hdr, json={"nombre": "a.mov", "bytes": 5}).json()["id"]
    assert c.get(f"{BASE}/videos", headers=hdr).json()["videos"] == []  # a medias no sale
    assert c.put(f"{BASE}/subidas/{vid}?offset=0", headers=hdr, content=b"123456789").status_code in (400, 422)


def test_admin_no_gasta_y_nivel(rapido):
    c, _, _ = rapido
    adm = {"Authorization": "Bearer " + make_ticket("jefe@example.com", "", scope="rapido", extra={"rol": "admin"})}
    s = c.get(f"{BASE}/saldo", headers=adm).json()
    assert s["nivel"] == "admin" and s["ilimitado"] is True
    svc.ajustar_creditos("jefe@example.com", -150)  # sin saldo
    vid = _subir(c, adm).json()["id"]
    assert c.post(f"{BASE}/videos/{vid}/cortar", headers=adm, json={}).status_code == 202
    assert c.get(f"{BASE}/saldo", headers=adm).json()["creditos"] == 0


def test_rol_desconocido_es_standard(rapido):
    c, _, _ = rapido
    h = {"Authorization": "Bearer " + make_ticket(EMAIL, "", scope="rapido", extra={"rol": "dios"})}
    assert c.get(f"{BASE}/saldo", headers=h).json()["nivel"] == "standard"


# ───────────────────── Estilo: opciones, subtítulos, flecha ─────────────────────

def _falso_cortador(vid, llamadas=None):
    class FalsoCortador:
        def run(self, *, input_path, output_path, config, ctx):
            if llamadas is not None:
                llamadas.append(config)
            open(output_path, "wb").write(b"mp4")
            if "manual_keep_intervals" not in config:
                (svc.carpeta(vid) / f"editproject_{ctx.job_id}.json").write_text(json.dumps({
                    "video_duration_s": 95.0, "keep_intervals": [[2.0, 60.0], [62.0, 95.0]],
                    "words": [{"word": "mmm", "start": 60.2, "end": 61.5}],
                }))
            ctx.on_progress(1.0, "Cortando…")
            return output_path
    return FalsoCortador


def _falsas_estilo(monkeypatch, subs_calls, flecha_calls, fallar_subs=False):
    class FalsoSubs:
        def run(self, *, input_path, output_path, config, ctx):
            subs_calls.append((input_path, config))
            if fallar_subs:
                raise RuntimeError("whisper roto")
            open(output_path, "wb").write(b"mp4+subs")
            return output_path

    class FalsaFlecha:
        def run(self, *, input_path, output_path, config, ctx):
            flecha_calls.append((input_path, config))
            open(output_path, "wb").write(open(input_path, "rb").read() + b"+flecha")
            return output_path

    import src.editor_auto.tools.silence_cutter as sc
    import src.editor_auto.tools.subs_auto as sa
    import src.editor_auto.tools.sticker_arrow as st
    monkeypatch.setattr(sa, "SubsAutoTool", FalsoSubs)
    monkeypatch.setattr(st, "StickerArrowTool", FalsaFlecha)
    return sc


def test_opciones_catalogo(rapido):
    c, _, hdr = rapido
    assert c.get(f"{BASE}/opciones").status_code == 401
    o = c.get(f"{BASE}/opciones", headers=hdr).json()
    assert o["posiciones"] == ["abajo", "centro", "arriba"]
    assert len(o["colores"]) == 8 and all(x.startswith("#") and len(x) == 7 for x in o["colores"])
    assert 1 <= len(o["fuentes"]) <= 8 and {"id", "nombre"} <= set(o["fuentes"][0])
    e = o["estilos"][0]
    assert {"id", "nombre", "fuente", "color_texto", "color_resalte", "modo_resalte", "borde"} <= set(e)
    assert o["flechas"] and not any("navidad" in f["id"] for f in o["flechas"])
    f = o["flechas"][0]
    assert f["png_url"] == f"{BASE}/flechas/{f['id']}.png"


def test_flecha_png_publica(rapido, tmp_path, monkeypatch):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("sin ffmpeg")
    c, _, _ = rapido
    carp = tmp_path / "flechas"
    carp.mkdir()
    fid = svc.flechas_disponibles()[0]
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1",
                    str(carp / fid["fichero"])], check=True)
    import src.editor_auto.config as cfg
    monkeypatch.setattr(cfg, "arrows_folder", lambda: str(carp))
    r = c.get(f"{BASE}/flechas/{fid['id']}.png")  # sin ticket
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:4] == b"\x89PNG"
    assert c.get(f"{BASE}/flechas/no_existe.png").status_code == 404


def test_cortar_con_estilo_se_guarda_y_valida(rapido):
    c, q, hdr = rapido
    o = c.get(f"{BASE}/opciones", headers=hdr).json()
    vid = _subir(c, hdr).json()["id"]
    for malo in ({"subtitulos": {"estilo": "nope"}}, {"subtitulos": {"posicion": "lado"}},
                 {"subtitulos": {"color": "rojo"}}, {"subtitulos": {"fuente": "zzz"}},
                 {"flecha": {"activo": True, "id": "nope"}}):
        assert c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json=malo).status_code in (400, 422)
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 150  # nada cobrado
    body = {"subtitulos": {"estilo": o["estilos"][1]["id"], "color": "#FDE047", "fuente": "anton", "posicion": "arriba"},
            "flecha": {"activo": True, "id": o["flechas"][0]["id"]}}
    assert c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json=body).status_code == 202
    aj = c.get(f"{BASE}/videos/{vid}", headers=hdr).json()["ajustes"]
    assert aj["subtitulos"]["color"] == "#FDE047" and aj["subtitulos"]["posicion"] == "arriba"
    assert aj["flecha"] == {"activo": True, "id": o["flechas"][0]["id"], "todo_video": False}


def test_peticion_antigua_defaults(rapido):
    c, _, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    assert c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={"ritmo": "natural"}).status_code == 202
    aj = c.get(f"{BASE}/videos/{vid}", headers=hdr).json()["ajustes"]
    assert aj["subtitulos"]["activo"] is True and aj["subtitulos"]["estilo"] and aj["subtitulos"]["posicion"] == "abajo"
    assert aj["flecha"]["activo"] is False


def test_runner_subs_flecha_estilo_y_resumen(rapido, monkeypatch):
    c, q, hdr = rapido
    o = c.get(f"{BASE}/opciones", headers=hdr).json()
    vid = _subir(c, hdr).json()["id"]
    c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={
        "idioma": "es", "subtitulos": {"color": "#22C55E", "posicion": "centro"},
        "flecha": {"activo": True, "id": o["flechas"][0]["id"]}})
    job = q.get_all()[0]
    subs, flechas = [], []
    sc = _falsas_estilo(monkeypatch, subs, flechas)
    monkeypatch.setattr(sc, "SilenceCutterTool", _falso_cortador(vid))
    monkeypatch.setattr(svc, "duracion_video", lambda p: 70.0)
    monkeypatch.setenv("EDITOR_RAPIDO_WHISPER_MODEL", "base")
    prog = []
    svc.ejecutar(job, lambda m: None, lambda f, m="": prog.append(f))
    assert prog == sorted(prog) and prog[-1] == 1.0
    cfg = subs[0][1]
    assert cfg["model_size"] == "base" and cfg["language"] == "es" and cfg["highlight_color"] == "#22C55E"
    assert cfg["y_position"] == 0.5 and cfg["corregir_nombres"] is False
    assert subs[0][0].endswith("cortado.mp4") and flechas[0][0] != subs[0][0]
    assert (svc.carpeta(vid) / "cortado.mp4").read_bytes() == b"mp4"
    assert svc.ruta_resultado(vid).read_bytes() == b"mp4+subs+flecha"
    v = c.get(f"{BASE}/videos/{vid}", headers=hdr).json()
    assert v["estado"] == "listo" and v["aviso"] is None
    assert v["resumen"] == {"pausas": 2, "repeticiones": 0, "segundos_quitados": 4.0,
                            "duracion_original_s": 95.0, "duracion_final_s": 70.0}
    assert set(v["resumen"]) == {"pausas", "repeticiones", "segundos_quitados", "duracion_original_s", "duracion_final_s"}

    # re-estilizar: sin cortar, gratis, solo subs sin flecha
    saldo0 = c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"]
    r = c.post(f"{BASE}/videos/{vid}/estilo", headers=hdr,
               json={"subtitulos": {"estilo": o["estilos"][2]["id"]}, "flecha": {"activo": False}})
    assert r.status_code == 202
    assert c.post(f"{BASE}/videos/{vid}/estilo", headers=hdr, json={"flecha": {"activo": False}}).status_code == 409
    job2 = q.get_all()[-1]
    assert job2.params["modo"] == "estilo"
    subs.clear(); flechas.clear()
    svc.ejecutar(job2, lambda m: None, lambda f, m="": None)
    assert subs[0][0].endswith("cortado.mp4") and not flechas
    assert svc.ruta_resultado(vid).read_bytes() == b"mp4+subs"
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == saldo0
    assert c.get(f"{BASE}/videos/{vid}", headers=hdr).json()["ajustes"]["subtitulos"]["estilo"] == o["estilos"][2]["id"]
    # validación del endpoint
    assert c.post(f"{BASE}/videos/{vid}/estilo", headers=hdr, json={}).status_code in (400, 422)
    assert c.post(f"{BASE}/videos/{vid}/estilo", headers=hdr, json={"subtitulos": {"estilo": "x"}}).status_code in (400, 422)


def test_subs_fallan_se_entrega_el_corte_con_aviso(rapido, monkeypatch):
    c, q, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={})
    job = q.get_all()[0]
    sc = _falsas_estilo(monkeypatch, [], [], fallar_subs=True)
    monkeypatch.setattr(sc, "SilenceCutterTool", _falso_cortador(vid))
    monkeypatch.setattr(svc, "duracion_video", lambda p: 70.0)
    svc.ejecutar(job, lambda m: None, lambda f, m="": None)
    v = c.get(f"{BASE}/videos/{vid}", headers=hdr).json()
    assert v["estado"] == "listo" and "subtítulos" in v["aviso"]
    assert svc.ruta_resultado(vid).read_bytes() == b"mp4"
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 149  # no se devuelven


def test_admin_cuentas_y_dar(rapido):
    c, _, hdr = rapido
    adm = {"Authorization": "Bearer " + make_ticket("jefe@example.com", "", scope="rapido", extra={"rol": "admin"})}
    assert c.get(f"{BASE}/admin/cuentas", headers=hdr).status_code == 403
    assert c.post(f"{BASE}/admin/dar", headers=hdr, json={"email": EMAIL, "creditos": 5}).status_code == 403
    _subir(c, hdr)  # crea saldo de ana
    cuentas = c.get(f"{BASE}/admin/cuentas", headers=adm).json()["cuentas"]
    ana = next(x for x in cuentas if x["email"] == EMAIL)
    assert ana == {"email": EMAIL, "creditos": 150, "n_videos": 1}
    r = c.post(f"{BASE}/admin/dar", headers=adm, json={"email": "Nuevo@Example.com", "creditos": 4})
    assert r.json() == {"email": "nuevo@example.com", "creditos": 154}
    assert c.post(f"{BASE}/admin/dar", headers=adm, json={"email": "nuevo@example.com", "creditos": -2}).json()["creditos"] == 152
    assert any(x["email"] == "nuevo@example.com" for x in c.get(f"{BASE}/admin/cuentas", headers=adm).json()["cuentas"])
    assert c.post(f"{BASE}/admin/dar", headers=adm, json={"email": "mal", "creditos": 1}).status_code in (400, 422)


# ───────────────────────── Actividad, valoración, dataset ─────────────────────────

def _listo(c, q, hdr, monkeypatch, tmp_path, vid=None):
    """Sube, corta y ejecuta el runner con herramientas falsas. Devuelve vid."""
    vid = vid or _subir(c, hdr).json()["id"]
    c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={})
    job = q.get_all()[-1]
    sc = _falsas_estilo(monkeypatch, [], [])
    monkeypatch.setattr(sc, "SilenceCutterTool", _falso_cortador(vid))
    monkeypatch.setattr(svc, "duracion_video", lambda p: 70.0)
    svc.ejecutar(job, lambda m: None, lambda f, m="": None)
    return vid


def _adm():
    return {"Authorization": "Bearer " + make_ticket("jefe@example.com", "", scope="rapido", extra={"rol": "admin"})}


def test_eventos_flujo_completo_y_ttl(rapido, monkeypatch, tmp_path):
    c, q, hdr = rapido
    ttls = []
    r = svc.get_editor_redis()
    r.expire = lambda k, s: ttls.append((k, s)) or True
    vid = _listo(c, q, hdr, monkeypatch, tmp_path)
    tipos = [e["tipo"] for e in svc.leer_eventos(vid)]
    assert tipos == ["subido", "cortar", "listo"]
    listo = svc.leer_eventos(vid)[-1]
    assert listo["n_cortes"] == 2 and listo["segundos_quitados"] == 4.0 and listo["duracion_final_s"] == 70.0
    assert listo["proceso_s"] >= 0 and listo["email"] == EMAIL
    assert any(k.startswith("rapido:eventos:") and s == 180 * 86400 for k, s in ttls)
    # retocar: devolver el corte 0 → evento con lo devuelto
    assert c.post(f"{BASE}/videos/{vid}/retocar", headers=hdr, json={"devueltos": [0]}).status_code == 202
    ev = svc.leer_eventos(vid)[-1]
    assert ev["tipo"] == "retocar" and ev["nuevos_devueltos"] == [0] and ev["re_aplicados"] == []
    # estilo
    f = svc.cargar_ficha(vid); f["estado"] = "listo"; svc.guardar_ficha(f)
    c.post(f"{BASE}/videos/{vid}/estilo", headers=hdr, json={"flecha": {"activo": False}})
    assert svc.leer_eventos(vid)[-1]["tipo"] == "estilo"


def test_registrar_evento_nunca_lanza(rapido, monkeypatch):
    monkeypatch.setattr(svc, "get_editor_redis", lambda: (_ for _ in ()).throw(RuntimeError("redis caído")))
    assert svc.registrar_evento("abc", EMAIL, "subido") is None


def test_valorar_y_calidad(rapido, monkeypatch, tmp_path):
    c, q, hdr = rapido
    vid = _listo(c, q, hdr, monkeypatch, tmp_path)
    assert c.post(f"{BASE}/videos/{vid}/valorar", headers=hdr, json={"nota": 9}).status_code in (400, 422)
    assert c.post(f"{BASE}/videos/{vid}/valorar", headers=hdr, json={"nota": "meh"}).status_code in (400, 422)
    assert c.post(f"{BASE}/videos/{vid}/valorar", headers=hdr,
                  json={"nota": 4, "comentario": "x" * 501}).status_code in (400, 422)
    r = c.post(f"{BASE}/videos/{vid}/valorar", headers=hdr, json={"nota": "mal", "comentario": " cortó mal "})
    assert r.json() == {"ok": True, "nota": 1, "voto": "mal"}
    f = svc.cargar_ficha(vid)
    assert f["nota"] == 1 and f["comentario"] == "cortó mal"
    assert svc.leer_eventos(vid)[-1]["tipo"] == "valoracion"
    assert c.get(f"{BASE}/videos/{vid}", headers=hdr).json()["nota"] == 1
    # otro usuario no puede valorar; vídeo no listo tampoco
    otro = {"Authorization": "Bearer " + make_ticket("otro@example.com", "", scope="rapido")}
    assert c.post(f"{BASE}/videos/{vid}/valorar", headers=otro, json={"nota": 5}).status_code == 404
    nuevo = _subir(c, hdr).json()["id"]
    assert c.post(f"{BASE}/videos/{nuevo}/valorar", headers=hdr, json={"nota": 5}).status_code == 409


def test_formula_calidad():
    base = {"estado": "listo", "n_cortes": 4}
    assert svc.calidad({**base}) == 80
    assert svc.calidad({**base, "devueltos": [0]}) == 65            # -60·1/4
    assert svc.calidad({**base, "devueltos": [0, 1, 2, 3]}) == 20   # -60
    assert svc.calidad({**base, "nota": 1}) == 50
    assert svc.calidad({**base, "nota": 5, "descarga_sin_retocar": True}) == 100  # 80+10+15 → 100
    assert svc.calidad({**base, "descarga_sin_retocar": True}) == 95
    assert svc.calidad({**base, "descarga_sin_retocar": True, "devueltos": [1]}) == 65  # sin bonus si retocó
    assert svc.calidad({"estado": "listo", "n_cortes": 0}) == 80
    assert svc.calidad({"estado": "error"}) is None
    assert svc.nota_valor("bien") == 5 and svc.nota_valor("3") == 3 and svc.nota_valor(True) is None


def test_descarga_registra_y_puntua(rapido, monkeypatch, tmp_path):
    c, q, hdr = rapido
    vid = _listo(c, q, hdr, monkeypatch, tmp_path)
    c.get(f"{BASE}/videos/{vid}/archivo", headers=hdr)  # reproducir no cuenta
    assert svc.cargar_ficha(vid).get("descargas", 0) == 0
    assert c.get(f"{BASE}/videos/{vid}/archivo?descargar=true", headers=hdr).status_code == 200
    f = svc.cargar_ficha(vid)
    assert f["descargas"] == 1 and f["descarga_sin_retocar"] is True
    ev = svc.leer_eventos(vid)[-1]
    assert ev["tipo"] == "descarga" and ev["sin_retocar"] is True
    assert svc.calidad(f) == 95


def test_historial_usuario_y_fecha(rapido, monkeypatch, tmp_path):
    c, q, hdr = rapido
    vid = _listo(c, q, hdr, monkeypatch, tmp_path)
    lista = c.get(f"{BASE}/videos", headers=hdr).json()["videos"]
    assert lista[0]["fecha"][:10] == svc.fecha_dia() and "T" in lista[0]["fecha"]
    h = c.get(f"{BASE}/historial", headers=hdr).json()
    assert h == {"dias": [{"fecha": svc.fecha_dia(), "videos": 1, "minutos_gastados": 1}],
                 "creditos_gastados_total": 1, "movimientos": []}
    # un fallo devuelve créditos y se descuenta del historial
    v2 = _subir(c, hdr).json()["id"]
    svc.ajustar_creditos(EMAIL, 0)
    c.post(f"{BASE}/videos/{v2}/cortar", headers=hdr, json={})
    q.set_status(q.get_all()[-1].id, "failed")
    c.get(f"{BASE}/videos/{v2}", headers=hdr)
    assert c.get(f"{BASE}/historial", headers=hdr).json()["creditos_gastados_total"] == 1
    # solo cuenta el propio usuario
    otro = {"Authorization": "Bearer " + make_ticket("otro@example.com", "", scope="rapido")}
    assert c.get(f"{BASE}/historial", headers=otro).json() == {"dias": [], "creditos_gastados_total": 0, "movimientos": []}


def test_admin_actividad_y_video(rapido, monkeypatch, tmp_path):
    c, q, hdr = rapido
    vid = _listo(c, q, hdr, monkeypatch, tmp_path)
    c.post(f"{BASE}/videos/{vid}/valorar", headers=hdr, json={"nota": 5})
    assert c.get(f"{BASE}/admin/actividad", headers=hdr).status_code == 403
    assert c.get(f"{BASE}/admin/videos/{vid}", headers=hdr).status_code == 403
    a = c.get(f"{BASE}/admin/actividad?dias=3", headers=_adm()).json()
    assert len(a["dias"]) == 3 and a["dias"][-1] == {"fecha": svc.fecha_dia(), "videos": 1, "minutos": 1.6, "usuarios": 1}
    assert a["dias"][0]["videos"] == 0
    v = a["videos"][0]
    assert v["id"] == vid and v["email"] == EMAIL and v["estado"] == "listo" and v["cortes"] == 2
    assert v["devueltos"] == 0 and v["descargado"] is False and v["nota"] == 5 and v["calidad"] == 90
    assert set(v) == {"id", "email", "nombre", "fecha", "duracion_s", "estado", "cortes", "devueltos",
                      "descargado", "nota", "calidad", "coste_api_usd", "proceso_s", "modo", "extras", "extras_s"}
    t = a["totales"]
    assert t["videos"] == 1 and t["listos"] == 1 and t["usuarios"] == 1 and t["errores"] == 0
    assert t["nota_media"] == 5 and t["calidad_media"] == 90 and t["valorados"] == 1 and t["descargados"] == 0
    u = a["usuarios"][0]
    assert u["email"] == EMAIL and u["videos"] == 1 and u["calidad_media"] == 90 and u["creditos"] is not None
    assert u["ultimo"] == v["fecha"]
    d = c.get(f"{BASE}/admin/videos/{vid}", headers=_adm()).json()
    assert d["ficha"]["id"] == vid and d["ficha"]["calidad"] == 90
    assert [e["tipo"] for e in d["eventos"]] == ["subido", "cortar", "listo", "valoracion"]
    assert d["original_url"].endswith(f"/admin/videos/{vid}/archivo?tipo=original")
    # archivos con ticket admin en query
    t = make_ticket("jefe@example.com", "", scope="rapido", extra={"rol": "admin"})
    assert c.get(f"{BASE}/admin/videos/{vid}/archivo?tipo=original&t={t}").content == b"datos"
    assert c.get(f"{BASE}/admin/videos/{vid}/archivo?tipo=resultado&t={t}").status_code == 200
    assert c.get(f"{BASE}/admin/videos/{vid}/archivo?tipo=original", headers=hdr).status_code == 403
    assert c.get(f"{BASE}/admin/videos/zzz", headers=_adm()).status_code == 404


def test_dataset_hardlink_cortes_finales_y_optout(rapido, monkeypatch, tmp_path):
    c, q, hdr = rapido
    ds = tmp_path / "ds"
    monkeypatch.setenv("EDITOR_RAPIDO_DATASET_DIR", str(ds))
    vid = _listo(c, q, hdr, monkeypatch, tmp_path)
    d = ds / vid
    assert (d / "original.mp4").read_bytes() == b"datos"
    assert (d / "original.mp4").stat().st_ino == svc.ruta_original(vid).stat().st_ino  # hardlink
    assert len(json.loads((d / "cortes.json").read_text())) == 2
    assert json.loads((d / "eventos.json").read_text())[-1]["tipo"] == "listo"
    # tras devolver un corte, cortes_finales lo excluye
    f = svc.cargar_ficha(vid); f["devueltos"] = [0]; svc.guardar_ficha(f)
    svc.guardar_dataset(f)
    assert [x["id"] for x in json.loads((d / "cortes_finales.json").read_text())] == [1]
    # borrar el vídeo conserva el original en el dataset
    assert c.delete(f"{BASE}/videos/{vid}", headers=hdr).status_code == 200
    assert (d / "original.mp4").exists() and json.loads((d / "eventos.json").read_text())[-1]["tipo"] == "borrado"
    # opt-out: el ticket lleva no_dataset
    optout = {"Authorization": "Bearer " + make_ticket("opt@example.com", "", scope="rapido", extra={"no_dataset": True})}
    v2 = _subir(c, optout).json()["id"]
    c.post(f"{BASE}/videos/{v2}/cortar", headers=optout, json={})
    job = q.get_all()[-1]
    sc = _falsas_estilo(monkeypatch, [], [])
    monkeypatch.setattr(sc, "SilenceCutterTool", _falso_cortador(v2))
    svc.ejecutar(job, lambda m: None, lambda f, m="": None)
    assert not (ds / v2).exists()


def test_dataset_poco_disco_no_copia(rapido, monkeypatch, tmp_path, caplog):
    c, q, hdr = rapido
    ds = tmp_path / "ds"
    monkeypatch.setenv("EDITOR_RAPIDO_DATASET_DIR", str(ds))
    monkeypatch.setattr(svc.os, "link", lambda a, b: (_ for _ in ()).throw(OSError("otro disco")))
    monkeypatch.setattr(svc.shutil, "disk_usage", lambda p: type("U", (), {"free": 2 * 1024 ** 3})())
    vid = _listo(c, q, hdr, monkeypatch, tmp_path)
    assert not (ds / vid / "original.mp4").exists()
    assert "no se copia" in caplog.text
    # con disco de sobra, copia
    monkeypatch.setattr(svc.shutil, "disk_usage", lambda p: type("U", (), {"free": 50 * 1024 ** 3})())
    svc.guardar_dataset(svc.cargar_ficha(vid))
    assert (ds / vid / "original.mp4").read_bytes() == b"datos"


def test_limpieza_global_no_toca_editor_rapido(rapido, monkeypatch, tmp_path):
    import os
    from src.api import temp_storage as ts
    monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path / "raiz"))
    sub = ts.upload_subdir("editor_rapido") / "abc"
    sub.mkdir()
    f = sub / "original.mp4"; f.write_bytes(b"x")
    otro = ts.upload_subdir("copyright") / "viejo.mp4"; otro.write_bytes(b"x")
    viejo = 1_000_000
    os.utime(f, (viejo, viejo)); os.utime(otro, (viejo, viejo))
    ts.cleanup_expired()
    assert f.exists() and not otro.exists()


def test_corregir_subtitulos_sin_whisper_y_gratis(rapido, monkeypatch):
    c, q, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={})
    llamadas = []

    class FalsoSubs:
        def run(self, *, input_path, output_path, config, ctx):
            llamadas.append(dict(ctx.extras))
            if ctx.extras.get("guardar_palabras"):
                open(ctx.extras["guardar_palabras"], "w").write(json.dumps([
                    {"word": "Hola", "start": 0.1, "end": 0.4},
                    {"word": "nebulas", "start": 0.5, "end": 0.9},
                    {"word": "eh", "start": 1.0, "end": 1.2}]))
            open(output_path, "wb").write(b"mp4+subs")
            return output_path

    import src.editor_auto.tools.silence_cutter as sc
    import src.editor_auto.tools.subs_auto as sa
    monkeypatch.setattr(sa, "SubsAutoTool", FalsoSubs)
    monkeypatch.setattr(sc, "SilenceCutterTool", _falso_cortador(vid))
    monkeypatch.setattr(svc, "duracion_video", lambda p: 70.0)
    assert c.get(f"{BASE}/videos/{vid}/subtitulos", headers=hdr).json() == {"palabras": []}
    assert c.post(f"{BASE}/videos/{vid}/subtitulos", headers=hdr,
                  json={"cambios": [{"i": 0, "texto": "x"}]}).status_code == 409  # aún en cola
    svc.ejecutar(q.get_all()[0], lambda m: None, lambda f, m="": None)
    assert "guardar_palabras" in llamadas[0]
    p = c.get(f"{BASE}/videos/{vid}/subtitulos", headers=hdr).json()["palabras"]
    assert [w["texto"] for w in p] == ["Hola", "nebulas", "eh"] and p[1]["inicio"] == 0.5

    saldo0 = c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"]
    assert c.post(f"{BASE}/videos/{vid}/subtitulos", headers=hdr,
                  json={"cambios": [{"i": 9, "texto": "x"}]}).status_code in (400, 422)
    r = c.post(f"{BASE}/videos/{vid}/subtitulos", headers=hdr,
               json={"cambios": [{"i": 1, "texto": " Nebulabs "}, {"i": 2, "texto": ""}, {"i": 0, "texto": "Hola"}]})
    assert r.status_code == 202 and r.json()["cambiadas"] == 2
    job2 = q.get_all()[-1]
    assert job2.params["modo"] == "estilo"
    svc.ejecutar(job2, lambda m: None, lambda f, m="": None)
    assert [w["word"] for w in llamadas[-1]["palabras"]] == ["Hola", "Nebulabs", ""]
    assert "guardar_palabras" not in llamadas[-1]
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == saldo0
    # sin cambios reales → no encola
    assert c.post(f"{BASE}/videos/{vid}/subtitulos", headers=hdr,
                  json={"cambios": [{"i": 1, "texto": "Nebulabs"}]}).json()["job_id"] is None

    # un corte nuevo (retoque) tira la transcripción vieja: los tiempos cambian
    svc.ruta_palabras(vid).write_text("[]")
    c.post(f"{BASE}/videos/{vid}/retocar", headers=hdr, json={"devueltos": [1]})
    svc.ejecutar(q.get_all()[-1], lambda m: None, lambda f, m="": None)
    assert "guardar_palabras" in llamadas[-1]


def test_subs_auto_con_palabras_dadas_no_transcribe(tmp_path, monkeypatch):
    import src.subtitles_only as so
    from src.editor_auto.tools.base import ToolContext
    from src.editor_auto.tools.subs_auto import SubsAutoTool
    vistos = {}
    monkeypatch.setattr(so, "extract_audio_from_video", lambda *a, **k: (_ for _ in ()).throw(AssertionError("whisper")))
    monkeypatch.setattr(so, "render_subtitles_on_video",
                        lambda inp, words, style, out, **k: vistos.update(words=words) or open(out, "wb").write(b"x"))
    t = SubsAutoTool()
    ctx = ToolContext(user_id="u", user_name="u", job_id="j", temp_folder=str(tmp_path), on_log=lambda m: None, on_progress=lambda f, m="": None,
                      extras={"palabras": [{"word": "Hola", "start": 0, "end": 1}, {"word": " ", "start": 1, "end": 2}]})
    t.run(input_path="in.mp4", output_path=str(tmp_path / "o.mp4"), config=t.default_config(), ctx=ctx)
    assert [w["word"] for w in vistos["words"]] == ["Hola"]


def test_ajustes_color_vacio_y_flecha_inteligente():
    from src.api.routers.editor_auto.rapido import Ajustes
    from src.editor_auto.rapido import servicio as s
    a = Ajustes(subtitulos={"activo": True, "color": "", "fuente": "", "estilo": ""}, flecha={"activo": True, "id": "auto"})
    assert a.subtitulos.color is None and a.subtitulos.fuente is None
    assert s.validar_flecha({"activo": True, "id": "auto"}) == {"activo": True, "id": "auto", "todo_video": False}
    assert s.validar_flecha({"activo": True})["id"] == "auto"


def test_revision_ia_sustituye_sin_mover_tiempos(monkeypatch):
    from src.editor_auto.tools import subs_auto
    from src.editor_auto.api import openai_client
    from src.editor_auto.rapido import servicio as sv

    words = [{"word": "estoy", "start": 0.0, "end": 0.3}, {"word": "bebiendo", "start": 0.3, "end": 0.8},
             {"word": "mi", "start": 0.8, "end": 0.9}, {"word": "vida", "start": 0.9, "end": 1.2}]
    monkeypatch.setattr(openai_client, "analyze_transcript_json", lambda **k: {"cambios": [
        {"i": 1, "bien": "viviendo"}, {"i": 9, "bien": "x"}, {"i": 2, "bien": "una frase demasiado larga"}]})

    class Ctx:
        on_log = staticmethod(lambda m: None)

    assert subs_auto._revisar_palabras(words, Ctx()) == 1
    assert [w["word"] for w in words] == ["estoy", "viviendo", "mi", "vida"]
    assert words[1]["start"] == 0.3 and words[1]["end"] == 0.8
    cfg = sv.config_subtitulos({}, "auto")
    assert cfg["revisar_ia"] and "TikTok Shop" in cfg["keyterms"]
    assert "carrito naranja" in sv.config_flecha({"activo": True, "id": "auto"}, "es")["keyterms"]


def test_preferencias_guardar_y_leer(rapido):
    c, _, hdr = rapido
    assert c.get(f"{BASE}/preferencias", headers=hdr).json() == {"guardado": False, "preferencias": None}
    r = c.put(f"{BASE}/preferencias", headers=hdr, json={
        "ritmo": "sin_pausas", "subtitulos": {"activo": True, "color": ""}, "flecha": {"activo": True}})
    assert r.status_code == 200
    p = c.get(f"{BASE}/preferencias", headers=hdr).json()
    assert p["guardado"] and p["preferencias"]["ritmo"] == "sin_pausas"
    assert p["preferencias"]["flecha"] == {"activo": True, "id": "auto", "todo_video": False}
    assert c.put(f"{BASE}/preferencias", headers=hdr, json={"ritmo": "loco"}).status_code == 422


# ── Webhook de Lemon Squeezy ────────────────────────────────────────────────

def _lemon(c, evento, pid="9001", *, email="compra@x.com", variante="2381430", estado="paid",
           tienda="525143", secreto="s" * 32, firma=None):
    import hashlib, hmac, json as _j
    cuerpo = _j.dumps({"meta": {"event_name": evento, "custom_data": {"email": email}},
                       "data": {"id": pid, "attributes": {"store_id": int(tienda), "status": estado,
                                                           "user_email": "otro@x.com", "total": 900,
                                                           "first_order_item": {"variant_id": int(variante)}}}}).encode()
    f = firma if firma is not None else hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return c.post("/api/v1/editor-auto/rapido/pagos/lemon", content=cuerpo,
                  headers={"X-Signature": f, "Content-Type": "application/json"})


@pytest.fixture
def lemon(rapido, monkeypatch):
    monkeypatch.setenv("EDITOR_LS_WEBHOOK_SECRET", "s" * 32)
    monkeypatch.setenv("EDITOR_LS_TIENDA_ID", "525143")
    monkeypatch.setenv("EDITOR_LS_VARIANTES", '{"2381430":25,"2381434":60,"2381437":150}')
    return rapido[0]


def test_lemon_firma_mala_401_y_sin_secreto_503(lemon, monkeypatch):
    assert _lemon(lemon, "order_created", firma="00" * 32).status_code == 401
    assert _lemon(lemon, "order_created", firma="").status_code == 401
    monkeypatch.delenv("EDITOR_LS_WEBHOOK_SECRET")
    assert _lemon(lemon, "order_created").status_code == 503
    assert svc.get_editor_redis().get_json("rapido:saldo:compra@x.com") is None


def test_lemon_compra_suma_una_vez_y_reembolso_resta(lemon):
    base = svc.saldo("compra@x.com")["creditos"]
    r = _lemon(lemon, "order_created")
    assert r.status_code == 200 and r.json()["accion"] == "sumado"
    assert "email" not in r.json()
    assert svc.saldo("compra@x.com")["creditos"] == base + 25
    assert _lemon(lemon, "order_created").json()["accion"] == "repetido"  # reintento de Lemon
    assert svc.saldo("compra@x.com")["creditos"] == base + 25
    assert _lemon(lemon, "order_refunded").json()["accion"] == "restado"
    assert _lemon(lemon, "order_refunded").json()["accion"] == "repetido"
    assert svc.saldo("compra@x.com")["creditos"] == base
    assert [e["tipo"] for e in svc.leer_eventos("pagos")] == ["compra", "reembolso"]


def test_lemon_ignora_otra_tienda_variante_estado_y_evento(lemon):
    assert _lemon(lemon, "order_created", tienda="1").json()["accion"] == "ignorado"
    assert _lemon(lemon, "order_created", variante="1").json()["accion"] == "ignorado"
    assert _lemon(lemon, "order_created", estado="pending").json()["accion"] == "ignorado"
    assert _lemon(lemon, "subscription_created").json()["accion"] == "ignorado"
    assert _lemon(lemon, "order_refunded", pid="77").json()["accion"] == "ignorado"
    assert _lemon(lemon, "order_created", pid="2", variante="2381437").json()["creditos"] == 150


def test_lemon_creditos_por_nombre_sin_ids(lemon, monkeypatch):
    from src.editor_auto.rapido import lemon as ls
    assert ls.creditos_de_nombre("Pack 60 vídeos", None) == 60
    assert ls.creditos_de_nombre("Editor 2026", "150 créditos") == 150
    assert ls.creditos_de_nombre("Default") is None
    monkeypatch.delenv("EDITOR_LS_VARIANTES")  # ids de live distintos: vale el nombre del pedido
    import hashlib, hmac, json as _j
    cuerpo = _j.dumps({"meta": {"event_name": "order_created", "custom_data": {"email": "n@x.com"}},
                       "data": {"id": "5", "attributes": {"store_id": 525143, "status": "paid",
                                "first_order_item": {"variant_id": 999, "product_name": "60 vídeos",
                                                     "variant_name": "Default"}}}}).encode()
    f = hmac.new(b"s" * 32, cuerpo, hashlib.sha256).hexdigest()
    r = lemon.post("/api/v1/editor-auto/rapido/pagos/lemon", content=cuerpo, headers={"X-Signature": f})
    assert r.json()["creditos"] == 60


def test_lemon_enlace_de_pago(lemon, rapido, monkeypatch):
    from src.editor_auto.rapido import lemon as ls
    c, _, hdr = rapido
    monkeypatch.setenv("EDITOR_PAGOS_PROVEEDOR", "lemon")
    r = c.post("/api/v1/editor-auto/rapido/pagos/enlace", json={"creditos": 60}, headers=hdr)
    assert r.status_code == 503  # sin EDITOR_LS_API_KEY
    pedidos = []
    monkeypatch.setattr(ls, "packs", lambda forzar=False: {60: {"variante": "77"}})
    monkeypatch.setattr(ls, "_pedir", lambda m, ruta, **kw: pedidos.append(kw["cuerpo"]) or
                        {"data": {"attributes": {"url": "https://pago/x"}}})
    r = c.post("/api/v1/editor-auto/rapido/pagos/enlace", json={"creditos": 60}, headers=hdr)
    assert r.status_code == 200 and r.json()["url"] == "https://pago/x"
    d = pedidos[0]["data"]
    assert d["relationships"]["variant"]["data"]["id"] == "77"
    assert d["attributes"]["checkout_data"]["custom"]["email"] == d["attributes"]["checkout_data"]["email"]
    assert c.post("/api/v1/editor-auto/rapido/pagos/enlace", json={"creditos": 25}, headers=hdr).status_code == 503


def test_nueva_version_reusa_original_y_se_corta_aparte(rapido):
    c, q, hdr = rapido
    vid = _subir(c, hdr, "receta.mp4").json()["id"]
    assert c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={"ritmo": "natural"}).status_code == 202
    orig = svc.ruta_original(vid)
    r = c.post(f"{BASE}/videos/{vid}/version", headers=hdr)
    assert r.status_code == 201
    v2 = r.json()
    assert v2["id"] != vid and v2["estado"] == "subido" and v2["nombre"].endswith("· v2")
    o2 = svc.ruta_original(v2["id"])
    assert o2 is not None and o2.read_bytes() == orig.read_bytes()
    # la v1 sigue igual; la v2 se corta con otros ajustes (y cobra)
    assert c.post(f"{BASE}/videos/{v2['id']}/cortar", headers=hdr, json={"ritmo": "sin_pausas"}).json()["saldo"] == 148
    assert svc.cargar_ficha(vid)["ajustes"]["ritmo"] == "natural"
    # desde la v2 sale la v3 (misma raíz)
    assert c.post(f"{BASE}/videos/{v2['id']}/version", headers=hdr).status_code == 201
    v3 = svc.listar_fichas(EMAIL)[0]
    assert v3["n_version"] == 3 and v3["version_de"] == vid
    # borrar la v1 no rompe la v2 (hardlink)
    svc.borrar_ficha(svc.cargar_ficha(vid))
    assert svc.ruta_original(v2["id"]).exists()
    # de otro usuario: 404
    otro = {"Authorization": "Bearer " + make_ticket("x@y.com", "", scope="rapido")}
    assert c.post(f"{BASE}/videos/{v2['id']}/version", headers=otro).status_code == 404


# ── Polar ───────────────────────────────────────────────────────────────────

def _polar(c, *, oid="ord-1", email="p@x.com", pack="60", producto="prod-60", paid=True, tipo="order.paid", estado=None,
           secreto="whsec_" + __import__("base64").b64encode(b"k" * 24).decode(), ts=None, firma=None, wid="msg_1", ref=None):
    import base64, hashlib, hmac, json as _j, time as _t
    cuerpo = _j.dumps({"type": tipo, "data": {"id": oid, "status": estado or ("paid" if paid else "pending"), "paid": paid,
                       "product_id": producto, "metadata": {"email": email, "pack": pack, **({"ref": ref} if ref else {})},
                       "customer": {"email": "otro@x.com"}}}).encode()
    ts = str(int(_t.time())) if ts is None else str(ts)
    if firma is None:
        k = base64.b64decode(secreto.removeprefix("whsec_"))
        firma = "v1," + base64.b64encode(hmac.new(k, f"{wid}.{ts}.".encode() + cuerpo, hashlib.sha256).digest()).decode()
    return c.post(f"{BASE}/pagos/polar/webhook", content=cuerpo, headers={
        "webhook-id": wid, "webhook-timestamp": ts, "webhook-signature": firma})


@pytest.fixture
def polar(rapido, monkeypatch):
    import base64
    monkeypatch.setenv("POLAR_WEBHOOK_SECRET", "whsec_" + base64.b64encode(b"k" * 24).decode())
    for n in ("25", "60", "150"):
        monkeypatch.setenv(f"POLAR_PRODUCT_{n}", f"prod-{n}")
    return rapido[0]


def test_polar_firma_invalida_vieja_y_sin_secreto(polar, monkeypatch):
    import time as _t
    assert _polar(polar, firma="v1,AAAA").status_code == 401
    assert _polar(polar, ts=int(_t.time()) - 400).status_code == 401
    assert svc.get_editor_redis().get_json("rapido:saldo:p@x.com") is None
    monkeypatch.delenv("POLAR_WEBHOOK_SECRET")
    assert _polar(polar).status_code == 503


def test_polar_compra_suma_una_vez(polar):
    base = svc.saldo("p@x.com")["creditos"]
    r = _polar(polar)
    assert r.status_code == 200 and r.json()["accion"] == "sumado" and r.json()["creditos"] == 60
    assert _polar(polar, wid="msg_2").json()["accion"] == "repetido"  # reintento
    assert svc.saldo("p@x.com")["creditos"] == base + 60


def test_polar_reembolso_resta_una_vez(polar):
    base = svc.saldo("p@x.com")["creditos"]
    assert _polar(polar, oid="r1").json()["accion"] == "sumado"
    parcial = _polar(polar, oid="r1", tipo="order.refunded", estado="partially_refunded", wid="m2")
    assert parcial.json()["accion"] == "ignorado"
    r = _polar(polar, oid="r1", tipo="order.refunded", estado="refunded", wid="m3")
    assert r.json()["accion"] == "restado"
    assert _polar(polar, oid="r1", tipo="order.refunded", estado="refunded", wid="m4").json()["accion"] == "repetido"
    assert svc.saldo("p@x.com")["creditos"] == base


def test_polar_secreto_legado(polar, monkeypatch):
    import base64, hashlib, hmac, time as _t
    monkeypatch.setenv("POLAR_WEBHOOK_SECRET", "whsec_legado")
    ts = str(int(_t.time()))
    # el cuerpo lo fija _polar, así que firmamos con la clave legada = bytes del secreto entero
    import json as _j
    cuerpo = _j.dumps({"type": "order.paid", "data": {"id": "o9", "paid": True, "product_id": "prod-25",
                       "metadata": {"email": "l@x.com"}}}).encode()
    f = "v1," + base64.b64encode(hmac.new(b"whsec_legado", f"m.{ts}.".encode() + cuerpo, hashlib.sha256).digest()).decode()
    r = polar.post(f"{BASE}/pagos/polar/webhook", content=cuerpo,
                   headers={"webhook-id": "m", "webhook-timestamp": ts, "webhook-signature": f})
    assert r.json()["creditos"] == 25  # pack deducido del product_id


def test_polar_ignora_evento_no_pagado_y_pack_desconocido(polar):
    assert _polar(polar, tipo="order.refunded").json()["accion"] == "ignorado"
    assert _polar(polar, oid="a", paid=False).json()["accion"] == "ignorado"
    assert _polar(polar, oid="b", pack="999", producto="otro").json()["accion"] == "ignorado"
    assert svc.get_editor_redis().get_json("rapido:saldo:p@x.com") is None


def test_polar_enlace_de_pago(polar, rapido, monkeypatch):
    import requests
    c, _, hdr = rapido
    monkeypatch.setenv("POLAR_SERVER", "sandbox")
    assert c.post(f"{BASE}/pagos/enlace", json={"creditos": 60}, headers=hdr).status_code == 503  # sin token
    monkeypatch.setenv("POLAR_ACCESS_TOKEN", "t")
    vistos = []

    class R:
        status_code = 201
        text = ""
        def json(self): return {"url": "https://polar/x"}
    monkeypatch.setattr(requests, "post", lambda u, **kw: vistos.append((u, kw["json"])) or R())
    r = c.post(f"{BASE}/pagos/enlace", json={"creditos": 60}, headers=hdr)
    assert r.status_code == 200 and r.json()["url"] == "https://polar/x"
    u, cuerpo = vistos[0]
    assert u == "https://sandbox-api.polar.sh/v1/checkouts/" and cuerpo["products"] == ["prod-60"]
    assert cuerpo["metadata"] == {"email": EMAIL, "pack": "60"} and cuerpo["customer_email"] == EMAIL
    assert c.post(f"{BASE}/pagos/enlace", json={"creditos": 7}, headers=hdr).status_code == 503


# ── Referidos ───────────────────────────────────────────────────────────────

def _codigo_de(email):
    return svc.referido(email)["codigo"]


def test_referido_endpoint_codigo_estable_y_enlace(rapido):
    c, _, hdr = rapido
    r = c.get(f"{BASE}/referido", headers=hdr).json()
    assert len(r["codigo"]) == 6 and r["codigo"] == r["codigo"].upper() and not set(r["codigo"]) & set("01OIL")
    assert r["enlace"] == f"https://editor.nebulabsmedia.com/editor?ref={r['codigo']}" and r["ganados"] == 0
    assert c.get(f"{BASE}/referido", headers=hdr).json()["codigo"] == r["codigo"]  # estable
    assert svc.dueno_de_codigo(r["codigo"].lower()) == EMAIL
    assert _codigo_de("otro@x.com") != r["codigo"]


def test_referido_abona_al_dueno_una_vez(polar):
    cod = _codigo_de("dueno@x.com")
    base_d, base_c = svc.saldo("dueno@x.com")["creditos"], svc.saldo("p@x.com")["creditos"]
    assert _polar(polar, ref=cod).json()["accion"] == "sumado"
    assert _polar(polar, wid="msg_2", ref=cod).json()["accion"] == "repetido"  # reintento
    assert svc.saldo("p@x.com")["creditos"] == base_c + 60 + 15  # el comprador gana lo mismo
    assert svc.saldo("dueno@x.com")["creditos"] == base_d + 15  # tabla fija: pack 60 → 15
    assert svc.historial("p@x.com")["movimientos"][0]["texto"] == "Bono por código: +15"
    assert svc.referido("dueno@x.com")["ganados"] == 15
    p = svc.get_editor_redis().get_json(svc._k_pedido("ord-1"))
    assert p["ref_email"] == "dueno@x.com" and p["ref_creditos"] == 15
    assert svc.historial("dueno@x.com")["movimientos"][0]["texto"] == "Referido: +15"


def test_referido_tabla_fija_por_pack(polar):
    cod = _codigo_de("dueno@x.com")
    base = svc.saldo("dueno@x.com")["creditos"]
    _polar(polar, oid="a", pack="25", producto="prod-25", ref=cod)
    _polar(polar, oid="b", pack="150", producto="prod-150", ref=cod, wid="m2")
    assert svc.saldo("dueno@x.com")["creditos"] == base + 5 + 45


def test_referido_devuelto_en_reembolso(polar):
    cod = _codigo_de("dueno@x.com")
    base, base_c = svc.saldo("dueno@x.com")["creditos"], svc.saldo("p@x.com")["creditos"]
    _polar(polar, oid="r1", ref=cod)
    assert _polar(polar, oid="r1", tipo="order.refunded", estado="partially_refunded", wid="m2").json()["accion"] == "ignorado"
    assert svc.saldo("dueno@x.com")["creditos"] == base + 15
    assert _polar(polar, oid="r1", tipo="order.refunded", estado="refunded", wid="m3").json()["accion"] == "restado"
    assert _polar(polar, oid="r1", tipo="order.refunded", estado="refunded", wid="m4").json()["accion"] == "repetido"
    assert svc.saldo("dueno@x.com")["creditos"] == base and svc.referido("dueno@x.com")["ganados"] == 0
    assert svc.historial("dueno@x.com")["movimientos"][0]["texto"] == "Referido devuelto: −15"
    assert svc.saldo("p@x.com")["creditos"] == base_c  # compra y bono devueltos


def test_autorreferido_rechazado_en_webhook(polar):
    cod = _codigo_de("p@x.com")  # el comprador usa su propio código
    base = svc.saldo("p@x.com")["creditos"]
    assert _polar(polar, ref=cod).json()["accion"] == "sumado"
    assert svc.saldo("p@x.com")["creditos"] == base + 60  # solo la compra, sin bonus
    assert "ref_email" not in svc.get_editor_redis().get_json(svc._k_pedido("ord-1"))


def test_codigo_inexistente_en_webhook_no_rompe_la_compra(polar):
    assert _polar(polar, ref="ZZZZZZ").json()["accion"] == "sumado"
    assert "ref_email" not in svc.get_editor_redis().get_json(svc._k_pedido("ord-1"))


def test_enlace_con_referido(polar, rapido, monkeypatch):
    import requests
    c, _, hdr = rapido
    monkeypatch.setenv("POLAR_ACCESS_TOKEN", "t")
    vistos = []

    class R:
        status_code = 201
        text = ""
        def json(self): return {"url": "https://polar/x"}
    monkeypatch.setattr(requests, "post", lambda u, **kw: vistos.append(kw["json"]) or R())
    cod = _codigo_de("dueno@x.com")
    assert c.post(f"{BASE}/pagos/enlace", json={"creditos": 60, "ref": f" {cod.lower()} "}, headers=hdr).status_code == 200
    assert vistos[-1]["metadata"] == {"email": EMAIL, "pack": "60", "ref": cod}
    assert c.post(f"{BASE}/pagos/enlace", json={"creditos": 60}, headers=hdr).status_code == 200
    assert "ref" not in vistos[-1]["metadata"]
    n = len(vistos)
    # inexistente y propio: 400 y sin checkout
    r = c.post(f"{BASE}/pagos/enlace", json={"creditos": 60, "ref": "NOEXIS"}, headers=hdr)
    assert r.status_code == 400 and "no existe" in json.dumps(r.json())
    propio = _codigo_de(EMAIL)
    r = c.post(f"{BASE}/pagos/enlace", json={"creditos": 60, "ref": propio}, headers=hdr)
    assert r.status_code == 400 and "propio" in json.dumps(r.json())
    assert len(vistos) == n


# ───────────────────── Modos y extras (solo admin de momento) ─────────────────────

def test_opciones_modos_y_extras_segun_admin(rapido):
    c, _, hdr = rapido
    o = c.get(f"{BASE}/opciones", headers=hdr).json()
    assert [m["id"] for m in o["modos"]] == ["basico"] and o["extras"] == []
    a = c.get(f"{BASE}/opciones", headers=_adm()).json()
    assert [m["id"] for m in a["modos"]] == ["basico", "replica", "conversacion"]
    rep = a["modos"][1]
    assert rep["solo_admin"] is True and rep["disponible"] is True
    ids = {e["id"]: e for e in a["extras"]}
    assert set(ids) == {"voz", "gancho", "fotos", "nombre_producto"}
    assert all(e["creditos"] == 0.5 and e["solo_admin"] for e in ids.values())
    assert ids["nombre_producto"]["pide_texto"] is True and ids["voz"]["pide_texto"] is False


def test_extras_solo_admin_403_y_validacion(rapido):
    c, q, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    url = f"{BASE}/videos/{vid}/cortar"
    assert c.post(url, headers=hdr, json={"extras": ["voz"]}).status_code == 403
    assert c.post(url, headers=hdr, json={"modo": "replica"}).status_code == 403
    assert c.put(f"{BASE}/preferencias", headers=hdr, json={"extras": ["gancho"]}).status_code == 403
    assert c.post(url, headers=hdr, json={"extras": ["nada"]}).status_code in (400, 422)
    assert c.post(url, headers=hdr, json={"modo": "x"}).status_code in (400, 422)
    assert q.get_all() == [] and c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 150
    adm = _adm()
    va = _subir(c, adm).json()["id"]
    ua = f"{BASE}/videos/{va}/cortar"
    assert c.post(ua, headers=adm, json={"modo": "replica"}).status_code in (400, 422)  # sin enlace
    assert c.post(ua, headers=adm, json={"modo": "replica", "referencia_url": "https://youtube.com/x"}).status_code in (400, 422)
    assert c.post(ua, headers=adm, json={"extras": ["nombre_producto"]}).status_code in (400, 422)  # sin texto
    assert c.post(ua, headers=adm, json={"extras": ["nombre_producto"], "nombre_producto": "x" * 41}).status_code in (400, 422)


def test_admin_extras_precio_y_orden(rapido):
    c, q, _ = rapido
    adm = _adm()
    vid = _subir(c, adm).json()["id"]
    r = c.post(f"{BASE}/videos/{vid}/cortar", headers=adm,
               json={"extras": ["nombre_producto", "voz", "gancho"], "nombre_producto": "  Botella térmica "})
    assert r.status_code == 202
    f = svc.cargar_ficha(vid)
    assert f["creditos_base"] == 1 and f["creditos"] == 2.5 and f["cobrado"] is False
    assert f["ajustes"]["extras"] == ["voz", "gancho", "nombre_producto"]  # orden de aplicación
    assert f["ajustes"]["nombre_producto"] == "Botella térmica" and f["ajustes"]["modo"] == "basico"
    assert c.get(f"{BASE}/saldo", headers=adm).json()["creditos"] == 150  # el admin no paga


def test_runner_con_extras_mide_segundos(rapido, monkeypatch):
    c, q, _ = rapido
    adm = _adm()
    vid = _subir(c, adm).json()["id"]
    c.post(f"{BASE}/videos/{vid}/cortar", headers=adm, json={
        "extras": ["voz", "fotos", "gancho", "nombre_producto"], "nombre_producto": "Lámpara"})
    job = q.get_all()[0]
    subs, flechas, usadas = [], [], []
    sc = _falsas_estilo(monkeypatch, subs, flechas)
    monkeypatch.setattr(sc, "SilenceCutterTool", _falso_cortador(vid))
    monkeypatch.setattr(svc, "duracion_video", lambda p: 70.0)
    palabras = [{"word": f"p{i}", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(100)]
    monkeypatch.setattr(svc, "leer_palabras", lambda v: palabras)

    def falsa(nombre):
        class T:
            def run(self, *, input_path, output_path, config, ctx):
                usadas.append((nombre, config, dict(ctx.extras)))
                open(output_path, "wb").write(open(input_path, "rb").read() + f"+{nombre}".encode())
                return output_path
        return T()
    monkeypatch.setattr(svc, "_tool_extra", falsa)
    from src.editor_auto.api import claude_client
    from src.editor_auto.rapido import extras as ex
    llamadas = []
    monkeypatch.setattr(claude_client, "activo", lambda: True)

    def falso_claude(**kw):
        llamadas.append(kw)
        return {"t0": 10.0, "t1": 12.2, "frase": "esto nadie te lo cuenta", "motivo": "curiosidad"}
    monkeypatch.setattr(claude_client, "analyze_transcript_json", falso_claude)
    prog = []
    svc.ejecutar(job, lambda m: None, lambda f, m="": prog.append(f))
    assert prog == sorted(prog) and prog[-1] == 1.0
    assert [u[0] for u in usadas] == ["audio_clean", "photo_insert", "vip_overlays", "texto_fijo"]
    assert usadas[1][1]["entidades_ia"] == "claude" and usadas[1][2]["palabras"] == palabras
    assert usadas[2][1]["plan_fijo"]["gancho"]["clip"] == {"t0": 10.0, "t1": 12.2}
    assert usadas[3][1]["texto"] == "Lámpara"
    assert llamadas[0]["modelo_forzado"] == ex.MODELO_GANCHO and llamadas[0]["detalle"] == "editor_rapido.gancho"
    assert "fotos_" in subs[0][0]  # los subtítulos van sobre el vídeo con voz y fotos
    assert svc.ruta_resultado(vid).read_bytes() == b"mp4+subs+vip_overlays+texto_fijo"
    assert not list(svc.carpeta(vid).glob("voz_*.mp4")) and not list(svc.carpeta(vid).glob("fotos_*.mp4"))
    f = svc.cargar_ficha(vid)
    assert set(f["extras_s"]) == {"voz", "fotos", "gancho", "nombre_producto"} and f["extras_total_s"]
    assert f["gancho"]["frase"] == "esto nadie te lo cuenta" and f["estado"] == "listo"
    # re-estilizar reusa el gancho elegido (no vuelve a llamar a Claude) y acumula segundos
    assert c.post(f"{BASE}/videos/{vid}/estilo", headers=adm, json={"flecha": {"activo": False}}).status_code == 202
    usadas.clear()
    svc.ejecutar(q.get_all()[-1], lambda m: None, lambda f, m="": None)
    assert len(llamadas) == 1 and "vip_overlays" in [u[0] for u in usadas]
    r = c.get(f"{BASE}/admin/videos/{vid}", headers=adm)
    if r.status_code == 200:
        assert "extras" in json.dumps(r.json())


def test_extra_que_falla_no_rompe(rapido, monkeypatch):
    c, q, _ = rapido
    adm = _adm()
    vid = _subir(c, adm).json()["id"]
    c.post(f"{BASE}/videos/{vid}/cortar", headers=adm, json={"extras": ["voz"]})
    sc = _falsas_estilo(monkeypatch, [], [])
    monkeypatch.setattr(sc, "SilenceCutterTool", _falso_cortador(vid))
    monkeypatch.setattr(svc, "duracion_video", lambda p: 70.0)

    class Rota:
        def run(self, **kw):
            raise RuntimeError("rnnoise roto")
    monkeypatch.setattr(svc, "_tool_extra", lambda n: Rota())
    svc.ejecutar(q.get_all()[0], lambda m: None, lambda f, m="": None)
    v = c.get(f"{BASE}/videos/{vid}", headers=adm).json()
    assert v["estado"] == "listo" and "Mejorar voz" in v["aviso"]
    assert svc.ruta_resultado(vid).read_bytes() == b"mp4+subs"


def test_elegir_gancho_limites(monkeypatch):
    from src.editor_auto.api import claude_client
    from src.editor_auto.rapido import extras as ex
    pal = [{"word": "hola", "start": 0.0, "end": 0.4}]
    monkeypatch.setattr(claude_client, "activo", lambda: False)
    assert ex.elegir_gancho(pal, 30.0, lambda m: None) is None
    monkeypatch.setattr(claude_client, "activo", lambda: True)
    for resp, ok in [({"t0": 1.0, "t1": 3.0}, False), ({"t0": 5.0, "t1": 5.5}, False),
                     ({"t0": 5.0, "t1": 9.0}, False), ({"t0": None, "t1": None}, False),
                     ({"t0": 29.0, "t1": 31.0}, False), ({"t0": 5.0, "t1": 7.0, "frase": "ojo"}, True)]:
        monkeypatch.setattr(claude_client, "analyze_transcript_json", lambda r=resp, **kw: r)
        g = ex.elegir_gancho(pal, 30.0, lambda m: None)
        assert (g is not None) == ok, resp
    monkeypatch.setattr(claude_client, "analyze_transcript_json", lambda **kw: (_ for _ in ()).throw(RuntimeError("x")))
    assert ex.elegir_gancho(pal, 30.0, lambda m: None) is None


def test_replica_admin_encola_con_enlace_y_precio(rapido):
    c, q, _ = rapido
    adm = _adm()
    vid = _subir(c, adm).json()["id"]
    r = c.post(f"{BASE}/videos/{vid}/cortar", headers=adm,
               json={"modo": "replica", "referencia_url": " https://vm.tiktok.com/ZNabc123/ "})
    assert r.status_code == 202
    f = svc.cargar_ficha(vid)
    assert f["ajustes"]["modo"] == "replica" and f["ajustes"]["referencia_url"] == "https://vm.tiktok.com/ZNabc123/"
    assert f["creditos"] == 3 and len(q.get_all()) == 1


def _runner_replica(rapido, monkeypatch, leer):
    c, q, _ = rapido
    adm = _adm()
    vid = _subir(c, adm).json()["id"]
    c.post(f"{BASE}/videos/{vid}/cortar", headers=adm,
           json={"modo": "replica", "referencia_url": "https://www.tiktok.com/@a/video/1"})
    job = q.get_all()[0]
    subs, flechas, usadas = [], [], []
    sc = _falsas_estilo(monkeypatch, subs, flechas)
    monkeypatch.setattr(sc, "SilenceCutterTool", _falso_cortador(vid))
    monkeypatch.setattr(svc, "duracion_video", lambda p: 70.0)
    monkeypatch.setattr(svc, "leer_palabras", lambda v: [{"word": "hola", "start": 0.0, "end": 0.4}])
    monkeypatch.setattr(svc, "_leer_replica", leer)

    def falsa(nombre):
        class T:
            def run(self, *, input_path, output_path, config, ctx):
                usadas.append((nombre, config))
                Path(output_path).write_bytes(Path(input_path).read_bytes())
        return T()
    monkeypatch.setattr(svc, "_tool_extra", falsa)
    svc.ejecutar(job, lambda m: None, lambda f, m: None)
    return vid, usadas


def test_replica_aplica_vip_con_lo_leido(rapido, monkeypatch):
    sacado = {"ritmo_ref": {"rotulos_min": 8}, "zooms": True, "_flujo": {"subs_auto": {}}}
    vid, usadas = _runner_replica(rapido, monkeypatch, lambda f, carp, log: sacado)
    assert [u[0] for u in usadas] == ["vip_overlays"]
    cfg = usadas[0][1]
    assert cfg["zooms"] is True and cfg["fotos_internet"] is False and "_flujo" not in cfg
    f = svc.cargar_ficha(vid)
    assert f["estado"] == "listo" and not f.get("aviso")


def test_replica_sin_viral_sigue_como_basico(rapido, monkeypatch):
    vid, usadas = _runner_replica(rapido, monkeypatch, lambda f, carp, log: None)
    assert usadas == []
    f = svc.cargar_ficha(vid)
    assert f["estado"] == "listo" and "modo Básico" in (f.get("aviso") or "")


def test_leer_replica_falla_descarga_devuelve_none(monkeypatch, tmp_path):
    from src.replicar_viral import servicio as rv

    def rompe(url, destino):
        raise RuntimeError("tikwm caído")
    monkeypatch.setattr(rv, "descargar_tiktok", rompe)
    ficha = {"ajustes": {"referencia_url": "https://www.tiktok.com/@a/video/1"}}
    assert svc._leer_replica(ficha, tmp_path, lambda m: None) is None
    assert "replica" not in ficha


# ───────────── Modo Conversación (17/11/2026) ─────────────

def test_chunks_no_mezclan_hablantes_y_color_fijo():
    from src.subtitles import _chunk_words
    ws = [{"word": w, "start": i * 0.3, "end": i * 0.3 + 0.25, "hablante": h}
          for i, (w, h) in enumerate([("hola", 0), ("qué", 0), ("tal", 1), ("bien", 1)])]
    assert [[w["word"] for w in c] for c in _chunk_words(ws, 3)] == [["hola", "qué"], ["tal", "bien"]]
    sin = [{k: v for k, v in w.items() if k != "hablante"} for w in ws]
    assert len(_chunk_words(sin, 3)) == 2 and len(_chunk_words(sin, 3)[0]) == 3  # monólogo: igual que antes


def test_asignar_palabras_y_colores():
    from src.editor_auto.tools import hablantes as H
    tramos = [[0.0, 2.0, 0], [2.0, 4.0, 1]]
    ws = [{"word": "a", "start": 0.2, "end": 0.5}, {"word": "b", "start": 2.2, "end": 2.5},
          {"word": "c", "start": 2.6, "end": 2.9}, {"word": "d", "start": 9.0, "end": 9.2}]
    assert [w["hablante"] for w in H.asignar_palabras(ws, tramos)] == [0, 1, 1, 1]
    col = svc.palabras_con_colores(ws, tramos, ["#111111"])
    assert [w["color"] for w in col[:2]] == ["#111111", "#FDE047"] and all(w["color_fijo"] for w in col)


def test_conversacion_solo_admin_y_colores_validados(rapido):
    c, q, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    url = f"{BASE}/videos/{vid}/cortar"
    assert c.post(url, headers=hdr, json={"modo": "conversacion"}).status_code == 403
    assert c.get(f"{BASE}/videos/{vid}/voces", headers=hdr).status_code == 403
    va = _subir(c, _adm()).json()["id"]
    ua = f"{BASE}/videos/{va}/cortar"
    assert c.post(ua, headers=_adm(), json={"modo": "conversacion",
                  "subtitulos": {"colores_hablantes": ["rojo"]}}).status_code in (400, 422)
    r = c.post(ua, headers=_adm(), json={"modo": "conversacion",
               "subtitulos": {"colores_hablantes": ["#FFFFFF", "#22C55E"]}})
    assert r.status_code == 202
    f = svc.cargar_ficha(va)
    assert f["ajustes"]["modo"] == "conversacion" and f["creditos"] == 2
    assert f["ajustes"]["subtitulos"]["colores_hablantes"] == ["#FFFFFF", "#22C55E"]
    assert svc.config_cortador(f["ajustes"])["manual_style"] == "conversation"
    assert "manual_style" not in svc.config_cortador({"modo": "basico"})


def test_voces_al_subir_admin(rapido, monkeypatch):
    c, q, hdr = rapido
    from src.editor_auto.tools import hablantes as H
    llamadas = []
    monkeypatch.setattr(H, "detectar_seguro", lambda p, on_log=None: llamadas.append(p) or
                        {"personas": 2, "tramos": [], "metricas": {}})

    class HiloSincrono:
        def __init__(self, target, args, **kw):
            self.t, self.a = target, args

        def start(self):
            self.t(*self.a)
    monkeypatch.setattr(svc.threading, "Thread", HiloSincrono)
    _subir(c, hdr)
    assert not llamadas  # usuario normal: no se gasta CPU
    va = _subir(c, _adm()).json()["id"]
    assert len(llamadas) == 1
    assert c.get(f"{BASE}/videos/{va}/voces", headers=_adm()).json() == {
        "estado": "listo", "personas": 2, "recomendado": "conversacion"}


def test_runner_conversacion_colorea_subs(rapido, monkeypatch):
    c, q, _ = rapido
    va = _subir(c, _adm()).json()["id"]
    c.post(f"{BASE}/videos/{va}/cortar", headers=_adm(), json={"modo": "conversacion"})
    job = q.get_all()[-1]
    subs, flechas = [], []
    sc = _falsas_estilo(monkeypatch, subs, flechas)
    cfgs = []
    monkeypatch.setattr(sc, "SilenceCutterTool", _falso_cortador(va, cfgs))
    palabras = [{"word": "hola", "start": 0.1, "end": 0.4}, {"word": "adiós", "start": 3.0, "end": 3.3}]
    monkeypatch.setattr(svc, "leer_palabras", lambda vid: palabras)
    from src.editor_auto.tools import hablantes as H
    monkeypatch.setattr(H, "detectar_seguro", lambda p, on_log=None:
                        {"personas": 2, "tramos": [[0, 2, 0], [2, 4, 1]], "metricas": {}})
    vistos = []

    class SubsQueMira:
        def run(self, *, input_path, output_path, config, ctx):
            vistos.append(ctx.extras.get("palabras"))
            open(output_path, "wb").write(b"x")
    import src.editor_auto.tools.subs_auto as sa
    monkeypatch.setattr(sa, "SubsAutoTool", SubsQueMira)
    svc.ejecutar(job, lambda m: None, lambda f, m="": None)
    assert cfgs[0]["manual_style"] == "conversation" and cfgs[0]["auto_detect_style"] is False
    assert [w["color"] for w in vistos[0]] == ["#FFFFFF", "#FDE047"]
    assert svc.ruta_hablantes(va).exists()


def test_ajustar_cambio_de_turno_a_la_pausa():
    from src.editor_auto.tools import hablantes as H
    # el cambio visual llega a 2,0 s pero la pausa real está entre 2,6 y 3,0
    ws = [{"word": w, "start": s, "end": e} for w, s, e in
          [("uno", 1.0, 1.4), ("dos", 1.45, 1.9), ("tres", 2.0, 2.6), ("cuatro", 3.0, 3.4)]]
    t = H.ajustar_a_pausas([[0.0, 2.0, 0], [2.0, 5.0, 1]], ws)
    assert t[0][1] == t[1][0] == 2.8
    assert [w["hablante"] for w in H.asignar_palabras(ws, [[0.0, 2.0, 0], [2.0, 5.0, 1]])] == [0, 0, 0, 1]


def _video_sintetico(path, turnos):
    """Fondo fijo y un «personaje» (caja) a la izquierda o la derecha en cada turno de 2 s."""
    import subprocess
    partes = "+".join(f"between(t,{2*i},{2*i+2})*{x}" for i, x in enumerate(turnos))
    d = 2 * len(turnos)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x406080:s=180x320:d={d}:r=10",
                    "-f", "lavfi", "-i", f"color=c=white:s=40x150:d={d}:r=10",
                    "-filter_complex", f"[0][1]overlay=x='{partes}+12*sin(t*5)':y=100:eval=frame", str(path)], check=True)


def test_por_imagen_dos_personajes_y_monologo(tmp_path):
    from src.editor_auto.tools import hablantes as H
    duelo = tmp_path / "duelo.mp4"
    _video_sintetico(duelo, [20, 120, 20, 120, 20, 120, 20])
    r = H._por_imagen(str(duelo), 14.0)
    assert r["personas"] == 2 and len(r["tramos"]) >= 5
    assert r["tramos"][0][2] != r["tramos"][1][2]
    quieto = tmp_path / "solo.mp4"
    _video_sintetico(quieto, [70, 75, 70, 75, 70, 75])
    assert H._por_imagen(str(quieto), 12.0)["personas"] == 1


def test_colores_hablantes_en_preferencias_y_estilo(rapido):
    c, q, hdr = rapido
    sub = {"colores_hablantes": ["#FFFFFF", "#22D3EE"]}
    r = c.put(f"{BASE}/preferencias", headers=_adm(), json={"modo": "conversacion", "subtitulos": sub})
    assert r.status_code == 200, r.text
    got = c.get(f"{BASE}/preferencias", headers=_adm()).json()["preferencias"]
    assert got["subtitulos"]["colores_hablantes"] == ["#FFFFFF", "#22D3EE"]
    vid = _subir(c, _adm()).json()["id"]
    f = svc.cargar_ficha(vid)
    f["estado"] = "listo"
    svc.guardar_ficha(f)
    r = c.post(f"{BASE}/videos/{vid}/estilo", headers=_adm(), json={"subtitulos": {"colores_hablantes": ["#FDE047", "#FFFFFF"]}})
    assert r.status_code == 202, r.text
    assert svc.cargar_ficha(vid)["ajustes"]["subtitulos"]["colores_hablantes"] == ["#FDE047", "#FFFFFF"]


def test_clon_junta_a_los_dos_personajes(tmp_path):
    import subprocess
    import numpy as np
    from src.editor_auto.tools import clon_duo, hablantes as H
    duelo = tmp_path / "duelo.mp4"
    _video_sintetico(duelo, [20, 120, 20, 120, 20, 120, 20])
    r = H._por_imagen(str(duelo), 14.0)
    m = r["metricas"]
    out = clon_duo.componer(str(duelo), str(tmp_path / "clon.mp4"), r["tramos"], m["img_izquierda"], m["img_corte"])
    assert out
    # en mitad de cada turno hay «persona» (blanco) a los DOS lados
    for t in (1.0, 3.0, 5.0):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", out, "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        f = np.frombuffer(raw, np.uint8).reshape(320, 180)
        assert (f[120:240, :90] > 200).mean() > 0.05 and (f[120:240, 90:] > 200).mean() > 0.05, t


def test_flecha_todo_video_y_minimo_5s():
    """Flecha en todo el vídeo o, por palabra clave, mínimo 5 s (y últimos 5 s si no se dice)."""
    from src.editor_auto.rapido import servicio as sv
    from src.editor_auto.tools import sticker_arrow as sa

    assert sv.validar_flecha({"activo": True, "id": "auto", "todo_video": True})["todo_video"] is True
    cfg = sv.config_flecha({"activo": True, "id": "auto", "todo_video": True}, "es")
    assert cfg["full_video"] is True and cfg["fallback_last_seconds"] == 5.0 and cfg["min_window_seconds"] == 5.0

    f = sa.filtro_flecha(windows=[(0.0, 40.0)], position_x_pct=22, position_y_pct=82, scale_width_pct=20,
                         rotation_deg=0, flip_horizontal=False, flip_vertical=False, de_entrada=False,
                         main_w_px=1080, entrada="0:v", sticker="1:v", salida="v")
    assert "overlay" in f and f.endswith("[v]") and "between(t,0.000,40.000)" in f


def test_flecha_posicion_libre():
    """La flecha se puede mover (x/y, centro 0-1) y se guarda; sin x/y va sobre el enlace."""
    from src.editor_auto.rapido import servicio as sv

    assert "y" not in sv.validar_flecha({"activo": True, "id": "auto"})
    d = sv.validar_flecha({"activo": True, "id": "auto", "x": 0.4, "y": 0.6})
    assert d["x"] == 0.4 and d["y"] == 0.6
    assert sv.validar_flecha({"activo": True, "y": 1.5})["y"] == 0.95
    cfg = sv.config_flecha(d, "es")
    assert cfg["position_x_pct"] == 40.0 and cfg["position_y_pct"] == 60.0
    cfg = sv.config_flecha({"activo": True, "id": "auto"}, "es")
    assert cfg["position_x_pct"] == 22.0 and cfg["position_y_pct"] == 82.0
    with pytest.raises(ValueError):
        sv.validar_flecha({"activo": True, "y": "abajo"})


def test_gratis_una_vez_por_buzon(rapido):
    """Alias de Gmail (+x, puntos, googlemail) y correos de usar y tirar no repiten los gratis."""
    assert svc.email_canonico("Pe.Pe+editor@GoogleMail.com") == "pepe@gmail.com"
    assert svc.email_canonico("pe.pe+x@outlook.com") == "pe.pe@outlook.com"
    assert svc.saldo("pepe@gmail.com")["creditos"] == 150
    assert svc.saldo("p.e.p.e+2@gmail.com")["creditos"] == 0
    assert svc.saldo("pepe@gmail.com")["creditos"] == 150  # el primero no pierde nada
    assert svc.saldo("alguien@yopmail.com")["creditos"] == 0
    assert svc.saldo("otra@example.com")["creditos"] == 150
