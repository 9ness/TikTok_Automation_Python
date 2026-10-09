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
import re
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
    # Las otras dos subcategorías de Moda Mujer en su web (sep 2026). Son de
    # mujer —el sexo sale del prefijo— pero NO son ropa: van en su propio
    # catálogo para no colarse entre las carpetas de ropa de siempre, que
    # numeran igual ("Carpeta 3" hay en las tres).
    "mujer_zapatos_web": "👠 Mujer zapatos",
    "mujer_accesorios_web": "👜 Mujer accesorios",
}
# Qué catálogo de la pantalla es cada género de la web. "web" es el de ropa de
# siempre (mujer_web / hombre_web).
CATALOGO_DE_GENERO: dict[str, str] = {
    "mujer_zapatos_web": "zapatos",
    "mujer_accesorios_web": "accesorios",
}


def catalogo_de_genero(genero: str) -> str:
    """`web` / `zapatos` / `accesorios` / `muestras` / `tareas`."""
    if genero in CATALOGO_DE_GENERO:
        return CATALOGO_DE_GENERO[genero]
    for sufijo in ("muestras", "tareas", "temporada"):
        if genero.endswith(f"_{sufijo}"):
            return sufijo
    return "web"
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
    # Prendas y accesorios de TEMPORADA (oct 2026): lo más vendido del Q4
    # anterior según EchoTik, para Ana. Mismo funcionamiento que muestras.
    "mujer_temporada": "🎄 Mujer · temporada",
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
    # ---- MULTIMODO (sep 2026) --------------------------------------------
    # NUESTRO, pensado para que lo trabaje un agente: los formatos MUDOS de
    # 10s de su web (los de "solo música", los de camiseta, los de marca y los
    # Vintage de bolsos y botas) juntos en un menú, y en cada producto se elige
    # el que mejor le va. Así la cuenta no se ancla en un formato.
    #
    # `tipo` dice para qué producto vale (ver `TIPOS_MULTIMODO`): unas botas no
    # se graban frente al espejo de la camiseta. Ninguno habla — la música la
    # pone el operador al publicar, como en todos los mudos.
    #
    # Reusan el estilo de los de arriba cuando es el mismo formato (el de
    # marca_espejo, el maniquí…): así el prompt vive en UN fichero.
    "mm_espejo": {
        "desc": "Frente al espejo con el móvil tapando la cara, solo música. Cualquier prenda.",
        "label": "🪞 Espejo Solo Música",
        "estilo_mof10": "espejo_musica",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "ropa",
    },
    "mm_espejo_escenas": {
        "desc": "El personaje frente al espejo, varias escenas en un clip y filtro premium.",
        "label": "🎞️ Espejo Multi Escena",
        "estilo_mof10": "marca_espejo",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "ropa",
    },
    "mm_maniqui": {
        "desc": "La camiseta en un maniquí sin cabeza y dos manos estirándola. Sin persona.",
        "label": "🧍 Camiseta Maniquí",
        "estilo_mof10": "maniqui",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "camiseta",
    },
    "mm_sarcastica": {
        "desc": "Camiseta con frase, comprando sin mirar a cámara. Al publicar se le pone el sonido de risas.",
        "label": "😏 Camiseta Sarcástica",
        "estilo_mof10": "sarcastica_mujer",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "camiseta",
    },
    "mm_zapatillas_espejo": {
        "desc": "Agachada frente al espejo enseñando y tocando la zapatilla, solo música.",
        "label": "👟 Zapatillas Espejo Agachada",
        "estilo_mof10": "zapatillas_espejo",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "calzado",
    },
    "mm_zapatos_escenas": {
        "desc": "El personaje con los zapatos, varias escenas y filtro premium.",
        "label": "👢 Zapatos Multi Escena",
        "estilo_mof10": "marca_zapatos",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "calzado",
    },
    "mm_zapatos_pov": {
        "desc": "Los zapatos vistos desde arriba, en primera persona.",
        "label": "👀 Zapatos Vista POV",
        "estilo_mof10": "marca_pov",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "calzado",
    },
    # Los dos de 20s de su web (Moda Mujer · aleatorios). Son los ÚNICOS del
    # multimodo que HABLAN, pero la voz no la pone el clip: los dos clips de
    # 10s salen mudos y encima va un guion de punto de dolor escrito para ese
    # producto y locutado con Fish — la misma receta del POV BOF Largo, con
    # sus mismos textos quemados. Valen para zapatillas, zapatos y botas.
    "mm_zapatillas_pov20": {
        "desc": "Dos manos con manicura sujetando y enseñando el calzado, 20s: DOS clips de 10s mudos y voz de mujer (Fish) con guion de punto de dolor. Zapatillas, zapatos o botas.",
        "label": "🎙️ Zapatillas Vista POV 20s",
        "estilo_mof10": "zapatillas_pov20",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "calzado",
    },
    "mm_zapatillas_sentado20": {
        "desc": "Sentada, de rodillas abajo, con el calzado puesto, 20s: DOS clips de 10s mudos y voz de mujer (Fish) con guion de punto de dolor. Zapatillas, zapatos o botas.",
        "label": "🎙️ Zapatillas Vista Sentado 20s",
        "estilo_mof10": "zapatillas_sentado20",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "calzado",
    },
    "mm_botas_1": {
        "desc": "Vintage otoño: en el coche enseñando el par, con texto otoñal en la imagen.",
        "label": "🍂 Vintage Botas 1",
        "estilo_mof10": "vintage_botas_1",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "botas",
    },
    "mm_botas_2": {
        "desc": "Vintage otoño: segunda escena de botas, con texto otoñal en la imagen.",
        "label": "🍂 Vintage Botas 2",
        "estilo_mof10": "vintage_botas_2",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "botas",
    },
    "mm_botas_largas_1": {
        "desc": "Vintage otoño: botas altas en un columpio de porche, de cintura para abajo.",
        "label": "🍂 Vintage Botas Largas 1",
        "estilo_mof10": "vintage_botas_largas_1",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "botas",
    },
    "mm_botas_largas_2": {
        "desc": "Vintage otoño: segunda escena de botas altas.",
        "label": "🍂 Vintage Botas Largas 2",
        "estilo_mof10": "vintage_botas_largas_2",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "botas",
    },
    # Los dos que publicó el curso el 9/10/2026 (Marca Personal).
    "mm_botas_calle": {
        "desc": "Vintage otoño: las botas en una calle mojada con hojas, de rodillas para abajo.",
        "label": "🍂 Vintage Botas Calle",
        "estilo_mof10": "vintage_botas_calle",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "botas",
    },
    "mm_botas_espejo4": {
        "desc": "Vintage otoño: POV desde arriba frente al espejo, las botas y su reflejo.",
        "label": "🍂 Vintage Botas Frente Espejo",
        "estilo_mof10": "vintage_botas_espejo4",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "botas",
    },
    "mm_bolso_1": {
        "desc": "Vintage otoño: el bolso en el asiento del copiloto, con café y texto otoñal.",
        "label": "👜 Vintage Bolso 1",
        "estilo_mof10": "vintage_bolso_1",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "bolso",
    },
    "mm_bolso_2": {
        "desc": "Vintage otoño: segunda escena del bolso.",
        "label": "👜 Vintage Bolso 2",
        "estilo_mof10": "vintage_bolso_2",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "bolso",
    },
    "mm_bolso_3": {
        "desc": "Vintage otoño: tercera escena del bolso.",
        "label": "👜 Vintage Bolso 3",
        "estilo_mof10": "vintage_bolso_3",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "bolso",
    },
    # Los hablados de ropa de Moda Mujer · Aleatorios, traídos al multimodo
    # (oct 2026): GenAI Pro tiene Omni 1.1 a 1 crédito el clip y los vídeos
    # que hablan le dan más visitas a la cuenta que los mudos. Mismo estilo
    # (prompts, guion y montaje) que el de aleatorios; lo único que cambia es
    # `personaje_fijo`: en vez de una chica al azar, el personaje de la
    # cuenta (se antepone NOTA_PERSONAJE_FIJO y se pide adjuntarlo).
    "mm_habla_espejo": {
        "desc": "Frente al espejo HABLANDO de la prenda que lleva (voz en el clip).",
        "label": "🎙️ Espejo Hablado 10s",
        "estilo_mof10": "espejo",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "ropa",
        "personaje_fijo": True,
    },
    "mm_habla_selfie": {
        "desc": "Selfie con el móvil en la mano, hablando a cámara con la prenda puesta.",
        "label": "🎙️ Selfie Hablado 10s",
        "estilo_mof10": "movil",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "ropa",
        "personaje_fijo": True,
    },
    "mm_habla_calle_1": {
        "desc": "En la calle alguien la para y le pregunta por su outfit (diálogo del curso).",
        "label": "🎙️ Situación Real 1 10s",
        "estilo_mof10": "real_1",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "ropa",
        "personaje_fijo": True,
    },
    "mm_habla_calle_2": {
        "desc": "Como Situación Real 1, sentados en una terraza; habla primero el grupo.",
        "label": "🎙️ Situación Real 2 10s",
        "estilo_mof10": "real_2",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "ropa",
        "personaje_fijo": True,
    },
    "mm_habla_dividido": {
        "desc": "En la calle hablando sola a cámara de cuerpo entero: DOS clips (frente y espaldas), 15s.",
        "label": "🎙️ Calle Dividido 15s",
        "estilo_mof10": "calle_dividido",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "ropa",
        "personaje_fijo": True,
    },
    "mm_habla_colores": {
        "desc": "En una tienda nombra los colores y la prenda cambia en cada uno: DOS clips, 15s. Solo prendas con 3+ colores.",
        "label": "🎙️ Tienda Colores 15s",
        "estilo_mof10": "tienda_colores",
        "sexos": ("mujer",),
        "modalidad": "multimodo",
        "tipo": "ropa",
        "personaje_fijo": True,
    },
}


def personaje_fijo_del_modo(modo: str) -> bool:
    """Si en ESE modo va el personaje de la cuenta. Es del estilo (los de marca
    personal) o del modo (los hablados de aleatorios traídos al multimodo,
    que comparten estilo con los de chica al azar)."""
    meta = MODOS.get(modo) or {}
    estilo = ESTILOS_MOF10.get(meta.get("estilo_mof10", "")) or {}
    return bool(meta.get("personaje_fijo") or estilo.get("personaje_fijo"))
MODO_DEFECTO = "espejo"

# La vista de TODO el multimodo: no es un formato que se grabe, es "el vídeo
# que tenga hecho este producto, sea del formato que sea". La usan la pantalla
# (para descargar sin ir formato a formato), los contadores y el progreso de
# carpeta — una carpeta del multimodo se da por hecha una vez, no por formato.
MODO_MULTI = "multimodo"

# Qué producto admite cada formato del multimodo. `palabras` lo adivina por el
# título ya extraído (como `es_calzado`); lo que no case con nada es "ropa".
# Se mira en orden: "botas" antes que "calzado" porque una bota es las dos.
TIPOS_MULTIMODO: dict[str, dict] = {
    "bolso": {
        "label": "Bolso",
        "palabras": ("bolso", "bolsa", "cartera", "mochila", "bandolera", "tote", "clutch", "bag", "rinonera", "riñonera"),
    },
    "botas": {
        "label": "Botas",
        "palabras": ("bota", "botas", "botin", "botín", "botines", "boots", "boot"),
    },
    "calzado": {"label": "Zapatos o zapatillas", "palabras": (
        "zapato", "zapatos", "zapatilla", "zapatillas", "sandalia", "sandalias", "deportiva",
        "deportivas", "tacon", "tacón", "tacones", "mocasin", "mocasín", "mocasines",
        "bailarina", "bailarinas", "sneaker", "sneakers", "loafer", "loafers", "heels",
        "shoes", "calzado", "zueco", "zuecos", "chancla", "chanclas", "slippers",
    )},
    "camiseta": {
        "label": "Camiseta",
        "palabras": ("camiseta", "camisetas", "t-shirt", "tshirt", "tee"),
    },
    "gafas": {
        "label": "Gafas (sin formato mudo: se saltan)",
        "palabras": ("gafas", "gafa", "sunglasses", "lentes"),
    },
    "ropa": {"label": "Ropa", "palabras": ()},
}


def es_multimodo(modo: str) -> bool:
    """¿Ese modo es del multimodo (o su vista de todos)?"""
    return modo == MODO_MULTI or MODOS.get(modo, {}).get("modalidad") == "multimodo"


def modos_multimodo() -> list[str]:
    return [k for k, v in MODOS.items() if v.get("modalidad") == "multimodo"]


def clave_progreso(modo: str) -> str:
    """Bajo qué modo se apunta el progreso de carpeta. Los del multimodo van
    todos juntos: la carpeta está hecha cuando cada producto tiene SU vídeo,
    del formato que sea."""
    return MODO_MULTI if es_multimodo(modo) else modo_valido(modo)


def tipo_multimodo(titulo: str, carpeta: str = "") -> str:
    """Para qué formatos vale un producto, por el título (y el catálogo)."""
    plano = _sin_acentos(titulo or "")
    palabras = set(re.sub(r"[^a-z0-9]+", " ", plano).split())
    for clave in ("bolso", "gafas", "botas", "calzado", "camiseta"):
        pals = {_sin_acentos(p) for p in TIPOS_MULTIMODO[clave]["palabras"]}
        if palabras & pals:
            return clave
    genero, _ = partes_web(carpeta)
    if genero.endswith("_zapatos_web"):
        return "calzado"
    if genero.endswith("_accesorios_web"):
        return "bolso"
    return "ropa"
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
    # `y`: en la vista POV el zapato va en el CENTRO y el rótulo a la altura de
    # siempre (42%) le caía encima; arriba queda sobre el suelo o la ventana.
    # 3 s y no todo el vídeo: un rótulo fijo los 10 s sobre una cámara quieta
    # es lo que TikTok sanciona como «contenido estático» (2/10/2026, -4).
    "marca_pov": {"titulo": "AUTUMN", "bajada": "cozy season", "segundos": 3.0, "y": 0.2},
}

# La TEMPORADA de los rótulos y de la música. Los rótulos se queman al MONTAR,
# pero el vídeo se publica días después (las tandas van por delante de lo que
# se sube), así que se mira la fecha en que se PUBLICARÁ. Y nunca un mes en el
# texto: un «septiembre» publicado en octubre delata un vídeo viejo.
#
#   otoño     hasta el 14 nov (Halloween del 10 al 31 oct, con el doble de peso)
#   invierno  del 15 nov al 30 nov y del 7 ene a febrero — Black Friday se
#             vende ya con abrigo y bota
#   navidad   del 1 dic al 6 ene
#
# Fuera de eso (primavera, verano) se queda lo de otoño, que es lo que pide
# el formato: los Vintage son otoñales por diseño.
ADELANTO_PUBLICAR_DIAS = 3
TEMPORADAS_MULTIMODO = ("otono", "invierno", "navidad")


def temporada_multimodo(hoy=None, adelanto: int = ADELANTO_PUBLICAR_DIAS) -> str:
    """`"otono"`, `"invierno"` o `"navidad"` para el día en que se publicará."""
    import datetime as _dt

    dia = (hoy or _dt.date.today()) + _dt.timedelta(days=adelanto)
    md = (dia.month, dia.day)
    if md >= (12, 1) or md <= (1, 6):
        return "navidad"
    if (11, 15) <= md or md <= (2, 29):
        return "invierno"
    return "otono"


# Con cuántos vídeos subidos HOY se da el día por hecho (el objetivo son 10;
# algún día se quedan en 8 porque el enlace del producto no existe).
SUBIDAS_DIA_HECHO = 8


def etiqueta_temporada(dia) -> str:
    """La etiqueta que ve el operador en cada tanda: qué época toca ese día."""
    if dia.month == 10 and dia.day >= 10:
        return "🎃 Halloween"
    t = temporada_multimodo(dia, adelanto=0)
    if t == "navidad":
        return "🎄 Navidad"
    if t == "invierno":
        return "❄️ Invierno · Black Friday" if dia.month == 11 else "❄️ Invierno"
    return "🍂 Otoño"


def halloween_al_publicar(hoy=None) -> bool:
    """¿Se publicará en plena semana de Halloween? Para el RÓTULO (se quema al
    montar): un 🎃 publicado el 2 de noviembre ya llega tarde."""
    import datetime as _dt

    dia = (hoy or _dt.date.today()) + _dt.timedelta(days=ADELANTO_PUBLICAR_DIAS)
    return dia.month == 10 and dia.day >= 10


# Los de marca (espejo, zapatos, POV): el curso pone UN rótulo a todos, pero
# sesenta vídeos seguidos con «AUTUMN · cozy season» se leen como plantilla.
# Varias frases por temporada, la primera la del curso; invierno y Navidad con
# sus `emojis`, porque las hojas del adorno no pegan en enero.
_MARCA_FRASES = {
    "marca_espejo": {
        "otono": [("AUTUMN", "cozy season"), ("FALL EDIT", "outfit de temporada"),
                  ("AUTUMN LOOK", "cozy & chic"), ("NUEVA TEMPORADA", "otoño con estilo")],
        "invierno": [("WINTER", "cozy season", ("🤍", "❄️")),
                     ("WINTER LOOK", "abrígate con estilo", ("❄️", "❄️")),
                     ("COZY WINTER", "outfit de temporada", ("☕", "🤍"))],
        "navidad": [("HOLIDAY SEASON", "cozy & chic", ("✨", "🎄")),
                    ("HOLIDAY LOOK", "brilla estas fiestas", ("✨", "✨")),
                    ("WINTER WONDERLAND", "outfit de fiesta", ("❄️", "🎄"))],
    },
    "marca_zapatos": {
        "otono": [("AUTUMN BOOTS", "step into style"), ("FALL SHOES", "paso a paso"),
                  ("AUTUMN STEPS", "nueva temporada")],
        "invierno": [("WINTER BOOTS", "step into style", ("🤍", "❄️")),
                     ("WINTER STEPS", "listas para el frío", ("❄️", "❄️"))],
        "navidad": [("HOLIDAY BOOTS", "step into style", ("✨", "🎄")),
                    ("HOLIDAY STEPS", "brilla estas fiestas", ("✨", "✨"))],
    },
    "marca_pov": {
        "otono": [("AUTUMN", "cozy season"), ("FALL VIBES", "paso a paso"),
                  ("COZY SEASON", "mi par favorito")],
        "invierno": [("WINTER", "cozy season", ("☕", "❄️")),
                     ("COZY WINTER", "mi par favorito", ("🤍", "❄️"))],
        "navidad": [("HOLIDAY SEASON", "cozy vibes", ("✨", "🎄")),
                    ("HOLIDAY STEPS", "brilla estas fiestas", ("✨", "✨"))],
    },
}


def _frases(lista: list) -> list[dict]:
    return [
        {"titulo": f[0], "bajada": f[1], **({"emojis": f[2]} if len(f) > 2 else {})}
        for f in lista
    ]


_MARCA_HALLOWEEN = [
    ("SPOOKY SEASON", "cozy & chic", ("🎃", "🍂")),
    ("HALLOWEEN LOOK", "outfit de temporada", ("🎃", "🖤")),
    ("SPOOKY VIBES", "otoño con un toque oscuro", ("🦇", "🎃")),
]
for _clave, _por in _MARCA_FRASES.items():
    TEXTO_MARCA[_clave]["variantes"] = _frases(_por["otono"])
    TEXTO_MARCA[_clave]["halloween"] = _frases(_MARCA_HALLOWEEN)
    TEXTO_MARCA[_clave]["temporadas"] = {
        "invierno": _frases(_por["invierno"]), "navidad": _frases(_por["navidad"]),
    }

# Los Vintage del multimodo (bolsos y botas). La web pide el rótulo otoñal
# DENTRO de la imagen (Nano Banana), y Kling lo deforma a mitad de clip —salió
# "ESENCIALES DE OTOÑO" convertido en "POEAOP"—. Se quita del prompt de imagen
# (`sin_texto_en_imagen`) y lo pone el montaje, como en los de marca: siempre
# legible y con sus emojis. Varias frases, elegidas por prenda para que dos
# vídeos seguidos no digan lo mismo. Sin `grado`: la foto ya trae su filtro de
# otoño y oscurecerla otra vez la apagaba. Se ve 3 s: entero (como en las
# imágenes de referencia) TikTok lo sancionó como «contenido estático».
_VINTAGE_BOLSO = [
    ("Otoño esencial", "colección de temporada"),
    ("Colección de Otoño", "elegancia de temporada"),
    ("Autumn Essentials", "cozy season"),
    ("Esencia de Otoño", "nueva temporada"),
    ("Autumn Mood", "tu bolso de temporada"),
    ("Otoño en el coche", "café, hojas y tu bolso"),
    ("Fall Favorites", "must have de otoño"),
    ("Hojas y café", "el bolso que combina con todo"),
]
_VINTAGE_BOTAS = [
    ("Autumn Edit", "step into style"),
    ("Nueva Colección", "otoño paso a paso"),
    ("Otoño esencial", "paso a paso"),
    ("Autumn Boots", "cozy season"),
    ("Pasos de Otoño", "botas de temporada"),
    ("Fall Favorites", "must have de otoño"),
    ("Otoño a tus pies", "nueva temporada"),
    ("Boots Season", "cozy vibes"),
]
# Frases de Halloween: se suman a las de otoño SOLO si el vídeo se publica en
# su semana (`halloween_al_publicar`), con sus propios emojis.
_VINTAGE_HALLOWEEN = [
    ("Spooky Season", "look de Halloween", ("🎃", "🎃")),
    ("Halloween Vibes", "otoño con un toque oscuro", ("🎃", "👻")),
    ("Noche de Halloween", "el complemento perfecto", ("🦇", "🎃")),
]
# Invierno y Navidad SUSTITUYEN a las de otoño. «Idea de regalo» sí, «regalo»
# a secas no: suena a que viene algo gratis y eso es promoción incoherente.
_VINTAGE_BOLSO_INVIERNO = [
    ("Winter Essentials", "cozy season", ("🤍", "❄️")),
    ("Esenciales de invierno", "tu bolso para el frío", ("☕", "❄️")),
    ("Winter Mood", "abrigo, café y tu bolso", ("☕", "🤍")),
    ("Nueva temporada", "invierno con estilo", ("❄️", "❄️")),
    ("Cozy Winter", "el bolso que combina con todo", ("🤍", "🤍")),
    ("Winter Edit", "must have de invierno", ("❄️", "✨")),
]
_VINTAGE_BOTAS_INVIERNO = [
    ("Winter Boots", "cozy season", ("🤍", "❄️")),
    ("Pasos de invierno", "calentitas y con estilo", ("❄️", "❄️")),
    ("Winter Edit", "step into style", ("❄️", "✨")),
    ("Botas de temporada", "listas para el frío", ("☕", "❄️")),
    ("Cozy Winter", "paso a paso", ("🤍", "🤍")),
    ("Boots Season", "winter vibes", ("❄️", "🤍")),
]
_VINTAGE_BOLSO_NAVIDAD = [
    ("Holiday Season", "brilla estas fiestas", ("✨", "🎄")),
    ("Navidad con estilo", "una idea de regalo que acierta", ("🎄", "🎁")),
    ("Winter Wonderland", "tu bolso de fiestas", ("❄️", "✨")),
    ("Ideas de regalo", "para ella", ("🎁", "🎁")),
    ("Cozy Christmas", "café, luces y tu bolso", ("☕", "🎄")),
]
_VINTAGE_BOTAS_NAVIDAD = [
    ("Holiday Season", "step into style", ("✨", "🎄")),
    ("Navidad a tus pies", "una idea de regalo", ("🎄", "🎁")),
    ("Winter Wonderland", "botas de fiesta", ("❄️", "✨")),
    ("Cozy Christmas", "paso a paso", ("☕", "🎄")),
    ("Holiday Boots", "brilla estas fiestas", ("✨", "✨")),
]


for _claves, _otono, _invierno, _navidad in (
    (("vintage_bolso_1", "vintage_bolso_2", "vintage_bolso_3"),
     _VINTAGE_BOLSO, _VINTAGE_BOLSO_INVIERNO, _VINTAGE_BOLSO_NAVIDAD),
    (("vintage_botas_1", "vintage_botas_2", "vintage_botas_largas_1", "vintage_botas_largas_2",
     "vintage_botas_calle", "vintage_botas_espejo4"),
     _VINTAGE_BOTAS, _VINTAGE_BOTAS_INVIERNO, _VINTAGE_BOTAS_NAVIDAD),
):
    for _clave in _claves:
        TEXTO_MARCA[_clave] = {
            "variantes": _frases(_otono),
            "halloween": _frases(_VINTAGE_HALLOWEEN),
            "temporadas": {"invierno": _frases(_invierno), "navidad": _frases(_navidad)},
            # Solo al principio: fijo los 10 s se sancionó como «contenido
            # estático / texto animado» (botas Vintage, 2/10/2026).
            "segundos": 3.0, "grado": False, "quitar_de_imagen": True,
        }


# La música la pone el operador en TikTok al publicar (los vídeos salen
# mudos). Para no pensarla vídeo a vídeo, cada formato trae VARIOS estilos que
# le van, cada uno con sus búsquedas para la biblioteca de sonidos de TikTok;
# a cada producto le toca un estilo y una búsqueda (por semilla), así dos
# vídeos seguidos no suenan igual. Con un estilo por formato, una tanda de
# bolsos y botas era toda «jazz vintage». En inglés porque así están
# etiquetados los sonidos en TikTok. Lo de temporada se suma aparte.
def _m(estilo: str, *busca: str) -> dict:
    return {"estilo": estilo, "busca": list(busca)}


_MUSICA_VINTAGE_BOLSO = [
    _m("jazz o soul vintage", "vintage jazz", "70s soul aesthetic", "motown soul", "old vinyl aesthetic"),
    _m("canción francesa de café", "old french song", "chanson française", "parisian cafe music"),
    _m("bossa nova suave", "bossa nova vintage", "bossa nova cafe", "brazilian jazz chill"),
    _m("pop de los 60 con encanto", "60s girl group", "retro 60s pop", "vintage love song"),
]
_MUSICA_VINTAGE_BOTAS = [
    _m("soul o funk de los 70", "70s soul aesthetic", "retro funk groove", "old vinyl aesthetic"),
    _m("country y folk vintage", "vintage country aesthetic", "cowboy aesthetic song", "western aesthetic"),
    _m("folk rock de carretera", "folk rock 70s", "road trip indie folk", "acoustic road trip"),
    _m("blues y guitarra vintage", "blues guitar vintage", "slow blues aesthetic", "vintage rock ballad"),
]
MUSICA_MULTIMODO: dict[str, list[dict]] = {
    "espejo_musica": [
        _m("pop pegadizo de tendencia, para enseñar el outfit",
           "outfit check", "fit check trend", "outfit of the day song", "fashion trending sound"),
        _m("pop con actitud, de pasarela casera",
           "main character energy", "confident walk song", "catwalk sound", "girly pop aesthetic"),
        _m("dance o house ligero de get ready",
           "get ready with me song", "pop dance trend", "house music get ready", "party getting ready"),
    ],
    "marca_espejo": [
        _m("indie suave y acogedor, vibra de vlog", "aesthetic vlog music", "soft indie", "bedroom pop chill"),
        _m("folk acústico tranquilo", "indie folk acoustic", "soft guitar aesthetic", "slow morning vlog"),
        _m("dream pop envolvente", "dreamy indie pop", "dream pop aesthetic", "ethereal pop"),
    ],
    "maniqui": [
        _m("beat minimal de desfile", "runway beat", "fashion show music", "minimal house fashion"),
        _m("deep house de tienda chic", "deep house fashion", "boutique lounge music", "chic minimal beat"),
        _m("techno elegante", "techno runway", "dark minimal techno fashion", "model walk beat"),
    ],
    "sarcastica_mujer": [
        _m("sonido de humor con risas (el formato lo pide)",
           "sitcom laugh", "funny laugh sound", "sarcastic meme sound", "laugh track", "awkward moment sound"),
    ],
    "zapatillas_espejo": [
        _m("hip hop chill con ritmo marcado", "sneaker check", "chill beat fashion", "boom bap chill"),
        _m("lo-fi urbano", "lofi hip hop chill", "city walk lofi", "street style beat"),
        _m("r&b suave", "rnb chill vibe", "smooth rnb aesthetic", "late night rnb"),
    ],
    "marca_zapatos": [
        _m("acústica cálida y cinematográfica", "cinematic acoustic", "acoustic guitar warm", "folk walk music"),
        _m("piano suave de película", "piano cinematic soft", "emotional piano aesthetic", "soft piano walk"),
        _m("indie folk de paseo", "indie folk walk", "happy acoustic stroll", "sunny indie folk"),
    ],
    "marca_pov": [
        _m("jazz de cafetería, tranquilo", "coffee shop jazz", "sunday morning jazz", "piano jazz morning"),
        _m("lo-fi jazz", "lofi jazz", "jazzhop chill", "study jazz lofi"),
        _m("bossa nova de cafetería", "bossa nova cafe", "cafe bossa nova", "brazilian jazz chill"),
    ],
}
for _clave in ("vintage_bolso_1", "vintage_bolso_2", "vintage_bolso_3"):
    MUSICA_MULTIMODO[_clave] = _MUSICA_VINTAGE_BOLSO
for _clave in ("vintage_botas_1", "vintage_botas_2", "vintage_botas_largas_1", "vintage_botas_largas_2",
     "vintage_botas_calle", "vintage_botas_espejo4"):
    MUSICA_MULTIMODO[_clave] = _MUSICA_VINTAGE_BOTAS
# Se SUMA una a las búsquedas del estilo que toque: así una parte de los
# vídeos suena a la época y el resto no se queda anclado en ella.
_MUSICA_TEMPORADA = {
    "otono": ["autumn vibes", "fall aesthetic", "cozy autumn", "autumn lofi"],
    "invierno": ["winter vibes", "cozy winter", "snow day aesthetic", "winter lofi"],
    "navidad": ["christmas aesthetic", "christmas jazz", "christmas lofi", "cozy christmas"],
}
_MUSICA_HALLOWEEN = ["spooky season", "halloween aesthetic", "witchy vibes"]


def musica_de(modo: str, semilla: str = "", hoy=None) -> dict:
    """`{busqueda, alternativas, estilo}` para ponerle sonido en TikTok.

    `{}` si el formato no tiene sugerencia (los que hablan no la necesitan).
    Se calcula al LISTAR, que es cuando se publica: la temporada es la de hoy.
    """
    import hashlib

    estilos = MUSICA_MULTIMODO.get(estilo_de_modo(modo)) if modo else None
    if not estilos:
        return {}
    h = hashlib.sha1(("musica:" + str(semilla or "")).encode("utf-8")).digest()
    meta = estilos[h[1] % len(estilos)]
    # UNA de temporada (y una de Halloween en su semana): con todas, la mitad
    # de los vídeos acababa con «autumn vibes».
    temporada = _MUSICA_TEMPORADA[temporada_multimodo(hoy, adelanto=0)]
    busca = list(meta["busca"]) + [temporada[h[2] % len(temporada)]]
    if es_halloween(hoy):
        busca.append(_MUSICA_HALLOWEEN[h[3] % len(_MUSICA_HALLOWEEN)])
    i = h[0] % len(busca)
    return {
        "busqueda": busca[i],
        "alternativas": busca[:i] + busca[i + 1:],
        "estilo": meta["estilo"],
    }


def _turnos(items: list, clave) -> list:
    """Reparte por turnos: uno de cada grupo, luego el segundo de cada uno…

    Los grupos van en el orden en que aparece su primer elemento y cada grupo
    conserva su orden interno.
    """
    grupos: dict = {}
    for it in items:
        grupos.setdefault(clave(it), []).append(it)
    salida: list = []
    listas = list(grupos.values())
    while any(listas):
        for lista in listas:
            if lista:
                salida.append(lista.pop(0))
    return salida


def orden_para_publicar(videos: list[dict]) -> list[dict]:
    """El orden de las tandas del multimodo: lo subido delante y lo que falta
    MEZCLADO.

    Se montan por carpetas (diez bolsos seguidos, luego diez botas…) y
    publicarlos así ancla la cuenta en un formato. Lo pendiente se alterna por
    tipo (ropa, bolso, botas…) y, dentro de cada tipo, por formato. Lo ya
    subido va primero y en el orden en que se subió: así las tandas cerradas
    no cambian cuando entran vídeos nuevos.
    """
    subidos = sorted(
        (v for v in videos if v.get("uploaded")),
        key=lambda v: (int(v.get("uploaded_at") or 0), int(v.get("video_listo_at") or 0)),
    )
    # Por la PRIMERA vez que se montó: un vídeo rehecho no pierde su puesto.
    pendientes = sorted(
        (v for v in videos if not v.get("uploaded")),
        key=lambda v: int(v.get("primer_listo_at") or v.get("video_listo_at") or 0),
    )
    por_tipo = _turnos(
        pendientes, lambda v: MODOS.get(v.get("formato") or "", {}).get("tipo") or "otro",
    )
    # Dentro del turno de cada tipo, que tampoco se repita el formato: se
    # rehace el reparto tipo a tipo con sus formatos alternados.
    grupos: dict = {}
    for v in pendientes:
        tipo = MODOS.get(v.get("formato") or "", {}).get("tipo") or "otro"
        grupos.setdefault(tipo, []).append(v)
    alternados = {
        tipo: _turnos(lista, lambda v: v.get("formato") or "") for tipo, lista in grupos.items()
    }
    mezclado = []
    for v in por_tipo:
        tipo = MODOS.get(v.get("formato") or "", {}).get("tipo") or "otro"
        mezclado.append(alternados[tipo].pop(0))
    return subidos + mezclado


def es_halloween(hoy=None) -> bool:
    """¿Estamos en la ventana en que tienen sentido las frases de Halloween?"""
    import datetime as _dt

    hoy = hoy or _dt.date.today()
    return (hoy.month == 10 and hoy.day >= 10) or (hoy.month == 11 and hoy.day == 1)

_PARRAFO_TEXTO_IMAGEN = re.compile(
    r"Añade directamente sobre la fotografía.*?integrado en la (?:imagen|fotografía)\.\s*", re.S,
)


def sin_texto_en_imagen(prompt: str) -> str:
    """El prompt de imagen sin el párrafo que pide el rótulo otoñal."""
    return _PARRAFO_TEXTO_IMAGEN.sub("", prompt)


# El prompt de MOVIMIENTO de los Vintage pide que "el texto se mantenga
# estático": con la foto ya sin rótulo, Kling lo tomaba como orden de poner
# uno y se inventaba letras sin sentido. Se cambia por la prohibición.
_FRASE_TEXTO_VIDEO = re.compile(
    r"(?:El [Tt]exto se mantiene est[aá]tico y fijo durante todo el clip\. No desaparece\."
    r"|El [Tt]exto de la pantalla no desaparece, queda fijado\.)\s*",
)
SIN_TEXTO_VIDEO = (
    "No aparece ningún texto, letra ni rótulo en pantalla. "
    "El producto no se mueve solo ni cambia de forma, color ni tamaño. "
)


def sin_texto_en_video(prompt: str) -> str:
    """El prompt de movimiento sin pedir texto y prohibiéndolo."""
    return _FRASE_TEXTO_VIDEO.sub(SIN_TEXTO_VIDEO, prompt)


# Remate para TODOS los formatos mudos del multimodo: el rótulo (si lo lleva)
# lo pone el montaje, así que cualquier letra que meta el generador es basura
# — Kling se inventó "PIAPIODMIRMA" sobre un bolso. Va al final del prompt de
# movimiento, que es lo último que lee el generador.
NOTA_SIN_TEXTO_VIDEO = (
    "\n\nIMPORTANTE: vídeo limpio, sin ningún texto sobreimpreso. Sin letras, "
    "palabras, títulos, rótulos, subtítulos, carteles, logotipos, marcas de "
    "agua ni tipografía de ningún tipo en ningún momento del clip. Si la "
    "imagen inicial no tiene texto, el vídeo tampoco."
)

_MANO_BOLSO = (
    "Para que el clip tenga movimiento: una mano de mujer con manicura cuidada "
    "entra por el lateral del plano, se apoya en el bolso, lo acaricia despacio "
    "y juega con el asa, y se retira por el mismo lado. La mano nunca pasa por "
    "delante de la cámara ni tapa el bolso, y no gesticula en el aire: siempre "
    "está tocando el bolso. Solo una mano, con cinco dedos. El bolso no cambia "
    "de forma, color, tamaño ni posición y no se mueve solo."
)
_MANO_BOTA = (
    "Para que el clip tenga movimiento: la mano que sujeta el zapato lo gira "
    "despacio para enseñarlo por los dos lados y lo acerca un poco a la "
    "cámara. El zapato no cambia de forma, color ni diseño y no aparece "
    "ningún zapato nuevo."
)

_DE_FRENTE_AL_ESPEJO = (
    "Está SIEMPRE de frente al espejo con el móvil en la mano tapándole parte "
    "de la cara; nunca se la ve de espaldas ni sin el móvil. El móvil va "
    "siempre sujeto en su mano: nunca se queda flotando ni suspendido en el "
    "aire."
)
_PIERNAS_BOTA = (
    "Para que el clip tenga movimiento: ella balancea despacio el pie de la "
    "pierna cruzada, descruza y vuelve a cruzar las piernas con calma y pasa "
    "una mano por la caña de la bota. Solo dos botas, las dos puestas; no "
    "cambian de forma, color, altura ni diseño."
)

# Lo que Kling hace mal o se queda corto en cada formato, dicho al final del
# prompt de movimiento (antes de la nota sin texto).
_SIN_VOZ_CLIP = (
    "Nadie habla ni se oye ninguna voz: el clip va sin diálogo (la voz se "
    "pone después)."
)

EXTRA_VIDEO_MULTIMODO = {
    # Los de 20s con voz de Fish. El «gesticula con la mano» del curso, con
    # dos manos sujetando un zapato, es lo que hace que Kling/Omni lo suelten,
    # lo deformen o saquen un tercer zapato; y un clip quieto es sanción
    # (-4 puntos por casi-foto). Se dice qué se mueve y qué no.
    "mm_zapatillas_pov20": (
        "Las manos sujetan el calzado y lo giran despacio para enseñarlo por "
        "los dos lados, acercándolo un poco a la cámara, con la cámara "
        "moviéndose un poco como un móvil en mano. Solo dos manos, con cinco "
        "dedos cada una, y nunca sueltan el calzado. El calzado no cambia de "
        "forma, color, tamaño ni diseño y no aparece ningún zapato nuevo. "
        + _SIN_VOZ_CLIP
    ),
    "mm_zapatillas_sentado20": (
        "Ella sigue sentada y mueve los pies con naturalidad: gira un poco un "
        "pie para enseñar el lateral del calzado, da un par de golpecitos con "
        "la punta en el suelo y cruza y descruza los tobillos, mientras la "
        "cámara se mueve un poco como un móvil en mano. Solo dos piernas y dos "
        "pies, con el calzado puesto en los dos; no cambia de forma, color ni "
        "diseño y no aparece ningún zapato nuevo. No se le ve la cara ni el "
        "cuerpo de las rodillas para arriba. " + _SIN_VOZ_CLIP
    ),
    # Los bolsos son un bodegón: con el «movimiento sutil» del curso salía
    # un temblor y poco más, y TikTok penaliza el contenido estático.
    "mm_bolso_1": _MANO_BOLSO,
    "mm_bolso_2": _MANO_BOLSO,
    "mm_bolso_3": _MANO_BOLSO,
    # En estos la imagen ya trae la mano sujetando el otro zapato.
    "mm_botas_1": _MANO_BOTA,
    "mm_botas_2": _MANO_BOTA,
    # Medido sobre lo montado (sep 2026): las botas altas eran lo más quieto
    # después de los bolsos — una chica de cintura para abajo sin moverse.
    "mm_botas_largas_1": _PIERNAS_BOTA + " Se mece suavemente en el columpio.",
    "mm_botas_largas_2": _PIERNAS_BOTA,
    # Los dos de 9/10: su «mueve sus piernas como enseñando las botas» ya va
    # en el prompt; se dice qué NO puede pasar.
    "mm_botas_calle": (
        "Solo dos piernas y dos botas, las dos puestas; no cambian de forma, "
        "color, altura ni diseño. Las hojas y los charcos del suelo se quedan "
        "donde están."
    ),
    "mm_botas_espejo4": (
        "Abajo, las dos botas reales vistas desde arriba; arriba, su reflejo en "
        "el espejo, que se mueve igual que ellas. Solo dos botas reales y dos "
        "en el reflejo, iguales entre sí; no cambian de forma, color ni diseño."
    ),
    # Lo que Kling se inventa en calzado, y el clip ya no vale: en POV el pie
    # descalzo acababa calzado con un tercer zapato; en el espejo entraba una
    # pierna real por delante, la chica acercaba la zapatilla a cámara o el
    # móvil se volvía zapato. Se dice cuántos pies y zapatos hay y se la deja
    # QUIETA: "no añadas" no basta, y el «enseña a cámara» del curso lo provoca.
    "mm_zapatos_pov": (
        "Los pies se quedan exactamente como en la imagen inicial: el pie "
        "descalzo sigue descalzo y no aparece ningún zapato nuevo; en todo el "
        "clip hay los mismos zapatos que en la imagen."
    ),
    # Kling giraba a la chica y la enseñaba de espaldas «haciéndose» el selfie
    # (imposible frente a un espejo): dos de cuatro clips de ropa rechazados.
    "mm_espejo": _DE_FRENTE_AL_ESPEJO,
    "mm_espejo_escenas": _DE_FRENTE_AL_ESPEJO,
    "mm_zapatillas_espejo": (
        "Selfie en el espejo casi estático: ella se queda agachada en la misma "
        "postura, con los dos pies apoyados en el suelo, y con la mano libre "
        "toca despacio los cordones de la zapatilla DELANTERA (la del pie más "
        "cercano al espejo), sin "
        "quitársela. No levanta el pie ni acerca la zapatilla a la cámara. El "
        "móvil sigue siendo el mismo móvil en su mano. Todo ocurre DENTRO del "
        "reflejo del espejo: delante del espejo no aparece ninguna pierna, pie "
        "ni zapato. Hay exactamente dos zapatillas en todo el clip, las dos en "
        "sus pies. La zapatilla de atrás no se toca nunca: la mano no pasa por "
        "ella ni por el tobillo de ese pie y la zapatilla se queda quieta en el "
        "suelo. La mano no agarra el talón ni tira de ninguna zapatilla: las "
        "dos conservan su forma y su color en todo el clip."
    ),
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
# guion tiene que nombrar, en ese orden. `pose_color` y `espalda_imagen` van
# en las imágenes de color y de espaldas: antes decían "pantalón" y
# "bolsillos traseros" fuera cual fuera la prenda, y una chaqueta salía mal.
# En TODAS la chica se la está PONIENDO, a MEDIAS, como en los virales (Drive
# del operador): el pantalón subiendo desde el muslo, el jersey recogido en el
# pecho enseñando el top de debajo, la chaqueta resbalando por los brazos, el
# vestido recogido en la cintura sobre las mallas. `cuerpo_imagen`: el cuerpo
# que realza ESA prenda (caderas y curvas en un pantalón, cintura en un
# vestido), como en los virales. Con "se la coloca" o
# "sujeta los delanteros" salía posando, y no es el formato.
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
        "cuerpo_imagen": "young slim-waisted figure with curvy, well-defined hips and a rounded, toned silhouette and long legs, the kind of body that shows off how trousers fit at the waist and hips",
        "pose_color": "poniéndose el pantalón, a mitad de muslo, con las mallas negras debajo",
        "espalda_imagen": (
            "con las manos apoyadas en la cintura o metidas en los bolsillos traseros, y la cabeza girada un poco por encima del hombro mirando a cámara. La prenda se ve entera por detrás (cintura, bolsillos traseros y largo)"
        ),
    },
    "punto": {
        "label": "Jersey, chaleco o camiseta",
        "palabras": (
            "jersey", "sueter", "suéter", "sweater", "punto", "chaleco", "camiseta",
            "top", "blusa", "camisa", "polo", "sudadera",
        ),
        "gesto": "está de pie, de frente, con la prenda ya metida por la cabeza pero todavía subida y recogida a la altura del pecho, dejando ver el top blanco de debajo, y tira de ella hacia abajo con las dos manos, como quien se la está poniendo",
        "final_gesto": "termina de bajársela, la estira sobre la cadera y se queda de pie, relajada, mirando a cámara",
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
        "pose_imagen": "she is in the middle of putting the garment on: it is already over her head and arms, but it is still pulled up and bunched at her chest, so her plain white crop top shows underneath, and she is pulling it down with both hands; the neckline, sleeves and knit are clearly visible.",
        "manos_imagen": "both hands gripping the bunched-up hem at chest height, pulling it down",
        "ropa_base": "Under the referenced garment she wears a plain white fitted crop top (visible because the garment is still pulled up), and below plain wide-leg blue jeans and simple white sneakers.",
        "cuerpo_imagen": "young slim, toned figure with a defined waist, so the knit drapes nicely over the body",
        "pose_color": "poniéndose la prenda, todavía subida y recogida en el pecho, enseñando el top blanco, y tirando de ella hacia abajo con las dos manos",
        "espalda_imagen": (
            "con los brazos relajados a los lados, y la cabeza girada un poco por encima del hombro mirando a cámara. La prenda se ve entera por detrás (hombros, espalda y bajo)"
        ),
    },
    "abierta": {
        "label": "Chaqueta, cárdigan o abrigo",
        "palabras": (
            "cardigan", "cárdigan", "chaqueta", "abrigo", "blazer", "americana",
            "kimono", "trench", "gabardina", "chaquetón", "capa",
        ),
        "gesto": "está de pie, de frente, con la prenda a medio poner, resbalando por los brazos, y con las dos manos en el cuello se la sube a los hombros, como quien se la está poniendo",
        "final_gesto": "se la asienta en los hombros, abre los delanteros hacia los lados para enseñarla y se queda de pie, relajada, mirando a cámara",
        "detalle_1": (
            "Plano medio, del pecho a las caderas, cámara fija. Abre los dos brazos "
            "en cruz para que se vea la amplitud de la prenda y los baja despacio"
        ),
        "detalle_2": (
            "Primer plano del pecho y la manga, la cámara se acerca. Pasa la mano por "
            "el tejido y por la manga para que se vean de cerca el tejido, el grosor "
            "y los detalles (cuello, botones, cinturón si los tiene)"
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
        "pose_imagen": "she is in the middle of putting the garment on: it is still half off her shoulders, slipping down her upper arms, and with both hands at the collar she is pulling it up onto her shoulders; the front, collar and fabric are clearly visible.",
        "manos_imagen": "both hands at the collar, pulling the garment up onto her shoulders",
        "ropa_base": "Under the referenced garment she wears a plain white fitted t-shirt, and below plain wide-leg blue jeans and simple white sneakers.",
        "cuerpo_imagen": "young tall, slender and elegant figure with defined shoulders and a slim waist, so the jacket hangs beautifully",
        "pose_color": "poniéndose la prenda, todavía resbalando por los brazos, y subiéndosela a los hombros con las dos manos en el cuello",
        "espalda_imagen": (
            "con los brazos relajados a los lados, y la cabeza girada un poco por encima del hombro mirando a cámara. La prenda se ve entera por detrás (hombros, espalda, mangas y largo)"
        ),
    },
    "capucha": {
        "label": "Sudadera con capucha o cremallera",
        "palabras": ("capucha", "hoodie", "cremallera", "zip", "chandal", "chándal"),
        "gesto": "está de pie, de frente, con la prenda abierta a medio poner, resbalando por los brazos, y con las dos manos en el cuello se la sube a los hombros, dejando ver la cremallera y la capucha, como quien se la está poniendo",
        "final_gesto": "se la asienta en los hombros, sube la cremallera hasta arriba de un tirón y se queda de pie, relajada, mirando a cámara",
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
        "pose_imagen": "she is in the middle of putting the garment on: it is open and still half off her shoulders, slipping down her upper arms, and with both hands at the collar she is pulling it up onto her shoulders; the hood, zip and fabric are clearly visible.",
        "manos_imagen": "both hands at the collar, pulling the open garment up onto her shoulders",
        "ropa_base": "Under the referenced garment she wears a plain white fitted top, and below plain black leggings and simple white sneakers.",
        "cuerpo_imagen": "young slim, fit and sporty figure with a defined waist",
        "pose_color": "poniéndose la prenda abierta, todavía resbalando por los brazos, y subiéndosela a los hombros con las dos manos en el cuello",
        "espalda_imagen": (
            "con los brazos relajados a los lados y la capucha bajada, y la cabeza girada un poco por encima del hombro mirando a cámara. La prenda se ve entera por detrás (capucha, espalda y bajo)"
        ),
    },
    "mono": {
        "label": "Mono o vestido",
        "palabras": ("mono", "jumpsuit", "vestido", "peto", "conjunto"),
        "gesto": "está de pie, de frente, con la parte de arriba ya puesta y la de abajo todavía subida y recogida en la cintura, por encima de unas mallas cortas negras, y tira de ella hacia abajo con las dos manos, como quien se la está poniendo",
        "final_gesto": "termina de bajársela, la prenda cae entera hasta el bajo, se la coloca en la cintura y se queda de pie, mirando a cámara",
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
        "pose_imagen": "she is in the middle of putting the garment on: the top part is already on, but the lower part is still pulled up and bunched around her waist and hips, so her plain black bike shorts are visible underneath, and she is pulling it down with both hands; the neckline, straps and fabric are clearly visible.",
        "manos_imagen": "both hands gripping the bunched-up fabric at hip height, pulling it down",
        "ropa_base": "Underneath the referenced garment she wears plain BLACK fitted bike shorts (mid-thigh sports shorts), visible because the garment is still pulled up; nothing over the garment; only simple neutral shoes. Nothing revealing: only normal sportswear.",
        "cuerpo_imagen": "young feminine hourglass figure with a defined waist and curvy hips, so the garment falls beautifully over the body",
        "pose_color": "poniéndose la prenda, con la parte de abajo todavía recogida en la cintura por encima de las mallas negras, y tirando de ella hacia abajo con las dos manos",
        "espalda_imagen": (
            "con una mano apoyada en la cintura, y la cabeza girada un poco por encima del hombro mirando a cámara. La prenda se ve entera por detrás (espalda, cintura y caída hasta el bajo)"
        ),
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
        "zonas", "pose_imagen", "manos_imagen", "ropa_base", "pose_color",
        "espalda_imagen", "cuerpo_imagen",
    ):
        texto = texto.replace("{{" + clave.upper() + "}}", fam[clave])
    return texto


def familias_para_pantalla() -> dict[str, dict]:
    """Los reemplazos de cada familia, para que la pantalla rellene los
    prompts sin pedir nada más: son cinco familias, no una por prenda."""
    campos = (
        "gesto", "final_gesto", "detalle_1", "detalle_2", "detalle_3", "prueba",
        "zonas", "pose_imagen", "manos_imagen", "ropa_base", "pose_color",
        "espalda_imagen", "cuerpo_imagen",
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


def modo_habla(modo: str) -> bool:
    """Si en ese formato la persona habla (el clip trae voz que conservar)."""
    return bool((ESTILOS_MOF10.get(estilo_de_modo(modo)) or {}).get("voz", True))


def lleva_fish(modo: str) -> bool:
    """Si ese formato se locuta con Fish (guion de punto de dolor del POV BOF
    Largo) y se monta con su editor. Los clips van mudos."""
    if not modo or modo == MODO_MULTI:
        return False
    return bool((ESTILOS_MOF10.get(estilo_de_modo(modo)) or {}).get("fish"))


# Los de Fish son de DOS clips de 10s: el guion se escribe para esos 20s.
SEGUNDOS_FISH = 20


def lleva_flecha(modo: str) -> bool:
    """Si a ese formato se le pone la flecha al carrito al final."""
    return bool((ESTILOS_MOF10.get(estilo_de_modo(modo)) or {}).get("flecha"))


def lleva_colores(modo: str) -> bool:
    """Si ese formato arranca con los cortes de color (los monta la app)."""
    return bool((ESTILOS_MOF10.get(estilo_de_modo(modo)) or {}).get("colores"))


def lleva_subtitulos(modo: str) -> bool:
    """Si a ese formato se le queman los subtítulos de lo que dice."""
    return bool((ESTILOS_MOF10.get(estilo_de_modo(modo)) or {}).get("subtitulos"))


def texto_de_modo(modo: str, semilla: str = "", hoy=None) -> dict:
    """El texto quemado que le toca a ese modo. `{}` si no lleva ninguno.

    Los que traen `variantes` eligen una por prenda (`semilla`), determinista:
    remontar el mismo vídeo en la misma temporada no le cambia la frase. La
    temporada es la del día en que se PUBLICARÁ (`temporada_multimodo`).
    """
    import hashlib

    texto = dict(TEXTO_MARCA.get(estilo_de_modo(modo)) or {})
    variantes = texto.pop("variantes", None)
    halloween = texto.pop("halloween", None)
    temporadas = texto.pop("temporadas", None) or {}
    propia = temporadas.get(temporada_multimodo(hoy))
    if isinstance(propia, list):
        variantes = propia
    elif propia:
        texto.update(propia)
    elif variantes and halloween and halloween_al_publicar(hoy):
        # Doble peso: en la semana de Halloween es lo que se busca.
        variantes = variantes + halloween + halloween
    if variantes:
        h = hashlib.sha1(("frase:" + str(semilla or "")).encode("utf-8")).digest()
        texto.update(variantes[h[0] % len(variantes)])
    return texto


def lleva_grado(modo: str) -> bool:
    """¿El montaje le aplica el color de película de marca personal?"""
    texto = texto_de_modo(modo) if modo else {}
    return bool(texto) and texto.get("grado", True)
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
    "multimodo": "🎛️ Multimodo",
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
            # Multimodo: para qué producto vale (ropa, camiseta, calzado…).
            "tipo": meta.get("tipo", ""),
            "personaje": bool(
                (ESTILOS_MOF10.get(meta["estilo_mof10"]) or {}).get("personaje")
                or meta.get("personaje_fijo")
            ),
            # Si el clip sale HABLADO. Los dos de camiseta no: su paso 2 es
            # solo movimiento, así que no gastan voz del generador —que es lo
            # caro— y la gracia la pone el texto de la prenda.
            "voz": bool(
                (ESTILOS_MOF10.get(meta["estilo_mof10"]) or {}).get("voz", True)
            ),
            # Clip mudo pero vídeo HABLADO: la voz la pone Fish al montar.
            "fish": bool((ESTILOS_MOF10.get(meta["estilo_mof10"]) or {}).get("fish")),
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
        # Habla: subtítulos de lo que dice (anti-sanción, AGENTS.md) y flecha
        # al carrito al final (oct 2026, al traerlos al multimodo).
        "subtitulos": True,
        "flecha": True,
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
        # Habla: subtítulos de lo que dice (anti-sanción, AGENTS.md) y flecha
        # al carrito al final (oct 2026, al traerlos al multimodo).
        "subtitulos": True,
        "flecha": True,
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
    # ---- MULTIMODO: los mudos de su web que no estaban --------------------
    # Los tres primeros los publica para chicas ALEATORIAS; en el multimodo va
    # siempre el personaje de la cuenta, así que llevan `personaje_fijo`: se
    # antepone una línea que manda sobre el "random woman" del texto, que se
    # queda literal debajo.
    "espejo_musica": {
        "duraciones": False,
        "label": "Frente al espejo · solo música",
        "voz": False,
        "personaje": True,
        "personaje_fijo": True,
        "ingrediente": False,
        "imagen": "prompt_mm_espejo_musica_imagen.md",
        "guion": "prompt_mm_espejo_musica_guion.md",
        "derivado": (),
    },
    "zapatillas_espejo": {
        "duraciones": False,
        "label": "Zapatillas frente al espejo, agachada · solo música",
        "voz": False,
        "personaje": True,
        "personaje_fijo": True,
        "ingrediente": False,
        "imagen": "prompt_mm_zapatillas_espejo_imagen.md",
        "guion": "prompt_mm_zapatillas_espejo_guion.md",
        "derivado": (),
    },
    # La de hombre y la de mujer no cambian solo el género (maquillaje, un
    # bloque de ropa entero): la de mujer va en su propio fichero.
    # Los de 20s con voz de Fish. Tres cosas que no tiene ningún otro:
    #   `fish`     el guion lo escribe Gemini con el prompt de punto de dolor
    #              del POV BOF Largo (es EL MISMO texto en su web) y se locuta
    #              con Fish; el montaje es el del Largo (voz repartida entre los
    #              dos clips, gancho, título, CTA, flecha y subtítulos).
    #   `voz`      False: el clip sale MUDO. Omni habla, pero su voz se tira
    #              (lo dice el propio curso), así que no se le pide.
    #   `partes`   dos clips de 10s, cada uno de SU imagen: el curso pide dos
    #              imágenes con el mismo prompt (sale otra chica y otro sitio).
    # Sin `personaje`: solo se ven manos o piernas, y el prompt pide una mujer
    # aleatoria.
    "zapatillas_pov20": {
        "duraciones": False,
        "label": "Zapatillas vista POV · 20s con voz Fish",
        "voz": False,
        "fish": True,
        "partes": 2,
        "segundos_clip": 10,
        "personaje": False,
        "ingrediente": False,
        "imagen": "prompt_mm_zapatillas_pov20_imagen.md",
        "guion": "prompt_mm_zapatillas_20_movimiento.md",
        "derivado": (),
    },
    "zapatillas_sentado20": {
        "duraciones": False,
        "label": "Zapatillas vista sentado · 20s con voz Fish",
        "voz": False,
        "fish": True,
        "partes": 2,
        "segundos_clip": 10,
        "personaje": False,
        "ingrediente": False,
        "imagen": "prompt_mm_zapatillas_sentado20_imagen.md",
        "guion": "prompt_mm_zapatillas_20_movimiento.md",
        "derivado": (),
    },
    "sarcastica_mujer": {
        "duraciones": False,
        "label": "Camiseta sarcástica · en el súper (chica)",
        "voz": False,
        "personaje": True,
        "personaje_fijo": True,
        "ingrediente": False,
        "imagen": "prompt_mof10_sarcastica_mujer_imagen.md",
        "guion": "prompt_mof10_sarcastica_mujer_guion.md",
        "derivado": (),
    },
    # Los "Vintage" de bolsos y botas (Marca Personal en su web): el producto
    # solo, sin personaje, con exposición baja de otoño y un texto otoñal que
    # Nano Banana quema YA en la imagen — el montaje no pone nada encima. La
    # imagen entra como FRAME INICIAL y el clip sale mudo.
    **{
        f"vintage_{clave}": {
            "duraciones": False,
            "label": f"Vintage otoño · {nombre}",
            "voz": False,
            "personaje": False,
            "ingrediente": False,
            "imagen": f"prompt_vintage_{clave}_imagen.md",
            "guion": f"prompt_vintage_{clave}_guion.md",
            "derivado": (),
        }
        for clave, nombre in (
            ("bolso_1", "bolso 1"), ("bolso_2", "bolso 2"), ("bolso_3", "bolso 3"),
            ("botas_1", "botas 1"), ("botas_2", "botas 2"),
            ("botas_largas_1", "botas largas 1"), ("botas_largas_2", "botas largas 2"),
            ("botas_calle", "botas calle"), ("botas_espejo4", "botas frente espejo"),
        )
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
        # Habla: subtítulos de lo que dice (anti-sanción, AGENTS.md) y flecha
        # al carrito al final (oct 2026, al traerlos al multimodo).
        "subtitulos": True,
        "flecha": True,
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
        # Habla: subtítulos de lo que dice (anti-sanción, AGENTS.md) y flecha
        # al carrito al final (oct 2026, al traerlos al multimodo).
        "subtitulos": True,
        "flecha": True,
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


# Lo que se antepone a los formatos que el curso publica con chica ALEATORIA
# cuando en el multimodo van con el personaje de la cuenta. En inglés como el
# resto del prompt, y delante para que mande sobre el "random" de debajo.
NOTA_PERSONAJE_FIJO = (
    "IMPORTANT — CHARACTER OVERRIDE: the woman in this image must be exactly the "
    "person shown in the attached character reference image (same face, hair "
    "colour and style, skin tone, body shape and apparent age). Ignore every "
    "instruction below that asks for a random, different or new woman; only the "
    "scene, the pose and the referenced product follow the prompt below.\n\n"
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
    if modo == MODO_MULTI:
        # La vista de todos los vídeos del multimodo no se graba: sin prompts.
        return salida
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
        # El personaje de la cuenta: por el estilo (marca personal) o por el
        # modo (los hablados de aleatorios traídos al multimodo).
        con_personaje = bool(meta.get("personaje")) or (
            bool(modo) and modo in MODOS and personaje_fijo_del_modo(modo))
        if meta.get("personaje_fijo") or (
                bool(modo) and modo in MODOS and personaje_fijo_del_modo(modo)):
            imagen = NOTA_PERSONAJE_FIJO + imagen
        if (TEXTO_MARCA.get(clave) or {}).get("quitar_de_imagen"):
            imagen = sin_texto_en_imagen(imagen)
            guion = sin_texto_en_video(guion)
        if modo and es_multimodo(modo):
            extra = EXTRA_VIDEO_MULTIMODO.get(modo, "")
            guion = guion.rstrip() + (" " + extra if extra else "") + NOTA_SIN_TEXTO_VIDEO
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
            "personaje": con_personaje,
            "ingrediente": bool(meta.get("ingrediente")),
            "voz": bool(meta.get("voz", True)),
            # El guion lo escribe la app (punto de dolor) y lo locuta Fish: el
            # botón de guiones vale aunque aquí no haya tope de caracteres.
            "fish": bool(meta.get("fish")),
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
