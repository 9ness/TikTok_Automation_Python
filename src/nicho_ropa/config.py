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


# Los estilos de 10s que tiene publicados. Van en lista porque va sacando más,
# y cada uno son DOS prompts: la imagen y el guion+movimiento.
#
# `derivado` dice de qué sexos el texto NO es suyo sino nuestro, cambiando las
# palabras de la persona. Se marca en la pantalla: un prompt derivado funciona,
# pero si él publica el suyo hay que pegarlo encima.
ESTILOS_MOF10: dict[str, dict] = {
    # De este publica los DOS sexos, así que no se deriva nada: van sus dos
    # textos tal cual. Y hace falta, porque entre ellos cambia más que el
    # género —maquillaje, joyería y un bloque de movimiento entero—.
    "espejo": {
        "label": "Frente al espejo · cuerpo entero",
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
    "movil": {
        "label": "Colocando el móvil · medio cuerpo",
        "imagen": "prompt_mof10_movil_imagen.md",
        "guion": "prompt_mof10_movil_guion.md",
        "derivado": ("mujer",),
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


def prompts_mof10(sexo: str = SEXO_DEFECTO, plazos: bool = False) -> list[dict]:
    """Los estilos de 10s, cada uno con sus dos prompts ya en ese sexo."""
    salida = []
    for clave, meta in ESTILOS_MOF10.items():
        propios = (meta.get("por_sexo") or {}).get(sexo)
        if propios:
            # Suyos los dos: se sirven literales, sin sustituir nada.
            imagen, guion = (_limpio(f) for f in propios)
        else:
            imagen = _con_sexo(meta["imagen"], sexo, SEXOS_MOF10)
            guion = _con_sexo(meta["guion"], sexo, SEXOS_MOF10)
        salida.append({
            "clave": clave,
            "label": meta["label"],
            "imagen": _con_plazos(imagen, plazos),
            "guion": _con_plazos(guion, plazos),
            "derivado": sexo in meta["derivado"],
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
