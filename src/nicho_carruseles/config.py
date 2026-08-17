"""Nicho Carruseles (Programa 4 — módulo 14 del curso).

No monta vídeo: publica un CARRUSEL de DOS fotos.

  - Foto 1 — una chica sorprendida, GENÉRICA: no tiene nada que ver con el
    producto. Se generan de golpe en Google Flow (de cuatro en cuatro) a partir
    de una foto de referencia y el prompt del curso, y se suben aquí en lote.
    Encima lleva quemado un mensaje corto que da curiosidad ("no me esperaba
    que fuera TAN bueno 😳"), tampoco atado al producto.
  - Foto 2 — el producto: ella sosteniéndolo, o el producto solo si es grande.
    Esta SÍ es de cada producto, se sube una a una y lleva quemado el mensaje
    del curso ("Han ajustado el precio de X…").

Como la foto 1 no depende del producto, el trabajo se reparte al revés que en
los demás nichos: primero una tanda enorme de chicas para toda la fuente y
después, producto a producto, solo la foto 2.

Del catálogo NO se toca nada: fuentes, carpetas, fotos, textos, hashtags,
escaparate y vendidos son los del Nicho POV BOF (ver `nicho_creativos`, que hace
lo mismo). Lo propio de aquí es:

  - qué productos VALEN para carrusel (belleza y suplementación; el resto no
    funciona en este formato) — `services/clasificador.py`,
  - los dos mensajes, escritos con los prompts del curso,
  - el banco de chicas y las fotos de producto, que viven en NUESTRO Drive,
  - quemar el texto sobre la foto (`services/texto_foto.py`),
  - y el progreso por carpeta, que es SUYO.
"""

from __future__ import annotations

import os
from pathlib import Path

REDIS_PREFIX = os.getenv("NICHO_CARRUSELES_REDIS_PREFIX", "nicho_carruseles:")

# Las MISMAS fuentes del Nicho POV BOF: mismo Drive, mismas carpetas, mismas
# fotos. Se importan para que añadir una fuente allí valga aquí sin tocar nada.
from src.nicho_pov_bof.config import (  # noqa: E402,F401
    SOURCES,
    es_fuente_propia,
    fuente_canonica,
    fuentes_a_barrer,
)

# Las fotos salen de Flow en vertical, como el vídeo. Se enseña al lado del
# prompt porque el generador no lo deduce del texto.
FORMATO = "9:16"

# ---------------------------------------------------------------------------
# Qué productos valen y DÓNDE está la chica
# ---------------------------------------------------------------------------
# El carrusel es una chica sorprendida hablando de "lo que le contaron". Eso
# cuela en cosmética y en suplementos… y también en un colchón o un sofá, con
# una condición: que la chica esté EN EL SITIO del producto. Una chica en la
# cocina anunciando un colchón no pega; la misma chica sentada en la cama, sí.
#
# Por eso la clasificación devuelve dos cosas: la categoría (qué es) y el
# ESCENARIO (dónde tiene que estar la chica de su foto 1). El escenario es lo
# que decide con qué prompt se genera en Flow, y el banco de chicas se lleva
# por escenario — no vale una del sofá para un producto de jardín.
#
# Lo clasifica Gemini leyendo los títulos YA extraídos (texto, sin imágenes: la
# llamada más barata que hay aquí).
CATEGORIAS = (
    "belleza", "suplementos", "descanso", "salon", "exterior",
    "cocina", "bano", "hogar", "coche", "tecnologia", "oficina", "fitness",
    "playa",
    "otro",
)

# Escenarios de la foto 1. La clave viaja por la API y da nombre al prompt
# (`prompts/foto_chica_<clave>.md`).
ESCENARIOS: dict[str, dict[str, str]] = {
    "generico": {
        "label": "En la calle, de noche",
        "para": "Belleza, suplementos, tecnología y fitness · chica de 19-23",
    },
    # Los productos de casa no los anuncia una de 20 en la calle: el tendedero
    # o el robot aspirador se los cree quien lleva una casa.
    "casa": {
        "label": "En casa",
        "para": "Limpieza, orden y decoración · mujer de 28-38",
    },
    "cama": {
        "label": "En la cama",
        "para": "Colchones, almohadas, ropa de cama · mujer de 25-35",
    },
    "sofa": {
        "label": "En el sofá",
        "para": "Sofás, mantas, cojines · mujer de 25-35",
    },
    "exterior": {
        "label": "Al aire libre",
        "para": "Camping, jardín, terraza · mujer de 28-38",
    },
    "cocina": {
        "label": "En la cocina",
        "para": "Freidoras, cafeteras, menaje · mujer de 28-38",
    },
    "bano": {
        "label": "En el baño",
        "para": "Toallas, ducha, espejos, organizadores de baño",
    },
    "coche": {
        "label": "En el coche",
        "para": "Organizadores, soportes, aspirador de coche",
    },
    "escritorio": {
        "label": "En el escritorio",
        "para": "Sillas de escritorio y gaming, lámparas, orden de oficina",
    },
    "playa": {
        "label": "En la playa o la piscina",
        "para": "Colchonetas, flotadores, paddle surf, toallas de playa",
    },
}

# Qué escenario le toca a cada categoría. Un producto es apto si su categoría
# tiene escenario; `otro` no lo tiene y por eso se queda fuera.
ESCENARIO_POR_CATEGORIA: dict[str, str] = {
    "belleza": "generico",
    "suplementos": "generico",
    "hogar": "casa",
    "descanso": "cama",
    "salon": "sofa",
    "exterior": "exterior",
    "cocina": "cocina",
    "bano": "bano",
    "coche": "coche",
    "oficina": "escritorio",
    # Estas dos van con la chica "en casa" y no piden prompt propio: lo que se
    # ve es ella, no el sitio (unos auriculares o una banda elástica se usan en
    # cualquier habitación).
    "tecnologia": "generico",
    "fitness": "generico",
    "playa": "playa",
}
CATEGORIAS_APTAS = tuple(ESCENARIO_POR_CATEGORIA)

# ---------------------------------------------------------------------------
# Dónde viven las fotos
# ---------------------------------------------------------------------------
# En NUESTRO Drive montado, no en el compartido del curso (que es solo lectura)
# y NUNCA en `api_uploads/` — eso se purga a las 24h y aquí una tanda de chicas
# tarda días en gastarse. Mismo criterio que Cuenta Piloto.
CARRUSELES_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_Carruseles"

# Subcarpetas por tipo de foto. Las `_txt` guardan la versión con el texto ya
# quemado: se conservan las dos para poder volver a quemar con otro mensaje sin
# haber perdido el original (quemar sobre lo quemado deja el texto doble).
SUBCARPETAS = {
    "chica": "chicas",
    "chica_txt": "chicas_con_texto",
    "producto": "productos",
    "producto_txt": "productos_con_texto",
}

# Las fotos de producto que sube en tanda y la IA no reconoce. NO se tiran: son
# generaciones de Flow que han costado su rato, así que se guardan aquí y la
# pantalla las enseña para asignarlas a mano.
SIN_ASIGNAR = "productos_sin_asignar"

# Cuántas chicas se piden de una tacada como máximo. No es un límite técnico:
# es el aviso de que una tanda mayor no cabe en una sesión de Flow.
CHICAS_POR_TANDA = 40

# ---------------------------------------------------------------------------
# Estilo del texto quemado
# ---------------------------------------------------------------------------
# Blanco, negrita, con borde negro y sombra: es lo que hace TikTok nativo y lo
# que llevan las cuentas de referencia del curso. Sin píldora — la caja negra
# canta a "editado fuera".
FUENTE_TEXTO = "Montserrat-ExtraBold.ttf"
# Proporción del ANCHO de la foto. Así el mismo estilo vale para una foto de
# Flow (1536 px) y para una captura de móvil, sin recalcular tamaños a mano.
TEXTO_TAM = 0.062
TEXTO_ANCHO_MAX = 0.86
# Altura donde se centra el bloque de texto (0 = arriba, 1 = abajo). En el
# tercio de arriba: probado sobre la foto de referencia, a 0.40 el texto caía
# encima de los ojos de la chica y ahí lo que tiene que verse es la cara.
TEXTO_Y = 0.28
TEXTO_BORDE = 0.11  # grosor del contorno, sobre el tamaño de letra


# Dónde se recrea el producto de la foto 2, según el escenario que le tocó. El
# prompt de la foto 2 NO necesita una composición de referencia: basta con la
# foto limpia del producto y decirle el sitio (mismo enfoque que el prompt de
# imagen del POV BOF).
LUGAR_POR_ESCENARIO: dict[str, str] = {
    "generico": "el sitio de la casa donde se use de verdad",
    "casa": "el sitio de la casa donde se use de verdad",
    "cama": "un dormitorio, sobre la cama o en la mesilla",
    "sofa": "un salón, sobre el sofá o la mesa de centro",
    "exterior": "un jardín o una terraza",
    "cocina": "la encimera de una cocina",
    "bano": "un cuarto de baño",
    "coche": "el interior de un coche",
    "escritorio": "un escritorio de casa",
    "playa": "la playa o el borde de una piscina",
}

# La mano en primera persona, como en el POV BOF. Hay dos, y cuál toca no lo
# decide el operador sino el PRODUCTO: lo que cabe en la mano se coge (una
# crema, un bote de vitaminas), y lo que no —un colchón, un sofá— se enseña en
# su sitio y como mucho se señala. Una mano "sujetando" un tendedero es la clase
# de imagen que delata que la foto es de IA.
LINEA_MANO_SUJETA = (
    "Aparece la mano de una persona, ultra realista, SUJETANDO el producto en "
    "modo POV, vista desde la altura de los ojos."
)
LINEA_MANO_SENALA = (
    "Aparece la mano de una persona, ultra realista, en modo POV SEÑALANDO el "
    "producto, vista desde la altura de los ojos."
)

# En qué escenarios el producto se coge con la mano. Son los de producto
# pequeño: belleza, suplementos, tecnología y fitness van todos al genérico.
ESCENARIOS_DE_MANO = frozenset({"generico", "bano", "coche"})
# "casa" queda fuera: lo que se anuncia ahí (mopas, tendederos, robots)
# no se sostiene con una mano.


def prompt_producto(escenario: str = "", con_mano: bool | None = None) -> str:
    """El prompt de la foto 2, con el sitio y la mano que le tocan.

    `con_mano=None` (lo normal) decide solo: se coge si el producto cabe en la
    mano. `True` fuerza la mano señalando —para cuando el producto es grande
    pero se quiere el punto de vista de alguien— y `False` la quita.
    """
    lugar = LUGAR_POR_ESCENARIO.get(escenario) or LUGAR_POR_ESCENARIO["generico"]
    texto = leer_prompt("foto_producto").replace("{lugar}", lugar)

    de_mano = (escenario or "generico") in ESCENARIOS_DE_MANO
    if con_mano is False:
        linea = ""
    elif con_mano is True and not de_mano:
        linea = LINEA_MANO_SENALA
    else:
        linea = LINEA_MANO_SUJETA if de_mano else ""

    if linea:
        # Detrás del primer párrafo, que es el que describe la escena.
        partes = texto.split("\n\n", 1)
        texto = f"{partes[0]} {linea}" + (f"\n\n{partes[1]}" if len(partes) > 1 else "")
    return texto


# El sitio de cada escenario, en INGLÉS: es lo que se mete en la ficha JSON de
# la chica (`services/chica_ficha.py`), que va en inglés como la del curso.
ESCENA_EN: dict[str, str] = {
    "generico": "on a city street at night, with city lights, cars and people blurred behind her",
    "casa": "at home, in the living room or hallway, with the real house behind her",
    "cama": "sitting on the bed of a real bedroom, with the headboard and pillows behind her",
    "sofa": "sitting on the sofa of a real living room, with cushions and a blanket",
    "exterior": "outdoors, in the garden or terrace of a house, in daylight",
    "cocina": "standing in the kitchen of a real home, next to the worktop",
    "bano": "in the bathroom of a real home, next to the sink and mirror",
    "coche": "sitting in the driver seat of a parked car at night, steering wheel and street lights visible through the window",
    "escritorio": "sitting at the desk of a home work corner",
    "playa": "at the beach or by a swimming pool, with the water behind her in daylight",
}


# La edad que le toca a la referencia de cada escenario. Misma tabla que la de
# los prompts de texto: a una de 20 anunciando un tendedero no se la cree nadie.
# OJO con estos números: el modelo SUMA cinco o siete años a lo que le pidas
# (probado hoy — pidiendo 28 salían de 35 y pidiendo 32, de 42). Así que aquí va
# la edad MENOS ese margen, no la que se quiere ver. El "looks young for her
# age" ayuda pero no basta.
EDAD_REFERENCIA: dict[str, str] = {
    "generico": "19 years old",
    "casa": "27 years old, looks young for her age",
    "cama": "24 years old, looks young for her age",
    "sofa": "24 years old, looks young for her age",
    "exterior": "27 years old, looks young for her age",
    "cocina": "27 years old, looks young for her age",
    "bano": "19 years old",
    "coche": "19 years old",
    "escritorio": "21 years old",
    "playa": "19 years old",
}


# Qué chica buscar para cada escenario. Solo la PERSONA: la referencia se hace
# con fondo neutro y el sitio lo pone el prompt de la tanda. Si la referencia
# trae escenario, el modelo lo arrastra a todas las fotos (pasó con la cocina de
# la foto del curso).
#
# Mejor una chica GENERADA que la foto de una persona real: la referencia se
# reutiliza en cientos de carruseles comerciales, y la cara de alguien de
# internet no es tuya para eso.
BUSQUEDA_CHICA: dict[str, str] = {
    "generico": "chica española de 20 años, guapa, pelo castaño claro o rubio oscuro",
    "casa": "mujer española de 32 años, guapa y natural",
    "cama": "chica española de 28 años, guapa",
    "sofa": "chica española de 28 años, guapa",
    "exterior": "mujer española de 32 años, guapa y natural",
    "cocina": "mujer española de 32 años, guapa y natural",
    "bano": "chica española de 21 años, guapa",
    "coche": "chica española de 21 años, guapa",
    "escritorio": "chica española de 23 años, guapa",
    "playa": "chica española de 20 años, guapa, con algo de moreno",
}


# Cómo es la chica de cada escenario. Sin esto los diez salían clavados —misma
# melena castaña, misma cara— porque la plantilla es una sola y el modelo tira
# siempre a su "española por defecto". Con rasgos distintos, la cuenta no parece
# la misma persona disfrazada en diez sitios.
#
# Solo se cambian los campos de aspecto: expresión, encuadre y estilo de foto
# son los mismos en todos, que es lo que da coherencia al carrusel.
RASGOS_POR_ESCENARIO: dict[str, dict[str, str]] = {
    "generico": {
        "face": "oval face, light freckles across the nose, green eyes, full lips, "
                "youthful face with smooth skin, very pretty",
        "hair_color": "dark blonde",
        "hair_style": "very long and straight, middle parting, no frizz",
    },
    "casa": {
        "face": "round friendly face, dark brown eyes, warm natural look, youthful "
                "face with smooth skin, pretty",
        "hair_color": "dark brown, almost black",
        "hair_style": "shoulder length, tied back in a low ponytail with a few loose "
                      "strands, no frizz",
    },
    "cama": {
        "face": "heart-shaped face, hazel eyes, freckles, youthful face with smooth "
                "skin, very pretty",
        "hair_color": "auburn (reddish brown)",
        "hair_style": "wavy, shoulder length, middle parting, no frizz",
    },
    "sofa": {
        "face": "soft oval face, blue eyes, full lips, youthful face with smooth "
                "skin, very pretty",
        "hair_color": "light blonde",
        "hair_style": "straight, just below the shoulders, side parting, no frizz",
    },
    "exterior": {
        "face": "long face, dark brown eyes, defined cheekbones, sun-kissed look, "
                "youthful face with smooth skin, pretty",
        "hair_color": "very dark brown",
        "hair_style": "very long and straight, middle parting, no frizz",
    },
    "cocina": {
        "face": "round face, light brown eyes, warm smile lines only when smiling, "
                "youthful face with smooth skin, pretty",
        "hair_color": "chestnut brown",
        "hair_style": "medium length with a straight fringe, no frizz",
    },
    "bano": {
        "face": "oval face, very dark eyes, thick eyebrows, porcelain skin, youthful "
                "face with smooth skin, very pretty",
        "hair_color": "black",
        "hair_style": "very long and sleek, middle parting, no frizz",
    },
    "coche": {
        "face": "small round face, light grey-blue eyes, small nose, youthful face "
                "with smooth skin, very pretty",
        "hair_color": "golden blonde",
        "hair_style": "long with loose waves, messy bun on top sometimes, no frizz",
    },
    "escritorio": {
        "face": "oval face with light freckles, brown eyes, wears thin-framed "
                "glasses, youthful face with smooth skin, pretty",
        "hair_color": "light brown",
        "hair_style": "long, tied in a high ponytail, no frizz",
    },
    "playa": {
        "face": "oval face, green-blue eyes, freckles, tanned skin, youthful face "
                "with smooth skin, very pretty",
        "hair_color": "sun-bleached blonde",
        "hair_style": "long, beach waves, slightly wind-blown, no frizz",
    },
}


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def leer_prompt(nombre: str) -> str:
    return (prompts_dir() / f"{nombre}.md").read_text(encoding="utf-8").strip()


# Ruta ya resuelta y creada. Se recuerda por lo mismo que en el POV BOF: el
# `mkdir` va contra el Drive MONTADO y en frío cuesta decenas de segundos,
# porque rclone tiene que resolver los cuatro niveles contra Google.
_RAIZ: Path | None = None


def carruseles_dir() -> Path:
    """Raíz del nicho en el Drive MONTADO (no el compartido del curso)."""
    global _RAIZ
    if _RAIZ is not None:
        return _RAIZ

    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    destino = (
        raiz / CARRUSELES_ROOT if raiz
        else Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "nicho_carruseles"
    )
    destino.mkdir(parents=True, exist_ok=True)
    _RAIZ = destino
    return destino


def carpeta_sin_asignar(usuario: str = "") -> Path:
    destino = carruseles_dir() / (usuario or "ness") / SIN_ASIGNAR
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def carpeta_de(tipo: str, usuario: str = "") -> Path:
    """Carpeta de un tipo de foto para ese usuario.

    Es POR USUARIO porque la cuenta de TikTok lo es: la chica que sale en los
    carruseles de Ana no puede salir en los de Mauro el mismo día.
    """
    sub = SUBCARPETAS.get(tipo)
    if not sub:
        raise ValueError(f"tipo de foto desconocido: {tipo}")
    destino = carruseles_dir() / (usuario or "ness") / sub
    destino.mkdir(parents=True, exist_ok=True)
    return destino
