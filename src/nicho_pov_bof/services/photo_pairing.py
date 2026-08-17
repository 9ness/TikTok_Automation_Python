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
# Por encima de este alto/ancho la foto es una captura de la ficha (pantallazo
# de móvil), no la foto del producto: 1320x2868 son 2,17.
TALL_MIN = 1.80
# Cuánto más debe pesar la captura para decidir por peso cuando la forma no
# separa.
SIZE_RATIO_CONFIDENT = 1.25

# Fotos con el nombre que les pone el móvil (`IMG_0245.jpg`). Ahí no hay número
# de producto que agrupe: cada fichero se tomaba como un producto suyo, así que
# la carpeta salía con el doble de productos y la mitad eran la CAPTURA de la
# ficha haciéndose pasar por foto de producto.
CAMARA_RE = re.compile(r"^(?:img|image|photo|foto|pxl|dsc)[ _-]?(\d+)$")
# Las dos fotos de un producto se hacen seguidas, así que sus números van
# pegados (0245/0246, y como mucho 0309/0311 si el operador borró alguna). De
# un producto al siguiente el salto es de decenas.
CAMARA_SALTO_MAX = 5


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
    """Agrupa las fotos de una carpeta por producto.

    Un mismo NÚMERO puede corresponder a DOS productos distintos: el operador
    guarda las capturas y a veces repite número entre tandas, así que en una
    carpeta conviven `2` y `2.PNG` que no son la misma ficha (distinto
    tamaño, distinto producto). Fundirlos escondía 15 productos en 10
    carpetas — carpetas de 20 fotos que salían con 8 productos.

    Se separan solo cuando el reparto es LIMPIO: si los ficheros de un número
    se agrupan por nombre exacto en bloques de exactamente dos (ficha +
    limpia), cada bloque es un producto. Si no cuadra, se deja como estaba —
    `4(1).PNG` y `4.PNG` SÍ son el mismo producto (el "(1)" lo pone Drive al
    repetirse el nombre), y ahí no hay nada que separar.
    """
    por_numero: dict[str, list[dict]] = {}
    for p in photos:
        por_numero.setdefault(_stem_key(p["name"]), []).append(p)

    _juntar_de_camara(por_numero)

    groups: dict[str, list[dict]] = {}
    for numero, fotos in por_numero.items():
        bloques: dict[str, list[dict]] = {}
        for p in fotos:
            bloques.setdefault(p["name"], []).append(p)

        if len(bloques) < 2 or any(len(v) != 2 for v in bloques.values()):
            por_fecha = _bloques_por_fecha(fotos)
            if por_fecha:
                bloques = {str(i): b for i, b in enumerate(por_fecha)}
            else:
                groups[numero] = fotos
                continue

        # Los que YA se veían (con extensión) conservan el número pelado: su
        # progreso está guardado en Redis con esa clave y moverlo apuntaría
        # los textos ya extraídos a las fotos del otro producto.
        orden = sorted(
            bloques.items(),
            key=lambda kv: (0 if _tiene_extension(kv[0]) else 1, kv[0]),
        )
        for i, (_nombre, bloque) in enumerate(orden):
            sufijo = "" if i == 0 else chr(ord("a") + i)  # 2, 2b, 2c…
            groups[f"{numero}{sufijo}"] = bloque
    return groups


def _juntar_de_camara(por_numero: dict[str, list[dict]]) -> None:
    """Junta las fotos con nombre de móvil que van de dos en dos.

    En algunas carpetas el curso no renumera y sube los ficheros tal cual salen
    del carrete: `IMG_0245.jpg` (el producto) e `IMG_0246.PNG` (la captura de
    la ficha). Como el nombre no empieza por número, cada uno se tomaba como un
    producto distinto: la carpeta salía con el doble de productos y en la mitad
    la "foto limpia" era en realidad el pantallazo con el precio encima.

    Se agrupan por CERCANÍA de número, que es lo que las relaciona: las dos se
    hacen seguidas y entre un producto y el siguiente pasan decenas de fotos.
    Solo se juntan si la pareja queda exacta —dos ficheros, uno de cada— porque
    juntar de más cruzaría dos productos, que es peor que dejarlos sueltos.

    Modifica el dict en sitio. La clave del par es la del PRIMERO: es la que ya
    tiene el progreso guardado en Redis.
    """
    sueltas = sorted(
        (int(m.group(1)), clave)
        for clave, fotos in por_numero.items()
        if len(fotos) == 1 and (m := CAMARA_RE.match(clave))
    )
    if len(sueltas) < 2:
        return

    grupo: list[tuple[int, str]] = []
    for actual in sueltas + [(10**9, "")]:
        if grupo and actual[0] - grupo[-1][0] > CAMARA_SALTO_MAX:
            if len(grupo) == 2:
                primera, segunda = grupo[0][1], grupo[1][1]
                por_numero[primera] = por_numero[primera] + por_numero.pop(segunda)
            grupo = []
        if actual[1]:
            grupo.append(actual)


def _bloques_por_fecha(fotos: list[dict]) -> list[list[dict]] | None:
    """Parte un número en productos usando CUÁNDO se subió cada foto.

    Última vía, para cuando los ficheros se llaman exactamente igual y el
    nombre no separa nada (una carpeta tenía cuatro `8.PNG`). Las dos fotos de
    un producto se suben seguidas —segundos— y entre un producto y otro pasan
    días, así que ordenando por fecha salen parejas evidentes.

    Solo se acepta si CADA pareja queda con una ficha (alta) y una foto de
    producto (no alta). Si no cuadra, se devuelve None y el número se deja
    entero: es preferible un producto de más con fotos de sobra que dos
    productos con las fotos cruzadas.
    """
    if len(fotos) < 4 or len(fotos) % 2 or not all(f.get("mtime") for f in fotos):
        return None

    ordenadas = sorted(fotos, key=lambda f: str(f.get("mtime")))
    parejas = [ordenadas[i:i + 2] for i in range(0, len(ordenadas), 2)]
    for pareja in parejas:
        altas = [f for f in pareja if (_ratio(f) or 0) >= TALL_MIN]
        if len(altas) != 1:
            return None
    return parejas


def _tiene_extension(name: str) -> bool:
    from src.nicho_pov_bof import config

    return "." in name and config.is_image(name)


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

    # 1b) Varias cuadradas y una sola captura: gana la que comparte ANCHO con
    # la captura. Las dos salen del mismo pantallazo del móvil, así que miden
    # lo mismo de ancho; una foto de otro producto traspapelada en la carpeta
    # (pasa: el `2.png` de un producto que era de otro) no coincide.
    # Sin esto se decidía por peso y se colaba la foto ajena.
    if len(squarish) > 1 and len(odd) == 1:
        titled = odd[0]
        w_titled = int(titled.get("width") or 0)
        iguales = [p for p in squarish if int(p.get("width") or 0) == w_titled]
        if len(iguales) == 1:
            clean = iguales[0]
            extras = [p for p in items if p not in (clean, titled)]
            return {"clean": clean, "titled": titled, "confident": True,
                    "reason": "mismo ancho que la captura", "extras": extras}

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
    # Orden: por número y, dentro, por sufijo — el 2b va pegado al 2, no
    # detrás del 10.
    def _orden(p: dict) -> tuple:
        m = re.match(r"^(\d+)([a-z]*)$", p["producto"])
        if not m:
            return (10**6, p["producto"])
        return (int(m.group(1)), m.group(2))

    out.sort(key=_orden)
    return out


def needs_review(pairs: Iterable[dict]) -> list[dict]:
    """Pares cuyo reparto limpia/captura no está claro (irían a Gemini)."""
    return [p for p in pairs if not p.get("confident")]


# ---------------------------------------------------------------------------
# Desempate por CONTENIDO, cuando la forma y el peso no bastan
# ---------------------------------------------------------------------------
# Pasó con una prenda cuyas dos fotos medían exactamente lo mismo (1320x2868):
# una era la ficha entera (título, precio, "Vendido por…") y la otra el visor
# del carrusel con la prenda sobre bandas negras. Al no poder distinguirlas se
# asignaron AL REVÉS, así que la extracción leyó la foto sin texto y dijo que
# la tienda no se veía — cuando sí estaba, en la otra.
#
# La señal que las separa a simple vista es el fondo: el visor del carrusel
# tiene bandas NEGRAS arriba y abajo; la ficha tiene un panel BLANCO de
# información debajo. Se mira una franja de píxeles, no hace falta OCR.
_NEGRO_MAX = 40      # por debajo de esto, píxel "negro"
_BLANCO_MIN = 210    # por encima de esto, píxel "blanco"


def _perfil_bandas(path: str) -> tuple[float, float]:
    """(fracción de filas casi negras, fracción de filas casi blancas)."""
    from PIL import Image

    with Image.open(path) as im:
        gris = im.convert("L").resize((32, 96))
        filas = [
            sum(gris.getpixel((x, y)) for x in range(32)) / 32
            for y in range(96)
        ]
    negras = sum(1 for v in filas if v <= _NEGRO_MAX) / len(filas)
    blancas = sum(1 for v in filas if v >= _BLANCO_MIN) / len(filas)
    return negras, blancas


def desempatar_por_contenido(pair: dict, fetch) -> dict:
    """Reordena limpia/captura mirando las imágenes. Solo si hacía falta.

    `fetch(file_id, suffix=...)` devuelve la ruta local (ya cacheada). Si algo
    falla se devuelve el par tal cual: es un afinado, no un requisito.
    """
    if pair.get("confident"):
        return pair
    clean, titled = pair.get("clean"), pair.get("titled")
    if not clean or not titled:
        return pair
    try:
        from pathlib import Path

        perfiles = {}
        for etiqueta, foto in (("clean", clean), ("titled", titled)):
            ruta = fetch(foto["id"], suffix=Path(foto.get("name", "")).suffix or ".jpg")
            perfiles[etiqueta] = _perfil_bandas(str(ruta))
    except Exception:
        return pair

    # La ficha es la que tiene MÁS blanco (el panel de información) y menos
    # banda negra. Si la que está puesta como "limpia" es más ficha que la
    # otra, se intercambian.
    def puntua(p: tuple[float, float]) -> float:
        negras, blancas = p
        return blancas - negras

    if puntua(perfiles["clean"]) > puntua(perfiles["titled"]):
        return {
            **pair,
            "clean": titled,
            "titled": clean,
            "reason": (pair.get("reason") or "") + " · desempatado por contenido",
        }
    return pair
