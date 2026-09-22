"""La captura del selector de colores de una prenda ("captura de variantes").

La captura de la ficha que viene del Drive o del ZIP casi nunca llega hasta
el selector "Color" de TikTok Shop, y el formato Tienda Colores necesita los
nombres EXACTOS de las variantes (el vídeo tiene que decir lo mismo que la
ficha, o TikTok lo sanciona como producto inconsistente). Así que el operador
sube UNA captura más —la del selector, con las miniaturas y sus nombres— y
se adjunta al guion junto con la ficha y la limpia.

Vive en el Drive montado, aparte de las fotos de la prenda: en la carpeta de
la prenda rompería el emparejado limpia/ficha (que mira todas las imágenes
del directorio). `_variantes` cuelga de la raíz de prendas importadas, que
no es un género y no sale en ningún selector.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.nicho_ropa import config

_EXTS = (".jpg", ".jpeg", ".png", ".webp")
MAX_BYTES = 12 * 1024 * 1024


def _dir(carpeta: str) -> Path:
    seguro = re.sub(r"[^\w.\- ]+", "_", carpeta or "").strip() or "_"
    return config.prendas_web_dir() / "_variantes" / seguro


def ruta(carpeta: str, producto: str) -> Path | None:
    """La captura guardada de esa prenda, o None."""
    d = _dir(carpeta)
    if not d.is_dir():
        return None
    for ext in _EXTS:
        f = d / f"{producto}{ext}"
        if f.is_file() and f.stat().st_size > 0:
            return f
    return None


def guardar(carpeta: str, producto: str, datos: bytes, nombre: str) -> Path:
    """Sustituye la que hubiera (con otra extensión también)."""
    ext = Path(nombre or "").suffix.lower()
    if ext not in _EXTS:
        raise ValueError(f"Formato no soportado ({nombre!r}): acepta jpg, jpeg, png o webp.")
    if not datos:
        raise ValueError("La captura llegó vacía.")
    if len(datos) > MAX_BYTES:
        raise ValueError(f"La captura pesa {len(datos) / 1e6:.0f} MB; el tope son 12 MB.")
    d = _dir(carpeta)
    d.mkdir(parents=True, exist_ok=True)
    quitar(carpeta, producto)
    destino = d / f"{producto}{ext}"
    destino.write_bytes(datos)
    return destino


def quitar(carpeta: str, producto: str) -> bool:
    habia = False
    for ext in _EXTS:
        f = _dir(carpeta) / f"{producto}{ext}"
        if f.is_file():
            f.unlink(missing_ok=True)
            habia = True
    return habia


def tienen(carpeta: str) -> set[str]:
    """Productos de la carpeta con captura, en una sola lectura del disco."""
    d = _dir(carpeta)
    if not d.is_dir():
        return set()
    return {f.stem for f in d.iterdir() if f.is_file() and f.suffix.lower() in _EXTS}
