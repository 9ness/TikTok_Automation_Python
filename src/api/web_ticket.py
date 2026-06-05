"""Verificación de tickets firmados por la web de cliente (nebulabs-media).

La web (Vercel) emite un JWT corto (HS256) firmado con un secreto compartido
`WEB_UPLOAD_SECRET`. El navegador del cliente lo lleva al box para subir
vídeos directamente (los bytes NO pasan por Vercel). El box valida el ticket
y resuelve el EditorUser por `account_email`.

Claims esperados: { email, day (YYYY-MM-DD), scope, iat, exp }.

Implementación HS256 manual (hmac+base64url) para no añadir dependencias y
ser compatible con `jose` (el que usa la web). Aislado de la auth X-API-Key
existente — esto es un mecanismo NUEVO y separado.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from fastapi import Header

from src.api.exceptions import UnauthorizedError


def _secret() -> str:
    return os.getenv("WEB_UPLOAD_SECRET") or ""


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


@dataclass
class TicketClaims:
    email: str
    day: str
    scope: str
    raw: dict


def verify_ticket(token: str) -> TicketClaims:
    """Valida firma HS256 + expiración. Lanza UnauthorizedError si falla."""
    secret = _secret()
    if not secret:
        raise UnauthorizedError("WEB_UPLOAD_SECRET no configurado en el servidor.")
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise UnauthorizedError("Ticket malformado.")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        given = _b64url_decode(sig_b64)
    except Exception:
        raise UnauthorizedError("Firma del ticket inválida.")
    if not hmac.compare_digest(expected, given):
        raise UnauthorizedError("Firma del ticket inválida.")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise UnauthorizedError("Payload del ticket inválido.")

    exp = payload.get("exp")
    if exp is not None and time.time() > float(exp):
        raise UnauthorizedError("Ticket caducado.")

    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise UnauthorizedError("Ticket sin email.")

    return TicketClaims(
        email=email,
        day=str(payload.get("day") or ""),
        scope=str(payload.get("scope") or ""),
        raw=payload,
    )


def make_ticket(email: str, day: str, *, scope: str = "upload", ttl_s: int = 1800) -> str:
    """Emite un ticket (para tests locales / scripts). En prod lo firma la web."""
    secret = _secret()
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"email": email.strip().lower(), "day": day, "scope": scope, "iat": now, "exp": now + ttl_s}
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode("utf-8"), f"{h}.{p}".encode("ascii"), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}"


def require_web_ticket(
    authorization: str | None = Header(default=None),
) -> TicketClaims:
    """Dependencia FastAPI: extrae `Authorization: Bearer <ticket>` y lo valida."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Falta el ticket (Authorization: Bearer).")
    token = authorization.split(" ", 1)[1].strip()
    return verify_ticket(token)
