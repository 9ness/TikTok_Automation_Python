"""Tests de los endpoints del histórico de generaciones + encolado."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _create_user(client: TestClient, username: str = "@gen_user") -> dict:
    r = client.post(
        "/api/v1/users",
        json={"username": username, "display_name": "Gen User"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_product(client: TestClient, name: str = "Producto Gen") -> dict:
    r = client.post("/api/v1/products", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _assign(client: TestClient, username: str, product_id: str) -> None:
    r = client.post(
        f"/api/v1/users/{quote(username, safe='')}/products",
        json={"product_id": product_id},
    )
    assert r.status_code == 200, r.text


def _save_generation(
    fake_shop_redis,
    user_id: str,
    product_id: str,
    *,
    tier: str = "standard",
    status_value: str = "completed",
    deleted: bool = False,
    local_path: str | None = None,
    duration: int = 15,
):
    """Crea un VideoGeneration en el FakeRedis directamente (sin pasar por la cola)."""
    from src.tiktok_shop.models import (
        GenerationStatus,
        HookUsed,
        VideoCost,
        VideoGeneration,
        VoiceUsed,
    )
    from src.tiktok_shop.repos import GenerationRepo

    gen = VideoGeneration(
        user_id=user_id,
        product_id=product_id,
        tier_used=tier,
        duration_seconds=duration,
        resolution="720p",
        hook=HookUsed(category="curiosity", text="¿Sabías que…?"),
        voice_used=VoiceUsed(voice_id="Spanish_EnergeticBoy"),
        cost=VideoCost(video_generation=0.27, voice_tts=0.005, total=0.275),
        generation_status=GenerationStatus(status_value),
        local_path=local_path,
        deleted=deleted,
    )
    GenerationRepo(fake_shop_redis).save(gen)
    return gen


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------
class TestListGenerations:
    def test_list_empty(self, app_client: TestClient):
        r = app_client.get("/api/v1/generations")
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}

    def test_list_returns_recent_first(
        self, app_client: TestClient, fake_shop_redis
    ):
        u = _create_user(app_client, username="@gg_user")
        p = _create_product(app_client)
        _save_generation(fake_shop_redis, u["id"], p["id"])
        _save_generation(fake_shop_redis, u["id"], p["id"], tier="advanced")
        r = app_client.get("/api/v1/generations")
        body = r.json()
        assert body["total"] == 2

    def test_list_excludes_deleted_by_default(
        self, app_client: TestClient, fake_shop_redis
    ):
        u = _create_user(app_client, username="@gg_user")
        p = _create_product(app_client)
        _save_generation(fake_shop_redis, u["id"], p["id"])
        _save_generation(fake_shop_redis, u["id"], p["id"], deleted=True)
        r = app_client.get("/api/v1/generations")
        assert r.json()["total"] == 1
        r2 = app_client.get("/api/v1/generations?include_deleted=true")
        assert r2.json()["total"] == 2

    def test_list_filtered_by_status(
        self, app_client: TestClient, fake_shop_redis
    ):
        u = _create_user(app_client, username="@gg_user")
        p = _create_product(app_client)
        _save_generation(fake_shop_redis, u["id"], p["id"], status_value="completed")
        _save_generation(fake_shop_redis, u["id"], p["id"], status_value="failed")
        r = app_client.get("/api/v1/generations?status=failed")
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["generation_status"] == "failed"

    def test_list_filtered_by_username(
        self, app_client: TestClient, fake_shop_redis
    ):
        u1 = _create_user(app_client, username="@u_one")
        u2 = _create_user(app_client, username="@u_two")
        p = _create_product(app_client)
        _save_generation(fake_shop_redis, u1["id"], p["id"])
        _save_generation(fake_shop_redis, u2["id"], p["id"])
        r = app_client.get("/api/v1/generations?username=@u_one")
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["user_id"] == u1["id"]

    def test_list_filtered_by_product(
        self, app_client: TestClient, fake_shop_redis
    ):
        u = _create_user(app_client, username="@gg_user")
        p1 = _create_product(app_client, name="P1")
        p2 = _create_product(app_client, name="P2")
        _save_generation(fake_shop_redis, u["id"], p1["id"])
        _save_generation(fake_shop_redis, u["id"], p2["id"])
        r = app_client.get(f"/api/v1/generations?product_id={p1['id']}")
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["product_id"] == p1["id"]

    def test_list_pagination(
        self, app_client: TestClient, fake_shop_redis
    ):
        u = _create_user(app_client, username="@gg_user")
        p = _create_product(app_client)
        for _ in range(5):
            _save_generation(fake_shop_redis, u["id"], p["id"])
        r = app_client.get("/api/v1/generations?limit=2&offset=1")
        body = r.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------
class TestGetGeneration:
    def test_get_existing(self, app_client: TestClient, fake_shop_redis):
        u = _create_user(app_client, username="@gg_user")
        p = _create_product(app_client)
        gen = _save_generation(fake_shop_redis, u["id"], p["id"])
        r = app_client.get(f"/api/v1/generations/{gen.id}")
        assert r.status_code == 200
        assert r.json()["id"] == gen.id

    def test_get_missing_returns_404(self, app_client: TestClient):
        r = app_client.get("/api/v1/generations/missing")
        assert r.status_code == 404
        assert r.json()["code"] == "generation_not_found"


# ---------------------------------------------------------------------------
# ENQUEUE
# ---------------------------------------------------------------------------
class TestEnqueue:
    def test_enqueue_happy_path(
        self, app_client: TestClient, fake_job_queue
    ):
        u = _create_user(app_client, username="@enq_user")
        p = _create_product(app_client)
        _assign(app_client, "@enq_user", p["id"])
        r = app_client.post(
            "/api/v1/generations/enqueue",
            json={
                "username": "@enq_user",
                "product_id": p["id"],
                "tier": "standard",
                "duration_seconds": 15,
                "resolution": "720p",
                "voice_enabled": True,
                "voice_id": "Spanish_EnergeticBoy",
                "hook_category": "curiosity",
                "shoppable": False,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["job_id"]
        assert body["estimated_cost"] > 0
        assert body["estimated_duration_seconds"] == 15
        assert body["position_in_queue"] == 0
        # El job está en la cola
        all_jobs = fake_job_queue.get_all()
        assert len(all_jobs) == 1
        assert all_jobs[0].id == body["job_id"]

    def test_enqueue_missing_user(self, app_client: TestClient):
        p = _create_product(app_client)
        r = app_client.post(
            "/api/v1/generations/enqueue",
            json={
                "username": "@missing_user",
                "product_id": p["id"],
                "voice_enabled": True,
                "voice_id": "Spanish_EnergeticBoy",
            },
        )
        assert r.status_code == 404
        assert r.json()["code"] == "user_not_found"

    def test_enqueue_missing_product(self, app_client: TestClient):
        _create_user(app_client, username="@enq_user")
        r = app_client.post(
            "/api/v1/generations/enqueue",
            json={
                "username": "@enq_user",
                "product_id": "missing",
                "voice_enabled": True,
                "voice_id": "Spanish_EnergeticBoy",
            },
        )
        assert r.status_code == 404
        assert r.json()["code"] == "product_not_found"

    def test_enqueue_unassigned_product(self, app_client: TestClient):
        _create_user(app_client, username="@enq_user")
        p = _create_product(app_client)
        # NO asignamos
        r = app_client.post(
            "/api/v1/generations/enqueue",
            json={
                "username": "@enq_user",
                "product_id": p["id"],
                "voice_enabled": True,
                "voice_id": "Spanish_EnergeticBoy",
            },
        )
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_enqueue_request"

    def test_enqueue_voice_required_when_enabled(
        self, app_client: TestClient
    ):
        _create_user(app_client, username="@enq_user")
        p = _create_product(app_client)
        _assign(app_client, "@enq_user", p["id"])
        r = app_client.post(
            "/api/v1/generations/enqueue",
            json={
                "username": "@enq_user",
                "product_id": p["id"],
                "voice_enabled": True,
                # falta voice_id
            },
        )
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_enqueue_request"

    def test_enqueue_resolution_not_supported_by_tier(
        self, app_client: TestClient
    ):
        _create_user(app_client, username="@enq_user")
        p = _create_product(app_client)
        _assign(app_client, "@enq_user", p["id"])
        # Standard NO soporta 480p (RESOLUTIONS["480p"]["tiers_supported"]=("advanced","pro"))
        r = app_client.post(
            "/api/v1/generations/enqueue",
            json={
                "username": "@enq_user",
                "product_id": p["id"],
                "tier": "standard",
                "resolution": "480p",
                "voice_enabled": False,
            },
        )
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_enqueue_request"

    def test_enqueue_veo3_no_cost(
        self, app_client: TestClient
    ):
        _create_user(app_client, username="@enq_user")
        p = _create_product(app_client)
        _assign(app_client, "@enq_user", p["id"])
        r = app_client.post(
            "/api/v1/generations/enqueue",
            json={
                "username": "@enq_user",
                "product_id": p["id"],
                "tier": "veo3_prompt_only",
                "duration_seconds": 8,
                "voice_enabled": False,
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["estimated_cost"] == 0.0
        assert r.json()["estimated_duration_seconds"] == 8

    def test_enqueue_position_tracks_pending(
        self, app_client: TestClient, fake_job_queue
    ):
        _create_user(app_client, username="@enq_user")
        p = _create_product(app_client)
        _assign(app_client, "@enq_user", p["id"])
        first = app_client.post(
            "/api/v1/generations/enqueue",
            json={
                "username": "@enq_user",
                "product_id": p["id"],
                "voice_enabled": True,
                "voice_id": "Spanish_EnergeticBoy",
            },
        ).json()
        second = app_client.post(
            "/api/v1/generations/enqueue",
            json={
                "username": "@enq_user",
                "product_id": p["id"],
                "voice_enabled": True,
                "voice_id": "Spanish_EnergeticBoy",
            },
        ).json()
        assert first["position_in_queue"] == 0
        assert second["position_in_queue"] == 1


# ---------------------------------------------------------------------------
# REGENERATE
# ---------------------------------------------------------------------------
class TestRegenerate:
    def test_regenerate_identical(
        self, app_client: TestClient, fake_shop_redis, fake_job_queue
    ):
        u = _create_user(app_client, username="@regen_user")
        p = _create_product(app_client)
        _assign(app_client, "@regen_user", p["id"])
        gen = _save_generation(fake_shop_redis, u["id"], p["id"])
        r = app_client.post(
            f"/api/v1/generations/{gen.id}/regenerate",
            json={"overrides": {}},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["job_id"]
        # El nuevo job tiene `regenerated_from` apuntando al original
        new_job = next(j for j in fake_job_queue.get_all() if j.id == body["job_id"])
        assert new_job.params["regenerated_from"] == gen.id
        assert new_job.params["tier"] == "standard"

    def test_regenerate_with_overrides(
        self, app_client: TestClient, fake_shop_redis, fake_job_queue
    ):
        u = _create_user(app_client, username="@regen_user")
        p = _create_product(app_client)
        _assign(app_client, "@regen_user", p["id"])
        gen = _save_generation(fake_shop_redis, u["id"], p["id"], tier="standard")
        r = app_client.post(
            f"/api/v1/generations/{gen.id}/regenerate",
            json={"overrides": {"tier": "advanced", "duration": 10}},
        )
        assert r.status_code == 201
        body = r.json()
        new_job = next(j for j in fake_job_queue.get_all() if j.id == body["job_id"])
        assert new_job.params["tier"] == "advanced"
        assert new_job.params["duration"] == 10

    def test_regenerate_invalid_override_tier(
        self, app_client: TestClient, fake_shop_redis
    ):
        u = _create_user(app_client, username="@regen_user")
        p = _create_product(app_client)
        gen = _save_generation(fake_shop_redis, u["id"], p["id"])
        r = app_client.post(
            f"/api/v1/generations/{gen.id}/regenerate",
            json={"overrides": {"tier": "fake_tier"}},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_enqueue_request"

    def test_regenerate_missing_returns_404(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/generations/missing/regenerate",
            json={"overrides": {}},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE (soft)
# ---------------------------------------------------------------------------
class TestDeleteGeneration:
    def test_soft_delete(self, app_client: TestClient, fake_shop_redis):
        u = _create_user(app_client, username="@gg_user")
        p = _create_product(app_client)
        gen = _save_generation(fake_shop_redis, u["id"], p["id"])
        r = app_client.delete(f"/api/v1/generations/{gen.id}")
        assert r.status_code == 204
        g = app_client.get(f"/api/v1/generations/{gen.id}")
        assert g.status_code == 200
        assert g.json()["deleted"] is True

    def test_delete_missing(self, app_client: TestClient):
        r = app_client.delete("/api/v1/generations/missing")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# STREAM VIDEO
# ---------------------------------------------------------------------------
class TestStreamVideo:
    def test_stream_existing_file(
        self, app_client: TestClient, fake_shop_redis, tmp_path: Path
    ):
        u = _create_user(app_client, username="@gg_user")
        p = _create_product(app_client)
        video_path = tmp_path / "out.mp4"
        video_path.write_bytes(b"\x00\x00\x00\x18ftypmp42")  # marker MP4
        gen = _save_generation(
            fake_shop_redis, u["id"], p["id"], local_path=str(video_path)
        )
        r = app_client.get(f"/api/v1/generations/{gen.id}/video")
        assert r.status_code == 200
        assert r.headers["content-type"] == "video/mp4"
        assert b"ftypmp42" in r.content

    def test_stream_no_local_path(
        self, app_client: TestClient, fake_shop_redis
    ):
        u = _create_user(app_client, username="@gg_user")
        p = _create_product(app_client)
        gen = _save_generation(fake_shop_redis, u["id"], p["id"], local_path=None)
        r = app_client.get(f"/api/v1/generations/{gen.id}/video")
        assert r.status_code == 404
        assert r.json()["code"] == "video_file_not_found"

    def test_stream_file_does_not_exist_on_disk(
        self, app_client: TestClient, fake_shop_redis
    ):
        u = _create_user(app_client, username="@gg_user")
        p = _create_product(app_client)
        gen = _save_generation(
            fake_shop_redis, u["id"], p["id"], local_path="/nonexistent/path.mp4"
        )
        r = app_client.get(f"/api/v1/generations/{gen.id}/video")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# METADATA
# ---------------------------------------------------------------------------
class TestVideoMetadata:
    def test_metadata_basic(
        self, app_client: TestClient, fake_shop_redis, tmp_path: Path
    ):
        u = _create_user(app_client, username="@gg_user")
        p = _create_product(app_client)
        video = tmp_path / "out.mp4"
        video.write_bytes(b"x" * 1234)
        gen = _save_generation(
            fake_shop_redis, u["id"], p["id"],
            local_path=str(video), duration=10,
        )
        r = app_client.get(f"/api/v1/generations/{gen.id}/metadata")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["generation_id"] == gen.id
        assert body["duration_seconds"] == 10
        assert body["resolution"] == "720p"
        assert body["file_size_bytes"] == 1234
        assert body["voice_id"] == "Spanish_EnergeticBoy"
        assert body["cost"]["total"] == 0.275

    def test_metadata_no_local_file(
        self, app_client: TestClient, fake_shop_redis
    ):
        u = _create_user(app_client, username="@gg_user")
        p = _create_product(app_client)
        gen = _save_generation(fake_shop_redis, u["id"], p["id"], local_path=None)
        r = app_client.get(f"/api/v1/generations/{gen.id}/metadata")
        assert r.status_code == 200
        body = r.json()
        assert body["file_size_bytes"] is None

    def test_metadata_missing_returns_404(self, app_client: TestClient):
        r = app_client.get("/api/v1/generations/missing/metadata")
        assert r.status_code == 404
