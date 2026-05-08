"""Tests de los modelos Pydantic + helpers."""

import pytest

from src.tiktok_shop.models import (
    GenerationStatus,
    Product,
    ProductPhoto,
    ProductPhotos,
    TikTokUser,
    VideoCost,
    VideoGeneration,
)
from src.tiktok_shop.models.product import slugify


class TestSlugify:
    @pytest.mark.parametrize("name,expected", [
        ("Primal Pump - Gominolas Creatina", "primal_pump_gominolas_creatina"),
        ("Hello World", "hello_world"),
        ("Café con Ñoño",                   "cafe_con_nono"),
        ("UPPERCASE",                       "uppercase"),
        ("with-dashes-and_under",           "with_dashes_and_under"),
        ("123 numbers 456",                 "123_numbers_456"),
        ("single",                          "single"),
        ("  spaced  ",                      "spaced"),
        ("",                                "producto"),  # fallback
        ("!@#$%",                           "producto"),  # solo símbolos
    ])
    def test_slugify_cases(self, name: str, expected: str):
        assert slugify(name) == expected

    def test_slugify_idempotent(self):
        # slugify(slugify(x)) == slugify(x)
        for name in ["Foo Bar", "TEST_123", "café"]:
            assert slugify(slugify(name)) == slugify(name)


class TestProductPhotos:
    def test_default_empty(self):
        ph = ProductPhotos()
        assert ph.source == []
        assert ph.generated == []

    def test_best_available_prefers_generated(self):
        ph = ProductPhotos(
            source=[ProductPhoto(filename="src.jpg")],
            generated=[ProductPhoto(filename="gen.jpg", type="packshot")],
        )
        photos, origin = ph.best_available()
        assert origin == "generated"
        assert photos[0].filename == "gen.jpg"

    def test_best_available_falls_back_to_source(self):
        ph = ProductPhotos(source=[ProductPhoto(filename="src.jpg")])
        photos, origin = ph.best_available()
        assert origin == "source"
        assert photos[0].filename == "src.jpg"

    def test_best_available_both_empty(self):
        ph = ProductPhotos()
        photos, origin = ph.best_available()
        assert origin == "source"
        assert photos == []


class TestProductValidation:
    def test_slug_required_lowercase(self):
        with pytest.raises(ValueError, match="slug inválido"):
            Product(slug="UpperCase", name="X")

    def test_slug_no_spaces(self):
        with pytest.raises(ValueError, match="slug inválido"):
            Product(slug="with spaces", name="X")

    def test_slug_no_special_chars(self):
        with pytest.raises(ValueError, match="slug inválido"):
            Product(slug="with!sym", name="X")

    def test_slug_empty_rejected(self):
        with pytest.raises(ValueError):
            Product(slug="", name="X")

    def test_slug_valid_underscore(self):
        p = Product(slug="valid_slug_123", name="X")
        assert p.slug == "valid_slug_123"

    def test_default_video_config_tier_standard(self):
        p = Product(slug="x", name="X")
        assert p.video_config.default_tier == "standard"


class TestTikTokUser:
    def test_default_pilot_state(self):
        u = TikTokUser(username="@x", display_name="X")
        assert u.status == "pilot"
        assert u.pilot_program.weekly_shoppable_remaining == 5
        assert u.creator_health_rating == 200
        assert u.default_video_tier == "standard"

    def test_touch_updates_timestamp(self):
        u = TikTokUser(username="@x", display_name="X")
        original = u.updated_at
        import time
        time.sleep(0.01)
        u.touch()
        assert u.updated_at != original


class TestVideoGeneration:
    def test_default_status_pending(self):
        g = VideoGeneration(user_id="u", product_id="p", tier_used="standard")
        assert g.generation_status == GenerationStatus.PENDING

    def test_status_enum_values(self):
        # Sanity: los valores que usa la app
        assert GenerationStatus.MANUAL_PENDING.value == "manual_pending"
        assert GenerationStatus.MANUAL_COMPLETED.value == "manual_completed"
        assert GenerationStatus.COMPLETED.value == "completed"
        assert GenerationStatus.FAILED.value == "failed"

    def test_video_cost_recompute(self):
        c = VideoCost(video_generation=0.27, voice_tts=0.005, other=0.001)
        c.recompute_total()
        assert c.total == 0.276

    def test_estimated_and_actual_independent(self):
        c = VideoCost(estimated_at_creation=0.30, actual_after_completion=0.27,
                      total=0.27)
        assert c.estimated_at_creation == 0.30
        assert c.actual_after_completion == 0.27
        assert c.total == 0.27
