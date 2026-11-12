"""Puente Editor Auto → usuario de la fábrica (12/11/2026).

Un admin de la web del editor (p. ej. la cuenta de Néstor o «nueveness») puede
mandar a editar un vídeo «para» un usuario de la fábrica (ness, ana, nestor2…).
Cada envío así se apunta en `ediciones_fabrica:<usuario>` (Redis del editor,
Upstash) y los agentes lo ven con `ediciones_editor` del MCP: qué se editó, en
qué estado está y el MP4, para registrarlo en Mis tandas con su producto
(`registrar_replica_video(edicion=...)`).

No mete nada en Mis tandas por sí solo: allí cada fila necesita producto y
enlace, y eso lo pone el agente.
"""

from __future__ import annotations

import os
import time

from src.editor_auto.config import user_output_day_folder
from src.editor_auto.repos.redis_base import get_editor_redis

_CLAVE = "ediciones_fabrica:{usuario}"
_MAX = 500


def usuarios_validos() -> list[str]:
    from src.api import users

    return list(users.USUARIOS.keys())


def apuntar(usuario: str, editor_user, day: str, enqueued: list[dict]) -> None:
    """Añade los trabajos recién encolados al índice del usuario de fábrica."""
    if not usuario or not enqueued:
        return
    r = get_editor_redis()
    clave = _CLAVE.format(usuario=usuario)
    cur = r.get_json(clave)
    lista = cur if isinstance(cur, list) else []
    ahora = time.time()
    for e in enqueued:
        lista.append({
            "job_id": e.get("job_id"),
            "filename": e.get("filename"),
            "day": day,
            "editor_user": editor_user.name,
            "editor_user_id": editor_user.id,
            "ts": ahora,
        })
    r.set_json(clave, lista[-_MAX:])


def _buscar_salida(editor_user: str, day: str, filename: str) -> str | None:
    """Si el trabajo ya salió de la cola: el editado en `salida/<día>/`."""
    try:
        carpeta = user_output_day_folder(editor_user, day)
        base = os.path.splitext(filename or "")[0]
        if not base or not os.path.isdir(carpeta):
            return None
        for n in sorted(os.listdir(carpeta)):
            if n.startswith(base) and n.lower().endswith(".mp4"):
                return os.path.join(carpeta, n)
    except Exception:
        return None
    return None


def listar(usuario: str, queue, *, limite: int = 50) -> list[dict]:
    """Ediciones del usuario, las más nuevas primero, con estado y salida."""
    cur = get_editor_redis().get_json(_CLAVE.format(usuario=usuario))
    lista = cur if isinstance(cur, list) else []
    jobs = {j.id: j for j in queue.get_all()}
    out: list[dict] = []
    for e in reversed(lista[-limite:]):
        job = jobs.get(e.get("job_id"))
        if job is not None:
            estado = job.status.value if hasattr(job.status, "value") else str(job.status)
            ruta = job.result_path if job.result_path and os.path.exists(job.result_path) else None
            error = job.error
        else:
            ruta = _buscar_salida(e.get("editor_user", ""), e.get("day", ""), e.get("filename", ""))
            estado = "completed" if ruta else "desconocido"
            error = None
        out.append({
            **e,
            "estado": estado,
            "listo": bool(ruta),
            "salida": os.path.basename(ruta) if ruta else None,
            "error": error,
        })
    return out


def ruta_mp4(usuario: str, job_id: str, queue) -> str | None:
    for e in listar(usuario, queue, limite=_MAX):
        if e.get("job_id") == job_id:
            if not e["listo"]:
                return None
            job = next((j for j in queue.get_all() if j.id == job_id), None)
            if job is not None and job.result_path and os.path.exists(job.result_path):
                return job.result_path
            return _buscar_salida(e.get("editor_user", ""), e.get("day", ""), e.get("filename", ""))
    return None
