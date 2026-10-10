from __future__ import annotations

import json

import httpx

from src.multiplataforma import config, publicador
from src.multiplataforma.clients.base import ErrorPublicacion
from src.multiplataforma.clients.instagram import InstagramClient
from src.multiplataforma.clients.pinterest import PinterestClient
from src.multiplataforma.models import CuentaDestino, Publicacion
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo
from tests.multiplataforma.conftest import Grabadora, form

AHORA = 1_800_000_000.0


def _cuenta(**kw) -> CuentaDestino:
    base = dict(slug="casa", nombre="Casa", dueno="ness", ig_user_id="17841", fb_page_id="999",
                threads_user_id="th1", pinterest_board_id="b1", afiliado_amazon_tag="ness-21")
    base.update(kw)
    return cuentas_repo.guardar(CuentaDestino(**base))


def _pub(video, **kw) -> Publicacion:
    base = dict(cuenta="casa", video_path=str(video), titulo="Lámpara", programada_en=AHORA - 10,
                textos={p: f"texto {p}" for p in config.PLATAFORMAS}, enlace="https://www.amazon.es/dp/B0ABC12345?tag=ness-21",
                comentario="enlace aquí")
    base.update(kw)
    p, _ = publicaciones_repo.encolar(Publicacion(**base))
    return p


def _rutas_ok():
    return [
        ("GET", "content_publishing_limit", {"data": [{"quota_usage": 1, "config": {"quota_total": 50}}]}),
        ("POST", "/17841/media_publish", {"id": "ig-media-1"}),
        ("POST", "/17841/media", {"id": "ig-cont-1"}),
        ("GET", "/ig-cont-1", {"status_code": "FINISHED"}),
        ("POST", "/999/video_reels", lambda r: {"video_id": "fbv1", "upload_url": "https://rupload.facebook.com/video-upload/v24.0/fbv1"}
         if "start" in r.content.decode() else {"success": True}),
        ("POST", "rupload.facebook.com/video-upload", {"success": True}),
        ("GET", "/fbv1", {"status": {"video_status": "ready", "publishing_phase": {"status": "complete"}}}),
        ("POST", "/fbv1/comments", {"id": "c1"}),
        ("GET", "threads_publishing_limit", {"data": [{"quota_usage": 0}]}),
        ("POST", "/th1/threads_publish", {"id": "th-post"}),
        ("POST", "/th1/threads", {"id": "th-cont"}),
        ("GET", "/th-cont", {"status": "FINISHED"}),
        ("POST", "/v5/media", {"media_id": "m1", "upload_url": "https://s3.example/up", "upload_parameters": {"key": "k"}}),
        ("POST", "s3.example", httpx.Response(204)),
        ("GET", "/v5/media/m1", {"status": "succeeded"}),
        ("POST", "/v5/pins", {"id": "pin1"}),
    ]


def test_dry_run_sin_tokens_no_toca_la_red(tmp_path, sin_red):
    _cuenta()
    pub = _pub(tmp_path / "v.mp4")
    inf = publicador.publicar_pendientes(AHORA, http=sin_red, sleep=lambda s: None)
    est = publicaciones_repo.get(pub.id).estado
    assert set(est.values()) == {config.ESTADO_SIMULADO}
    pasos = inf["publicaciones"][0]["plataformas"]["instagram"]["pasos"]
    assert any("/17841/media" in p["url"] for p in pasos)
    assert all("access_token" not in (p.get("data") or {}) for p in pasos)
    # segundo tick: sigue sin token → no re-simula, y sigue en la cola
    inf2 = publicador.publicar_pendientes(AHORA + 60, http=sin_red, sleep=lambda s: None)
    assert inf2["publicaciones"][0]["plataformas"]["instagram"]["nota"] == "sigue sin token"
    assert publicaciones_repo.pendientes()


def test_dry_run_global_no_guarda(tmp_path, sin_red):
    _cuenta(tokens={p: "tok" for p in config.PLATAFORMAS})
    pub = _pub(tmp_path / "v.mp4")
    publicador.publicar_pendientes(AHORA, dry_run=True, http=sin_red)
    assert publicaciones_repo.get(pub.id).estado["instagram"] == config.ESTADO_PENDIENTE


def test_publica_todo_y_es_idempotente(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"0" * 1000)
    _cuenta(tokens={p: "tok" for p in config.PLATAFORMAS})
    pub = _pub(video)
    g = Grabadora(_rutas_ok())
    inf = publicador.publicar_pendientes(AHORA, http=g.cliente(), sleep=lambda s: None)
    p = publicaciones_repo.get(pub.id)
    assert set(p.estado.values()) == {config.ESTADO_PUBLICADO}, inf
    assert p.resultados["instagram"]["media_id"] == "ig-media-1"
    assert p.resultados["facebook"]["comentario_id"] == "c1"
    assert p.resultados["pinterest"]["pin_id"] == "pin1"
    assert not publicaciones_repo.pendientes()
    n = len(g.peticiones)
    # otro tick y re-encolar el mismo vídeo: nada nuevo
    publicador.publicar_pendientes(AHORA + 100, http=g.cliente(), sleep=lambda s: None)
    assert len(g.peticiones) == n
    assert publicaciones_repo.envios_24h("casa", "instagram", AHORA) == 1


def test_encolar_dos_veces_misma_clave(tmp_path):
    _cuenta()
    a = _pub(tmp_path / "v.mp4")
    b, creada = publicaciones_repo.encolar(Publicacion(cuenta="casa", video_path=str(tmp_path / "v.mp4")))
    assert not creada and b.id == a.id


def test_limite_diario(tmp_path, sin_red):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    _cuenta(tokens={"instagram": "tok"})
    for i in range(config.LIMITES_24H["instagram"]):
        publicaciones_repo.registrar_envio("casa", "instagram", AHORA - 3600 + i)
    pub = _pub(video, plataformas=["instagram"])
    inf = publicador.publicar_pendientes(AHORA, http=sin_red)
    assert "límite" in inf["publicaciones"][0]["plataformas"]["instagram"]["nota"]
    assert publicaciones_repo.get(pub.id).estado["instagram"] == config.ESTADO_PENDIENTE
    # pasadas 24h vuelve a haber hueco
    assert publicaciones_repo.envios_24h("casa", "instagram", AHORA + 86400) == 0


def test_instagram_reel_de_prueba_trial_params():
    estados = iter(["IN_PROGRESS", "FINISHED"])
    g = Grabadora([
        ("GET", "content_publishing_limit", {"data": [{"quota_usage": 3, "config": {"quota_total": 50}}]}),
        ("POST", "/17841/media_publish", {"id": "m9"}),
        ("POST", "/17841/media", {"id": "c9"}),
        ("GET", "/c9", lambda r: {"status_code": next(estados)}),
    ])
    esperas = []
    res = InstagramClient("tok", http=g.cliente(), sleep=esperas.append, poll_intervalo=5).publicar(
        "17841", caption="hola", video_url="https://x/v.mp4", trial=True, graduacion="SS_PERFORMANCE")
    assert res["media_id"] == "m9" and res["trial"] is True
    crear = next(r for r in g.peticiones if r.method == "POST" and r.url.path.endswith("/17841/media"))
    datos = form(crear)
    assert datos["media_type"] == "REELS"
    assert json.loads(datos["trial_params"]) == {"graduation_strategy": "SS_PERFORMANCE"}
    assert datos["video_url"] == "https://x/v.mp4"
    assert esperas == [5]


def test_instagram_reintento_reutiliza_contenedor():
    g = Grabadora([
        ("GET", "content_publishing_limit", {"data": [{"quota_usage": 0}]}),
        ("POST", "/17841/media_publish", {"id": "m2"}),
        ("GET", "/c-viejo", {"status_code": "FINISHED"}),
    ])
    res = InstagramClient("tok", http=g.cliente()).publicar(
        "17841", caption="x", video_url="https://x/v.mp4", previo={"container_id": "c-viejo"})
    assert res["media_id"] == "m2"
    assert not any(r.url.path.endswith("/17841/media") for r in g.peticiones)



def test_instagram_contenedor_en_error_se_reintenta_con_otro():
    g = Grabadora([
        ("GET", "content_publishing_limit", {"data": [{"quota_usage": 0}]}),
        ("GET", "/c-malo", {"status_code": "ERROR"}),
    ])
    try:
        InstagramClient("tok", http=g.cliente()).publicar(
            "17841", caption="x", video_url="https://x/v.mp4", previo={"container_id": "c-malo"})
    except ErrorPublicacion as e:
        assert e.reintentable and e.parcial["container_id"] == ""
    else:
        raise AssertionError("debía fallar")

def test_pinterest_pin_de_video(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"datos")
    g = Grabadora([
        ("POST", "/v5/media", {"media_id": "m1", "upload_url": "https://s3.example/up",
                               "upload_parameters": {"key": "k", "policy": "p"}}),
        ("POST", "s3.example", httpx.Response(204)),
        ("GET", "/v5/media/m1", {"status": "succeeded"}),
        ("POST", "/v5/pins", {"id": "pin7"}),
    ])
    res = PinterestClient("tok", http=g.cliente()).publicar(
        "b1", titulo="T" * 150, descripcion="desc", enlace="https://www.amazon.es/dp/B0ABC12345?tag=t",
        video_path=str(video), cover_url="https://x/c.jpg")
    assert res["pin_id"] == "pin7"
    pin = json.loads(next(r for r in g.peticiones if r.url.path.endswith("/v5/pins")).content)
    assert pin["board_id"] == "b1" and len(pin["title"]) == 100
    assert pin["link"].startswith("https://www.amazon.es/")
    assert pin["media_source"] == {"source_type": "video_id", "media_id": "m1", "cover_image_url": "https://x/c.jpg"}
    s3 = next(r for r in g.peticiones if "s3.example" in str(r.url))
    assert b'name="key"' in s3.content and b"datos" in s3.content
    assert all(r.headers.get("authorization") == "Bearer tok" for r in g.peticiones if "pinterest" in str(r.url))


def test_error_no_reintentable_y_reintentable(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    _cuenta(tokens={"instagram": "tok"})
    pub = _pub(video, plataformas=["instagram"])
    g = Grabadora([("GET", "content_publishing_limit", httpx.Response(500, json={"error": {"message": "caído"}}))])
    for i in range(config.MAX_INTENTOS):
        publicador.publicar_pendientes(AHORA + i, http=g.cliente())
    p = publicaciones_repo.get(pub.id)
    assert p.estado["instagram"] == config.ESTADO_FALLIDO and "caído" in p.errores["instagram"]
    assert p.intentos["instagram"] == config.MAX_INTENTOS
    assert not publicaciones_repo.pendientes()
