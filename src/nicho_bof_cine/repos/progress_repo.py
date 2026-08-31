"""Tracking de carpetas de producto ya completadas.

El estado vive en Redis (SET por fuente), NUNCA en Drive — "Productos España"
es un Drive de terceros y es solo lectura.

Key: `nicho_bof_cine:completed:<source>` → SET de nombres de carpeta.

Progreso INDEPENDIENTE del Nicho POV BOF aunque las carpetas sean las mismas:
completar "1 Pront Flow" allí no la completa aquí, porque son vídeos distintos
del mismo producto.
"""

from __future__ import annotations

from src.nicho_bof_cine.repos.redis_base import get_nicho_bof_cine_redis
from src.nicho_pov_bof import config as pov_config


def _key(source: str, usuario: str = "") -> str:
    """Clave del progreso. Es POR USUARIO: cada uno va por su carpeta.

    El histórico (sin usuario) se conserva como clave de `ness`, que es quien
    lo generó — así no pierde por dónde iba al separar las cuentas.
    """
    # La copia de seguridad comparte progreso con la fuente del curso: son las
    # mismas carpetas, solo cambia de dónde se leen las fotos. Sin esto, al
    # trabajar desde "🗄️ Copia" el progreso se guardaba aparte y la carpeta
    # aparecía sin empezar al volver a la fuente normal.
    source = pov_config.fuente_canonica(source)
    if not usuario or usuario == "ness":
        return f"completed:{source}"
    return f"completed:{source}:{usuario}"


def _require_redis():
    r = get_nicho_bof_cine_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede leer/guardar el "
            "progreso del Nicho BOF Cinematográfico. Define UPSTASH_REDIS_REST_URL y "
            "UPSTASH_REDIS_REST_TOKEN."
        )
    return r


def get_completed(source: str, usuario: str = "") -> set[str]:
    """Nombres de carpeta marcados como completados en esta fuente."""
    return set(_require_redis().smembers(_key(source, usuario)))


def is_completed(source: str, folder: str, usuario: str = "") -> bool:
    return _require_redis().sismember(_key(source, usuario), folder)


def mark_completed(source: str, folder: str, usuario: str = "") -> None:
    _require_redis().sadd(_key(source, usuario), folder)


def unmark_completed(source: str, folder: str, usuario: str = "") -> None:
    """Rollback — degrada en silencio si Redis no está (igual que viralización)."""
    r = get_nicho_bof_cine_redis()
    if r.is_available():
        r.srem(_key(source, usuario), folder)


# ---------------------------------------------------------------------------
# Carpetas con los vídeos hechos pero SIN subir todavía
# ---------------------------------------------------------------------------
# SET propio, no un flag dentro de las completadas: se preparan vídeos de días
# futuros y esa carpeta no está cerrada —queda por subirlos—, y una ya cerrada
# puede seguir sin subir. Mismo esquema que en el Nicho POV BOF.


def _key_pendientes(source: str, usuario: str = "") -> str:
    source = pov_config.fuente_canonica(source)
    if not usuario or usuario == "ness":
        return f"pending_upload:{source}"
    return f"pending_upload:{source}:{usuario}"


def get_pendientes(source: str, usuario: str = "") -> set[str]:
    """Degrada a vacío si Redis no está: es un aviso de color, no puede dejar
    sin listado de carpetas."""
    r = get_nicho_bof_cine_redis()
    if not r.is_available():
        return set()
    return set(r.smembers(_key_pendientes(source, usuario)))


def set_pendiente(
    source: str, folder: str, pendiente: bool, usuario: str = "",
) -> None:
    r = _require_redis()
    clave = _key_pendientes(source, usuario)
    if pendiente:
        r.sadd(clave, folder)
    else:
        r.srem(clave, folder)
