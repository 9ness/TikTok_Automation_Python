"""Tracking de carpetas de producto ya completadas.

El estado vive en Redis (SET por fuente), NUNCA en Drive — "Productos España"
es un Drive de terceros y es solo lectura.

Key: `nicho_pov_bof:completed:<source>` → SET de nombres de carpeta.
"""

from __future__ import annotations

from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis


def _key(source: str) -> str:
    return f"completed:{source}"


def _require_redis():
    r = get_nicho_pov_bof_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede leer/guardar el "
            "progreso del Nicho POV BOF. Define UPSTASH_REDIS_REST_URL y "
            "UPSTASH_REDIS_REST_TOKEN."
        )
    return r


def get_completed(source: str) -> set[str]:
    """Nombres de carpeta marcados como completados en esta fuente."""
    return set(_require_redis().smembers(_key(source)))


def is_completed(source: str, folder: str) -> bool:
    return _require_redis().sismember(_key(source), folder)


def mark_completed(source: str, folder: str) -> None:
    _require_redis().sadd(_key(source), folder)


def unmark_completed(source: str, folder: str) -> None:
    """Rollback — degrada en silencio si Redis no está (igual que viralización)."""
    r = get_nicho_pov_bof_redis()
    if r.is_available():
        r.srem(_key(source), folder)
