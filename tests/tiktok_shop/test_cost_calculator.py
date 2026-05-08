"""Tests del cost_calculator: tarifas por tier × resolución × voz on/off."""

import pytest

from src.tiktok_shop.services.cost_calculator import (
    MINIMAX_TTS_USD_PER_1K_CHARS,
    actual_cost_from_response,
    estimate_cost,
    estimate_video_cost,
    estimate_voice_cost,
)


# ---------------------------------------------------------------------------
# Coste de vídeo por tier (rates per doc oficial)
# ---------------------------------------------------------------------------
class TestVideoCost:
    def test_standard_15s_720p(self):
        # $0.018/seg × 15s × 1.0 = $0.27
        assert estimate_video_cost("standard", 15, "720p") == 0.27

    def test_advanced_15s_720p(self):
        # $0.047/seg × 15s × 1.0 = $0.705 (round: 0.705)
        assert abs(estimate_video_cost("advanced", 15, "720p") - 0.705) < 0.001

    def test_pro_15s_720p(self):
        # $0.072/seg × 15s × 1.0 = $1.08
        assert estimate_video_cost("pro", 15, "720p") == 1.08

    def test_advanced_10s_480p(self):
        # $0.047 × 10 × 0.7 = $0.329
        assert abs(estimate_video_cost("advanced", 10, "480p") - 0.329) < 0.001

    def test_pro_15s_1080p_sr(self):
        # $0.072 × 15 × 1.5 = $1.62
        assert estimate_video_cost("pro", 15, "1080p-SR") == 1.62

    def test_pro_15s_1440p_sr(self):
        # $0.072 × 15 × 2.0 = $2.16
        assert estimate_video_cost("pro", 15, "1440p-SR") == 2.16

    def test_resolution_unknown_uses_default_1x(self):
        # Resolución desconocida → multiplier 1.0
        assert estimate_video_cost("standard", 10, "999p") == 0.18  # 0.018 × 10 × 1.0

    def test_tier_unknown_returns_zero(self):
        # Tier no registrado → 0 (defensivo, no rompe el flow)
        assert estimate_video_cost("inexistente", 15, "720p") == 0.0

    def test_prompt_only_tiers_zero_cost(self):
        # veo3 y nano_banana son prompt-only → cost_per_second 0
        assert estimate_video_cost("veo3_prompt_only", 8, "720p") == 0.0
        assert estimate_video_cost("nano_banana_prompt_only", 0, "720p") == 0.0

    def test_zero_duration(self):
        assert estimate_video_cost("standard", 0, "720p") == 0.0

    @pytest.mark.parametrize("duration", [5, 10, 12, 15, 20, 24, 25, 30])
    def test_standard_duration_scales_linearly(self, duration: int):
        assert estimate_video_cost("standard", duration, "720p") == round(0.018 * duration, 4)


# ---------------------------------------------------------------------------
# Coste de voz MiniMax
# ---------------------------------------------------------------------------
class TestVoiceCost:
    def test_rate_per_1k_chars_per_doc(self):
        # Doc oficial: speech-02-turbo = $0.06 / 1000 chars
        assert MINIMAX_TTS_USD_PER_1K_CHARS == 0.06

    def test_voice_80_chars(self):
        # 80 chars × 0.00006 = $0.0048
        assert estimate_voice_cost(80) == 0.0048

    def test_voice_accepts_string(self):
        assert estimate_voice_cost("hello" * 16) == 0.0048  # 80 chars

    def test_voice_accepts_int(self):
        assert estimate_voice_cost(80) == 0.0048

    def test_voice_empty(self):
        assert estimate_voice_cost(0) == 0.0
        assert estimate_voice_cost("") == 0.0

    def test_voice_none_safe(self):
        # int o None → 0
        assert estimate_voice_cost(None) == 0.0


# ---------------------------------------------------------------------------
# estimate_cost (combinado video + voz, con/sin voz)
# ---------------------------------------------------------------------------
class TestEstimateCost:
    def test_with_voice(self):
        c = estimate_cost(tier="standard", duration=15, resolution="720p",
                          voice_chars=80, with_voice=True)
        assert c["video_generation"] == 0.27
        assert c["voice_tts"] == 0.0048
        assert c["total"] == 0.2748

    def test_without_voice(self):
        c = estimate_cost(tier="standard", duration=15, resolution="720p",
                          voice_chars=80, with_voice=False)
        assert c["voice_tts"] == 0.0
        assert c["total"] == 0.27

    def test_without_voice_ignores_chars(self):
        # with_voice=False ignora voice_chars (no cobra aunque el guion sea largo)
        c = estimate_cost(tier="pro", duration=15, resolution="720p",
                          voice_chars=10000, with_voice=False)
        assert c["voice_tts"] == 0.0
        assert c["total"] == c["video_generation"]

    def test_returns_three_keys(self):
        c = estimate_cost(tier="standard", duration=5, resolution="720p", voice_chars=0)
        assert set(c.keys()) == {"video_generation", "voice_tts", "total"}

    def test_total_is_sum_of_parts(self):
        c = estimate_cost(tier="advanced", duration=10, resolution="720p",
                          voice_chars=200, with_voice=True)
        assert c["total"] == round(c["video_generation"] + c["voice_tts"], 4)


# ---------------------------------------------------------------------------
# actual_cost_from_response: recálculo con valores reales tras completar
# ---------------------------------------------------------------------------
class TestActualCost:
    def test_actual_matches_estimate_when_same_inputs(self):
        est = estimate_cost(tier="standard", duration=15, resolution="720p",
                            voice_chars=200, with_voice=True)
        act = actual_cost_from_response(tier="standard", actual_duration=15,
                                        resolution="720p", actual_voice_chars=200)
        assert act == est

    def test_actual_with_zero_voice_chars(self):
        act = actual_cost_from_response(tier="pro", actual_duration=15,
                                        resolution="720p", actual_voice_chars=0)
        # Si chars=0, with_voice=False internamente → voice_tts=0
        assert act["voice_tts"] == 0.0
        assert act["video_generation"] == 1.08
