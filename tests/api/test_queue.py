"""Tests del router de cola (lectura + cancelación)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _make_job(fake_job_queue, *, title: str = "test job", mode: str = "tiktok_shop"):
    """Helper: encola un job y devuelve su id."""
    from src.queue.models import JobMode
    job = fake_job_queue.enqueue(JobMode(mode), title, {"tier": "standard"})
    return job


# ---------------------------------------------------------------------------
# GET /queue
# ---------------------------------------------------------------------------
class TestGetQueueState:
    def test_state_empty(self, app_client: TestClient):
        r = app_client.get("/api/v1/queue")
        assert r.status_code == 200
        body = r.json()
        assert body == {
            "active_jobs": [],
            "pending_count": 0,
            "running_count": 0,
            "recent_completed": [],
        }

    def test_state_with_pending_and_running(
        self, app_client: TestClient, fake_job_queue
    ):
        a = _make_job(fake_job_queue, title="A")
        b = _make_job(fake_job_queue, title="B")
        fake_job_queue.set_status(a.id, "running")
        r = app_client.get("/api/v1/queue")
        body = r.json()
        assert body["pending_count"] == 1
        assert body["running_count"] == 1
        assert len(body["active_jobs"]) == 2
        # B sigue pending, A está running
        ids = {j["job_id"]: j["status"] for j in body["active_jobs"]}
        assert ids[a.id] == "running"
        assert ids[b.id] == "pending"

    def test_state_includes_recent_completed(
        self, app_client: TestClient, fake_job_queue
    ):
        for letra in "ABCDEFG":  # 7 finalizados
            j = _make_job(fake_job_queue, title=letra)
            fake_job_queue.set_status(j.id, "completed")
        r = app_client.get("/api/v1/queue")
        body = r.json()
        assert body["pending_count"] == 0
        assert body["running_count"] == 0
        # Solo los 5 más recientes
        assert len(body["recent_completed"]) == 5


# ---------------------------------------------------------------------------
# GET /queue/{job_id}
# ---------------------------------------------------------------------------
class TestGetJob:
    def test_get_existing(self, app_client: TestClient, fake_job_queue):
        j = _make_job(fake_job_queue, title="Mi job")
        r = app_client.get(f"/api/v1/queue/{j.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["job_id"] == j.id
        assert body["title"] == "Mi job"
        assert body["status"] == "pending"
        assert body["progress_percent"] == 0.0

    def test_get_missing_returns_404(self, app_client: TestClient):
        r = app_client.get("/api/v1/queue/missing")
        assert r.status_code == 404
        assert r.json()["code"] == "job_not_found"


# ---------------------------------------------------------------------------
# DELETE /queue/{job_id}  (cancel)
# ---------------------------------------------------------------------------
class TestCancelJob:
    def test_cancel_pending(
        self, app_client: TestClient, fake_job_queue
    ):
        j = _make_job(fake_job_queue, title="A")
        r = app_client.delete(f"/api/v1/queue/{j.id}")
        assert r.status_code == 204
        # Job pasó a CANCELLED
        from src.queue.models import JobStatus
        cancelled = next(jj for jj in fake_job_queue.get_all() if jj.id == j.id)
        assert cancelled.status == JobStatus.CANCELLED

    def test_cancel_running_marks_intent(
        self, app_client: TestClient, fake_job_queue
    ):
        j = _make_job(fake_job_queue, title="A")
        fake_job_queue.set_status(j.id, "running")
        r = app_client.delete(f"/api/v1/queue/{j.id}")
        assert r.status_code == 204
        running = next(jj for jj in fake_job_queue.get_all() if jj.id == j.id)
        assert running.params.get("_cancel_requested") is True

    def test_cancel_completed_returns_409(
        self, app_client: TestClient, fake_job_queue
    ):
        j = _make_job(fake_job_queue, title="A")
        fake_job_queue.set_status(j.id, "completed")
        r = app_client.delete(f"/api/v1/queue/{j.id}")
        assert r.status_code == 409
        assert r.json()["code"] == "job_not_cancellable"

    def test_cancel_failed_returns_409(
        self, app_client: TestClient, fake_job_queue
    ):
        j = _make_job(fake_job_queue, title="A")
        fake_job_queue.set_status(j.id, "failed")
        r = app_client.delete(f"/api/v1/queue/{j.id}")
        assert r.status_code == 409

    def test_cancel_already_cancelled_returns_409(
        self, app_client: TestClient, fake_job_queue
    ):
        j = _make_job(fake_job_queue, title="A")
        fake_job_queue.set_status(j.id, "cancelled")
        r = app_client.delete(f"/api/v1/queue/{j.id}")
        assert r.status_code == 409

    def test_cancel_missing_returns_404(self, app_client: TestClient):
        r = app_client.delete("/api/v1/queue/missing")
        assert r.status_code == 404
