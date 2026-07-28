"""Empareja las DOS fotos que tiene cada producto.

Dentro de una carpeta de producto hay ficheros con el MISMO nombre (`2.PNG`
dos veces). No son duplicados: uno es el producto limpio y otro es una captura
del mismo producto con su título y metadatos encima.

    foto limpia    -> se descarga y se manda a Veo3/Kling
    captura título -> de ahí se sacan título, tienda y caption

Cómo se distingue (comprobado sobre el Drive real):

1. **Forma.** La foto de producto es prácticamente CUADRADA (ratio 0.79-1.06).
   La captura se aleja mucho de cuadrada: o es un pantallazo de móvil (alto,
   ratio ~2.17) o uno de escritorio (ancho, ratio ~0.22).
2. **Peso.** Si las dos son parecidas de forma, la captura pesa bastante más
   porque lleva texto y UI encima.
3. Si ninguna de las dos separa, se mira la imagen con Gemini.

El peso SOLO no vale: hay pares con 160KB vs 162KB donde la ancha es la
captura, y fiarse del tamaño los invertía.
"""

from __future__ import annotations

import re
from typing import Iterable

# Fuera de esta banda de ratio (alto/ancho) una imagen ya no es "de producto":
# es un pantallazo alto de móvil o una tira ancha de escritorio.
SQUARE_MIN, SQUARE_MAX = 0.60, 1.50
# Cuánto más debe pesar la captura para decidir por peso cuando la forma no
# separa.
SIZE_RATIO_CONFIDENT = 1.25


def _stem_key(name: str) -> str:
    """Clave de emparejado: el número del fichero, ignorando extensión y caja.

    `1.PNG`, `1.png` y `1.jpeg` son el mismo producto; `1-1.PNG` también.
    """
    stem = name.rsplit(".", 1)[0].strip().lower()
    m = re.match(r"^(\d+)", stem)
    return m.group(1) if m else stem


def _ratio(photo: dict) -> float | None:
    """Alto/ancho si se conocen las dimensiones."""
    w = int(photo.get("width") or 0)
    h = int(photo.get("height") or 0)
    if w <= 0 or h <= 0:
        return None
    return h / w


def _is_squarish(photo: dict) -> bool | None:
    r = _ratio(photo)
    if r is None:
        return None
    return SQUARE_MIN <= r <= SQUARE_MAX


def group_by_product(photos: Iterable[dict]) -> dict[str, list[dict]]:
    """Agrupa las fotos de una carpeta por producto."""
    groups: dict[str, list[dict]] = {}
    for p in photos:
        groups.setdefault(_stem_key(p["name"]), []).append(p)
    return groups


def split_pair(group: list[dict]) -> dict:
    """Decide cuál es la limpia y cuál la captura dentro de un grupo.

    Las fotos pueden traer `width`/`height` (mejor señal). Sin ellas se cae a
    decidir por peso, que es menos fiable.

    Devuelve {"clean", "titled", "confident", "reason", "extras"}.
    """
    items = list(group)
    if not items:
        return {"clean": None, "titled": None, "confident": False,
                "reason": "vacío", "extras": []}
    if len(items) == 1:
        # Sin captura no se podrán extraer título ni tienda de ese producto.
        return {"clean": items[0], "titled": None, "confident": False,
                "reason": "solo hay una foto", "extras": []}

    # 1) Por forma: la cuadrada es el producto.
    squarish = [p for p in items if _is_squarish(p) is True]
    odd = [p for p in items if _is_squarish(p) is False]
    if len(squarish) == 1 and odd:
        # La captura más "rara" de forma es la que lleva el título.
        titled = max(odd, key=lambda p: abs((_ratio(p) or 1.0) - 1.0))
        extras = [p for p in items if p not in (squarish[0], titled)]
        return {"clean": squarish[0], "titled": titled, "confident": True,
                "reason": "forma", "extras": extras}

    # 2) Por peso: la captura lleva texto y UI, pesa más.
    by_size = sorted(items, key=lambda p: int(p.get("size") or 0))
    clean, titled = by_size[0], by_size[-1]
    small = int(clean.get("size") or 0)
    big = int(titled.get("size") or 0)
    if small > 0 and big >= small * SIZE_RATIO_CONFIDENT:
        return {"clean": clean, "titled": titled, "confident": True,
                "reason": "peso", "extras": by_size[1:-1]}

    # 3) Ni forma ni peso separan → hay que mirarlo.
    return {"clean": clean, "titled": titled, "confident": False,
            "reason": "indistinguible por forma y peso", "extras": by_size[1:-1]}


def pair_folder(photos: Iterable[dict]) -> list[dict]:
    """Pares de una carpeta, ordenados por número de producto."""
    out: list[dict] = []
    for key, group in group_by_product(photos).items():
        pair = split_pair(group)
        pair["producto"] = key
        out.append(pair)
    out.sort(key=lambda p: (len(p["producto"]), p["producto"]))
    return out


def needs_review(pairs: Iterable[dict]) -> list[dict]:
    """Pares cuyo reparto limpia/captura no está claro (irían a Gemini)."""
    return [p for p in pairs if not p.get("confident")]
