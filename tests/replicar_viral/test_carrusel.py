"""Replicar carrusel: tikwm, Gemini, Redis, quemado del texto y ZIP.

Sin red: tikwm, la descarga de diapositivas, Gemini y el catálogo del POV BOF
van con dobles; Redis es un diccionario; las fotos, a `tmp_path`.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from src.replicar_viral import carrusel, servicio
from src.replicar_viral.servicio import ErrorReplica


class FakeRedis:
    def __init__(self) -> None:
        self.d: dict[str, object] = {}

    def is_available(self) -> bool:
        return True

    def get_json(self, k):
        v = self.d.get(k)
        return json.loads(json.dumps(v)) if v is not None else None

    def set_json(self, k, v):
        self.d[k] = json.loads(json.dumps(v))
        return True

    def mget_json(self, ks):
        return [self.get_json(k) for k in ks]


def _jpeg(w=1080, h=1440, color=(120, 160, 200)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "JPEG")
    return b.getvalue()


class _Resp:
    def __init__(self, *, js=None, content=b"") -> None:
        self._js, self.content = js, content

    def json(self):
        return self._js

    def raise_for_status(self):
        pass


RESPUESTA_IA = {
    "original": {"tema": "calendario de adviento de perritos", "por_que_funciona": "sorpresa"},
    "apto": True,
    "motivo_no_apto": "",
    "diapositivas": [
        {"n": 1, "rol": "gancho", "texto_original": "Un perrito por 1500 €?",
         "texto": "¿Esto por menos de lo que piensas? 😱", "usa_foto_producto": False,
         "prompt_imagen": "Vertical 3:4 photo of a surprised woman on a sofa"},
        {"n": 2, "rol": "PRODUCTO", "texto": "Aplica tus cupones y llévatelo",
         "usa_foto_producto": True, "prompt_imagen": "Use the attached reference photo"},
        {"n": 3, "rol": "rarisimo", "texto": "", "prompt_imagen": ""},
    ],
    "caption": "Con tu cupón sale genial",
    "hashtags": ["adviento", "#navidad"],
}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(servicio, "_redis", lambda: r)
    monkeypatch.setattr(carrusel, "_raiz", lambda: tmp_path / "raiz")
    monkeypatch.setattr(servicio, "_producto", lambda *a, **k: (
        {"titulo": "Calendario Adviento Perritos", "tienda": "Tienda X", "precio": "19,99 €"}, None))

    def get(url, params=None, timeout=None, **kw):
        if "tikwm" in url:
            return _Resp(js={"code": 0, "data": {
                "title": "Un perrito por 1500 €?", "author": {"unique_id": "saludconsciente"},
                "play_count": 1800000, "play": "https://x/musica.mp3",
                "images": ["https://img/1.jpg", "https://img/2.jpg", "https://img/3.jpg"]}})
        return _Resp(content=_jpeg())

    monkeypatch.setattr(carrusel.requests, "get", get)
    monkeypatch.setattr(servicio.requests, "get", get)
    llamadas: list[dict] = []

    def generate_text(sistema, mensaje, **kw):
        llamadas.append({"sistema": sistema, "mensaje": mensaje, **kw})
        return "```json\n" + json.dumps(RESPUESTA_IA) + "\n```"

    import src.tiktok_shop.api.gemini as gemini
    import src.cost_tracking as ct

    monkeypatch.setattr(gemini, "generate_text", generate_text)
    monkeypatch.setattr(ct, "start_job", lambda **kw: None)
    monkeypatch.setattr(ct, "finalize_and_persist", lambda: None)
    return {"redis": r, "llamadas": llamadas, "raiz": tmp_path / "raiz"}


def _replicar():
    return carrusel.replicar("ness", source="mis_productos", folder="Carpeta_1", producto="3",
                             url="https://www.tiktok.com/@x/photo/123")


def test_descargar_tiktok_sigue_rechazando_carruseles(entorno, tmp_path):
    with pytest.raises(ErrorReplica, match="Replicar carrusel"):
        servicio.descargar_tiktok("https://www.tiktok.com/@x/photo/1", tmp_path / "v.mp4")


def test_datos_carrusel_rechaza_videos(monkeypatch):
    monkeypatch.setattr(servicio.requests, "get", lambda *a, **k: _Resp(
        js={"code": 0, "data": {"play": "https://v.mp4", "title": "t"}}))
    with pytest.raises(ErrorReplica, match="Replicar viral"):
        carrusel.datos_carrusel("https://www.tiktok.com/@x/video/1")


def test_datos_carrusel_pide_enlace_de_tiktok():
    with pytest.raises(ErrorReplica, match="TikTok"):
        carrusel.datos_carrusel("https://instagram.com/p/1")


def test_replicar_guarda_tipo_carrusel_y_normaliza(entorno):
    doc = _replicar()
    assert doc["tipo"] == "carrusel" and doc["formato"] == "3:4"
    assert doc["referencia"]["diapositivas"] == 3 and doc["referencia"]["autor"] == "saludconsciente"
    d = doc["diapositivas"]
    assert [x["rol"] for x in d] == ["gancho", "producto", "producto"]
    # Cupones nunca afirmados, ni en el texto ni en el caption.
    assert "tus cupones" not in d[1]["texto"] and "revisa si tienes cupones" in d[1]["texto"]
    assert "tu cupón" not in doc["caption"].lower()
    # Sin texto en la imagen, siempre.
    assert all("no text" in x["prompt_imagen"].lower() for x in d if x["prompt_imagen"])
    assert doc["hashtags"] == ["#adviento", "#navidad"]
    assert doc["hechas"] == 0 and doc["total"] == 3 and not doc["completo"]
    # En Redis, junto a las de vídeo (mismo prefijo e índice).
    r = entorno["redis"]
    assert r.get_json(servicio.CLAVE.format(id=doc["id"]))["tipo"] == "carrusel"
    assert r.get_json(servicio.INDICE.format(usuario="ness"))["ids"] == [doc["id"]]
    # Las originales quedan en disco para compararlas.
    assert carrusel.ruta_foto("ness", doc["id"], 1, "orig")
    # A Gemini le llegan las 3 diapositivas y el formato en el prompt.
    ll = entorno["llamadas"][0]
    assert len(ll["images"]) == 3 and "3:4" in ll["sistema"] and "{{FORMATO}}" not in ll["sistema"]


def test_formato_9_16_si_la_diapositiva_es_alargada(entorno, monkeypatch):
    real = carrusel.requests.get

    def get(url, **kw):
        return _Resp(content=_jpeg(1080, 1920)) if "img/" in url else real(url, **kw)

    monkeypatch.setattr(carrusel.requests, "get", get)
    assert _replicar()["formato"] == "9:16"


def test_lista_filtra_por_tipo(entorno):
    doc = _replicar()
    servicio.guardar({"id": "aaaaaaaaaaaa", "usuario": "ness", "adaptacion": {"idea": "vídeo"}})
    assert [x["id"] for x in servicio.lista("ness", "carrusel")] == [doc["id"]]
    assert [x["id"] for x in servicio.lista("ness", "video")] == ["aaaaaaaaaaaa"]
    assert {x["tipo"] for x in servicio.lista("ness")} == {"video", "carrusel"}
    carrusel.subir_imagen("ness", doc["id"], 2, _jpeg())
    assert servicio.lista("ness", "carrusel")[0]["hechas"] == 1


def test_subir_quema_el_texto_y_zip(entorno):
    doc = _replicar()
    id_ = doc["id"]
    st = carrusel.subir_imagen("ness", id_, 1, _jpeg(color=(250, 250, 250)))
    assert st["diapositivas"][0]["tiene_texto"] and st["hechas"] == 1
    base = carrusel.ruta_foto("ness", id_, 1, "base")
    txt = carrusel.ruta_foto("ness", id_, 1, "txt")
    assert base and txt and base.read_bytes() != txt.read_bytes()
    # La 3 no lleva texto: con la foto ya está lista, sin versión quemada.
    st = carrusel.subir_imagen("ness", id_, 3, _jpeg())
    assert st["diapositivas"][2]["lista"] and not st["diapositivas"][2]["tiene_texto"]
    datos, nombre = carrusel.zip_carrusel("ness", id_)
    assert nombre.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(datos)) as z:
        nombres = sorted(z.namelist())
        assert [Path(n).name for n in nombres] == ["01.jpg", "03.jpg", "caption.txt"]
        assert "#navidad" in z.read([n for n in nombres if n.endswith("caption.txt")][0]).decode()


def test_cambiar_texto_vuelve_a_quemar_desde_la_base(entorno):
    doc = _replicar()
    id_ = doc["id"]
    carrusel.subir_imagen("ness", id_, 1, _jpeg())
    antes = carrusel.ruta_foto("ness", id_, 1, "txt").read_bytes()
    st = carrusel.cambiar_texto("ness", id_, 1, "Otro texto con tu cupón")
    assert "tu cupón" not in st["diapositivas"][0]["texto"]
    assert carrusel.ruta_foto("ness", id_, 1, "txt").read_bytes() != antes
    carrusel.cambiar_texto("ness", id_, 1, "")
    assert carrusel.ruta_foto("ness", id_, 1, "txt") is None


def test_errores(entorno):
    doc = _replicar()
    with pytest.raises(ErrorReplica):
        carrusel.zip_carrusel("ness", doc["id"])  # sin fotos aún
    with pytest.raises(ErrorReplica):
        carrusel.subir_imagen("ness", doc["id"], 9, _jpeg())  # no existe la diapositiva
    with pytest.raises(ErrorReplica):
        carrusel.subir_imagen("ness", doc["id"], 1, b"no es imagen")
    with pytest.raises(ErrorReplica):
        carrusel.ver("ana", doc["id"])  # de otro usuario
    with pytest.raises(ErrorReplica):
        carrusel.dir_replica("ness", "../../etc")


def test_si_la_ia_falla_no_deja_fotos_huerfanas(entorno, monkeypatch):
    import src.tiktok_shop.api.gemini as gemini

    monkeypatch.setattr(gemini, "generate_text", lambda *a, **k: "esto no es json")
    with pytest.raises(ErrorReplica, match="JSON"):
        _replicar()
    assert not any((entorno["raiz"] / "ness").glob("*/orig/*.jpg"))


@pytest.mark.parametrize("entrada,esperado", [
    ("Aplica tus cupones ya", "revisa si tienes cupones ya"),
    ("Llévatelo con tu cupón", "Llévatelo revisa si tienes cupones"),
    ("Revisa si tienes cupones", "Revisa si tienes cupones"),
])
def test_sin_cupones_afirmados(entrada, esperado):
    assert carrusel.sin_cupones_afirmados(entrada) == esperado


def test_api_rutas(entorno):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.dependencies import get_current_user, get_web_user
    from src.api.exceptions import APIError
    from src.api.routers.replicar_viral import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: "k"
    app.dependency_overrides[get_web_user] = lambda: "ness"

    from fastapi.responses import JSONResponse

    @app.exception_handler(APIError)
    async def _h(request, exc):  # noqa: ANN001
        return JSONResponse({"error": str(exc)}, status_code=getattr(exc, "status_code", 500))

    c = TestClient(app)
    r = c.post("/api/v1/replicar-viral/carrusel/analizar", data={
        "source": "mis_productos", "folder": "Carpeta_1", "producto": "3",
        "url": "https://www.tiktok.com/@x/photo/1"})
    assert r.status_code == 200, r.text
    id_ = r.json()["id"]
    assert c.get("/api/v1/replicar-viral?tipo=carrusel").json()["items"][0]["id"] == id_
    assert c.get(f"/api/v1/replicar-viral/carrusel/{id_}/zip").status_code == 404
    r = c.post(f"/api/v1/replicar-viral/carrusel/{id_}/imagen/1",
               files={"file": ("a.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200 and r.json()["hechas"] == 1
    assert c.get(f"/api/v1/replicar-viral/carrusel/{id_}/imagen/1?tipo=orig").status_code == 200
    assert c.get(f"/api/v1/replicar-viral/carrusel/{id_}/imagen/2").status_code == 404
    r = c.post(f"/api/v1/replicar-viral/carrusel/{id_}/texto/1", json={"texto": "Nuevo"})
    assert r.json()["diapositivas"][0]["texto"] == "Nuevo"
    z = c.get(f"/api/v1/replicar-viral/carrusel/{id_}/zip")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    # La de vídeo sigue resolviéndose por /{id_}.
    assert c.get(f"/api/v1/replicar-viral/{id_}").json()["tipo"] == "carrusel"


def test_mcp_enlaces(monkeypatch):
    pytest.importorskip("mcp")
    from src.agente_mcp import archivos, servidor

    monkeypatch.setattr(archivos, "enlace_interno", lambda u, r: f"E:{r}")
    doc = {"id": "abcabcabcabc", "hechas": 1, "diapositivas": [
        {"n": 1, "tiene_original": True, "tiene_imagen": True},
        {"n": 2, "tiene_original": True, "tiene_imagen": False}]}
    out = servidor._enlaces_carrusel("ness", doc)
    assert out["zip"].endswith("/carrusel/abcabcabcabc/zip")
    assert "tipo=orig" in out["diapositivas"][1]["original"] and "descargar" not in out["diapositivas"][1]
    import asyncio

    nombres = {t.name for t in asyncio.run(servidor.mcp.list_tools())}
    assert {"replicar_carrusel", "subir_imagen_carrusel", "descargar_carrusel"} <= nombres
