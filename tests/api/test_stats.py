"""Tests del router /api/v1/stats."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


def _save_gen(
    fake_shop_redis,
    *,
    user_id: str = "u1",
    product_id: str = "p1",
    tier: str = "standard",
    cost_total: float = 0.275,
    created_at: str | None = None,
    deleted: bool = False,
):
    from src.tiktok_shop.models import (
        GenerationStatus,
        VideoCost,
        VideoGeneration,
    )
    from src.tiktok_shop.repos import GenerationRepo

    gen = VideoGeneration(
        user_id=user_id,
        product_id=product_id,
        tier_used=tier,
        duration_seconds=15,
        resolution="720p",
        cost=VideoCost(video_generation=cost_total - 0.005, voice_tts=0.005, total=cost_total),
        generation_status=GenerationStatus.COMPLETED,
        deleted=deleted,
    )
    if created_at:
        gen.created_at = created_at
    GenerationRepo(fake_shop_redis).save(gen)
    return gen


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


# ---------------------------------------------------------------------------
# /stats/monthly
# ---------------------------------------------------------------------------
class TestMonthlyStats:
    def test_monthly_empty(self, app_client: TestClient):
        r = app_client.get("/api/v1/stats/monthly")
        assert r.status_code == 200
        body = r.json()
        assert body["total_cost_usd"] == 0.0
        assert body["total_videos_generated"] == 0
        assert body["cost_by_module"]["tiktok_shop"] == 0.0

    def test_monthly_with_generations(
        self, app_client: TestClient, fake_shop_redis
    ):
        _save_gen(fake_shop_redis, user_id="u1", product_id="p1", tier="standard", cost_total=0.27)
        _save_gen(fake_shop_redis, user_id="u2", product_id="p1", tier="advanced", cost_total=0.71)
        _save_gen(fake_shop_redis, user_id="u1", product_id="p2", tier="pro", cost_total=1.08)

        r = app_client.get("/api/v1/stats/monthly")
        body = r.json()
        assert body["total_videos_generated"] == 3
        assert body["total_cost_usd"] == pytest.approx(2.06, abs=0.001)
        assert body["cost_by_module"]["tiktok_shop"] == pytest.approx(2.06, abs=0.001)
        assert body["cost_by_user"]["u1"] == pytest.approx(0.27 + 1.08)
        assert body["cost_by_user"]["u2"] == pytest.approx(0.71)
        assert set(body["cost_by_tier"].keys()) == {"standard", "advanced", "pro"}
        # daily_breakdown: hoy debe tener 3 vídeos
        assert len(body["daily_breakdown"]) >= 1
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_point = next((p for p in body["daily_breakdown"] if p["date"] == today), None)
        assert today_point is not None
        assert today_point["count"] == 3

    def test_monthly_excludes_deleted(
        self, app_client: TestClient, fake_shop_redis
    ):
        _save_gen(fake_shop_redis, cost_total=1.0)
        _save_gen(fake_shop_redis, cost_total=1.0, deleted=True)
        r = app_client.get("/api/v1/stats/monthly")
        assert r.json()["total_videos_generated"] == 1
        assert r.json()["total_cost_usd"] == pytest.approx(1.0)

    def test_monthly_filter_by_month(
        self, app_client: TestClient, fake_shop_redis
    ):
        # Una de febrero, otra de abril
        _save_gen(fake_shop_redis, cost_total=0.5, created_at="2026-02-15T10:00:00+00:00")
        _save_gen(fake_shop_redis, cost_total=0.5, created_at="2026-04-15T10:00:00+00:00")

        r1 = app_client.get("/api/v1/stats/monthly?month=2026-02")
        body1 = r1.json()
        assert body1["total_videos_generated"] == 1
        assert body1["month"] == "2026-02"

        r2 = app_client.get("/api/v1/stats/monthly?month=2026-04")
        assert r2.json()["total_videos_generated"] == 1

    def test_monthly_invalid_format(self, app_client: TestClient):
        r = app_client.get("/api/v1/stats/monthly?month=2026/05")
        assert r.status_code == 422

    def test_monthly_includes_cr_completed_jobs(
        self, app_client: TestClient, fake_job_queue
    ):
        from src.queue.models import JobMode
        # Encolar y completar 2 jobs de Presidentes en el mes en curso
        for i in range(2):
            j = fake_job_queue.enqueue(JobMode.PRESIDENTS, f"j{i}", {})
            fake_job_queue.set_status(j.id, "completed")
        r = app_client.get("/api/v1/stats/monthly")
        body = r.json()
        # 2 jobs CR + 0 TT Shop = 2 vídeos en total
        assert body["total_videos_generated"] == 2


# ---------------------------------------------------------------------------
# /stats/historical
# ---------------------------------------------------------------------------
class TestHistoricalStats:
    def test_historical_default_12_months(self, app_client: TestClient):
        r = app_client.get("/api/v1/stats/historical")
        assert r.status_code == 200
        body = r.json()
        assert body["total_months"] == 12
        assert len(body["months"]) == 12

    def test_historical_custom_range(self, app_client: TestClient):
        r = app_client.get("/api/v1/stats/historical?months=3")
        body = r.json()
        assert body["total_months"] == 3
        assert len(body["months"]) == 3

    def test_historical_clamp(self, app_client: TestClient):
        r = app_client.get("/api/v1/stats/historical?months=70")
        assert r.status_code == 422  # >60


# ---------------------------------------------------------------------------
# /stats/budget
# ---------------------------------------------------------------------------
class TestBudgetStatus:
    def test_no_budget_configured(self, app_client: TestClient, monkeypatch):
        monkeypatch.delenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD", raising=False)
        r = app_client.get("/api/v1/stats/budget")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "no_budget"
        assert body["monthly_budget_usd"] is None

    def test_budget_status_ok(
        self, app_client: TestClient, fake_shop_redis, monkeypatch
    ):
        monkeypatch.setenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD", "100.0")
        _save_gen(fake_shop_redis, cost_total=10.0)
        r = app_client.get("/api/v1/stats/budget")
        body = r.json()
        assert body["status"] == "ok"
        assert body["percent_used"] == 10.0

    def test_budget_status_warning(
        self, app_client: TestClient, fake_shop_redis, monkeypatch
    ):
        monkeypatch.setenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD", "10.0")
        _save_gen(fake_shop_redis, cost_total=8.5)  # 85%
        r = app_client.get("/api/v1/stats/budget")
        body = r.json()
        assert body["status"] == "warning"

    def test_budget_status_exceeded(
        self, app_client: TestClient, fake_shop_redis, monkeypatch
    ):
        monkeypatch.setenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD", "5.0")
        _save_gen(fake_shop_redis, cost_total=10.0)
        r = app_client.get("/api/v1/stats/budget")
        body = r.json()
        assert body["status"] == "exceeded"
        assert body["percent_used"] == 200.0

    def test_budget_invalid_env_treated_as_no_budget(
        self, app_client: TestClient, monkeypatch
    ):
        monkeypatch.setenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD", "not-a-number")
        r = app_client.get("/api/v1/stats/budget")
        assert r.json()["status"] == "no_budget"

    def test_budget_includes_projection(
        self, app_client: TestClient, fake_shop_redis, monkeypatch
    ):
        monkeypatch.setenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD", "100.0")
        _save_gen(fake_shop_redis, cost_total=10.0)
        r = app_client.get("/api/v1/stats/budget")
        body = r.json()
        # `projected_month_end_cost` siempre >= current_cost (extrapolación lineal)
        assert body["projected_month_end_cost"] >= body["current_month_cost"]
        assert body["days_remaining_in_month"] >= 0
