"""Modelos del sistema de cola: Job dataclass + enums.

`Job` se serializa/deserializa a JSON para persistencia (estado de cola
sobrevive reinicios de la app local). Los `params` son libres por modo
— cada runner sabe interpretar los suyos.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class JobMode(str, Enum):
    PRESIDENTS = "presidents"
    PRONOSTICOS = "pronosticos"
    SUBS_AUTO = "subs_auto"
    COPYRIGHT = "copyright"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Etiqueta legible por modo (para mostrar en UI)
MODE_LABELS = {
    JobMode.PRESIDENTS: "🏛️ Presidentes",
    JobMode.PRONOSTICOS: "📊 Pronósticos",
    JobMode.SUBS_AUTO: "🎬 Subs sobre Vídeo",
    JobMode.COPYRIGHT: "🛡️ Quitar Copy",
}


@dataclass
class Job:
    """Trabajo de generación de vídeo. Vive en la cola hasta que termine."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    mode: JobMode = JobMode.PRESIDENTS
    title: str = ""                      # Texto corto que el usuario verá ("Top 5 worst…")
    params: dict[str, Any] = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0                # 0.0 → 1.0
    progress_label: str = "En espera"
    logs: list[str] = field(default_factory=list)
    result_path: str | None = None       # MP4 final si completó
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    # ---- helpers ----
    @property
    def elapsed_s(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return max(0.0, end - self.started_at)

    @property
    def eta_s(self) -> float | None:
        """ETA estimada en segundos (None si aún no se puede calcular)."""
        if self.status != JobStatus.RUNNING or self.progress < 0.05:
            return None
        elapsed = self.elapsed_s
        if elapsed <= 0:
            return None
        total_est = elapsed / self.progress
        return max(0.0, total_est - elapsed)

    def append_log(self, msg: str, max_lines: int = 200) -> None:
        self.logs.append(msg)
        if len(self.logs) > max_lines:
            del self.logs[: len(self.logs) - max_lines]

    # ---- serialización (JSON-safe) ----
    def to_dict(self) -> dict:
        d = asdict(self)
        d["mode"] = self.mode.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        d = dict(d)
        d["mode"] = JobMode(d["mode"])
        d["status"] = JobStatus(d["status"])
        return cls(**d)
