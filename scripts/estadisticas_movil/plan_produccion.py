#!/usr/bin/env python3
"""Plan de producción diario hacia lo que vende. Solo lectura: no genera ni sube nada.

A partir del volcado de que_vende.py (vídeos, carruseles y ventas de una cuenta):
  1. clasifica cada formato: «vende» (tiene pedidos), «sin datos» (pocas publicaciones con
     ventana suficiente antes del corte de ventas) o «dejar» (≥MIN_PUB con ventana y 0 pedidos);
  2. reparte el cupo diario: la mayor parte al formato que más vende por publicación, algo a
     los otros que venden y un hueco fijo para seguir probando lo que aún no tiene datos;
  3. lista candidatos de la categoría que vende (bolso…): variantes de los productos con
     ventas primero y luego los que tienen menos contenido.

Uso:  python3 -I scripts/estadisticas_movil/plan_produccion.py ana --desde-fichero ana.json [--cupo 6] [--bandit [--semilla N]] [--out x.md] [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path


def _cargar(nombre: str, fichero: str):
    spec = importlib.util.spec_from_file_location(nombre, Path(__file__).with_name(fichero))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


qv = _cargar("que_vende_plan", "que_vende.py")
dg = _cargar("diag_carr_plan", "diagnostico_carruseles.py")

MIN_PUB = 5          # publicaciones con ventana para dar un formato por muerto
MIN_VENTANA = 3      # días antes del corte para que una publicación cuente
PESO_TOP = 0.6       # parte del cupo para el formato que más vende
EXPLORAR = 0.2       # parte del cupo para lo que aún no tiene datos


def clasificar(datos: dict, analisis: dict | None = None) -> list[dict]:
    """Formatos con su estado: vende / sin datos / dejar, y cuántas publicaciones tenían ventana."""
    r = analisis or qv.analizar(datos)
    corte = qv._fecha((datos.get("ventas") or {}).get("actualizado"))
    con_ventana: Counter = Counter()
    for p in qv.publicados(datos):
        if corte and (corte - p["fecha"]).days >= MIN_VENTANA:
            con_ventana[p["formato"]] += 1
    out = []
    for f in r["formatos"]:
        n = con_ventana.get(f["formato"], 0)
        estado = "vende" if f["pedidos"] else ("dejar" if n >= MIN_PUB else "sin datos")
        out.append({**f, "con_ventana": n, "estado": estado,
                    "tasa": f["pedidos"] / n if n else (f["pedidos"] / f["publicados"] if f["publicados"] else 0)})
    return out


def _redondeo(pesos: dict[str, float], total: int) -> dict[str, int]:
    """Reparte `total` en enteros proporcionales a `pesos` (método del mayor resto, estable por orden)."""
    s = sum(pesos.values())
    if not s or total <= 0:
        return {k: 0 for k in pesos}
    exactos = {k: total * w / s for k, w in pesos.items()}
    base = {k: int(v) for k, v in exactos.items()}
    resto = total - sum(base.values())
    for k in sorted(pesos, key=lambda k: -(exactos[k] - base[k]))[:resto]:
        base[k] += 1
    return base


def reparto(formatos: list[dict], cupo: int, peso_top: float = PESO_TOP, explorar: float = EXPLORAR) -> dict[str, int]:
    """Cuántas piezas al día de cada formato. Los «dejar» no reciben nada."""
    vende = sorted((f for f in formatos if f["estado"] == "vende"), key=lambda f: -f["tasa"])
    probar = sorted((f for f in formatos if f["estado"] == "sin datos"), key=lambda f: f["publicados"])
    if not vende:
        return _redondeo({f["formato"]: 1 for f in probar}, cupo) if probar else {}
    n_explorar = round(cupo * explorar) if probar else 0
    n_vende = cupo - n_explorar
    pesos = {vende[0]["formato"]: peso_top if len(vende) > 1 else 1.0}
    resto_tasa = sum(f["tasa"] for f in vende[1:]) or 1
    for f in vende[1:]:
        pesos[f["formato"]] = (1 - peso_top) * f["tasa"] / resto_tasa
    out = _redondeo(pesos, n_vende)
    # lo que menos se ha probado primero; un hueco por formato hasta agotar el de explorar
    for i, f in enumerate(probar[:n_explorar]):
        out[f["formato"]] = 1
    for i in range(n_explorar - min(n_explorar, len(probar))):
        out[vende[0]["formato"]] += 1
    return {k: v for k, v in out.items() if v}


def reparto_bandit(formatos: list[dict], cupo: int, explorar: int = 1, semilla: int | None = None,
                   a: float = 0.5, b: float = 1.0) -> dict[str, int]:
    """Reparto por muestreo de Thompson (Gamma-Poisson: pedidos por publicación con ventana).

    Cada hueco del día va al formato con mayor tasa sorteada de su posterior Gamma(pedidos+a, n+b);
    `explorar` huecos van a los «sin datos» con menos publicaciones. Los «dejar» no entran.
    Con la misma semilla sale siempre lo mismo (tests y reproducibilidad).
    """
    rnd = random.Random(semilla)
    vivos = [f for f in formatos if f["estado"] in ("vende", "sin datos")]
    probar = sorted((f for f in vivos if f["estado"] == "sin datos"), key=lambda f: f["publicados"])
    out: Counter = Counter()
    for f in probar[:min(explorar, cupo)]:
        out[f["formato"]] += 1
    for _ in range(cupo - sum(out.values())):
        if not vivos:
            break
        mejor = max(vivos, key=lambda f: rnd.gammavariate(f["pedidos"] + a, 1.0 / ((f["con_ventana"] or f["publicados"] or 0) + b)))
        out[mejor["formato"]] += 1
    return dict(out)


def candidatos(datos: dict, categoria: str, limite: int = 15) -> list[dict]:
    """Productos de `categoria`: primero los que venden (para variantes), luego los de menos contenido."""
    r = qv.analizar(datos)
    ventas = {a["clave"]: a["ventas"] for a in r["productos"] if a.get("encontrado", True)}
    prods: dict[str, dict] = {}
    n_pub: Counter = Counter()
    en_cola: Counter = Counter()
    for v in datos.get("videos", []):
        k = qv.clave(v)
        if v.get("uploaded"):
            n_pub[k] += 1
        else:
            en_cola[k] += 1
        prods.setdefault(k, v)
    for c in datos.get("carruseles", []):
        k = qv.clave(c)
        if c.get("subido"):
            n_pub[k] += 1
        else:
            en_cola[k] += 1
        prods.setdefault(k, c)
    out = []
    for k, it in prods.items():
        titulo = (it.get("titulo") or it.get("caption") or "").replace("\n", " ")
        if dg.categoria(titulo) != categoria:
            continue
        out.append({"clave": k, "titulo": titulo[:70], "tienda": it.get("tienda", ""),
                    "ventas": ventas.get(k, 0), "publicados": n_pub[k], "en_cola": en_cola[k],
                    "url": it.get("product_url", "")})
    out.sort(key=lambda c: (-c["ventas"], c["publicados"] + c["en_cola"], c["titulo"]))
    return out[:limite]


def plan(datos: dict, cupo: int = 6, bandit: bool = False, semilla: int | None = None) -> dict:
    r = qv.analizar(datos)
    fmts = clasificar(datos, r)
    cv = dg.cat_ventas(datos)
    top_cat = cv.most_common(1)[0][0] if cv else None
    return {"cupo": cupo, "formatos": fmts, "reparto": reparto_bandit(fmts, cupo, semilla=semilla) if bandit else reparto(fmts, cupo), "modo": "bandit" if bandit else "fijo",
            "categoria_top": top_cat, "categorias_venta": dict(cv),
            "candidatos": candidatos(datos, top_cat) if top_cat else [],
            "dejar": [f for f in fmts if f["estado"] == "dejar"],
            "corte": qv._fecha((datos.get("ventas") or {}).get("actualizado"))}


def informe_md(p: dict, cuenta: str = "") -> str:
    l = [f"# Plan de producción{' de ' + cuenta if cuenta else ''}", "",
         f"Ventas hasta {p['corte'] or '?'} · cupo {p['cupo']}/día ({p.get('modo', 'fijo')}) · categoría que vende: **{p['categoria_top'] or '—'}**.", "",
         "## Reparto diario", ""]
    if not p["reparto"]:
        l.append("- Sin datos para repartir.")
    for f, n in sorted(p["reparto"].items(), key=lambda kv: -kv[1]):
        l.append(f"- {n} × {f}")
    l += ["", "## Formatos", "", "| Formato | Publicados | Con ventana | Pedidos | Estado |", "|---|---:|---:|---:|---|"]
    for f in p["formatos"]:
        l.append(f"| {f['formato']} | {f['publicados']} | {f['con_ventana']} | {f['pedidos']:g} | {f['estado']} |")
    if p["dejar"]:
        l += ["", "## Dejar de hacer", ""] + [f"- {f['formato']}: {f['con_ventana']} publicados con ventana y 0 pedidos" for f in p["dejar"]]
    if p["candidatos"]:
        l += ["", f"## Candidatos ({p['categoria_top']})", "", "| Producto | Tienda | Ventas | Publicados | En cola |", "|---|---|---:|---:|---:|"]
        for c in p["candidatos"]:
            l.append(f"| {c['titulo']} | {c['tienda']} | {c['ventas']} | {c['publicados']} | {c['en_cola']} |")
    return "\n".join(l) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("usuario", nargs="?", default="ana")
    ap.add_argument("--desde-fichero")
    ap.add_argument("--cupo", type=int, default=6)
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--bandit", action="store_true", help="reparto por muestreo de Thompson")
    ap.add_argument("--semilla", type=int)
    a = ap.parse_args(argv)
    datos = json.loads(Path(a.desde_fichero).read_text(encoding="utf-8")) if a.desde_fichero else qv.recoger(a.usuario)
    p = plan(datos, a.cupo, a.bandit, a.semilla)
    md = informe_md(p, datos.get("usuario") or a.usuario)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
    print(json.dumps(p, ensure_ascii=False, indent=1, default=str) if a.json else md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
