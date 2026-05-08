"""Tests de validadores de inputs UI."""

import pytest

from src.tiktok_shop.utils.validators import (
    PHOTO_MAX_SIZE_BYTES,
    require_non_empty,
    validate_photo_extension,
    validate_photo_resolution,
    validate_photo_size,
    validate_photo_upload,
    validate_slug,
    validate_tiktok_shop_url,
    validate_tiktok_username,
)


class TestValidateSlug:
    @pytest.mark.parametrize("slug", [
        "valid_slug",
        "slug123",
        "a",
        "primal_pump_gominolas_de_creatina",
        "_underscore_start",
    ])
    def test_valid(self, slug: str):
        ok, err = validate_slug(slug)
        assert ok, f"esperado ok pero falló con: {err}"

    @pytest.mark.parametrize("slug,reason_keyword", [
        ("",                  "vacío"),
        ("UpperCase",         "minúsculas"),
        ("with spaces",       "espacios"),
        ("dash-not-allowed",  "Slug inválido"),
        ("with!sym",          "Slug inválido"),
        ("español",           "Slug inválido"),
        ("with.period",       "Slug inválido"),
    ])
    def test_invalid(self, slug: str, reason_keyword: str):
        ok, err = validate_slug(slug)
        assert not ok
        assert reason_keyword.lower() in err.lower()


class TestValidateUsername:
    @pytest.mark.parametrize("username", [
        "@user",
        "@user_123",
        "@my.handle",
        "@a1",
    ])
    def test_valid(self, username: str):
        ok, err = validate_tiktok_username(username)
        assert ok, err

    @pytest.mark.parametrize("username,reason", [
        ("",              "vacío"),
        ("nohash",        "@"),
        ("@",             "al menos 2"),
        ("@a",            "al menos 2"),
        ("@" + "x" * 25,  "más de 24"),
        ("@user!",        "Username inválido"),
        ("@user-dash",    "Username inválido"),
        ("@user space",   "Username inválido"),
    ])
    def test_invalid(self, username: str, reason: str):
        ok, err = validate_tiktok_username(username)
        assert not ok
        assert reason.lower() in err.lower()


class TestValidateTikTokShopURL:
    @pytest.mark.parametrize("url", [
        "https://www.tiktok.com/view/product/123",
        "http://tiktok.com/path",
        "https://shop-en.tiktok.com/view/X",
        "https://shop-es.tiktok.com/view/abc",
    ])
    def test_valid(self, url: str):
        ok, err = validate_tiktok_shop_url(url)
        assert ok, err

    def test_empty_optional(self):
        ok, err = validate_tiktok_shop_url("")
        assert ok  # opcional, vacío es OK

    def test_empty_required(self):
        ok, err = validate_tiktok_shop_url("", required=True)
        assert not ok
        assert "obligatoria" in err

    @pytest.mark.parametrize("url", [
        "https://amazon.com/x",
        "https://random.com/path",
        "tiktok.com/no/scheme",
        "javascript:alert(1)",
        "ftp://tiktok.com/x",
    ])
    def test_invalid_url(self, url: str):
        ok, err = validate_tiktok_shop_url(url)
        assert not ok
        assert "tiktok shop" in err.lower()


class TestValidatePhotoExtension:
    @pytest.mark.parametrize("name", ["a.jpg", "B.JPEG", "c.png", "d.webp"])
    def test_valid(self, name: str):
        ok, _ = validate_photo_extension(name)
        assert ok

    @pytest.mark.parametrize("name", ["a.gif", "b.bmp", "c.tiff", "noextension", "d.heic"])
    def test_invalid(self, name: str):
        ok, err = validate_photo_extension(name)
        assert not ok
        assert "no soportado" in err.lower()


class TestValidatePhotoSize:
    def test_within_limits(self):
        ok, _ = validate_photo_size(1024 * 100)  # 100 KB
        assert ok

    def test_zero_rejected(self):
        ok, err = validate_photo_size(0)
        assert not ok
        assert "vacío" in err

    def test_exceeds_limit(self):
        ok, err = validate_photo_size(PHOTO_MAX_SIZE_BYTES + 1)
        assert not ok
        assert "MB" in err

    def test_at_limit_passes(self):
        ok, _ = validate_photo_size(PHOTO_MAX_SIZE_BYTES)
        assert ok

    def test_custom_limit(self):
        ok, err = validate_photo_size(100, max_bytes=50)
        assert not ok


class TestValidatePhotoResolution:
    def test_high_res_passes(self, png_path):
        # 1080×1920 → ambos lados >=512
        ok, _ = validate_photo_resolution(png_path, min_px=512)
        assert ok

    def test_low_res_fails(self, small_jpeg_path):
        # 800×600 → ambos >=512 → pasa
        ok, _ = validate_photo_resolution(small_jpeg_path, min_px=512)
        assert ok
        # Pero con min=1024 → 600<1024 → falla
        ok, err = validate_photo_resolution(small_jpeg_path, min_px=1024)
        assert not ok
        assert "demasiado baja" in err.lower()

    def test_missing_file(self, tmp_path):
        ok, err = validate_photo_resolution(tmp_path / "no.jpg")
        assert not ok
        assert "no encontrado" in err.lower()

    def test_corrupt_file(self, tmp_path):
        bad = tmp_path / "bad.jpg"
        bad.write_bytes(b"not a real image")
        ok, err = validate_photo_resolution(bad)
        assert not ok
        assert "no se pudo leer" in err.lower()


class TestValidatePhotoUpload:
    """Validación combinada usada por el wizard de productos."""

    def test_all_ok(self, jpeg_path):
        ok, _ = validate_photo_upload(
            filename=jpeg_path.name, num_bytes=jpeg_path.stat().st_size,
            photo_path=jpeg_path, min_px=512,
        )
        assert ok

    def test_bad_extension_short_circuits(self, tmp_path):
        gif = tmp_path / "x.gif"
        gif.write_bytes(b"GIF89a")
        ok, err = validate_photo_upload(filename="x.gif", num_bytes=10, photo_path=gif)
        assert not ok
        assert "no soportado" in err.lower()

    def test_too_big(self, jpeg_path):
        ok, err = validate_photo_upload(
            filename=jpeg_path.name, num_bytes=10 * 1024 * 1024,
        )
        assert not ok
        assert "máximo" in err.lower()

    def test_low_res(self, small_jpeg_path):
        ok, err = validate_photo_upload(
            filename=small_jpeg_path.name,
            num_bytes=small_jpeg_path.stat().st_size,
            photo_path=small_jpeg_path,
            min_px=1024,  # <1024 falla
        )
        assert not ok
        assert "resolución" in err.lower()

    def test_skips_resolution_if_no_path(self):
        # Solo extensión + tamaño cuando no hay archivo en disco aún
        ok, _ = validate_photo_upload(filename="x.jpg", num_bytes=1000)
        assert ok


class TestRequireNonEmpty:
    def test_empty_string(self):
        ok, err = require_non_empty("", "Nombre")
        assert not ok
        assert "obligatorio" in err
        assert "Nombre" in err

    def test_only_spaces(self):
        ok, err = require_non_empty("   ", "Nombre")
        assert not ok

    def test_none(self):
        ok, _ = require_non_empty(None, "Nombre")
        assert not ok

    def test_valid(self):
        ok, _ = require_non_empty("hello", "Nombre")
        assert ok
