"""Tests del tier_selector — actual stub + slot para futura heurística."""

from src.tiktok_shop.models import PerformanceHistory, Product, VideoConfig
from src.tiktok_shop.services import recommend_tier


class TestTierSelectorStub:
    """El stub actual devuelve `product.video_config.default_tier`."""

    def test_returns_default_tier(self):
        p = Product(slug="test", name="Test")
        assert recommend_tier(p) == "standard"  # default

    def test_respects_explicit_default_tier_pro(self):
        p = Product(slug="test", name="Test",
                    video_config=VideoConfig(default_tier="pro"))
        assert recommend_tier(p) == "pro"

    def test_respects_explicit_default_tier_advanced(self):
        p = Product(slug="test", name="Test",
                    video_config=VideoConfig(default_tier="advanced"))
        assert recommend_tier(p) == "advanced"

    def test_ignores_performance_history_for_now(self):
        # Aunque haya órdenes generadas, el stub NO sube tier todavía
        p = Product(
            slug="test", name="Test",
            performance_history=PerformanceHistory(
                total_videos_generated=50, total_orders_generated=15,
            ),
        )
        # Stub: respeta default_tier pase lo que pase
        assert recommend_tier(p) == "standard"
