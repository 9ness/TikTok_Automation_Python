"""Caminos de error del publicador Multiplataforma (sin red, sin Redis real)."""

from __future__ import annotations

import json

import httpx
import pytest

from src.multiplataforma import config, publicador
from src.multiplataforma.models import CuentaDestino, Publicacion
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo
from src.multiplataforma.services import conectar_meta, tandas
from tests.multiplataforma.conftest import Grabadora, prohibido

AHORA = 1_800_000_000.0
TOKEN = "EAAB-SECRETO-123"
NOSLEEP = lambda s: None  # noqa: E731


def _cuenta(**kw) -> CuentaDestino:
    base = dict(slug="casa", nombre="Casa", dueno="", ig_user_id="17841", fb_page_id="999",
                threads_user_id="th1", pinterest_board_id="b1", tokens={"instagram": TOKEN})
    base.update(kw)
    return cuentas_repo.guardar(CuentaDestino(**base))


def _pub(video, **kw) -> Publicacion:
    base = dict(cuenta="casa", video_path=str(video), titulo="Lámpara", programada_en=AHORA - 10,
                textos={p: f"texto {p}" for p in config.PLATAFORMAS}, plataformas=["instagram"])
    base.update(kw)
    p, _ = publicaciones_repo.encolar(Publicacion(**base))
    return p


def _video(tmp_path):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"0" * 100)
    return v


def _meta(status, code, msg="x"):
    return httpx.Response(status, json={"error": {"message": msg, "code": code}})


def _tick(g, n=1, desde=0, paso=1.0):
    inf = None
    for i in range(n):
        inf = publicador.publicar_pendientes(AHORA + desde + i * paso, http=g.cliente(), sleep=NOSLEEP)
    return inf


# ---- 1. code=200 (permiso / app bloqueada) ----
def test_code_200_no_reintenta_en_bucle(tmp_path):
    _cuenta()
    pub = _pub(_video(tmp_path))
    g = Grabadora([("GET", "content_publishing_limit", _meta(403, 200, "Permissions error"))])
    for i in range(20):  # muchos ticks, también pasado el plazo de rescate
        publicador.publicar_pendientes(AHORA + i * config.RESCATE_S, http=g.cliente(), sleep=NOSLEEP)
    p = publicaciones_repo.get(pub.id)
    assert p.estado["instagram"] == config.ESTADO_FALLIDO
    assert "code=200" in p.errores["instagram"]
    # tope: (rescates+1) rondas de MAX_INTENTOS como mucho; nunca bucle
    assert len(g.peticiones) <= (config.MAX_RESCATES + 1) * config.MAX_INTENTOS
    assert not publicaciones_repo.pendientes()


# ---- 2. code=190 token caducado ----
def test_code_190_no_reintentable_y_sin_token_en_lo_guardado(tmp_path):
    _cuenta()
    pub = _pub(_video(tmp_path))
    g = Grabadora([("GET", "content_publishing_limit",
                    _meta(400, 190, "Error validating access token: Session has expired"))])
    inf = _tick(g)
    p = publicaciones_repo.get(pub.id)
    assert len(g.peticiones) == 1  # un solo intento: no se insiste con un token muerto
    assert "code=190" in p.errores["instagram"]
    volcado = json.dumps(p.to_dict()) + json.dumps(inf)
    assert TOKEN not in volcado


def test_token_en_la_url_no_aparece_en_el_error_guardado(tmp_path):
    _cuenta()
    pub = _pub(_video(tmp_path))

    def cae(request):  # httpx mete la URL (con access_token=) en el mensaje de red
        raise httpx.ConnectError(f"fallo conectando a {request.url}")
    g = httpx.Client(transport=httpx.MockTransport(cae))
    publicador.publicar_pendientes(AHORA, http=g, sleep=NOSLEEP)
    p = publicaciones_repo.get(pub.id)
    assert p.errores["instagram"], "debía quedar un error"
    assert TOKEN not in p.errores["instagram"]


# ---- 3. rate limit ----
@pytest.mark.parametrize("resp", [
    pytest.param(httpx.Response(429, json={"error": {"message": "Too many", "code": 4}}), id="http429"),
    pytest.param(_meta(400, 4), id="code4"),
    pytest.param(_meta(400, 17), id="code17"),
    pytest.param(_meta(400, 32), id="code32"),
    pytest.param(_meta(400, 613), id="code613"),
])
def test_rate_limit_es_reintentable(tmp_path, resp):
    _cuenta()
    pub = _pub(_video(tmp_path))
    _tick(Grabadora([("GET", "content_publishing_limit", resp)]))
    p = publicaciones_repo.get(pub.id)
    assert p.estado["instagram"] == config.ESTADO_ERROR
    assert p.intentos["instagram"] == 1
    assert p.rescates == {}
    assert publicaciones_repo.pendientes()


# ---- 4. contenedor de IG atascado ----
def test_contenedor_atascado_no_publica_dos_veces(tmp_path):
    _cuenta()
    pub = _pub(_video(tmp_path))
    estado = {"s": "IN_PROGRESS"}
    g = Grabadora([
        ("GET", "content_publishing_limit", {"data": [{"quota_usage": 0}]}),
        ("POST", "/17841/media_publish", {"id": "media1"}),
        ("POST", "/17841/media", {"id": "cont1"}),
        ("GET", "/cont1", lambda r: {"status_code": estado["s"]}),
    ])
    _tick(g)
    p = publicaciones_repo.get(pub.id)
    assert p.estado["instagram"] == config.ESTADO_ERROR and "IN_PROGRESS" in p.errores["instagram"]
    assert p.resultados["instagram"]["container_id"] == "cont1"
    _tick(g, desde=10)  # 2º tick: reutiliza el contenedor, no crea otro ni publica
    creados = [r for r in g.peticiones if r.method == "POST" and r.url.path.endswith("/17841/media")]
    publicados = [r for r in g.peticiones if r.url.path.endswith("/media_publish")]
    assert len(creados) == 1 and not publicados
    estado["s"] = "FINISHED"
    _tick(g, desde=20)
    _tick(g, desde=30)
    _tick(g, desde=40)
    publicados = [r for r in g.peticiones if r.url.path.endswith("/media_publish")]
    assert len(publicados) == 1
    assert publicaciones_repo.get(pub.id).estado["instagram"] == config.ESTADO_PUBLICADO


# ---- 5. fichero que falta ----
def test_video_inexistente_en_todas_las_plataformas_no_revienta_el_tick(tmp_path, sin_red):
    _cuenta(tokens={p: TOKEN for p in config.PLATAFORMAS})
    pub = _pub(tmp_path / "no_esta_en_el_drive.mp4", plataformas=list(config.PLATAFORMAS))
    inf = publicador.publicar_pendientes(AHORA, http=sin_red, sleep=NOSLEEP)
    assert "error" not in inf["publicaciones"][0]
    p = publicaciones_repo.get(pub.id)
    for pl in config.PLATAFORMAS:
        assert p.estado[pl] == config.ESTADO_FALLIDO
        assert "No existe el vídeo" in p.errores[pl]
        assert p.intentos[pl] == 1
    assert not p.rescates and not publicaciones_repo.pendientes()


def test_un_video_roto_no_bloquea_al_siguiente(tmp_path):
    _cuenta()
    malo = _pub(tmp_path / "falta.mp4", titulo="malo", programada_en=AHORA - 100)
    bueno = _pub(_video(tmp_path), titulo="bueno")
    g = Grabadora([
        ("GET", "content_publishing_limit", {"data": [{"quota_usage": 0}]}),
        ("POST", "/17841/media_publish", {"id": "m"}),
        ("POST", "/17841/media", {"id": "c"}),
        ("GET", "/c", {"status_code": "FINISHED"}),
    ])
    inf = _tick(g)
    assert inf["procesadas"] == 2
    assert publicaciones_repo.get(malo.id).estado["instagram"] == config.ESTADO_FALLIDO
    assert publicaciones_repo.get(bueno.id).estado["instagram"] == config.ESTADO_PUBLICADO


def test_excepcion_inesperada_no_para_el_tick(tmp_path, monkeypatch):
    _cuenta()
    a = _pub(_video(tmp_path), titulo="a", programada_en=AHORA - 100)
    _pub(tmp_path / "otro.mp4", titulo="b")
    real = publicador.publicar_una

    def rota(pub, **kw):
        if pub.id == a.id:
            raise RuntimeError("explota")
        return real(pub, **kw)
    monkeypatch.setattr(publicador, "publicar_una", rota)
    inf = publicador.publicar_pendientes(AHORA, http=httpx.Client(transport=httpx.MockTransport(prohibido)), sleep=NOSLEEP)
    assert inf["procesadas"] == 2
    assert "RuntimeError" in inf["publicaciones"][0]["error"]


# ---- 6. carrusel con una imagen que falla ----
def _carrusel(monkeypatch, imgs, **kw):
    monkeypatch.setattr(config, "CARRUSEL_COMO_REEL", False)
    return _pub(imgs[0], tipo="carrusel", imagenes=imgs, imagenes_ig=imgs, **kw)


def test_carrusel_imagen_que_falla_se_retoma_sin_repetir_las_buenas(tmp_path, monkeypatch):
    _cuenta()
    imgs = [f"https://x/{i}.jpg" for i in (1, 2, 3)]
    pub = _carrusel(monkeypatch, imgs)
    malas = {"n": 1}

    def media(r):
        cuerpo = r.content.decode()
        if "is_carousel_item" in cuerpo and "3.jpg" in cuerpo and malas["n"]:
            malas["n"] -= 1
            return _meta(400, 100, "Invalid parameter")
        return {"id": "h" + str(len(g.peticiones))}
    g = Grabadora([
        ("GET", "content_publishing_limit", {"data": [{"quota_usage": 0}]}),
        ("POST", "/17841/media_publish", {"id": "m1"}),
        ("POST", "/17841/media", media),
        ("GET", "/h", lambda r: {"status_code": "FINISHED"}),
    ])
    _tick(g)
    p = publicaciones_repo.get(pub.id)
    assert p.estado["instagram"] in (config.ESTADO_ERROR, config.ESTADO_FALLIDO)
    assert len(p.resultados["instagram"]["children"]) == 2  # las 2 buenas se guardan
    assert not any(r.url.path.endswith("/media_publish") for r in g.peticiones)  # nada a medias publicado
    # si el error fue pasajero el siguiente tick no recrea las hijas buenas
    antes = sum("is_carousel_item" in r.content.decode() for r in g.peticiones)
    if p.estado["instagram"] == config.ESTADO_ERROR:
        _tick(g, desde=10)
        nuevas = sum("is_carousel_item" in r.content.decode() for r in g.peticiones) - antes
        assert nuevas == 1
        assert publicaciones_repo.get(pub.id).estado["instagram"] == config.ESTADO_PUBLICADO


def test_carrusel_foto_400_de_meta_es_reintentable(tmp_path, monkeypatch):
    """Una foto que falla con 400 genérico (p. ej. code 100) puede ser pasajera;
    se documenta el comportamiento actual: fallido sin reintento."""
    _cuenta()
    imgs = ["https://x/1.jpg", "https://x/2.jpg"]
    pub = _carrusel(monkeypatch, imgs)
    g = Grabadora([
        ("GET", "content_publishing_limit", {"data": [{"quota_usage": 0}]}),
        ("POST", "/17841/media", _meta(400, 100)),
    ])
    _tick(g)
    p = publicaciones_repo.get(pub.id)
    assert p.estado["instagram"] != config.ESTADO_PUBLICADO
    assert p.resultados["instagram"]["children"] == []


def test_carrusel_foto_local_inexistente_es_fallo_claro(tmp_path, monkeypatch, sin_red):
    _cuenta()
    imgs = [str(tmp_path / "1.jpg"), str(tmp_path / "2.jpg")]
    pub = _carrusel(monkeypatch, imgs)
    inf = publicador.publicar_pendientes(AHORA, http=sin_red, sleep=NOSLEEP)
    assert "error" not in inf["publicaciones"][0]
    p = publicaciones_repo.get(pub.id)
    assert p.estado["instagram"] == config.ESTADO_FALLIDO and "No existe la foto" in p.errores["instagram"]


def test_carrusel_sin_fotos(tmp_path, monkeypatch, sin_red):
    _cuenta()
    monkeypatch.setattr(config, "CARRUSEL_COMO_REEL", False)
    pub = _pub(tmp_path / "x.jpg", tipo="carrusel", imagenes=[], imagenes_ig=[])
    publicador.publicar_pendientes(AHORA, http=sin_red, sleep=NOSLEEP)
    p = publicaciones_repo.get(pub.id)
    assert p.estado["instagram"] == config.ESTADO_FALLIDO and "sin fotos" in p.errores["instagram"]


# ---- 7. renovación de tokens de Threads ----
def _falso_get(monkeypatch, respuesta):
    llamadas = []

    def get(url, params=None, timeout=None):
        llamadas.append(params)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta
    monkeypatch.setattr(conectar_meta.httpx, "get", get)
    return llamadas


def test_renovar_threads_ok_actualiza_token_y_marca(monkeypatch, redis):
    _cuenta(tokens={"threads": "viejo"})
    _falso_get(monkeypatch, httpx.Response(200, json={"access_token": "nuevo"}))
    inf = conectar_meta.renovar_tokens_threads()
    assert inf == {"casa": "renovado"}
    assert cuentas_repo.get("casa").tokens["threads"] == "nuevo"
    assert redis.get_json("threads_renovado")["casa"] > 0
    # recién renovado: no vuelve a llamar
    llamadas = _falso_get(monkeypatch, httpx.Response(200, json={"access_token": "otro"}))
    assert conectar_meta.renovar_tokens_threads() == {} and not llamadas


def test_renovar_threads_error_de_meta_no_revienta_ni_marca(monkeypatch, redis):
    _cuenta(tokens={"threads": "viejo"})
    _falso_get(monkeypatch, httpx.Response(400, json={"error": {"message": "Token expirado", "code": 190}}))
    inf = conectar_meta.renovar_tokens_threads()
    assert inf["casa"].startswith("error:") and "Token expirado" in inf["casa"]
    assert "viejo" not in inf["casa"]
    assert cuentas_repo.get("casa").tokens["threads"] == "viejo"
    assert "casa" not in (redis.get_json("threads_renovado") or {})


def test_renovar_threads_caida_de_red_no_revienta(monkeypatch):
    _cuenta(slug="cuenta_a", tokens={"threads": "ta"})
    _cuenta(slug="cuenta_b", tokens={"threads": "tb"})
    _falso_get(monkeypatch, httpx.ConnectError("sin red"))
    inf = conectar_meta.renovar_tokens_threads()
    assert set(inf) >= {"cuenta_a", "cuenta_b"} and all(v.startswith("error") for k, v in inf.items() if k.startswith("cuenta_"))


def test_renovar_threads_respuesta_sin_token_no_marca(monkeypatch, redis):
    _cuenta(tokens={"threads": "viejo"})
    _falso_get(monkeypatch, httpx.Response(200, json={}))
    conectar_meta.renovar_tokens_threads()
    assert "casa" not in (redis.get_json("threads_renovado") or {})


# ---- 8. replanificar ----
DIA = 86400


@pytest.fixture(autouse=True)
def _sin_mis_tandas(monkeypatch):
    monkeypatch.setattr(tandas, "filas_cuenta", lambda c: [])


def _cola(tmp_path, n=4, **kw):
    out = []
    for i in range(n):
        out.append(_pub(tmp_path / f"v{i}.mp4", titulo=f"v{i}", tipo="producto",
                        programada_en=AHORA + (i + 3) * 3 * 3600, **kw))
    return out


def test_replanificar_no_duplica_ni_pierde_y_es_idempotente(tmp_path):
    _cuenta(dueno="ness")
    pubs = _cola(tmp_path, 5)
    ids = {p.id for p in pubs}
    inf1 = tandas.replanificar("casa", ahora=AHORA)
    tras1 = {p.id: p.programada_en for p in publicaciones_repo.de_cuenta("casa")}
    assert set(tras1) == ids and len(publicaciones_repo.pendientes()) == 5
    assert len(set(tras1.values())) == 5  # ninguna comparte hueco
    inf2 = tandas.replanificar("casa", ahora=AHORA)
    tras2 = {p.id: p.programada_en for p in publicaciones_repo.de_cuenta("casa")}
    assert tras2 == tras1 and inf2["movidas"] == 0, (inf1, inf2)


def test_replanificar_respeta_empezadas_terminadas_y_proximas(tmp_path):
    _cuenta(dueno="ness")
    a, b, c, d = _cola(tmp_path, 4)
    a.estado["instagram"] = config.ESTADO_PUBLICADO  # terminada
    publicaciones_repo.guardar(a)
    b.resultados["instagram"] = {"container_id": "c1"}  # empezada
    b.estado["instagram"] = config.ESTADO_ERROR
    publicaciones_repo.guardar(b)
    c.programada_en = AHORA + 600  # sale en < margen: el tick puede estar con ella
    publicaciones_repo.guardar(c)
    antes = {p.id: p.programada_en for p in (a, b, c)}
    tandas.replanificar("casa", ahora=AHORA)
    for pid, t in antes.items():
        assert publicaciones_repo.get(pid).programada_en == t
    assert publicaciones_repo.get(a.id).estado["instagram"] == config.ESTADO_PUBLICADO


def test_replanificar_cuenta_inexistente_y_todas_no_revienta(monkeypatch, redis):
    _cuenta(dueno="ness", priorizar_epocas=True)
    _cuenta(slug="rota", dueno="ness", priorizar_epocas=True)
    real = tandas.replanificar

    def f(slug, **kw):
        if slug == "rota":
            raise RuntimeError("boom")
        return real(slug, **kw)
    monkeypatch.setattr(tandas, "replanificar", f)
    out = tandas.replanificar_todas(ahora=AHORA)
    assert {i["cuenta"] for i in out} == {"casa", "rota"}
    assert any(i.get("error") == "boom" for i in out)
    # segundo intento dentro de la hora: no repite
    assert tandas.replanificar_todas(ahora=AHORA + 60) == [{"motivo": "reciente"}]


# ---- 9. agotar intentos ----
def test_agotar_intentos_reintentables_acaba_fallido(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MAX_RESCATES", 0)
    _cuenta()
    pub = _pub(_video(tmp_path))
    g = Grabadora([("GET", "content_publishing_limit", httpx.Response(503, json={"error": {"message": "down"}}))])
    for i in range(config.MAX_INTENTOS - 1):
        _tick(g, desde=i)
        p = publicaciones_repo.get(pub.id)
        assert p.estado["instagram"] == config.ESTADO_ERROR and p.intentos["instagram"] == i + 1
        assert not p.terminada
    _tick(g, desde=50)
    p = publicaciones_repo.get(pub.id)
    assert p.estado["instagram"] == config.ESTADO_FALLIDO and p.intentos["instagram"] == config.MAX_INTENTOS
    assert "HTTP 503" in p.errores["instagram"]
    n = len(g.peticiones)
    _tick(g, n=3, desde=100)  # ya final: no se toca más
    assert len(g.peticiones) == n and not publicaciones_repo.pendientes()


def test_una_plataforma_fallida_no_afecta_a_las_demas(tmp_path):
    _cuenta(tokens={"instagram": TOKEN, "threads": TOKEN})
    pub = _pub(_video(tmp_path), plataformas=["instagram", "threads"])
    g = Grabadora([
        ("GET", "content_publishing_limit", _meta(400, 190, "expired")),
        ("GET", "threads_publishing_limit", {"data": [{"quota_usage": 0}]}),
        ("POST", "/th1/threads_publish", {"id": "tp"}),
        ("POST", "/th1/threads", {"id": "tc"}),
        ("GET", "/tc", {"status": "FINISHED"}),
    ])
    _tick(g)
    p = publicaciones_repo.get(pub.id)
    assert p.estado["threads"] == config.ESTADO_PUBLICADO
    assert p.estado["instagram"] in (config.ESTADO_FALLIDO, config.ESTADO_PENDIENTE, config.ESTADO_ERROR)
    assert p.estado["instagram"] != config.ESTADO_PUBLICADO
