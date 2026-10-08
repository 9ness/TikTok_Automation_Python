"""Enlaces por producto, resubida de Mis tandas y página pública /links."""

from __future__ import annotations

import datetime as dt
import zoneinfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.exceptions import register_exception_handlers
from src.api.routers import multiplataforma as router_mp
from src.multiplataforma import config, publicador
from src.multiplataforma.models import CuentaDestino, Publicacion
from src.multiplataforma.repos import cuentas_repo, enlaces_repo, publicaciones_repo
from src.multiplataforma.services import tandas

TZ = zoneinfo.ZoneInfo("Europe/Madrid")
AHORA = dt.datetime(2026, 10, 8, 10, 0, tzinfo=TZ).timestamp()
SHEIN = "https://onelink.shein.com/17/4z8x1abc"


@pytest.fixture()
def drive(tmp_path, monkeypatch):
    """Mount falso: los vídeos de Mis tandas viven bajo TIKTOK_SHOP_AI_PRO."""
    monkeypatch.setenv("DRIVE_MOUNT_ROOT", str(tmp_path))
    monkeypatch.setenv("MULTIPLATAFORMA_DRIVE_ROOT", str(tmp_path / config.DRIVE_SUBDIR))
    base = tmp_path / config.AI_PRO_SUBDIR / "Nicho_POV_BOF_Largo" / "videos"
    base.mkdir(parents=True)
    return base


def _fila(base, id_, titulo, tienda="Tienda", uploaded=True, uploaded_at=1.0, **kw):
    v = base / f"{id_.replace('|', '_')}.mp4"
    v.write_bytes(b"v")
    d = {"id": id_, "nicho": "largo", "source": "inv", "carpeta": "C1", "carpeta_label": "Inv · C1",
         "producto": id_[-1], "titulo": titulo, "tienda": tienda, "caption": "Mira esto",
         "uploaded": uploaded, "uploaded_at": uploaded_at, "video_path": str(v), "video_listo_at": 5.0,
         "product_url": ""}
    d.update(kw)
    return d


@pytest.fixture()
def filas(monkeypatch, drive):
    lista: list[dict] = []
    from src.mis_tandas import fuentes, servicio

    monkeypatch.setattr(fuentes, "todas", lambda u: (list(lista), [], []))
    monkeypatch.setattr(servicio, "ocultos", lambda u: {"largo|inv|C1|9|"})
    return lista


@pytest.fixture()
def cuenta():
    return cuentas_repo.guardar(CuentaDestino(slug="ama_shop", nombre="Ama Shop", dueno="ana",
                                              afiliado_amazon_tag="ama-21"))


def test_clave_igual_entre_versiones_y_copias():
    a = {"titulo": "Lámpara LED", "tienda": "Casa", "nicho": "pov", "source": "inv", "carpeta": "1", "producto": "3"}
    b = {"titulo": "lampara led", "tienda": "casa", "nicho": "largo", "source": "q4", "carpeta": "Q4", "producto": "8"}
    assert tandas.producto_key(a) == tandas.producto_key(b)
    sin = {"titulo": "", "tienda": "", "nicho": "pov", "source": "inv", "carpeta": "1", "producto": "3"}
    assert tandas.producto_key(sin) != tandas.producto_key(a)


def test_productos_agrupa_y_filtra(filas, drive, cuenta):
    filas += [_fila(drive, "largo|inv|C1|1|", "Vestido verde"),
              _fila(drive, "largo|inv|C1|1|dolor", "Vestido verde", uploaded=False),
              _fila(drive, "largo|inv|C1|2|", "Bolso negro"),
              _fila(drive, "largo|inv|C1|9|", "Oculto")]
    d = tandas.productos("ama_shop")
    por_titulo = {p["titulo"]: p for p in d["productos"]}
    assert set(por_titulo) == {"Vestido verde", "Bolso negro"}  # el oculto no sale
    assert por_titulo["Vestido verde"]["videos"] == 2
    assert por_titulo["Vestido verde"]["subidos_tiktok"] == 1
    k = por_titulo["Bolso negro"]["producto_key"]
    tandas.guardar_enlace("ama_shop", k, shein=SHEIN, nota="igual")
    sin = tandas.productos("ama_shop", sin_enlace=True)["productos"]
    assert [p["titulo"] for p in sin] == ["Vestido verde"]


def test_guardar_enlace_validaciones(filas, drive, cuenta):
    filas.append(_fila(drive, "largo|inv|C1|1|", "Vestido"))
    k = tandas.producto_key(filas[0])
    e = tandas.guardar_enlace("ama_shop", k, shein=SHEIN)
    assert e["enlace"] == SHEIN and e["titulo"] == "Vestido" and e["fila_id"] == filas[0]["id"]
    e = tandas.guardar_enlace("ama_shop", k, asin="b0abcdefgh")
    assert e["enlace"] == "https://www.amazon.es/dp/B0ABCDEFGH?tag=ama-21" and e["shein"] == ""
    e = tandas.guardar_enlace("ama_shop", k, shein="sin_equivalente", nota="no hay")
    assert e["sin_equivalente"] and enlaces_repo.enlace_de("ama_shop", k) == ""
    with pytest.raises(tandas.ErrorTandas):
        tandas.guardar_enlace("ama_shop", k, shein="https://bit.ly/x")
    with pytest.raises(tandas.ErrorTandas):
        tandas.guardar_enlace("ama_shop", k, shein="https://www.amazon.es/dp/B0ABCDEFGH")
    with pytest.raises(tandas.ErrorTandas):
        tandas.guardar_enlace("ama_shop", "no-hex!", shein=SHEIN)


def test_encolar_idempotente_y_con_ritmo(filas, drive, cuenta):
    filas += [_fila(drive, "largo|inv|C1|1|", "Vestido", uploaded_at=20.0),
              _fila(drive, "largo|inv|C1|2|", "Bolso", uploaded_at=10.0),
              _fila(drive, "largo|inv|C1|3|", "Gorra", uploaded=False),
              _fila(drive, "largo|inv|C1|4|", "Sin enlace")]
    for f in filas[:3]:
        tandas.guardar_enlace("ama_shop", tandas.producto_key(f), shein=SHEIN)
    inf = tandas.encolar("ama_shop", ahora=AHORA)
    assert [e["titulo"] for e in inf["encoladas"]] == ["Bolso", "Vestido"]  # orden de TikTok
    assert inf["omitidas"]["no_subidos"] == 1 and inf["omitidas"]["sin_enlace"] == 1
    horas = [dt.datetime.fromtimestamp(e["programada_en"], TZ) for e in inf["encoladas"]]
    assert [(h.day, h.hour) for h in horas] == [(8, 13), (9, 13)]  # ritmo producto 1/día a las 13:00
    pub = publicaciones_repo.get(inf["encoladas"][0]["id"])
    assert pub.enlace == SHEIN and pub.origen == "tandas" and pub.producto_ref
    assert SHEIN in pub.textos["threads"]
    # Segunda vez: nada nuevo; con incluir_no_subidos entra la gorra.
    assert tandas.encolar("ama_shop", ahora=AHORA)["total"] == 0
    inf2 = tandas.encolar("ama_shop", incluir_no_subidos=True, ahora=AHORA)
    assert [e["titulo"] for e in inf2["encoladas"]] == ["Gorra"]
    assert dt.datetime.fromtimestamp(inf2["encoladas"][0]["programada_en"], TZ).day == 10


def test_encolar_rechaza_rutas_fuera(filas, drive, cuenta, tmp_path):
    fuera = tmp_path / "otro" / "x.mp4"
    fuera.parent.mkdir()
    fuera.write_bytes(b"v")
    f = _fila(drive, "largo|inv|C1|1|", "Vestido")
    f["video_path"] = str(fuera)
    filas.append(f)
    tandas.guardar_enlace("ama_shop", tandas.producto_key(f), shein=SHEIN)
    inf = tandas.encolar("ama_shop", ahora=AHORA)
    assert inf["total"] == 0 and inf["omitidas"]["ruta_no_valida"] == 1


def test_publicador_rellena_enlace_de_producto_ref(cuenta, sin_red):
    k = "a" * 16
    enlaces_repo.guardar("ama_shop", k, {"enlace": SHEIN, "titulo": "Vestido"})
    pub = Publicacion(cuenta="ama_shop", video_path="/tmp/x.mp4", producto_ref=k, titulo="Vestido",
                      caption="Mira", plataformas=["threads"], programada_en=AHORA - 1)
    publicaciones_repo.guardar(pub)
    inf = publicador.publicar_una(pub, ahora=AHORA, http=sin_red, sleep=lambda s: None)
    assert inf["enlace_rellenado"] == SHEIN
    guardada = publicaciones_repo.get(pub.id)
    assert guardada.enlace == SHEIN and SHEIN in guardada.textos["threads"]


def test_ingesta_rellena_desde_producto_ref(cuenta, tmp_path, monkeypatch):
    import json

    from src.multiplataforma.services import ingesta

    monkeypatch.setenv("MULTIPLATAFORMA_DRIVE_ROOT", str(tmp_path / "MP"))
    k = "b" * 16
    enlaces_repo.guardar("ama_shop", k, {"enlace": SHEIN})
    d = tmp_path / "MP" / "ama_shop" / "producto"
    d.mkdir(parents=True)
    (d / "1.mp4").write_bytes(b"v")
    (d / "1.json").write_text(json.dumps({"titulo": "Vestido", "producto_ref": k}))
    inf = ingesta.ingestar("ama_shop", AHORA)
    pub = publicaciones_repo.get(inf["encoladas"][0]["id"])
    assert pub.enlace == SHEIN and pub.caption == ""


# ---- API ----
@pytest.fixture()
def cliente():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router_mp.router)
    app.include_router(router_mp.router_publico)
    return TestClient(app)


def test_api_enlaces_y_links_publicos(filas, drive, cuenta, cliente, monkeypatch):
    filas += [_fila(drive, "largo|inv|C1|1|", "Vestido verde"),
              _fila(drive, "largo|inv|C1|2|", "Bolso"),
              _fila(drive, "largo|inv|C1|3|", "Gorra")]
    ks = [tandas.producto_key(f) for f in filas]
    r = cliente.get("/api/v1/multiplataforma/cuentas/ama_shop/productos?sin_enlace=1")
    assert r.status_code == 200 and r.json()["total"] == 3
    assert cliente.put(f"/api/v1/multiplataforma/cuentas/ama_shop/enlaces/{ks[0]}",
                       json={"shein": SHEIN}).status_code == 200
    assert cliente.put(f"/api/v1/multiplataforma/cuentas/ama_shop/enlaces/{ks[1]}",
                       json={"asin": "B0ABCDEFGH"}).status_code == 200
    assert cliente.put(f"/api/v1/multiplataforma/cuentas/ama_shop/enlaces/{ks[2]}",
                       json={"shein": "sin_equivalente", "nota": "nada"}).status_code == 200
    assert cliente.put(f"/api/v1/multiplataforma/cuentas/ama_shop/enlaces/{ks[2]}",
                       json={"shein": "https://amzn.to/x"}).status_code == 400

    r = cliente.post("/api/v1/multiplataforma/cuentas/ama_shop/encolar-tandas")
    assert r.status_code == 200 and r.json()["total"] == 2

    pub = r.json()["encoladas"][0]
    p = publicaciones_repo.get(pub["id"])
    p.estado["instagram"] = config.ESTADO_PUBLICADO
    p.resultados["instagram"] = {"publicado_en": AHORA}
    publicaciones_repo.guardar(p)

    r = cliente.get("/api/v1/multiplataforma/links/ama_shop")
    assert r.status_code == 200
    d = r.json()
    assert d["cuenta"] == "Ama Shop"
    assert len(d["productos"]) == 2  # sin_equivalente no sale
    assert d["productos"][0]["id"] == pub["producto_key"]  # lo último publicado, primero
    assert "obtengo ingresos" in d["aviso_amazon"]
    texto = r.text
    assert str(drive) not in texto and "fila_id" not in texto and "largo|" not in texto

    # Foto pública: solo productos con enlace; la de un sin_equivalente, 404.
    from src.mis_tandas import servicio

    foto = drive / "f.jpg"
    foto.write_bytes(b"\xff\xd8jpg")
    monkeypatch.setattr(servicio, "foto", lambda u, i, w=96: foto)
    assert cliente.get(f"/api/v1/multiplataforma/links/ama_shop/foto/{ks[0]}").status_code == 200
    assert cliente.get(f"/api/v1/multiplataforma/links/ama_shop/foto/{ks[2]}").status_code == 404
    assert cliente.get("/api/v1/multiplataforma/links/ama_shop/foto/..%2F..").status_code == 404
    assert cliente.get("/api/v1/multiplataforma/links/nadie").status_code == 404

    assert cliente.delete(f"/api/v1/multiplataforma/cuentas/ama_shop/enlaces/{ks[0]}").status_code == 200
    assert cliente.delete(f"/api/v1/multiplataforma/cuentas/ama_shop/enlaces/{ks[0]}").status_code == 404


def test_links_publico_con_sesion_pro_no_da_403():
    from src.api import main

    assert any("/api/v1/multiplataforma/links/x".startswith(p) for p in main._PREFIJOS_PRO)
    assert not any("/api/v1/multiplataforma/cola".startswith(p) for p in main._PREFIJOS_PRO)


def test_mcp_tiene_las_herramientas():
    pytest.importorskip("mcp")
    from src.agente_mcp import servidor

    for nombre in ("productos_sin_enlace", "guardar_enlace", "encolar_tandas", "cola_multiplataforma",
                   "cuentas_multiplataforma"):
        assert callable(getattr(servidor, nombre))
    assert "NUNCA en TikTok" in servidor.guia("multiplataforma")
