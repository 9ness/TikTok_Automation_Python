"""Salud completa de la fábrica: lo que el panel de mando NO ve.

El panel (panel.nebulabsmedia.com) ya vigila el VPS desde fuera: CPU, RAM,
disco, contenedores, servicios caídos, móviles y cron. Lo que no puede ver es
lo de DENTRO de la app, y eso es lo que se mira aquí:

  · los dos Redis (el local de la fábrica y el Upstash compartido de Editor
    Auto/Pronósticos): si responden y cuánto tardan;
  · el Drive montado: si se puede leer (un FUSE colgado deja la API "healthy"
    pero sin Drive, ver learnings 6/11);
  · la cola: workers vivos y trabajos ATASCADOS (corriendo demasiado tiempo,
    o pendientes sin que nadie los coja).

`GET /api/health` sigue siendo el latido barato del healthcheck de Docker; este
es el caro y va con sesión.

Endpoint:
  GET /api/health/completo
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Iterable

from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user, get_queue
from src.queue.models import Job, JobStatus


router = APIRouter(
    prefix="/api/health",
    tags=["meta"],
    dependencies=[Depends(get_current_user)],
)

# Un vídeo normal tarda 5-20 min; el más largo (Viralización en lote) ronda la
# hora. Pasado esto, "corriendo" casi seguro es un worker colgado.
CORRIENDO_MAX_S = float(os.getenv("SALUD_CORRIENDO_MAX_MIN", "60")) * 60
# Pendiente sin NADA corriendo: la cola debería cogerlo en segundos.
PENDIENTE_MAX_S = float(os.getenv("SALUD_PENDIENTE_MAX_MIN", "10")) * 60
# Lo que puede tardar cada sonda antes de darla por caída (un FUSE colgado no
# devuelve nunca: sin tope, la petición se quedaría esperando con él).
_TOPE_SONDA_S = 4.0



def _sondear(sondas: dict) -> dict:
    """Lanza todas las sondas a la vez, cada una en su hilo, con un tope común.

    Hilos sueltos (daemon) y no un pool: una sonda colgada en un FUSE muerto
    no vuelve nunca, y en un pool se quedaría con el hilo para siempre hasta
    agotarlo. Así, como mucho, queda un hilo dormido por llamada mientras el
    Drive siga caído.
    """
    import threading

    res: dict[str, dict] = {}
    hilos = []
    t0 = time.monotonic()

    def correr(nombre, fn):
        try:
            extra = dict(fn() or {})
            ok = extra.pop("ok", True)
            res[nombre] = {"ok": ok, "ms": int((time.monotonic() - t0) * 1000), **extra}
        except Exception as e:  # noqa: BLE001
            res[nombre] = {"ok": False, "ms": int((time.monotonic() - t0) * 1000), "error": str(e)[:200]}

    for nombre, fn in sondas.items():
        h = threading.Thread(target=correr, args=(nombre, fn), daemon=True, name=f"salud-{nombre}")
        h.start()
        hilos.append(h)
    limite = t0 + _TOPE_SONDA_S
    for h in hilos:
        h.join(timeout=max(0.0, limite - time.monotonic()))
    for nombre in sondas:
        res.setdefault(nombre, {"ok": False, "ms": int(_TOPE_SONDA_S * 1000),
                                "error": f"no responde en {_TOPE_SONDA_S:.0f} s"})
    return {k: res[k] for k in sondas}


def _ping(cliente) -> dict:
    if not cliente.is_available():
        return {"ok": False, "error": "sin configurar"}
    res = cliente._get("ping", timeout=_TOPE_SONDA_S)
    return {"ok": res == "PONG"} if res == "PONG" else {"ok": False, "error": "sin PONG"}


def _redis_fabrica() -> dict:
    from src.viralizacion.repos.redis_base import get_viralizacion_redis

    return _ping(get_viralizacion_redis())


def _redis_compartido() -> dict:
    from src.editor_auto.repos.redis_base import get_editor_redis

    return _ping(get_editor_redis())


def _drive() -> dict:
    from src.rutas_drive import raiz_drive

    raiz = raiz_drive()
    if not raiz.is_dir():
        return {"ok": False, "error": f"{raiz} no existe"}
    # `Nebulabs/` es lo único que está seguro en la raíz (docs/DRIVE.md).
    n = sum(1 for _ in os.scandir(raiz))
    return {"ok": n > 0, "entradas": n, **({} if n else {"error": "montaje vacío"})}


def _disco(ruta: str) -> dict:
    u = shutil.disk_usage(ruta)
    libre = round(u.free / 1024**3, 1)
    return {"ok": libre >= 5, "libre_gb": libre, "uso_pct": round(u.used / u.total * 100, 1)}


def analizar_cola(jobs: Iterable[Job], ahora: float, workers_vivos: int | None = None) -> dict:
    """Resumen de la cola y lista de lo atascado. Pura: se prueba sin hilos."""
    pendientes: list[Job] = []
    corriendo: list[Job] = []
    for j in jobs:
        if j.status == JobStatus.PENDING:
            pendientes.append(j)
        elif j.status == JobStatus.RUNNING:
            corriendo.append(j)

    atascados: list[dict[str, Any]] = []
    for j in corriendo:
        t = ahora - (j.started_at or j.created_at)
        if t > CORRIENDO_MAX_S:
            atascados.append(_fila(j, "corriendo", t, f"lleva {int(t // 60)} min corriendo"))
    if not corriendo:
        # Solo cuenta lo que ya debería haber empezado: lo programado para
        # la madrugada espera a propósito.
        for j in pendientes:
            if j.scheduled_for and j.scheduled_for > ahora:
                continue
            t = ahora - max(j.created_at, j.scheduled_for or 0)
            if t > PENDIENTE_MAX_S:
                atascados.append(_fila(j, "pendiente", t, f"{int(t // 60)} min en cola sin que nadie lo coja"))

    out: dict[str, Any] = {
        "pendientes": len(pendientes),
        "corriendo": len(corriendo),
        "atascados": atascados,
    }
    if workers_vivos is not None:
        out["workers_vivos"] = workers_vivos
    out["ok"] = not atascados and workers_vivos != 0
    return out


def _fila(j: Job, estado: str, segundos: float, motivo: str) -> dict:
    return {
        "id": j.id,
        "modo": getattr(j.mode, "value", str(j.mode)),
        "titulo": (j.title or "")[:80],
        "estado": estado,
        "minutos": int(segundos // 60),
        "progreso": round(j.progress or 0, 2),
        "etiqueta": (j.progress_label or "")[:80],
        "usuario": j.enqueued_by,
        "motivo": motivo,
    }


def _workers_vivos(queue) -> int | None:
    workers = getattr(queue, "_workers", None)
    if workers is None:
        return None
    return sum(1 for t in workers if t.is_alive())


@router.get("/completo")
def salud_completa(queue=Depends(get_queue)) -> dict:
    """Todas las sondas en paralelo, cada una con su tope (≈4 s en el peor caso)."""
    sondas = {
        "redis_fabrica": _redis_fabrica,
        "redis_compartido": _redis_compartido,
        "drive": _drive,
        "disco_trabajo": lambda: _disco("temp_work" if Path("temp_work").is_dir() else "/"),
    }
    res: dict[str, Any] = _sondear(sondas)
    res["cola"] = analizar_cola(queue.get_all(), time.time(), _workers_vivos(queue))
    fallos = [k for k, v in res.items() if not v.get("ok")]
    return {"ok": not fallos, "fallos": fallos, **res}
