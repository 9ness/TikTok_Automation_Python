"""Enlaces de afiliado POR PRODUCTO y cuenta: `enlaces:<slug>` (un JSON).

`{producto_key: {shein, asin, amazon, titulo, foto_url, precio, nota,
fila_id, clave, actualizado}}`. Un solo documento por cuenta: son decenas o
pocos cientos de productos y se leen siempre todos (listado, página /links).

`producto_key` sale de `clave_producto` (ver `services/tandas.py`): un hash
corto de `tienda|título` normalizados, la MISMA identidad que usa Mis tandas
para «mismo producto» y el escaparate. Así un enlace vale para todas sus
versiones (otro modo del Largo, la copia de Productos Q4, el POV BOF corto).

`sin_equivalente=True` (o `shein`/`asin` = "sin_equivalente" en la API)
marca «no hay producto parecido en SHEIN/Amazon»: cuenta como revisado pero
NO tiene enlace (no se encola ni sale en /links).
"""

from __future__ import annotations

import re
import time

from src.multiplataforma.repos import redis_base

SIN_EQUIVALENTE = "sin_equivalente"
_KEY_RE = re.compile(r"^[a-f0-9]{8,40}$")


def _key(slug: str) -> str:
    return f"enlaces:{slug}"


def key_valida(producto_key: str) -> bool:
    return bool(_KEY_RE.match(producto_key or ""))


def todos(slug: str) -> dict[str, dict]:
    d = redis_base.get_redis().get_json(_key(slug))
    return d if isinstance(d, dict) else {}


def get(slug: str, producto_key: str) -> dict | None:
    return todos(slug).get(producto_key)


def enlace_de(slug: str, producto_key: str) -> str:
    """El enlace utilizable ('' si no hay o es `sin_equivalente`)."""
    d = get(slug, producto_key) or {}
    if d.get("sin_equivalente"):
        return ""
    return str(d.get("enlace") or "")


def guardar(slug: str, producto_key: str, datos: dict) -> dict:
    """Crea o actualiza (fusiona: lo que no venga se conserva)."""
    if not key_valida(producto_key):
        raise ValueError(f"producto_key no válida: {producto_key!r}")
    r = redis_base.get_redis()
    doc = todos(slug)
    actual = dict(doc.get(producto_key) or {})
    actual.update({k: v for k, v in datos.items() if v is not None})
    actual["actualizado"] = time.time()
    doc[producto_key] = actual
    r.set_json(_key(slug), doc)
    return actual


def tocar_meta(slug: str, metas: dict[str, dict]) -> None:
    """Refresca título/fila de los productos que YA tienen entrada (para que
    la foto pública siga la fila vigente). No crea entradas nuevas."""
    doc = todos(slug)
    cambio = False
    for k, meta in metas.items():
        if k in doc:
            nuevo = {**doc[k], **{c: v for c, v in meta.items() if v}}
            if nuevo != doc[k]:
                doc[k] = nuevo
                cambio = True
    if cambio:
        redis_base.get_redis().set_json(_key(slug), doc)


def borrar(slug: str, producto_key: str) -> bool:
    doc = todos(slug)
    if producto_key not in doc:
        return False
    doc.pop(producto_key)
    redis_base.get_redis().set_json(_key(slug), doc)
    return True
