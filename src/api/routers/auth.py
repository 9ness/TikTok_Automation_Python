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

from src.api import users
from src.api.dependencies import get_current_user
from src.api.session import _cookie_config, _sign, _verify
from src.api.exceptions import APIError, UnauthorizedError


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
    dependencies=[Depends(get_current_user)],
)


def _available_users() -> list[str]:
    """Usuarios que pueden entrar. Ya no salen de `.env`: la lista vive en
    `src/api/users.py`, con su rol."""
    return [u["username"] for u in users.listar()]


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


class CrearPinRequest(BaseModel):
    username: str
    pin: str
    pin2: str


@router.get("/me")
def get_me(
    request: Request,
) -> dict:
    """Devuelve `{username, available_users}` leyendo el cookie firmado.

    `username` = null si no hay cookie válido. Fallback histórico (solo en
    modo dev sin AUTH_COOKIE_KEY): devuelve `WEB_USER` o el primer
    USERNAME_*."""
    fichas = users.listar()
    available = [u["username"] for u in fichas]
    cookie_key, cookie_name, _ = _cookie_config()
    # Modo dev: sin AUTH_COOKIE_KEY no exigimos login.
    if not cookie_key:
        forced = os.getenv("WEB_USER", "").strip()
        quien = forced or (available[0] if available else "ness")
        return {
            "username": quien,
            "nombre": users.nombre_de(quien),
            "rol": users.rol_de(quien),
            "available_users": available,
            "usuarios": fichas,
        }
    token = request.cookies.get(cookie_name)
    payload = _verify(token, cookie_key) if token else None
    username = payload.get("u") if payload else None
    # Si el usuario desaparece de la lista, la sesión deja de valer.
    if username and not users.existe(username):
        username = None
    return {
        "username": username,
        "nombre": users.nombre_de(username) if username else None,
        "rol": users.rol_de(username) if username else None,
        "available_users": available,
        "usuarios": fichas,
    }


@router.post("/crear-pin")
def crear_pin(payload: CrearPinRequest, response: Response) -> dict:
    """Primera entrada de un usuario: elige su PIN y queda dentro.

    Solo se permite si NO tiene PIN todavía. Cambiarlo después no se hace
    aquí — para eso habría que estar identificado, y no hace falta hoy: son
    tres personas y el PIN se lo pone cada una la primera vez.
    """
    if not users.existe(payload.username):
        raise UnauthorizedError("Usuario desconocido.")
    if users.tiene_pin(payload.username):
        raise APIError(
            "Este usuario ya tiene PIN. Entra con él.", status_code=409,
        )
    if payload.pin != payload.pin2:
        raise APIError("Los dos PIN no coinciden.", status_code=400)
    try:
        users.guardar_pin(payload.username, payload.pin)
    except ValueError as e:
        raise APIError(str(e), status_code=400) from e
    except RuntimeError as e:
        raise APIError(str(e), status_code=503) from e

    # Se entra directamente: acabar de crear el PIN y tener que escribirlo
    # otra vez sería absurdo.
    cookie_key, cookie_name, expiry_days = _cookie_config()
    if cookie_key:
        exp = int(time.time()) + expiry_days * 86400
        token = _sign({"u": payload.username, "exp": exp}, cookie_key)
        response.set_cookie(
            key=cookie_name, value=token, max_age=expiry_days * 86400,
            httponly=True, samesite="lax", secure=True, path="/",
        )
    return {
        "ok": True,
        "username": payload.username,
        "nombre": users.nombre_de(payload.username),
        "rol": users.rol_de(payload.username),
    }


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict:
    cookie_key, cookie_name, expiry_days = _cookie_config()
    if not cookie_key:
        raise APIError(
            "Auth no configurada (falta AUTH_COOKIE_KEY en .env)."
        )
    if not users.existe(payload.username):
        raise UnauthorizedError("Usuario o contraseña inválidos.")
    pwd_hash = users.hash_de(payload.username)
    if not pwd_hash:
        raise APIError(
            "Este usuario todavía no tiene PIN. Créalo desde la pantalla de "
            "entrada.", status_code=409,
        )
    if not _verify_password(payload.password, pwd_hash):
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
