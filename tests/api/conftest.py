"""Fixtures compartidas para tests de la API FastAPI.

- Inyecta `FakeRedis` (definido en `tests/tiktok_shop/conftest.py`) en
  todas las dependencias de la app a través de `dependency_overrides`.
- Inyecta `FakeJobQueue` para evitar arrancar el worker thread real con
  el dispatcher de Streamlit en cada test.
- Mockea las funciones que tocan filesystem real para los tests de
  productos (creación de carpetas, escritura de fotos).
- Mockea `analyze_product` y `generate_nano_banana_prompt` para no llamar
  a Gemini.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.tiktok_shop.conftest import FakeRedis


class FakeJobQueue:
    """Sustituto sincrónico de `JobQueue` para tests. No tiene worker
    thread — los jobs se quedan en `PENDING` hasta que el test los mute
    explícitamente (ej. via `set_status`).

    Cubre el subset que usan los routers: `enqueue`, `cancel`, `get_all`,
    `remove`. Compatible con la lógica de `position_in_queue` del router.
    """

    def __init__(self) -> None:
        self._jobs: list = []

    def enqueue(self, mode, title, params, enqueued_by=None):
        from src.queue.models import Job
        job = Job(
            mode=mode,
            title=title,
            params=dict(params or {}),
            enqueued_by=enqueued_by,
        )
        self._jobs.append(job)
        return job

    def cancel(self, job_id):
        from src.queue.models import JobStatus
        for j in self._jobs:
            if j.id == job_id:
                if j.status == JobStatus.PENDING:
                    j.status = JobStatus.CANCELLED
                    j.finished_at = time.time()
                    j.progress_label = "Cancelado antes de empezar"
                    return True
                if j.status == JobStatus.RUNNING:
                    j.params["_cancel_requested"] = True
                    return True
                return False
        return False

    def get_all(self):
        return list(self._jobs)

    def posiciones_pendientes(self):
        """Mismo cálculo que la cola de verdad: `{job_id: puesto}` de los
        pendientes, con las ediciones de cliente al final."""
        from src.queue.manager import _is_client_edit_job
        from src.queue.models import JobStatus

        pendientes = [
            (i, j) for i, j in enumerate(self._jobs)
            if j.status == JobStatus.PENDING
        ]
        pendientes.sort(key=lambda par: (_is_client_edit_job(par[1]), par[0]))
        return {j.id: puesto for puesto, (_i, j) in enumerate(pendientes, start=1)}

    def remove(self, job_id):
        from src.queue.models import JobStatus
        finals = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
        for i, j in enumerate(self._jobs):
            if j.id == job_id and j.status in finals:
                del self._jobs[i]
                return True
        return False

    # Helpers para tests — no son parte del interfaz de JobQueue
    def set_status(self, job_id, status_name: str):
        from src.queue.models import JobStatus
        for j in self._jobs:
            if j.id == job_id:
                j.status = JobStatus(status_name)
                if status_name == "running":
                    j.started_at = time.time()
                if status_name in ("completed", "failed", "cancelled"):
                    j.finished_at = time.time()
                return
        raise KeyError(job_id)


@pytest.fixture
def fake_shop_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def shop_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Reemplaza `TIKTOK_SHOP_ROOT_PATH` por una carpeta temporal para que
    la creación de estructura Drive no toque el filesystem real.

    También resetea la caché de `get_settings`/Redis singleton para evitar
    contagio entre tests.
    """
    root = tmp_path / "TIKTOK_SHOP"
    root.mkdir()
    (root / "_users").mkdir()
    (root / "_products").mkdir()
    monkeypatch.setenv("TIKTOK_SHOP_ROOT_PATH", str(root))
    return root


@pytest.fixture
def fake_job_queue() -> FakeJobQueue:
    return FakeJobQueue()


@pytest.fixture
def app_client(
    fake_shop_redis: FakeRedis,
    fake_job_queue: FakeJobQueue,
    shop_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """TestClient con dependencias overrideadas para FakeRedis y stubs Gemini."""
    # Resetear caché de settings (la lifespan lee env vars una vez)
    from src.api.config import get_settings as _get_settings
    _get_settings.cache_clear()

    # Forzar singleton ShopRedis a FakeRedis ANTES de importar la app
    import src.tiktok_shop.repos.redis_base as redis_base

    monkeypatch.setattr(redis_base, "_INSTANCE", fake_shop_redis)
    monkeypatch.setattr(redis_base, "get_shop_redis", lambda: fake_shop_redis)

    from src.api.main import create_app
    from src.api.dependencies import get_queue, get_redis

    app = create_app()
    app.dependency_overrides[get_redis] = lambda: fake_shop_redis
    app.dependency_overrides[get_queue] = lambda: fake_job_queue

    # Manager WebSocket con polling rápido (50ms) — tests deterministas
    from src.api.websockets.queue_ws import (
        ConnectionManager,
        get_connection_manager,
    )
    fast_manager = ConnectionManager(poll_interval_s=0.05)
    app.dependency_overrides[get_connection_manager] = lambda: fast_manager

    # Stub Gemini para no salir a internet
    def _fake_analyze(photo_paths, *, extra_context: str = "", language: str = "es"):
        return {
            "product_type": "test",
            "category": "fitness",
            "subcategory": None,
            "key_features": ["liviano", "duradero"],
            "materials_visual": ["plástico"],
            "has_complex_packaging_text": False,
            "best_camera_angles": ["packshot"],
            "suggested_audiences": ["a", "b", "c", "d", "e"],
            "selling_points": ["punto 1", "punto 2"],
            "needs_nano_banana_regeneration": True,
            "warnings": [],
        }

    def _fake_nano_banana(**kwargs):
        return "Generate professional product photography of test_product..."

    import src.tiktok_shop.pipeline.analyzer as analyzer_mod
    import src.tiktok_shop.pipeline.nano_banana_prompt_generator as nb_mod

    monkeypatch.setattr(analyzer_mod, "analyze_product", _fake_analyze)
    monkeypatch.setattr(nb_mod, "generate_nano_banana_prompt", _fake_nano_banana)

    # Stub `src.utils.load_config` — los routers de Creator Reward lo
    # llaman pero no tenemos `config/config.json` ni TIKTOK_ROOT_PATH en
    # tests. Devolvemos un dict con paths a tmp para que el runner real
    # tenga algo válido (si llega a ejecutarse, cosa que no pasa con
    # FakeJobQueue).
    cr_root = tmp_path_for_cr(shop_root.parent)

    def _fake_load_config(path: str = "config/config.json") -> dict:
        return {
            "paths": {
                "library_base": str(cr_root / "presidents"),
                "intro_library": str(cr_root / "intro"),
                "output_folder": str(cr_root / "output"),
                "resources_library": str(cr_root / "resources"),
                "pronosticos_clips": str(cr_root / "pronosticos_clips"),
                "temp_folder": str(cr_root / "temp_work"),
            },
            "video_settings": {"resolution": [1080, 1920]},
            "folder_structure": {},
        }

    import src.utils as utils_mod
    monkeypatch.setattr(utils_mod, "load_config", _fake_load_config)

    # Forzar API_TEMP_ROOT a un tmp aislado por test
    monkeypatch.setenv("API_TEMP_ROOT", str(cr_root / "temp_work"))

    with TestClient(app) as client:
        yield client


def tmp_path_for_cr(base: Path) -> Path:
    """Crea (idempotente) una raíz temporal para tests Creator Reward."""
    cr_root = base / "cr_test_root"
    for sub in (
        "presidents", "intro", "output", "resources",
        "pronosticos_clips", "temp_work",
    ):
        (cr_root / sub).mkdir(parents=True, exist_ok=True)
    return cr_root
