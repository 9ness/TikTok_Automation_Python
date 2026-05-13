"""Endpoints de identidad — solo lectura, no hay flow de login real.

La autenticación contra la API se hace vía `X-API-Key` (header), pero el
usuario humano que está usando el frontend es uno de los configurados en
`.env` (USERNAME_NESS / USERNAME_BUGA). Como NO hay login interactivo en
el stack Next.js (compartimos la URL Tailscale), el usuario activo se
fija por env var `WEB_USER` (o `ness` por defecto si hay credenciales).

Endpoint:
- GET /api/v1/auth/me → {username, available_users}
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
    dependencies=[Depends(get_current_user)],
)


def _available_users() -> list[str]:
    """Lista de usuarios definidos en `.env` (USERNAME_*). Vacía si ninguno."""
    out: list[str] = []
    for env_key, val in os.environ.items():
        if env_key.startswith("USERNAME_") and val.strip():
            out.append(val.strip())
    return sorted(set(out))


@router.get("/me")
def get_me() -> dict:
    """Devuelve el usuario web activo y la lista de configurados.

    El usuario activo se determina así:
      1. `WEB_USER` env var (override explícito).
      2. Primer `USERNAME_*` definido.
      3. "ness" como último fallback (modo dev).
    """
    available = _available_users()
    active = os.getenv("WEB_USER", "").strip()
    if not active:
        active = available[0] if available else "ness"
    return {"username": active, "available_users": available}
