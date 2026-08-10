"""Miniaturas de las fotos de producto.

Existe por una razón muy concreta: **la APK se cerraba sola**.

Las fotos del Drive son grandes —una ficha típica es 1320×2868— y lo que ocupa
en el móvil no es el fichero (1-2 MB) sino el BITMAP descodificado: ancho × alto
× 4 bytes = **15 MB por foto**. Una carpeta son diez productos con dos fotos
cada uno, así que la pantalla llegaba a pedirle al renderer ~300 MB. Chrome lo
mata por memoria y, en una TWA, eso se ve exactamente igual que "Android ha
cerrado la app". Por eso pasaba "a veces": dependía de la pantalla.

Sirviendo la foto a 400 px de ancho, ese bitmap baja a ~1,4 MB — 10× menos, y en
una cuadrícula de móvil no se nota la diferencia. El original se sigue sirviendo
tal cual donde importa: las descargas (`/foto-limpia`) y el montaje del vídeo,
que leen el fichero del disco y no pasan por aquí.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from src.nicho_pov_bof import config

logger = logging.getLogger("api")

# Cuánto se re-comprime. 82 es el punto donde una foto de producto ya no mejora
# a ojo pero el fichero sigue bajando.
_CALIDAD = 82


def _dir() -> Path:
    d = Path(config.photo_cache_dir()) / "thumbs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def miniatura(origen: Path, ancho: int) -> Path:
    """Devuelve una copia de `origen` de como mucho `ancho` px, cacheada.

    Si algo falla —formato raro, Pillow sin el códec, disco lleno— devuelve el
    ORIGINAL. Una foto pesada es un problema; una foto que no sale es peor.
    """
    try:
        st = origen.stat()
    except OSError:
        return origen

    # El mtime y el tamaño van en la clave a propósito: en "Mis productos" el
    # identificador es la RUTA, y la ruta se REUTILIZA al borrar un producto y
    # subir otro. Sin esto, la miniatura del producto viejo se serviría para el
    # nuevo (que es justo el bug que ya nos comimos con la caché del navegador).
    firma = f"{origen}|{st.st_mtime_ns}|{st.st_size}|{ancho}".encode()
    destino = _dir() / f"{hashlib.sha1(firma).hexdigest()}.jpg"
    if destino.is_file() and destino.stat().st_size > 0:
        return destino

    try:
        from PIL import Image

        with Image.open(origen) as im:
            # `draft` deja que el decodificador de JPEG baje la resolución
            # mientras lee: descodificar entero para luego encoger cuesta el
            # mismo pico de memoria en el SERVIDOR que queríamos evitar en el
            # móvil. En PNG no hace nada, y no pasa nada.
            im.draft("RGB", (ancho, ancho * 4))

            if im.mode in ("RGBA", "LA", "P"):
                # Muchas fotos de producto vienen recortadas con transparencia.
                # Convertir a RGB a secas pinta el fondo de NEGRO; sobre blanco
                # se ve como en el Drive.
                im = im.convert("RGBA")
                fondo = Image.new("RGB", im.size, (255, 255, 255))
                fondo.paste(im, mask=im.split()[-1])
                im = fondo
            else:
                im = im.convert("RGB")

            if im.width > ancho:
                alto = max(1, round(im.height * ancho / im.width))
                im = im.resize((ancho, alto), Image.LANCZOS)

            # Se escribe aparte y se renombra: dos peticiones a la vez sobre la
            # misma foto no pueden dejar un JPEG a medias servido como bueno.
            tmp = destino.with_suffix(f".{os.getpid()}.part")
            im.save(tmp, "JPEG", quality=_CALIDAD, optimize=True)
            tmp.replace(destino)
        return destino
    except Exception as e:
        logger.warning("miniatura de %s falló (%s); sirvo el original", origen.name, e)
        return origen
