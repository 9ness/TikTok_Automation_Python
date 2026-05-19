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


def _full_key(name: str, namespace: str | None) -> str:
    """Construye la clave Redis final: `tiktokCR:config:[<ns>:]<name>`.

    El namespace permite separar presets por nicho (Presidentes vs POV vs
    otros) sin colisionar el `__default`. Si `namespace=None` se mantiene
    el comportamiento legacy (clave plana).
    """
    name = name.strip()
    if namespace:
        return f"{PREFIX}{namespace.strip()}:{name}"
    return PREFIX + name


def save_config(name: str, config: dict, namespace: str | None = None) -> bool:
    """Guarda un preset bajo `tiktokCR:config:[ns:]{name}`. Devuelve True si OK."""
    if not is_available() or not name.strip():
        return False
    key = _full_key(name, namespace)
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


def load_config(name: str, namespace: str | None = None) -> dict | None:
    """Recupera el preset y lo devuelve como dict, o None si no existe / error."""
    if not is_available() or not name.strip():
        return None
    key = _full_key(name, namespace)
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


def list_configs(namespace: str | None = None) -> list[str]:
    """Devuelve nombres de presets (sin prefijo ni namespace), ordenados.

    - Si `namespace=None` (legacy Presidentes), devuelve TODOS los nombres
      bajo `tiktokCR:config:*` (incluidos los namespaceados, que aparecen
      como `<ns>:<name>` — Presidentes los ignora al filtrarlos por
      ausencia de ":" en la lista).
    - Si `namespace` está definido, devuelve solo los que matchean
      `tiktokCR:config:<ns>:*` con el namespace stripeado.
    """
    if not is_available():
        return []
    if namespace:
        full_prefix = f"{PREFIX}{namespace.strip()}:"
        pattern = full_prefix + "*"
    else:
        full_prefix = PREFIX
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
        names = sorted(k[len(full_prefix):] for k in keys if k.startswith(full_prefix))
        # En modo legacy, filtra los keys que tengan namespace anidado
        # (cualquier ":") para no contaminar la lista de Presidentes.
        if not namespace:
            names = [n for n in names if ":" not in n]
        return names
    except Exception as e:
        print(f"[configs_store] list_configs error: {e}")
        return []


def delete_config(name: str, namespace: str | None = None) -> bool:
    """Borra un preset. Devuelve True si Upstash respondió OK."""
    if not is_available() or not name.strip():
        return False
    key = _full_key(name, namespace)
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
