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


# Modos que NO pueden correr en paralelo entre sí (máx 1 RUNNING a la vez),
# aunque haya varios workers. Quitar-marca usa Replicate ProPainter, que con
# <$5 de crédito limita a ráfaga de 1 req → 2 jobs simultáneos dan 429.
_EXCLUSIVE_MODES: set[JobMode] = {JobMode.TIKTOK_SHOP_WATERMARK}


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

        # Multi-worker: cada thread procesa un job a la vez. Permite que
        # mientras un worker está bloqueado esperando Atlas (que puede
        # tardar 20-30+ min en horas pico Standard), otros workers sigan
        # procesando jobs distintos. La selección del próximo PENDING es
        # atómica bajo el lock — dos workers no pueden tomar el mismo job.
        #
        # Sizing: cada worker usa pico ~500MB RAM (Whisper small + ffmpeg).
        # En Hetzner CX21 (4GB) → max 3 workers. CX31 (8GB) → 4-5. Por
        # defecto 2, configurable con QUEUE_WORKERS env var.
        try:
            n_workers = int(os.environ.get("QUEUE_WORKERS", "2"))
        except ValueError:
            n_workers = 2
        n_workers = max(1, min(4, n_workers))

        self._workers: list[threading.Thread] = []
        for i in range(n_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"JobQueueWorker-{i + 1}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)

    # ----------------------------------------------------------
    # API pública
    # ----------------------------------------------------------
    def set_dispatcher(self, dispatch: Callable[[Job], None]) -> None:
        """Registra la función que ejecuta el job. La inyectamos desde
        fuera para evitar imports circulares con runners.py."""
        with self._lock:
            self._dispatch = dispatch

    # ----------------------------------------------------------
    # Graceful shutdown (deploy seguro sin matar jobs)
    # ----------------------------------------------------------
    def start_draining(self) -> None:
        """Inicia drain: los workers dejan de aceptar nuevos jobs
        PENDING pero TERMINAN el que estén ejecutando ahora. El
        proceso debe llamar `wait_for_drain()` después y luego salir.

        Llamado típicamente desde el SIGTERM handler de api/main.py
        cuando docker-compose hace recreate. Combinado con
        `stop_grace_period: 1800s` en docker-compose, garantiza que
        ningún job se mate a media generación.
        """
        with self._cond:
            if self._stop_event.is_set():
                return
            self._stop_event.set()
            self._cond.notify_all()

    def is_draining(self) -> bool:
        return self._stop_event.is_set()

    def wait_for_drain(self, timeout: float | None = None) -> bool:
        """Bloquea hasta que TODOS los workers terminen su job actual
        y salgan limpiamente. Devuelve True si todos salieron antes
        del timeout, False si algún worker sigue ocupado. Si `timeout`
        es None, espera para siempre (sirve para deploys: docker-compose
        ya tiene su propio stop_grace_period que actúa como hard limit).
        """
        deadline = (time.time() + timeout) if timeout is not None else None
        for t in self._workers:
            remaining = None
            if deadline is not None:
                remaining = max(0.0, deadline - time.time())
                if remaining == 0:
                    return False
            t.join(timeout=remaining)
            if t.is_alive():
                return False
        return True

    def n_running_jobs(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs if j.status == JobStatus.RUNNING)

    def enqueue(
        self, mode: JobMode, title: str, params: dict,
        enqueued_by: str | None = None,
        scheduled_for: float | None = None,
    ) -> Job:
        """Encola un job. Si `scheduled_for` está poblado y es > now,
        el worker NO lo cogerá hasta esa hora — útil para programar a
        madrugada cuando los providers AI tienen cola despejada."""
        job = Job(
            mode=mode, title=title, params=params,
            enqueued_by=enqueued_by, scheduled_for=scheduled_for,
        )
        with self._cond:
            self._jobs.append(job)
            self._save_state_locked()
            self._cond.notify_all()
        return job

    def reschedule(self, job_id: str, scheduled_for: float | None) -> bool:
        """Cambia la hora programada de un job PENDING. Pasa `None` para
        desprogramar (ejecutar inmediatamente). Devuelve True si lo cambió."""
        with self._cond:
            for j in self._jobs:
                if j.id == job_id:
                    if j.status != JobStatus.PENDING:
                        return False
                    j.scheduled_for = scheduled_for
                    self._save_state_locked()
                    # Notificar workers — si el job pasa a estar disponible
                    # ahora (scheduled_for=None o <now), uno lo cogerá.
                    self._cond.notify_all()
                    return True
            return False

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
                # Esperar a que haya algo pendiente.
                # El orden de selección es el de la lista `_jobs`. Los
                # métodos move_up/move_down/move_to_top reordenan la lista
                # directamente — así el orden visible en la UI == orden
                # real de ejecución, sin truco de priority field.
                # Para jobs con `scheduled_for` futuro: los IGNORAMOS hasta
                # esa hora. El timeout 2s del wait nos hace re-evaluar
                # frecuentemente sin necesitar timers separados.
                while not self._stop_event.is_set():
                    now = time.time()
                    # Modos EXCLUSIVOS: máx 1 corriendo a la vez (aunque haya
                    # varios workers). Ej. quitar-marca usa Replicate, que con
                    # poco crédito limita a ráfaga de 1 → 2 en paralelo = 429.
                    running_exclusive = {
                        j.mode for j in self._jobs
                        if j.status == JobStatus.RUNNING and j.mode in _EXCLUSIVE_MODES
                    }
                    pending = next(
                        (
                            j for j in self._jobs
                            if j.status == JobStatus.PENDING
                            and (j.scheduled_for is None or j.scheduled_for <= now)
                            and not (
                                j.mode in _EXCLUSIVE_MODES
                                and j.mode in running_exclusive
                            )
                        ),
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

            # Medir duración del MP4 final con ffprobe (cacheado). Se guarda
            # en el job para que la UI lo muestre y se persiste en disk.
            try:
                if job.status == JobStatus.COMPLETED and job.result_path:
                    from src.queue.metrics import _video_duration
                    dur = _video_duration(job.result_path)
                    if dur is not None:
                        with self._cond:
                            job.duration_seconds = dur
                            self._save_state_locked()
                            # CRÍTICO: notificar al WS para que el frontend
                            # reciba el update con `duration_seconds`. Sin
                            # esto, la card de Recientes nunca muestra la
                            # duración del MP4 (solo se ve tras refresco).
                            self._cond.notify_all()
            except Exception as e:
                print(f"[JobQueue] ffprobe duration error: {e}")

            # Persistir métrica de duración para ETA inteligente (fuera del
            # lock — fallos aquí NO deben afectar al worker loop).
            try:
                from src.queue.metrics import record_job_metric
                record_job_metric(job)
            except Exception as e:
                print(f"[JobQueue] record_job_metric error: {e}")

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
        retomarse — los marcamos como FAILED.

        Para jobs `editor_auto` con `source=entrada`, además devolvemos
        el input desde `cola/` a `entrada/` para que el admin pueda
        re-encolarlo. Sin esto, el archivo queda atrapado en cola/ tras
        cada deploy/restart con un job a medio procesar.
        """
        changed = False
        orphan_jobs: list = []
        with self._lock:
            for j in self._jobs:
                if j.status != JobStatus.RUNNING:
                    continue
                p = j.params or {}
                is_editor = (
                    str(j.mode) == "JobMode.EDITOR_AUTO"
                    or getattr(j.mode, "value", None) == "editor_auto"
                )
                # Subida WEB (tiene output_subdir, sin guion): el input sigue en
                # Drive → lo RE-ENCOLAMOS para que se reanude solo tras el
                # reinicio (máx 2 reanudaciones, anti-bucle). Así un reinicio
                # NO rompe los vídeos de los clientes.
                is_web = is_editor and bool(p.get("output_subdir")) and not (p.get("script") or "").strip()
                resumes = int(p.get("_resume_count", 0) or 0)
                if is_web and resumes < 2:
                    p["_resume_count"] = resumes + 1
                    j.params = p
                    j.status = JobStatus.PENDING
                    j.progress = 0.0
                    j.progress_label = "🔁 Reanudado tras reinicio"
                    j.error = None
                    j.started_at = None
                    j.finished_at = None
                    changed = True
                else:
                    j.status = JobStatus.FAILED
                    j.error = "Interrumpido (la app se reinició mientras procesaba)"
                    j.progress_label = "❌ Interrumpido por reinicio"
                    j.finished_at = time.time()
                    changed = True
                    orphan_jobs.append(j)
            if changed:
                self._save_state_locked()

        # Cleanup filesystem fuera del lock (puede ser lento en Drive
        # FUSE). Best-effort: errores se loguean pero no abortan.
        for j in orphan_jobs:
            try:
                self._cleanup_orphan_editor_auto(j)
            except Exception as e:
                print(f"[JobQueue] cleanup orphan {j.id} falló: {e}")

    @staticmethod
    def _cleanup_orphan_editor_auto(job) -> None:
        """Si el job era editor_auto con `source=entrada`, mueve el input
        de cola → entrada. Para otros modos / sources, no-op."""
        if str(job.mode) != "JobMode.EDITOR_AUTO" and getattr(job.mode, "value", None) != "editor_auto":
            return
        p = job.params or {}
        if p.get("source") != "entrada":
            return
        filename = p.get("source_filename")
        user_name = p.get("user_name")
        if not filename or not user_name:
            return
        # Import diferido para no acoplar el módulo `queue` con `editor_auto`.
        from src.editor_auto.services import folder_manager
        try:
            folder_manager.move_file(user_name, "cola", "entrada", filename)
            print(
                f"[JobQueue] orphan {job.id}: input {filename!r} devuelto "
                f"de cola/ a entrada/ para reencolar"
            )
        except folder_manager.FolderError as e:
            # Puede que ya esté en entrada (mismo run del cleanup, etc).
            # No es un error real.
            print(
                f"[JobQueue] orphan {job.id}: no se pudo mover "
                f"{filename!r} ({e}) — quizá ya está en entrada/"
            )


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
