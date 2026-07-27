"""Tests del router 🚀 Viralización (Programa 4 — Tiktok Shop AI Pro)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


class TestPonentesEndpoint:
    def test_list_ponentes_ok(self, app_client: TestClient, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "src.viralizacion.config.ponente_audio_files",
            lambda slug: [f"audio_{i}.mp3" for i in range(3)],
        )
        monkeypatch.setattr(
            "src.viralizacion.services.allocator.count_available_hooks",
            lambda slug: (10, 20),
        )
        monkeypatch.setattr(
            "src.viralizacion.services.allocator.count_available_paisajes",
            lambda slug: (100, 200),
        )
        r = app_client.get("/api/v1/viralizacion/ponentes")
        assert r.status_code == 200, r.text
        body = r.json()
        slugs = {item["slug"] for item in body["items"]}
        assert slugs == {"pablo", "victor"}
        for item in body["items"]:
            assert item["n_audios"] == 3
            assert item["hooks_available"] == 10
            assert item["hooks_total"] == 20
            assert item["paisajes_available"] == 100
            assert item["paisajes_total"] == 200


class TestGenerateEndpoint:
    def test_generate_happy_path(
        self, app_client: TestClient, fake_job_queue, monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            "src.viralizacion.pipeline.batch.preflight_check",
            lambda ponentes, cantidad: [],
        )
        r = app_client.post(
            "/api/v1/viralizacion/generate",
            json={
                "ponentes": ["pablo"],
                "cantidad": {"pablo": 5},
                "nombre_cuenta": "pepito",
                "music_rounds": 1,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["job_id"]
        assert body["total_videos"] == 5
        assert body["position_in_queue"] == 0

        from src.queue.models import JobMode
        all_jobs = fake_job_queue.get_all()
        assert len(all_jobs) == 1
        job = all_jobs[0]
        assert job.mode == JobMode.VIRALIZACION_BATCH
        assert job.params["ponentes"] == ["pablo"]
        assert job.params["cantidad"] == {"pablo": 5}
        assert job.params["nombre_cuenta"] == "pepito"
        assert job.params["music_rounds"] == 1

    def test_generate_empty_ponentes_rejected(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/viralizacion/generate",
            json={"ponentes": [], "cantidad": {}, "nombre_cuenta": "x", "music_rounds": 1},
        )
        assert r.status_code in (400, 422)

    def test_generate_zero_cantidad_rejected(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/viralizacion/generate",
            json={
                "ponentes": ["pablo"],
                "cantidad": {"pablo": 0},
                "nombre_cuenta": "x",
                "music_rounds": 1,
            },
        )
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_enqueue_request"

    def test_generate_pool_exhausted_surfaces_error(
        self, app_client: TestClient, monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            "src.viralizacion.pipeline.batch.preflight_check",
            lambda ponentes, cantidad: ["'pablo': pool de gancho insuficiente — pedidos 5, disponibles 2."],
        )
        r = app_client.post(
            "/api/v1/viralizacion/generate",
            json={
                "ponentes": ["pablo"],
                "cantidad": {"pablo": 5},
                "nombre_cuenta": "x",
                "music_rounds": 1,
            },
        )
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_enqueue_request"
        assert "pool de gancho" in r.json()["error"]
