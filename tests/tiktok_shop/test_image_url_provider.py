"""Tests del image_url_provider: base64 unificado para los 3 tiers."""

import pytest

from src.tiktok_shop.utils.image_url_provider import (
    get_atlas_image_ref,
    get_atlas_image_refs,
    to_base64_data_uri,
)


class TestGetAtlasImageRef:
    @pytest.mark.parametrize("tier", ["standard", "advanced", "pro"])
    def test_returns_data_uri_for_all_tiers(self, jpeg_path, tier: str):
        ref = get_atlas_image_ref(jpeg_path, tier=tier)
        assert ref.startswith("data:image/jpeg;base64,")
        # Sanity: cuerpo no vacío
        body = ref.split("base64,", 1)[1]
        assert len(body) > 100

    def test_jpeg_mime(self, jpeg_path):
        assert get_atlas_image_ref(jpeg_path, tier="standard").startswith("data:image/jpeg;")

    def test_png_mime(self, png_path):
        assert get_atlas_image_ref(png_path, tier="standard").startswith("data:image/png;")

    def test_webp_mime(self, webp_path):
        assert get_atlas_image_ref(webp_path, tier="standard").startswith("data:image/webp;")

    def test_unknown_extension_falls_to_jpeg(self, tmp_path):
        # Archivo .bin con bytes válidos JPEG → caemos a jpeg como default
        p = tmp_path / "weird.bin"
        p.write_bytes(b"\xff\xd8\xff\xe0fakedata")
        assert get_atlas_image_ref(p, tier="pro").startswith("data:image/jpeg;")

    def test_no_extension_falls_to_jpeg(self, tmp_path):
        p = tmp_path / "noext"
        p.write_bytes(b"\xff\xd8\xff\xe0")
        assert get_atlas_image_ref(p, tier="standard").startswith("data:image/jpeg;")

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Photo not found"):
            get_atlas_image_ref(tmp_path / "no_existe.jpg", tier="standard")

    def test_accepts_string_or_path(self, jpeg_path):
        # str y Path equivalen
        ref_str = get_atlas_image_ref(str(jpeg_path), tier="standard")
        ref_path = get_atlas_image_ref(jpeg_path, tier="standard")
        assert ref_str == ref_path

    def test_tier_none_works(self, jpeg_path):
        # tier es opcional (compat con código antiguo)
        ref = get_atlas_image_ref(jpeg_path)
        assert ref.startswith("data:image/jpeg;base64,")


class TestGetAtlasImageRefs:
    def test_maps_list(self, jpeg_path, png_path):
        refs = get_atlas_image_refs([jpeg_path, png_path], tier="pro")
        assert len(refs) == 2
        assert refs[0].startswith("data:image/jpeg;")
        assert refs[1].startswith("data:image/png;")

    def test_empty_list(self):
        assert get_atlas_image_refs([], tier="standard") == []

    def test_one_missing_raises(self, jpeg_path, tmp_path):
        with pytest.raises(FileNotFoundError):
            get_atlas_image_refs([jpeg_path, tmp_path / "x.jpg"], tier="pro")


class TestToBase64DataUri:
    """Helper exposed para compat con código antiguo. Mismo output que ref."""

    def test_equivalent_to_get_atlas_image_ref(self, jpeg_path):
        a = to_base64_data_uri(jpeg_path)
        b = get_atlas_image_ref(jpeg_path)
        assert a == b
