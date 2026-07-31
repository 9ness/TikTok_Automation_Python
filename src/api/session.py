"""Cookie de sesión firmado (HMAC): firmar, verificar y leer el usuario.

Vive aparte del router de auth porque lo necesitan también las dependencias
(`get_web_user`), y meterlo en el router creaba un import circular:
`dependencies` → `routers.auth` → `dependencies`.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import time
from hashlib import sha256

from fastapi import Request, WebSocket

from src.api import users


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



def usuario_de_request(request: "Request | WebSocket") -> str | None:
    """Username del cookie, o None si no hay sesión válida.

    Acepta también un `WebSocket`: la cola en vivo va por ahí y también tiene
    que saber quién mira.

    En modo dev (sin `AUTH_COOKIE_KEY`) devuelve el usuario forzado por
    `WEB_USER` o el primero de la lista, para no exigir login en local.
    """
    key, name, _ = _cookie_config()
    if not key:
        forzado = os.getenv("WEB_USER", "").strip()
        if forzado and users.existe(forzado):
            return forzado
        listado = users.listar()
        return listado[0]["username"] if listado else None
    token = request.cookies.get(name)
    payload = _verify(token, key) if token else None
    quien = payload.get("u") if payload else None
    return quien if quien and users.existe(quien) else None
