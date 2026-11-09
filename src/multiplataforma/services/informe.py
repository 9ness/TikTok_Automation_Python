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


def seccion_embudo(ultimo: dict) -> list[str]:
    """Página de la bio (`/links/<cuenta>`): visitas, clics y qué se abre.
    Sale en cuanto la lectura trae el dato, aunque sea cero: «nadie entra en
    la bio» también es una respuesta."""
    cuentas = {c: d["embudo"] for c, d in (ultimo.get("cuentas") or {}).items()
               if isinstance(d.get("embudo"), dict)}
    if not cuentas:
        return []
    l = ["## 🧭 Página de la bio (semana)", "",
         "Visitas a `/links/<cuenta>` y clics en un producto (personas, sin rastreadores; solo contadores).", ""]
    filas = []
    for c, e in sorted(cuentas.items()):
        v, k = int(e.get("visitas") or 0), int(e.get("clics") or 0)
        filas.append([c, _n(v), _n(k), f"{_n(round(100 * k / v, 1))} %" if v else "—"])
    l += _tabla(["cuenta", "visitas", "clics", "clics por visita"], filas)
    top = sorted(((c, p) for c, e in cuentas.items() for p in e.get("productos") or []),
                 key=lambda cp: -int(cp[1].get("clics") or 0))[:10]
    if top:
        l += ["", "Lo que más se abre:", ""]
        l += _tabla(["cuenta", "clics", "producto"],
                    [[c, _n(p.get("clics")), (p.get("titulo") or p.get("id") or "")[:60]] for c, p in top])
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


REPETIDO_MIN = 3  # veces que sale el mismo producto en la semana para avisar
HORAS_MIN_N = 3   # publicaciones por franja para comparar horas dentro de un formato


def repetidos(pubs: list[dict], minimo: int = REPETIDO_MIN) -> list[dict]:
    """Productos que han salido `minimo` veces o más en una cuenta (vídeos de producto)."""
    grupos: dict = collections.defaultdict(list)
    for m in pubs:
        if m.get("producto_ref") and (m.get("tipo") or "producto") == "producto":
            grupos[(m["cuenta"], m["producto_ref"])].append(m)
    out = []
    for (cuenta, _), ms in grupos.items():
        if len(ms) < minimo:
            continue
        ms.sort(key=lambda m: _ts(m) or 0)
        r = resumen([vistas(m, "instagram") for m in ms])
        out.append({"cuenta": cuenta, "titulo": ms[0].get("titulo") or "", "veces": len(ms),
                    "dias": [(m.get("fecha") or "")[8:] for m in ms], "mediana": r["mediana"] if r else None})
    return sorted(out, key=lambda x: (-x["veces"], x["cuenta"]))


def seccion_repetidos(semana: list[dict]) -> list[str]:
    """El mismo producto varias veces en la semana: a quien sigue la cuenta le sale lo mismo cada día."""
    rep = repetidos(semana)
    if not rep:
        return []
    l = [f"## 🔁 Mismo producto ≥{REPETIDO_MIN} veces (semana)", "",
         "Vídeos de producto del mismo artículo en la misma cuenta. La cola ya los separa "
         "(`MULTIPLATAFORMA_SEPARACION_PRODUCTO_DIAS`); si siguen saliendo aquí, faltan productos distintos en la cola.", ""]
    l += _tabla(["cuenta", "veces", "días", "mediana IG", "producto"],
                [[x["cuenta"], x["veces"], " ".join(x["dias"]), _n(x["mediana"]), x["titulo"][:45]] for x in rep[:10]])
    return l + [""]


def seccion_horas_por_formato(pubs: list[dict]) -> list[str]:
    """La hora, comparada DENTRO de cada formato. La tabla general de horas mezcla
    formatos (cada uno sale a la suya), así que ahí gana la hora del formato que
    más rinde, no la mejor hora. Solo formatos con dos franjas o más con datos."""
    def clave(m: dict):
        fr = franja(m)
        return (formato(m), fr) if fr else None

    g = {k: r for k, r in agrupar(pubs, clave).items() if r["n"] >= HORAS_MIN_N}
    por_formato: dict = collections.defaultdict(list)
    for (f, fr), r in g.items():
        por_formato[f].append((fr, r))
    filas, notas = [], []
    for f in sorted(por_formato):
        franjas = sorted(por_formato[f], key=lambda x: -x[1]["mediana"])
        if len(franjas) < 2:
            continue
        filas += [[f, fr, r["n"], _n(r["mediana"]), _n(r["max"])] for fr, r in franjas]
        (h1, r1), (h2, r2) = franjas[0], franjas[-1]
        if r2["mediana"] and r1["mediana"] / r2["mediana"] >= 1.5:
            notas.append(f"- `{f}`: a las {h1} hace {r1['mediana'] / r2['mediana']:.1f}× la mediana de las {h2} "
                         f"({_n(r1['mediana'])} vs {_n(r2['mediana'])}; n={r1['n']} y {r2['n']}). "
                         "Con tan pocas, es una pista, no una prueba.")
    if not filas:
        return []
    l = ["## Hora dentro de cada formato (histórico)", "",
         f"Solo franjas con ≥{HORAS_MIN_N} publicaciones del mismo formato; así la hora no se confunde con el formato.", ""]
    return l + _tabla(["formato", "franja", "n", "mediana", "máx"], filas) + [""] + notas + ([""] if notas else [])


def seccion_epocas(ultimo: dict) -> list[str]:
    """¿Cabe lo de temporada antes de que acabe su época? Solo sale si hay
    vídeos de temporada en cola."""
    filas, notas = [], []
    for c, d in sorted((ultimo.get("cuentas") or {}).items()):
        cap = d.get("epocas")
        if not isinstance(cap, dict):
            continue
        for e in cap.get("epocas") or []:
            filas.append([c, e["epoca"], f"{e['fin'][8:]}/{e['fin'][5:7]}", _n(e["pendientes"]),
                          _n(e["a_tiempo"]), _n(e["tarde"])])
        if cap.get("tarde"):
            falta = (cap.get("ritmo_necesario") or 0) > (cap.get("ritmo") or 0)
            notas.append(f"- **{c}**: {cap['tarde']} saldrían tarde. " +
                         (f"Para que quepan harían falta **{cap['ritmo_necesario']} vídeos de producto al día** "
                          f"(hoy {cap.get('ritmo')}): subir el ritmo o elegir cuáles se quedan fuera."
                          if falta else "Caben con el ritmo de hoy: basta ordenar la cola por época (replanificar)."))
        if cap.get("fuera_de_epoca"):
            notas.append(f"- **{c}**: {cap['fuera_de_epoca']} de una época que ya pasó esperan a la siguiente.")
    if not filas and not notas:
        return []
    l = ["## 🎄 Temporada: ¿cabe en la cola?", "",
         "Vídeos de producto pendientes de cada época y cuántos saldrían cuando ya ha pasado, con el reparto de hoy.", ""]
    if filas:
        l += _tabla(["cuenta", "época", "acaba", "en cola", "a tiempo", "tarde"], filas) + [""]
    return l + notas + ([""] if notas else [])


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
    l += seccion_horas_por_formato(todas)
    l += ["## Por día de la semana (histórico)", ""] + _tabla_grupos(agrupar(todas, dia_semana), "día") + [""]

    top = sorted((m for m in semana if vistas(m, "instagram") is not None), key=lambda m: -vistas(m, "instagram"))[:10]
    l += ["## Top 10 de la semana", ""]
    l += _tabla(["cuenta", "formato", "fecha", "IG", "Threads", "FB", "título"],
                [[m["cuenta"], formato(m), f"{m.get('fecha', '')} {m.get('hora', '')}".strip(), _n(vistas(m, "instagram")),
                  _n(vistas(m, "threads")), _n(vistas(m, "facebook")), (m.get("titulo") or "")[:45]] for m in top]) + [""]

    l += seccion_repetidos(semana)
    l += seccion_clics(semana)
    l += seccion_embudo(ultimo)
    l += seccion_epocas(ultimo)

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
