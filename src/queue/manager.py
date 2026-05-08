"""JobQueue singleton: gestiona la cola y un worker thread daemon.

El singleton vive entre reruns de Streamlit gracias a `@st.cache_resource`.
El worker procesa los jobs FIFO: toma el primero PENDING, lo pasa al
runner correspondiente con callbacks que actualizan progreso, y al
terminar guarda `result_path` o `error` en el Job.

Persistencia: el estado se escribe a `temp_work/queue_state.json` tras
cada cambio relevante. Al iniciar el singleton, intentamos recargar
trabajos pendientes (los `RUNNING` huérfanos por crash se marcan como
`FAILED` con motivo "Interrumpido por reinicio").

Migración a cloud: el `_dispatch` invoca runners locales, pero la
interfaz pública (`enqueue` / `cancel` / `get_*`) no asume nada del
backend. Para cloud bastará sustituir el thread por un consumidor
Redis/SQS que reciba JSON-jobs.
"""

from __future__ import annotations

import json
import os
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

from .models import Job, JobMode, JobStatus


_PERSIST_FILENAME = "queue_state.json"


class JobQueue:
    def __init__(self, persist_dir: str | Path):
        self._jobs: list[Job] = []
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._stop_event = threading.Event()
        self._persist_path = Path(persist_dir) / _PERSIST_FILENAME
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._dispatch: Callable[[Job], None] | None = None

        self._load_state()
        self._reset_orphans()

        self._worker = threading.Thread(
            target=self._worker_loop,
            name="JobQueueWorker",
            daemon=True,
        )
        self._worker.start()

    # ----------------------------------------------------------
    # API pública
    # ----------------------------------------------------------
    def set_dispatcher(self, dispatch: Callable[[Job], None]) -> None:
        """Registra la función que ejecuta el job. La inyectamos desde
        fuera para evitar imports circulares con runners.py."""
        with self._lock:
            self._dispatch = dispatch

    def enqueue(
        self, mode: JobMode, title: str, params: dict,
        enqueued_by: str | None = None,
    ) -> Job:
        job = Job(mode=mode, title=title, params=params, enqueued_by=enqueued_by)
        with self._cond:
            self._jobs.append(job)
            self._save_state_locked()
            self._cond.notify_all()
        return job

    def cancel(self, job_id: str) -> bool:
        """Cancela un job. Si está en cola → CANCELLED inmediato. Si está
        en ejecución solo se marca (el runner puede no atender la señal)."""
        with self._cond:
            for j in self._jobs:
                if j.id == job_id:
                    if j.status == JobStatus.PENDING:
                        j.status = JobStatus.CANCELLED
                        j.finished_at = time.time()
                        j.progress_label = "Cancelado antes de empezar"
                        self._save_state_locked()
                        return True
                    if j.status == JobStatus.RUNNING:
                        # Marcamos cancel intent — el runner debería revisar
                        # job.status, pero las pipelines existentes no lo
                        # hacen. Es best-effort: aún terminará.
                        j.params["_cancel_requested"] = True
                        return True
            return False

    def move_up(self, job_id: str) -> bool:
        """Sube una posición un job PENDING (intercambia con el anterior
        que también esté pendiente)."""
        with self._cond:
            pending_indices = [
                i for i, j in enumerate(self._jobs)
                if j.status == JobStatus.PENDING
            ]
            try:
                idx = next(i for i in pending_indices if self._jobs[i].id == job_id)
            except StopIteration:
                return False
            pos = pending_indices.index(idx)
            if pos == 0:
                return False
            prev_idx = pending_indices[pos - 1]
            self._jobs[idx], self._jobs[prev_idx] = self._jobs[prev_idx], self._jobs[idx]
            self._save_state_locked()
            self._cond.notify_all()
            return True

    def move_down(self, job_id: str) -> bool:
        """Baja una posición un job PENDING."""
        with self._cond:
            pending_indices = [
                i for i, j in enumerate(self._jobs)
                if j.status == JobStatus.PENDING
            ]
            try:
                idx = next(i for i in pending_indices if self._jobs[i].id == job_id)
            except StopIteration:
                return False
            pos = pending_indices.index(idx)
            if pos == len(pending_indices) - 1:
                return False
            next_idx = pending_indices[pos + 1]
            self._jobs[idx], self._jobs[next_idx] = self._jobs[next_idx], self._jobs[idx]
            self._save_state_locked()
            self._cond.notify_all()
            return True

    def move_to_top(self, job_id: str) -> bool:
        """Mueve un job PENDING al principio de la cola pendiente (siguiente
        en ejecutarse cuando termine el actual)."""
        with self._cond:
            pending_indices = [
                i for i, j in enumerate(self._jobs)
                if j.status == JobStatus.PENDING
            ]
            if not pending_indices:
                return False
            try:
                idx = next(i for i in pending_indices if self._jobs[i].id == job_id)
            except StopIteration:
                return False
            first_pending = pending_indices[0]
            if idx == first_pending:
                return False
            job = self._jobs.pop(idx)
            self._jobs.insert(first_pending, job)
            self._save_state_locked()
            self._cond.notify_all()
            return True

    def remove(self, job_id: str) -> bool:
        """Elimina un job de la lista (solo si está finalizado)."""
        with self._cond:
            for i, j in enumerate(self._jobs):
                if j.id == job_id and j.status in (
                    JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED
                ):
                    del self._jobs[i]
                    self._save_state_locked()
                    return True
            return False

    def clear_finished(self) -> int:
        """Limpia todos los completados/fallidos/cancelados. Devuelve cuántos."""
        with self._cond:
            before = len(self._jobs)
            self._jobs = [
                j for j in self._jobs
                if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
            ]
            removed = before - len(self._jobs)
            if removed:
                self._save_state_locked()
            return removed

    def get_all(self) -> list[Job]:
        with self._lock:
            return list(self._jobs)

    def get_running(self) -> Job | None:
        with self._lock:
            for j in self._jobs:
                if j.status == JobStatus.RUNNING:
                    return j
            return None

    def get_pending(self) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs if j.status == JobStatus.PENDING]

    def get_finished(self, limit: int = 10) -> list[Job]:
        """Más recientes primero (por finished_at)."""
        with self._lock:
            done = [
                j for j in self._jobs
                if j.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
            ]
            done.sort(key=lambda x: x.finished_at or 0, reverse=True)
            return done[:limit]

    # ----------------------------------------------------------
    # Worker loop
    # ----------------------------------------------------------
    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._cond:
                # Esperar a que haya algo pendiente
                while not self._stop_event.is_set():
                    pending = next(
                        (j for j in self._jobs if j.status == JobStatus.PENDING),
                        None,
                    )
                    if pending is not None:
                        break
                    self._cond.wait(timeout=2.0)
                if self._stop_event.is_set():
                    return
                job = pending
                job.status = JobStatus.RUNNING
                job.started_at = time.time()
                job.progress_label = "Iniciando…"
                self._save_state_locked()
                dispatch = self._dispatch

            # Ejecutar fuera del lock
            if dispatch is None:
                with self._cond:
                    job.status = JobStatus.FAILED
                    job.error = "No hay dispatcher registrado en JobQueue"
                    job.finished_at = time.time()
                    self._save_state_locked()
                continue

            try:
                dispatch(job)  # esto debe rellenar job.result_path
                with self._cond:
                    if job.status == JobStatus.RUNNING:
                        job.status = JobStatus.COMPLETED
                        job.progress = 1.0
                        job.progress_label = "✅ Completado"
                    job.finished_at = time.time()
                    self._save_state_locked()
            except Exception as e:
                with self._cond:
                    job.status = JobStatus.FAILED
                    job.error = f"{e}\n\n{traceback.format_exc()}"
                    job.progress_label = f"❌ {e}"
                    job.finished_at = time.time()
                    self._save_state_locked()

    # ----------------------------------------------------------
    # Persistencia
    # ----------------------------------------------------------
    def _save_state_locked(self) -> None:
        """Escribe el estado actual. ASUME que el lock ya está adquirido."""
        try:
            data = {"jobs": [j.to_dict() for j in self._jobs]}
            tmp = self._persist_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._persist_path)
        except Exception as e:
            print(f"[JobQueue] Error guardando estado: {e}")

    def _load_state(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            self._jobs = [Job.from_dict(d) for d in data.get("jobs", [])]
        except Exception as e:
            print(f"[JobQueue] Estado corrupto, se ignora: {e}")
            self._jobs = []

    def _reset_orphans(self) -> None:
        """Trabajos que estaban RUNNING al reiniciar la app no pueden
        retomarse — los marcamos como FAILED."""
        changed = False
        with self._lock:
            for j in self._jobs:
                if j.status == JobStatus.RUNNING:
                    j.status = JobStatus.FAILED
                    j.error = "Interrumpido (la app se reinició mientras procesaba)"
                    j.progress_label = "❌ Interrumpido por reinicio"
                    j.finished_at = time.time()
                    changed = True
            if changed:
                self._save_state_locked()


# ----------------------------------------------------------
# Singleton helper para Streamlit
# ----------------------------------------------------------
def _make_queue(persist_dir: str) -> JobQueue:
    """Constructor que también registra el dispatcher (runners). Lo
    llamamos desde `get_queue()` con cache_resource."""
    queue = JobQueue(persist_dir)
    # Import diferido para evitar ciclos
    from .runners import dispatch_job
    queue.set_dispatcher(dispatch_job)
    return queue


def get_queue(persist_dir: str | None = None) -> JobQueue:
    """Devuelve el singleton (cacheado en Streamlit). En la primera
    llamada hay que pasar `persist_dir`.

    Nota crítica: re-registramos el dispatcher en CADA llamada porque el
    `@st.cache_resource` mantiene viva la instancia entre reruns y reloads
    de código. Sin este re-registro, si añades un runner nuevo (p. ej.
    `JobMode.TIKTOK_SHOP`) al `_RUNNERS` dict de `runners.py`, el
    dispatcher cacheado seguirá apuntando a la versión vieja de
    `dispatch_job` y los jobs nuevos fallarán con "Modo desconocido".
    """
    import streamlit as st

    if persist_dir is None:
        persist_dir = os.path.join(os.getcwd(), "temp_work")
    # Normalizar para evitar split de singleton si se pasan paths
    # equivalentes pero con representación distinta (rel vs abs).
    persist_dir = os.path.abspath(persist_dir)

    @st.cache_resource(show_spinner=False)
    def _cached(_persist_dir: str) -> JobQueue:
        return _make_queue(_persist_dir)

    queue = _cached(persist_dir)
    # Re-registra el dispatcher con la versión ACTUAL del código.
    from .runners import dispatch_job
    queue.set_dispatcher(dispatch_job)
    return queue
