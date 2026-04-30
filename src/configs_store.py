"""Persistencia de configuraciones de UI vía Upstash Redis REST API.

Usa el endpoint REST de Upstash (no requiere instalar redis-py). Las claves se guardan
con el prefijo ``tiktokCR:config:`` para diferenciarlas de cualquier otra cosa que haya
en la base de datos (p.ej. data del proyecto bet-ai-master que comparte instancia).

Claves leídas del .env:
    UPSTASH_REDIS_REST_URL
    UPSTASH_REDIS_REST_TOKEN

Si las claves no están definidas, las funciones devuelven valores neutros (False o []),
permitiendo que la UI degrade limpiamente.
"""

from __future__ import annotations

import json
import os
import urllib.parse

import requests
from dotenv import load_dotenv

load_dotenv()

UPSTASH_URL = (os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""

PREFIX = "tiktokCR:config:"


def is_available() -> bool:
    """True si tenemos credenciales de Upstash en el entorno."""
    return bool(UPSTASH_URL and UPSTASH_TOKEN)


def _headers() -> dict:
    return {"Authorization": f"Bearer {UPSTASH_TOKEN}"}


def _enc(s: str) -> str:
    """URL-encode aceptando los dos puntos del prefijo."""
    return urllib.parse.quote(s, safe="")


def save_config(name: str, config: dict) -> bool:
    """Guarda un preset bajo `tiktokCR:config:{name}`. Devuelve True si OK."""
    if not is_available() or not name.strip():
        return False
    key = PREFIX + name.strip()
    body = json.dumps(config, ensure_ascii=False)
    try:
        r = requests.post(
            f"{UPSTASH_URL}/set/{_enc(key)}",
            headers=_headers(),
            data=body.encode("utf-8"),
            timeout=10,
        )
        return r.status_code == 200 and r.json().get("result") == "OK"
    except Exception as e:
        print(f"[configs_store] save_config error: {e}")
        return False


def load_config(name: str) -> dict | None:
    """Recupera el preset y lo devuelve como dict, o None si no existe / error."""
    if not is_available() or not name.strip():
        return None
    key = PREFIX + name.strip()
    try:
        r = requests.get(
            f"{UPSTASH_URL}/get/{_enc(key)}",
            headers=_headers(),
            timeout=10,
        )
        if r.status_code != 200:
            return None
        result = r.json().get("result")
        if result is None:
            return None
        return json.loads(result)
    except Exception as e:
        print(f"[configs_store] load_config error: {e}")
        return None


def list_configs() -> list[str]:
    """Devuelve los nombres de presets guardados (sin el prefijo), ordenados alfabéticamente."""
    if not is_available():
        return []
    pattern = PREFIX + "*"
    try:
        r = requests.get(
            f"{UPSTASH_URL}/keys/{_enc(pattern)}",
            headers=_headers(),
            timeout=10,
        )
        if r.status_code != 200:
            return []
        keys = r.json().get("result") or []
        names = sorted(k[len(PREFIX):] for k in keys if k.startswith(PREFIX))
        return names
    except Exception as e:
        print(f"[configs_store] list_configs error: {e}")
        return []


def delete_config(name: str) -> bool:
    """Borra un preset. Devuelve True si Upstash respondió OK."""
    if not is_available() or not name.strip():
        return False
    key = PREFIX + name.strip()
    try:
        r = requests.get(
            f"{UPSTASH_URL}/del/{_enc(key)}",
            headers=_headers(),
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"[configs_store] delete_config error: {e}")
        return False
