"""Tests de la Cuenta Piloto (Programa 4 — Tiktok Shop AI Pro).

El foco está en lo ÚNICO que este nicho hace y ningún otro: **guardar varios
vídeos por producto**. En el resto de nichos el segundo montaje pisa al primero
(un solo `video_path`), así que si esto se rompe el operador pierde trabajo sin
que nada avise.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.queue.models import JobMode


class RedisFalso:
    """Upstash in-memory. Solo los comandos que usa `product_repo`."""

    def __init__(self) -> None:
        self.kv: dict[str, object] = {}
        self.locks: set[str] = set()
        self.prefix = "cuenta_piloto:"

    def is_available(self) -> bool:
        return True

    def _k(self, key: str) -> str:
        return key if key.startswith(self.prefix) else f"{self.prefix}{key}"

    def get_json(self, key: str):
        v = self.kv.get(self._k(key))
        return v if isinstance(v, (dict, list)) else None

    def set_json(self, key: str, value) -> bool:
        self.kv[self._k(key)] = value
        return True

    def set_nx(self, key: str, value: str, ttl_s: int) -> bool:
        k = self._k(key)
        if k in self.locks:
            return False
        self.locks.add(k)
        return True

    def delete(self, key: str) -> bool:
        k = self._k(key)
        self.locks.discard(k)
        return self.kv.pop(k, None) is not None


@pytest.fixture
def redis_piloto(monkeypatch: pytest.MonkeyPatch) -> RedisFalso:
    import src.cuenta_piloto.repos.redis_base as base

    falso = RedisFalso()
    monkeypatch.setattr(base, "_INSTANCE", falso)
    monkeypatch.setattr(base, "get_cuenta_piloto_redis", lambda: falso)
    import src.cuenta_piloto.repos.product_repo as repo

    monkeypatch.setattr(repo, "get_cuenta_piloto_redis", lambda: falso)
    return falso


@pytest.fixture
def assets_piloto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Sin mount de Drive: las fotos van a `API_TEMP_ROOT`."""
    monkeypatch.setattr(
        "src.nicho_pov_bof.services.audio_bank.mount_root", lambda: None,
    )
    monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
    return tmp_path


def _crear(client: TestClient, *, con_ficha: bool = True) -> dict:
    ficheros = {"foto_limpia": ("limpia.jpg", b"\xff\xd8foto", "image/jpeg")}
    if con_ficha:
        ficheros["foto_ficha"] = ("ficha.png", b"\x89PNGficha", "image/png")
    r = client.post("/api/v1/cuenta-piloto/productos", files=ficheros)
    assert r.status_code == 200, r.text
    return r.json()["producto"]


class TestAltaProducto:
    def test_crea_producto_y_guarda_las_dos_fotos(
        self, app_client: TestClient, redis_piloto, assets_piloto,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # La extracción con Gemini se apaga: aquí se prueba el alta, no el OCR.
        monkeypatch.setattr(
            "src.cuenta_piloto.services.text_extractor.extraer",
            lambda productos, **kw: {},
        )
        prod = _crear(app_client)
        assert prod["id"] == "1"
        assert prod["tiene_ficha"] is True
        assert prod["videos"] == []

        from src.cuenta_piloto.repos import product_repo

        guardado = product_repo.get_product("", "1")
        assert Path(guardado["foto_limpia"]).read_bytes() == b"\xff\xd8foto"
        assert Path(guardado["foto_ficha"]).read_bytes() == b"\x89PNGficha"

    def test_rechaza_un_formato_que_no_es_foto(
        self, app_client: TestClient, redis_piloto, assets_piloto,
    ):
        r = app_client.post(
            "/api/v1/cuenta-piloto/productos",
            files={"foto_limpia": ("clip.mp4", b"video", "video/mp4")},
        )
        assert r.status_code == 400
        assert "formato" in r.text.lower()

    def test_la_ficha_es_opcional(
        self, app_client: TestClient, redis_piloto, assets_piloto,
    ):
        prod = _crear(app_client, con_ficha=False)
        assert prod["tiene_ficha"] is False

    def test_gemini_caido_no_pierde_el_producto(
        self, app_client: TestClient, redis_piloto, assets_piloto,
        monkeypatch: pytest.MonkeyPatch,
    ):
        def _revienta(productos, **kw):
            raise RuntimeError("Gemini 503")

        monkeypatch.setattr(
            "src.cuenta_piloto.services.text_extractor.extraer", _revienta,
        )
        prod = _crear(app_client)
        # Queda creado y sin textos: se reintenta sin volver a subir fotos.
        assert prod["id"] == "1"
        assert prod["titulo"] == ""


class TestVariosVideosPorProducto:
    """Lo que distingue a este nicho: subir otro vídeo NO pisa el anterior."""

    def test_add_video_acumula(self, redis_piloto, assets_piloto):
        from src.cuenta_piloto.repos import product_repo

        product_repo.crear_producto("ana", foto_limpia="/tmp/a.jpg")
        product_repo.add_video("ana", "1", path="/v/1_v1.mp4", sexo="hombre")
        product_repo.add_video("ana", "1", path="/v/1_v2.mp4", sexo="mujer")

        videos = product_repo.get_product("ana", "1")["videos"]
        assert [v["path"] for v in videos] == ["/v/1_v1.mp4", "/v/1_v2.mp4"]
        assert [v["sexo"] for v in videos] == ["hombre", "mujer"]

    def test_update_product_no_borra_los_videos(self, redis_piloto, assets_piloto):
        from src.cuenta_piloto.repos import product_repo

        product_repo.crear_producto("ana", foto_limpia="/tmp/a.jpg")
        product_repo.add_video("ana", "1", path="/v/1_v1.mp4")
        product_repo.update_product("ana", "1", titulo="Gorra negra")

        prod = product_repo.get_product("ana", "1")
        assert prod["titulo"] == "Gorra negra"
        assert len(prod["videos"]) == 1

    def test_upload_encola_con_el_producto_y_la_voz(
        self, app_client: TestClient, fake_job_queue, redis_piloto, assets_piloto,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            "src.cuenta_piloto.services.text_extractor.extraer",
            lambda productos, **kw: {},
        )
        _crear(app_client)
        r = app_client.post(
            "/api/v1/cuenta-piloto/video/upload",
            files={"file": ("bruto.mp4", b"video-de-prueba", "video/mp4")},
            data={"producto": "1", "sexo": "mujer"},
        )
        assert r.status_code == 200, r.text
        job = fake_job_queue.get_all()[-1]
        assert job.mode == JobMode.CUENTA_PILOTO_VIDEO
        assert job.params["producto"] == "1"
        assert job.params["sexo"] == "mujer"
        assert Path(job.params["raw_path"]).is_file()

    def test_upload_rechaza_un_sexo_que_no_existe(
        self, app_client: TestClient, redis_piloto, assets_piloto,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            "src.cuenta_piloto.services.text_extractor.extraer",
            lambda productos, **kw: {},
        )
        _crear(app_client)
        r = app_client.post(
            "/api/v1/cuenta-piloto/video/upload",
            files={"file": ("bruto.mp4", b"x", "video/mp4")},
            data={"producto": "1", "sexo": "robot"},
        )
        assert r.status_code == 400

    def test_upload_de_un_producto_inexistente_da_404(
        self, app_client: TestClient, redis_piloto, assets_piloto,
    ):
        r = app_client.post(
            "/api/v1/cuenta-piloto/video/upload",
            files={"file": ("bruto.mp4", b"x", "video/mp4")},
            data={"producto": "99", "sexo": "hombre"},
        )
        assert r.status_code == 404


class TestAislamientoPorUsuario:
    def test_cada_usuario_ve_solo_lo_suyo(self, redis_piloto, assets_piloto):
        from src.cuenta_piloto.repos import product_repo

        product_repo.crear_producto("ana", foto_limpia="/tmp/ana.jpg")
        product_repo.crear_producto("mauro", foto_limpia="/tmp/mauro.jpg")

        assert len(product_repo.listar("ana")) == 1
        assert len(product_repo.listar("mauro")) == 1
        assert product_repo.get_product("ana", "1")["foto_limpia"] == "/tmp/ana.jpg"
        assert product_repo.get_product("mauro", "1")["foto_limpia"] == "/tmp/mauro.jpg"


class TestBorrado:
    def test_borra_el_producto_y_sus_ficheros(
        self, tmp_path: Path, redis_piloto, assets_piloto,
    ):
        from src.cuenta_piloto.repos import product_repo

        foto = tmp_path / "foto.jpg"
        foto.write_bytes(b"x")
        video = tmp_path / "v1.mp4"
        video.write_bytes(b"y")

        product_repo.crear_producto("ana", foto_limpia=str(foto))
        product_repo.add_video("ana", "1", path=str(video))

        assert product_repo.borrar_producto("ana", "1") is True
        assert product_repo.listar("ana") == []
        assert not foto.exists()
        assert not video.exists()

    def test_borrar_lo_que_no_existe_devuelve_false(self, redis_piloto, assets_piloto):
        from src.cuenta_piloto.repos import product_repo

        assert product_repo.borrar_producto("ana", "404") is False
