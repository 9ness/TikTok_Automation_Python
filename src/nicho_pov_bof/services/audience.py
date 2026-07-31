"""A quién le habla el producto → qué voz locuta el vídeo.

El operador elegía siempre "hombre" a mano y luego lo corregía en los de
belleza. Esto es solo un DEFECTO razonable: la UI deja cambiarlo con un clic,
así que un fallo no cuesta nada y acertar la mayoría de veces ahorra trabajo.

Por qué por palabras clave y no con IA: el título ya está guardado, la
decisión es binaria y cada llamada a un modelo cuesta dinero y segundos.
"""

from __future__ import annotations

import re
import unicodedata

# Producto claramente dirigido a mujer. Ordenado por familias para poder
# ampliarlo sin duplicar.
_PALABRAS_MUJER = (
    # lo dice el propio título
    "mujer", "femenin", "para ella",
    # cosmética y cuidado facial
    "crema", "serum", "cosmetic", "maquillaje", "belleza", "facial",
    "hidratante", "antiarrugas", "antimanchas", "mascarilla", "exfoliante",
    "tonico", "limpiador facial", "contorno de ojos", "acido hialuronico",
    "retinol", "colageno", "bronceador", "autobronceador",
    # maquillaje concreto
    "labial", "pintalabios", "rimel", "mascara de pestanas", "pestanas",
    "eyeliner", "delineador", "corrector", "base de maquillaje", "colorete",
    "sombra de ojos", "brocha", "esmalte", "manicura", "unas postizas",
    # pelo — incluidos los tratamientos, que es la mitad del catálogo
    "plancha de pelo", "rizador", "moldeador", "secador", "champu",
    "acondicionador", "mascarilla capilar", "extensiones",
    "capilar", "keratina", "queratina", "alisado", "botox capilar",
    "cabello", "para el pelo", "protector termico",
    # depilación y cuerpo
    "depilad", "depilacion", "cera", "celulitis", "reafirmante",
    "anticeluliti", "moldeador corporal", "faja",
    "estrias", "aceite corporal", "crema corporal", "antiedad",
    "anti-edad", "despigment", "iluminador", "cicatrices",
    # ropa y complementos
    "vestido", "falda", "blusa", "sujetador", "lenceria", "bikini",
    "bolso", "monedero", "pendientes", "collar", "pulsera", "anillo",
    "diadema", "tacon", "sandalias de tacon",
    # otros
    "perfume femenino", "menstrual", "copa menstrual", "compresas",
    "embarazo", "lactancia", "bebe",
)

# Contraejemplos: llevan una palabra de la lista pero NO son de mujer. Se
# comprueban ANTES, porque si no "crema de manos para trabajadores" o
# "mascarilla de soldadura" caerían del lado equivocado.
_EXCEPCIONES = (
    "cepillo para perro", "cepillo para gato", "quitapelos",
    "cortapelo para mascota",
    "mascarilla de soldadura", "mascarilla facial de buceo",
    "crema para calzado", "crema de zapatos", "cera para coche",
    "cera para muebles", "collar para perro", "collar antipulgas",
    "collar para gato", "pulsera antimosquitos",
)


def _plano(txt: str) -> str:
    """Minúsculas y sin acentos, para comparar sin sorpresas."""
    sin = unicodedata.normalize("NFKD", txt or "")
    sin = "".join(c for c in sin if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin.lower())


def sexo_sugerido(*textos: str) -> str:
    """"mujer" si el producto apunta claramente a mujer, si no "hombre".

    El defecto es "hombre" a propósito: es lo que encaja con la mayoría del
    catálogo (hogar, tecnología, herramientas, mascotas…).
    """
    texto = _plano(" ".join(t for t in textos if t))
    if not texto:
        return "hombre"
    for exc in _EXCEPCIONES:
        if exc in texto:
            return "hombre"
    for palabra in _PALABRAS_MUJER:
        if palabra in texto:
            return "mujer"
    return "hombre"
