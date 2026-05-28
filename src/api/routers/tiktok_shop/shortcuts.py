"""Endpoints CRUD de shortcuts cuenta+producto del operador.

Scope por operador (ness, buga, ...) — usa el cookie firmado para
identificar quién hace la llamada. Permite que el mismo operador vea sus
shortcuts desde PC y móvil (cualquier dispositivo que esté logueado).

Endpoints:
  GET    /api/v1/tiktok-shop/shortcuts            → lista del operador
  POST   /api/v1/tiktok-shop/shortcuts            → crea (idempotente por combo)
  DELETE /api/v1/tiktok-shop/shortcuts/{id}       → borra (solo si es del operador)
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import time
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from src.api.dependencies import get_current_user, get_redis
from src.api.exceptions import APIError, ValidationError
from src.tiktok_shop.repos import ShopRedis, ShortcutRepo


router = APIRouter(
    prefix="/api/v1/tiktok-shop/shortcuts",
    tags=["tiktok-shop · shortcuts"],
    dependencies=[Depends(get_current_user)],
)


# ─────────────────────────────────────────────────────────────────────
# Helper: leer operador desde el cookie firmado (compartido con auth.py)
# ─────────────────────────────────────────────────────────────────────
def _cookie_name() -> str:
    return os.getenv("AUTH_COOKIE_NAME", "tiktok_factory_auth").strip() or "tiktok_factory_auth"


def _cookie_key() -> str:
    return os.getenv("AUTH_COOKIE_KEY", "").strip()


def _verify_cookie(token: str, key: str) -> dict | None:
    if not token or "." not in token:
        return None
    body, sig_b = token.rsplit(".", 1)
    try:
        expected = hmac.new(key.encode(), body.encode(), sha256).digest()
        actual = base64.urlsafe_b64decode(sig_b.encode())
    except Exception:
        return None
    if not hmac.compare_digest(expected, actual):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode()).decode())
    except Exception:
        return None
    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and time.time() > exp:
        return None
    return payload


def _fallback_operator() -> str:
    """Modo dev sin cookie firmado: usa WEB_USER o primer USERNAME_*."""
    forced = os.getenv("WEB_USER", "").strip()
    if forced:
        return forced
    for env_key, val in os.environ.items():
        if env_key.startswith("USERNAME_") and val.strip():
            return val.strip()
    return "anonymous"


def get_current_operator(request: Request) -> str:
    """Devuelve el operator username (ness, buga, ...) del cookie firmado.
    Si la cookie no está configurada (modo dev) usa WEB_USER o el primer
    USERNAME_*. Si no hay nada, devuelve 'anonymous'."""
    key = _cookie_key()
    if not key:
        return _fallback_operator()
    token = request.cookies.get(_cookie_name())
    payload = _verify_cookie(token or "", key) if token else None
    if payload and isinstance(payload.get("u"), str):
        return payload["u"]
    return _fallback_operator()


def get_shortcut_repo(
    redis: Annotated[ShopRedis, Depends(get_redis)],
) -> ShortcutRepo:
    return ShortcutRepo(redis)


# ─────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────
class ShortcutResponse(BaseModel):
    id: str
    operator: str
    user_id: str
    product_id: str
    created_at: str


class ShortcutListResponse(BaseModel):
    items: list[ShortcutResponse]
    total: int


class CreateShortcutRequest(BaseModel):
    user_id: str
    product_id: str


# ─────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────
@router.get("", response_model=ShortcutListResponse)
def list_shortcuts(
    request: Request,
    repo: Annotated[ShortcutRepo, Depends(get_shortcut_repo)],
) -> ShortcutListResponse:
    operator = get_current_operator(request)
    items = repo.list_by_operator(operator)
    return ShortcutListResponse(
        items=[ShortcutResponse(**s.model_dump()) for s in items],
        total=len(items),
    )


@router.post("", response_model=ShortcutResponse, status_code=201)
def create_shortcut(
    payload: CreateShortcutRequest,
    request: Request,
    repo: Annotated[ShortcutRepo, Depends(get_shortcut_repo)],
) -> ShortcutResponse:
    if not payload.user_id.strip() or not payload.product_id.strip():
        raise ValidationError("user_id y product_id son requeridos")
    operator = get_current_operator(request)
    sc = repo.create(
        operator=operator,
        user_id=payload.user_id.strip(),
        product_id=payload.product_id.strip(),
    )
    return ShortcutResponse(**sc.model_dump())


@router.delete("/{shortcut_id}", status_code=204)
def delete_shortcut(
    shortcut_id: str,
    request: Request,
    repo: Annotated[ShortcutRepo, Depends(get_shortcut_repo)],
) -> None:
    operator = get_current_operator(request)
    deleted = repo.delete(operator, shortcut_id)
    if not deleted:
        raise APIError(
            f"Shortcut '{shortcut_id}' no existe o no es de tu operador.",
            status_code=404,
        )
