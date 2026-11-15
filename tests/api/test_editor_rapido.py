"""Editor rápido: créditos, subida, cobro, cola, retoque y descarga."""

from __future__ import annotations

import io
import json

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
    monkeypatch.setenv("EDITOR_RAPIDO_FREE_CREDITS", "3")
    monkeypatch.delenv("API_KEY", raising=False)
    redis = FakeRedis()
    redis.prefix = "editor_auto:"
    monkeypatch.setattr(svc, "get_editor_redis", lambda: redis)
    monkeypatch.setattr(svc, "duracion_video", lambda p: 95.0)  # 2 min → 2 créditos
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
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 3
    svc.ajustar_creditos(EMAIL, -1)
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 2


def test_creditos_redondeo_hacia_arriba():
    assert svc.creditos_de(59) == 1
    assert svc.creditos_de(60) == 1
    assert svc.creditos_de(60.5) == 2
    assert svc.creditos_de(109) == 2
    assert svc.creditos_de(0.2) == 1


def test_subir_rechaza_formato_y_no_cobra(rapido):
    c, _, hdr = rapido
    r = c.post(f"{BASE}/videos", headers=hdr, files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")})
    assert r.status_code == 422 or r.status_code == 400
    r = _subir(c, hdr)
    assert r.status_code == 201
    assert r.json()["creditos"] == 2 and r.json()["saldo"] == 3


def test_cortar_cobra_encola_y_progreso(rapido):
    c, q, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    r = c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr,
               json={"ritmo": "sin_pausas", "formato": "original", "idioma": "es"})
    assert r.status_code == 202 and r.json()["saldo"] == 1
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
    svc.ajustar_creditos(EMAIL, -2)  # queda 1
    vid = _subir(c, hdr).json()["id"]
    r = c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={})
    assert r.status_code == 402
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 1


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
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 3  # devuelto una sola vez


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
        assert r.json()["creditos"] == 8
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
    assert r.status_code == 200 and r.json()["creditos"] == 2
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
    svc.ajustar_creditos("jefe@example.com", -3)  # sin saldo
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
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 3  # nada cobrado
    body = {"subtitulos": {"estilo": o["estilos"][1]["id"], "color": "#FDE047", "fuente": "anton", "posicion": "arriba"},
            "flecha": {"activo": True, "id": o["flechas"][0]["id"]}}
    assert c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json=body).status_code == 202
    aj = c.get(f"{BASE}/videos/{vid}", headers=hdr).json()["ajustes"]
    assert aj["subtitulos"]["color"] == "#FDE047" and aj["subtitulos"]["posicion"] == "arriba"
    assert aj["flecha"] == {"activo": True, "id": o["flechas"][0]["id"]}


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
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 1  # no se devuelven


def test_admin_cuentas_y_dar(rapido):
    c, _, hdr = rapido
    adm = {"Authorization": "Bearer " + make_ticket("jefe@example.com", "", scope="rapido", extra={"rol": "admin"})}
    assert c.get(f"{BASE}/admin/cuentas", headers=hdr).status_code == 403
    assert c.post(f"{BASE}/admin/dar", headers=hdr, json={"email": EMAIL, "creditos": 5}).status_code == 403
    _subir(c, hdr)  # crea saldo de ana
    cuentas = c.get(f"{BASE}/admin/cuentas", headers=adm).json()["cuentas"]
    ana = next(x for x in cuentas if x["email"] == EMAIL)
    assert ana == {"email": EMAIL, "creditos": 3, "n_videos": 1}
    r = c.post(f"{BASE}/admin/dar", headers=adm, json={"email": "Nuevo@Example.com", "creditos": 4})
    assert r.json() == {"email": "nuevo@example.com", "creditos": 7}
    assert c.post(f"{BASE}/admin/dar", headers=adm, json={"email": "nuevo@example.com", "creditos": -2}).json()["creditos"] == 5
    assert any(x["email"] == "nuevo@example.com" for x in c.get(f"{BASE}/admin/cuentas", headers=adm).json()["cuentas"])
    assert c.post(f"{BASE}/admin/dar", headers=adm, json={"email": "mal", "creditos": 1}).status_code in (400, 422)
