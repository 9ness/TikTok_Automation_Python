"""«👑 Editor VIP»: modo de réplica para lo editado con el VIP del Editor Auto
y vídeo de referencia en `editar_en_editor`. Sin red: `Interno` falso."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp")

from src.agente_mcp import servidor  # noqa: E402
from src.agente_mcp.interno import ErrorApp  # noqa: E402
from src.replicar_viral import video  # noqa: E402

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


class _Interno:
    llamadas: list = []

    def __init__(self, u):
        self.u = u

    async def get_bytes(self, ruta, **kw):
        _Interno.llamadas.append(("get_bytes", ruta, kw))
        return MP4, "video/mp4", "edicion.mp4"

    async def post(self, ruta, datos):
        _Interno.llamadas.append(("post", ruta, dict(datos)))
        return {"ok": True}

    async def post_form(self, ruta, datos, fichero, otros=None):
        _Interno.llamadas.append(("post_form", ruta, dict(datos), fichero, otros))
        return {"id": "abc123abc123", "ok": True}


@pytest.fixture
def fake(monkeypatch):
    _Interno.llamadas = []
    monkeypatch.setattr(servidor, "Interno", _Interno)
    monkeypatch.setattr(servidor, "_usuario", lambda ctx: "ness")

    async def leer_origen(u, *, url="", archivo_id="", ruta_bandeja=""):
        return MP4, f"{archivo_id or 'x'}.mp4"

    monkeypatch.setattr(servidor.archivos, "leer_origen", leer_origen)
    return _Interno


CTX = SimpleNamespace(headers={})


def _correr(fn, **kw):
    return asyncio.run(fn(CTX, **kw))


def test_modo_editor_vip_existe_y_es_fisico():
    from src.nicho_pov_bof.services import marcas

    assert video.MODOS["editor_vip"] == "👑 Editor VIP"
    assert marcas.formato_de("rv", "editor_vip") == "fisico"


def test_registrar_con_edicion_y_sin_modo_sale_editor_vip(fake):
    _correr(servidor.registrar_replica_video, edicion="job1", titulo="Bici", product_id="1729123456789")
    post = [c for c in fake.llamadas if c[0] == "post_form"][0]
    assert post[2]["modo"] == "editor_vip"


def test_registrar_con_edicion_respeta_el_modo_dado(fake):
    _correr(servidor.registrar_replica_video, edicion="job1", modo="sin_ia", titulo="Bici")
    assert [c for c in fake.llamadas if c[0] == "post_form"][0][2]["modo"] == "sin_ia"


def test_registrar_sin_edicion_ni_modo_falla(fake):
    with pytest.raises(ErrorApp, match="Falta `modo`"):
        _correr(servidor.registrar_replica_video, url="https://x/v.mp4", titulo="Bici")


def test_editar_referencia_url_y_bandeja_van_en_el_form(fake):
    _correr(servidor.editar_en_editor, ruta_bandeja="a.mp4", referencia_url="https://www.tiktok.com/@x/video/1")
    _, ruta, datos, fichero, otros = fake.llamadas[-1]
    assert ruta.endswith("/ediciones-fabrica/enviar")
    assert datos["referencia_url"] == "https://www.tiktok.com/@x/video/1"
    assert datos["ruta_bandeja"] == "a.mp4" and fichero is None and otros is None

    _correr(servidor.editar_en_editor, ruta_bandeja="a.mp4", referencia_ruta_bandeja="refs/viral.mp4")
    datos = fake.llamadas[-1][2]
    assert datos["referencia_ruta_bandeja"] == "refs/viral.mp4" and "referencia_url" not in datos


def test_editar_referencia_archivo_va_como_fichero_referencia(fake):
    _correr(servidor.editar_en_editor, archivo_id="vid", referencia_archivo_id="ref")
    _, _, datos, fichero, otros = fake.llamadas[-1]
    assert fichero[0] == "vid.mp4"
    assert otros["referencia"][0] == "ref.mp4" and otros["referencia"][1] == MP4
    assert "referencia_url" not in datos


def test_editar_referencia_una_sola_y_solo_vip(fake):
    with pytest.raises(ErrorApp, match="UNA referencia"):
        _correr(servidor.editar_en_editor, ruta_bandeja="a.mp4",
                referencia_url="https://t/1", referencia_ruta_bandeja="b.mp4")
    with pytest.raises(ErrorApp, match="solo vale con estilo"):
        _correr(servidor.editar_en_editor, ruta_bandeja="a.mp4", estilo="normal",
                referencia_url="https://t/1")
    assert not fake.llamadas


def test_post_form_manda_los_dos_ficheros(monkeypatch):
    from src.agente_mcp.interno import Interno

    vistos = {}

    async def pedir(self, metodo, ruta, **kw):
        vistos.update(kw)
        return SimpleNamespace(content=b"{}", json=lambda: {})

    monkeypatch.setattr(Interno, "_pedir", pedir)
    asyncio.run(Interno("ness").post_form("/r", {"a": True}, ("v.mp4", b"1", "video/mp4"),
                                          {"referencia": ("r.mp4", b"2", "video/mp4")}))
    assert set(vistos["files"]) == {"file", "referencia"} and vistos["data"] == {"a": "true"}


def test_editar_quitar_marca_va_en_el_form_y_valida(fake):
    _correr(servidor.editar_en_editor, ruta_bandeja="a.mp4", quitar_marca="Omni")
    assert fake.llamadas[-1][2]["quitar_marca"] == "omni"
    _correr(servidor.editar_en_editor, ruta_bandeja="a.mp4")
    assert "quitar_marca" not in fake.llamadas[-1][2]
    with pytest.raises(ErrorApp):
        _correr(servidor.editar_en_editor, ruta_bandeja="a.mp4", quitar_marca="todo")


def test_semaforo_con_para(fake):
    _correr(servidor.semaforo_tanda, id="rv|x", color="verde", motivo="ok", para="ana")
    assert fake.llamadas[-1][2]["para"] == "ana"
    _correr(servidor.semaforo_tanda, id="rv|x", color="verde", motivo="ok")
    assert "para" not in fake.llamadas[-1][2]


def test_bandeja_de_para_si_no_esta_en_la_mia(monkeypatch, tmp_path):
    from src.api.routers import replicar_viral as r
    from src.replicar_viral import carrusel

    rutas = []

    def ruta_bandeja(u, rel):
        rutas.append(u)
        if u == "ness":
            raise video.ErrorReplica("No está", status=404)
        return tmp_path / rel

    monkeypatch.setattr(video, "ruta_bandeja", ruta_bandeja)
    monkeypatch.setattr(carrusel, "destino", lambda u, p="": p or u)
    monkeypatch.setattr(video, "registrar", lambda quien, **kw: {"quien": quien, "origen": str(kw["origen"])})
    monkeypatch.setattr(video, "resumen", lambda d: d)
    body = r.VideoBandejaRequest(ruta="v.mp4", modo="sin_ia", titulo="t", para="ana")
    out = r.video_bandeja(body, usuario="ness")
    assert rutas == ["ness", "ana"] and out["quien"] == "ana"
