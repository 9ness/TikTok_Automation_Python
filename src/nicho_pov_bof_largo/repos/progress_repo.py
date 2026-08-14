"""Tracking de carpetas de producto ya completadas en el Nicho POV BOF Largo.

Es un CALCO del `progress_repo` del Nicho POV BOF, pero con el cliente Redis y
el prefijo propios (`nicho_pov_bof_largo:`): las carpetas se comparten, el
progreso NO. Haber terminado una carpeta en el POV BOF no significa haberla
hecho aquí — son vídeos distintos del mismo producto.

Key: `nicho_pov_bof_largo:completed:<source>` → SET de nombres de carpeta.
"""

from __future__ import annotations

from src.nicho_pov_bof import config as pov_config

from src.nicho_pov_bof_largo.repos.redis_base import get_nicho_pov_bof_largo_redis


def _key(source: str, usuario: str = "") -> str:
    """Clave del progreso. Es POR USUARIO: cada uno va por su carpeta.

    `ness` se queda en la clave sin usuario (su histórico), igual que en el
    POV BOF, para no perder por dónde iba al separar cuentas.
    """
    # La copia de seguridad comparte progreso con la fuente del curso: son las
    # MISMAS carpetas, solo cambia de dónde se leen las fotos.
    source = pov_config.fuente_canonica(source)
    if not usuario or usuario == "ness":
        return f"completed:{source}"
    return f"completed:{source}:{usuario}"


def _require_redis():
    r = get_nicho_pov_bof_largo_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede leer/guardar el "
            "progreso del Nicho POV BOF Largo. Define UPSTASH_REDIS_REST_URL y "
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
    """Rollback — degrada en silencio si Redis no está."""
    r = get_nicho_pov_bof_largo_redis()
    if r.is_available():
        r.srem(_key(source, usuario), folder)
