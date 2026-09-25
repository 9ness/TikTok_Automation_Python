"""Trabajos largos del MCP que no caben en una llamada de herramienta.

Leer los textos de una carpeta del POV BOF es síncrono y tarda ~1 min; los
clientes MCP cortan antes. Se lanza aquí en segundo plano y la herramienta
contesta al momento con un id que se consulta con `estado`.

Vive en memoria del proceso (la API corre con UN worker a propósito, ver
Dockerfile.api): si se reinicia, se pierde el seguimiento pero no el trabajo
hecho — lo que se guardó, guardado está.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable

_TAREAS: dict[str, dict[str, Any]] = {}
_VIVAS: set[asyncio.Task] = set()
_MAX = 200


def lanzar(titulo: str, fn: Callable[[], Awaitable[Any]]) -> str:
    tid = "t_" + uuid.uuid4().hex[:10]
    _TAREAS[tid] = {"id": tid, "titulo": titulo, "estado": "en_marcha",
                    "inicio": time.time(), "resultado": None, "error": ""}

    async def _correr() -> None:
        try:
            _TAREAS[tid]["resultado"] = await fn()
            _TAREAS[tid]["estado"] = "hecha"
        except Exception as e:  # noqa: BLE001 — se reporta tal cual al agente
            _TAREAS[tid]["estado"] = "fallida"
            _TAREAS[tid]["error"] = str(e)
        finally:
            _TAREAS[tid]["fin"] = time.time()

    t = asyncio.get_running_loop().create_task(_correr())
    _VIVAS.add(t)
    t.add_done_callback(_VIVAS.discard)
    if len(_TAREAS) > _MAX:
        for viejo in sorted(_TAREAS, key=lambda k: _TAREAS[k]["inicio"])[: len(_TAREAS) - _MAX]:
            if _TAREAS[viejo]["estado"] != "en_marcha":
                _TAREAS.pop(viejo, None)
    return tid


def estado(tid: str) -> dict[str, Any] | None:
    return _TAREAS.get(tid)
