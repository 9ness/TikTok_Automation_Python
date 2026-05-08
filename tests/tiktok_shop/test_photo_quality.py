"""Tests del photo_quality: detección de fotos pobres."""

from src.tiktok_shop.utils.photo_quality import (
    any_photo_low_resolution,
    is_low_resolution,
    needs_nano_banana_regeneration,
)


class TestIsLowResolution:
    def test_below_threshold(self, small_jpeg_path):
        # 800×600 → ambos lados <1024 → low res
        assert is_low_resolution(str(small_jpeg_path)) is True

    def test_above_threshold(self, jpeg_path):
        # 1200×800 → 800<1024 → low res (CUALQUIER lado <1024)
        # Nota: el helper marca low-res si MIN(w,h) < umbral. 800<1024 → True.
        assert is_low_resolution(str(jpeg_path)) is True

    def test_truly_high_resolution(self, png_path):
        # 1080×1920 → ambos lados >=1024 → no low res
        assert is_low_resolution(str(png_path)) is False

    def test_missing_path_returns_false(self):
        assert is_low_resolution("/no/existe.jpg") is False

    def test_empty_path_returns_false(self):
        assert is_low_resolution("") is False

    def test_custom_threshold(self, png_path):
        # 1080×1920 → con threshold=1500, 1080<1500 → True
        assert is_low_resolution(str(png_path), threshold_px=1500) is True
        # con threshold=512, 1080>=512 → False
        assert is_low_resolution(str(png_path), threshold_px=512) is False


class TestAnyPhotoLowResolution:
    def test_all_high(self, png_path):
        assert any_photo_low_resolution([str(png_path)]) is False

    def test_one_low(self, png_path, small_jpeg_path):
        assert any_photo_low_resolution([str(png_path), str(small_jpeg_path)]) is True

    def test_empty_list(self):
        assert any_photo_low_resolution([]) is False


class TestNeedsNanoBananaRegeneration:
    def test_gemini_flag_true_short_circuits(self):
        # Si Gemini analyzer dice True, da igual la resolución
        assert needs_nano_banana_regeneration(gemini_flag=True, photo_paths=[]) is True

    def test_only_pil_low_res(self, small_jpeg_path):
        assert needs_nano_banana_regeneration(
            gemini_flag=False, photo_paths=[str(small_jpeg_path)],
        ) is True

    def test_neither_flag(self, png_path):
        assert needs_nano_banana_regeneration(
            gemini_flag=False, photo_paths=[str(png_path)],
        ) is False

    def test_combined_short_circuits_on_first_low(self, png_path, small_jpeg_path):
        # 1 foto low entre varias → True
        assert needs_nano_banana_regeneration(
            gemini_flag=False, photo_paths=[str(png_path), str(small_jpeg_path)],
        ) is True
