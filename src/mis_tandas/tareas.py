"""Tareas de «Campañas de creadores» de TikTok (cupones / dinero por subir N
vídeos de ciertos productos antes de una fecha).

Una tarea es solo una ETIQUETA sobre los vídeos de Mis tandas: no cambia
tandas ni orden. Se casa con cada vídeo por el ID de producto de TikTok (sale
de `product_url`) o por su sitio en el catálogo (`source|carpeta|producto`),
así un producto puede estar en varias tareas y un vídeo de cualquier nicho
cuenta. El progreso son los vídeos de sus productos marcados subidos DESDE que
se apuntó la tarea (lo de antes no cuenta para TikTok).

Redis: `mis_tandas:tareas:<usuario>` → {"tareas": [ {...}, ... ]}.
"""

from __future__ import annotations

import datetime as dt
import re
import time
import unicodedata
import zoneinfo

TAREAS_KEY = "mis_tandas:tareas:{usuario}"
_TZ = zoneinfo.ZoneInfo("Europe/Madrid")
_RE_PID = re.compile(r"/product/(\d{15,22})")
_RE_SOLO_PID = re.compile(r"^\d{15,22}$")


class ErrorTarea(Exception):
    def __init__(self, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.status = status


def _redis():
    from src.viralizacion.repos.redis_base import get_viralizacion_redis

    return get_viralizacion_redis()


def id_producto(url: str) -> str:
    m = _RE_PID.search(url or "")
    return m.group(1) if m else ""


def ref_de(f: dict) -> str:
    return f"{f.get('source', '')}|{f.get('carpeta', '')}|{f.get('producto', '')}"


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:40] or "tarea"


def _fin_ts(t: dict) -> float | None:
    fin = t.get("fin") or ""
    if not fin:
        return None
    try:
        d = dt.datetime.fromisoformat(fin)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_TZ)
    return d.timestamp()


def listar(usuario: str) -> list[dict]:
    """Las tareas del usuario. Son TEMPORALES: la que ya ha pasado su `fin` se
    borra de Redis al leerla, y con ella su filtro y su etiqueta en los vídeos."""
    r = _redis()
    if not r.is_available():
        return []
    todas = list((r.get_json(TAREAS_KEY.format(usuario=usuario or "ness")) or {}).get("tareas") or [])
    ahora = time.time()
    vivas = [t for t in todas if (_fin_ts(t) or ahora + 1) > ahora]
    if len(vivas) != len(todas):
        _guardar(usuario, vivas)
    return vivas


def _guardar(usuario: str, tareas: list[dict]) -> None:
    r = _redis()
    if not r.is_available():
        raise ErrorTarea("Redis no está disponible.", status=503)
    r.set_json(TAREAS_KEY.format(usuario=usuario or "ness"), {"tareas": tareas, "updated_at": time.time()})


def guardar(usuario: str, datos: dict) -> dict:
    """Crea o actualiza (por `id`) una tarea. `productos` acepta IDs de
    producto de TikTok o enlaces a la ficha; `refs` es `source|carpeta|producto`.
    `anadir=True` suma productos/refs a los que ya tenía en vez de sustituirlos."""
    nombre = str(datos.get("nombre") or "").strip()
    id_ = str(datos.get("id") or "").strip() or _slug(nombre)
    if not nombre and not datos.get("id"):
        raise ErrorTarea("Falta el nombre de la tarea.")
    productos = []
    for p in datos.get("productos") or []:
        p = str(p).strip()
        pid = p if _RE_SOLO_PID.match(p) else id_producto(p)
        if not pid:
            raise ErrorTarea(f"No es un ID ni un enlace de producto de TikTok: {p!r}")
        productos.append(pid)
    refs = [str(x).strip() for x in datos.get("refs") or [] if str(x).strip().count("|") == 2]
    if datos.get("fin"):
        try:
            dt.datetime.fromisoformat(str(datos["fin"]))
        except ValueError as e:
            raise ErrorTarea("`fin` tiene que ser fecha ISO (2026-10-30T17:00).") from e
    tareas = listar(usuario)
    previa = next((t for t in tareas if t["id"] == id_), None)
    t = dict(previa or {"id": id_, "creada_at": time.time(), "productos": [], "refs": []})
    for campo in ("nombre", "recompensa", "fin", "notas", "desde"):
        if datos.get(campo) is not None:
            t[campo] = str(datos[campo])
    if datos.get("videos_requeridos") is not None:
        t["videos_requeridos"] = max(0, int(datos["videos_requeridos"]))
    if datos.get("productos") is not None:
        base = t.get("productos", []) if datos.get("anadir") else []
        t["productos"] = list(dict.fromkeys(base + productos))
    if datos.get("refs") is not None:
        base = t.get("refs", []) if datos.get("anadir") else []
        t["refs"] = list(dict.fromkeys(base + refs))
    if datos.get("archivada") is not None:
        t["archivada"] = bool(datos["archivada"])
    t["updated_at"] = time.time()
    tareas = [x for x in tareas if x["id"] != id_] + [t]
    _guardar(usuario, tareas)
    return t


def borrar(usuario: str, id_: str) -> dict:
    tareas = listar(usuario)
    quedan = [t for t in tareas if t["id"] != id_]
    if len(quedan) == len(tareas):
        raise ErrorTarea(f"No hay ninguna tarea «{id_}».", status=404)
    _guardar(usuario, quedan)
    return {"ok": True, "borrada": id_}


def activa(t: dict, ahora: float | None = None) -> bool:
    if t.get("archivada"):
        return False
    fin = _fin_ts(t)
    return fin is None or fin > (ahora or time.time())


def de_fila(f: dict, tareas: list[dict]) -> list[str]:
    pid = id_producto(f.get("product_url", ""))
    ref = ref_de(f)
    return [t["id"] for t in tareas if (pid and pid in t.get("productos", [])) or ref in t.get("refs", [])]


def resumen(tareas: list[dict], filas: list[dict], ahora: float | None = None) -> list[dict]:
    """Progreso de cada tarea activa sobre TODAS las filas del usuario (también
    las de tandas cerradas): `filas` ya traen `tareas` (de `de_fila`)."""
    ahora = ahora or time.time()
    salida = []
    for t in tareas:
        if not activa(t, ahora):
            continue
        suyas = [f for f in filas if t["id"] in f.get("tareas", [])]
        desde = t.get("creada_at") or 0
        if t.get("desde"):
            try:
                d = dt.datetime.fromisoformat(t["desde"])
                desde = (d if d.tzinfo else d.replace(tzinfo=_TZ)).timestamp()
            except ValueError:
                pass
        con_video = {id_producto(f.get("product_url", "")) for f in suyas}
        fin = _fin_ts(t)
        salida.append({
            **{k: t.get(k) for k in ("id", "nombre", "recompensa", "fin", "notas")},
            "videos_requeridos": int(t.get("videos_requeridos") or 0),
            "videos": len(suyas),
            "subidos": sum(1 for f in suyas if f["uploaded"] and (f.get("uploaded_at") or 0) >= desde),
            "pendientes": sum(1 for f in suyas if not f["uploaded"] and not f["sin_stock"]),
            "productos": len(t.get("productos", [])) + len(t.get("refs", [])),
            "productos_sin_video": [p for p in t.get("productos", []) if p not in con_video],
            "faltan": max(0, int(t.get("videos_requeridos") or 0) - sum(
                1 for f in suyas if f["uploaded"] and (f.get("uploaded_at") or 0) >= desde)),
            "horas_restantes": round((fin - ahora) / 3600, 1) if fin else None,
        })
    salida.sort(key=lambda x: (x["horas_restantes"] is None, x["horas_restantes"] or 0))
    return salida
