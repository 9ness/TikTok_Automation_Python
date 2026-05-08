"""Tests del servicio de regeneración (FUNC 2)."""

from __future__ import annotations

import pytest

from src.tiktok_shop.models import (
    HookUsed, Product, TikTokUser, VideoCost, VideoGeneration, VoiceUsed,
)
from src.tiktok_shop.services.regenerate_service import (
    build_regen_params,
    build_regen_title,
)


@pytest.fixture
def sample_gen():
    return VideoGeneration(
        user_id="u-1",
        product_id="p-1",
        tier_used="standard",
        model_used="bytedance/seedance-v1.5-pro/image-to-video-fast",
        duration_seconds=15,
        resolution="720p",
        num_clips=3,
        clip_strategy="multi_clip_anchor",
        language="es",
        hook=HookUsed(category="curiosity", text="POV: pruebas..."),
        voice_used=VoiceUsed(voice_id="Spanish_EnergeticBoy", name="ES Energetic"),
        voiceover_script="...",
        video_type="shoppable",
        ai_disclosure=True,
        cost=VideoCost(total=0.275),
    )


@pytest.fixture
def sample_user():
    return TikTokUser(
        username="@test", display_name="Test", niche="fitness",
        language="es", country="ES", default_language="es",
    )


@pytest.fixture
def sample_product():
    return Product(slug="prod_x", name="Producto X")


# ---------------------------------------------------------------------------
# build_regen_params: idéntico (sin overrides)
# ---------------------------------------------------------------------------
class TestBuildRegenParamsIdentical:
    def test_basic_fields_match_original(self, sample_gen, sample_user, sample_product):
        params = build_regen_params(sample_gen, sample_user, sample_product)
        assert params["user_id"] == sample_user.id
        assert params["product_id"] == sample_product.id
        assert params["tier"] == "standard"
        assert params["duration"] == 15
        assert params["resolution"] == "720p"
        assert params["language"] == "es"

    def test_hook_extracted_from_gen(self, sample_gen, sample_user, sample_product):
        params = build_regen_params(sample_gen, sample_user, sample_product)
        assert params["hook_category"] == "curiosity"
        assert params["hook_text"] == "POV: pruebas..."

    def test_voice_extracted_from_gen(self, sample_gen, sample_user, sample_product):
        params = build_regen_params(sample_gen, sample_user, sample_product)
        assert params["voice_id"] == "Spanish_EnergeticBoy"
        assert params["with_voice"] is True

    def test_shoppable_flag_preserved(self, sample_gen, sample_user, sample_product):
        # video_type="shoppable" → is_shoppable=True
        params = build_regen_params(sample_gen, sample_user, sample_product)
        assert params["is_shoppable"] is True

    def test_normal_video_not_shoppable(self, sample_user, sample_product):
        gen = VideoGeneration(
            user_id="u-1", product_id="p-1", tier_used="standard",
            video_type="normal",
        )
        params = build_regen_params(gen, sample_user, sample_product)
        assert params["is_shoppable"] is False

    def test_photo_overrides_default_none(self, sample_gen, sample_user, sample_product):
        # NO se reusan asignaciones de fotos (catálogo puede haber cambiado)
        params = build_regen_params(sample_gen, sample_user, sample_product)
        assert params["clip_photo_overrides"] is None
        assert params["pro_ref_photo_overrides"] is None

    def test_regenerated_from_marker(self, sample_gen, sample_user, sample_product):
        params = build_regen_params(sample_gen, sample_user, sample_product)
        assert params["regenerated_from"] == sample_gen.id

    def test_temp_folder_default(self, sample_gen, sample_user, sample_product):
        params = build_regen_params(sample_gen, sample_user, sample_product)
        assert params["temp_folder"] == "./temp_work"


# ---------------------------------------------------------------------------
# build_regen_params: con overrides
# ---------------------------------------------------------------------------
class TestBuildRegenParamsWithOverrides:
    def test_override_tier(self, sample_gen, sample_user, sample_product):
        params = build_regen_params(
            sample_gen, sample_user, sample_product,
            overrides={"tier": "pro"},
        )
        assert params["tier"] == "pro"
        # El resto se mantiene
        assert params["duration"] == 15

    def test_override_duration_and_resolution(self, sample_gen, sample_user, sample_product):
        params = build_regen_params(
            sample_gen, sample_user, sample_product,
            overrides={"duration": 10, "resolution": "1080p-SR"},
        )
        assert params["duration"] == 10
        assert params["resolution"] == "1080p-SR"

    def test_override_hook(self, sample_gen, sample_user, sample_product):
        params = build_regen_params(
            sample_gen, sample_user, sample_product,
            overrides={"hook_category": "social_proof",
                       "hook_text": "Mi madre lleva 1 mes con esto..."},
        )
        assert params["hook_category"] == "social_proof"
        assert params["hook_text"] == "Mi madre lleva 1 mes con esto..."

    def test_override_clip_assignments(self, sample_gen, sample_user, sample_product):
        params = build_regen_params(
            sample_gen, sample_user, sample_product,
            overrides={"clip_photo_overrides": [2, 0, 1]},
        )
        assert params["clip_photo_overrides"] == [2, 0, 1]

    def test_override_with_voice_off(self, sample_gen, sample_user, sample_product):
        params = build_regen_params(
            sample_gen, sample_user, sample_product,
            overrides={"with_voice": False},
        )
        assert params["with_voice"] is False

    def test_override_preserves_regenerated_from(self, sample_gen, sample_user, sample_product):
        params = build_regen_params(
            sample_gen, sample_user, sample_product,
            overrides={"tier": "advanced"},
        )
        assert params["regenerated_from"] == sample_gen.id


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_gen_without_hook(self, sample_user, sample_product):
        gen = VideoGeneration(
            user_id="u-1", product_id="p-1", tier_used="standard",
            hook=None,
        )
        params = build_regen_params(gen, sample_user, sample_product)
        assert params["hook_category"] == "general"
        assert params["hook_text"] == ""

    def test_gen_without_voice(self, sample_user, sample_product):
        gen = VideoGeneration(
            user_id="u-1", product_id="p-1", tier_used="standard",
            voice_used=None,
        )
        params = build_regen_params(gen, sample_user, sample_product)
        # Cae al default conocido
        assert params["voice_id"] == "Spanish_EnergeticBoy"

    def test_language_fallback_user_default(self, sample_user, sample_product):
        gen = VideoGeneration(
            user_id="u-1", product_id="p-1", tier_used="standard",
            language="",  # vacío
        )
        params = build_regen_params(gen, sample_user, sample_product)
        # Usa default_language del user
        assert params["language"] == "es"


# ---------------------------------------------------------------------------
# build_regen_title
# ---------------------------------------------------------------------------
class TestBuildRegenTitle:
    def test_title_identical(self, sample_gen, sample_user, sample_product):
        title = build_regen_title(
            sample_gen, sample_user, sample_product,
            tier_label="🟢 Seedance v1.5 Pro Fast",
        )
        assert "@test" in title
        assert "Producto X" in title
        assert "🟢 Seedance v1.5 Pro Fast" in title
        assert "🔁 regen" in title
        assert "regen+" not in title  # idéntico, no es con cambios
        assert sample_gen.id[:6] in title  # trazabilidad

    def test_title_with_changes(self, sample_gen, sample_user, sample_product):
        title = build_regen_title(
            sample_gen, sample_user, sample_product,
            tier_label="🔴 Pro", is_with_changes=True,
        )
        assert "🔁 regen+" in title
        assert sample_gen.id[:6] in title
