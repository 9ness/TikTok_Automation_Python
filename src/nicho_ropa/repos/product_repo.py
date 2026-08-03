"""Estado de cada prenda en Redis (prefijo `nicho_ropa:`).

Mucho más simple que el del Nicho POV BOF: aquí hay UNA sola carpeta, así que
no hay progreso por carpeta ni documentos por usuario. Un único documento con
todos los productos dentro.
"""

from __future__ import annotations

import os
import random
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from src.nicho_ropa.repos.redis_base import get_nicho_ropa_redis

_KEY = "productos"
_LOCK = "lock:productos"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_redis():
    r = get_nicho_ropa_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se pueden guardar los "
            "textos de las prendas."
        )
    return r


@contextmanager
def _cerrojo(espera_s: float = 10.0):
    """Mismo cerrojo que en los otros repos: se guarda el documento ENTERO y
    la API corre con varios workers, así que sin él se pierden escrituras."""
    r = get_nicho_ropa_redis()
    mio = False
    if r.is_available():
        limite = time.monotonic() + espera_s
        while time.monotonic() < limite:
            if r.set_nx(_LOCK, str(os.getpid()), ttl_s=30):
                mio = True
                break
            time.sleep(0.15 + random.random() * 0.2)
    try:
        yield mio
    finally:
        if mio:
            r.delete(_LOCK)


def load() -> dict:
    r = get_nicho_ropa_redis()
    if not r.is_available():
        return {}
    return r.get_json(_KEY) or {}


def get_product(producto: str) -> dict:
    return (load().get("productos") or {}).get(str(producto)) or {}


def save_extracted_texts(textos: dict[str, dict]) -> dict:
    """Guarda lo que devolvió Gemini, sin pisar el estado de los vídeos."""
    with _cerrojo():
        r = _require_redis()
        doc = r.get_json(_KEY) or {}
        productos = doc.setdefault("productos", {})
        for pid, campos in textos.items():
            prod = productos.setdefault(str(pid), {})
            prod.update(campos)
            prod["textos_at"] = _now()
        doc["textos_extraidos"] = True
        doc["updated_at"] = _now()
        r.set_json(_KEY, doc)
        return doc


def update_product(producto: str, **campos) -> dict:
    """Parche parcial. Ignora los campos que vengan `None`."""
    with _cerrojo():
        r = _require_redis()
        doc = r.get_json(_KEY) or {}
        productos = doc.setdefault("productos", {})
        prod = productos.setdefault(str(producto), {})
        prod.update({k: v for k, v in campos.items() if v is not None})
        prod["updated_at"] = _now()
        r.set_json(_KEY, doc)
        return prod
