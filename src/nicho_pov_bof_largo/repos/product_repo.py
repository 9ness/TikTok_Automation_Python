"""Estado del Nicho POV BOF Largo por carpeta de productos (`nicho_pov_bof_largo:`).

**Los textos del producto NO se guardan aquí.** Título, tienda, caption y
emojis salen de la foto de Drive, cuestan llamadas de Gemini y son un dato
objetivo del producto: se leen del Nicho POV BOF, que es el que los extrae. Si
se duplicaran, el mismo producto costaría la extracción dos veces y las dos
copias se irían separando en cuanto alguien corrigiera un título.

Aquí vive SOLO lo propio de este nicho, y por usuario:

    clip1_path, clip2_path   los dos vídeos subidos
    guion, subliminal        lo que escribió la IA para ESTE producto
    voz_label, voz_sexo      qué voz le tocó
    video_path, video_listo_at, uploaded

Es por usuario porque el material lo sube cada uno: dos operadores pueden
hacer el mismo producto por separado y ninguno debe ver los clips del otro.

Key: `nicho_pov_bof_largo:folder:<source>:<carpeta>:u:<usuario>`
"""

from __future__ import annotations

import os
import random
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from src.nicho_pov_bof_largo.repos.redis_base import get_nicho_pov_bof_largo_redis


def _slug_usuario(usuario: str) -> str:
    return (usuario or "").strip() or "ness"


def _key(source: str, folder: str, usuario: str) -> str:
    return f"folder:{source}:{folder}:u:{_slug_usuario(usuario)}"


def _lock(source: str, folder: str, usuario: str) -> str:
    return f"lock:{_key(source, folder, usuario)}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_redis():
    r = get_nicho_pov_bof_largo_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede guardar el "
            "estado del Nicho POV BOF Largo."
        )
    return r


@contextmanager
def _cerrojo(source: str, folder: str, usuario: str, espera_s: float = 10.0):
    """Se guarda el documento ENTERO y la API corre con varios workers: sin
    cerrojo se pierden escrituras (dos clips subidos a la vez, por ejemplo)."""
    r = get_nicho_pov_bof_largo_redis()
    mio = False
    if r.is_available():
        limite = time.monotonic() + espera_s
        while time.monotonic() < limite:
            if r.set_nx(_lock(source, folder, usuario), str(os.getpid()), ttl_s=30):
                mio = True
                break
            time.sleep(0.15 + random.random() * 0.2)
    try:
        yield mio
    finally:
        if mio:
            r.delete(_lock(source, folder, usuario))


def load_folder(source: str, folder: str, usuario: str = "") -> dict:
    r = get_nicho_pov_bof_largo_redis()
    if not r.is_available():
        return {}
    return r.get_json(_key(source, folder, usuario)) or {}


def get_product(source: str, folder: str, producto: str, usuario: str = "") -> dict:
    return (load_folder(source, folder, usuario).get("productos") or {}).get(
        str(producto), {}
    )


def update_product(
    source: str, folder: str, producto: str, usuario: str = "", **campos
) -> dict:
    """Parche parcial. Ignora los campos que vengan `None`."""
    with _cerrojo(source, folder, usuario):
        r = _require_redis()
        clave = _key(source, folder, usuario)
        doc = r.get_json(clave) or {}
        productos = doc.setdefault("productos", {})
        prod = productos.setdefault(str(producto), {})
        prod.update({k: v for k, v in campos.items() if v is not None})
        prod["updated_at"] = _now()
        doc["updated_at"] = _now()
        r.set_json(clave, doc)
        return prod


def textos_producto(source: str, folder: str, producto: str, usuario: str = "") -> dict:
    """Título / tienda / caption / emojis, leídos del Nicho POV BOF.

    Es el único sitio donde se extraen: aquí solo se consultan.
    """
    from src.nicho_pov_bof.repos import product_repo as pov

    return pov.get_product(source, folder, producto, usuario) or {}
