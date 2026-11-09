"""Informe semanal de Meta a partir de los JSON de `scripts/multiplataforma_estadisticas.py`.

Solo biblioteca estándar: corre en el host (sin el contenedor) y no llama a
ninguna API. Junta todas las fotos guardadas en `~/multiplataforma/estadisticas`
(la más reciente manda para cada publicación) y escribe un Markdown con qué
formato, cuenta, hora y día rinde más, el top 10 y lo que no despega.

Las medias se rompen con un viral (25K frente a 100): se ordena por MEDIANA y la
media va solo de referencia. `None` es «sin dato», nunca 0.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
import statistics
from pathlib import Path

CAMPO_VISTAS = {"instagram": "views", "facebook": "fb_reels_total_plays", "threads": "views"}
IG_INTERACCION = ("likes", "comments", "shares", "saved")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
NOMBRE_JSON = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")
EDAD_MIN_FLOJO_H = 48  # antes de 2 días no se juzga si despega
FB_CERO_MAX = 2
VIRAL_VECES = 10  # «despegó» = ≥10× la mediana de su cuenta en IG
ESTADOS_BIEN = (":publicado", ":simulado")  # Pinterest sale simulado a propósito  # 0-2 reproducciones = «a cero» (las de los propios admins)


# ── carga ──────────────────────────────────────────────────────────────────

def cargar(carpeta: Path) -> list[tuple[str, dict]]:
    """[(fecha, informe)] de los `AAAA-MM-DD.json` válidos, del más viejo al más nuevo."""
    fotos = []
    for f in sorted(Path(carpeta).glob("*.json")):
        m = NOMBRE_JSON.match(f.name)
        if not m:
            continue
        try:
            fotos.append((m.group(1), json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    return fotos


def _clave(cuenta: str, m: dict) -> str:
    return f"{cuenta}:{m.get('pid') or m.get('id')}"


def _ts(m: dict) -> float | None:
    if m.get("ts"):
        return float(m["ts"])
    try:  # fotos viejas sin hora: mediodía del día publicado
        return dt.datetime.strptime(m["fecha"], "%Y-%m-%d").replace(hour=12).timestamp()
    except (KeyError, ValueError, TypeError):
        return None


def publicaciones(fotos: list[tuple[str, dict]]) -> list[dict]:
    """Cada publicación una vez, con las cifras de la foto más reciente que la trae."""
    juntas: dict[str, dict] = {}
    for fecha, inf in fotos:
        for cuenta, datos in (inf.get("cuentas") or {}).items():
            for m in datos.get("publicaciones") or []:
                juntas[_clave(cuenta, m)] = {**m, "cuenta": cuenta, "leido": fecha}
    return list(juntas.values())


# ── métricas de una publicación ────────────────────────────────────────────

def formato(m: dict) -> str:
    """El tipo de la cola, afinado por el título para los formatos con nombre propio."""
    titulo = (m.get("titulo") or "").lower()
    if "pablo motos" in titulo:
        return "viral_pablo_motos"
    if titulo.startswith("remedios"):
        return "remedios"
    return m.get("tipo") or "?"


def vistas(m: dict, plataforma: str):
    return (m.get(plataforma) or {}).get(CAMPO_VISTAS[plataforma])


def interaccion_ig(m: dict) -> float | None:
    """(me gusta + comentarios + compartidos + guardados) / vistas en IG, en %."""
    ig = m.get("instagram") or {}
    v = ig.get("views")
    partes = [ig.get(k) for k in IG_INTERACCION]
    if not v or all(p is None for p in partes):
        return None
    return 100 * sum(p or 0 for p in partes) / v


# ── estadística ────────────────────────────────────────────────────────────

def resumen(valores: list) -> dict | None:
    vs = [v for v in valores if v is not None]
    if not vs:
        return None
    return {"n": len(vs), "mediana": statistics.median(vs), "media": sum(vs) / len(vs), "max": max(vs)}


def agrupar(pubs: list[dict], clave, plataforma: str = "instagram") -> dict:
    grupos: dict = collections.defaultdict(list)
    for m in pubs:
        k = clave(m)
        if k is not None:
            grupos[k].append(vistas(m, plataforma))
    return {k: r for k, vs in grupos.items() if (r := resumen(vs))}


def franja(m: dict) -> str | None:
    h = m.get("hora")
    if not h:
        return None
    hh = int(h.split(":")[0])
    return f"{hh:02d}-{hh + 1:02d} h"


def dia_semana(m: dict) -> str | None:
    try:
        return DIAS[dt.datetime.strptime(m["fecha"], "%Y-%m-%d").weekday()]
    except (KeyError, ValueError, TypeError):
        return None


def flojas(pubs: list[dict], ahora: float) -> list[dict]:
    """Publicadas hace ≥48 h con vistas de IG por debajo de 1/4 de la mediana de su cuenta y formato."""
    por_grupo = agrupar(pubs, lambda m: (m["cuenta"], formato(m)))
    out = []
    for m in pubs:
        ts, v = _ts(m), vistas(m, "instagram")
        r = por_grupo.get((m["cuenta"], formato(m)))
        if ts is None or v is None or r is None or r["n"] < 3 or ahora - ts < EDAD_MIN_FLOJO_H * 3600:
            continue
        if v < r["mediana"] / 4:
            out.append({**m, "_ref": r["mediana"]})
    return sorted(out, key=lambda m: vistas(m, "instagram"))


def despegaron(pubs: list[dict]) -> list[dict]:
    """Las que hacen ≥VIRAL_VECES la mediana de IG de su cuenta (cualquier formato)."""
    medianas = {c: r["mediana"] for c, r in agrupar(pubs, lambda m: m["cuenta"]).items() if r["n"] >= 5}
    out = [{**m, "_veces": v / medianas[m["cuenta"]]} for m in pubs
           if (v := vistas(m, "instagram")) and medianas.get(m["cuenta"]) and v >= VIRAL_VECES * medianas[m["cuenta"]]]
    return sorted(out, key=lambda m: -m["_veces"])


def facebook_a_cero(pubs: list[dict]) -> tuple[int, int]:
    """(reels de FB a 0-2 reproducciones, reels de FB con dato)."""
    fb = [vistas(m, "facebook") for m in pubs]
    fb = [v for v in fb if v is not None]
    return sum(1 for v in fb if v <= FB_CERO_MAX), len(fb)


def seguidores(inf: dict) -> dict:
    out = {}
    for cuenta, datos in (inf.get("cuentas") or {}).items():
        for pl in ("instagram", "facebook", "threads"):
            out[(cuenta, pl)] = (datos.get(pl) or {}).get("seguidores")
    return out


def foto_anterior(fotos: list[tuple[str, dict]], dias: int = 7):
    """La foto más cercana a `dias` antes de la última (al menos 4 días antes), o None."""
    if len(fotos) < 2:
        return None
    ultima = dt.date.fromisoformat(fotos[-1][0])
    candidatas = [(f, inf) for f, inf in fotos[:-1] if (ultima - dt.date.fromisoformat(f)).days >= 4]
    if not candidatas:
        return None
    return min(candidatas, key=lambda x: abs((ultima - dt.date.fromisoformat(x[0])).days - dias))


# ── Markdown ───────────────────────────────────────────────────────────────

def _n(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.1f}".replace(",", "·").replace(".", ",").replace("·", ".")
    return f"{int(v):,}".replace(",", ".")


def _tabla(cabecera: list[str], filas: list[list]) -> list[str]:
    lineas = ["| " + " | ".join(cabecera) + " |", "|" + "---|" * len(cabecera)]
    lineas += ["| " + " | ".join(str(c) for c in f) + " |" for f in filas]
    return lineas


def _tabla_grupos(grupos: dict, nombre: str) -> list[str]:
    filas = [[k if isinstance(k, str) else " · ".join(k), r["n"], _n(r["mediana"]), _n(round(r["media"], 1)), _n(r["max"])]
             for k, r in sorted(grupos.items(), key=lambda kv: -kv[1]["mediana"])]
    return _tabla([nombre, "n", "mediana", "media", "máx"], filas)


def clics_total(m: dict) -> int:
    return sum(int(v or 0) for v in (m.get("clics") or {}).values())


def seccion_clics(pubs: list[dict]) -> list[str]:
    """Clics del enlace corto (#296). Sin ninguno, la sección no sale."""
    con = [m for m in pubs if clics_total(m)]
    if not con:
        return []
    por = collections.Counter()
    for m in con:
        for red, n in m["clics"].items():
            por[(m["cuenta"], red)] += int(n or 0)
    l = ["## 🔗 Clics en el enlace (semana)", "", "Clics acumulados de las publicadas esta semana (personas, sin rastreadores).", ""]
    l += _tabla(["cuenta", "red", "clics"], [[c, r, _n(n)] for (c, r), n in sorted(por.items(), key=lambda kv: -kv[1])])
    top = sorted(con, key=lambda m: -clics_total(m))[:10]
    l += ["", "Top 10 por clics:", ""]
    l += _tabla(["cuenta", "formato", "fecha", "clics", "IG vistas", "título"],
                [[m["cuenta"], formato(m), m.get("fecha", ""), _n(clics_total(m)), _n(vistas(m, "instagram")),
                  (m.get("titulo") or "")[:45]] for m in top])
    return l + [""]


def recomendaciones(pubs: list[dict]) -> list[str]:
    """Una línea por cuenta: el formato que más rinde frente al siguiente (por mediana de IG)."""
    out = []
    for cuenta in sorted({m["cuenta"] for m in pubs}):
        g = agrupar([m for m in pubs if m["cuenta"] == cuenta], formato)
        orden = sorted(((k, r) for k, r in g.items() if r["n"] >= 3), key=lambda kv: -kv[1]["mediana"])
        if len(orden) < 2:
            out.append(f"- **{cuenta}**: pocos datos (hacen falta ≥3 publicaciones de 2 formatos).")
            continue
        (f1, r1), (f2, r2) = orden[0], orden[1]
        veces = r1["mediana"] / r2["mediana"] if r2["mediana"] else None
        if veces and veces >= 1.5:
            out.append(f"- **{cuenta}**: `{f1}` rinde {veces:.1f}× más que `{f2}` (mediana {_n(r1['mediana'])} vs "
                       f"{_n(r2['mediana'])} vistas IG). Candidato a subir su ritmo (decide Néstor).")
        else:
            out.append(f"- **{cuenta}**: sin formato claramente mejor (`{f1}` {_n(r1['mediana'])} vs `{f2}` "
                       f"{_n(r2['mediana'])}). Mantener.")
    return out


def generar(fotos: list[tuple[str, dict]], ahora: float | None = None, dias: int = 7) -> str:
    """El Markdown del informe. `dias` = ventana de «esta semana» para top y tablas."""
    if not fotos:
        return "# Informe Meta\n\nSin datos: no hay ningún JSON de estadísticas.\n"
    ahora = ahora if ahora is not None else dt.datetime.now().timestamp()
    fecha, ultimo = fotos[-1]
    todas = publicaciones(fotos)
    semana = [m for m in todas if (_ts(m) or 0) >= ahora - dias * 86400]
    l = [f"# Informe Meta · semana hasta {fecha}", "",
         f"{len(semana)} publicaciones en los últimos {dias} días · {len(todas)} en el histórico ({len(fotos)} lecturas).",
         "Vistas de **Instagram** salvo que se diga otra cosa. Se ordena por mediana: un viral no tapa al resto.", ""]

    cero, con_dato = facebook_a_cero(semana)
    if con_dato and cero == con_dato:
        l += [f"> ⚠️ **Facebook a cero**: los {con_dato} reels de FB de la semana tienen 0-{FB_CERO_MAX} reproducciones. "
              "Sigue el modo desarrollo de la app (tarea 225).", ""]
    elif con_dato:
        l += [f"> Facebook: {con_dato - cero} de {con_dato} reels con más de {FB_CERO_MAX} reproducciones.", ""]

    errores = {c: d.get("errores") for c, d in (ultimo.get("cuentas") or {}).items() if d.get("errores")}
    if errores:
        l += ["## ⚠️ Errores de la API en la última lectura", ""]
        l += [f"- **{c}**: {len(e)} · {'; '.join(e[:3])}" for c, e in errores.items()] + [""]

    l += ["## Recomendación por cuenta (histórico)", ""] + recomendaciones(todas) + [""]
    virales = despegaron(todas)
    if virales:
        l += [f"## 🚀 Despegaron (≥{VIRAL_VECES}× la mediana de su cuenta, histórico)", ""]
        l += [f"- **{m['cuenta']}** · `{formato(m)}` · {m.get('fecha', '')}: {_n(vistas(m, 'instagram'))} vistas IG "
              f"({m['_veces']:.0f}×) — {(m.get('titulo') or '')[:60]}" for m in virales[:5]] + [""]

    ant = foto_anterior(fotos)
    seg_hoy = seguidores(ultimo)
    seg_ant = seguidores(ant[1]) if ant else {}
    l += ["## Seguidores", ""]
    filas = []
    for (cuenta, pl), v in sorted(seg_hoy.items()):
        a = seg_ant.get((cuenta, pl))
        dif = f"{v - a:+d}" if isinstance(v, int) and isinstance(a, int) else "—"
        filas.append([cuenta, pl, _n(v), dif])
    l += _tabla(["cuenta", "plataforma", "seguidores", f"vs {ant[0] if ant else '—'}"], filas) + [""]

    l += ["## Por cuenta y formato (semana)", ""]
    l += _tabla_grupos(agrupar(semana, lambda m: (m["cuenta"], formato(m))), "cuenta · formato") + [""]
    l += ["## Por formato y plataforma (semana)", ""]
    filas = []
    for pl in ("instagram", "threads", "facebook"):
        for k, r in sorted(agrupar(semana, formato, pl).items(), key=lambda kv: -kv[1]["mediana"]):
            filas.append([pl, k, r["n"], _n(r["mediana"]), _n(r["max"])])
    l += _tabla(["plataforma", "formato", "n", "mediana", "máx"], filas) + [""]

    inter = collections.defaultdict(list)
    for m in semana:
        if (i := interaccion_ig(m)) is not None:
            inter[formato(m)].append(i)
    if inter:
        l += ["## Interacción en IG (semana)", "", "(me gusta + comentarios + compartidos + guardados) / vistas.", ""]
        l += _tabla(["formato", "n", "mediana %"],
                    [[k, len(v), _n(round(statistics.median(v), 1))] for k, v in sorted(inter.items())]) + [""]

    l += ["## Por hora de publicación (histórico)", ""]
    horas = agrupar(todas, franja)
    l += (_tabla_grupos(horas, "franja") if horas else ["Sin horas aún (las lecturas viejas no las guardaban)."]) + [""]
    l += ["## Por día de la semana (histórico)", ""] + _tabla_grupos(agrupar(todas, dia_semana), "día") + [""]

    top = sorted((m for m in semana if vistas(m, "instagram") is not None), key=lambda m: -vistas(m, "instagram"))[:10]
    l += ["## Top 10 de la semana", ""]
    l += _tabla(["cuenta", "formato", "fecha", "IG", "Threads", "FB", "título"],
                [[m["cuenta"], formato(m), f"{m.get('fecha', '')} {m.get('hora', '')}".strip(), _n(vistas(m, "instagram")),
                  _n(vistas(m, "threads")), _n(vistas(m, "facebook")), (m.get("titulo") or "")[:45]] for m in top]) + [""]

    l += seccion_clics(semana)

    flo = [m for m in flojas(todas, ahora) if (_ts(m) or 0) >= ahora - dias * 86400][:10]
    l += ["## No despegan (semana, ≥48 h y < 1/4 de la mediana de su cuenta y formato)", ""]
    l += (_tabla(["cuenta", "formato", "fecha", "IG", "mediana ref.", "título"],
                 [[m["cuenta"], formato(m), m.get("fecha", ""), _n(vistas(m, "instagram")), _n(m["_ref"]),
                   (m.get("titulo") or "")[:45]] for m in flo]) if flo else ["Ninguna."]) + [""]

    salud = ["## Salud de la cola (última lectura)", ""]
    for c, d in (ultimo.get("cuentas") or {}).items():
        s = d.get("salud") or {}
        malos = {k: v for k, v in (s.get("estados") or {}).items() if not k.endswith(ESTADOS_BIEN)}
        salud.append(f"- **{c}**: en cola {d.get('en_cola', '—')} · comentarios FB fallidos "
                     f"{s.get('comentarios_fb_fallidos', '—')} · otros estados {malos or 'ninguno'}")
    return "\n".join(l + salud) + "\n"
