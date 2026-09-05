"""Estado del Nicho General · UGC por carpeta de productos (`nicho_general:`).

**Los textos del producto NO se guardan aquí** —título, tienda, caption, precio
y plazos salen del Nicho POV BOF, que es quien los extrae y quien paga esas
llamadas de Gemini—. Aquí vive solo lo propio de este nicho, por usuario:

    escenas          las tres del anuncio, cada una con su prompt de imagen,
                     su prompt de vídeo, el guion y cuántos caracteres tiene
    voz              la identidad vocal, que va copiada en las tres
    personaje        con qué persona se graba (se elige por producto)
    clips            los vídeos subidos, SIN orden: los ordena el montaje
    video_path, video_listo_at, uploaded, sold

Key: `nicho_general:folder:<source>:<carpeta>:u:<usuario>[:<gancho>_<duracion>]`

El gancho y la duración van en la CLAVE porque separan todo el trabajo: el
guion de 8 s no es el de 10 recortado —se escribe entero para caber—, así que
son dos anuncios distintos del mismo producto, con sus clips y su vídeo. Lo del
producto (textos, escaparate, vendidos) sigue siendo común y no se duplica.

La combinación por DEFECTO se queda en la clave sin sufijo, como en el POV BOF
Largo: así lo primero que se graba no se mueve de sitio si algún día cambia el
defecto.
"""

from __future__ import annotations

import os
import random
import time
from contextlib import contextmanager

from src.nicho_general import config
from src.nicho_general.repos.redis_base import get_nicho_general_redis


def _slug_usuario(usuario: str) -> str:
    return (usuario or "").strip() or "ness"


def _key(source: str, folder: str, usuario: str, gancho: str, duracion: str) -> str:
    from src.nicho_pov_bof import config as pov_config

    # La fuente se canoniza: leer una carpeta desde la copia de seguridad es
    # leer la MISMA carpeta del curso, con el mismo progreso.
    base = (
        f"folder:{pov_config.fuente_canonica(source)}:{folder}"
        f":u:{_slug_usuario(usuario)}"
    )
    clave = config.clave_guion(gancho, duracion)
    defecto = config.clave_guion(config.GANCHO_DEFECTO, config.DURACION_DEFECTO)
    return base if clave == defecto else f"{base}:{clave}"


def _require_redis():
    r = get_nicho_general_redis()
    if not r.is_available():
        raise RuntimeError(
            "Upstash no está configurado: sin él no se puede guardar el estado "
            "del nicho (UPSTASH_REDIS_REST_URL / _TOKEN)."
        )
    return r


@contextmanager
def _cerrojo(source: str, folder: str, usuario: str, gancho: str, duracion: str,
             espera_s: float = 10.0):
    """Se guarda el documento ENTERO y la API corre con varios workers: sin
    cerrojo se pierden escrituras (subir tres clips a la vez, por ejemplo).

    Si no se consigue en `espera_s` se escribe igual, como en el POV BOF
    Largo: perder una escritura es malo, pero dejar al operador sin poder
    guardar es peor.
    """
    r = get_nicho_general_redis()
    key = _key(source, folder, usuario, gancho, duracion) + ":lock"
    mio = False
    if r.is_available():
        limite = time.monotonic() + espera_s
        while time.monotonic() < limite:
            if r.set_nx(key, str(os.getpid()), ttl_s=30):
                mio = True
                break
            time.sleep(0.15 + random.random() * 0.2)
    try:
        yield mio
    finally:
        if mio:
            r.delete(key)


def load_folder(
    source: str, folder: str, usuario: str = "",
    gancho: str = "", duracion: str = "",
) -> dict:
    r = get_nicho_general_redis()
    if not r.is_available():
        return {}
    return r.get_json(_key(source, folder, usuario, gancho, duracion)) or {}


def get_product(
    source: str, folder: str, producto: str, usuario: str = "",
    gancho: str = "", duracion: str = "",
) -> dict:
    doc = load_folder(source, folder, usuario, gancho, duracion)
    return (doc.get("productos") or {}).get(str(producto)) or {}


def update_product(
    source: str, folder: str, producto: str, usuario: str = "",
    gancho: str = "", duracion: str = "", **campos,
) -> dict:
    """Escribe campos de un producto sin pisar los demás."""
    with _cerrojo(source, folder, usuario, gancho, duracion):
        r = _require_redis()
        key = _key(source, folder, usuario, gancho, duracion)
        doc = r.get_json(key) or {}
        prods = doc.setdefault("productos", {})
        prod = prods.setdefault(str(producto), {})
        prod.update(campos)
        prod["updated_at"] = int(time.time())
        r.set_json(key, doc)
        return prod


def guardar_escenas(
    source: str, folder: str, producto: str, escenas: list[dict], voz: str,
    usuario: str = "", gancho: str = "", duracion: str = "",
) -> dict:
    """Las tres escenas que escribió la IA, con la voz que las tres comparten.

    Se guarda `voz` aparte de los prompts aunque el documento del curso la
    exija DENTRO de cada uno: así se puede enseñar en la pantalla y comprobar
    de un vistazo que es la misma en las tres, que es de lo que depende que el
    anuncio suene como un solo vídeo y no como tres.
    """
    return update_product(
        source, folder, producto, usuario, gancho, duracion,
        escenas=escenas, voz=voz, escenas_at=int(time.time()),
    )


def anadir_clips(
    source: str, folder: str, producto: str, rutas: list[str],
    usuario: str = "", gancho: str = "", duracion: str = "",
) -> dict:
    """Añade clips subidos, SIN orden.

    El operador los adjunta todos de una vez y en el orden que le salga del
    selector de ficheros; quién es el 1, el 2 y el 3 lo decide el montaje
    transcribiéndolos y casándolos con el guion de cada escena.
    """
    with _cerrojo(source, folder, usuario, gancho, duracion):
        r = _require_redis()
        key = _key(source, folder, usuario, gancho, duracion)
        doc = r.get_json(key) or {}
        prod = doc.setdefault("productos", {}).setdefault(str(producto), {})
        clips = [c for c in (prod.get("clips") or []) if c]
        for ruta in rutas:
            if ruta and ruta not in clips:
                clips.append(ruta)
        prod["clips"] = clips
        prod["updated_at"] = int(time.time())
        r.set_json(key, doc)
        return prod


def quitar_clips(
    source: str, folder: str, producto: str,
    usuario: str = "", gancho: str = "", duracion: str = "",
) -> dict:
    """Vacía los clips para volver a subirlos (se generó uno mal y se rehace)."""
    return update_product(
        source, folder, producto, usuario, gancho, duracion, clips=[],
    )
