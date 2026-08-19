"""WebSocket /ws/queue — empuja cambios de la cola al frontend en tiempo real.

Diseño:
- Polling interno cada 1s al `JobQueue.get_all()`. NO se modifica
  `manager.py` con hooks intrusivos.
- Por cada conexión activa se mantiene un snapshot del estado anterior.
  Al detectar diferencias se emite el delta como mensaje JSON.
- Eventos:
    snapshot → estado completo (al conectar)
    update   → cambio de status / nuevo job
    progress → progress / current_step (status sigue running)
    removed  → job que ya no está en la lista (clear_finished)
    pong     → respuesta a ping del cliente
- Auth: si `API_KEY` está configurada, se valida vía query param `?api_key=`.

ConnectionManager es un singleton (igual que `get_queue()`). En tests se
inyecta un manager fresco con `app.dependency_overrides`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status

from src.api.config import APISettings, get_settings
from src.api.dependencies import get_queue
from src.queue.manager import JobQueue
from src.queue.models import Job


logger = logging.getLogger("api.websockets.queue")
DEFAULT_POLL_INTERVAL_S = 1.0


# Trabajos de antes del multiusuario: se guardaron como "api-key-user" (o
# sin dueño). Son del admin, que era el único que había.
_SIN_DUENIO = {"", "api-key-user", "anonymous", "None"}


def _duenio(job: Job) -> str:
    quien = (job.enqueued_by or "").strip()
    return "" if quien in _SIN_DUENIO else quien


def _visible_para(job: Job, usuario: str, admin: bool) -> bool:
    """Cada uno ve LO SUYO; el admin ve además los huérfanos.

    Sin sesión (acceso por API key a secas) se ven todos: es el caso de una
    máquina, no de una persona.
    """
    if not usuario:
        return True
    duenio = _duenio(job)
    if duenio == usuario:
        return True
    return admin and not duenio


def _activos_de_otros(queue: JobQueue, usuario: str) -> dict[str, dict]:
    """Qué tiene cada uno de los DEMÁS ahora mismo.

    `{usuario: {"total": n, "ejecutando": n}}`. Antes era solo el total, y con
    eso no se distingue "Ana tiene tres esperando" de "Ana está renderizando" —
    que es lo que de verdad interesa mirar desde fuera.
    """
    fuera: dict[str, dict] = {}
    for j in queue.get_all():
        duenio = _duenio(j)
        if not duenio or duenio == usuario:
            continue
        estado = j.status.value
        if estado not in ("pending", "running"):
            continue
        d = fuera.setdefault(duenio, {"total": 0, "ejecutando": 0})
        d["total"] += 1
        if estado == "running":
            d["ejecutando"] += 1
    return fuera


def _job_payload(
    job: Job, posiciones: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Snapshot mínimo de un job para el WebSocket (subset de fields
    relevantes para la UI). Excluye `logs` por tamaño."""
    # ETA inteligente: blend self-based + histórico (samples Redis). Cae
    # silenciosamente a None si no hay datos. Cacheado por job_id.
    try:
        from src.queue.metrics import smart_eta_seconds
        eta = smart_eta_seconds(job)
    except Exception:
        eta = job.eta_s
    return {
        "job_id": job.id,
        "mode": job.mode.value,
        "title": job.title,
        "status": job.status.value,
        "progress_percent": round(max(0.0, min(1.0, job.progress)) * 100, 2),
        "current_step": job.progress_label or "",
        "elapsed_seconds": job.elapsed_s,
        "estimated_remaining_seconds": eta,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "enqueued_by": job.enqueued_by,
        "error": job.error,
        "result_path": job.result_path,
        "duration_seconds": job.duration_seconds,
        # Puesto REAL en la cola compartida (1 = el siguiente). `None` si no
        # está pendiente. El total va aparte para poder decir "3 de 9".
        "queue_position": (posiciones or {}).get(job.id),
        "queue_pending_total": len(posiciones) if posiciones is not None else 0,
    }


def _diff_jobs(
    old: dict[str, dict],
    new: dict[str, dict],
) -> tuple[list[dict], list[dict], list[str]]:
    """Compara dos snapshots de jobs por id. Devuelve `(updates, progress_only, removed_ids)`.

    - `updates`: jobs nuevos o con cambio de `status`. El frontend reescribe.
    - `progress_only`: jobs con cambio SOLO en progreso/step (mismo status).
      El frontend hace patch barato sin recolocar.
    - `removed_ids`: jobs que estaban en `old` pero ya no en `new`.
    """
    updates: list[dict] = []
    progress: list[dict] = []
    for jid, payload in new.items():
        if jid not in old:
            updates.append(payload)
            continue
        prev = old[jid]
        if prev["status"] != payload["status"]:
            updates.append(payload)
            continue
        if (
            prev["progress_percent"] != payload["progress_percent"]
            or prev["current_step"] != payload["current_step"]
            or prev["error"] != payload["error"]
            # El puesto en la cola cambia sin que el job se mueva (adelanta
            # porque el de delante ha terminado). Sin esto, un pendiente se
            # quedaba con el número del momento en que se encoló.
            or prev.get("queue_position") != payload.get("queue_position")
            or prev.get("queue_pending_total") != payload.get("queue_pending_total")
        ):
            progress.append(payload)
    removed = [jid for jid in old if jid not in new]
    return updates, progress, removed


class ConnectionManager:
    """Mantiene la lista de WebSockets activos y empuja diffs.

    Cada conexión registra un task asyncio que pollea `queue.get_all()`
    a intervalo fijo y emite deltas. Si el cliente se desconecta, el task
    se cancela limpiamente.
    """

    def __init__(self, *, poll_interval_s: float = DEFAULT_POLL_INTERVAL_S) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.poll_interval_s = poll_interval_s

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def serve(
        self, websocket: WebSocket, queue: JobQueue, usuario: str = "",
        admin: bool = False, ver_de: str = "",
    ) -> None:
        """Bucle principal por conexión: snapshot inicial + loop de polling
        + recepción de pings del cliente. Termina cuando el cliente desconecta.

        `usuario` filtra lo que se manda: la cola es por persona. Va aquí y no
        solo en el REST porque la interfaz se alimenta de ESTE socket — filtrar
        únicamente el endpoint REST no habría servido de nada.
        """
        # Un admin puede mirar la cola de otro (o la de todos). A quien no lo
        # es se le ignora: la URL del socket también se escribe a mano.
        mirado = ver_de if admin else ""
        efectivo = "" if mirado == "todos" else (mirado or usuario)

        # 1. Snapshot inicial
        # Las posiciones se calculan sobre la cola ENTERA (no sobre lo que se
        # ve): el puesto tiene que ser el de verdad, no el del subconjunto.
        posiciones = queue.posiciones_pendientes()
        snapshot = {
            j.id: _job_payload(j, posiciones) for j in queue.get_all()
            if _visible_para(j, efectivo, admin and not mirado)
        }
        await self._send_json(websocket, {
            "type": "snapshot",
            "data": {
                "jobs": list(snapshot.values()),
                "viendo": efectivo or "todos",
                "es_admin": admin,
                "otros": _activos_de_otros(queue, usuario) if admin else {},
            },
        })

        # 2. Tarea de polling concurrente con la recepción de mensajes
        recv_task = asyncio.create_task(self._receive_loop(websocket))
        poll_task = asyncio.create_task(
            self._poll_loop(
                websocket, queue, snapshot, efectivo,
                admin and not mirado, usuario if admin else "",
            )
        )
        try:
            done, pending = await asyncio.wait(
                {recv_task, poll_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        finally:
            await self.disconnect(websocket)

    async def _receive_loop(self, websocket: WebSocket) -> None:
        """Recibe mensajes del cliente. Solo soportamos `ping` por ahora."""
        try:
            while True:
                msg = await websocket.receive_json()
                if isinstance(msg, dict) and msg.get("type") == "ping":
                    await self._send_json(websocket, {"type": "pong", "data": {}})
        except WebSocketDisconnect:
            return
        except Exception as e:
            logger.warning("WebSocket recv error: %s", e)
            return

    async def _poll_loop(
        self,
        websocket: WebSocket,
        queue: JobQueue,
        snapshot: dict[str, dict],
        usuario: str = "",
        admin: bool = False,
        avisar_de_otros: str = "",
    ) -> None:
        otros_previo: dict[str, dict] = {}
        try:
            while True:
                await asyncio.sleep(self.poll_interval_s)
                posiciones = queue.posiciones_pendientes()
                current = {
                    j.id: _job_payload(j, posiciones) for j in queue.get_all()
                    if _visible_para(j, usuario, admin)
                }
                # Aviso al admin de que otro tiene trabajos en marcha. Solo se
                # manda cuando CAMBIA, para no llenar el socket de ruido.
                if avisar_de_otros:
                    otros = _activos_de_otros(queue, avisar_de_otros)
                    if otros != otros_previo:
                        otros_previo = otros
                        await self._send_json(websocket, {
                            "type": "otros", "data": {"otros": otros},
                        })
                updates, progress, removed = _diff_jobs(snapshot, current)
                if updates:
                    await self._send_json(websocket, {
                        "type": "update",
                        "data": {"jobs": updates},
                    })
                if progress:
                    await self._send_json(websocket, {
                        "type": "progress",
                        "data": {"jobs": progress},
                    })
                if removed:
                    await self._send_json(websocket, {
                        "type": "removed",
                        "data": {"job_ids": removed},
                    })
                snapshot = current
        except WebSocketDisconnect:
            return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("WebSocket poll error: %s", e)
            return

    @staticmethod
    async def _send_json(websocket: WebSocket, payload: dict) -> None:
        try:
            await websocket.send_json(payload)
        except WebSocketDisconnect:
            return
        except Exception as e:
            logger.warning("WebSocket send error: %s", e)


# Singleton
_MANAGER: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = ConnectionManager()
    return _MANAGER


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(tags=["websockets"])


@router.websocket("/ws/queue")
async def queue_ws(
    websocket: WebSocket,
    api_key: str | None = Query(default=None),
    de: str | None = Query(default=None),
    queue: JobQueue = Depends(get_queue),
    settings: APISettings = Depends(get_settings),
    manager: ConnectionManager = Depends(get_connection_manager),
) -> None:
    """WebSocket de la cola. Cliente debe pasar `?api_key=...` si el
    backend tiene `API_KEY` configurada en .env."""
    if settings.api_key and api_key != settings.api_key:
        # Cierre con 1008 = "Policy Violation"
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid api_key")
        return

    # Quién mira: sale del cookie de sesión, igual que en el resto de la API.
    from src.api import users
    from src.api.session import usuario_de_request

    quien = usuario_de_request(websocket) or ""

    await manager.connect(websocket)
    try:
        await manager.serve(
            websocket, queue, quien, users.es_admin(quien), (de or "").strip(),
        )
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WebSocket /ws/queue terminó con error: %s", e)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
    finally:
        await manager.disconnect(websocket)
