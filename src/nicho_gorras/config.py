"""Nicho Gorras (Programa 4 — módulo 11 del curso).

El más simple de todos: aquí NO se edita vídeo. El vídeo sale del generador y
se publica tal cual. Lo único que hace falta de la app es encontrar la gorra y
tener a mano su título, su tienda y su caption — y los prompts para copiarlos
fuera.

Por eso este módulo no tiene ni `pipeline/`, ni `JobMode`, ni runner, ni cola.

**El emparejado es DISTINTO al de los otros nichos.** Las fotos se llaman
`IMG_5033.PNG`, `IMG_5034.PNG`… y los números NO se repiten entre la foto y su
ficha, así que agrupar por el número del nombre (lo que hace `photo_pairing`)
daría 20 productos donde hay 10. Van **de dos en dos por orden**: primero la
foto limpia, después la ficha. Comprobado sobre 40 parejas de cuatro carpetas:
40 de 40, y la ficha siempre con ratio 2,17 (pantallazo de móvil) frente a la
limpia, que ronda el cuadrado.
"""

from __future__ import annotations

import os
from pathlib import Path

REDIS_PREFIX = os.getenv("NICHO_GORRAS_REDIS_PREFIX", "nicho_gorras:")

DRIVE_REMOTE = "gdrive:"

# Las 8 carpetas de la tienda asignada, dentro de
# `Productos España/Gorras/Jonny/Tienda Budget Fashion Hats`. Se leen con
# `--drive-root-folder-id`, como el Nicho Ropa: son carpetas de un Drive ajeno
# compartido, no están en "Compartido conmigo" a este nivel.
CARPETAS: dict[str, dict[str, str]] = {
    "1": {"label": "Carpeta 1", "id": "1QGOaVVcuSsaPuOKlWYry0VRHiJYkl0Yx"},
    "2": {"label": "Carpeta 2", "id": "1HfKcBEVwIwkWNUtGUO4i_knF25xxcfI3"},
    "3": {"label": "Carpeta 3", "id": "169yYWUK2P4KYLr0X-sMWFYP1y-P6PdIM"},
    "4": {"label": "Carpeta 4", "id": "1sltnmgACHOAX9FRdS778MgmSa0-lXBAK"},
    "5": {"label": "Carpeta 5", "id": "1UvsM7WQcSFd-XZB62kZ7PxohFSBFpnwu"},
    "6": {"label": "Carpeta 6", "id": "1F5HfdKbAJd11yyRK1ZEapViWDQBYxigu"},
    "7": {"label": "Carpeta 7", "id": "1O4VgOGP2zD_KEbbqVHq2MWgUVRGFsSGi"},
    "8": {"label": "Carpeta 8", "id": "1_TQHEzKwIqYpuh8aNH5H-WLABEtoCmzy"},
}

CARPETA_DEFECTO = "1"

RCLONE_TIMEOUT_S = 120.0
LISTING_TTL_S = 3600.0


def es_carpeta_conocida(slug: str) -> bool:
    return slug in CARPETAS


def carpeta_id(slug: str) -> str:
    if not es_carpeta_conocida(slug):
        raise ValueError(f"Carpeta de gorras desconocida: {slug!r}")
    return CARPETAS[slug]["id"]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
# Uno de imagen y CINCO de vídeo, uno por escenario. El curso los tiene en
# documentos sueltos y el operador elige el sitio donde quiere la gorra, así
# que se ofrecen todos en vez de escoger uno por él.
PROMPTS: tuple[tuple[str, str], ...] = (
    ("imagen", "🖼️ Imagen base (Flow)"),
    ("ambiente_general", "🎥 Ambiente general"),
    ("estanteria", "🎥 Estantería de habitación"),
    ("garaje_lujo", "🎥 Garaje de lujo"),
    ("mesa_terraza", "🎥 Mesa de terraza"),
    ("terraza_premium", "🎥 Terraza premium"),
)


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def prompt(slug: str) -> str:
    texto = (prompts_dir() / f"{slug}.md").read_text(encoding="utf-8")
    if "-->" in texto:
        texto = texto.split("-->", 1)[1]
    return texto.strip()


def rclone_config_path() -> str:
    from src.nicho_pov_bof.config import rclone_config_path as _p

    return _p()
