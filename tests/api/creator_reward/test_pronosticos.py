"""Tests del router 📊 Pronósticos Diarios."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fake_pronosticos_data(monkeypatch: pytest.MonkeyPatch):
    """Reemplaza `data_loader` para servir payloads in-memory."""
    import src.pronosticos.data_loader as dl

    storage: dict[str, dict | None] = {}

    def _load_raw(date: str):
        return storage.get(date)

    def _list_versions(payload: dict | None):
        if not payload:
            return []
        versions = payload.get("versions") or []
        sel = payload.get("selected_version_id")
        out = []
        for v in versions:
            d = dict(v)
            d["is_selected"] = (str(d.get("id")) == str(sel))
            out.append(d)
        return out

    def _get_picks(payload: dict):
        return payload.get("picks", [])

    def _find_latest(max_lookback_days: int = 14, redis=None):
        return next(iter(storage.keys()), None) if storage else None

    monkeypatch.setattr(dl, "load_raw_payload", _load_raw)
    monkeypatch.setattr(dl, "list_versions", _list_versions)
    monkeypatch.setattr(dl, "get_picks", _get_picks)
    monkeypatch.setattr(dl, "find_latest_available_date", _find_latest)

    return storage


def _make_payload(versions: list[dict], selected: str | None = None) -> dict:
    return {
        "versions": versions,
        "selected_version_id": selected,
    }


# ---------------------------------------------------------------------------
# GET /versions
# ---------------------------------------------------------------------------
class TestPronosticosVersions:
    def test_versions_no_payload(self, app_client: TestClient, fake_pronosticos_data):
        r = app_client.get("/api/v1/creator-reward/pronosticos/versions?date=2026-12-31")
        assert r.status_code == 200
        body = r.json()
        assert body["payload_exists"] is False
        assert body["versions"] == []

    def test_versions_with_payload(
        self, app_client: TestClient, fake_pronosticos_data
    ):
        fake_pronosticos_data["2026-05-10"] = _make_payload(
            versions=[
                {
                    "id": "v1", "trigger": "cron", "mode": "multi_match",
                    "word_count": 220, "estimated_duration_s": 65,
                    "script": "Empezamos…", "title": "Hoy 5 picks",
                    "competition_focus": None,
                    "picks": [{"match": "x"}, {"match": "y"}],
                },
                {
                    "id": "v2", "trigger": "manual", "mode": "single_match",
                    "word_count": 180, "estimated_duration_s": 55,
                    "script": "Para el partido…", "title": "Single",
                    "competition_focus": "Champions",
                    "picks": [{"match": "z"}],
                },
            ],
            selected="v2",
        )
        r = app_client.get("/api/v1/creator-reward/pronosticos/versions?date=2026-05-10")
        assert r.status_code == 200
        body = r.json()
        assert body["payload_exists"] is True
        assert body["selected_version_id"] == "v2"
        assert len(body["versions"]) == 2
        v1 = body["versions"][0]
        assert v1["id"] == "v1"
        assert v1["picks_count"] == 2
        assert v1["is_selected"] is False
        v2 = body["versions"][1]
        assert v2["is_selected"] is True
        assert v2["competition_focus"] == "Champions"

    def test_versions_invalid_date_format(
        self, app_client: TestClient, fake_pronosticos_data
    ):
        r = app_client.get("/api/v1/creator-reward/pronosticos/versions?date=2026/05/10")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /latest-date
# ---------------------------------------------------------------------------
class TestLatestDate:
    def test_latest_when_empty(self, app_client: TestClient, fake_pronosticos_data):
        r = app_client.get("/api/v1/creator-reward/pronosticos/latest-date")
        assert r.status_code == 200
        assert r.json() == {"latest_date": None}

    def test_latest_with_data(
        self, app_client: TestClient, fake_pronosticos_data
    ):
        fake_pronosticos_data["2026-05-08"] = _make_payload(versions=[{"id": "v1"}])
        r = app_client.get("/api/v1/creator-reward/pronosticos/latest-date")
        assert r.status_code == 200
        assert r.json()["latest_date"] == "2026-05-08"


# ---------------------------------------------------------------------------
# POST /enqueue
# ---------------------------------------------------------------------------
class TestPronosticosEnqueue:
    def test_enqueue_single_version(
        self, app_client: TestClient, fake_pronosticos_data, fake_job_queue
    ):
        fake_pronosticos_data["2026-05-10"] = _make_payload(
            versions=[{"id": "v1", "mode": "multi_match", "script": "x"}],
            selected="v1",
        )
        r = app_client.post(
            "/api/v1/creator-reward/pronosticos/enqueue",
            json={
                "target_date": "2026-05-10",
                "version_ids": ["v1"],
                "voice_id_override": "Spanish_EnergeticBoy",
                "publish_to_redis": False,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["total_enqueued"] == 1
        assert body["jobs"][0]["version_id"] == "v1"

        from src.queue.models import JobMode
        all_jobs = fake_job_queue.get_all()
        assert len(all_jobs) == 1
        params = all_jobs[0].params
        assert all_jobs[0].mode == JobMode.PRONOSTICOS
        assert params["target_date"] == "2026-05-10"
        assert params["version_id"] == "v1"
        assert params["voice_id_override"] == "Spanish_EnergeticBoy"
        assert params["script_override"] is None

    def test_enqueue_multiple_versions(
        self, app_client: TestClient, fake_pronosticos_data, fake_job_queue
    ):
        fake_pronosticos_data["2026-05-10"] = _make_payload(
            versions=[
                {"id": "v1", "mode": "multi_match", "script": "a"},
                {"id": "v2", "mode": "single_match", "script": "b"},
            ],
            selected="v1",
        )
        r = app_client.post(
            "/api/v1/creator-reward/pronosticos/enqueue",
            json={
                "target_date": "2026-05-10",
                "version_ids": ["v1", "v2"],
                "script_overrides": {"v2": "guion editado"},
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["total_enqueued"] == 2
        # v2 lleva script_override
        all_jobs = fake_job_queue.get_all()
        v2_job = next(j for j in all_jobs if j.params["version_id"] == "v2")
        assert v2_job.params["script_override"] == "guion editado"
        v1_job = next(j for j in all_jobs if j.params["version_id"] == "v1")
        assert v1_job.params["script_override"] is None

    def test_enqueue_legacy_version_id_becomes_none(
        self, app_client: TestClient, fake_pronosticos_data, fake_job_queue
    ):
        fake_pronosticos_data["2026-05-10"] = _make_payload(
            versions=[{"id": "legacy", "mode": "multi_match", "script": "x"}],
        )
        r = app_client.post(
            "/api/v1/creator-reward/pronosticos/enqueue",
            json={"target_date": "2026-05-10", "version_ids": ["legacy"]},
        )
        assert r.status_code == 201
        # version_id=None significa "usar selected_version_id del payload"
        params = fake_job_queue.get_all()[0].params
        assert params["version_id"] is None

    def test_enqueue_no_payload_returns_404(
        self, app_client: TestClient, fake_pronosticos_data
    ):
        r = app_client.post(
            "/api/v1/creator-reward/pronosticos/enqueue",
            json={"target_date": "2026-12-31", "version_ids": ["v1"]},
        )
        assert r.status_code == 404
        assert r.json()["code"] == "pronosticos_version_not_found"

    def test_enqueue_missing_version_id(
        self, app_client: TestClient, fake_pronosticos_data
    ):
        fake_pronosticos_data["2026-05-10"] = _make_payload(
            versions=[{"id": "v1", "mode": "multi_match", "script": "x"}],
        )
        r = app_client.post(
            "/api/v1/creator-reward/pronosticos/enqueue",
            json={"target_date": "2026-05-10", "version_ids": ["v_not_exists"]},
        )
        assert r.status_code == 404
        assert r.json()["code"] == "pronosticos_version_not_found"
        assert "missing" in r.json()["details"]

    def test_enqueue_invalid_date(self, app_client: TestClient, fake_pronosticos_data):
        r = app_client.post(
            "/api/v1/creator-reward/pronosticos/enqueue",
            json={"target_date": "no-date", "version_ids": ["v1"]},
        )
        assert r.status_code == 422

    def test_enqueue_empty_version_ids(
        self, app_client: TestClient, fake_pronosticos_data
    ):
        r = app_client.post(
            "/api/v1/creator-reward/pronosticos/enqueue",
            json={"target_date": "2026-05-10", "version_ids": []},
        )
        assert r.status_code == 422
