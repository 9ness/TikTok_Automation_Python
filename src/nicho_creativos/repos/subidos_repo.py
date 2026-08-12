"""Qué creativos se han publicado ya, marcado a mano por el operador.

Es PROPIO de este nicho y no se comparte con el Nicho POV BOF aunque el
producto sea el mismo: allí "Subido" significa que se publicó el VÍDEO, y aquí
que se publicó el CREATIVO. Son dos publicaciones distintas del mismo producto,
así que mezclarlas daría por hecho trabajo que nadie ha hecho.

(Distinto del escaparate y de los vendidos, que sí son únicos y globales: meter
el producto en el Marketplace o venderlo pasa una sola vez, lo grabe el nicho
que lo grabe.)

Tampoco lo pone ningún runner: en Creativos Pro no hay montaje que termine, la
imagen se genera fuera. Lo marca el operador cuando sube el creativo.

Se guarda `producto -> hora` y no un simple SET: el operador quiere ver A QUÉ
HORA marcó cada uno, para saber si al repetir un producto el toque entró.

Key: `nicho_creativos:subidos:<source>:<carpeta>[:usuario]` → {producto: epoch}
"""

from __future__ import annotations

import time

from src.nicho_creativos.repos.redis_base import get_nicho_creativos_redis


def _key(source: str, folder: str, usuario: str = "") -> str:
    """Es POR USUARIO: cada uno publica en su cuenta. `ness` se queda en la
    clave sin usuario, que es donde está su histórico."""
    base = f"subidos:{source}:{folder}"
    if not usuario or usuario == "ness":
        return base
    return f"{base}:{usuario}"


def subidos(source: str, folder: str, usuario: str = "") -> dict[str, float]:
    """`{producto: hora}` de los ya publicados. Vacío si Redis no está: es un
    dato de progreso, no vale la pena tumbar la pantalla por él."""
    r = get_nicho_creativos_redis()
    if not r.is_available():
        return {}
    doc = r.get_json(_key(source, folder, usuario)) or {}
    return {str(k): float(v or 0) for k, v in doc.items()}


def marcar(
    source: str, folder: str, producto: str, subido: bool, usuario: str = "",
) -> None:
    r = get_nicho_creativos_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede guardar qué "
            "creativos has subido."
        )
    clave = _key(source, folder, usuario)
    doc = r.get_json(clave) or {}
    if subido:
        doc[str(producto)] = time.time()
    else:
        doc.pop(str(producto), None)
    # Se comprueba que la escritura CONFIRMA. Sin esto el fallo es mudo: la
    # pantalla se pinta como si hubiera guardado y al recargar no está. Pasó de
    # verdad — al cambiar el formato de SET a JSON, Redis rechazaba el `set`
    # sobre las claves viejas (tipo distinto) y el "Subido" se perdía.
    if not r.set_json(clave, doc):
        raise RuntimeError(
            "Redis no aceptó guardar qué creativos has subido. Vuelve a "
            "intentarlo; si sigue igual, avisa (puede ser un dato en formato "
            "antiguo)."
        )
