"""#296 enlace corto con contador de clics y #297 «Comenta SÍ» (en seco)."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.exceptions import register_exception_handlers
from src.api.routers.multiplataforma import router_publico
from src.multiplataforma import config, publicador
from src.multiplataforma.models import CuentaDestino, Publicacion
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo
from src.multiplataforma.services import comenta_si, enlace_corto, informe
from tests.multiplataforma.conftest import Grabadora

AHORA = 1_800_000_000.0
SHEIN = "https://es.shein.com/p-123.html?url_from=afiliado"
AMAZON = "https://www.amazon.es/dp/B000000001?tag=viva-21"
NAVEGADOR = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148 Instagram 350.0"


@pytest.fixture
def encendido(monkeypatch):
    monkeypatch.setenv("MULTIPLATAFORMA_ENLACE_CORTO", "1")


def _pub(**kw) -> Publicacion:
    base = dict(cuenta="casa", video_path="/x/v.mp4", enlace=SHEIN, plataformas=["threads", "facebook"],
                textos={"threads": f"Mira esto 👇 {SHEIN}", "facebook": "Mira esto"},
                comentario=f"👉 Lo tienes aquí: {SHEIN}")
    base.update(kw)
    return Publicacion(**base)


def _cliente() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router_publico)
    return TestClient(app, follow_redirects=False)


# ── #296 enlace corto ──────────────────────────────────────────────────────

def test_apagado_por_defecto_no_toca_nada():
    pub = _pub()
    assert enlace_corto.para_envio(pub, "threads") is pub


def test_codigo_determinista_y_distinto_por_red():
    assert enlace_corto.codigo("abc", "threads") == enlace_corto.codigo("abc", "threads")
    assert enlace_corto.codigo("abc", "threads") != enlace_corto.codigo("abc", "facebook")
    assert enlace_corto.CODIGO_RE.match(enlace_corto.codigo("abc", "threads"))


def test_para_envio_cambia_texto_comentario_y_no_la_original(encendido, redis):
    pub = _pub()
    th = enlace_corto.para_envio(pub, "threads")
    fb = enlace_corto.para_envio(pub, "facebook")
    assert SHEIN not in th.textos["threads"] and th.enlace in th.textos["threads"]
    assert fb.comentario.endswith(fb.enlace) and fb.enlace != th.enlace
    assert pub.enlace == SHEIN and SHEIN in pub.textos["threads"]  # la cola guarda el original
    assert th.id == pub.id
    assert redis.data[f"corto:{enlace_corto.codigo(pub.id, 'threads')}"]["url"] == SHEIN


def test_amazon_no_se_acorta_salvo_que_se_pida(encendido, monkeypatch):
    pub = _pub(enlace=AMAZON)
    assert enlace_corto.para_envio(pub, "threads") is pub
    monkeypatch.setenv("MULTIPLATAFORMA_ENLACE_CORTO_AMAZON", "1")
    assert enlace_corto.para_envio(pub, "threads").enlace != AMAZON


def test_dry_run_no_guarda_el_codigo(encendido, redis):
    enlace_corto.para_envio(_pub(), "threads", guardar=False)
    assert not [k for k in redis.data if k.startswith("corto:")]


def test_redireccion_cuenta_personas_y_no_bots(encendido, redis):
    pub = _pub()
    url = enlace_corto.para_envio(pub, "threads").enlace
    ruta = "/api/v1/multiplataforma/links/r/" + url.rsplit("/", 1)[1]
    c = _cliente()
    r = c.get(ruta, headers={"user-agent": NAVEGADOR})
    assert r.status_code == 302 and r.headers["location"] == SHEIN
    c.get(ruta, headers={"user-agent": "facebookexternalhit/1.1"})
    c.head(ruta, headers={"user-agent": NAVEGADOR})
    c.get(ruta, headers={"user-agent": ""})
    assert enlace_corto.clics(pub.id) == {"threads": 1}


def test_redireccion_codigo_raro_o_destino_malo_da_404(encendido, redis):
    c = _cliente()
    assert c.get("/api/v1/multiplataforma/links/r/NOEXISTE").status_code == 404
    assert c.get("/api/v1/multiplataforma/links/r/aaaaaaaa").status_code == 404
    redis.data["corto:bbbbbbbb"] = {"url": "http://inseguro.com", "pid": "x"}
    redis.data["corto:cccccccc"] = {"url": "https://bit.ly/x", "pid": "x"}
    assert c.get("/api/v1/multiplataforma/links/r/bbbbbbbb").status_code == 404
    assert c.get("/api/v1/multiplataforma/links/r/cccccccc").status_code == 404


def test_publicador_envia_el_corto_a_threads(encendido, redis, monkeypatch):
    cuentas_repo.guardar(CuentaDestino(slug="casa", threads_user_id="th1", tokens={"threads": "T"}))
    pub, _ = publicaciones_repo.encolar(_pub(video_path="https://x/v.mp4", plataformas=["threads"],
                                             programada_en=AHORA - 1))
    enviado = {}

    def falso(self, destino, *, texto, video_url, previo):
        enviado["texto"] = texto
        return {"post_id": "p1"}

    monkeypatch.setattr(publicador.ThreadsClient, "publicar", falso)
    publicador.publicar_pendientes(AHORA, sleep=lambda s: None)
    corto = enlace_corto.url_corta(enlace_corto.codigo(pub.id, "threads"))
    assert corto in enviado["texto"] and SHEIN not in enviado["texto"]
    guardada = publicaciones_repo.get(pub.id)
    assert guardada.estado["threads"] == config.ESTADO_PUBLICADO
    assert guardada.enlace == SHEIN and SHEIN in guardada.textos["threads"]


def test_informe_saca_los_clics():
    fotos = [("2027-01-07", {"cuentas": {"viva_shop": {"publicaciones": [
        {"pid": "a", "tipo": "producto", "titulo": "Botas", "fecha": "2027-01-06", "ts": AHORA - 3600,
         "clics": {"threads": 3, "facebook": 2}},
        {"pid": "b", "tipo": "producto", "titulo": "Bolso", "fecha": "2027-01-06", "ts": AHORA - 3600},
    ]}}})]
    md = informe.generar(fotos, ahora=AHORA)
    assert "Clics en el enlace" in md and "| viva_shop | threads | 3 |" in md
    sin = informe.generar([("2027-01-07", {"cuentas": {"viva_shop": {"publicaciones": [
        {"pid": "b", "tipo": "producto", "fecha": "2027-01-06", "ts": AHORA - 3600}]}}})], ahora=AHORA)
    assert "Clics en el enlace" not in sin


# ── #297 «Comenta SÍ» ──────────────────────────────────────────────────────

@pytest.mark.parametrize("texto", ["Sí", "si", "SIIII 🙌", "sí!!", "Si por favor", "sí porfa 😍", "yes please",
                                   "Siii quiero", " sí. "])
def test_es_si(texto):
    assert comenta_si.es_si(texto)


@pytest.mark.parametrize("texto", ["", "no", "sin duda es caro", "si lo compro me lo devuelven?", "s",
                                   "simplemente precioso", "a mi si me gusta", "sí sí sí sí sí sí sí"])
def test_no_es_si(texto):
    assert not comenta_si.es_si(texto)


def _montar(n_reels=1, **pub_kw):
    c = cuentas_repo.guardar(CuentaDestino(slug="casa", ig_user_id="17841", tokens={"instagram": "TOK"}))
    pubs = []
    for i in range(n_reels):
        base = dict(cuenta="casa", video_path=f"/x/v{i}.mp4", enlace=SHEIN, plataformas=["instagram"],
                    programada_en=AHORA - 3600, estado={"instagram": config.ESTADO_PUBLICADO},
                    resultados={"instagram": {"media_id": f"m{i}"}})
        base.update(pub_kw)
        p, _ = publicaciones_repo.encolar(Publicacion(**base))
        pubs.append(p)
    return c, pubs


def _comentarios(*lista):
    return {"data": [{"id": cid, "text": t, "username": u} for cid, t, u in lista]}


def test_en_seco_anota_y_no_manda(redis):
    c, (pub,) = _montar()
    g = Grabadora([("GET", "/m0/comments", _comentarios(("c1", "Sí!!", "ana"), ("c2", "qué bonito", "eva"),
                                                         ("c3", "si porfa", "ana")))])
    inf = comenta_si.procesar_cuenta(c, ahora=AHORA, http=g.cliente())
    assert inf["modo"] == "seco" and inf["si"] == 2 and inf["repetidos"] == 1
    assert [m["comentario"] for m in inf["mandados"]] == ["c1"]
    assert all(p.method == "GET" for p in g.peticiones)  # nada de POST /messages
    seco = next(v for k, v in redis.data.items() if k.startswith("comenta_si:seco:"))
    assert seco[0]["usuario"] == "ana" and SHEIN in seco[0]["mensaje"]
    # Segundo pase: el mismo comentario no se repite.
    inf2 = comenta_si.procesar_cuenta(c, ahora=AHORA + 60, http=g.cliente())
    assert inf2["mandados"] == [] and inf2["repetidos"] == 2


def test_tope_por_hora(redis, monkeypatch):
    monkeypatch.setattr(config, "COMENTA_SI_TOPE_HORA", 2)
    c, _ = _montar()
    g = Grabadora([("GET", "/m0/comments", _comentarios(*[(f"c{i}", "sí", f"u{i}") for i in range(5)]))])
    inf = comenta_si.procesar_cuenta(c, ahora=AHORA, http=g.cliente())
    assert len(inf["mandados"]) == 2 and inf["tope"] == 3


def test_envio_real_manda_privado_y_si_falla_reintenta(redis):
    c, _ = _montar()
    fallar = {"si": True}

    def mensajes(req):
        if fallar["si"]:
            return httpx.Response(500, json={"error": {"message": "x", "code": 2}})
        return {"recipient_id": "r", "message_id": "mid"}

    g = Grabadora([("GET", "/m0/comments", _comentarios(("c1", "sí", "ana"))),
                   ("POST", "/17841/messages", mensajes)])
    inf = comenta_si.procesar_cuenta(c, ahora=AHORA, enviar=True, http=g.cliente())
    assert inf["mandados"] == [] and inf["errores"]
    fallar["si"] = False
    inf = comenta_si.procesar_cuenta(c, ahora=AHORA + 60, enviar=True, http=g.cliente())
    assert [m["comentario"] for m in inf["mandados"]] == ["c1"]
    post = [p for p in g.peticiones if p.method == "POST"][-1]
    assert b'"comment_id":"c1"' in post.content.replace(b" ", b"")


def test_error_definitivo_no_se_reintenta(redis):
    c, _ = _montar()
    g = Grabadora([("GET", "/m0/comments", _comentarios(("c1", "sí", "ana"))),
                   ("POST", "/17841/messages", httpx.Response(400, json={"error": {"message": "x", "code": 10}}))])
    comenta_si.procesar_cuenta(c, ahora=AHORA, enviar=True, http=g.cliente())
    inf = comenta_si.procesar_cuenta(c, ahora=AHORA + 60, enviar=True, http=g.cliente())
    assert inf["repetidos"] == 1 and len([p for p in g.peticiones if p.method == "POST"]) == 1


def test_envio_sin_redis_no_manda(redis, monkeypatch):
    c, _ = _montar()
    monkeypatch.setattr(redis, "is_available", lambda: False)
    g = Grabadora([])
    inf = comenta_si.procesar_cuenta(c, ahora=AHORA, enviar=True, http=g.cliente())
    assert inf["errores"] and g.peticiones == []


def test_error_con_token_en_url_no_lo_saca(redis):
    c, _ = _montar()
    pag2 = "https://graph.facebook.com/v21.0/m0/comments?access_token=SECRETO123&after=x"
    g = Grabadora([("GET", "/m0/comments", lambda req: (
        httpx.Response(500, json={"error": {"message": "x"}}) if "after=" in str(req.url)
        else {"data": [], "paging": {"next": pag2}}))])
    inf = comenta_si.procesar_cuenta(c, ahora=AHORA, http=g.cliente())
    assert inf["errores"] and "SECRETO123" not in str(inf["errores"])


def test_error_al_leer_comentarios_no_para_el_resto(redis):
    c, _ = _montar(n_reels=2)
    g = Grabadora([("GET", "/m0/comments", httpx.Response(403, json={"error": {"message": "perm", "code": 10}})),
                   ("GET", "/m1/comments", _comentarios(("c9", "sí", "eva")))])
    inf = comenta_si.procesar_cuenta(c, ahora=AHORA, http=g.cliente())
    assert len(inf["errores"]) == 1 and [m["comentario"] for m in inf["mandados"]] == ["c9"]


def test_solo_reels_recientes_publicados_con_enlace(redis):
    c, _ = _montar()
    publicaciones_repo.encolar(Publicacion(cuenta="casa", video_path="/x/viejo.mp4", enlace=SHEIN,
                                           programada_en=AHORA - 30 * 86400, estado={"instagram": "publicado"},
                                           resultados={"instagram": {"media_id": "viejo"}}, plataformas=["instagram"]))
    publicaciones_repo.encolar(Publicacion(cuenta="casa", video_path="/x/sin.mp4", enlace="",
                                           programada_en=AHORA - 60, estado={"instagram": "publicado"},
                                           resultados={"instagram": {"media_id": "sin"}}, plataformas=["instagram"]))
    assert [p.resultados["instagram"]["media_id"] for p in comenta_si.candidatas("casa", AHORA)] == ["m0"]


def test_sin_token_no_toca_la_red(redis):
    c = cuentas_repo.guardar(CuentaDestino(slug="casa", ig_user_id="17841"))
    inf = comenta_si.procesar_cuenta(c, ahora=AHORA, http=Grabadora([]).cliente())
    assert inf["errores"] == ["sin token o ig_user_id de Instagram"]
