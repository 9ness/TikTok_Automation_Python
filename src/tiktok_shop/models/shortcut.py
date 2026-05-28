"""Shortcut de operador: combinación cuenta×producto guardada en Redis
para sync entre dispositivos.

Antes vivía solo en `localStorage` del navegador del operador. Lo
server-side permite que el mismo operador (ness, buga, ...) vea sus
mismos shortcuts desde PC y móvil.

Scope: por operador (no por TikTok user). Cada operador tiene su propia
lista. La combinación (operator, user_id, product_id) es única — no
duplicamos shortcuts equivalentes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperatorShortcut(BaseModel):
    """Combinación cuenta TikTok + producto pinneada por un operador."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    operator: str           # "ness", "buga", ... (extraído del cookie auth)
    user_id: str            # TikTok user id (no username — invariante)
    product_id: str         # Product id
    created_at: str = Field(default_factory=_utc_now)
