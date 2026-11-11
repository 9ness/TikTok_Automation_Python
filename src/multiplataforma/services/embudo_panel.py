"""Embudo de /links al panel (Cuentas › Tráfico, fuente `web:links_<slug>`).

El panel solo ve los clics que pasan por su redirector /r, y Amazon va directo
(sus normas): sin esto, las páginas de links no salían en el tráfico. Cada hora
se mandan hoy y ayer de cada cuenta activa con datos (`POST /api/trafico`); el
panel fusiona el mismo día, así que repetir no duplica. `rellenar()` manda
todos los días medidos de los últimos meses (una vez a mano). Solo días con
datos de verdad: nada de ceros anteriores al embudo.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import urllib.request
from zoneinfo import ZoneInfo

from src.multiplataforma import config
from src.multiplataforma.repos import cuentas_repo, enlaces_repo
from src.multiplataforma.repos.redis_base import get_redis

log = logging.getLogger(__name__)

_MAX_DESGLOSE = 200


def dias_del_mes(slug: str, anio: int, mes: int) -> dict[str, dict]:
    """{AAAA-MM-DD: {visitas, clics, productos{id: n}}} de los días con datos."""
    out: dict[str, dict] = {}
    for campo, n in get_redis().hgetall(f"embudo:{slug}:{anio:04d}-{mes:02d}").items():
        partes = campo.split(":", 2)
        try:
            dia = dt.date(anio, mes, int(partes[1])).isoformat()
            n = int(n)
        except (IndexError, ValueError, TypeError):
            continue
        fila = out.setdefault(dia, {"visitas": 0, "clics": 0, "productos": {}})
        if partes[0] == "v":
            fila["visitas"] += n
        elif partes[0] == "c" and len(partes) == 3:
            fila["clics"] += n
            fila["productos"][partes[2]] = fila["productos"].get(partes[2], 0) + n
    return out


def metricas(fila: dict, titulos: dict) -> dict:
    por_producto: dict[str, int] = {}
    for k, n in sorted(fila["productos"].items(), key=lambda kv: -kv[1]):
        t = str((titulos.get(k) or {}).get("titulo") or k).strip()[:80] or k
        if t not in por_producto and len(por_producto) >= _MAX_DESGLOSE:
            continue
        por_producto[t] = por_producto.get(t, 0) + n
    return {"visitas": fila["visitas"], "clics": fila["clics"], "clics_por_producto": por_producto}


def _enviar(slug: str, fecha: str, m: dict) -> None:
    req = urllib.request.Request(
        os.getenv("PANEL_URL", "").rstrip("/") + "/api/trafico", method="POST",
        data=json.dumps({"fuente": f"web:links_{slug}", "fecha": fecha, "metricas": m}).encode(),
        headers={"Authorization": f"Bearer {os.getenv('PANEL_TOKEN', '')}", "X-Agente": "Links bio",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()


def enviar(dias_atras: int = 1, meses: int | None = None) -> dict:
    """Manda al panel los días con datos: los últimos `dias_atras`+hoy, o con
    `meses` todos los días de este mes y los `meses-1` anteriores (relleno)."""
    if not (os.getenv("PANEL_URL") and os.getenv("PANEL_TOKEN")):
        return {"ok": False, "motivo": "sin PANEL_URL/PANEL_TOKEN"}
    hoy = dt.datetime.now(ZoneInfo(config.ZONA_HORARIA)).date()
    if meses:
        primero = (hoy.replace(day=1) - dt.timedelta(days=31 * (meses - 1))).replace(day=1)
    else:
        primero = hoy - dt.timedelta(days=dias_atras)
    meses_ = sorted({(d.year, d.month) for d in (primero + dt.timedelta(days=i)
                                                  for i in range((hoy - primero).days + 1))})
    hechos, fallos = [], []
    for c in cuentas_repo.listar():
        if not c.activa:
            continue
        titulos = None
        for anio, mes in meses_:
            for fecha, fila in sorted(dias_del_mes(c.slug, anio, mes).items()):
                if not primero.isoformat() <= fecha <= hoy.isoformat():
                    continue
                if titulos is None:
                    titulos = enlaces_repo.todos(c.slug)
                try:
                    _enviar(c.slug, fecha, metricas(fila, titulos))
                    hechos.append(f"{c.slug} {fecha}")
                except Exception as e:  # noqa: BLE001 — el panel caído no para el resto
                    fallos.append(f"{c.slug} {fecha}: {e}")
    if fallos:
        log.warning("embudo→panel: %d fallos (%s)", len(fallos), fallos[0])
    return {"ok": not fallos, "enviados": hechos, "fallos": fallos}


async def bucle(stop) -> None:
    """Cada hora, hoy y ayer al panel (el panel fusiona el mismo día)."""
    import asyncio

    while not stop.is_set():
        try:
            await asyncio.to_thread(enviar, 1)
        except Exception as e:  # noqa: BLE001
            log.warning("embudo→panel falló: %s", e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=3600)
        except asyncio.TimeoutError:
            pass
