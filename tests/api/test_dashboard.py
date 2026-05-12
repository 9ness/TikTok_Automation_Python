"""Tests del router /api/v1/dashboard."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _create_user(client: TestClient, username: str = "@dash_user") -> dict:
    r = client.post(
        "/api/v1/users",
        json={"username": username, "display_name": "Dash"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_product(client: TestClient, name: str = "P") -> dict:
    r = client.post("/api/v1/products", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _save_gen(fake_shop_redis, user_id: str, product_id: str, cost: float = 0.275):
    from src.tiktok_shop.models import (
        GenerationStatus,
        VideoCost,
        VideoGeneration,
    )
    from src.tiktok_shop.repos import GenerationRepo

    gen = VideoGeneration(
        user_id=user_id,
        product_id=product_id,
        tier_used="standard",
        cost=VideoCost(video_generation=cost - 0.005, voice_tts=0.005, total=cost),
        generation_status=GenerationStatus.COMPLETED,
    )
    GenerationRepo(fake_shop_redis).save(gen)
    return gen


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
class TestDashboardSummary:
    def test_summary_empty(self, app_client: TestClient):
        r = app_client.get("/api/v1/dashboard/summary")
        assert r.status_code == 200
        body = r.json()
        assert body["total_users"] == 0
        assert body["total_products"] == 0
        assert body["total_videos_this_month"] == 0
        assert body["total_cost_this_month"] == 0.0
        assert body["active_jobs_count"] == 0
        assert body["pending_jobs_count"] == 0
        assert body["running_jobs_count"] == 0
        assert body["recent_videos"] == []
        assert body["pilot_users_summary"] == []
        assert body["alerts"] == []

    def test_summary_with_data(
        self, app_client: TestClient, fake_shop_redis, fake_job_queue
    ):
        u = _create_user(app_client, "@dash_a")
        u2 = _create_user(app_client, "@dash_b")
        p = _create_product(app_client, "Prod1")
        _save_gen(fake_shop_redis, u["id"], p["id"], cost=0.27)
        _save_gen(fake_shop_redis, u2["id"], p["id"], cost=0.71)

        # Encolar un par de jobs
        from src.queue.models import JobMode
        fake_job_queue.enqueue(JobMode.TIKTOK_SHOP, "pending job", {})
        running = fake_job_queue.enqueue(JobMode.PRESIDENTS, "running job", {})
        fake_job_queue.set_status(running.id, "running")

        r = app_client.get("/api/v1/dashboard/summary")
        body = r.json()
        assert body["total_users"] == 2
        assert body["total_products"] == 1
        assert body["total_videos_this_month"] == 2
        assert body["total_cost_this_month"] > 0
        assert body["pending_jobs_count"] == 1
        assert body["running_jobs_count"] == 1
        assert body["active_jobs_count"] == 2
        assert len(body["recent_videos"]) == 2
        assert len(body["pilot_users_summary"]) == 2

    def test_summary_recent_videos_capped_at_5(
        self, app_client: TestClient, fake_shop_redis
    ):
        u = _create_user(app_client, "@cap_u")
        p = _create_product(app_client, "Cap")
        for _ in range(8):
            _save_gen(fake_shop_redis, u["id"], p["id"])
        r = app_client.get("/api/v1/dashboard/summary")
        assert len(r.json()["recent_videos"]) == 5

    def test_summary_excludes_deleted_users_and_products(
        self, app_client: TestClient
    ):
        u = _create_user(app_client, "@del_user")
        p = _create_product(app_client, "DelProd")
        from urllib.parse import quote
        app_client.delete(f"/api/v1/users/{quote('@del_user', safe='')}")
        app_client.delete(f"/api/v1/products/{p['id']}")
        r = app_client.get("/api/v1/dashboard/summary")
        body = r.json()
        assert body["total_users"] == 0
        assert body["total_products"] == 0


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
class TestDashboardAlerts:
    def test_budget_warning_alert(
        self, app_client: TestClient, fake_shop_redis, monkeypatch
    ):
        monkeypatch.setenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD", "10.0")
        _save_gen(fake_shop_redis, "u1", "p1", cost=8.5)
        r = app_client.get("/api/v1/dashboard/summary")
        codes = {a["code"] for a in r.json()["alerts"]}
        assert "budget_warning" in codes

    def test_budget_exceeded_alert(
        self, app_client: TestClient, fake_shop_redis, monkeypatch
    ):
        monkeypatch.setenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD", "5.0")
        _save_gen(fake_shop_redis, "u1", "p1", cost=10.0)
        r = app_client.get("/api/v1/dashboard/summary")
        alerts = r.json()["alerts"]
        codes = {a["code"] for a in alerts}
        assert "budget_exceeded" in codes
        # Severity error
        budget_alert = next(a for a in alerts if a["code"] == "budget_exceeded")
        assert budget_alert["severity"] == "error"

    def test_no_alerts_when_no_budget(self, app_client: TestClient, monkeypatch):
        monkeypatch.delenv("TIKTOK_SHOP_MONTHLY_BUDGET_USD", raising=False)
        r = app_client.get("/api/v1/dashboard/summary")
        codes = {a["code"] for a in r.json()["alerts"]}
        assert "budget_warning" not in codes
        assert "budget_exceeded" not in codes

    def test_recent_failures_alert(
        self, app_client: TestClient, fake_job_queue
    ):
        from src.queue.models import JobMode
        for i in range(4):
            j = fake_job_queue.enqueue(JobMode.TIKTOK_SHOP, f"f{i}", {})
            fake_job_queue.set_status(j.id, "failed")
        r = app_client.get("/api/v1/dashboard/summary")
        codes = {a["code"] for a in r.json()["alerts"]}
        assert "recent_failures" in codes

    def test_pilot_freeze_alert(self, app_client: TestClient):
        # Crear usuario con weekly_shoppable_remaining = 0
        from src.tiktok_shop.models import PilotProgramState, TikTokUser
        from src.tiktok_shop.repos import UserRepo
        from src.tiktok_shop.repos.redis_base import get_shop_redis

        user = TikTokUser(
            username="@frozen",
            display_name="Frozen",
            pilot_program=PilotProgramState(
                weekly_shoppable_remaining=0,
                weekly_shoppable_reset_at="2099-12-31",  # futuro lejano
            ),
        )
        UserRepo(get_shop_redis()).save(user)

        r = app_client.get("/api/v1/dashboard/summary")
        codes = {a["code"] for a in r.json()["alerts"]}
        assert "pilot_freeze" in codes
