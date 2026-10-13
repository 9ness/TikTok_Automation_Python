"""«Replicar virales» (vídeo ya montado): alta (subida y bandeja), lista,
reemplazo, borrado, API y su fila en «Mis tandas». Sin red ni Drive: Redis es
un diccionario y el «Drive» y la bandeja, `tmp_path`."""

from __future__ import annotations

import json

import pytest

from src.replicar_viral import servicio, video
from src.replicar_viral.servicio import ErrorReplica

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


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

    def delete(self, k):
        self.d.pop(k, None)
        return True


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(servicio, "_redis", lambda: r)
    monkeypatch.setattr(video, "_raiz", lambda: tmp_path / "drive")
    monkeypatch.setenv("AGENTE_BANDEJA_DIR", str(tmp_path / "bandeja"))
    monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path / "tmp"))
    from src.mis_tandas import servicio as mt_servicio

    monkeypatch.setattr(mt_servicio, "_redis", lambda: r)
    monkeypatch.setattr(mt_servicio.fuentes, "todas", lambda u: ([], [], []))
    mt_servicio._cache.clear()
    from src.cuotas.repos import cuota_repo

    monkeypatch.setattr(cuota_repo, "marcar", lambda *a, **k: None)
    return r


def _mp4(tmp_path, nombre="v.mp4", datos=MP4):
    p = tmp_path / nombre
    p.write_bytes(datos)
    return p


def _bandeja(usuario="ness"):
    from src.agente_mcp import config as agente_config

    return agente_config.bandeja_dir(usuario)


def test_registrar_y_listar(entorno, tmp_path):
    doc = video.registrar("ness", modo="con_ia", origen=_mp4(tmp_path), titulo="  Lámpara   LED ",
                          product_url="https://www.tiktok.com/view/product/1729123456789?x=1",
                          hashtags="#lampara deco", prompts=["clip 1", "clip 2"])
    assert doc["tipo"] == "video" and doc["producto"]["titulo"] == "Lámpara LED"
    assert doc["producto"]["product_id"] == "1729123456789"
    assert doc["producto"]["product_url"] == "https://www.tiktok.com/view/product/1729123456789"
    assert doc["hashtags"] == ["#lampara", "#deco"]
    assert (tmp_path / "drive" / "ness" / f"{doc['id']}.mp4").read_bytes() == MP4
    assert [d["id"] for d in video.listar("ness")] == [doc["id"]]
    assert video.listar("ness", "sin_ia") == [] and video.listar("ana") == []
    # No ensucia el índice general (guiones y carruseles: tope de 200).
    assert servicio.lista("ness") == []


def test_validaciones(entorno, tmp_path):
    with pytest.raises(ErrorReplica):
        video.registrar("ness", modo="otro", origen=_mp4(tmp_path), titulo="X")
    with pytest.raises(ErrorReplica):
        video.registrar("ness", modo="sin_ia", origen=_mp4(tmp_path), titulo="  ")
    with pytest.raises(ErrorReplica):
        video.registrar("ness", modo="sin_ia", origen=_mp4(tmp_path, "f.mp4", b"no es video" * 3), titulo="X")
    with pytest.raises(ErrorReplica):
        video.registrar("ness", modo="sin_ia", origen=_mp4(tmp_path), titulo="X",
                        product_url="https://amazon.es/dp/123")


def test_bandeja_y_rutas_fuera(entorno, tmp_path):
    b = _bandeja("ness")
    (b / "rv").mkdir(parents=True, exist_ok=True)
    (b / "rv" / "final.mp4").write_bytes(MP4)
    doc = video.desde_bandeja("ness", "rv/final.mp4", modo="sin_ia", titulo="Bici", product_id="123456789")
    assert doc["producto"]["product_url"].endswith("/123456789")
    (tmp_path / "fuera.mp4").write_bytes(MP4)
    for mala in ("../../fuera.mp4", "/../fuera.mp4", "", "rv/no.mp4", "rv/final.txt"):
        with pytest.raises(ErrorReplica):
            video.desde_bandeja("ness", mala, modo="sin_ia", titulo="X")


def test_reemplazo_y_borrado(entorno, tmp_path):
    doc = video.registrar("ness", modo="con_ia", origen=_mp4(tmp_path), titulo="X")
    video.marcar("ness", doc["id"], rehacer=True, rehacer_nota="producto distinto")
    antes = doc["video_listo_at"]
    nuevo = video.registrar("ness", modo="", origen=_mp4(tmp_path, "b.mp4", MP4 + b"1"), titulo="",
                            replica_id=doc["id"])
    assert nuevo["id"] == doc["id"] and nuevo["rehecho"] and not nuevo["rehacer"]
    assert nuevo["video_listo_at"] >= antes and nuevo["modo"] == "con_ia"
    with pytest.raises(ErrorReplica):
        video.registrar("ana", modo="", origen=_mp4(tmp_path), titulo="", replica_id=doc["id"])
    video.borrar("ness", doc["id"])
    assert video.listar("ness") == [] and not (tmp_path / "drive" / "ness" / f"{doc['id']}.mp4").exists()
    with pytest.raises(ErrorReplica):
        video.ver("ness", doc["id"])


def test_mis_tandas_fila_y_botones(entorno, tmp_path):
    from src.mis_tandas import servicio as mt

    doc = video.registrar("ness", modo="sin_ia", origen=_mp4(tmp_path), titulo="Bici",
                          caption="Mira esto", hashtags=["bici"])
    filas = mt.filas("ness", fresco=True)
    assert [f["id"] for f in filas] == [f"rv|{doc['id']}"]
    f = filas[0]
    assert f["nicho"] == "rv" and f["puede_rehacer"] and f["caption"] == "Mira esto #bici"
    assert mt._partes(f["id"]) == ["rv", doc["id"]]
    assert mt.marcar("ness", f["id"], uploaded=True)["uploaded"]
    assert video.ver("ness", doc["id"])["uploaded"] is True
    mt.marcar("ness", f["id"], sin_stock=True)
    assert video.ver("ness", doc["id"])["sin_stock"] is True
    # Rojo en el semáforo marca «rehacer» en el documento de la réplica.
    assert mt.poner_semaforo("ness", f["id"], "rojo", "marca de agua")["rehacer"]
    assert video.ver("ness", doc["id"])["rehacer_nota"].endswith("marca de agua")
    p, _ = mt.video("ness", f["id"])
    assert p.read_bytes() == MP4
    with pytest.raises(mt.ErrorTanda):
        mt.marcar("ana", f["id"], uploaded=True)  # no es suya


def test_rv_nuevo_entra_al_final(entorno, monkeypatch):
    from src.mis_tandas import fuentes, servicio as mt

    pov = [fuentes._fila(id="p1", nicho="pov", orden_at=10), fuentes._fila(id="p2", nicho="pov", orden_at=20)]
    rv = [fuentes._fila(id="rv|aaaaaaaaaaaa", nicho="rv", orden_at=1)]
    assert [f["id"] for f in mt._ordenar("ness", pov, [], [], rv)] == ["p1", "p2", "rv|aaaaaaaaaaaa"]


def test_api(entorno, tmp_path):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    from src.api.dependencies import get_current_user, get_web_user
    from src.api.exceptions import APIError
    from src.api.routers.replicar_viral import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: "k"
    app.dependency_overrides[get_web_user] = lambda: "ness"

    @app.exception_handler(APIError)
    async def _h(request, exc):  # noqa: ANN001
        return JSONResponse({"error": str(exc)}, status_code=getattr(exc, "status_code", 500))

    c = TestClient(app)
    r = c.post("/api/v1/replicar-viral/video", files={"file": ("v.mp4", MP4, "video/mp4")},
               data={"modo": "con_ia", "titulo": "Lámpara", "product_id": "987654321",
                     "prompts": '["a", "b"]', "hashtags": "#x\n#y"})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert r.json()["prompts"] == 2 and r.json()["hashtags"] == ["#x", "#y"]
    b = _bandeja("ness")
    b.mkdir(parents=True, exist_ok=True)
    (b / "dos.mp4").write_bytes(MP4)
    r2 = c.post("/api/v1/replicar-viral/video/bandeja",
                json={"ruta": "dos.mp4", "modo": "sin_ia", "titulo": "Bici", "hashtags": ["bici"]})
    assert r2.status_code == 200, r2.text
    assert c.post("/api/v1/replicar-viral/video/bandeja",
                  json={"ruta": "../x.mp4", "modo": "sin_ia", "titulo": "B"}).status_code == 403
    lista = c.get("/api/v1/replicar-viral/video").json()
    assert [i["id"] for i in lista["items"]] == [r2.json()["id"], rid] and "con_ia" in lista["modos"]
    assert len(c.get("/api/v1/replicar-viral/video", params={"modo": "con_ia"}).json()["items"]) == 1
    assert c.get(f"/api/v1/replicar-viral/video/{rid}").json()["prompts"] == ["a", "b"]
    m = c.get(f"/api/v1/replicar-viral/video/{rid}/mp4", params={"descargar": True})
    assert m.status_code == 200 and m.content == MP4 and "replica_L" in m.headers["content-disposition"]
    assert c.delete(f"/api/v1/replicar-viral/video/{rid}").status_code == 200
    assert c.get(f"/api/v1/replicar-viral/video/{rid}").status_code == 404
