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
    monkeypatch.setenv("EDITOR_RAPIDO_FREE_CREDITS", "150")
    monkeypatch.delenv("API_KEY", raising=False)
    redis = FakeRedis()
    redis.prefix = "editor_auto:"
    monkeypatch.setattr(svc, "get_editor_redis", lambda: redis)
    monkeypatch.setattr(svc, "duracion_video", lambda p: 95.0)  # 95 s → 95 créditos
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


def test_creditos_por_segundo_con_minimo_y_tope():
    # 1 crédito = 1 segundo hacia abajo, mínimo 10 y tope 300
    assert svc.creditos_de(0.2) == 10
    assert svc.creditos_de(9.9) == 10
    assert svc.creditos_de(47.9) == 47
    assert svc.creditos_de(60) == 60
    assert svc.creditos_de(299.5) == 299
    assert svc.creditos_de(600) == 300


def test_saldo_viejo_en_minutos_pasa_a_segundos_una_vez(rapido):
    from src.editor_auto.rapido.servicio import get_editor_redis, _k_saldo
    get_editor_redis().set_json(_k_saldo("viejo@x.com"), {"creditos": 105, "gratis_dados": 5})
    assert svc.saldo("viejo@x.com")["creditos"] == 6300
    assert svc.saldo("viejo@x.com")["creditos"] == 6300  # no vuelve a multiplicar
    assert svc.saldo("nuevo@x.com")["creditos"] == svc.gratis_inicial() == 150


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
    assert r.json()["creditos"] == 95 and r.json()["saldo"] == 150


def test_cortar_cobra_encola_y_progreso(rapido):
    c, q, hdr = rapido
    vid = _subir(c, hdr).json()["id"]
    r = c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr,
               json={"ritmo": "sin_pausas", "formato": "original", "idioma": "es"})
    assert r.status_code == 202 and r.json()["saldo"] == 55
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
    svc.ajustar_creditos(EMAIL, -100)  # quedan 50
    vid = _subir(c, hdr).json()["id"]
    r = c.post(f"{BASE}/videos/{vid}/cortar", headers=hdr, json={})
    assert r.status_code == 402
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 50


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
    assert r.status_code == 200 and r.json()["creditos"] == 95
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
    assert c.get(f"{BASE}/saldo", headers=hdr).json()["creditos"] == 55  # no se devuelven


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
    assert h == {"dias": [{"fecha": svc.fecha_dia(), "videos": 1, "minutos_gastados": 95}],
                 "creditos_gastados_total": 95}
    # un fallo devuelve créditos y se descuenta del historial
    v2 = _subir(c, hdr).json()["id"]
    svc.ajustar_creditos(EMAIL, 0)
    c.post(f"{BASE}/videos/{v2}/cortar", headers=hdr, json={})
    q.set_status(q.get_all()[-1].id, "failed")
    c.get(f"{BASE}/videos/{v2}", headers=hdr)
    assert c.get(f"{BASE}/historial", headers=hdr).json()["creditos_gastados_total"] == 95
    # solo cuenta el propio usuario
    otro = {"Authorization": "Bearer " + make_ticket("otro@example.com", "", scope="rapido")}
    assert c.get(f"{BASE}/historial", headers=otro).json() == {"dias": [], "creditos_gastados_total": 0}


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
                      "descargado", "nota", "calidad"}
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
