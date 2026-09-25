"""Configuración del servidor MCP para agentes (Programa 4 — Tiktok Shop AI Pro).

El MCP deja que una IA (Claude, ChatGPT, Codex…) haga el trabajo de un menú
del Programa 4 sin clicar la app: lista carpetas y productos, prepara textos y
guiones, le da los prompts de cada producto, recibe los clips y lanza el
montaje. Lo único que sigue haciendo en el navegador es generar las imágenes y
los clips fuera (Flow, GenAI Pro, Magnific), que no tienen API.

Cómo se entra: una URL por usuario con un token dentro
(`<base>/api/mcp/<token>`). Es lo que aceptan tal cual los conectores de
Claude y de ChatGPT sin montar OAuth. El token NO se guarda: es un HMAC del
usuario con la clave de las cookies, así que no hay nada que filtrar de Redis
y se revocan TODOS cambiando `MCP_TOKEN_SALT`.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

GUIAS_DIR = Path(__file__).resolve().parent / "guias"

# La URL pública de la app: la que se pega en el conector y la que llevan los
# enlaces de descarga que devuelve el MCP.
def base_publica() -> str:
    return (
        os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        or "https://factory.nebulabsmedia.com"
    )


def _clave() -> bytes:
    key = os.getenv("AUTH_COOKIE_KEY", "").strip() or "dev-sin-clave"
    sal = os.getenv("MCP_TOKEN_SALT", "1").strip()
    return f"{key}|mcp|{sal}".encode()


def token_de(usuario: str) -> str:
    """`<usuario>.<firma>` — el usuario va a la vista para poder depurar."""
    firma = hmac.new(_clave(), usuario.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{usuario}.{firma}"


def usuario_de_token(token: str) -> str | None:
    """El usuario si el token es bueno y el usuario existe; si no, None."""
    from src.api import users

    usuario, _, firma = (token or "").partition(".")
    if not usuario or not firma:
        return None
    esperado = token_de(usuario).partition(".")[2]
    if not hmac.compare_digest(esperado, firma):
        return None
    return usuario if users.existe(usuario) else None


def url_mcp(usuario: str) -> str:
    return f"{base_publica()}/api/mcp/{token_de(usuario)}"


# ---------------------------------------------------------------------------
# Bandeja: la carpeta del Drive que comparten el agente y la app
# ---------------------------------------------------------------------------
# En el PC del operador el Drive está sincronizado (Google Drive para
# escritorio) y en el VPS montado con rclone: los dos ven la MISMA carpeta. El
# MCP deja ahí las fotos y el plan de cada producto, el agente guarda al lado
# lo que genera, y el MCP lo sube a la app desde ahí. Es lo único que funciona
# igual para un agente de escritorio y para uno de servidor.
BANDEJA_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/_agente"


def bandeja_dir(usuario: str) -> Path:
    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    forzada = os.getenv("AGENTE_BANDEJA_DIR", "").strip()  # pruebas / dev
    base = (
        Path(forzada) if forzada
        else raiz / BANDEJA_ROOT if raiz
        else Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "agente_bandeja"
    )
    destino = base / (usuario or "ness")
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def subidas_dir(usuario: str) -> Path:
    """Donde caen los ficheros que el agente sube por HTTP (`/subir`)."""
    destino = (
        Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "agente_subidas" / (usuario or "ness")
    )
    destino.mkdir(parents=True, exist_ok=True)
    return destino


# Tope de lo que se acepta de fuera (clip de 10 s en 1080p ≈ 20-40 MB).
MAX_FICHERO_MB = 300
