"""Empareja las gorras DE DOS EN DOS POR ORDEN.

Aquí no sirve el emparejador de los otros nichos. Allí las dos fotos de un
producto comparten número (`2.PNG` y `2(1).PNG`); en las carpetas de gorras se
llaman `IMG_5033.PNG`, `IMG_5034.PNG`… y cada foto tiene el suyo, así que
agrupar por número daría 20 productos donde hay 10.

Lo que sí se cumple —comprobado sobre 40 parejas de cuatro carpetas, 40 de
40— es el ORDEN: van de dos en dos, primero la foto limpia y después la ficha.
Los números saltan (de `IMG_5051` a `IMG_5053`), pero dentro de cada pareja los
dos ficheros van seguidos.

Se verifica igualmente por la FORMA en vez de fiarse del orden a ciegas: la
ficha es un pantallazo de móvil (alto, ratio ~2,17) y la limpia ronda el
cuadrado. Si una pareja no encaja se marca `confident=False` y la pantalla lo
avisa, en vez de asignar al revés en silencio — que fue el fallo que ya costó
una extracción entera en el Nicho POV BOF.
"""

from __future__ import annotations

import re

# Por encima de esto la foto es la ficha (pantallazo de móvil).
TALL_MIN = 1.80


def _natural(nombre: str) -> tuple:
    return tuple(
        int(p) if p.isdigit() else p.lower()
        for p in re.split(r"(\d+)", nombre or "")
    )


def _ratio(foto: dict) -> float:
    w = int(foto.get("width") or 0)
    h = int(foto.get("height") or 0)
    return (h / w) if (w > 0 and h > 0) else 0.0


def pair_folder(fotos: list[dict]) -> list[dict]:
    """`[{producto, clean, titled, confident, reason}]`, en orden.

    El número de producto es la POSICIÓN (1, 2, 3…), no el del fichero: los
    nombres saltan y no significan nada aquí.
    """
    ordenadas = sorted(fotos, key=lambda f: _natural(f.get("name", "")))
    salida: list[dict] = []

    for i in range(0, len(ordenadas), 2):
        bloque = ordenadas[i:i + 2]
        pid = str(i // 2 + 1)
        if len(bloque) == 1:
            salida.append({
                "producto": pid, "clean": bloque[0], "titled": None,
                "confident": False, "reason": "queda una foto suelta",
            })
            continue

        a, b = bloque
        ra, rb = _ratio(a), _ratio(b)
        altas = [f for f, r in ((a, ra), (b, rb)) if r >= TALL_MIN]
        if len(altas) == 1:
            titled = altas[0]
            clean = b if titled is a else a
            salida.append({
                "producto": pid, "clean": clean, "titled": titled,
                "confident": True, "reason": "forma",
            })
        else:
            # Ni las dos altas ni las dos anchas: se respeta el orden (limpia
            # primero) pero se avisa, porque aquí es donde se cruzarían.
            salida.append({
                "producto": pid, "clean": a, "titled": b,
                "confident": False,
                "reason": "no se distingue la ficha por la forma",
            })
    return salida
