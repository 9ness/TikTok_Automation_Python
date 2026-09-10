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
        "label": "🪞 BOF Frente a Espejo",
        "estilo_mof10": "espejo",
        "sexos": ("mujer", "hombre"),
    },
    "camara": {
        "label": "🤳 BOF Selfie",
        "estilo_mof10": "movil",
        # Desde sep 2026 lo publica también para mujer, con su propio texto.
        "sexos": ("mujer", "hombre"),
    },
    "calle_1": {
        "label": "🚶 Situación Real 1",
        "estilo_mof10": "real_1",
        # Desde sep 2026 también está en Moda Chica, con su propia imagen.
        "sexos": ("mujer", "hombre"),
    },
    "calle_2": {
        "label": "☕ Situación Real 2",
        "estilo_mof10": "real_2",
        # Desde sep 2026 también está en Moda Chica, con sus dos textos.
        "sexos": ("mujer", "hombre"),
    },
    "gafas_coche": {
        "label": "🕶️ Gafas en Coche",
        "estilo_mof10": "gafas",
        "sexos": ("hombre",),
    },
    "sarcastica": {
        "label": "😏 Camiseta Sarcástica",
        "estilo_mof10": "sarcastica",
        "sexos": ("hombre",),
    },
    # El maniquí no lleva persona, así que la prenda podría ser de cualquiera;
    # se deja en hombre porque es donde lo publica y porque el resto del menú
    # de mujer va con modelo.
    "maniqui": {
        "label": "🧍 Camiseta Maniquí",
        "estilo_mof10": "maniqui",
        "sexos": ("hombre",),
    },
    # "BOLSO MOF MUJER POV ONMI 10S" existe en su web pero AÚN NO tiene
    # prompts publicados, así que no se ofrece: un modo sin prompt es un botón
    # que no lleva a nada. Al pegarlos, se añade aquí con `estilo_mof10:
    # "bolso"` y su entrada en `ESTILOS_MOF10`. Ojo: solo vale para prendas
    # que SEAN bolsos — necesita el filtro por categoría (ver tasks.md).
    # ---- MARCA PERSONAL (sep 2026) -------------------------------------
    # La otra modalidad de Moda Mujer. Lo que la separa de los de arriba no es
    # el estilo, es la CUENTA: aquellos van con personajes distintos cada vez y
    # estos repiten el mismo, que es lo que construye la marca. Por eso llevan
    # `modalidad` y la pantalla los enseña por separado.
    #
    # `categoria` filtra el catálogo: dos de los tres son de calzado y en una
    # carpeta con vestidos no pintan nada (ver `es_calzado`).
    "marca_espejo": {
        "label": "🪞 Espejo Multi Escena 10s",
        "estilo_mof10": "marca_espejo",
        "sexos": ("mujer",),
        "modalidad": "marca",
    },
    "marca_zapatos": {
        "label": "👢 Zapatos Multi Escena 10s",
        "estilo_mof10": "marca_zapatos",
        "sexos": ("mujer",),
        "modalidad": "marca",
        "categoria": "calzado",
    },
    "marca_pov": {
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
# ---------------------------------------------------------------------------
# Las carpetas del ZIP vienen de la web del curso, y allí la ropa NO se enseña
# en percha: se enseña puesta, grabándose frente al espejo. Ese prompt solo
# está publicado en su versión de mujer, así que la de hombre se deriva
# cambiando las cinco piezas que hablan de quién graba — igual que hace Jonny
# en el Nicho Zapatos, donde el par mujer/hombre es el mismo texto con
# `adult woman` → `adult man`.
SEXOS: dict[str, dict[str, str]] = {
    "mujer": {
        "label": "Mujer",
        "CREADOR": "Una creadora española joven y guapa",
        "SUJETO_DICE": "La mujer dice en español:",
        "VOZ_SINC": "voz femenina española, juvenil y natural",
        "EJEMPLO": (
            "Han ajustado el precio de estos jeans virales. Son elásticos y de "
            "campana. Comprueba tus cupones antes de comprar.{{FRASE_PLAZOS}}"
        ),
        "VOZ_DESC": (
            "Voz femenina ligera, viva y luminosa, perteneciente a una mujer de "
            "aproximadamente 25 años. Tono medio-agudo, brillante y claro, con un "
            "timbre cálido, amigable y cercano. Ritmo conversacional ágil y "
            "natural, ligeramente enérgico y espontáneo, como una creadora UGC "
            "real. Pronunciación española clara, sin tono de locutora publicitaria "
            "y sin entonación robótica. La misma voz debe mantenerse en las tres "
            "escenas, con sincronización labial precisa."
        ),
    },
    "hombre": {
        "label": "Hombre",
        "CREADOR": "Un creador español joven y atractivo",
        "SUJETO_DICE": "El hombre dice en español:",
        "VOZ_SINC": "voz masculina española, juvenil y natural",
        "EJEMPLO": (
            "Han ajustado el precio de esta sudadera viral. Es de algodón grueso "
            "y cae perfecta. Comprueba tus cupones antes de comprar."
            "{{FRASE_PLAZOS}}"
        ),
        "VOZ_DESC": (
            "Voz masculina natural, viva y cercana, perteneciente a un hombre de "
            "aproximadamente 25 años. Tono medio-grave, limpio y claro, con un "
            "timbre cálido, amigable y cercano. Ritmo conversacional ágil y "
            "natural, ligeramente enérgico y espontáneo, como un creador UGC "
            "real. Pronunciación española clara, sin tono de locutor publicitario "
            "y sin entonación robótica. La misma voz debe mantenerse en las tres "
            "escenas, con sincronización labial precisa."
        ),
    },
}

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


def prompt_video_espejo(sexo: str = SEXO_DEFECTO, plazos: bool = False) -> str:
    """El prompt de la web con las palabras de ESE sexo ya sustituidas.

    `plazos` mete la frase de la financiación en lo que dice la persona. Va
    apagado por defecto: prometerla cuando no la hay es lo caro, y aquí no se
    puede corregir después — la voz la pone el propio vídeo.
    """
    piezas = SEXOS.get(sexo) or SEXOS[SEXO_DEFECTO]
    texto = _limpio("prompt_video_espejo.md")
    for clave, valor in piezas.items():
        if clave != "label":
            texto = texto.replace("{{" + clave + "}}", valor)
    return _con_plazos(texto, plazos)


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


def _con_duracion(texto: str, duracion: str) -> str:
    """Rellena el tope de caracteres que le toca a esa duración."""
    meta = DURACIONES[duracion_valida(duracion)]
    return (
        texto.replace("{{CARACTERES}}", str(meta["caracteres"]))
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
}


# La frase del pago a plazos, que va SUELTA y no dentro del ejemplo.
#
# En este nicho la voz la pone el propio vídeo (la persona habla), así que lo
# que diga el ejemplo es lo que va a decir: si el ejemplo promete plazos, el
# clip lo promete aunque esa prenda no los tenga. Y aquí no se puede arreglar
# después como en el POV BOF —allí la voz se genera aparte y se puede
# resintetizar—: habría que volver a generar el vídeo entero.
FRASE_PLAZOS = " Y si lo prefieres, puedes pagarlo a plazos."


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
            # Suyos los dos: se sirven literales, sin sustituir nada.
            imagen, guion = (_limpio(f) for f in propios)
        else:
            imagen = _con_sexo(meta["imagen"], sexo, SEXOS_MOF10)
            guion = _con_sexo(meta["guion"], sexo, SEXOS_MOF10)
        # El tope de caracteres solo se toca en los estilos cuyo guion se
        # escribe fuera; en los de calle no hay marcador que rellenar.
        dur = duracion_valida(duracion) if meta.get("duraciones") else DURACION_DEFECTO
        salida.append({
            "clave": clave,
            "label": meta["label"],
            "imagen": _con_duracion(_con_plazos(imagen, plazos), dur),
            "guion": _nota_duracion(
                _con_duracion(_con_plazos(guion, plazos), dur), dur,
            ),
            "derivado": sexo in meta["derivado"],
            # Lo que hay que saber AL PEGARLO, y que no se ve en el prompt:
            # si se adjunta el personaje de referencia, si la imagen entra
            # como ingrediente en vez de como frame inicial, y si el clip
            # sale hablado. Van con el prompt para que la pantalla los pinte
            # al lado del botón de copiar y no haya que recordarlos.
            "personaje": bool(meta.get("personaje")),
            "ingrediente": bool(meta.get("ingrediente")),
            "voz": bool(meta.get("voz", True)),
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
