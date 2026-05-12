"""Tests del WebSocket /ws/queue.

Usa `TestClient.websocket_connect()` de starlette/FastAPI — síncrono.
El polling del manager se acelera a 50ms vía override en `conftest.py`.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


def _enqueue(fake_job_queue, mode_value: str = "tiktok_shop", title: str = "test"):
    from src.queue.models import JobMode
    return fake_job_queue.enqueue(JobMode(mode_value), title, {"x": 1})


def _wait_for_event(
    ws,
    expected_types: set[str],
    *,
    settle_ms: int = 150,
    max_attempts: int = 8,
) -> list[dict]:
    """Recibe mensajes hasta encontrar uno cuyo `type` esté en
    `expected_types`. Devuelve TODOS los mensajes recibidos hasta ese
    punto inclusive (puede haber otros tipos antes).

    `settle_ms` es la pausa inicial que da el polling al manager para
    detectar el cambio. `max_attempts` limita reintentos por si el
    polling tarda más que el sleep.
    """
    time.sleep(settle_ms / 1000)
    out: list[dict] = []
    for _ in range(max_attempts):
        msg = ws.receive_json()
        out.append(msg)
        if msg["type"] in expected_types:
            return out
    return out


def _wait_for_pong(ws) -> list[dict]:
    return _wait_for_event(ws, {"pong"})


# ---------------------------------------------------------------------------
# Conexión + snapshot inicial
# ---------------------------------------------------------------------------
class TestWebSocketSnapshot:
    def test_connect_empty_queue(self, app_client: TestClient):
        with app_client.websocket_connect("/ws/queue") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "snapshot"
            assert msg["data"] == {"jobs": []}

    def test_snapshot_includes_existing_jobs(
        self, app_client: TestClient, fake_job_queue
    ):
        j1 = _enqueue(fake_job_queue, title="j1")
        j2 = _enqueue(fake_job_queue, "presidents", "j2")
        with app_client.websocket_connect("/ws/queue") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "snapshot"
            ids = {j["job_id"] for j in msg["data"]["jobs"]}
            assert ids == {j1.id, j2.id}
            modes = {j["mode"] for j in msg["data"]["jobs"]}
            assert modes == {"tiktok_shop", "presidents"}


# ---------------------------------------------------------------------------
# Updates en vivo
# ---------------------------------------------------------------------------
class TestWebSocketUpdates:
    def test_new_job_emits_update(
        self, app_client: TestClient, fake_job_queue
    ):
        with app_client.websocket_connect("/ws/queue") as ws:
            ws.receive_json()  # snapshot inicial vacío
            j = _enqueue(fake_job_queue, title="nuevo")
            msgs = _wait_for_event(ws, {"update"})
            update_msgs = [m for m in msgs if m["type"] == "update"]
            assert update_msgs, f"No update msg recibido: {msgs}"
            jobs = update_msgs[0]["data"]["jobs"]
            assert any(jj["job_id"] == j.id for jj in jobs)

    def test_status_change_emits_update(
        self, app_client: TestClient, fake_job_queue
    ):
        j = _enqueue(fake_job_queue, title="x")
        with app_client.websocket_connect("/ws/queue") as ws:
            ws.receive_json()  # snapshot
            fake_job_queue.set_status(j.id, "running")
            msgs = _wait_for_event(ws, {"update"})
            update_msgs = [m for m in msgs if m["type"] == "update"]
            assert update_msgs
            updated = update_msgs[0]["data"]["jobs"][0]
            assert updated["job_id"] == j.id
            assert updated["status"] == "running"

    def test_progress_change_emits_progress_event(
        self, app_client: TestClient, fake_job_queue
    ):
        j = _enqueue(fake_job_queue, title="x")
        fake_job_queue.set_status(j.id, "running")
        # Encontrar el job en la lista interna y actualizar progreso
        for jj in fake_job_queue.get_all():
            if jj.id == j.id:
                jj.progress = 0.10
                jj.progress_label = "Empezando"
                break

        with app_client.websocket_connect("/ws/queue") as ws:
            ws.receive_json()  # snapshot
            # Cambiar SOLO progreso (status sigue running)
            for jj in fake_job_queue.get_all():
                if jj.id == j.id:
                    jj.progress = 0.55
                    jj.progress_label = "Mitad"
                    break

            msgs = _wait_for_event(ws, {"progress"})
            progress_msgs = [m for m in msgs if m["type"] == "progress"]
            assert progress_msgs, f"esperaba progress, recibido: {msgs}"
            j_payload = progress_msgs[0]["data"]["jobs"][0]
            assert j_payload["progress_percent"] == 55.0
            assert j_payload["current_step"] == "Mitad"

    def test_remove_emits_removed_event(
        self, app_client: TestClient, fake_job_queue
    ):
        j = _enqueue(fake_job_queue, title="x")
        fake_job_queue.set_status(j.id, "completed")
        with app_client.websocket_connect("/ws/queue") as ws:
            ws.receive_json()  # snapshot
            # Quitar el job (simula `clear_finished`)
            fake_job_queue.remove(j.id)
            msgs = _wait_for_event(ws, {"removed"})
            removed_msgs = [m for m in msgs if m["type"] == "removed"]
            assert removed_msgs
            assert j.id in removed_msgs[0]["data"]["job_ids"]


# ---------------------------------------------------------------------------
# Ping / Pong
# ---------------------------------------------------------------------------
class TestWebSocketPingPong:
    def test_ping_responds_with_pong(self, app_client: TestClient):
        with app_client.websocket_connect("/ws/queue") as ws:
            ws.receive_json()  # snapshot
            ws.send_json({"type": "ping"})
            msgs = _wait_for_pong(ws)
            assert any(m["type"] == "pong" for m in msgs)


# ---------------------------------------------------------------------------
# Multi-cliente
# ---------------------------------------------------------------------------
class TestWebSocketMultipleClients:
    def test_multiple_clients_receive_same_event(
        self, app_client: TestClient, fake_job_queue
    ):
        with app_client.websocket_connect("/ws/queue") as ws_a:
            with app_client.websocket_connect("/ws/queue") as ws_b:
                ws_a.receive_json()  # snapshot
                ws_b.receive_json()
                _enqueue(fake_job_queue, title="multi")
                a_msgs = _wait_for_event(ws_a, {"update"})
                b_msgs = _wait_for_event(ws_b, {"update"})
                assert any(m["type"] == "update" for m in a_msgs)
                assert any(m["type"] == "update" for m in b_msgs)


# ---------------------------------------------------------------------------
# Auth (cuando API_KEY está configurada)
# ---------------------------------------------------------------------------
class TestWebSocketAuth:
    def test_no_api_key_required_by_default(self, app_client: TestClient):
        with app_client.websocket_connect("/ws/queue") as ws:
            assert ws.receive_json()["type"] == "snapshot"

    def test_invalid_api_key_rejected(
        self, monkeypatch: pytest.MonkeyPatch, fake_shop_redis, fake_job_queue, shop_root
    ):
        from fastapi.testclient import TestClient
        from src.api.config import get_settings as _get_settings

        del shop_root  # fixture side-effect-only

        monkeypatch.setenv("API_KEY", "secret-token")
        _get_settings.cache_clear()

        import src.tiktok_shop.repos.redis_base as redis_base
        monkeypatch.setattr(redis_base, "_INSTANCE", fake_shop_redis)
        monkeypatch.setattr(redis_base, "get_shop_redis", lambda: fake_shop_redis)

        from src.api.dependencies import get_queue, get_redis
        from src.api.main import create_app
        from src.api.websockets.queue_ws import (
            ConnectionManager,
            get_connection_manager,
        )

        app = create_app()
        app.dependency_overrides[get_redis] = lambda: fake_shop_redis
        app.dependency_overrides[get_queue] = lambda: fake_job_queue
        fast = ConnectionManager(poll_interval_s=0.05)
        app.dependency_overrides[get_connection_manager] = lambda: fast

        from starlette.websockets import WebSocketDisconnect

        with TestClient(app) as client:
            # Sin api_key → cierra con 1008
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect("/ws/queue") as ws:
                    ws.receive_json()
            assert exc.value.code == 1008

            # Con api_key correcto → snapshot OK
            with client.websocket_connect("/ws/queue?api_key=secret-token") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "snapshot"

        _get_settings.cache_clear()
