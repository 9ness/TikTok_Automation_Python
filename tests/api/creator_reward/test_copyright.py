"""Tests del router 🛡️ Quitar Copy."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _fake_video_bytes() -> bytes:
    """16 bytes con header MP4 plausible — suficiente para los tests
    (no se reproduce ni decodifica)."""
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8


class TestCopyrightEnqueue:
    def test_enqueue_happy_path(
        self, app_client: TestClient, fake_job_queue
    ):
        r = app_client.post(
            "/api/v1/creator-reward/copyright/enqueue",
            files={"file": ("test.mp4", _fake_video_bytes(), "video/mp4")},
            data={
                "clean_mode": "Subtítulos Virales",
                "hook_y_pct": "0.20",
                "hook_color": "#FDD002",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["job_id"]
        assert "test.mp4" in body["title"]
        assert body["position_in_queue"] == 0
        assert body["input_path_relative"].startswith("api_uploads/copyright/")
        assert body["input_path_relative"].endswith(".mp4")

        from src.queue.models import JobMode
        all_jobs = fake_job_queue.get_all()
        assert len(all_jobs) == 1
        assert all_jobs[0].mode == JobMode.COPYRIGHT
        params = all_jobs[0].params
        assert params["clean_mode"] == "Subtítulos Virales"
        assert params["hook_y_pct"] == 0.20
        assert params["hook_color"] == "#FDD002"
        # input_path absoluto en disco, dentro de temp_root
        assert Path(params["input_path"]).exists()

    def test_enqueue_camuflaje_mode(
        self, app_client: TestClient, fake_job_queue
    ):
        r = app_client.post(
            "/api/v1/creator-reward/copyright/enqueue",
            files={"file": ("video.mov", _fake_video_bytes(), "video/quicktime")},
            data={
                "clean_mode": "Camuflaje Geométrico (Sin Subtítulos)",
                "hook_y_pct": "0.45",
                "hook_color": "#FFFFFF",
            },
        )
        assert r.status_code == 201
        params = fake_job_queue.get_all()[0].params
        assert params["clean_mode"] == "Camuflaje Geométrico (Sin Subtítulos)"
        assert params["hook_y_pct"] == 0.45

    def test_enqueue_invalid_extension(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/creator-reward/copyright/enqueue",
            files={"file": ("video.avi", b"\x00" * 100, "video/avi")},
            data={"clean_mode": "Subtítulos Virales", "hook_y_pct": "0.20"},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "validation_error"

    def test_enqueue_empty_file(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/creator-reward/copyright/enqueue",
            files={"file": ("video.mp4", b"", "video/mp4")},
            data={"clean_mode": "Subtítulos Virales", "hook_y_pct": "0.20"},
        )
        assert r.status_code == 422

    def test_enqueue_invalid_clean_mode(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/creator-reward/copyright/enqueue",
            files={"file": ("video.mp4", _fake_video_bytes(), "video/mp4")},
            data={"clean_mode": "OtroModo", "hook_y_pct": "0.20"},
        )
        assert r.status_code == 422

    def test_enqueue_invalid_hook_y_pct(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/creator-reward/copyright/enqueue",
            files={"file": ("video.mp4", _fake_video_bytes(), "video/mp4")},
            data={"clean_mode": "Subtítulos Virales", "hook_y_pct": "0.99"},
        )
        assert r.status_code == 422
