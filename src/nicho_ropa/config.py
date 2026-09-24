"""Nicho Ropa Sin Personas (Programa 4 — módulo 8 del curso).

Qué lo diferencia del Nicho POV BOF, que es el que más se le parece:

- El Drive de fotos se comparte **por enlace**, no aparece en "Compartido
  conmigo". Se lee con `--drive-root-folder-id`, que convierte esa carpeta en
  la raíz del remote.
- Es UNA sola carpeta con todos los productos dentro, no una fuente con
  carpetas de producto. De momento solo hay camisetas.
- El vídeo final **no lleva texto quemado** — ni gancho, ni título, ni CTA, ni
  flecha. El producto se enseña y ya. Y va **mudo por defecto**: el operador
  le pone la música al publicar.

Lo que SÍ se reutiliza del Nicho POV BOF, porque es idéntico y funciona:
`photo_pairing` (emparejar foto limpia + captura con título, incluidos los
nombres duplicados) y la descarga de fotos por file ID.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Drive de origen (SOLO LECTURA)
# ---------------------------------------------------------------------------
DRIVE_REMOTE = "gdrive:"

# Carpetas de producto, dentro del Drive compartido "Productos España". Con
# `--drive-root-folder-id` rclone trata la carpeta como la raíz del remote, así
# que los paths van vacíos ("gdrive:").
#
# Una MISMA prenda vale para los dos nichos de ropa: en percha (sin nadie) o
# puesta por una modelo. Lo que cambia es el prompt, no la foto — por eso estas
# carpetas no son exclusivas de este módulo aunque el curso las separe.
CARPETAS: dict[str, dict[str, str]] = {
    "camisetas": {
        "label": "Camisetas / Conjuntos",
        "id": "10jSRauIlUVFXo3Dr6RCi8iO1gIY2TDIL",
    },
    "mono": {
        "label": "Mono (mujer)",
        "id": "1MXBSXZRwqbo1F25OAM-MhO-qTf4SmxyK",
    },
    "pantalon_corto": {
        "label": "Pantalón corto (mujer)",
        "id": "11enOhq4DL_lmdttQWqgowmA1MRqrR3_0",
    },
    "bikinis": {
        "label": "Bikinis",
        "id": "1T-nqij3xl4Dp-h2JvGJofCq6Wzoia25a",
    },
}

CARPETA_DEFECTO = "camisetas"

# ---------------------------------------------------------------------------
# Las prendas de la web del curso, importadas por ZIP
# ---------------------------------------------------------------------------
# Las cuatro de arriba son carpetas del Drive del curso, planas: una sola
# carpeta con todas las prendas dentro. Lo de la web NO es así — son 31
# carpetas de diez, mujer y hombre por separado—, así que necesitaba un nivel
# más.
#
# En vez de meterle un nivel al nicho entero, cada carpeta importada ES una
# carpeta más del selector, con su slug: `mujer_web__Carpeta 23`. Con eso todo
# lo que ya existe —fotos, textos, estado, vídeo— funciona sin tocarse, porque
# para el resto del código sigue siendo "una carpeta".
GENEROS_WEB: dict[str, str] = {
    "mujer_web": "👗 Mujer web",
    "hombre_web": "👔 Hombre web",
}
SEPARADOR_WEB = "__"
PRENDAS_WEB_ROOT = (
    "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_Ropa_Sin_Personas/prendas_web"
)

# Los catálogos del OPERADOR, igual que en el POV BOF: una prenda se graba
# porque la tienda mandó MUESTRA o porque es una TAREA pagada, y no se
# trabajan igual. Aquí hay cuatro y no dos porque el género manda: lo que
# subas en mujer no tiene nada que ver con hombre, ni en prenda ni en modelo.
#
# Se comportan como un género más de los de la web (`mujer_web__Carpeta 23`),
# así que reusan TODO lo que ya existe —slug, fotos, textos, estado, vídeo— y
# solo cambian de carpeta raíz en Drive.
GENEROS_OPERADOR: dict[str, str] = {
    "mujer_muestras": "👗 Mujer · muestras",
    "mujer_tareas": "👗 Mujer · tareas",
    "hombre_muestras": "👔 Hombre · muestras",
    "hombre_tareas": "👔 Hombre · tareas",
}
MIS_PRENDAS_ROOT = (
    "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_Ropa_Sin_Personas/mis_prendas"
)
# Cuántas prendas entran en cada carpeta. Diez, como en todo lo demás.
MIS_PRENDAS_POR_CARPETA = 10


def es_genero_operador(genero: str) -> bool:
    return genero in GENEROS_OPERADOR


# Los MODOS de grabación. Cada uno es un vídeo distinto de la MISMA prenda —
# cambia dónde está la cámara—, así que cada uno guarda su vídeo por separado:
# igual que los estilos de guion del POV BOF Largo (precio / punto de dolor).
#
# Lo que NO se separa son los textos ni el escaparate: son de la prenda, no de
# cómo se grabe. Por eso el modo no entra en la clave del documento (eso
# duplicaría los textos), sino que cuelga de cada producto.
# Cada modo dice además CON QUÉ estilo se graba, para que la pantalla enseñe
# solo su prompt: estando en "frente al espejo" no pinta nada el de dejar el
# móvil apoyado. `estilo_mof10` es la clave de `ESTILOS_MOF10`.
#
# `sexos` dice a quién se le enseña: son los FORMATOS que publica el curso y no
# publica los mismos para los dos. El de bolso es de mujer y las dos
# situaciones de calle son de hombre; enseñarlos en el otro sexo sería ofrecer
# un modo sin prompt.
#
# La clave `camara` se queda como está aunque su nombre sea ahora "BOF Selfie":
# es la que lleva dentro cada producto (`modos.camara`) y renombrarla perdería
# los vídeos ya grabados.
MODOS: dict[str, dict] = {
    "espejo": {
        "desc": "La prenda puesta, grabándose frente a un espejo de cuerpo entero en casa. El de siempre, y de los pocos con versión de pago a plazos.",
        "label": "🪞 BOF Frente a Espejo",
        "estilo_mof10": "espejo",
        "sexos": ("mujer", "hombre"),
    },
    "camara": {
        "desc": "Selfie con el móvil en la mano, hablando a cámara con la prenda puesta.",
        "label": "🤳 BOF Selfie",
        "estilo_mof10": "movil",
        # Desde sep 2026 lo publica también para mujer, con su propio texto.
        "sexos": ("mujer", "hombre"),
    },
    "calle_1": {
        "desc": "En la calle: alguien le para y le piropea el outfit. El diálogo viene cerrado del curso.",
        "label": "🚶 Situación Real 1",
        "estilo_mof10": "real_1",
        # Desde sep 2026 también está en Moda Chica, con su propia imagen.
        "sexos": ("mujer", "hombre"),
    },
    "calle_2": {
        "desc": "Igual que Situación Real 1 pero sentados en una terraza, y ahí habla primero el grupo.",
        "label": "☕ Situación Real 2",
        "estilo_mof10": "real_2",
        # Desde sep 2026 también está en Moda Chica, con sus dos textos.
        "sexos": ("mujer", "hombre"),
    },
    "gafas_coche": {
        "desc": "Selfie en el asiento del conductor con el coche parado. Es para GAFAS, no para ropa.",
        "label": "🕶️ Gafas en Coche",
        "estilo_mof10": "gafas",
        "sexos": ("hombre",),
    },
    "sarcastica": {
        "desc": "Camiseta con frase, comprando en un súper sin mirar a cámara. Sale MUDO: la gracia la pone el texto de la camiseta.",
        "label": "😏 Camiseta Sarcástica",
        "estilo_mof10": "sarcastica",
        "sexos": ("hombre",),
    },
    # El maniquí no lleva persona, así que la prenda podría ser de cualquiera;
    # se deja en hombre porque es donde lo publica y porque el resto del menú
    # de mujer va con modelo.
    "maniqui": {
        "desc": "La camiseta en un maniquí sin cabeza y dos manos estirándola. Sin persona y MUDO.",
        "label": "🧍 Camiseta Maniquí",
        "estilo_mof10": "maniqui",
        "sexos": ("hombre",),
    },
    # "BOLSO MOF MUJER POV ONMI 10S" existe en su web pero AÚN NO tiene
    # prompts publicados, así que no se ofrece: un modo sin prompt es un botón
    # que no lleva a nada. Al pegarlos, se añade aquí con `estilo_mof10:
    # "bolso"` y su entrada en `ESTILOS_MOF10`. Ojo: solo vale para prendas
    # que SEAN bolsos — necesita el filtro por categoría (ver tasks.md).
    # El primero que se graba en DOS partes: el generador no da los 15
    # segundos de una pieza, así que son dos clips de la misma chica en dos
    # calles distintas que se pegan al montar (ver `PARTES`).
    "calle_dividido": {
        "desc": "En la calle, hablando sola a cámara de cuerpo entero. Son DOS clips (dos calles) que se pegan: 15s en total.",
        "label": "🚶\u200d♀️ Calle Dividido 15s",
        "estilo_mof10": "calle_dividido",
        "sexos": ("mujer",),
    },
    # NUESTRO, no del curso: la receta de cinco virales de pantalones (sep
    # 2026). Como el de calle dividido son dos clips de 8s, pero en una
    # TIENDA y con el arranque de colores: la chica nombra tres o cuatro y
    # en cada uno el pantalón cambia de golpe. Ese corte no lo hace Flow —
    # lo monta la app recoloreando el primer fotograma (ver `colores` en el
    # estilo y `pipeline/colores.py`).
    "tienda_colores": {
        "desc": "En una tienda, top blanco y cuerpo entero. Arranca nombrando los colores (el pantalón cambia en cada uno, lo monta la app), enseña cintura y bolsillos, se da la vuelta y se agacha. DOS clips de 8s.",
        "label": "🏬 Tienda Colores 15s",
        "estilo_mof10": "tienda_colores",
        "sexos": ("mujer",),
    },
    # ---- MARCA PERSONAL (sep 2026) -------------------------------------
    # La otra modalidad de Moda Mujer. Lo que la separa de los de arriba no es
    # el estilo, es la CUENTA: aquellos van con personajes distintos cada vez y
    # estos repiten el mismo, que es lo que construye la marca. Por eso llevan
    # `modalidad` y la pantalla los enseña por separado.
    #
    # `categoria` filtra el catálogo: dos de los tres son de calzado y en una
    # carpeta con vestidos no pintan nada (ver `es_calzado`).
    "marca_espejo": {
        "desc": "Tu personaje fijo frente al espejo, varias escenas en un clip.",
        "label": "🪞 Espejo Multi Escena 10s",
        "estilo_mof10": "marca_espejo",
        "sexos": ("mujer",),
        "modalidad": "marca",
    },
    "marca_zapatos": {
        "desc": "Tu personaje fijo con los zapatos, varias escenas. Solo calzado.",
        "label": "👢 Zapatos Multi Escena 10s",
        "estilo_mof10": "marca_zapatos",
        "sexos": ("mujer",),
        "modalidad": "marca",
        "categoria": "calzado",
    },
    "marca_pov": {
        "desc": "Los zapatos vistos desde arriba, en primera persona. Solo calzado.",
        "label": "👟 Zapatos Vista POV 10s",
        "estilo_mof10": "marca_pov",
        "sexos": ("mujer",),
        "modalidad": "marca",
        "categoria": "calzado",
    },
}
MODO_DEFECTO = "espejo"
# Las dos modalidades de Moda Mujer. Los modos sin `modalidad` son los de
# siempre (personajes aleatorios); es el defecto para no tocar lo ya guardado.
MODALIDAD_DEFECTO = "aleatorios"

# El texto que se quema en los formatos de marca personal. NO sale del
# producto: en los vídeos de referencia el de espejo y el de POV llevan el
# mismo ("AUTUMN / cozy season") y solo el de zapatos lo cambia por el tipo de
# prenda. Es una etiqueta de TEMPORADA, así que se escribe aquí y se cambia
# cuando cambie la estación, no producto a producto.
#
# `segundos` es cuánto se ve: medido sobre los vídeos del curso, el del espejo
# lo enseña un par de segundos y el de POV lo deja el vídeo entero (0 = todo).
TEXTO_MARCA: dict[str, dict] = {
    "marca_espejo": {"titulo": "AUTUMN", "bajada": "cozy season", "segundos": 3.0},
    "marca_zapatos": {"titulo": "AUTUMN BOOTS", "bajada": "step into style", "segundos": 3.0},
    "marca_pov": {"titulo": "AUTUMN", "bajada": "cozy season", "segundos": 0.0},
}


# El ritmo del Nicho General, que es el que ya funciona en clips de 8s: 136
# caracteres para 8 segundos (17 car/s).
CARACTERES_POR_SEGUNDO_CLIP = 17


def caracteres_por_clip(meta: dict) -> int:
    """Lo que cabe en un clip de ese formato. 0 = no se parte.

    Se descuenta UN segundo: el bloque de vídeo pide empezar a hablar pasado
    medio segundo y acabar antes del último (`nota_tiempos`), porque sin ese
    respiro el generador se comía la primera palabra y la última frase. 8s →
    7s hablados → 119 caracteres.
    """
    segundos = int(meta.get("segundos_clip") or 0)
    if not segundos or int(meta.get("partes") or 1) < 2:
        return 0
    # Un estilo puede fijar el suyo más bajo: el de la tienda con 102 car en
    # el clip 2 se comió "elige el tuyo" (Omni repitió media frase y llegó al
    # segundo 8 hablando). Con ~100 hay margen para esos tropiezos.
    if meta.get("caracteres_clip"):
        return int(meta["caracteres_clip"])
    return (segundos - 1) * CARACTERES_POR_SEGUNDO_CLIP


# ---------------------------------------------------------------------------
# Familias de prenda (formato Tienda Colores)
# ---------------------------------------------------------------------------
# El formato es el mismo para cualquier prenda —cortes de color al ritmo de
# la voz, dos detalles y cierre con el perchero— pero el GESTO y las ZONAS
# cambian con lo que se enseña. Sale de medir diez virales: solo en los
# pantalones se la suben; en las prendas de arriba el cambio de color se hace
# con un gesto neutro repetido (sostenerla delante, abrir el cárdigan, tirar
# del bajo del jersey) y corte seco.
#
# `palabras` detecta la familia por el título, como el filtro de calzado.
# `gesto` es lo que hace mientras nombra los colores; `detalle_1/2` los dos
# planos del clip 1; `detalle_3` el primero del clip 2; `zonas` lo que el
# guion tiene que nombrar, en ese orden.
FAMILIAS_PRENDA: dict[str, dict] = {
    "pantalon": {
        "label": "Pantalón, falda o short",
        "palabras": (
            "pantalon", "pantalón", "jean", "vaquero", "palazzo", "culotte",
            "jogger", "cargo", "short", "bermuda", "falda", "legging", "wide leg",
        ),
        "gesto": (
            "está de tres cuartos, algo encorvada, tirando de la prenda hacia arriba "
            "con las dos manos desde el muslo, por encima de unas mallas cortas "
            "negras tipo ciclista, como quien se la acaba de poner; el cuerpo "
            "girado deja ver la curva de la cadera de perfil"
        ),
        "final_gesto": (
            "termina de subírsela, la asienta en la cintura y se yergue del todo, "
            "quedando de pie con las manos en las caderas"
        ),
        "detalle_1": (
            "Primer plano de la cintura y las caderas, la cámara se acerca. Con las "
            "dos manos estira la cinturilla hacia fuera y enseña el cordón y los "
            "bolsillos; la tela se ve de cerca, con su textura real"
        ),
        "detalle_2": (
            "Plano de las piernas, del pecho a los pies, cámara fija. Estira la tela "
            "de las dos perneras hacia los lados para que se vea el ancho, y da un "
            "paso o balancea una pierna para que se vea la caída"
        ),
        "detalle_3": (
            "Plano entero de espaldas, cuerpo entero, cámara fija, con las manos en "
            "la cintura y la cabeza girada por encima del hombro. Se gira despacio "
            "sobre sí misma y arquea un poco la espalda, marcando la curva de la "
            "cadera, para que se vea cómo sienta la prenda por detrás"
        ),
        "prueba": (
            "Plano más cerrado, de la espalda a las rodillas, con la cámara algo más "
            "cerca: hace una sentadilla completa, baja del todo y se levanta "
            "despacio, para que se vea de cerca que la cintura no se baja ni se "
            "abre y que la tela no transparenta"
        ),
        "zonas": "la cintura (alta, elástica, con cordón o botón, los bolsillos) y la pierna (ancha, la caída, el tejido)",
        "pose_imagen": "the trousers are pulled up only to mid-thigh and she is about to pull them up, so her plain black bike shorts are visible above them; her body is in three-quarter view so the curve of her hip shows; the trousers keep their full length and their hem reaches the shoes.",
        "manos_imagen": "both hands gripping the waistband of the trousers at mid-thigh height, mid-motion, about to pull them up",
        "ropa_base": "On top she wears a plain, fitted, PLAIN WHITE top with no print, no logo and no text, cropped so her waist is visible. Underneath the referenced trousers she wears plain BLACK fitted bike shorts (mid-thigh sports shorts), visible above them. Nothing revealing: only normal sportswear.",
    },
    "punto": {
        "label": "Jersey, chaleco o camiseta",
        "palabras": (
            "jersey", "sueter", "suéter", "sweater", "punto", "chaleco", "camiseta",
            "top", "blusa", "camisa", "polo", "sudadera",
        ),
        "gesto": (
            "está de pie, de frente, y agarra el bajo de la prenda con las dos manos "
            "dándole un tirón corto hacia abajo para colocársela, como quien se la "
            "acaba de poner"
        ),
        "final_gesto": (
            "suelta el bajo, se coloca el cuello con una mano y se queda de pie, "
            "relajada, mirando a cámara"
        ),
        "detalle_1": (
            "Primer plano del cuello y los hombros, la cámara se acerca. Se coloca el "
            "cuello con las dos manos y pasa la mano por el punto para que se vea la "
            "textura de cerca"
        ),
        "detalle_2": (
            "Plano medio, del pecho a las caderas, cámara fija. Agarra el bajo de la "
            "prenda con las dos manos, lo estira hacia los lados y se lo mete y lo "
            "saca del pantalón para enseñar cómo queda de las dos maneras"
        ),
        "detalle_3": (
            "Plano entero de espaldas, cuerpo entero, cámara fija, con la cabeza "
            "girada por encima del hombro. Gira despacio sobre sí misma para que "
            "se vea cómo cae por detrás y cómo sienta de perfil"
        ),
        "prueba": (
            "Levanta y estira los dos brazos y los baja, para que se vea que el punto "
            "no tira ni se deforma"
        ),
        "zonas": "el cuello y el tejido (suave, grueso, cómodo) y el corte (holgado, la caída, cómo queda por dentro o por fuera del pantalón)",
        "pose_imagen": "she holds the hem of the garment with both hands and gives it a short downward tug to settle it.",
        "manos_imagen": "both hands holding the hem of the garment at hip height, tugging it down",
        "ropa_base": "Below the referenced garment she wears plain wide-leg blue jeans and simple white sneakers; if the garment is open or sleeveless, a plain white fitted top underneath.",
    },
    "abierta": {
        "label": "Chaqueta, cárdigan o abrigo",
        "palabras": (
            "cardigan", "cárdigan", "chaqueta", "abrigo", "blazer", "americana",
            "kimono", "trench", "gabardina", "chaquetón", "capa",
        ),
        "gesto": (
            "está de pie, de frente, y abre la prenda agarrándola por los dos "
            "delanteros y separándolos, y la vuelve a cerrar, como quien se la acaba "
            "de poner"
        ),
        "final_gesto": (
            "suelta los delanteros, se recoloca los hombros y se queda de pie, "
            "relajada, mirando a cámara"
        ),
        "detalle_1": (
            "Plano medio, del pecho a las caderas, cámara fija. Abre los dos brazos "
            "en cruz para que se vea la amplitud de la prenda y los baja despacio"
        ),
        "detalle_2": (
            "Primer plano del pecho y la manga, la cámara se acerca. Pasa la mano por "
            "el tejido y se frota el antebrazo para que se vea el punto de cerca y el "
            "largo de la manga"
        ),
        "detalle_3": (
            "Plano entero, cámara fija. Gira despacio sobre sí misma para que se vea "
            "la espalda y cómo cae la prenda de perfil"
        ),
        "prueba": (
            "Se cruza la prenda por delante y se abraza con los dos brazos, para que "
            "se vea que abriga y no tira de los hombros"
        ),
        "zonas": "el tejido y la amplitud (suave, holgada, cómo cae) y el corte (el largo, la manga, cómo queda abierta o cerrada)",
        "pose_imagen": "she holds both front panels of the open garment, one in each hand, slightly opened, as if she had just put it on.",
        "manos_imagen": "each hand holding one front panel of the open garment at chest height",
        "ropa_base": "Under the referenced garment she wears a plain white fitted t-shirt, and below plain wide-leg blue jeans and simple white sneakers.",
    },
    "capucha": {
        "label": "Sudadera con capucha o cremallera",
        "palabras": ("capucha", "hoodie", "cremallera", "zip", "chandal", "chándal"),
        "gesto": (
            "está de pie, de frente, con la prenda abierta y las manos agarrando los "
            "dos lados de la cremallera, moviéndolos un poco, como quien se la acaba "
            "de poner"
        ),
        "final_gesto": (
            "sube la cremallera hasta arriba de un tirón y se queda de pie, relajada, "
            "mirando a cámara"
        ),
        "detalle_1": (
            "Primer plano del pecho y la cintura, la cámara se acerca. Sube la "
            "cremallera de abajo arriba despacio para que se vea el tirador y el "
            "cordón, y mete las manos en los bolsillos"
        ),
        "detalle_2": (
            "Plano medio, cámara fija. Se pone la capucha con las dos manos, se la "
            "coloca y se la vuelve a quitar"
        ),
        "detalle_3": (
            "Plano entero de espaldas, cuerpo entero, cámara fija, con la capucha "
            "puesta y la cabeza girada por encima del hombro"
        ),
        "prueba": (
            "Se ajusta el puño de una manga con la otra mano y se cierra la prenda "
            "cruzándose los brazos, para que se vea que abriga"
        ),
        "zonas": "la cremallera y el tejido (suave, de invierno, con capucha) y el corte (holgado, el largo, los bolsillos)",
        "pose_imagen": "the garment is open and she holds both sides of the zip, about to zip it up.",
        "manos_imagen": "both hands holding the two sides of the open zip at waist height",
        "ropa_base": "Under the referenced garment she wears a plain white fitted top, and below plain black leggings and simple white sneakers.",
    },
    "mono": {
        "label": "Mono o vestido",
        "palabras": ("mono", "jumpsuit", "vestido", "peto", "conjunto"),
        "gesto": (
            "está de pie, de frente, y se coloca la prenda tirando del escote con una "
            "mano y de la cintura con la otra, como quien se la acaba de poner"
        ),
        "final_gesto": (
            "suelta la prenda, abre un poco los brazos para enseñarla entera y se "
            "queda de pie, mirando a cámara"
        ),
        "detalle_1": (
            "Primer plano del escote y el hombro, la cámara se acerca. Se coloca el "
            "escote con la mano y pasa los dedos por el borde para que se vea de cerca"
        ),
        "detalle_2": (
            "Plano medio, de los hombros a las caderas, cámara fija. Estira la goma "
            "de la cintura con los dedos y la suelta, para que se vea que es elástica"
        ),
        "detalle_3": (
            "Plano entero, cámara fija. Gira despacio sobre sí misma para que se vea "
            "cómo queda por detrás y cómo cae la falda o la pierna"
        ),
        "prueba": (
            "Da dos pasos y se gira para que la tela se mueva y se vea la caída"
        ),
        "zonas": "el escote y la cintura (elástica, fruncida, favorecedora) y la caída (la pierna ancha o el vuelo, el tejido)",
        "pose_imagen": "she is settling the garment, one hand at the neckline and the other at the waist.",
        "manos_imagen": "one hand at the neckline and the other at the waistband, settling the garment",
        "ropa_base": "She wears nothing over the referenced garment; only simple neutral shoes.",
    },
}
FAMILIA_DEFECTO = "pantalon"


def familia_de(titulo: str) -> str:
    """Qué familia de prenda es, por el título. Se mira en orden: las
    específicas (capucha, abierta, mono) antes que las generales, porque
    "sudadera con capucha" es de las dos y manda la capucha."""
    plano = _sin_acentos(titulo or "")
    for clave in ("capucha", "abierta", "mono", "pantalon", "punto"):
        if any(pal in plano for pal in FAMILIAS_PRENDA[clave]["palabras"]):
            return clave
    return FAMILIA_DEFECTO


def _sin_acentos(txt: str) -> str:
    import unicodedata

    plano = unicodedata.normalize("NFKD", txt or "")
    return "".join(c for c in plano if not unicodedata.combining(c)).lower()


def con_familia(texto: str, titulo: str) -> str:
    """Rellena los marcadores de familia de un prompt con los de esa prenda."""
    fam = FAMILIAS_PRENDA[familia_de(titulo)]
    for clave in (
        "gesto", "final_gesto", "detalle_1", "detalle_2", "detalle_3", "prueba",
        "zonas", "pose_imagen", "manos_imagen", "ropa_base",
    ):
        texto = texto.replace("{{" + clave.upper() + "}}", fam[clave])
    return texto


def familias_para_pantalla() -> dict[str, dict]:
    """Los reemplazos de cada familia, para que la pantalla rellene los
    prompts sin pedir nada más: son cinco familias, no una por prenda."""
    campos = (
        "gesto", "final_gesto", "detalle_1", "detalle_2", "detalle_3", "prueba",
        "zonas", "pose_imagen", "manos_imagen", "ropa_base",
    )
    return {
        clave: {"label": fam["label"], **{c: fam[c] for c in campos}}
        for clave, fam in FAMILIAS_PRENDA.items()
    }


def minimo_variantes(modo: str) -> int:
    """Cuántos colores necesita una prenda para poder grabarse con ese modo.
    0 = da igual (todos los formatos menos el de la tienda)."""
    return int((ESTILOS_MOF10.get(estilo_de_modo(modo)) or {}).get("minimo_variantes") or 0)


def partes_de_modo(modo: str) -> int:
    """En cuántos clips se graba ese formato. 1 = como siempre."""
    return int((ESTILOS_MOF10.get(estilo_de_modo(modo)) or {}).get("partes") or 1)


def lleva_flecha(modo: str) -> bool:
    """Si a ese formato se le pone la flecha al carrito al final."""
    return bool((ESTILOS_MOF10.get(estilo_de_modo(modo)) or {}).get("flecha"))


def lleva_colores(modo: str) -> bool:
    """Si ese formato arranca con los cortes de color (los monta la app)."""
    return bool((ESTILOS_MOF10.get(estilo_de_modo(modo)) or {}).get("colores"))


def lleva_subtitulos(modo: str) -> bool:
    """Si a ese formato se le queman los subtítulos de lo que dice."""
    return bool((ESTILOS_MOF10.get(estilo_de_modo(modo)) or {}).get("subtitulos"))


def texto_de_modo(modo: str) -> dict:
    """El texto quemado que le toca a ese modo. `{}` si no lleva ninguno."""
    return dict(TEXTO_MARCA.get(estilo_de_modo(modo)) or {})
# Palabras que delatan un calzado en el título ya extraído. Se filtra por
# palabra y no con una llamada a la IA porque la pregunta es fácil: en
# Carruseles hizo falta Gemini porque allí se preguntaba "¿este producto
# funciona en este formato?", que es de criterio; "¿esto es un zapato?" lo
# responde una lista.
#
# No pretende acertar siempre —"Dr. Martens 1460" no lleva ninguna—, por eso
# hay interruptor manual por prenda: esto es para no tener que marcar las
# nueve que sí son obvias.
PALABRAS_CALZADO = (
    "zapato", "zapatilla", "zapatillas", "bota", "botas", "botin", "botín",
    "botines", "sandalia", "sandalias", "deportiva", "deportivas", "tacon",
    "tacón", "tacones", "mocasin", "mocasín", "mocasines", "bailarina",
    "bailarinas", "sneaker", "sneakers", "chancla", "chanclas", "alpargata",
    "alpargatas", "playera", "playeras", "calzado", "slippers", "loafer",
    "loafers", "heels", "boots", "shoes",
)


def es_calzado(titulo: str) -> bool:
    """¿El título dice que esto es un zapato?"""
    import unicodedata

    t = unicodedata.normalize("NFKD", (titulo or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    palabras = set(t.replace("/", " ").replace("-", " ").split())
    return any(
        unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode() in palabras
        for w in PALABRAS_CALZADO
    )


def categoria_de_modo(modo: str) -> str:
    """`"calzado"` si ese modo solo vale para zapatos; `""` si vale para todo."""
    return str(MODOS.get(modo_valido(modo), {}).get("categoria") or "")


MODALIDADES: dict[str, str] = {
    "aleatorios": "🎭 Personajes aleatorios",
    "marca": "👤 Marca Personal",
}


def modo_valido(modo: str) -> str:
    return modo if modo in MODOS else MODO_DEFECTO


def modos_de(sexo: str, modalidad: str = MODALIDAD_DEFECTO) -> list[dict]:
    """Los modos que existen para ese sexo, en el orden de la web.

    El de siempre (`espejo`) va el primero y vale para los dos, así que una
    prenda nunca se queda sin ningún modo.
    """
    sexo = sexo if sexo in ("mujer", "hombre") else SEXO_DEFECTO
    quiere = modalidad if modalidad in MODALIDADES else MODALIDAD_DEFECTO
    return [
        {
            "clave": clave,
            "label": meta["label"],
            # Con qué se graba: los de marca personal necesitan el personaje
            # de referencia y los de calzado, que la prenda sea un zapato.
            "modalidad": meta.get("modalidad", MODALIDAD_DEFECTO),
            # Qué se ve en ese vídeo, en una frase. Va en el backend y no en
            # la pantalla porque es lo que dice el curso de cada formato, y
            # sin ello los modos son siete botones con un emoji.
            "desc": meta.get("desc", ""),
            "categoria": meta.get("categoria", ""),
            "personaje": bool(
                (ESTILOS_MOF10.get(meta["estilo_mof10"]) or {}).get("personaje")
            ),
            # Si el clip sale HABLADO. Los dos de camiseta no: su paso 2 es
            # solo movimiento, así que no gastan voz del generador —que es lo
            # caro— y la gracia la pone el texto de la prenda.
            "voz": bool(
                (ESTILOS_MOF10.get(meta["estilo_mof10"]) or {}).get("voz", True)
            ),
        }
        for clave, meta in MODOS.items()
        if sexo in meta["sexos"]
        and meta.get("modalidad", MODALIDAD_DEFECTO) == quiere
    ]


def estilo_de_modo(modo: str) -> str:
    """La clave de `ESTILOS_MOF10` que le toca a ese modo."""
    return MODOS[modo_valido(modo)]["estilo_mof10"]


def es_carpeta_web(slug: str) -> bool:
    return SEPARADOR_WEB in (slug or "")


def partes_web(slug: str) -> tuple[str, str]:
    """`mujer_web__Carpeta 23` → `("mujer_web", "Carpeta 23")`."""
    genero, _, carpeta = (slug or "").partition(SEPARADOR_WEB)
    return genero, carpeta


def slug_web(genero: str, carpeta: str) -> str:
    return f"{genero}{SEPARADOR_WEB}{carpeta}"


_MIS_PRENDAS_DIR: Path | None = None


def mis_prendas_dir() -> Path:
    """Raíz de las prendas que sube el operador, en el Drive MONTADO.

    Se recuerda por lo mismo que en el POV BOF: el `mkdir` contra el mount en
    frío cuesta segundos y la llaman todas las demás.
    """
    global _MIS_PRENDAS_DIR
    if _MIS_PRENDAS_DIR is not None:
        return _MIS_PRENDAS_DIR

    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    destino = (
        raiz / MIS_PRENDAS_ROOT if raiz
        else Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "mis_prendas"
    )
    destino.mkdir(parents=True, exist_ok=True)
    _MIS_PRENDAS_DIR = destino
    return destino


_PRENDAS_WEB_DIR: Path | None = None


def prendas_web_dir() -> Path:
    """Raíz de las prendas importadas, en el Drive MONTADO."""
    global _PRENDAS_WEB_DIR
    if _PRENDAS_WEB_DIR is not None:
        return _PRENDAS_WEB_DIR

    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    destino = (
        raiz / PRENDAS_WEB_ROOT if raiz
        else Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "prendas_web"
    )
    destino.mkdir(parents=True, exist_ok=True)
    _PRENDAS_WEB_DIR = destino
    return destino


def es_carpeta_conocida(slug: str) -> bool:
    """¿Se puede trabajar con esa carpeta?

    Los catálogos del operador cuentan igual que los de la web: son un género
    más. Dejarlos fuera fue el fallo al estrenarlos — el alta funcionaba, la
    carpeta salía en el selector y al abrirla contestaba "Carpeta desconocida:
    'hombre_tareas__Tareas 1'", porque quien valida el slug es esto.
    """
    if es_carpeta_web(slug):
        genero, carpeta = partes_web(slug)
        return bool(carpeta) and (genero in GENEROS_WEB or genero in GENEROS_OPERADOR)
    return slug in CARPETAS


def carpeta_label(slug: str) -> str:
    if es_carpeta_web(slug):
        genero, carpeta = partes_web(slug)
        etiqueta = GENEROS_WEB.get(genero) or GENEROS_OPERADOR.get(genero) or genero
        return f"{etiqueta} · {carpeta}"
    return CARPETAS.get(slug, {}).get("label", slug)


def carpeta_id(slug: str = "") -> str:
    """ID de Drive de una carpeta. Override global por `.env` para pruebas."""
    forzado = (os.getenv("NICHO_ROPA_FOLDER_ID") or "").strip()
    if forzado:
        return forzado
    if es_carpeta_web(slug):
        raise ValueError(
            f"{slug!r} es una carpeta importada por ZIP: no está en Drive, se "
            "lee del disco."
        )
    meta = CARPETAS.get(slug or CARPETA_DEFECTO)
    if not meta:
        raise ValueError(
            f"Carpeta desconocida: {slug!r}. Válidas: {sorted(CARPETAS)}"
        )
    return meta["id"]


def redis_prefix() -> str:
    return os.getenv("NICHO_ROPA_REDIS_PREFIX", "nicho_ropa:")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
def _limpio(fichero: str) -> str:
    """El `.md` sin sus notas `<!-- ... -->`, listo para pegar."""
    from src.nicho_pov_bof.config import limpiar_prompt

    return limpiar_prompt((prompts_dir() / fichero).read_text(encoding="utf-8"))


def prompt_recolor(color: str, tono: str = "") -> str:
    """El encargo a Gemini para recolorear el primer fotograma a ESE color.

    `tono` es el hex de la miniatura de esa variante en la tienda: con él se
    pide clavar ese matiz y no el genérico del nombre. Vacío = por el nombre.
    """
    referencia = (
        f"Target shade: approximately {tono.strip()} (sampled from the shop's "
        "own swatch for this variant). Match that hue and lightness with "
        "realistic fabric shading, not a generic version of the colour name."
        if tono.strip() else ""
    )
    return (
        _limpio("recolor_prenda.md")
        .replace("{{COLOR}}", color.strip())
        .replace("{{REFERENCIA}}", referencia)
        .strip()
    )


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


# El prompt de vídeo tiene dos versiones y la diferencia es UNA frase: la de la
# mano acariciando la ropa. Se guarda una sola vez y la versión sin manos es
# ese texto menos esa línea, para que no puedan quedar desincronizados.
LINEA_MANOS = "Una mano aparece en escena y acaricia la ropa."


def prompt_video(con_manos: bool) -> str:
    texto = _limpio("prompt_video.md")
    if con_manos:
        return texto
    return " ".join(texto.replace(LINEA_MANOS, "").split())


def prompt_video_percha() -> str:
    """Segundo estilo del nicho: la prenda colgada en una percha, sin nadie.

    Sale de `Camisetas／Conjuntos/Ropa/Pronts/Ropa Percha.docx`. No estaba en la
    carpeta de Skool — apareció al mirar el Drive de productos. Es el otro
    prompt de los seis de ropa que NO lleva modelo (los demás sí, y esos son
    del módulo 7).

    Va aparte y no como variante del de alfombra porque no comparte texto: es
    otro escenario entero, no la misma toma con o sin manos.
    """
    return _limpio("prompt_video_percha.md")


# ---------------------------------------------------------------------------
# Prompt del espejo (el de la web, con persona)
SEXO_DEFECTO = "mujer"


def sexo_de_carpeta(slug: str) -> str:
    """Qué versión del prompt del espejo le toca a una carpeta.

    Las importadas por ZIP lo llevan en el slug (`hombre_web__Carpeta 3`). Las
    cuatro del Drive son todas de mujer, así que caen en el defecto.
    """
    if es_carpeta_web(slug):
        genero, _ = partes_web(slug)
        if genero.startswith("hombre"):
            return "hombre"
    return SEXO_DEFECTO


# ---------------------------------------------------------------------------
# "MOF 10 segundos": imagen en Flow + vídeo en Omni
# ---------------------------------------------------------------------------
# El otro camino de su web, y el que deja un clip ÚNICO de 10s: primero se
# genera la imagen de la persona con la prenda puesta (Flow, con la foto de la
# prenda como referencia) y después esa imagen se anima con voz en Omni. El
# guion lo escribe ChatGPT a partir de la foto de la FICHA, así que sale con el
# precio y los detalles de ESE producto — 180 caracteres, no 160.
#
# El texto de HOMBRE es suyo, literal. El de mujer se deriva.
SEXOS_MOF10: dict[str, dict[str, str]] = {
    "hombre": {
        "PERSONA": "man",
        "EL": "He",
        "SU": "His",
        "SU_MIN": "his",
        "GENERO_ADJ": "masculine",
        "GENERO_SUJETO": "male",
        "MAQUILLAJE": "none",
        "CARA": (
            "realistic masculine facial features, visible pores and natural "
            "skin texture, clean-shaven or subtle light stubble"
        ),
        "EL_SUJETO": "el chico dice",
        "EL_SUJETO_MAY": "El chico",
        "VOZ_ADJ": "masculina",
        "VOZ_DESC": (
            "Joven, natural, desenfadada, cercana. Tono medio-grave, cálido y "
            "conversacional, sin cadencia publicitaria. Ritmo ágil, espontáneo, "
            "como un creador UGC real. Pronunciación española clara. Misma voz "
            "toda la escena."
        ),
        "CARA_ESPEJO": (
            "none, natural skin texture, clean-shaven or light stubble, "
            "realistic skin texture"
        ),
        "SUJETO_CORTO": "chico",
        "UN_SUJETO": "Un chico",
        "A": "",
    },
    "mujer": {
        "PERSONA": "woman",
        "EL": "She",
        "SU": "Her",
        "SU_MIN": "her",
        "GENERO_ADJ": "feminine",
        "GENERO_SUJETO": "female",
        "MAQUILLAJE": "natural, minimal",
        "CARA": (
            "realistic feminine facial features, visible pores and natural "
            "skin texture"
        ),
        "EL_SUJETO": "la chica dice",
        "EL_SUJETO_MAY": "La chica",
        "VOZ_ADJ": "femenina",
        "VOZ_DESC": (
            "Joven, natural, desenfadada, cercana. Tono medio-agudo, cálido y "
            "conversacional, sin cadencia publicitaria. Ritmo ágil, espontáneo, "
            "como una creadora UGC real. Pronunciación española clara. Misma "
            "voz toda la escena."
        ),
        "CARA_ESPEJO": (
            "natural and minimal, natural skin texture, realistic skin texture"
        ),
        "SUJETO_CORTO": "chica",
        "UN_SUJETO": "Una chica",
        "A": "a",
    },
}


# La duración del clip que se va a generar. Omni da 10 segundos y GenAI Pro
# (Veo) da 8, y en 8 segundos NO cabe el mismo guion: aquí la voz la pone el
# propio vídeo, así que un guion que no entra sale cortado a media frase.
#
# El tope baja proporcional (18 car/s, que es lo que sale de sus 180 para 10s),
# igual que en el Nicho General. Solo aplica a los estilos cuyo guion se
# escribe con ChatGPT; los de calle traen el diálogo cerrado y no se tocan.
CARACTERES_POR_SEGUNDO = 18
DURACIONES: dict[str, dict] = {
    "10": {"label": "10 s · Omni", "segundos": 10, "caracteres": 180},
    "8": {"label": "8 s · GenAI Pro (Veo)", "segundos": 8, "caracteres": 144},
}
DURACION_DEFECTO = "10"


def duracion_valida(duracion: str) -> str:
    return duracion if duracion in DURACIONES else DURACION_DEFECTO


# Aviso NUESTRO, y solo cuando el clip no dura los 10 segundos suyos: su
# ejemplo está escrito para Omni y mide lo que mide, así que sin esta línea
# ChatGPT copia esa longitud y el guion se sale del clip.
NOTA_DURACION = (
    "\n\nOJO: este clip dura {segundos} segundos, no 10. El ejemplo de arriba "
    "está escrito para 10, así que el tuyo tiene que ser más corto: "
    "{caracteres} caracteres como máximo."
)


def _con_duracion(texto: str, duracion: str, caracteres: int = 0) -> str:
    """Rellena el tope de caracteres que le toca a esa duración.

    `caracteres` lo pisa: hay formatos cuyo tope es del FORMATO y no de la
    duración elegida (el de calle dividido son 15 segundos, siempre).
    """
    meta = DURACIONES[duracion_valida(duracion)]
    tope = caracteres or meta["caracteres"]
    return (
        texto.replace("{{CARACTERES}}", str(tope))
        # El mínimo va 30 por debajo del tope: con el "mínimo 250" del curso y
        # un tope de 240 se le pedía algo imposible.
        .replace("{{MINIMO}}", str(max(0, tope - 30)))
        .replace("{{SEGUNDOS}}", str(meta["segundos"]))
    )


# Los estilos de 10s que tiene publicados. Van en lista porque va sacando más,
# y cada uno son DOS prompts: la imagen y el guion+movimiento.
#
# `derivado` dice de qué sexos el texto NO es suyo sino nuestro, cambiando las
# palabras de la persona. Se marca en la pantalla: un prompt derivado funciona,
# pero si él publica el suyo hay que pegarlo encima.
ESTILOS_MOF10: dict[str, dict] = {
    # ---- MARCA PERSONAL --------------------------------------------------
    # Tres diferencias con los de arriba, y las tres importan al pegarlos:
    #   `personaje`  se adjunta la imagen del personaje de referencia. En el
    #                POV no: su prompt pide una mujer ALEATORIA.
    #   `ingrediente` la imagen entra en Flow como ingrediente y no como frame
    #                inicial. Solo el de zapatos multi escena, y equivocarse
    #                no da error: sale otro vídeo.
    #   `voz`        ninguno habla. El de zapatos lo prohíbe en su propio
    #                prompt (`audio: none`), así que la música se pone en
    #                TikTok al publicar — y aquí hace falta, porque un vídeo
    #                mudo entero no retiene.
    "marca_espejo": {
        "label": "Marca personal · frente al espejo",
        "voz": False,
        "duraciones": False,
        "personaje": True,
        "ingrediente": False,
        "por_sexo": {
            "mujer": (
                "prompt_marca_espejo_imagen.md",
                "prompt_marca_espejo_guion.md",
            ),
        },
        "derivado": (),
    },
    "marca_zapatos": {
        "label": "Marca personal · zapatos multi escena",
        "voz": False,
        "duraciones": False,
        "personaje": True,
        "ingrediente": True,
        "por_sexo": {
            "mujer": (
                "prompt_marca_zapatos_imagen.md",
                "prompt_marca_zapatos_guion.md",
            ),
        },
        "derivado": (),
    },
    "marca_pov": {
        "label": "Marca personal · zapatos vista POV",
        "voz": False,
        "duraciones": False,
        # Sin personaje: el prompt pide "a completely random young woman".
        "personaje": False,
        "ingrediente": False,
        "por_sexo": {
            "mujer": (
                "prompt_marca_pov_imagen.md",
                "prompt_marca_pov_guion.md",
            ),
        },
        "derivado": (),
    },
    # De este publica los DOS sexos, así que no se deriva nada: van sus dos
    # textos tal cual. Y hace falta, porque entre ellos cambia más que el
    # género —maquillaje, joyería y un bloque de movimiento entero—.
    "espejo": {
        "label": "Frente al espejo · cuerpo entero",
        "voz": True,
        "duraciones": True,
        "por_sexo": {
            "hombre": (
                "prompt_mof10_espejo_hombre_imagen.md",
                "prompt_mof10_espejo_hombre_guion.md",
            ),
            "mujer": (
                "prompt_mof10_espejo_mujer_imagen.md",
                "prompt_mof10_espejo_mujer_guion.md",
            ),
        },
        "derivado": (),
    },
    # Ya publica los DOS sexos, así que se acabó derivar: entre ellos cambia
    # más que el género (maquillaje, joyería, el encuadre del brazo).
    "movil": {
        "label": "BOF Selfie · brazo estirado",
        "voz": True,
        "duraciones": True,
        "por_sexo": {
            "hombre": (
                "prompt_mof10_movil_hombre_imagen.md",
                "prompt_mof10_movil_hombre_guion.md",
            ),
            "mujer": (
                "prompt_mof10_movil_mujer_imagen.md",
                "prompt_mof10_movil_mujer_guion.md",
            ),
        },
        "derivado": (),
    },
    # El primero que NO va de ropa: unas gafas puestas, en el coche. Mismo
    # molde de guion que el espejo y el selfie —tope de caracteres incluido—,
    # así que también elige duración. Solo de hombre.
    "gafas": {
        "duraciones": True,
        "label": "Gafas en el coche · selfie",
        "voz": True,
        "imagen": "prompt_mof10_gafas_imagen.md",
        "guion": "prompt_mof10_gafas_guion.md",
        "derivado": (),
    },
    # Estos dos son distintos de todo lo demás: NADIE HABLA. Su paso 2 no es
    # un guion sino tres líneas de movimiento, así que no hay tope que bajar y
    # no eligen duración. En el de las camisetas la gracia la pone el texto de
    # la prenda y la risa que se añade en Omni; en el del maniquí no sale
    # ninguna persona, solo dos manos.
    "sarcastica": {
        "duraciones": False,
        "label": "Camiseta sarcástica · en el súper",
        "voz": False,
        "imagen": "prompt_mof10_sarcastica_imagen.md",
        "guion": "prompt_mof10_sarcastica_guion.md",
        "derivado": (),
    },
    "maniqui": {
        "duraciones": False,
        "label": "Camiseta en maniquí · sin persona",
        "voz": False,
        "imagen": "prompt_mof10_maniqui_imagen.md",
        "guion": "prompt_mof10_maniqui_guion.md",
        "derivado": (),
    },
    # Este va en los DOS menús de su web, cada uno con su imagen. El guion de
    # mujer sí es NUESTRO: lo que publica en Moda Chica es el de hombre tal
    # cual —el del outfit es un chico— y con la imagen de una chica el vídeo
    # saldría con un hombre llevando ropa de mujer. Su propio Situación Real 2
    # de mujer enseña cómo va el formato: la del outfit es ella.
    "real_1": {
        # Diálogo cerrado: no hay tope que bajar, así que va siempre a 10s.
        "duraciones": False,
        "label": "Situación Real 1 · le paran por la calle",
        "voz": True,
        "por_sexo": {
            "hombre": (
                "prompt_mof10_real_1_imagen.md",
                "prompt_mof10_real_1_guion.md",
            ),
            "mujer": (
                "prompt_mof10_real_1_mujer_imagen.md",
                "prompt_mof10_real_1_mujer_guion.md",
            ),
        },
        "derivado": ("mujer",),
    },
    # El paso 1 solo saca el RETRATO con el outfit puesto, no la escena: esa la
    # pone el paso 2, en la calle o en la terraza. Por eso una misma imagen
    # sirve para los dos estilos.
    "real_2": {
        # Diálogo cerrado: no hay tope que bajar, así que va siempre a 10s.
        "duraciones": False,
        "label": "Situación Real 2 · le reciben en una terraza",
        "voz": True,
        "por_sexo": {
            "hombre": (
                # Comparte la IMAGEN con Real 1 —es el mismo texto en su web,
                # palabra por palabra—; lo que cambia es la escena del vídeo.
                # Se apunta al mismo fichero en vez de duplicarlo: dos copias
                # se desincronizan a la primera.
                "prompt_mof10_real_1_imagen.md",
                "prompt_mof10_real_2_guion.md",
            ),
            "mujer": (
                # En mujer NO la comparte: cambian cinco frases sueltas
                # respecto a la de Real 1, así que va su propio fichero.
                "prompt_mof10_real_2_mujer_imagen.md",
                "prompt_mof10_real_2_mujer_guion.md",
            ),
        },
        "derivado": (),
    },
    # El de 15 segundos en la calle, partido en dos clips. Tres cosas que no
    # tiene ningún otro estilo:
    #   `imagen2`    un tercer prompt: la misma chica en otra calle, que es la
    #                segunda mitad del vídeo.
    #   `partes`     cuántos clips se suben y se pegan al montar.
    #   `caracteres` el tope lo manda el FORMATO (15s), no el selector de
    #                duración, así que va fijo aquí y no en `DURACIONES`.
    "calle_dividido": {
        "duraciones": False,
        "label": "Calle dividido · 15s en dos clips",
        "voz": True,
        # El tope es POR CLIP, no del vídeo: el curso pide 250-300 para 15s de
        # una pieza, pero aquí son dos clips de 8s y cada uno arranca y acaba
        # su frase. 8s a 18 car/s son 144, y con el respiro de entrada y
        # salida caben ~130. Con 300 partidos en dos, cada mitad salía de
        # 150-240 y el clip se comía el final.
        "segundos_clip": 8,
        # Menos que 2 x 129 a propósito: el corte cae en un punto o una coma,
        # no en el centro, así que una mitad sale siempre algo más larga.
        "caracteres": 240,
        "partes": 2,
        # Refuerzo anti-sanción: el clip habla, así que lo que dice se lee
        # también (ver AGENTS.md). El curso lo publica sin texto encima.
        "subtitulos": True,
        # La flecha al carrito los últimos segundos: el guion del curso no
        # lleva CTA (y no se toca), así que es la única llamada a comprar.
        "flecha": True,
        "imagen2": "prompt_mof10_calle_dividido_imagen2.md",
        "por_sexo": {
            "mujer": (
                "prompt_mof10_calle_dividido_imagen.md",
                "prompt_mof10_calle_dividido_guion.md",
            ),
        },
        "derivado": (),
    },
    # El de la tienda con los colores. Mismo esqueleto que el de calle
    # dividido (dos clips de 8s, segunda imagen, subtítulos y flecha) y una
    # cosa que no tiene ningún otro:
    #   `colores`    el guion devuelve además la lista de colores que nombra
    #                (el puesto, el último), y al montar se recolorea el
    #                primer fotograma del clip 1 con Gemini y se intercalan
    #                los cortes al ritmo de las palabras. El operador NO
    #                genera nada más: sube los dos clips y ya.
    # El tope es más bajo que el de calle dividido: medido sobre cinco
    # virales, los que cabían sin comerse palabras iban de 236 a 276
    # caracteres de UNA pieza; partido en dos clips con respiro, 230.
    "tienda_colores": {
        "duraciones": False,
        "label": "Tienda colores · 15s en dos clips",
        "voz": True,
        "segundos_clip": 8,
        # Medido sobre clips reales de Omni: locuta a 12-14 car/s (no a los
        # 17-18 de los formatos de Flow), así que en los ~7,3 s útiles de un
        # clip de 8 caben unos 100 caracteres. No más: en la toma lenta (12
        # car/s) 105 ya se sale y el generador se come el final del guion,
        # que es peor que quedarse corto — el silencio del último clip lo
        # aprovecha la flecha al carrito.
        "caracteres": 200,
        "caracteres_clip": 100,
        "partes": 2,
        "subtitulos": True,
        "flecha": True,
        "colores": True,
        # El formato vive de enseñar varios colores: con menos de tres
        # variantes no hay gancho (el vídeo se queda en "mira este pantalón")
        # y esa prenda es mejor grabarla con otro modo. Se cuenta la del
        # producto más las `Producto_N_Color_K` que trajo el ZIP.
        "minimo_variantes": 3,
        "imagen2": "prompt_mof10_tienda_colores_imagen2.md",
        # La misma imagen 1 con el pantalón en cada uno de los otros colores
        # (una por color, en Flow): son las fotos de los cortes de color.
        "imagen_color": "prompt_mof10_tienda_colores_imagen_color.md",
        # Variante del clip 1 en la que los cambios de color los hace Omni
        # con las fotos de cada color como ingredientes (sin subirlas a la
        # app). `{{DICE}}` y `{{COLORES}}` los rellena la pantalla del guion.
        "video_omni": "prompt_mof10_tienda_colores_video_omni.md",
        "video_omni2": "prompt_mof10_tienda_colores_video_omni2.md",
        "por_sexo": {
            "mujer": (
                "prompt_mof10_tienda_colores_imagen.md",
                "prompt_mof10_tienda_colores_guion.md",
            ),
        },
        "derivado": (),
    },
}


# La frase del pago a plazos, que va SUELTA y no dentro del ejemplo.
#
# En este nicho la voz la pone el propio vídeo (la persona habla), así que lo
# que diga el ejemplo es lo que va a decir: si el ejemplo promete plazos, el
# clip lo promete aunque esa prenda no los tenga. Y aquí no se puede arreglar
# después como en el POV BOF —allí la voz se genera aparte y se puede
# resintetizar—: habría que volver a generar el vídeo entero.
FRASE_PLAZOS = " Y si lo prefieres, puedes pagarlo a plazos."

# Con la frase metida, el ejemplo del curso se va a 214 caracteres y el propio
# prompt pide 180: dos órdenes que se contradicen, y ChatGPT resuelve por su
# cuenta —normalmente cortando la CTA del final, que es lo que hace vender—. La
# frase es NUESTRA, así que el aviso también: cuenta dentro del tope.
NOTA_PLAZOS = (
    "\n\nOJO: la frase del pago a plazos cuenta DENTRO del máximo de "
    "caracteres. Recorta las características para que el total no se pase — "
    "el ejemplo de arriba ya se pasa."
)


def _con_plazos(texto: str, plazos: bool) -> str:
    """Mete (o quita) la frase de los plazos en un prompt ya montado."""
    return texto.replace("{{FRASE_PLAZOS}}", FRASE_PLAZOS if plazos else "")


def _con_sexo(fichero: str, sexo: str, piezas: dict) -> str:
    texto = _limpio(fichero)
    for clave, valor in (piezas.get(sexo) or piezas[SEXO_DEFECTO]).items():
        texto = texto.replace("{{" + clave + "}}", valor)
    return texto


def _nota_duracion(guion: str, duracion: str) -> str:
    """Le avisa del recorte cuando el clip no es de 10 segundos."""
    if duracion_valida(duracion) == DURACION_DEFECTO:
        return guion
    return guion.rstrip() + NOTA_DURACION.format(**DURACIONES[duracion])


def _nota_plazos(guion: str, avisar: bool) -> str:
    """Avisa de que la frase de los plazos entra en el tope, si la lleva."""
    return guion.rstrip() + NOTA_PLAZOS if avisar else guion


# La época del año, en el idioma del prompt. Los del curso son JSON en inglés
# para Flow, así que la nota va en inglés: mezclar idiomas dentro del mismo
# prompt es pedirle al generador que elija.
#
# Es el mismo apaño que en el POV BOF (`pov_config.epoca_actual`), y por lo
# mismo: sin fecha, la calle sale con luz de agosto y manga corta en
# noviembre. Lo que NO puede tocar es la prenda: viene de la foto de
# referencia y es lo único fijo de la escena.
_MESES_EN = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)
_ESTACIONES_EN = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
}


# Qué prendas son "de temporada" en cada estación. Sirve de ejemplo para que
# Gemini distinga: sin esto, "si la prenda es de temporada" lo leía como "di
# que es perfecta para otoño" y lo metía en TODOS los guiones, también en unos
# vaqueros o una camiseta básica.
_PRENDAS_DE_TEMPORADA = {
    "otoño": "jerséis, chaquetas, cazadoras, gabardinas, botas o prendas de punto o pana",
    "invierno": "abrigos, plumíferos, jerséis gruesos, botas o bufandas",
    "primavera": "vestidos ligeros, chaquetas finas, blusas o gabardinas",
    "verano": "bikinis, bañadores, shorts, vestidos de tirantes o sandalias",
}


def nota_temporada_guion() -> str:
    """El apunte de la época para el prompt del GUION (que va en español).

    Es un permiso, no un encargo: por defecto NO se nombra la estación. Solo
    si la prenda es claramente de esta época, y una vez. Y con el freno del
    POV BOF: la época cambia CÓMO se habla de la prenda, nunca lo que es — sin
    él, un vestido de tirantes se volvía "ideal para el frío".
    """
    from src.nicho_pov_bof import config as pov_config

    estacion = pov_config.estacion_actual()
    ejemplos = _PRENDAS_DE_TEMPORADA.get(estacion, "")
    return (
        f"\n\nÚLTIMO APUNTE: el vídeo se publica en {pov_config.epoca_actual()}. "
        "Por defecto NO nombres la estación. Solo si la prenda es claramente "
        f"de {estacion} ({ejemplos}), puedes mencionarlo UNA vez y de pasada, "
        "nunca como gancho. Si es una prenda de todo el año (vaqueros, "
        "camisetas, vestidos de entretiempo…) o de otra estación, no digas "
        "nada de la época. Nunca le atribuyas tejidos, abrigo ni usos que no "
        "estén en la ficha."
    )


# Lo que se VE en cada estación. "Que parezca otoño" a secas no bastaba: la
# primera prueba salió con un jardín verde de pleno verano. A un generador de
# imagen hay que darle cosas que pintar, no una fecha.
_PISTAS_EN = {
    "autumn": "warm low-angle sunlight, trees turning yellow and orange, some fallen dry leaves on the ground",
    "winter": "cold soft light, bare trees, passers-by in coats and scarves in the background",
    "spring": "fresh bright green leaves, flowers in bloom, soft clear light",
    "summer": "strong bright sunlight, lush green trees, passers-by in light summer clothes",
}
_PISTAS_ES = {
    "autumn": "luz cálida y baja, árboles amarilleando y alguna hoja seca en el suelo",
    "winter": "luz fría, árboles sin hojas y gente con abrigo al fondo",
    "spring": "hojas verdes nuevas, flores y luz suave",
    "summer": "sol fuerte, árboles muy verdes y gente con ropa de verano",
}


def _estacion_hoy() -> tuple[int, str]:
    from datetime import datetime

    mes = datetime.now().month
    return mes, _ESTACIONES_EN[mes]


def nota_temporada() -> str:
    """El apunte de la época que se le pega al prompt de imagen."""
    mes, estacion = _estacion_hoy()
    return (
        "\n\nSEASON (mandatory): this is shot in "
        f"{_MESES_EN[mes - 1]} in Spain ({estacion}). Show it in the scene: "
        f"{_PISTAS_EN[estacion]}. The setting, the weather, the light and any "
        "clothing that is NOT in the reference image must match that time of "
        "year. The referenced garment stays exactly as it is: do not cover it, "
        "do not layer anything over it and do not change it for the season."
    )


def nota_temporada_imagen2() -> str:
    """Lo mismo para la SEGUNDA imagen, que se pide en español y en una frase.

    Se creía que la heredaba del chat —es la misma conversación que hizo la
    primera— y no: al cambiar de sitio, el generador cambiaba también de
    estación.
    """
    mes, estacion = _estacion_hoy()
    from src.nicho_pov_bof import config as pov_config

    return (
        f" Sigue siendo {pov_config._MESES[mes - 1]} en España, en "
        f"{pov_config.estacion_actual()}: que se note ({_PISTAS_ES[estacion]}). "
        "La prenda no cambia."
    )


def prompts_mof10(
    sexo: str = SEXO_DEFECTO, plazos: bool = False, modo: str = "",
    duracion: str = DURACION_DEFECTO,
) -> list[dict]:
    """Los estilos de 10s, cada uno con sus dos prompts ya en ese sexo.

    Con `modo` se devuelve SOLO el suyo: en la pantalla se trabaja un modo a la
    vez y enseñar los dos era invitar a copiar el prompt equivocado.
    """
    salida = []
    for clave, meta in ESTILOS_MOF10.items():
        if modo and clave != estilo_de_modo(modo):
            continue
        propios = (meta.get("por_sexo") or {}).get(sexo)
        if propios:
            # El texto es suyo, pero los marcadores se rellenan IGUAL: el del
            # selfie de hombre los lleva dentro (`{{EL_SUJETO_MAY}}`, `{{VOZ_DESC}}`)
            # para poder derivar el de mujer, y servirlo "literal" copiaba el
            # prompt con las llaves puestas — el operador lo pegaba así en
            # ChatGPT. Sustituir es inocuo en los que no tienen ninguno.
            imagen, guion = (_con_sexo(f, sexo, SEXOS_MOF10) for f in propios)
        elif not meta.get("imagen"):
            # Estilo que SOLO existe por sexo (los de marca personal son de
            # mujer): pedido para el otro, no hay texto que derivar. Antes esto
            # reventaba con KeyError y devolvía un 500 al pedir los prompts de
            # una carpeta de hombre sin decir el modo.
            continue
        else:
            imagen = _con_sexo(meta["imagen"], sexo, SEXOS_MOF10)
            guion = _con_sexo(meta["guion"], sexo, SEXOS_MOF10)
        # El tope de caracteres solo se toca en los estilos cuyo guion se
        # escribe fuera; en los de calle no hay marcador que rellenar.
        dur = duracion_valida(duracion) if meta.get("duraciones") else DURACION_DEFECTO
        tope = int(meta.get("caracteres") or 0)
        salida.append({
            "clave": clave,
            "label": meta["label"],
            # Con la época del año puesta: es lo que hace que la calle y la
            # luz sean de este mes y no de cuando se escribió el prompt.
            "imagen": _con_duracion(_con_plazos(imagen, plazos), dur, tope)
            + nota_temporada(),
            # La SEGUNDA imagen, en los formatos que se graban en dos partes.
            # Vacío en el resto: la pantalla solo pinta el botón si viene.
            "imagen2": (
                _limpio(meta["imagen2"]) + nota_temporada_imagen2()
                if meta.get("imagen2") else ""
            ),
            # Cuántos clips hay que generar y subir. 1 = como siempre.
            "partes": int(meta.get("partes") or 1),
            # Lo que cabe en CADA clip, para repartir el guion sin pasarse.
            "caracteres_clip": caracteres_por_clip(meta),
            # Si el montaje intercala los cortes de color al principio (los
            # genera la app, no el operador): la pantalla lo avisa.
            "colores": bool(meta.get("colores")),
            # Colores mínimos para que la prenda valga en este formato.
            "minimo_variantes": int(meta.get("minimo_variantes") or 0),
            # La plantilla para pedir en Flow la imagen 1 en otro color
            # (`{{COLOR}}` lo rellena la pantalla con cada variante).
            "imagen_color": _limpio(meta["imagen_color"]) if meta.get("imagen_color") else "",
            "video_omni": _limpio(meta["video_omni"]) if meta.get("video_omni") else "",
            "video_omni2": _limpio(meta["video_omni2"]) if meta.get("video_omni2") else "",
            "segundos_clip": int(meta.get("segundos_clip") or 0),
            "guion": _nota_plazos(
                _nota_duracion(
                    _con_duracion(_con_plazos(guion, plazos), dur, tope), dur,
                ),
                # Solo si ESTE guion lleva de verdad la frase y además su tope
                # lo escribe ChatGPT: en los demás, el aviso hablaría de una
                # frase que no está.
                plazos
                and "{{FRASE_PLAZOS}}" in guion
                and "{{CARACTERES}}" in guion,
            ) + (nota_temporada_guion() if "{{CARACTERES}}" in guion else ""),
            "derivado": sexo in meta["derivado"],
            # Lo que hay que saber AL PEGARLO, y que no se ve en el prompt:
            # si se adjunta el personaje de referencia, si la imagen entra
            # como ingrediente en vez de como frame inicial, y si el clip
            # sale hablado. Van con el prompt para que la pantalla los pinte
            # al lado del botón de copiar y no haya que recordarlos.
            "personaje": bool(meta.get("personaje")),
            "ingrediente": bool(meta.get("ingrediente")),
            "voz": bool(meta.get("voz", True)),
            # Si ESTE formato tiene de verdad versión con plazos. La frase va
            # dentro de lo que dice la persona, y el curso solo la publicó en
            # el del espejo: en los demás el botón copiaba el MISMO texto y
            # parecía que hacía algo.
            "plazos": "{{FRASE_PLAZOS}}" in imagen or "{{FRASE_PLAZOS}}" in guion,
            # Dos formatos del curso (selfie de mujer y gafas) llevan la
            # financiación METIDA en su ejemplo, así que la prometen SIEMPRE,
            # con el interruptor o sin él. Como la voz la pone el propio clip,
            # eso no se arregla después: hay que avisarlo antes de generar.
            "plazos_fijo": "pago a plazos" in _con_plazos(guion, False).lower(),
            # Si ese "guion" es en realidad el encargo para ChatGPT/DeepSeek
            # (lleva el tope de caracteres dentro) o el texto final que se pega
            # tal cual en Flow. Son DOS pasos distintos y confundirlos es
            # pegarle a Flow un "no me devuelvas nada".
            "escrito_fuera": "{{CARACTERES}}" in guion,
            # El tope de caracteres que se le pide al guion: el del formato si
            # lo tiene fijo, y si no el de la duración elegida.
            "caracteres": tope or DURACIONES[dur]["caracteres"],
            "duracion": dur,
            "duraciones": [
                {"clave": k, "label": v["label"], "segundos": v["segundos"]}
                for k, v in DURACIONES.items()
            ] if meta.get("duraciones") else [],
        })
    return salida


def prompt_imagen() -> str:
    return _limpio("prompt_imagen.md")


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------
# Mismo patrón que el resto del Programa 4: todo cuelga de TIKTOK_SHOP_AI_PRO.
DRIVE_UPLOAD_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_Ropa_Sin_Personas"


def video_dir() -> Path:
    """Dónde quedan los vídeos montados.

    Va al mismo Drive montado que el resto del Programa 4, bajo su propia
    carpeta. Si el mount no está (dev local), cae a `API_TEMP_ROOT`.
    """
    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    if raiz:
        destino = raiz / DRIVE_UPLOAD_ROOT / "videos"
    else:
        destino = Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "nicho_ropa" / "videos"
    destino.mkdir(parents=True, exist_ok=True)
    return destino
