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

Key: `nicho_creativos:subidos:<source>:<carpeta>[:usuario]` → SET de números de
producto.
"""

from __future__ import annotations

from src.nicho_creativos.repos.redis_base import get_nicho_creativos_redis


def _key(source: str, folder: str, usuario: str = "") -> str:
    """Es POR USUARIO: cada uno publica en su cuenta. `ness` se queda en la
    clave sin usuario, que es donde está su histórico."""
    base = f"subidos:{source}:{folder}"
    if not usuario or usuario == "ness":
        return base
    return f"{base}:{usuario}"


def subidos(source: str, folder: str, usuario: str = "") -> set[str]:
    """Productos de esa carpeta ya publicados. Vacío si Redis no está: es un
    dato de progreso, no vale la pena tumbar la pantalla por él."""
    r = get_nicho_creativos_redis()
    if not r.is_available():
        return set()
    return {str(x) for x in r.smembers(_key(source, folder, usuario)) if x}


def marcar(
    source: str, folder: str, producto: str, subido: bool, usuario: str = "",
) -> None:
    r = get_nicho_creativos_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede guardar qué "
            "creativos has subido."
        )
    if subido:
        r.sadd(_key(source, folder, usuario), str(producto))
    else:
        r.srem(_key(source, folder, usuario), str(producto))
