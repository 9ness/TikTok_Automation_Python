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
    from src.api.dependencies import get_current_user, get_web_user
    app.dependency_overrides[get_current_user] = lambda: "k"
    app.dependency_overrides[get_web_user] = lambda: "ness"
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

    pub, otra = r.json()["encoladas"][:2]
    p = publicaciones_repo.get(pub["id"])
    p.estado["instagram"] = config.ESTADO_PUBLICADO
    p.resultados["instagram"] = {"publicado_en": AHORA}
    publicaciones_repo.guardar(p)

    r = cliente.get("/api/v1/multiplataforma/links/ama_shop")
    assert r.status_code == 200
    d = r.json()
    assert d["cuenta"] == "Ama Shop"
    # Solo lo ya publicado: el otro con enlace sigue en cola y sin_equivalente no sale.
    assert [x["id"] for x in d["productos"]] == [pub["producto_key"]]
    assert d["productos"][0]["publicado_en"] == int(AHORA)

    # Al publicarse la otra (antes), sale DETRÁS: lo último publicado, primero.
    p = publicaciones_repo.get(otra["id"])
    p.resultados["instagram"] = {"publicado_en": AHORA - 3600}
    publicaciones_repo.guardar(p)
    tandas._links_cache.clear()
    d = cliente.get("/api/v1/multiplataforma/links/ama_shop").json()
    assert [x["id"] for x in d["productos"]] == [pub["producto_key"], otra["producto_key"]]
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
                   "cuentas_multiplataforma", "encolar_carrusel"):
        assert callable(getattr(servidor, nombre))
    assert "NUNCA en TikTok" in servidor.guia("multiplataforma")


def test_encolar_texto_en_espanol_con_hashtags(filas, drive, cuenta):
    filas.append(_fila(drive, "largo|inv|C1|1|", "Vestido verde", caption="Vestido verde de verano",
                       emojis="😍👗"))
    k = tandas.producto_key(filas[0])
    tandas.guardar_enlace("ama_shop", k, shein=SHEIN, titulo="Women's Long Summer Dress With Pockets")
    inf = tandas.encolar("ama_shop", ahora=AHORA)
    pub = publicaciones_repo.get(inf["encoladas"][0]["id"])
    assert pub.titulo == "Vestido verde" and "Women" not in pub.textos["instagram"]
    assert pub.textos["instagram"].startswith("Vestido verde de verano 😍👗")
    assert "#outfit" in pub.textos["instagram"] and "#shein" in pub.textos["instagram"]
    assert tandas._hashtags("Creatina monohidratada", "https://www.amazon.es/dp/B000000000")[:1] == ["bienestar"]


def test_auto_encolar_mantiene_dias_en_cola(filas, drive, cuenta):
    for i in range(1, 6):
        filas.append(_fila(drive, f"largo|inv|C1|{i}|", f"Producto {i}", uploaded_at=float(i)))
        tandas.guardar_enlace("ama_shop", tandas.producto_key(filas[-1]), shein=SHEIN)
    assert tandas.auto_encolar("ama_shop", ahora=AHORA)["motivo"] == "apagado"
    cuenta.auto_tandas = 2
    cuentas_repo.guardar(cuenta)
    assert tandas.auto_encolar("ama_shop", ahora=AHORA)["total"] == 2
    # dentro de la hora no vuelve a mirar; pasada la hora, la cola ya está llena
    assert tandas.auto_encolar("ama_shop", ahora=AHORA + 60)["motivo"] == "reciente"
    assert tandas.auto_encolar("ama_shop", ahora=AHORA + 4000)["motivo"] == "cola llena"
    assert [i["total"] for i in tandas.auto_encolar_todas(ahora=AHORA + 9000)] == [0]


def test_temporada_se_guarda_pero_no_se_encola_fuera(filas, drive, cuenta):
    filas.append(_fila(drive, "largo|inv|C1|1|", "Tumbona de playa"))
    k = tandas.producto_key(filas[0])
    tandas.guardar_enlace("ama_shop", k, shein=SHEIN, temporada="verano")
    octubre = dt.datetime(2026, 10, 9, 12, tzinfo=TZ).timestamp()
    inf = tandas.encolar("ama_shop", ahora=octubre)
    assert inf["total"] == 0 and inf["omitidas"]["fuera_temporada"] == 1
    junio = dt.datetime(2027, 6, 1, 12, tzinfo=TZ).timestamp()
    assert tandas.encolar("ama_shop", ahora=junio)["total"] == 1
    with pytest.raises(tandas.ErrorTandas):
        tandas.guardar_enlace("ama_shop", k, shein=SHEIN, temporada="primavera")


def test_hashtags_por_cuenta_sin_categoria():
    # viva_salud no puede caer en #hogar; el aceite corporal es belleza
    amz = "https://www.amazon.es/dp/B000000000"
    assert tandas._hashtags("Freshly Aceite Corporal para estrías y cicatrices", amz, "viva_salud")[:1] == ["skincare"]
    assert tandas._hashtags("Producto raro sin categoría", amz, "viva_salud")[:1] == ["bienestar"]
    assert tandas._hashtags("Producto raro sin categoría", amz, "viva_shop")[:1] == ["hogar"]


def test_categoria_link():
    assert tandas.categoria_link("Women's Knee High Boots Round Toe") == "👢 Botas"
    assert tandas.categoria_link("Bolso bandolera estampado con mariposas") == "👜 Bolsos"
    assert tandas.categoria_link("Women's Bohemian Gladiator Sandals") == "👟 Zapatos"
    assert tandas.categoria_link("Conjunto deportivo de dos piezas para mujer") == "👚 Conjuntos"
    assert tandas.categoria_link("Set 12 Utensilios de Cocina de Silicona") == "🍳 Cocina"
    assert tandas.categoria_link("Cosa rara") == config.CATEGORIA_OTROS
