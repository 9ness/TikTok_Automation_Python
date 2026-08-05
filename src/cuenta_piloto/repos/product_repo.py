"""Estado de los productos de la Cuenta Piloto en Redis (`cuenta_piloto:`).

Un documento por USUARIO, con todos sus productos dentro. No hay documento
compartido ni campos privados que separar como en el Nicho POV BOF: allí la
carpeta de Drive es la misma para todos y solo el estado es de cada uno; aquí
el producto ENTERO lo crea un usuario subiendo sus dos fotos, así que la
separación es la clave y ya está.

Lo que sí es distinto de todos los demás repos del proyecto: **`videos` es una
LISTA**. En el resto de nichos un producto tiene un `video_path` y subir otro
vídeo lo pisa sin avisar. Aquí se prueban varios ángulos del mismo producto y
se guardan todos, así que se añade con `add_video()` —bajo cerrojo, porque dos
montajes del mismo producto pueden terminar a la vez y un `update_product`
normal haría que el último leído se cargara al otro.
"""

from __future__ import annotations

import os
import random
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from src.cuenta_piloto.config import _slug_usuario
from src.cuenta_piloto.repos.redis_base import get_cuenta_piloto_redis


def _key(usuario: str) -> str:
    return f"productos:{_slug_usuario(usuario)}"


def _lock(usuario: str) -> str:
    return f"lock:productos:{_slug_usuario(usuario)}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_redis():
    r = get_cuenta_piloto_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se pueden guardar los "
            "productos de la Cuenta Piloto."
        )
    return r


@contextmanager
def _cerrojo(usuario: str, espera_s: float = 10.0):
    """Mismo cerrojo que en los otros repos: se guarda el documento ENTERO y
    la API corre con varios workers, así que sin él se pierden escrituras."""
    r = get_cuenta_piloto_redis()
    mio = False
    if r.is_available():
        limite = time.monotonic() + espera_s
        while time.monotonic() < limite:
            if r.set_nx(_lock(usuario), str(os.getpid()), ttl_s=30):
                mio = True
                break
            time.sleep(0.15 + random.random() * 0.2)
    try:
        yield mio
    finally:
        if mio:
            r.delete(_lock(usuario))


def load(usuario: str) -> dict:
    r = get_cuenta_piloto_redis()
    if not r.is_available():
        return {}
    return r.get_json(_key(usuario)) or {}


def listar(usuario: str) -> list[dict]:
    """Productos del usuario, el más nuevo primero."""
    productos = (load(usuario).get("productos") or {}).values()
    return sorted(productos, key=lambda p: float(p.get("creado_at") or 0), reverse=True)


def get_product(usuario: str, producto: str) -> dict:
    return (load(usuario).get("productos") or {}).get(str(producto)) or {}


def crear_producto(usuario: str, *, foto_limpia: str, foto_ficha: str = "") -> dict:
    """Da de alta un producto con sus fotos ya guardadas en disco.

    El identificador es un correlativo por usuario asignado DENTRO del cerrojo:
    dos altas simultáneas desde el móvil y el portátil darían el mismo número
    si se calculara fuera.
    """
    with _cerrojo(usuario):
        r = _require_redis()
        doc = r.get_json(_key(usuario)) or {}
        productos = doc.setdefault("productos", {})
        siguiente = 1 + max(
            (int(k) for k in productos if str(k).isdigit()), default=0,
        )
        pid = str(siguiente)
        productos[pid] = {
            "id": pid,
            "foto_limpia": str(foto_limpia),
            "foto_ficha": str(foto_ficha or ""),
            "videos": [],
            "creado_at": time.time(),
            "updated_at": _now(),
        }
        doc["updated_at"] = _now()
        r.set_json(_key(usuario), doc)
        return productos[pid]


def update_product(usuario: str, producto: str, **campos) -> dict:
    """Parche parcial. Ignora los campos que vengan `None`.

    No sirve para `videos`: para eso está `add_video()`, que añade en vez de
    reemplazar.
    """
    with _cerrojo(usuario):
        r = _require_redis()
        doc = r.get_json(_key(usuario)) or {}
        productos = doc.setdefault("productos", {})
        prod = productos.setdefault(str(producto), {"id": str(producto), "videos": []})
        prod.update({k: v for k, v in campos.items() if v is not None})
        prod["updated_at"] = _now()
        doc["updated_at"] = _now()
        r.set_json(_key(usuario), doc)
        return prod


def add_video(usuario: str, producto: str, *, path: str, sexo: str = "",
              job_id: str = "") -> dict:
    """AÑADE un vídeo montado a la lista del producto. Nunca pisa los previos.

    Es la razón de ser de este nicho: el mismo producto se prueba varias veces.
    """
    with _cerrojo(usuario):
        r = _require_redis()
        doc = r.get_json(_key(usuario)) or {}
        productos = doc.setdefault("productos", {})
        prod = productos.setdefault(str(producto), {"id": str(producto)})
        videos = prod.setdefault("videos", [])
        if not isinstance(videos, list):
            # Defensa por si algún día alguien guarda ahí un string suelto:
            # mejor arrancar lista nueva que reventar el montaje ya hecho.
            videos = []
            prod["videos"] = videos
        videos.append({
            "path": str(path),
            "sexo": str(sexo or ""),
            "job_id": str(job_id or ""),
            "at": int(time.time()),
        })
        prod["updated_at"] = _now()
        doc["updated_at"] = _now()
        r.set_json(_key(usuario), doc)
        return prod


def borrar_producto(usuario: str, producto: str) -> bool:
    """Quita el producto del índice y borra sus ficheros (fotos y vídeos).

    Se borra de Redis PRIMERO: si falla el borrado de un fichero, el producto
    ya no aparece —que es lo que pidió el operador— y lo único que queda es
    basura en disco, no un producto fantasma en la pantalla.
    """
    with _cerrojo(usuario):
        r = _require_redis()
        doc = r.get_json(_key(usuario)) or {}
        productos = doc.setdefault("productos", {})
        prod = productos.pop(str(producto), None)
        if prod is None:
            return False
        doc["updated_at"] = _now()
        r.set_json(_key(usuario), doc)

    rutas = [prod.get("foto_limpia"), prod.get("foto_ficha")]
    rutas += [v.get("path") for v in (prod.get("videos") or []) if isinstance(v, dict)]
    for ruta in rutas:
        if not ruta:
            continue
        try:
            Path(ruta).unlink(missing_ok=True)
        except OSError:
            pass
    return True


def save_extracted_texts(usuario: str, textos: dict[str, dict]) -> dict:
    """Guarda lo que devolvió Gemini, sin tocar la lista de vídeos."""
    with _cerrojo(usuario):
        r = _require_redis()
        doc = r.get_json(_key(usuario)) or {}
        productos = doc.setdefault("productos", {})
        for pid, campos in textos.items():
            prod = productos.setdefault(str(pid), {"id": str(pid), "videos": []})
            prod.update(campos)
            prod["textos_at"] = _now()
            prod["updated_at"] = _now()
        doc["updated_at"] = _now()
        r.set_json(_key(usuario), doc)
        return doc
