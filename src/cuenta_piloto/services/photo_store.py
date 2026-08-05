"""Guarda en disco las dos fotos que sube el operador.

El resto de nichos leen las fotos de Drive por file ID; este es el primero en
el que llegan por HTTP. Van a la carpeta persistente del usuario
(`config.fotos_dir`) y NO a `api_uploads/`, que la API purga cada 24h — si
estuvieran ahí, el producto amanecería sin fotos.
"""

from __future__ import annotations

import time
from pathlib import Path

from src.cuenta_piloto import config


def guardar(usuario: str, datos: bytes, *, filename: str, etiqueta: str) -> Path:
    """Escribe una foto y devuelve su ruta absoluta.

    `etiqueta` es `limpia` o `ficha` — va en el nombre para poder mirar la
    carpeta y saber cuál es cuál sin abrir Redis.
    """
    ext = _extension(filename)
    destino = config.fotos_dir(usuario) / f"{int(time.time() * 1000)}_{etiqueta}{ext}"
    destino.write_bytes(datos)
    return destino


def _extension(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    return ext if ext in config.FOTO_EXTS else ".jpg"


def es_foto(filename: str) -> bool:
    return Path(filename or "").suffix.lower() in config.FOTO_EXTS
