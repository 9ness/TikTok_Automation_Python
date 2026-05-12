"""Tests del router 🏛️ Presidentes Top 5."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# ENQUEUE
# ---------------------------------------------------------------------------
class TestPresidentsEnqueue:
    def test_enqueue_single_minimal(
        self, app_client: TestClient, fake_job_queue
    ):
        r = app_client.post(
            "/api/v1/creator-reward/presidents/enqueue",
            json={"items": [{"topic": "worst", "top_count": 5}]},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["total_enqueued"] == 1
        assert len(body["jobs"]) == 1
        job = body["jobs"][0]
        assert job["job_id"]
        assert "worst" in job["title"]
        assert job["position_in_queue"] == 0
        # En la cola
        from src.queue.models import JobMode
        all_jobs = fake_job_queue.get_all()
        assert len(all_jobs) == 1
        assert all_jobs[0].mode == JobMode.PRESIDENTS
        # Params del job correctos
        params = all_jobs[0].params
        assert params["topic"] == "worst"
        assert params["top_count"] == 5
        assert params["title_prefix"] == "The 5"
        assert params["engine_version"] == "v2_estable"
        assert params["subs_enabled"] is False  # default
        assert params["hook_enabled"] is False  # default

    def test_enqueue_random_topic(self, app_client: TestClient, fake_job_queue):
        r = app_client.post(
            "/api/v1/creator-reward/presidents/enqueue",
            json={"items": [{"top_count": 3, "prefix": "Top"}]},
        )
        assert r.status_code == 201
        params = fake_job_queue.get_all()[0].params
        assert params["topic"] is None
        assert params["title_prefix"] == "Top 3"
        assert "Aleatorio" in fake_job_queue.get_all()[0].title

    def test_enqueue_batch_5_items(
        self, app_client: TestClient, fake_job_queue
    ):
        items = [{"topic": f"theme_{i}", "top_count": 5} for i in range(5)]
        r = app_client.post(
            "/api/v1/creator-reward/presidents/enqueue",
            json={"items": items, "creative_mode": True},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["total_enqueued"] == 5
        assert len(fake_job_queue.get_all()) == 5
        # creative_mode propagado
        assert all(j.params["creative_mode"] for j in fake_job_queue.get_all())
        # position_in_queue es 0,1,2,3,4
        positions = [j["position_in_queue"] for j in body["jobs"]]
        assert positions == [0, 1, 2, 3, 4]

    def test_enqueue_with_subs_and_hook(
        self, app_client: TestClient, fake_job_queue
    ):
        r = app_client.post(
            "/api/v1/creator-reward/presidents/enqueue",
            json={
                "items": [{"topic": "richest", "top_count": 5}],
                "subs": {
                    "enabled": True,
                    "font_choice": "Rubik Bold (CapCut)",
                    "highlight_color": "#22D3EE",
                    "case_mode": "UPPERCASE",
                    "font_scale": 0.045,
                    "max_words": 3,
                    "y_position": 0.78,
                    "highlight_mode": "color_swap",
                },
                "hook": {
                    "enabled": True,
                    "duration": 5.0,
                    "animation": "swipe_left",
                    "y_position": 0.20,
                    "shadow_color": "#FF0000",
                    "box_color": "#FFFFFF",
                    "text_color": "#000000",
                    "font_scale": 0.025,
                },
            },
        )
        assert r.status_code == 201, r.text
        params = fake_job_queue.get_all()[0].params
        assert params["subs_enabled"] is True
        assert params["subs_highlight_color"] == "#22D3EE"
        assert params["subs_font_path"] == "Rubik-Bold.ttf"
        assert params["subs_highlight_mode"] == "color_swap"
        assert params["hook_enabled"] is True
        assert params["hook_animation"] == "swipe_left"

    def test_enqueue_invalid_top_count(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/creator-reward/presidents/enqueue",
            json={"items": [{"top_count": 7}]},
        )
        assert r.status_code == 422

    def test_enqueue_empty_items_fails(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/creator-reward/presidents/enqueue",
            json={"items": []},
        )
        assert r.status_code == 422

    def test_enqueue_too_many_items(self, app_client: TestClient):
        items = [{"top_count": 5} for _ in range(11)]
        r = app_client.post(
            "/api/v1/creator-reward/presidents/enqueue",
            json={"items": items},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# PRESETS — patcheamos configs_store
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_configs_store(monkeypatch: pytest.MonkeyPatch):
    """Reemplaza configs_store con un dict in-memory."""
    import src.configs_store as cs
    storage: dict[str, dict] = {}

    monkeypatch.setattr(cs, "is_available", lambda: True)
    monkeypatch.setattr(cs, "save_config", lambda name, config: (storage.update({name: dict(config)}), True)[1])
    monkeypatch.setattr(cs, "load_config", lambda name: storage.get(name))
    monkeypatch.setattr(cs, "list_configs", lambda: sorted(storage.keys()))
    def _delete(name):
        storage.pop(name, None)
        return True
    monkeypatch.setattr(cs, "delete_config", _delete)

    return storage


class TestPresidentsPresets:
    def test_list_empty(self, app_client: TestClient, fake_configs_store):
        r = app_client.get("/api/v1/creator-reward/presidents/presets")
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0}

    def test_list_when_redis_unavailable(self, app_client: TestClient, monkeypatch):
        import src.configs_store as cs
        monkeypatch.setattr(cs, "is_available", lambda: False)
        r = app_client.get("/api/v1/creator-reward/presidents/presets")
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0}

    def test_save_and_get(self, app_client: TestClient, fake_configs_store):
        cfg = {
            "subs_enabled": True,
            "subs_highlight_color": "#FF00FF",
            "hook_enabled": False,
        }
        r = app_client.put(
            "/api/v1/creator-reward/presidents/presets/mi_preset",
            json=cfg,
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "mi_preset"
        assert r.json()["config"] == cfg
        # Y se persistió
        g = app_client.get("/api/v1/creator-reward/presidents/presets/mi_preset")
        assert g.status_code == 200
        assert g.json()["config"] == cfg

    def test_get_missing(self, app_client: TestClient, fake_configs_store):
        r = app_client.get("/api/v1/creator-reward/presidents/presets/missing")
        assert r.status_code == 404
        assert r.json()["code"] == "preset_not_found"

    def test_list_after_save(self, app_client: TestClient, fake_configs_store):
        app_client.put(
            "/api/v1/creator-reward/presidents/presets/preset_a",
            json={"subs_enabled": True},
        )
        app_client.put(
            "/api/v1/creator-reward/presidents/presets/preset_b",
            json={"hook_enabled": True},
        )
        r = app_client.get("/api/v1/creator-reward/presidents/presets")
        body = r.json()
        assert body["total"] == 2
        assert sorted(body["items"]) == ["preset_a", "preset_b"]

    def test_delete(self, app_client: TestClient, fake_configs_store):
        app_client.put(
            "/api/v1/creator-reward/presidents/presets/del_me",
            json={"x": 1},
        )
        r = app_client.delete("/api/v1/creator-reward/presidents/presets/del_me")
        assert r.status_code == 204
        # Ya no existe
        g = app_client.get("/api/v1/creator-reward/presidents/presets/del_me")
        assert g.status_code == 404

    def test_delete_missing(self, app_client: TestClient, fake_configs_store):
        r = app_client.delete("/api/v1/creator-reward/presidents/presets/missing")
        assert r.status_code == 404

    def test_save_when_redis_unavailable(
        self, app_client: TestClient, monkeypatch
    ):
        import src.configs_store as cs
        monkeypatch.setattr(cs, "is_available", lambda: False)
        r = app_client.put(
            "/api/v1/creator-reward/presidents/presets/x",
            json={"a": 1},
        )
        assert r.status_code == 500
