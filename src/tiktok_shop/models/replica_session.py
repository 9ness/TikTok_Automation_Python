"""Sesión de Réplica Viral — persiste cada réplica generada (standalone).

El operador sube un vídeo viral + foto del producto en la página "Replicar
viral"; el análisis produce N versiones (o una réplica troceada). Cada
generación se guarda como una `ReplicaSession` en Redis (`replica:<id>`,
índice `replica:index`) para que NO se pierdan las ideas al recargar y se
puedan revisar/descargar más tarde, tipo historial/calendario.

Cada item de `videos` sigue el schema 2-step de problem_videos (concept,
image_prompt, animate_prompt, segments, hook_text, cta_text, caption…). Al
subir y quemar el vídeo final (editor genérico), se guarda su `ready_token`
en el item correspondiente → el botón verde de descarga sobrevive recargas.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReplicaSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""                       # derivado del gancho / concepto
    mode: str = "versions"                # "versions" | "segments"
    language: str = "es"
    duration_s: float = 0.0
    used_reference_photo: bool = False
    same_product: bool = True
    why_viral: dict = Field(default_factory=dict)
    # Cada item: schema 2-step + opcional `ready_token` (vídeo quemado).
    videos: list[dict] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def touch(self) -> None:
        self.updated_at = _now_iso()
