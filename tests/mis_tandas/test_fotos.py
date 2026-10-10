"""«Mis tandas › Fotos»: carruseles de «Replicar carrusel» en tandas de diez,
con su propio contador, «Subido» y ZIP por tanda. Sin red ni Drive (fixture
`entorno` de los tests de carrusel: Redis en memoria y fotos en tmp_path)."""

from __future__ import annotations

import io
import zipfile

import pytest

from src.mis_tandas import fotos
from src.replicar_viral import carrusel, servicio
from tests.replicar_viral.test_carrusel import FakeRedis, _jpeg, entorno  # noqa: F401 — fixture


@pytest.fixture(autouse=True)
def _sin_redis_real(monkeypatch):
    """Textos del POV BOF (sin stock) y tope diario en memoria: nada toca Upstash."""
    from src.cuotas.repos import cuota_repo
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    rp = FakeRedis()
    monkeypatch.setattr(pov_repo, "get_nicho_pov_bof_redis", lambda: rp)
    cuotas: list[tuple] = []
    monkeypatch.setattr(cuota_repo, "marcar", lambda *a, **k: cuotas.append(a))
    return cuotas


def _crear(n: int, usuario: str = "ness", con_foto: bool = True) -> list[str]:
    ids = []
    for i in range(n):
        doc = carrusel.replicar(usuario, source="mis_productos", folder="Mis Productos 5",
                                producto="1", url=f"https://www.tiktok.com/@x/photo/{i}")
        r = servicio._redis()
        clave = servicio.CLAVE.format(id=doc["id"])
        d = r.get_json(clave)
        d["creado_at"] = 1_000 + i  # orden de creación determinista
        r.set_json(clave, d)
        if con_foto:
            carrusel.subir_imagen(usuario, doc["id"], 1, _jpeg())
        ids.append(doc["id"])
    return ids


def test_tandas_de_diez_con_su_contador(entorno):  # noqa: F811
    ids = _crear(12)
    _crear(1, con_foto=False)  # sin fotos no entra
    t = fotos.tandas("ness")
    assert t["total"] == 12 and t["abiertas"] == 2 and t["cerradas"] == 0
    assert [x["total"] for x in t["tandas"]] == [10, 2]
    assert [c["id"] for c in t["tandas"][0]["items"]] == ids[:10]
    assert t["tandas"][0]["fecha"] < t["tandas"][1]["fecha"]
    assert t["tandas"][0]["items"][0]["hechas"] == 1 and not t["tandas"][0]["items"][0]["completo"]
    assert fotos.tandas("ana")["total"] == 0  # cada usuario lo suyo


def test_marcar_subido_cierra_la_tanda(entorno):  # noqa: F811
    ids = _crear(11)
    for i in ids[:10]:
        assert fotos.marcar("ness", i, True)["subido"]
    t = fotos.tandas("ness")
    assert t["cerradas"] == 1 and t["subidos"] == 10 and [x["numero"] for x in t["tandas"]] == [2]
    assert [x["numero"] for x in fotos.tandas("ness", todas=True)["tandas"]] == [1, 2]
    assert not fotos.marcar("ness", ids[0], False)["subido"]
    assert fotos.tandas("ness")["cerradas"] == 0
    # El listado de «Replicar carrusel» también lo ve.
    assert {x["id"]: x["subido"] for x in servicio.lista("ness", "carrusel")}[ids[1]] is True


def test_zip_de_la_tanda(entorno):  # noqa: F811
    ids = _crear(3)
    fotos.marcar("ness", ids[0], True)
    datos, nombre = fotos.zip_tanda("ness", 1)
    assert nombre == "fotos_tanda_001.zip"
    nombres = zipfile.ZipFile(io.BytesIO(datos)).namelist()
    assert {n.split("/")[0][:3] for n in nombres} == {"01_", "02_", "03_"}
    assert any(n.endswith("caption.txt") for n in nombres)
    pend = zipfile.ZipFile(io.BytesIO(fotos.zip_tanda("ness", 1, pendientes=True)[0])).namelist()
    assert not any(n.startswith("01_") for n in pend)
    try:
        fotos.zip_tanda("ness", 5)
    except carrusel.ErrorReplica as e:
        assert e.status == 404
    else:
        raise AssertionError("tenía que fallar")


def test_api_fotos(entorno):  # noqa: F811
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from src.api.dependencies import get_current_user, get_web_user
    from src.api.exceptions import APIError
    from src.api.routers.mis_tandas import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: "k"
    app.dependency_overrides[get_web_user] = lambda: "ness"

    @app.exception_handler(APIError)
    async def _h(request, exc):  # noqa: ANN001
        return JSONResponse({"error": str(exc)}, status_code=getattr(exc, "status_code", 500))

    c = TestClient(app)
    ids = _crear(2)
    assert c.get("/api/v1/mis-tandas/fotos").json()["total"] == 2
    r = c.post("/api/v1/mis-tandas/fotos/estado", json={"id": ids[0], "subido": True})
    assert r.status_code == 200 and r.json()["subido"]
    z = c.get("/api/v1/mis-tandas/fotos/zip", params={"tanda": 1})
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    assert c.get("/api/v1/mis-tandas/fotos/zip", params={"tanda": 9}).status_code == 404
    assert c.post("/api/v1/mis-tandas/fotos/estado", json={"id": "nope", "subido": True}).status_code == 404


def test_subido_suma_al_tope_de_carruseles(entorno, _sin_redis_real):  # noqa: F811
    ids = _crear(1)
    fotos.marcar("ness", ids[0], subido=True)
    assert _sin_redis_real == [("carruseles", f"replica_carrusel|{ids[0]}", "ness", True)]
    assert fotos.tandas("ness")["subidos_hoy"] == 1


def test_sin_stock_es_del_producto(entorno):  # noqa: F811
    from src.nicho_pov_bof.repos import product_repo as pov_repo

    ids = _crear(3)
    r = fotos.marcar("ness", ids[1], sin_stock=True)
    assert r["sin_stock"] and not r["subido"]
    # Se escribe en los textos del POV BOF: lo ven sus vídeos y los demás carruseles del producto.
    prods = pov_repo.load_folder("mis_productos", "Mis Productos 5")["productos"]
    assert prods["1"]["sin_stock"] is True
    t = fotos.tandas("ness", todas=True)
    assert t["sin_stock"] == 3 and t["tandas"][0]["sin_stock"] == 3
    assert t["abiertas"] == 0 and t["cerradas"] == 1  # nada que publicar
    try:
        fotos.zip_tanda("ness", 1)
    except carrusel.ErrorReplica as e:
        assert e.status == 404  # sin stock no entra en el ZIP
    else:
        raise AssertionError("tenía que fallar")
    assert not fotos.marcar("ness", ids[1], sin_stock=False)["sin_stock"]
    assert fotos.tandas("ness")["abiertas"] == 1
    try:
        fotos.marcar("ness", ids[0])
    except carrusel.ErrorReplica:
        pass
    else:
        raise AssertionError("sin cambios tenía que fallar")
