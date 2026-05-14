"""Schemas del estado de la cola de jobs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatusValue = Literal["pending", "running", "completed", "failed", "cancelled"]
JobModeValue = Literal[
    "presidents", "pronosticos", "subs_auto", "copyright", "tiktok_shop",
    "editor_auto",
]


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


class QueueStateResponse(BaseModel):
    active_jobs: list[ActiveJobResponse]  # pending + running, en orden de cola
    pending_count: int
    running_count: int
    recent_completed: list[ActiveJobResponse]  # últimos 5 (incluye failed/cancelled)
