"""Schemas del estado de la cola de jobs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatusValue = Literal["pending", "running", "completed", "failed", "cancelled"]
# Cualquier `JobMode.value`. Era una lista escrita a mano con seis modos, y como
# esto valida la SALIDA, un job de un modo que no estuviera en la lista tumbaba
# la cola entera con un 500 — no solo ese job. Con veintitantos modos y uno
# nuevo por nicho, la lista siempre iba a quedarse corta.
JobModeValue = str


class ActiveJobResponse(BaseModel):
    job_id: str
    mode: JobModeValue
    title: str
    status: JobStatusValue
    progress_percent: float = Field(..., ge=0.0, le=100.0)
    current_step: str
    estimated_remaining_seconds: float | None = None
    elapsed_seconds: float
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    enqueued_by: str | None = None
    error: str | None = None
    result_path: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    # Unix timestamp a la que el job se ejecutará. Si está en el futuro
    # el worker no lo coge hasta esa hora. None = ejecutar inmediato.
    scheduled_for: float | None = None
    duration_seconds: float | None = None


class QueueStateResponse(BaseModel):
    # Multiusuario: de quién es la cola que se está viendo, si quien mira es
    # admin, y cuántos trabajos activos tiene cada uno de los demás (para el
    # aviso discreto del admin).
    viendo: str = ""
    es_admin: bool = False
    activos_de_otros: dict[str, int] = Field(default_factory=dict)
    active_jobs: list[ActiveJobResponse]  # pending + running, en orden de cola
    pending_count: int
    running_count: int
    recent_completed: list[ActiveJobResponse]  # últimos 5 (incluye failed/cancelled)
