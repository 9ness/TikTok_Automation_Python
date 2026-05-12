"""Tests del filtro `?mode=` en /queue y del cleanup de temp_work."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# /queue?mode=
# ---------------------------------------------------------------------------
class TestQueueModeFilter:
    def _enqueue(self, fake_job_queue, mode_value: str, title: str):
        from src.queue.models import JobMode
        return fake_job_queue.enqueue(JobMode(mode_value), title, {"x": 1})

    def test_no_filter_returns_all(self, app_client: TestClient, fake_job_queue):
        self._enqueue(fake_job_queue, "tiktok_shop", "shop job")
        self._enqueue(fake_job_queue, "presidents", "presidents job")
        self._enqueue(fake_job_queue, "pronosticos", "pronosticos job")
        r = app_client.get("/api/v1/queue")
        assert r.status_code == 200
        assert len(r.json()["active_jobs"]) == 3

    def test_filter_single_mode(self, app_client: TestClient, fake_job_queue):
        self._enqueue(fake_job_queue, "tiktok_shop", "shop")
        self._enqueue(fake_job_queue, "presidents", "pres")
        r = app_client.get("/api/v1/queue?mode=tiktok_shop")
        body = r.json()
        assert len(body["active_jobs"]) == 1
        assert body["active_jobs"][0]["mode"] == "tiktok_shop"

    def test_filter_multiple_modes_csv(
        self, app_client: TestClient, fake_job_queue
    ):
        self._enqueue(fake_job_queue, "tiktok_shop", "shop")
        self._enqueue(fake_job_queue, "presidents", "pres")
        self._enqueue(fake_job_queue, "pronosticos", "pron")
        self._enqueue(fake_job_queue, "copyright", "cp")
        r = app_client.get(
            "/api/v1/queue?mode=presidents,pronosticos,copyright,subs_auto"
        )
        body = r.json()
        assert len(body["active_jobs"]) == 3  # los 3 CR (no shop)
        modes = {j["mode"] for j in body["active_jobs"]}
        assert "tiktok_shop" not in modes

    def test_filter_invalid_mode_returns_422(
        self, app_client: TestClient, fake_job_queue
    ):
        self._enqueue(fake_job_queue, "tiktok_shop", "shop")
        r = app_client.get("/api/v1/queue?mode=invalid_mode")
        assert r.status_code == 422
        assert r.json()["code"] == "validation_error"

    def test_finished_limit(self, app_client: TestClient, fake_job_queue):
        from src.queue.models import JobMode
        for i in range(15):
            j = fake_job_queue.enqueue(JobMode.PRESIDENTS, f"job{i}", {})
            fake_job_queue.set_status(j.id, "completed")
        r = app_client.get("/api/v1/queue?finished_limit=10")
        assert r.status_code == 200
        assert len(r.json()["recent_completed"]) == 10

    def test_finished_limit_combined_with_mode(
        self, app_client: TestClient, fake_job_queue
    ):
        from src.queue.models import JobMode
        for _ in range(3):
            j = fake_job_queue.enqueue(JobMode.PRESIDENTS, "p", {})
            fake_job_queue.set_status(j.id, "completed")
        for _ in range(3):
            j = fake_job_queue.enqueue(JobMode.TIKTOK_SHOP, "s", {})
            fake_job_queue.set_status(j.id, "completed")
        r = app_client.get("/api/v1/queue?mode=presidents&finished_limit=10")
        body = r.json()
        assert len(body["recent_completed"]) == 3  # solo PRESIDENTS


# ---------------------------------------------------------------------------
# Cleanup de temp_work
# ---------------------------------------------------------------------------
class TestTempCleanup:
    def test_cleanup_removes_old_uploads(self, tmp_path: Path, monkeypatch):
        from src.api import temp_storage

        monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
        # Forzar `temp_root()` a recalcular (no hay cache; idempotente)

        uploads = tmp_path / "api_uploads" / "test"
        uploads.mkdir(parents=True)

        old_file = uploads / "old.mp4"
        old_file.write_bytes(b"old")
        # mtime hace 25h (fuera del TTL de 24h)
        old_ts = time.time() - 25 * 3600
        os.utime(old_file, (old_ts, old_ts))

        new_file = uploads / "new.mp4"
        new_file.write_bytes(b"new")

        removed, freed = temp_storage.cleanup_expired(ttl_seconds=24 * 3600)
        assert removed == 1
        assert freed == 3
        assert not old_file.exists()
        assert new_file.exists()

    def test_cleanup_with_no_uploads_dir(self, tmp_path: Path, monkeypatch):
        from src.api import temp_storage

        monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
        # Aún sin haber llamado temp_root, la función no debe romper si
        # no hay api_uploads/
        # Como `temp_root()` crea api_uploads, simulamos llamar y luego
        # borrar para testear el branch.
        temp_storage.temp_root()
        (tmp_path / "api_uploads").rmdir()
        removed, freed = temp_storage.cleanup_expired()
        assert removed == 0
        assert freed == 0


# ---------------------------------------------------------------------------
# Path traversal tests
# ---------------------------------------------------------------------------
class TestTempStorageSecurity:
    def test_resolve_relative_rejects_absolute(self, monkeypatch, tmp_path: Path):
        from src.api import temp_storage

        monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
        with pytest.raises(ValueError):
            temp_storage.resolve_relative("/etc/passwd")

    def test_resolve_relative_rejects_traversal(self, monkeypatch, tmp_path: Path):
        from src.api import temp_storage

        monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
        with pytest.raises(ValueError):
            temp_storage.resolve_relative("../../etc/passwd")

    def test_resolve_relative_accepts_valid(self, monkeypatch, tmp_path: Path):
        from src.api import temp_storage

        monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
        # Crear un archivo dentro de temp_root y resolverlo
        target = tmp_path / "api_uploads" / "test" / "x.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"")
        resolved = temp_storage.resolve_relative("api_uploads/test/x.mp4")
        assert resolved == target.resolve()

    def test_resolve_relative_rejects_empty(self, monkeypatch, tmp_path: Path):
        from src.api import temp_storage

        monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
        with pytest.raises(ValueError):
            temp_storage.resolve_relative("")
