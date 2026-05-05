"""Resolución de fuentes cross-platform.

El proyecto se desarrolló sobre Windows y muchos sitios hardcodean rutas
tipo `C:\\Windows\\Fonts\\impact.ttf`. En el VPS Linux esas rutas no
existen — este módulo traduce nombres de fuente Windows a sus
equivalentes en Linux.

En Linux se asume que está instalado `ttf-mscorefonts-installer` (lo
hace `deploy/setup.sh`), que pone Impact / Arial / Verdana / etc. en
`/usr/share/fonts/truetype/msttcorefonts/`. Si no está, cae a fuentes
de respaldo (DejaVu / Liberation, instaladas por defecto en Ubuntu).

Uso:
    from src.font_resolver import resolve_font, safe_truetype
    path = resolve_font(r"C:\\Windows\\Fonts\\impact.ttf")
    # En Windows: devuelve la ruta tal cual
    # En Linux: devuelve /usr/share/fonts/truetype/msttcorefonts/Impact.ttf

    # O el wrapper que ya carga el ImageFont:
    font = safe_truetype(r"C:\\Windows\\Fonts\\impact.ttf", 48)
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from PIL import ImageFont


# Mapeo nombre archivo Windows → nombre archivo Linux (msttcorefonts).
# El paquete `ttf-mscorefonts-installer` usa nombres con guiones bajos.
_WIN_TO_LINUX = {
    "impact.ttf":      "Impact.ttf",
    "arial.ttf":       "Arial.ttf",
    "arialbd.ttf":     "Arial_Bold.ttf",
    "ariali.ttf":      "Arial_Italic.ttf",
    "arialbi.ttf":     "Arial_Bold_Italic.ttf",
    "ariblk.ttf":      "Arial_Black.ttf",
    "comic.ttf":       "Comic_Sans_MS.ttf",
    "comicbd.ttf":     "Comic_Sans_MS_Bold.ttf",
    "verdana.ttf":     "Verdana.ttf",
    "verdanab.ttf":    "Verdana_Bold.ttf",
    "verdanai.ttf":    "Verdana_Italic.ttf",
    "verdanaz.ttf":    "Verdana_Bold_Italic.ttf",
    "tahoma.ttf":      "DejaVuSans.ttf",          # tahoma no está en mscorefonts, fallback
    "tahomabd.ttf":    "DejaVuSans-Bold.ttf",
    "trebuc.ttf":      "Trebuchet_MS.ttf",
    "trebucbd.ttf":    "Trebuchet_MS_Bold.ttf",
    "georgia.ttf":     "Georgia.ttf",
    "georgiab.ttf":    "Georgia_Bold.ttf",
    "times.ttf":       "Times_New_Roman.ttf",
    "timesbd.ttf":     "Times_New_Roman_Bold.ttf",
    "cour.ttf":        "Courier_New.ttf",
    "courbd.ttf":      "Courier_New_Bold.ttf",
    "bahnschrift.ttf": "DejaVuSans-Bold.ttf",     # no en mscorefonts → DejaVu
    "rockwell.ttf":    "DejaVuSerif-Bold.ttf",    # idem
    "rockeb.ttf":      "DejaVuSerif-Bold.ttf",
    "calibri.ttf":     "Liberation_Sans-Regular.ttf",
    "calibrib.ttf":    "Liberation_Sans-Bold.ttf",
}

# Directorios a escanear en Linux (orden de preferencia)
_LINUX_FONT_DIRS = [
    "/usr/share/fonts/truetype/msttcorefonts",
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/freefont",
    "/usr/share/fonts/TTF",
    "/usr/share/fonts/opentype",
    "/usr/share/fonts",  # raíz, recursivo solo como último recurso
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
]

# Fallback final si nada matchea — viene preinstalado en Ubuntu
_LAST_RESORT_LINUX = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _is_windows() -> bool:
    return os.name == "nt"


@lru_cache(maxsize=128)
def resolve_font(path: str) -> str:
    """Devuelve una ruta válida a la fuente para el OS actual.

    - Si el `path` ya existe en disco, lo devuelve tal cual.
    - En Linux, si el path es Windows-style, mapea por nombre conocido
      (Impact.ttf, Arial_Bold.ttf...) y busca en `_LINUX_FONT_DIRS`.
    - Si no encuentra ninguna, devuelve `_LAST_RESORT_LINUX` (DejaVu).
    - Como último último recurso, devuelve el path original (PIL fallará
      con un error explícito).

    Resultado cacheado para no escanear el FS en cada palabra de subtítulo.
    """
    if not path:
        return path

    if os.path.exists(path):
        return path

    if _is_windows():
        # Windows: si la ruta no existe es problema del usuario; devolvemos tal cual
        return path

    # ---- Linux ----
    basename = os.path.basename(path).lower()
    linux_name = _WIN_TO_LINUX.get(basename, basename)

    # Búsqueda directa por nombre conocido
    for d in _LINUX_FONT_DIRS:
        candidate = os.path.join(d, linux_name)
        if os.path.exists(candidate):
            return candidate

    # Búsqueda recursiva más amplia (caso fonts/X11/...)
    for d in _LINUX_FONT_DIRS:
        if not os.path.isdir(d):
            continue
        try:
            for root, _, files in os.walk(d):
                if linux_name in files:
                    return os.path.join(root, linux_name)
                # Variante case-insensitive en algunos sistemas
                lower_files = {f.lower(): f for f in files}
                if linux_name.lower() in lower_files:
                    return os.path.join(root, lower_files[linux_name.lower()])
        except OSError:
            continue

    # Fallback final
    if os.path.exists(_LAST_RESORT_LINUX):
        return _LAST_RESORT_LINUX

    # Devolvemos path original — PIL lanzará error claro si no existe
    return path


def safe_truetype(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Wrapper de `ImageFont.truetype` que primero pasa el path por
    `resolve_font`. Útil para sustituir llamadas existentes."""
    return ImageFont.truetype(resolve_font(path), size)


def get_default_bold_font() -> str:
    """Fuente bold "estándar" del proyecto, resuelta para el OS actual.
    Útil cuando un caller no tiene un path concreto sino "quiero una bold"."""
    return resolve_font(r"C:\Windows\Fonts\impact.ttf")


def get_default_regular_font() -> str:
    """Fuente regular "estándar" del proyecto, resuelta para el OS actual."""
    return resolve_font(r"C:\Windows\Fonts\arial.ttf")
