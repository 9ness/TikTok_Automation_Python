"""Carruseles de fotos (Replicar carrusel) → IG/FB/Threads/Pinterest."""

from __future__ import annotations

import datetime as dt
import json
import zoneinfo

import pytest
from PIL import Image

from src.multiplataforma import config, publicador
from src.multiplataforma.models import CuentaDestino
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo
from src.multiplataforma.services import carruseles
from tests.multiplataforma.conftest import Grabadora, form

TZ = zoneinfo.ZoneInfo("Europe/Madrid")
AHORA = dt.datetime(2026, 10, 9, 12, 0, tzinfo=TZ).timestamp()


@pytest.fixture()
def replica(tmp_path, monkeypatch):
    """Un carrusel de 3 diapositivas (la 2 sin texto) con sus fotos en disco."""
    monkeypatch.setenv("MULTIPLATAFORMA_DRIVE_ROOT", str(tmp_path / "mp"))
    monkeypatch.setenv("AUTH_COOKIE_KEY", "k")
    from src.replicar_viral import carrusel

    fotos = tmp_path / "rc"
    rutas = {}
    for n, tipo in ((1, "txt"), (2, "base"), (3, "txt")):
        p = fotos / tipo / f"{n:02d}.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (900, 1600), (200, 50, 50)).save(p)  # 9:16
        rutas[(n, tipo)] = p
    doc = {"id": "abc123", "usuario": "ness", "tipo": "carrusel", "url": "u",
           "producto": {"titulo": "Paraguas\nautomático", "tienda": "Tienda X"},
           "caption": "Un paraguas que se abre solo. Lo tienes en el carrito naranja.",
           "hashtags": ["#paraguas", "#TikTokShop", "#lluvia"],
           "diapositivas": [{"n": 1, "texto": "hola"}, {"n": 2, "texto": ""}, {"n": 3, "texto": "fin"}],
           "musica": {"meta": {"estilo": "lofi_otono", "pista": "Slow Walk"}}}
    monkeypatch.setattr(carrusel, "ver", lambda u, i: doc)
    monkeypatch.setattr(carrusel, "ruta_foto", lambda u, i, n, t: rutas.get((n, t)))
    from src.mis_tandas import fuentes

    monkeypatch.setattr(fuentes, "todas", lambda u: ([], [], []))
    return doc


@pytest.fixture()
def cuenta():
    return cuentas_repo.guardar(CuentaDestino(slug="viva_shop", dueno="ness", afiliado_amazon_tag="viva-21",
                                              ig_user_id="ig1", fb_page_id="pg1", threads_user_id="th1"))


def test_horas_y_tipo_por_defecto():
    assert config.HORAS_DEFAULT["carrusel"] == ["17:00"]
    assert "carrusel" in config.TIPOS


def test_encolar_sin_enlace_no_va(replica, cuenta):
    with pytest.raises(carruseles.ErrorCarrusel, match="no tiene enlace"):
        carruseles.encolar("viva_shop", "abc123", ahora=AHORA)


def test_encolar_copia_fotos_ig_45_texto_y_hora(replica, cuenta):
    inf = carruseles.encolar("viva_shop", "abc123", asin="B0ABC12345", desde="2026-10-10", ahora=AHORA)
    pub = publicaciones_repo.get(inf["publicacion"]["id"])
    assert pub.tipo == "carrusel" and len(pub.imagenes) == 3 and len(pub.imagenes_ig) == 3
    with Image.open(pub.imagenes_ig[0]) as im:
        assert im.size == config.IG_LIENZO_CARRUSEL
    assert pub.enlace == "https://www.amazon.es/dp/B0ABC12345?tag=viva-21"
    ig = pub.textos["instagram"]
    assert "carrito" not in ig and "TikTok" not in ig and "#paraguas" in ig and "#amazonfinds" in ig
    assert "B0ABC12345" in pub.comentario
    hora = dt.datetime.fromtimestamp(pub.programada_en, TZ)
    assert hora.date() == dt.date(2026, 10, 10) and abs(hora.hour * 60 + hora.minute - 17 * 60) <= 4
    assert inf["musica_sugerida"]["pista"] == "Slow Walk"
    # idempotente; el enlace ya guardado vale para el siguiente
    again = carruseles.encolar("viva_shop", "abc123", ahora=AHORA)
    assert again["creada"] is False and len(publicaciones_repo.de_cuenta("viva_shop")) == 1


def test_uno_al_dia(replica, cuenta, monkeypatch):
    carruseles.encolar("viva_shop", "abc123", asin="B0ABC12345", desde="2026-10-10", ahora=AHORA)
    replica["id"] = "def456"
    inf = carruseles.encolar("viva_shop", "def456", desde="2026-10-10", ahora=AHORA)
    assert dt.datetime.fromtimestamp(inf["publicacion"]["programada_en"], TZ).date() == dt.date(2026, 10, 11)


def test_falta_texto_quemado(replica, cuenta, monkeypatch):
    from src.replicar_viral import carrusel

    original = carrusel.ruta_foto
    monkeypatch.setattr(carrusel, "ruta_foto", lambda u, i, n, t: None if (n, t) == (3, "txt") else original(u, i, n, t))
    with pytest.raises(carruseles.ErrorCarrusel, match=r"\[3\]"):
        carruseles.encolar("viva_shop", "abc123", asin="B0ABC12345", ahora=AHORA)


def test_publica_carrusel_en_las_tres(replica, cuenta):
    cuentas_repo.set_tokens("viva_shop", {"facebook": "tok", "threads": "tok"})
    inf = carruseles.encolar("viva_shop", "abc123", asin="B0ABC12345", ahora=AHORA,
                             plataformas=["instagram", "facebook", "threads"])
    pub = publicaciones_repo.get(inf["publicacion"]["id"])
    n = {"ig": 0, "th": 0, "fb": 0}

    def item(clave):
        def f(r):
            n[clave] += 1
            return {"id": f"{clave}-{n[clave]}"}
        return f

    def ig_media(r):
        d = form(r)
        return {"id": "ig-car"} if d.get("media_type") == "CAROUSEL" else item("ig")(r)

    def th_media(r):
        d = form(r)
        return {"id": "th-car"} if d.get("media_type") == "CAROUSEL" else item("th")(r)

    g = Grabadora([
        ("GET", "content_publishing_limit", {"data": [{"quota_usage": 0}]}),
        ("POST", "/ig1/media_publish", {"id": "ig-post"}),
        ("POST", "/ig1/media", ig_media),
        ("GET", "/ig-", {"status_code": "FINISHED"}),
        ("POST", "/pg1/photos", item("fb")),
        ("POST", "/pg1/feed", {"id": "pg1_post"}),
        ("POST", "/pg1_post/comments", {"id": "c1"}),
        ("GET", "threads_publishing_limit", {"data": [{"quota_usage": 0}]}),
        ("POST", "/th1/threads_publish", {"id": "th-post"}),
        ("POST", "/th1/threads", th_media),
        ("GET", "/th-", {"status": "FINISHED"}),
    ])
    rep = publicador.publicar_pendientes(pub.programada_en + 1, http=g.cliente(), sleep=lambda s: None)
    est = publicaciones_repo.get(pub.id).estado
    assert est == {p: config.ESTADO_PUBLICADO for p in ("instagram", "facebook", "threads")}, rep
    car = next(form(r) for r in g.peticiones if "/ig1/media" in str(r.url) and "CAROUSEL" in r.content.decode())
    assert car["children"] == "ig-1,ig-2,ig-3"
    items = [form(r) for r in g.peticiones if str(r.url).endswith("/ig1/media") and "is_carousel_item" in r.content.decode()]
    assert all("/archivo/" in i["image_url"] for i in items)
    feed = form(next(r for r in g.peticiones if "/pg1/feed" in str(r.url)))
    assert json.loads(feed["attached_media[2]"]) == {"media_fbid": "fb-3"}
    thc = next(form(r) for r in g.peticiones if "/th1/threads" in str(r.url) and "CAROUSEL" in r.content.decode())
    assert thc["children"] == "th-1,th-2,th-3" and "amazon.es" in thc["text"]


def test_dry_run_sin_tokens(replica, cuenta, sin_red):
    inf = carruseles.encolar("viva_shop", "abc123", asin="B0ABC12345", ahora=AHORA)
    pub = publicaciones_repo.get(inf["publicacion"]["id"])
    publicador.publicar_pendientes(pub.programada_en + 1, http=sin_red, sleep=lambda s: None)
    assert set(publicaciones_repo.get(pub.id).estado.values()) == {config.ESTADO_SIMULADO}
