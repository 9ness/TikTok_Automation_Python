"""Emojis que acompañan al caption: una reacción + uno del producto.

Lo normal es que los devuelva Gemini en la extracción de textos — entiende
"silla de camping" mucho mejor que ninguna lista de palabras. Esto es el
RESPALDO: para los productos extraídos antes de que existiera el campo, y por
si el modelo se lo deja.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Reacciones genéricas. Se rota por producto para que diez captions seguidos
# no empiecen igual.
_REACCIONES = ("😍", "🤯", "😱", "👀", "🔥", "👏", "🙌", "✨")

# (emoji, palabras que lo disparan). El orden importa: gana la primera que
# case, así que lo específico va antes que lo general.
_FAMILIAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("🏕️", ("camping", "acampada", "playa", "picnic", "pícnic", "exterior")),
    ("🎒", ("mochila", "bolso", "maleta", "equipaje", "bandolera")),
    ("🧴", ("crema", "serum", "sérum", "locion", "loción", "aceite", "gel",
            "champu", "champú", "mascarilla", "protector solar", "esencia")),
    ("🌸", ("perfume", "colonia", "fragancia", "eau de")),
    ("🛒", ("carrito de compra", "carro de la compra")),
    ("💄", ("maquillaje", "labial", "pintalabios", "rimel", "esmalte")),
    ("💇", ("pelo", "cabello", "capilar", "keratina", "plancha", "secador")),
    ("🍽️", ("escurreplatos", "vajilla", "platos", "cocina", "cubiertos",
             "sarten", "sartén", "olla", "tupper")),
    ("☕", ("cafe", "café", "cafetera", "taza", "termo")),
    ("🪑", ("silla", "sillon", "sillón", "sofa", "sofá", "taburete", "asiento")),
    ("🛏️", ("colchon", "colchón", "almohada", "sabana", "sábana", "edredon")),
    ("🧹", ("aspirador", "limpieza", "fregona", "escoba", "mopa")),
    ("💡", ("lampara", "lámpara", "luz", "led", "bombilla", "foco")),
    ("🐶", ("perro", "gato", "mascota", "transportin", "transportín")),
    ("👶", ("bebe", "bebé", "cochecito", "cuna", "pañal", "cabestrillo")),
    ("🎮", ("gaming", "gamer", "consola", "mando", "videojuego")),
    ("💻", ("portatil", "portátil", "ordenador", "laptop", "teclado", "raton")),
    ("📱", ("movil", "móvil", "telefono", "teléfono", "funda", "cargador")),
    ("⌚", ("reloj", "smartwatch", "pulsera de actividad")),
    ("🎧", ("auricular", "cascos", "altavoz", "sonido")),
    ("🏋️", ("gimnasio", "fitness", "mancuerna", "deporte", "yoga", "futbol",
             "fútbol", "baloncesto")),
    ("🚗", ("coche", "auto", "vehiculo", "vehículo", "moto")),
    ("🔧", ("herramienta", "taladro", "destornillador", "bricolaje")),
    ("🪞", ("espejo", "tocador")),
    ("🌱", ("planta", "jardin", "jardín", "maceta", "riego")),
)

# Cuando nada casa: algo neutro de "producto" antes que un emoji que engañe.
_GENERICO = "🛍️"


def _plano(txt: str) -> str:
    sin = unicodedata.normalize("NFKD", txt or "")
    sin = "".join(c for c in sin if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin.lower())


def emoji_producto(*textos: str) -> str:
    """El emoji que pega con el producto, o uno neutro."""
    texto = _plano(" ".join(t for t in textos if t))
    for emoji, palabras in _FAMILIAS:
        for p in palabras:
            if _plano(p) in texto:
                return emoji
    return _GENERICO


def emojis_para(producto_id: str, *textos: str) -> str:
    """Los dos emojis del caption: reacción + producto.

    La reacción se sortea por producto (determinista) para que no salgan diez
    captions seguidos empezando por el mismo.
    """
    h = hashlib.sha1(str(producto_id).encode("utf-8")).digest()
    return _REACCIONES[h[0] % len(_REACCIONES)] + emoji_producto(*textos)
