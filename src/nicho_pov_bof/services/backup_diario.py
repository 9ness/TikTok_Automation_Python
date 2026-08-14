"""Lanza la copia del Drive del curso una vez al día, sin que nadie la pulse.

El admin de aquel Drive borra carpetas cada cierto tiempo y no avisa: "10
Agosto 2026" perdió ocho productos con los que ya se estaba trabajando, y solo
se salvaron porque justo dos días antes se había pulsado "Sincronizar" a mano.
Dejar la copia a merced de que alguien se acuerde es lo que hay que quitar.

Cómo:

- **Encola un job**, no copia aquí. Así sale en la cola con su progreso, usa el
  mismo runner que el botón y no bloquea el arranque de la API.
- **Una copia al día como mucho**, aunque la API se reinicie diez veces (cada
  deploy la reinicia): la marca del último intento va en Redis, no en memoria.
- Si el Drive no ha cambiado, `run_sync` no copia nada — mirar es barato.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

# Cada cuánto se comprueba si toca. No es cada cuánto se copia: eso lo decide
# la marca en Redis.
INTERVALO_S = 3600
CADA_S = 24 * 3600
_CLAVE = "backup:ultimo_intento"


def _repo():
    from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis

    return get_nicho_pov_bof_redis()


def _ultimo_intento() -> float:
    try:
        doc = _repo().get_json(_CLAVE) or {}
        return float(doc.get("ts") or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _marcar(ts: float) -> None:
    try:
        _repo().set_json(_CLAVE, {"ts": ts})
    except Exception:  # noqa: BLE001
        # Sin marca se reintentaría a la siguiente vuelta: molesto, no grave.
        logger.warning("backup diario: no pude guardar la marca en Redis")


def toca(ahora: float | None = None) -> bool:
    ahora = time.time() if ahora is None else ahora
    return ahora - _ultimo_intento() >= CADA_S


def lanzar() -> str:
    """Encola la copia y devuelve el id del job (vacío si no se pudo)."""
    from src.queue import get_queue
    from src.queue.models import JobMode, JobStatus

    cola = get_queue()
    # Si ya hay una copia esperando o en marcha, no se encola otra: dos rclone
    # a la vez sobre el mismo Drive solo se estorban.
    for j in cola.get_all() or []:
        if j.mode == JobMode.NICHO_POV_BOF_BACKUP and j.status in (
            JobStatus.PENDING, JobStatus.RUNNING,
        ):
            return ""
    job = cola.enqueue(
        JobMode.NICHO_POV_BOF_BACKUP,
        title="💾 Backup Productos España (diario)",
        params={"force_full": False},
    )
    return job.id


async def bucle(stop: asyncio.Event) -> None:
    """Comprueba cada hora si toca copiar. Pensado para el VPS 24/7."""
    while not stop.is_set():
        try:
            if toca():
                _marcar(time.time())
                job_id = lanzar()
                if job_id:
                    logger.info("backup diario encolado (%s)", job_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("backup diario falló al encolar: %s", e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=INTERVALO_S)
        except asyncio.TimeoutError:
            pass
