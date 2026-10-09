from __future__ import annotations

import datetime as dt
import json
import zoneinfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.exceptions import register_exception_handlers
from src.api.routers.multiplataforma import router_publico
from src.multiplataforma import config, publicador
from src.multiplataforma.models import CuentaDestino
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo
from src.multiplataforma.services import ingesta, video_url

TZ = zoneinfo.ZoneInfo("Europe/Madrid")
# 8 oct 2026 10:00 en Madrid
AHORA = dt.datetime(2026, 10, 8, 10, 0, tzinfo=TZ).timestamp()


@pytest.fixture()
def raiz(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTIPLATAFORMA_DRIVE_ROOT", str(tmp_path / "Multiplataforma"))
    return tmp_path / "Multiplataforma"


def _cuenta(**kw) -> CuentaDestino:
    base = dict(slug="casa", nombre="Casa", afiliado_amazon_tag="ness-21")
    base.update(kw)
    return cuentas_repo.guardar(CuentaDestino(**base))


def _video(raiz, carpeta, nombre, slug="casa"):
    d = raiz / slug / carpeta
    d.mkdir(parents=True, exist_ok=True)
    f = d / nombre
    f.write_bytes(b"video")
    return f


def _local(ts):
    return dt.datetime.fromtimestamp(ts, TZ).strftime("%m-%d %H:%M")


def test_crea_carpetas(raiz):
    ingesta.asegurar_carpetas("casa")
    for c in ("viralizacion", "producto"):
        assert (raiz / "casa" / c / "publicados").is_dir()


def test_ingesta_sin_duplicar_y_orden_natural(raiz):
    _cuenta()
    for n in ("10.mp4", "2.mp4", "1.MOV", "nota.pdf"):
        _video(raiz, "viralizacion", n)
    inf = ingesta.ingestar("casa", AHORA)
    assert [e["video"].rsplit("/", 1)[1] for e in inf["encoladas"]] == ["1.MOV", "2.mp4", "10.mp4"]
    assert all(e["tipo"] == "prueba_viral" for e in inf["encoladas"])
    # segunda pasada: nada nuevo
    assert ingesta.ingestar("casa", AHORA)["encoladas"] == []
    assert len(publicaciones_repo.pendientes()) == 3


def test_reparto_por_dias_y_horas(raiz, monkeypatch):
    monkeypatch.setattr(config, "DESFASE_MAX_MIN", 0)
    _cuenta(ritmo={"prueba_viral": 2, "producto": 1}, horas={"prueba_viral": ["19:00", "09:00"], "producto": ["13:00"]})
    for n in ("a.mp4", "b.mp4", "c.mp4"):
        _video(raiz, "viralizacion", n)
    for n in ("p1.mp4", "p2.mp4"):
        _video(raiz, "producto", n)
    inf = ingesta.ingestar("casa", AHORA)
    por = {e["video"].rsplit("/", 1)[1]: _local(e["programada_en"]) for e in inf["encoladas"]}
    # hoy a las 09:00 ya pasó (son las 10:00) → hoy 19:00, mañana 09:00 y 19:00
    assert por["a.mp4"] == "10-08 19:00"
    assert por["b.mp4"] == "10-09 09:00"
    assert por["c.mp4"] == "10-09 19:00"
    assert por["p1.mp4"] == "10-08 13:00" and por["p2.mp4"] == "10-09 13:00"
    # un vídeo nuevo continúa tras la última programada
    _video(raiz, "viralizacion", "d.mp4")
    e = ingesta.ingestar("casa", AHORA)["encoladas"]
    assert [_local(x["programada_en"]) for x in e] == ["10-10 09:00"]


def test_defaults_y_ritmo_mayor_que_horas():
    c = CuentaDestino(slug="x")
    assert c.ritmo == {"prueba_viral": 1, "producto": 1, "carrusel": 1}
    assert c.horas["prueba_viral"] == ["19:00"] and c.horas["producto"] == ["13:00"]
    assert ingesta.horas_del_dia(3, ["19:00"]) == [(19, 0), (20, 0), (21, 0)]
    assert ingesta.horas_del_dia(0, ["19:00"]) == []


def test_ritmo_cero_no_ingesta(raiz):
    _cuenta(ritmo={"prueba_viral": 0, "producto": 1})
    _video(raiz, "viralizacion", "a.mp4")
    assert ingesta.ingestar("casa", AHORA)["encoladas"] == []


def test_metadatos_txt_y_json(raiz):
    _cuenta()
    f = _video(raiz, "producto", "01_lampara_led.mp4")
    f.with_suffix(".txt").write_text("Luz cálida para leer\nhttps://www.amazon.es/dp/B0ABC12345?tag=ness-21\n#hogar #luz\n")
    g = _video(raiz, "producto", "02_mesa.mp4")
    g.with_suffix(".json").write_text(json.dumps({"titulo": "Mesa", "asin": "B0XYZ98765", "caption": "Plegable"}))
    _video(raiz, "producto", "03_sin.mp4")
    ingesta.ingestar("casa", AHORA)
    pubs = {p.video_path.rsplit("/", 1)[1]: p for p in publicaciones_repo.pendientes()}
    p1 = pubs["01_lampara_led.mp4"]
    assert p1.enlace.startswith("https://www.amazon.es/dp/B0ABC12345") and p1.tipo == "producto"
    assert "Luz cálida" in p1.textos["instagram"] and "#hogar" in p1.textos["instagram"]
    assert p1.titulo.startswith("Lampara led")
    assert pubs["02_mesa.mp4"].enlace == "https://www.amazon.es/dp/B0XYZ98765?tag=ness-21"
    assert pubs["03_sin.mp4"].enlace == ""


def test_json_roto_no_se_marca_ingestado(raiz):
    _cuenta()
    f = _video(raiz, "producto", "a.mp4")
    f.with_suffix(".json").write_text("{roto")
    inf = ingesta.ingestar("casa", AHORA)
    assert inf["errores"] and not inf["encoladas"]
    f.with_suffix(".json").write_text("{}")
    assert len(ingesta.ingestar("casa", AHORA)["encoladas"]) == 1


def test_mueve_a_publicados_al_publicar_todo(raiz, monkeypatch):
    _cuenta()
    f = _video(raiz, "producto", "a.mp4")
    f.with_suffix(".txt").write_text("hola")
    ingesta.ingestar("casa", AHORA)
    pub = publicaciones_repo.pendientes()[0]

    def falso(plataforma, pub, cuenta, **kw):
        return {"id": f"{plataforma}-1"}

    monkeypatch.setattr(publicador, "_ejecutar", falso)
    monkeypatch.setattr(CuentaDestino, "lista_para", lambda self, p: True)
    publicador.publicar_pendientes(pub.programada_en + 1)
    destino = raiz / "casa" / "producto" / "publicados" / "a.mp4"
    assert destino.is_file() and not f.exists()
    assert (destino.with_suffix(".txt")).is_file()
    hecha = publicaciones_repo.get(pub.id)
    assert hecha.terminada and hecha.video_path == str(destino)
    # el mismo nombre vuelve a ser nuevo
    _video(raiz, "producto", "a.mp4")
    assert len(ingesta.ingestar("casa", AHORA)["encoladas"]) == 1


def test_no_mueve_si_alguna_plataforma_no_publica(raiz):
    _cuenta()  # sin tokens: todo simulado
    f = _video(raiz, "producto", "a.mp4")
    ingesta.ingestar("casa", AHORA)
    pub = publicaciones_repo.pendientes()[0]
    publicador.publicar_pendientes(pub.programada_en + 1)
    assert f.is_file()


def test_mover_falla_solo_log(raiz, monkeypatch):
    _cuenta()
    _video(raiz, "producto", "a.mp4")
    ingesta.ingestar("casa", AHORA)
    pub = publicaciones_repo.pendientes()[0]
    import shutil

    def roto(*a, **k):
        raise OSError("disco lleno")

    monkeypatch.setattr(shutil, "move", roto)
    logs = []
    assert ingesta.mover_a_publicados(pub, logs.append) is None
    assert any("disco lleno" in m for m in logs)


def test_validacion_de_ruta(raiz, tmp_path, monkeypatch):
    monkeypatch.delenv("API_TEMP_ROOT", raising=False)
    dentro = _video(raiz, "producto", "ok.mp4")
    fuera = tmp_path / "fuera.mp4"
    fuera.write_bytes(b"x")
    escape = raiz / "casa" / ".." / ".." / "fuera.mp4"
    assert video_url.ruta_permitida(str(dentro))
    assert not video_url.ruta_permitida(str(fuera))
    assert not video_url.ruta_permitida(str(escape))
    enlace = raiz / "casa" / "link.mp4"
    enlace.symlink_to(fuera)
    assert not video_url.ruta_permitida(str(enlace))
    monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
    assert video_url.ruta_permitida(str(fuera))
    monkeypatch.delenv("API_TEMP_ROOT")

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router_publico)
    c = TestClient(app)
    assert c.get(f"/api/v1/multiplataforma/archivo/{video_url.firmar(str(dentro))}").status_code == 200
    assert c.get(f"/api/v1/multiplataforma/archivo/{video_url.firmar(str(fuera))}").status_code == 403


def test_texto_carpeta_no_usa_el_nombre_como_titulo(tmp_path):
    from src.multiplataforma.services import ingesta as ing
    v = tmp_path / "pablo1_2.mp4"
    v.write_bytes(b"x")
    (tmp_path / ing.TEXTO_CARPETA).write_text("Reflexión de Pablo Motos\n#pablomotos #reflexion\n", encoding="utf-8")
    meta = ing.leer_metadatos(v)
    assert meta["titulo"] == ""
    assert meta["caption"] == "Reflexión de Pablo Motos"


def test_huecos_con_desfase_no_repite_dia():
    import itertools
    from src.multiplataforma import config
    from src.multiplataforma.services import ingesta as ing
    t0 = 1791500000.0
    ts = list(itertools.islice(ing.huecos(1, ["14:00"], t0, semilla="viva_shop"), 10))
    assert all(abs(((t - 3600 * 12) % 86400) - 0) >= 0 for t in ts)
    dias = [round((b - a) / 86400) for a, b in zip(ts, ts[1:])]
    assert dias == [1] * 9
    # seguir desde la última (con desfase) no vuelve a dar el mismo día
    sig = next(ing.huecos(1, ["14:00"], ts[-1], semilla="viva_shop"))
    assert round((sig - ts[-1]) / 86400) == 1
    sin = list(itertools.islice(ing.huecos(1, ["14:00"], t0), 3))
    assert all(int(t) % 3600 == 0 for t in sin)
    assert any(int(t) % 3600 != 0 for t in ts) or config.DESFASE_MAX_MIN == 0


def test_virales_solo_instagram(tmp_path):
    from src.multiplataforma.models import CuentaDestino
    from src.multiplataforma.services import ingesta as ing
    v = tmp_path / "pablo1_3.mp4"
    v.write_bytes(b"x")
    pub = ing._publicacion(CuentaDestino(slug="x", nombre="x"), v, "prueba_viral", 0.0)
    assert pub.plataformas == ["instagram"]
