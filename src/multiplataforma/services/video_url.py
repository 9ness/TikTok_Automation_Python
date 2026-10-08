"""URL pública y temporal de un vídeo local (IG y Threads la descargan).

`<PUBLIC_BASE_URL>/api/v1/multiplataforma/archivo/<token>` donde
`token = base64url({"p": ruta, "e": caduca}) + "." + HMAC`. Misma idea que el
token del MCP (`src/agente_mcp/config.py`): no se guarda nada, la firma es un
HMAC con `AUTH_COOKIE_KEY` + un contexto propio, así una firma de aquí no vale
como token del MCP ni al revés. Solo se sirven extensiones de vídeo/imagen.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from src.multiplataforma import config

RUTA_ARCHIVO = "/api/v1/multiplataforma/archivo"


def _clave() -> bytes:
    key = os.getenv("AUTH_COOKIE_KEY", "").strip() or "dev-sin-clave"
    return f"{key}|multiplataforma|video".encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _firma(cuerpo: str) -> str:
    return hmac.new(_clave(), cuerpo.encode(), hashlib.sha256).hexdigest()[:40]


def servible(ruta: str) -> bool:
    return Path(ruta).suffix.lower() in config.EXTENSIONES_SERVIBLES


def ruta_permitida(ruta: str) -> bool:
    """Solo se sirven ficheros bajo la raíz Multiplataforma del Drive,
    `temp_work/` o `API_TEMP_ROOT` (ver `config.raices_servibles`). Se
    resuelven symlinks y `..` antes de comparar."""
    try:
        p = Path(ruta).resolve()
    except (OSError, RuntimeError):
        return False
    for raiz in config.raices_servibles():
        try:
            if p.is_relative_to(raiz.resolve()):
                return True
        except (OSError, RuntimeError):
            continue
    return False


def firmar(ruta: str, ttl: int | None = None, ahora: float | None = None) -> str:
    """Token firmado para `ruta` (no comprueba que exista: en prueba puede no estar)."""
    if not servible(ruta):
        raise ValueError(f"Solo se firman vídeos/imágenes: {ruta}")
    ahora = time.time() if ahora is None else ahora
    caduca = int(ahora + (config.VIDEO_URL_TTL_S if ttl is None else ttl))
    cuerpo = _b64(json.dumps({"p": str(ruta), "e": caduca}, separators=(",", ":")).encode())
    return f"{cuerpo}.{_firma(cuerpo)}"


def verificar(token: str, ahora: float | None = None) -> str | None:
    """La ruta si el token es bueno y no ha caducado; si no, None."""
    cuerpo, _, firma = (token or "").partition(".")
    if not cuerpo or not firma or not hmac.compare_digest(_firma(cuerpo), firma):
        return None
    try:
        d = json.loads(_unb64(cuerpo))
    except (ValueError, json.JSONDecodeError):
        return None
    ahora = time.time() if ahora is None else ahora
    if float(d.get("e", 0)) < ahora:
        return None
    ruta = str(d.get("p") or "")
    return ruta if ruta and servible(ruta) else None


def url_publica(ruta: str, ttl: int | None = None) -> str:
    """URL completa: lo que se pasa como `video_url` / `cover_url`."""
    if ruta.startswith(("http://", "https://")):
        return ruta
    return f"{config.base_publica()}{RUTA_ARCHIVO}/{firmar(ruta, ttl)}"
