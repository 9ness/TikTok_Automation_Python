"""Estado de cada prenda en Redis (prefijo `nicho_ropa_personas:`).

Un documento por carpeta de prendas (camisetas, mono, bikinis…), con todos sus
productos dentro.

**Separado a propósito del módulo 8.** Las dos versiones del nicho usan las
MISMAS fotos de Drive, pero son vídeos distintos: haber hecho una prenda en
percha no significa haberla hecho puesta por la modelo, y compartir el estado
haría que una se diera por hecha sin estarlo.
"""

from __future__ import annotations

import os
import random
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from src.nicho_ropa_personas.repos.redis_base import get_nicho_ropa_personas_redis

def _key(carpeta: str) -> str:
    return f"productos:{carpeta}"


def _lock(carpeta: str) -> str:
    return f"lock:productos:{carpeta}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_redis():
    r = get_nicho_ropa_personas_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se pueden guardar los "
            "textos de las prendas."
        )
    return r


@contextmanager
def _cerrojo(carpeta: str, espera_s: float = 10.0):
    """Mismo cerrojo que en los otros repos: se guarda el documento ENTERO y
    la API corre con varios workers, así que sin él se pierden escrituras."""
    r = get_nicho_ropa_personas_redis()
    mio = False
    if r.is_available():
        limite = time.monotonic() + espera_s
        while time.monotonic() < limite:
            if r.set_nx(_lock(carpeta), str(os.getpid()), ttl_s=30):
                mio = True
                break
            time.sleep(0.15 + random.random() * 0.2)
    try:
        yield mio
    finally:
        if mio:
            r.delete(_lock(carpeta))


def load(carpeta: str) -> dict:
    r = get_nicho_ropa_personas_redis()
    if not r.is_available():
        return {}
    return r.get_json(_key(carpeta)) or {}


def get_product(carpeta: str, producto: str) -> dict:
    return (load(carpeta).get("productos") or {}).get(str(producto)) or {}


def save_extracted_texts(carpeta: str, textos: dict[str, dict]) -> dict:
    """Guarda lo que devolvió Gemini, sin pisar el estado de los vídeos."""
    with _cerrojo(carpeta):
        r = _require_redis()
        doc = r.get_json(_key(carpeta)) or {}
        productos = doc.setdefault("productos", {})
        for pid, campos in textos.items():
            prod = productos.setdefault(str(pid), {})
            prod.update(campos)
            prod["textos_at"] = _now()
        doc["textos_extraidos"] = True
        doc["updated_at"] = _now()
        r.set_json(_key(carpeta), doc)
        return doc


def update_product(carpeta: str, producto: str, **campos) -> dict:
    """Parche parcial. Ignora los campos que vengan `None`."""
    with _cerrojo(carpeta):
        r = _require_redis()
        doc = r.get_json(_key(carpeta)) or {}
        productos = doc.setdefault("productos", {})
        prod = productos.setdefault(str(producto), {})
        prod.update({k: v for k, v in campos.items() if v is not None})
        prod["updated_at"] = _now()
        r.set_json(_key(carpeta), doc)
        return prod
