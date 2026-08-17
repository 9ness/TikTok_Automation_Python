"""Tracking de carpetas de producto ya completadas.

El estado vive en Redis (SET por fuente), NUNCA en Drive — "Productos España"
es un Drive de terceros y es solo lectura.

Key: `nicho_carruseles:completed:<source>` → SET de nombres de carpeta.

Progreso INDEPENDIENTE del Nicho POV BOF aunque las carpetas sean las mismas:
completar "1 Pront Flow" allí no la completa aquí: el vídeo y el carrusel son
dos publicaciones distintas del mismo producto.
"""

from __future__ import annotations

from src.nicho_carruseles.repos.redis_base import get_nicho_carruseles_redis


def _key(source: str, usuario: str = "") -> str:
    """Clave del progreso. Es POR USUARIO: cada uno va por su carpeta.

    El histórico (sin usuario) se conserva como clave de `ness`, que es quien
    lo generó — así no pierde por dónde iba al separar las cuentas.
    """
    if not usuario or usuario == "ness":
        return f"completed:{source}"
    return f"completed:{source}:{usuario}"


def _require_redis():
    r = get_nicho_carruseles_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede leer/guardar el "
            "progreso del Nicho Carruseles. Define UPSTASH_REDIS_REST_URL y "
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
    r = get_nicho_carruseles_redis()
    if r.is_available():
        r.srem(_key(source, usuario), folder)
