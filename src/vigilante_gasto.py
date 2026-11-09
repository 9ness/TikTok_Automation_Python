"""Vigilante de gasto de IA y de salud de la fábrica (tarea #293 del panel, 9/11/2026).

Análisis PURO (solo biblioteca estándar): lo usa el host, que no tiene las
dependencias de la app. Los datos los saca `scripts/vigilante_gasto.py` dentro
del contenedor y los avisos los manda `scripts/vigilante_gasto_avisar.py`.

Qué mira:
  · gasto del día por API (kind), modelo y modo, con la previsión del mes de
    Claude API frente al crédito de 100 $/mes;
  · un modo que se dispara: hoy más de ×3 su media diaria de los 7 días
    anteriores (y por encima de un mínimo, para no avisar por céntimos);
  · `/api/health/completo`: Drive, los dos Redis, disco y cola atascada.

Solo avisa. Nunca reinicia ni cambia nada.
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("Europe/Madrid")
PRESUPUESTO_CLAUDE_USD = 100.0  # créditos de la API que trae el plan Max (caducan cada mes)
FACTOR_DISPARO = 3.0
MINIMO_DISPARO_USD = 1.0  # por debajo de esto un ×3 es ruido
DIAS_MEDIA = 7
MIN_DIAS_HISTORIAL = 3  # con menos días con gasto, la media no sirve de referencia


def _dia(ts: float) -> str:
    return datetime.fromtimestamp(ts, ZONA).strftime("%Y-%m-%d")


def modelo_de(linea: dict) -> str:
    """Modelo de una línea de coste: `record_claude`/`record_gemini` lo ponen al
    principio del `detail` («claude-haiku-5-5 · in=…»). Si no hay, el kind."""
    detalle = str(linea.get("detail") or "")
    if linea.get("kind") in ("claude", "gemini", "openai_chat") and detalle:
        return detalle.split(" · ", 1)[0].strip() or str(linea.get("kind"))
    return str(linea.get("kind") or "?")


def adelgazar(jobs: Iterable[dict]) -> list[dict]:
    """Lo mínimo de cada JobCost para el análisis (sin títulos ni usuarios)."""
    out = []
    for j in jobs:
        lineas = [
            {"kind": l.get("kind"), "modelo": modelo_de(l), "usd": float(l.get("cost_usd") or 0)}
            for l in (j.get("lines") or [])
        ]
        if not lineas:
            continue
        out.append({"mode": j.get("mode") or "?", "ts": float(j.get("started_at") or 0), "lineas": lineas})
    return out


def resumen(jobs: list[dict], ahora: float) -> dict[str, Any]:
    """Gasto de hoy (hora de España) por API, modelo y modo; Claude del mes y su previsión.

    `jobs` es la salida de `adelgazar` (mes actual y anterior: la media de 7
    días necesita los últimos días del mes pasado a primeros de mes).
    """
    hoy = _dia(ahora)
    dt = datetime.fromtimestamp(ahora, ZONA)
    mes = dt.strftime("%Y-%m")
    dias_mes = calendar.monthrange(dt.year, dt.month)[1]
    previos = {(dt - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, DIAS_MEDIA + 1)}

    por_kind: dict[str, float] = defaultdict(float)
    por_modelo: dict[str, float] = defaultdict(float)
    por_modo: dict[str, float] = defaultdict(float)
    modo_previo: dict[str, float] = defaultdict(float)
    dias_modo: dict[str, set] = defaultdict(set)
    claude_mes = 0.0
    for j in jobs:
        dia = _dia(j["ts"])
        total = sum(l["usd"] for l in j["lineas"])
        if dia == hoy:
            por_modo[j["mode"]] += total
            for l in j["lineas"]:
                por_kind[l["kind"]] += l["usd"]
                por_modelo[l["modelo"]] += l["usd"]
        elif dia in previos:
            modo_previo[j["mode"]] += total
            dias_modo[j["mode"]].add(dia)
        if dia.startswith(mes):
            claude_mes += sum(l["usd"] for l in j["lineas"] if l["kind"] == "claude")

    # Días transcurridos contando hoy en fracción: a las 8:00 del día 1 no se
    # multiplica lo de 8 horas por 30 días enteros como si fuera un día entero.
    transcurrido = (dt.day - 1) + (dt.hour * 3600 + dt.minute * 60) / 86400
    prevision = claude_mes / max(transcurrido, 1.0) * dias_mes

    def _r(d: dict[str, float]) -> dict[str, float]:
        return {k: round(v, 3) for k, v in sorted(d.items(), key=lambda kv: -kv[1]) if v > 0}

    return {
        "dia": hoy,
        "total_hoy": round(sum(por_modo.values()), 3),
        "por_kind": _r(por_kind),
        "por_modelo": _r(por_modelo),
        "por_modo": _r(por_modo),
        # Media sobre los días que tuvieron gasto (no entre 7 fijos: diluiría un modo nuevo);
        # sin MIN_DIAS_HISTORIAL días no hay media y no se compara.
        "media_modo_7d": {k: round(v / len(dias_modo[k]), 3) for k, v in modo_previo.items()
                          if len(dias_modo[k]) >= MIN_DIAS_HISTORIAL},
        "claude_mes": round(claude_mes, 2),
        "claude_prevision_mes": round(prevision, 2),
        "presupuesto_claude": PRESUPUESTO_CLAUDE_USD,
    }


def avisos_gasto(r: dict[str, Any]) -> list[dict]:
    out = []
    if r["claude_prevision_mes"] > r["presupuesto_claude"]:
        out.append({
            "clave": f"gasto:claude_ritmo:{r['dia']}",
            "nivel": "aviso",
            "texto": (f"Claude API va a {r['claude_prevision_mes']:.0f} $ este mes "
                      f"(llevamos {r['claude_mes']:.2f} $; crédito {r['presupuesto_claude']:.0f} $). "
                      f"Hoy por modelo: {_top(r['por_modelo'])}."),
        })
    for modo, hoy in r["por_modo"].items():
        media = r["media_modo_7d"].get(modo, 0.0)
        if media > 0 and hoy >= MINIMO_DISPARO_USD and hoy > FACTOR_DISPARO * media:
            out.append({
                "clave": f"gasto:modo:{modo}:{r['dia']}",
                "nivel": "aviso",
                "texto": (f"Gasto disparado en «{modo}»: {hoy:.2f} $ hoy, ×{hoy / media:.1f} "
                          f"su media diaria de la última semana ({media:.2f} $/día)."),
            })
    return out


def _top(d: dict[str, float], n: int = 3) -> str:
    return ", ".join(f"{k} {v:.2f} $" for k, v in list(d.items())[:n]) or "nada"


def _limpio(x: Any) -> str:
    """Texto de una sonda sin URLs (podrían llevar credenciales) y recortado."""
    return re.sub(r"\w+://\S+", "<url>", str(x))[:200]


def avisos_salud(salud: dict | None) -> list[dict]:
    """Un aviso por cada sonda caída. `salud=None` = no se pudo llamar al endpoint."""
    if salud is None:
        return [{"clave": "salud:sin_respuesta", "nivel": "aviso",
                 "texto": "No contesta /api/health/completo de tiktok-api (¿contenedor caído o colgado?)."}]
    out = []
    for k in salud.get("fallos") or []:
        v = salud.get(k) or {}
        if k == "cola":
            atascados = v.get("atascados") or []
            detalle = "; ".join(
                f"{a.get('titulo') or a.get('title') or a.get('id', '?')} ({a.get('estado')}, {a.get('motivo', '')})"
                for a in atascados[:3]
            ) or _limpio(v)
            texto = (f"Cola atascada: {len(atascados)} trabajo(s). {detalle}" if atascados
                     else f"Cola sin workers vivos ({v.get('pendientes', 0)} pendientes).")
        else:
            texto = f"Salud de la fábrica: falla «{k}» ({_limpio(v.get('error') or v)})."
        out.append({"clave": f"salud:{k}", "nivel": "aviso", "texto": texto})
    return out


def nuevos(avisos: list[dict], estado: dict[str, float], ahora: float,
           repetir_s: float = 6 * 3600) -> tuple[list[dict], dict[str, float]]:
    """Avisa UNA vez por incidencia (y otra si sigue igual pasadas `repetir_s`).

    Las de salud que ya no fallan salen del estado, así que si vuelven a caer
    se avisa de nuevo. Las de gasto llevan el día en la clave: una por día.
    """
    activas = {a["clave"] for a in avisos}
    estado = {k: t for k, t in estado.items()
              if k in activas or (k.startswith("gasto:") and ahora - t < 3 * 86400)}
    out = []
    for a in avisos:
        t = estado.get(a["clave"])
        if t is None or (a["clave"].startswith("salud:") and ahora - t >= repetir_s):
            out.append(a)
            estado[a["clave"]] = ahora
    return out, estado
