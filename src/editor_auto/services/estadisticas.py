"""Estadísticas del Editor Auto y de nebulabsmedia.com, en LOCAL (SQLite).

Nada de Redis ni de servicios de pago: una base SQLite en el disco del
contenedor (`EDITOR_STATS_DB`, por defecto `/app/temp_work/estadisticas/`,
que es el disco ampliado del VPS donde ya vive el estado de la cola).

Qué guarda:
  - `eventos`: pasos del embudo. Los de la web (visita, precios, registro…)
    llegan por un beacon sin cookies; los del servidor (prueba empezada,
    vídeo enviado, descargado…) los apunta la API. La «sesión» de la web es
    un hash de día + IP + navegador con sal secreta: no se guarda la IP ni
    deja rastrear a nadie de un día a otro.
  - `trabajos`: un vídeo editado = una fila con segundos de render y dólares
    de IA (lo que ya mide `cost_tracking`).
  - `cuentas`: foto de cada cuenta web (alta, plan, vídeos de prueba) para la
    conversión prueba → pago. Se refresca desde Upstash cada pasada.

Todo es defensivo: un fallo aquí NUNCA rompe una petición ni un job.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Iterable

logger = logging.getLogger("editor_auto.estadisticas")

# Pasos del embudo en orden. Los `web_*` vienen del navegador (beacon); el
# resto, del servidor. Un tipo que no esté aquí se rechaza.
EMBUDO_WEB = ("visita", "precios", "registro_visto")
EMBUDO_SERVIDOR = ("registro", "prueba_empezada", "video_enviado", "video_listo",
                   "descarga", "pago")
TIPOS = EMBUDO_WEB + EMBUDO_SERVIDOR + ("login",)
# Rutas públicas que se apuntan como visita (el resto se ignora: panel, api…).
_RUTAS_WEB = ("/", "/precios", "/como-empezar", "/faq", "/resenas", "/contacto",
              "/registro", "/login")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_conn_path: str | None = None

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS eventos (
  id INTEGER PRIMARY KEY,
  ts REAL NOT NULL,
  dia TEXT NOT NULL,
  tipo TEXT NOT NULL,
  sesion TEXT,
  cuenta TEXT,
  ruta TEXT,
  origen TEXT,
  movil INTEGER,
  extra TEXT
);
CREATE INDEX IF NOT EXISTS ev_dia_tipo ON eventos(dia, tipo);
CREATE INDEX IF NOT EXISTS ev_cuenta ON eventos(cuenta, tipo);
CREATE TABLE IF NOT EXISTS trabajos (
  job_id TEXT PRIMARY KEY,
  usuario TEXT,
  dia TEXT,
  inicio REAL,
  fin REAL,
  seg_render REAL,
  coste_usd REAL,
  herramientas TEXT,
  estado TEXT
);
CREATE INDEX IF NOT EXISTS tr_usuario ON trabajos(usuario);
CREATE TABLE IF NOT EXISTS cuentas (
  cuenta TEXT PRIMARY KEY,
  usuario TEXT,
  alta TEXT,
  plan TEXT,
  rol TEXT,
  prueba_restante INTEGER,
  primer_pago TEXT,
  actualizada REAL
);
"""


def ruta_db() -> str:
    return os.getenv("EDITOR_STATS_DB") or "/app/temp_work/estadisticas/editor.sqlite"


def _db() -> sqlite3.Connection:
    global _conn, _conn_path
    path = ruta_db()
    if _conn is None or _conn_path != path:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        c = sqlite3.connect(path, check_same_thread=False, timeout=10)
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(_ESQUEMA)
        _conn, _conn_path = c, path
    return _conn


def _reset_para_tests() -> None:
    global _conn, _conn_path
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = _conn_path = None


def _hoy(ts: float | None = None) -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(ts or time.time(), ZoneInfo("Europe/Madrid")).date().isoformat()
    except Exception:  # noqa: BLE001
        return date.fromtimestamp(ts or time.time()).isoformat()


def cuenta_id(email: str | None) -> str | None:
    """Id estable y no reversible de una cuenta (no guardamos emails)."""
    if not email:
        return None
    sal = os.getenv("EDITOR_STATS_SALT") or os.getenv("API_KEY") or "nebulabs"
    return hashlib.sha256(f"{sal}|{email.strip().lower()}".encode()).hexdigest()[:16]


def sesion_anonima(ip: str | None, agente: str | None, dia: str | None = None) -> str:
    """Hash diario de IP + navegador: cuenta visitantes únicos de un día sin
    cookies y sin poder seguir a nadie al día siguiente (cambia cada día)."""
    sal = os.getenv("EDITOR_STATS_SALT") or os.getenv("API_KEY") or "nebulabs"
    base = f"{sal}|{dia or _hoy()}|{ip or ''}|{agente or ''}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def _es_movil(agente: str | None) -> int:
    a = (agente or "").lower()
    return int(any(x in a for x in ("iphone", "android", "mobile", "ipad")))


def _origen(ref: str | None, utm: str | None) -> str | None:
    if utm:
        return utm.strip().lower()[:40]
    if not ref:
        return None
    r = ref.lower()
    for nombre in ("tiktok", "instagram", "google", "facebook", "youtube", "bing", "whatsapp"):
        if nombre in r:
            return nombre
    if "nebulabsmedia" in r:
        return None  # navegación interna
    return "otro"


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------
def registrar_evento(tipo: str, *, cuenta: str | None = None, sesion: str | None = None,
                     ruta: str | None = None, origen: str | None = None,
                     movil: int | None = None, extra: str | None = None,
                     ts: float | None = None, unico: bool = False) -> bool:
    """Apunta un paso del embudo. `unico` = solo la primera vez por cuenta
    (p. ej. «prueba_empezada»). Devuelve si se apuntó. Nunca lanza."""
    if tipo not in TIPOS:
        return False
    ts = ts or time.time()
    try:
        with _lock:
            c = _db()
            if unico and cuenta:
                hay = c.execute("SELECT 1 FROM eventos WHERE cuenta=? AND tipo=? LIMIT 1",
                                (cuenta, tipo)).fetchone()
                if hay:
                    return False
            c.execute(
                "INSERT INTO eventos(ts,dia,tipo,sesion,cuenta,ruta,origen,movil,extra)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (ts, _hoy(ts), tipo, sesion, cuenta, (ruta or "")[:80] or None,
                 origen, movil, (extra or "")[:200] or None),
            )
            c.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[estadisticas] evento %s sin apuntar: %s", tipo, e)
        return False


def registrar_beacon(*, tipo: str, ruta: str | None, ref: str | None, utm: str | None,
                     ip: str | None, agente: str | None) -> bool:
    """Evento del navegador (público, sin login). Solo pasos web y rutas
    conocidas; los bots no cuentan."""
    if tipo not in EMBUDO_WEB:
        return False
    ruta = (ruta or "/").split("?")[0].split("#")[0].rstrip("/") or "/"
    if tipo == "visita" and ruta not in _RUTAS_WEB:
        return False
    a = (agente or "").lower()
    if not a or any(b in a for b in ("bot", "crawl", "spider", "preview", "headless", "lighthouse")):
        return False
    return registrar_evento(
        tipo, sesion=sesion_anonima(ip, agente), ruta=ruta,
        origen=_origen(ref, utm), movil=_es_movil(agente),
    )


def registrar_trabajo(job: dict) -> None:
    """Fila de un vídeo editado a partir del `JobCost.to_dict()` de
    cost_tracking. Idempotente por job_id. Nunca lanza."""
    try:
        if (job.get("program") or "") != "editor_auto":
            return
        ini = float(job.get("started_at") or 0) or None
        fin = float(job.get("finished_at") or 0) or None
        meta = job.get("meta") or {}
        coste = job.get("total_usd")
        if coste is None:
            coste = sum(float(l.get("cost_usd") or 0) for l in job.get("lines") or [])
        with _lock:
            c = _db()
            c.execute(
                "INSERT OR REPLACE INTO trabajos(job_id,usuario,dia,inicio,fin,seg_render,"
                "coste_usd,herramientas,estado) VALUES(?,?,?,?,?,?,?,?,?)",
                (job.get("job_id"), meta.get("editor_user") or job.get("user"), _hoy(ini) if ini else None, ini, fin,
                 round(fin - ini, 1) if ini and fin else None, round(float(coste), 6),
                 meta.get("tools_key"), meta.get("estado") or "hecho"),
            )
            c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("[estadisticas] trabajo sin apuntar: %s", e)


def actualizar_cuentas(cuentas: Iterable[dict], usuarios_por_email: dict[str, str] | None = None) -> int:
    """Foto de las cuentas web (`nebulabs:user:*`). Detecta el primer pago:
    cuando una cuenta pasa a tener plan, se apunta el día y el evento «pago»."""
    usuarios_por_email = usuarios_por_email or {}
    n = 0
    try:
        for a in cuentas:
            email = (a.get("email") or "").strip().lower()
            cid = cuenta_id(email)
            if not cid:
                continue
            plan = a.get("planId") or None
            rol = a.get("role") or None
            pagando = bool(plan) and rol != "admin"
            with _lock:
                c = _db()
                previa = c.execute("SELECT plan, primer_pago FROM cuentas WHERE cuenta=?",
                                   (cid,)).fetchone()
                primer_pago = previa[1] if previa else None
                nuevo_pago = pagando and not primer_pago
                if nuevo_pago:
                    primer_pago = _hoy()
                alta = (a.get("createdAt") or "")[:10] or None
                c.execute(
                    "INSERT OR REPLACE INTO cuentas(cuenta,usuario,alta,plan,rol,prueba_restante,"
                    "primer_pago,actualizada) VALUES(?,?,?,?,?,?,?,?)",
                    (cid, usuarios_por_email.get(email) or a.get("username"), alta, plan, rol,
                     a.get("trialVideos"), primer_pago, time.time()),
                )
                c.commit()
            if not previa and alta:
                registrar_evento("registro", cuenta=cid, ts=_ts_de_dia(alta), unico=True)
            if nuevo_pago:
                registrar_evento("pago", cuenta=cid, extra=plan, unico=True)
            n += 1
    except Exception as e:  # noqa: BLE001
        logger.warning("[estadisticas] cuentas sin actualizar: %s", e)
    return n


_ULTIMA_FOTO = {"ts": 0.0}
FOTO_CADA_S = 2 * 3600.0


def maybe_actualizar_cuentas(log=logger.info) -> int:
    """Foto de las cuentas web cada FOTO_CADA_S (lo llama el loop del
    draft_sweeper). Lee Upstash, pero escribe solo en local."""
    if time.time() - _ULTIMA_FOTO["ts"] < FOTO_CADA_S:
        return 0
    _ULTIMA_FOTO["ts"] = time.time()
    try:
        from src.editor_auto.repos import UserRepo
        from src.editor_auto.repos.web_account_repo import get_web_account_repo
        cuentas = get_web_account_repo().list_all()
        nombres = {(u.account_email or "").strip().lower(): u.name for u in UserRepo().list_all()
                   if getattr(u, "account_email", None) and not getattr(u, "deleted", False)}
    except Exception as e:  # noqa: BLE001
        log(f"[estadisticas] sin cuentas esta vez: {e}")
        return 0
    return actualizar_cuentas(cuentas, nombres)


def ip_cliente(headers: dict, directa: str | None) -> str | None:
    """IP real detrás de Caddy / Vercel (primer X-Forwarded-For)."""
    xff = headers.get("x-forwarded-for") or headers.get("x-real-ip") or ""
    return (xff.split(",")[0].strip() or directa) if xff else directa


def _ts_de_dia(dia: str) -> float:
    try:
        return datetime.fromisoformat(dia).replace(hour=12).timestamp()
    except Exception:  # noqa: BLE001
        return time.time()


# ---------------------------------------------------------------------------
# Lectura (página de admin)
# ---------------------------------------------------------------------------
def _rango(desde: str | None, hasta: str | None, dias: int = 30) -> tuple[str, str]:
    hasta = hasta or _hoy()
    desde = desde or (date.fromisoformat(hasta) - timedelta(days=dias - 1)).isoformat()
    return desde, hasta


def embudo(desde: str | None = None, hasta: str | None = None) -> list[dict]:
    """Cada paso con cuántos lo dieron en el rango. Web = sesiones únicas
    por día; servidor = cuentas únicas."""
    desde, hasta = _rango(desde, hasta)
    out: list[dict] = []
    with _lock:
        c = _db()
        for t in EMBUDO_WEB + EMBUDO_SERVIDOR:
            if t == "video_listo":  # clientes web con algún vídeo editado
                n = c.execute("SELECT COUNT(DISTINCT t.usuario) FROM trabajos t JOIN cuentas cu "
                              "ON cu.usuario=t.usuario WHERE t.estado='hecho' "
                              "AND t.dia BETWEEN ? AND ?", (desde, hasta)).fetchone()[0]
                out.append({"paso": t, "n": int(n or 0)})
                continue
            col = "dia || sesion" if t in EMBUDO_WEB else "cuenta"
            n = c.execute(f"SELECT COUNT(DISTINCT {col}) FROM eventos WHERE tipo=? "
                          "AND dia BETWEEN ? AND ?", (t, desde, hasta)).fetchone()[0]
            out.append({"paso": t, "n": int(n or 0)})
    prev = None
    for p in out:
        p["desde_anterior"] = (round(100 * p["n"] / prev, 1) if prev else None)
        prev = p["n"] or prev
    return out


def por_dia(desde: str | None = None, hasta: str | None = None) -> list[dict]:
    desde, hasta = _rango(desde, hasta)
    with _lock:
        c = _db()
        ev = c.execute(
            "SELECT dia, tipo, COUNT(DISTINCT COALESCE(cuenta, sesion)) FROM eventos "
            "WHERE dia BETWEEN ? AND ? GROUP BY dia, tipo", (desde, hasta)).fetchall()
        tr = c.execute(
            "SELECT dia, SUM(estado='hecho'), SUM(coste_usd), AVG(seg_render) FROM trabajos "
            "WHERE dia BETWEEN ? AND ? GROUP BY dia", (desde, hasta)).fetchall()
    dias: dict[str, dict] = {}
    d = date.fromisoformat(desde)
    while d.isoformat() <= hasta:
        dias[d.isoformat()] = {"dia": d.isoformat(), "videos": 0, "coste_usd": 0.0,
                               "seg_medio": None, **{t: 0 for t in TIPOS}}
        d += timedelta(days=1)
    for dia, tipo, n in ev:
        if dia in dias:
            dias[dia][tipo] = int(n)
    for dia, n, coste, seg in tr:
        if dia in dias:
            dias[dia].update(videos=int(n), coste_usd=round(coste or 0, 4),
                             seg_medio=round(seg, 1) if seg else None)
    return list(dias.values())


def por_cliente() -> list[dict]:
    """Una fila por cliente: alta, plan, prueba, vídeos, coste y tiempo."""
    with _lock:
        c = _db()
        cuentas = c.execute(
            "SELECT cuenta, usuario, alta, plan, rol, prueba_restante, primer_pago FROM cuentas"
        ).fetchall()
        tr = {u: (n, coste, seg, ult) for u, n, coste, seg, ult in c.execute(
            "SELECT usuario, SUM(estado='hecho'), SUM(coste_usd), AVG(seg_render), MAX(dia) "
            "FROM trabajos GROUP BY usuario").fetchall()}
        prueba = {cu: d for cu, d in c.execute(
            "SELECT cuenta, MIN(dia) FROM eventos WHERE tipo='prueba_empezada' GROUP BY cuenta"
        ).fetchall()}
    out = []
    for cid, usuario, alta, plan, rol, restante, pago in cuentas:
        n, coste, seg, ult = tr.get(usuario, (0, 0.0, None, None))
        out.append({
            "cuenta": cid, "usuario": usuario, "alta": alta, "plan": plan, "rol": rol,
            "prueba_restante": restante, "prueba_empezada": prueba.get(cid),
            "primer_pago": pago, "videos": int(n or 0),
            "coste_usd": round(coste or 0, 4),
            "coste_por_video": round((coste or 0) / n, 4) if n else None,
            "seg_medio": round(seg, 1) if seg else None, "ultimo_video": ult,
        })
    out.sort(key=lambda r: (-r["videos"], r["alta"] or ""))
    return out


def conversion(desde: str | None = None, hasta: str | None = None) -> dict:
    """Altas del rango y cuántas empezaron la prueba y cuántas pagan."""
    desde, hasta = _rango(desde, hasta, dias=90)
    with _lock:
        c = _db()
        altas = [r[0] for r in c.execute(
            "SELECT cuenta FROM cuentas WHERE alta BETWEEN ? AND ? AND COALESCE(rol,'')!='admin'",
            (desde, hasta)).fetchall()]
        if not altas:
            return {"desde": desde, "hasta": hasta, "altas": 0, "prueba": 0, "pago": 0,
                    "pct_prueba": None, "pct_pago": None}
        marcas = ",".join("?" * len(altas))
        prueba = c.execute(f"SELECT COUNT(DISTINCT cuenta) FROM eventos WHERE tipo='prueba_empezada'"
                           f" AND cuenta IN ({marcas})", altas).fetchone()[0]
        pago = c.execute(f"SELECT COUNT(*) FROM cuentas WHERE primer_pago IS NOT NULL"
                         f" AND cuenta IN ({marcas})", altas).fetchone()[0]
    n = len(altas)
    return {"desde": desde, "hasta": hasta, "altas": n, "prueba": prueba, "pago": pago,
            "pct_prueba": round(100 * prueba / n, 1), "pct_pago": round(100 * pago / n, 1)}


def coste_por_video(desde: str | None = None, hasta: str | None = None) -> dict:
    desde, hasta = _rango(desde, hasta)
    with _lock:
        c = _db()
        n, fallidos, coste, seg, seg_max = c.execute(
            "SELECT SUM(estado='hecho'), SUM(estado!='hecho'), SUM(coste_usd), AVG(seg_render), MAX(seg_render) FROM trabajos "
            "WHERE dia BETWEEN ? AND ?", (desde, hasta)).fetchone()
        combos = c.execute(
            "SELECT COALESCE(herramientas,'?'), COUNT(*), AVG(coste_usd), AVG(seg_render) "
            "FROM trabajos WHERE dia BETWEEN ? AND ? GROUP BY 1 ORDER BY 2 DESC",
            (desde, hasta)).fetchall()
    return {
        "videos": int(n or 0), "fallidos": int(fallidos or 0), "coste_usd": round(coste or 0, 4),
        "coste_medio_usd": round((coste or 0) / n, 4) if n else None,
        "seg_medio": round(seg, 1) if seg else None, "seg_max": round(seg_max, 1) if seg_max else None,
        "por_herramientas": [{"herramientas": h, "videos": k, "coste_medio_usd": round(cm or 0, 4),
                              "seg_medio": round(s, 1) if s else None} for h, k, cm, s in combos],
    }


def resumen(desde: str | None = None, hasta: str | None = None) -> dict[str, Any]:
    return {
        "rango": dict(zip(("desde", "hasta"), _rango(desde, hasta))),
        "embudo": embudo(desde, hasta),
        "conversion": conversion(),
        "coste": coste_por_video(desde, hasta),
        "por_dia": por_dia(desde, hasta),
        "clientes": por_cliente(),
    }
