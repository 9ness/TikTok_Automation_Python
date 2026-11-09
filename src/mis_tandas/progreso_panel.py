"""Progreso de la tarea manual «Subir vídeos de …» del panel (panel.nebulabsmedia.com).

Cuando alguien marca o desmarca un vídeo como subido en Mis tandas, el progreso
de la tarea del día de esa cuenta pasa a ser el TOTAL de vídeos subidos hoy en
la cuenta (no se suma de uno en uno, así un desmarcado resta solo). El estado
de la tarea no se toca: la marca hecha Néstor.

Para otra cuenta, añade su usuario de la app y el id de la plantilla del panel
(Rutinas › plantilla, o `rutinas_ver` en el MCP del panel).
Sin `PANEL_URL`/`PANEL_TOKEN` en el `.env` no hace nada. Nunca tumba el marcado.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import threading
import time
import urllib.parse
import urllib.request
import zoneinfo

# usuario de la app → plantilla de la tarea manual «Subir vídeos» en el panel
PLANTILLA_VIDEOS: dict[str, int] = {
    "ness": 33,   # Viva Shop · «Subir vídeos de Viva Shop» (objetivo 20)
    # "ana": 30,  # Ama Shop · «Subir los vídeos del día» (pausada en el panel)
}

_TZ = zoneinfo.ZoneInfo("Europe/Madrid")
_ESPERA = 2.0   # agrupa los marcados en bloque (completar_tanda) en una sola llamada
_pendientes: set[str] = set()
_cerrojo = threading.Lock()
log = logging.getLogger(__name__)


def _peticion(metodo: str, ruta: str, cuerpo: dict | None = None):
    url = os.getenv("PANEL_URL", "").rstrip("/") + ruta
    req = urllib.request.Request(url, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo else None, headers={
        "Authorization": f"Bearer {os.getenv('PANEL_TOKEN', '')}", "X-Agente": "Mis tandas",
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode() or "null")


def subidos_hoy(usuario: str) -> int:
    from src.mis_tandas import servicio

    dia = dt.datetime.now(_TZ).date()
    return sum(1 for f in servicio.filas(usuario)
               if f["uploaded"] and f["uploaded_at"]
               and dt.datetime.fromtimestamp(f["uploaded_at"], _TZ).date() == dia)


def actualizar(usuario: str) -> dict | None:
    """Pone el progreso de la tarea de hoy = subidos hoy. Devuelve la tarea o None."""
    plantilla = PLANTILLA_VIDEOS.get(usuario)
    if not plantilla or not os.getenv("PANEL_URL") or not os.getenv("PANEL_TOKEN"):
        return None
    fecha = dt.datetime.now(_TZ).date().isoformat()
    tareas = _peticion("GET", "/api/tareas?" + urllib.parse.urlencode({"fecha": fecha, "manual": 1})) or []
    tarea = next((t for t in tareas if t.get("plantilla") == plantilla), None)
    if not tarea:
        return None
    n = subidos_hoy(usuario)
    if tarea.get("progreso") == n:
        return tarea
    return _peticion("PATCH", f"/api/tareas/{tarea['id']}", {"progreso": n})


def avisar(usuario: str) -> None:
    """Llamar tras marcar/desmarcar subido. En segundo plano y agrupado por usuario."""
    if usuario not in PLANTILLA_VIDEOS:
        return
    with _cerrojo:
        if usuario in _pendientes:
            return
        _pendientes.add(usuario)

    def _hilo() -> None:
        time.sleep(_ESPERA)
        with _cerrojo:
            _pendientes.discard(usuario)
        try:
            actualizar(usuario)
        except Exception as e:  # noqa: BLE001 — el panel caído no afecta a Mis tandas
            log.warning("progreso del panel (%s): %s", usuario, e)

    threading.Thread(target=_hilo, daemon=True).start()
