"""Endpoints de identidad — login con cookie firmado (HMAC).

La autenticación contra la API se hace vía `X-API-Key` (header de máquina),
pero el usuario HUMANO que está usando el frontend se identifica vía un
cookie firmado HTTP-only emitido tras un login con bcrypt.

Variables de entorno (mismas que la auth Streamlit):
  AUTH_COOKIE_KEY        — token random (firma HMAC del cookie).
  USERNAME_<KEY>=ness    — username del usuario.
  PASSWORD_HASH_<KEY>=$2b$... — bcrypt hash del password.
  AUTH_COOKIE_NAME       — opcional, default "tiktok_factory_auth".
  AUTH_COOKIE_EXPIRY_DAYS — opcional, default 30.

Endpoints:
- GET  /api/v1/auth/me     → { username | null, available_users }
- POST /api/v1/auth/login  → valida bcrypt, emite cookie. body: {username, password}
- POST /api/v1/auth/logout → borra cookie
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import time
from hashlib import sha256

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from src.api.dependencies import get_current_user
from src.api.exceptions import APIError, UnauthorizedError


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
    dependencies=[Depends(get_current_user)],
)


def _available_users() -> list[str]:
    """Lista de usuarios definidos en `.env` (USERNAME_*)."""
    out: list[str] = []
    for env_key, val in os.environ.items():
        if env_key.startswith("USERNAME_") and val.strip():
            out.append(val.strip())
    return sorted(set(out))


def _load_credentials() -> dict[str, str]:
    """Devuelve {username: password_hash} leído de los pares
    USERNAME_<KEY> / PASSWORD_HASH_<KEY> del entorno."""
    creds: dict[str, str] = {}
    keys: set[str] = set()
    for env_key in os.environ:
        if env_key.startswith("USERNAME_"):
            keys.add(env_key[len("USERNAME_"):])
    for k in keys:
        username = os.getenv(f"USERNAME_{k}", "").strip()
        pwd_hash = os.getenv(f"PASSWORD_HASH_{k}", "").strip()
        if username and pwd_hash:
            creds[username] = pwd_hash
    return creds


def _cookie_config() -> tuple[str, str, int]:
    """(cookie_key, cookie_name, expiry_days). Lanza si falta cookie_key."""
    key = os.getenv("AUTH_COOKIE_KEY", "").strip()
    name = os.getenv("AUTH_COOKIE_NAME", "tiktok_factory_auth").strip() or "tiktok_factory_auth"
    try:
        days = int(os.getenv("AUTH_COOKIE_EXPIRY_DAYS", "30"))
    except ValueError:
        days = 30
    return key, name, days


def _sign(payload: dict, key: str) -> str:
    """Devuelve `b64(payload).b64(hmac)`. Payload es JSON corto."""
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode()
    sig = hmac.new(key.encode(), body.encode(), sha256).digest()
    sig_b = base64.urlsafe_b64encode(sig).decode()
    return f"{body}.{sig_b}"


def _verify(token: str, key: str) -> dict | None:
    """Devuelve el payload si la firma es válida y no ha expirado, si no None."""
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


def _verify_password(password: str, bcrypt_hash: str) -> bool:
    """Valida `password` contra el bcrypt hash. Devuelve False si bcrypt
    no está disponible o el hash es inválido."""
    try:
        import bcrypt
    except ImportError:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), bcrypt_hash.encode("utf-8"))
    except Exception:
        return False


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/me")
def get_me(
    request: Request,
) -> dict:
    """Devuelve `{username, available_users}` leyendo el cookie firmado.

    `username` = null si no hay cookie válido. Fallback histórico (solo en
    modo dev sin AUTH_COOKIE_KEY): devuelve `WEB_USER` o el primer
    USERNAME_*."""
    available = _available_users()
    cookie_key, cookie_name, _ = _cookie_config()
    # Modo dev: sin AUTH_COOKIE_KEY no exigimos login.
    if not cookie_key:
        forced = os.getenv("WEB_USER", "").strip()
        return {
            "username": forced or (available[0] if available else "ness"),
            "available_users": available,
        }
    token = request.cookies.get(cookie_name)
    payload = _verify(token, cookie_key) if token else None
    username = payload.get("u") if payload else None
    # Validar que el user del cookie aún existe en .env (revocación
    # implícita si borras al usuario del .env).
    if username and username not in _load_credentials():
        username = None
    return {"username": username, "available_users": available}


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict:
    creds = _load_credentials()
    cookie_key, cookie_name, expiry_days = _cookie_config()
    if not cookie_key:
        raise APIError(
            "Auth no configurada (falta AUTH_COOKIE_KEY en .env)."
        )
    if not creds:
        raise APIError(
            "No hay usuarios configurados (define USERNAME_X y PASSWORD_HASH_X en .env)."
        )
    pwd_hash = creds.get(payload.username)
    if not pwd_hash or not _verify_password(payload.password, pwd_hash):
        raise UnauthorizedError("Usuario o contraseña inválidos.")

    exp = int(time.time()) + expiry_days * 86400
    token = _sign({"u": payload.username, "exp": exp}, cookie_key)
    response.set_cookie(
        key=cookie_name,
        value=token,
        max_age=expiry_days * 86400,
        httponly=True,
        samesite="lax",
        # `secure=True` requiere HTTPS — siempre lo usamos vía Tailscale Funnel
        # o dominio TLS. En dev local plain HTTP el browser igualmente acepta
        # el cookie con `secure=False`; aquí lo decidimos por env.
        secure=os.getenv("AUTH_COOKIE_SECURE", "true").lower() != "false",
        path="/",
    )
    return {"username": payload.username, "exp": exp}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    _, cookie_name, _ = _cookie_config()
    response.delete_cookie(cookie_name, path="/")
