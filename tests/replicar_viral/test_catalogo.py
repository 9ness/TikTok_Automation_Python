"""Catálogo «Carruseles virales»: alta desde «Replicar carrusel», textos de la
ficha (con coste), URL del producto y replicar otra vez para otro usuario.

Sin red ni Drive: el catálogo escribe en `tmp_path` (se COMPRUEBA, como en
`test_mis_productos.py`), Redis del POV BOF es un diccionario y Gemini, tikwm
y el redirect de la URL van con dobles.
"""

from __future__ import annotations

import pytest

from src.nicho_pov_bof import config as pov_config
from src.nicho_pov_bof.repos import product_repo
from src.nicho_pov_bof.services import mis_productos, photo_pairing, reanclaje, text_extractor
from src.nicho_pov_bof.services import product_url as url_svc
from src.replicar_viral import carrusel, catalogo, servicio
from src.replicar_viral.servicio import ErrorReplica
from tests.replicar_viral.test_carrusel import _jpeg, entorno  # noqa: F401 — fixture

URL_FICHA = "https://www.tiktok.com/view/product/1729?region=ES"
URL_VIRAL = "https://www.tiktok.com/@x/photo/999"


@pytest.fixture
def cat(tmp_path, monkeypatch):
    raiz = tmp_path / "carruseles_virales"
    raiz.mkdir()
    real = pov_config.dir_operador
    monkeypatch.setattr(pov_config, "dir_operador",
                        lambda source="mis_productos": raiz if source == catalogo.SOURCE else real(source))
    assert tmp_path in mis_productos._dir(catalogo.SOURCE).parents, "escribiría en el Drive real"
    mis_productos._invalidar()

    docs: dict[tuple[str, str], dict] = {}

    def _prods(s, f):
        return docs.setdefault((s, f), {}).setdefault("productos", {})

    def update_product(s, f, p, usuario="", **campos):
        _prods(s, f).setdefault(p, {}).update(campos)
        return dict(_prods(s, f)[p])

    def save_extracted_texts(s, f, textos):
        for p, t in textos.items():
            _prods(s, f).setdefault(p, {}).update(t)

    def anadir_id_vigente(s, f, p):
        docs.setdefault((s, f), {}).setdefault("ids_vigentes", []).append(p)

    urls: dict[str, str] = {}
    monkeypatch.setattr(product_repo, "update_product", update_product)
    monkeypatch.setattr(product_repo, "save_extracted_texts", save_extracted_texts)
    monkeypatch.setattr(product_repo, "anadir_id_vigente", anadir_id_vigente)
    monkeypatch.setattr(product_repo, "get_product", lambda s, f, p, u="": dict(_prods(s, f).get(p, {})))
    monkeypatch.setattr(product_repo, "load_folders", lambda e: [docs.get(k, {}) for k in e])
    monkeypatch.setattr(product_repo, "guardar_url", lambda prod, url: urls.setdefault(prod["titulo"], url))
    monkeypatch.setattr(reanclaje, "borrar_productos", lambda *a, **k: 0)
    monkeypatch.setattr(url_svc, "id_desde_url", lambda url, **k: "1729")
    monkeypatch.setattr(photo_pairing, "desempatar_por_contenido", lambda par, fetch: par)

    pedidos: list[list[str]] = []

    def extract_from_pairs(pares, **kw):
        pedidos.append([p["producto"] for p in pares])
        return {p["producto"]: {"titulo": "Lámpara efecto agua", "tienda": "Luz SL", "precio": "19,99"}
                for p in pares}

    monkeypatch.setattr(text_extractor, "extract_from_pairs", extract_from_pairs)
    monkeypatch.setattr(text_extractor, "_load_system_prompt", lambda: "prompt")
    import src.cost_tracking as ct

    trabajos: list[dict] = []
    monkeypatch.setattr(ct, "start_job", lambda **kw: trabajos.append(kw))
    monkeypatch.setattr(ct, "finalize_and_persist", lambda: None)
    return {"raiz": raiz, "docs": docs, "urls": urls, "pedidos": pedidos, "trabajos": trabajos}


def _alta(**kw):
    datos = {"product_url": URL_FICHA, "carrusel_url": URL_VIRAL,
             "nombre_limpia": "limpia.jpg", "nombre_ficha": "ficha.png", "usuario": "ness"}
    datos.update(kw)
    return catalogo.crear_producto(_jpeg(), _jpeg(600, 1300), **datos)


def test_catalogo_registrado_como_del_operador():
    assert catalogo.SOURCE in pov_config.SOURCES
    assert pov_config.es_catalogo_operador(catalogo.SOURCE)
    assert pov_config.es_fuente_propia(catalogo.SOURCE)
    assert catalogo.SOURCE in pov_config.fuentes_a_barrer()


def test_alta_guarda_fotos_textos_y_url(cat):
    p = _alta()
    assert (p["folder"], p["producto"]) == ("Carruseles Virales 1", "1")
    assert sorted(x.name for x in (cat["raiz"] / "Carruseles Virales 1").iterdir()) == ["1(1).png", "1.jpg"]
    assert p["titulo"] == "Lámpara efecto agua" and not p["aviso"]
    assert p["product_url"] == URL_FICHA and p["carrusel_url"] == URL_VIRAL
    prod = cat["docs"][(catalogo.SOURCE, "Carruseles Virales 1")]["productos"]["1"]
    assert prod["product_id"] == "1729" and prod["creado_por"] == "ness"
    assert cat["urls"] == {"Lámpara efecto agua": URL_FICHA}  # al índice global de fichas
    # Solo se lee la ficha de ESTE producto y el gasto va a /costs.
    p2 = _alta()
    assert p2["producto"] == "2" and cat["pedidos"] == [["1"], ["2"]]
    assert [t["mode"] for t in cat["trabajos"]] == ["replicar_carrusel_textos"] * 2


def test_lista_lo_nuevo_primero(cat):
    _alta()
    _alta(carrusel_url="")
    filas = catalogo.listar()
    assert [f["producto"] for f in filas] == ["2", "1"]
    assert filas[1]["carrusel_url"] == URL_VIRAL and filas[0]["carrusel_url"] == ""


def test_si_falla_la_lectura_el_producto_queda_y_se_reintenta(cat, monkeypatch):
    monkeypatch.setattr(text_extractor, "extract_from_pairs", lambda *a, **k: {})
    p = _alta()
    assert p["aviso"] and not p["titulo"] and p["product_url"] == URL_FICHA
    with pytest.raises(ErrorReplica):
        catalogo.releer_textos(p["folder"], p["producto"])
    monkeypatch.setattr(text_extractor, "extract_from_pairs",
                        lambda pares, **k: {"1": {"titulo": "Lámpara", "tienda": "Luz"}})
    assert catalogo.releer_textos(p["folder"], "1")["titulo"] == "Lámpara"
    assert cat["urls"] == {"Lámpara": URL_FICHA}


@pytest.mark.parametrize("kw, msg", [
    ({"product_url": ""}, "URL del producto"),
    ({"product_url": "https://amazon.es/x"}, "URL del producto"),
    ({"carrusel_url": "https://instagram.com/p/1"}, "carrusel viral"),
    ({"nombre_limpia": "foto.gif"}, "formato"),
])
def test_alta_valida(cat, kw, msg):
    with pytest.raises(ErrorReplica, match=msg):
        _alta(**kw)
    assert not any(cat["raiz"].iterdir()) or not any((cat["raiz"] / "Carruseles Virales 1").iterdir())


def test_falta_la_ficha(cat):
    with pytest.raises(ErrorReplica, match="ficha"):
        catalogo.crear_producto(_jpeg(), b"", product_url=URL_FICHA)


def test_replicar_desde_el_catalogo_apunta_el_viral(entorno, monkeypatch):  # noqa: F811
    apuntes = []
    monkeypatch.setattr(catalogo, "guardar_carrusel_url", lambda *a: apuntes.append(a))
    carrusel.replicar("ness", source=catalogo.SOURCE, folder="Carruseles Virales 1", producto="1",
                      url=URL_VIRAL)
    carrusel.replicar("ness", source="mis_productos", folder="Mis Productos 5", producto="1",
                      url=URL_VIRAL)
    assert apuntes == [("Carruseles Virales 1", "1", URL_VIRAL)]


def test_destino():
    assert carrusel.destino("ness") == "ness"
    assert carrusel.destino("ness", "Ana") == "ana"
    assert carrusel.destino("ana", "ana") == "ana"
    with pytest.raises(ErrorReplica) as e:
        carrusel.destino("ana", "mauro")
    assert e.value.status == 403
    with pytest.raises(ErrorReplica):
        carrusel.destino("ness", "pepito")


def test_replicar_otra_vez_para_otro_usuario(entorno):  # noqa: F811
    orig = carrusel.replicar("ness", source="mis_productos", folder="Mis Productos 5", producto="1",
                             url=URL_VIRAL)
    nuevo = carrusel.replicar_otra_vez("ness", orig["id"], "ana")
    assert nuevo["usuario"] == "ana" and nuevo["replica_de"] == orig["id"]
    assert nuevo["url"] == URL_VIRAL and nuevo["producto"]["folder"] == "Mis Productos 5"
    assert len(entorno["llamadas"]) == 2  # Gemini otra vez: textos nuevos para otra cuenta
    assert [x["id"] for x in servicio.lista("ana", "carrusel")] == [nuevo["id"]]
    assert servicio.lista("ana", "carrusel")[0]["replica_de"] == orig["id"]
    assert [x["id"] for x in servicio.lista("ness", "carrusel")] == [orig["id"]]
    with pytest.raises(ErrorReplica):  # Ana no ve el de ness
        carrusel.replicar_otra_vez("ana", orig["id"])


def _cliente(usuario="ness"):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from src.api.dependencies import get_current_user, get_web_user
    from src.api.exceptions import APIError
    from src.api.routers.replicar_viral import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: "k"
    app.dependency_overrides[get_web_user] = lambda: usuario

    @app.exception_handler(APIError)
    async def _h(request, exc):  # noqa: ANN001
        return JSONResponse({"error": str(exc)}, status_code=getattr(exc, "status_code", 500))

    return TestClient(app)


def test_api_alta_y_catalogo(cat):
    c = _cliente("mauro")
    r = c.post("/api/v1/replicar-viral/carrusel/producto",
               data={"product_url": URL_FICHA, "carrusel_url": URL_VIRAL},
               files={"foto_limpia": ("l.jpg", _jpeg(), "image/jpeg"),
                      "foto_ficha": ("f.png", _jpeg(), "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["creado_por"] == "mauro"
    items = c.get("/api/v1/replicar-viral/carrusel/catalogo").json()["items"]
    assert items[0]["titulo"] == "Lámpara efecto agua"
    r = c.post("/api/v1/replicar-viral/carrusel/producto/textos",
               json={"folder": "Carruseles Virales 1", "producto": "1"})
    assert r.status_code == 200, r.text
    assert c.post("/api/v1/replicar-viral/carrusel/producto",
                  data={"product_url": "nope"},
                  files={"foto_limpia": ("l.jpg", _jpeg(), "image/jpeg"),
                         "foto_ficha": ("f.png", _jpeg(), "image/png")}).status_code == 400


def test_api_replicar_para_solo_admin(entorno):  # noqa: F811
    c = _cliente("ana")
    datos = {"source": "mis_productos", "folder": "Mis Productos 5", "producto": "1", "url": URL_VIRAL}
    assert c.post("/api/v1/replicar-viral/carrusel/analizar", data={**datos, "para": "mauro"}).status_code == 403
    r = _cliente("ness").post("/api/v1/replicar-viral/carrusel/analizar", data={**datos, "para": "ana"})
    assert r.status_code == 200 and r.json()["usuario"] == "ana"
    r2 = c.post(f"/api/v1/replicar-viral/carrusel/{r.json()['id']}/replicar", json={})
    assert r2.status_code == 200 and r2.json()["usuario"] == "ana"


def test_mcp_herramientas():
    pytest.importorskip("mcp")
    import asyncio

    from src.agente_mcp import servidor

    nombres = {t.name for t in asyncio.run(servidor.mcp.list_tools())}
    assert {"producto_carrusel", "replicar_carrusel", "mis_tandas", "marcar_tanda"} <= nombres
