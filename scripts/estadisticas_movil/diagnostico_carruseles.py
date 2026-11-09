#!/usr/bin/env python3
"""Por qué no venden los carruseles de una cuenta: causas probables por orden. Solo lectura.

Cruza cada carrusel subido con lo que sí vende (vídeos con pedidos):
  - ventana: días entre la subida y el corte de las ventas guardadas (`ventas.actualizado`);
  - categoría del producto (bolso, chaqueta, pantalón…) frente a las que venden;
  - hora y día de subida frente a los vídeos que vendieron;
  - carrito: enlace de producto válido y, si hay registro de fases de la subida, si se añadió el producto;
  - repetición: mismo producto o misma tienda muchas veces;
  - vistas de Studio, si se pasan (lista de {id|caption, vistas}).

Uso:  python3 -I scripts/estadisticas_movil/diagnostico_carruseles.py ana \
          [--desde-fichero ana.json] [--fases /tmp/carr_ana/fases.jsonl] [--studio s.json] [--out x.md] [--json]
El volcado es el mismo de que_vende.py (`--json` de allí o su `recoger`).
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

_QV = Path(__file__).with_name("que_vende.py")
_spec = importlib.util.spec_from_file_location("que_vende_diag", _QV)
qv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qv)

# Primera palabra que aparezca manda; el orden importa (conjunto antes que pantalón).
CATEGORIAS = [
    ("bolso", {"bolso", "tote", "bandolera", "mochila", "cartera", "rinonera"}),
    ("calzado", {"zapatos", "zapatillas", "botas", "botines", "mocasines", "sandalias", "deportivas"}),
    ("conjunto", {"conjunto", "chandal"}),
    ("abrigo/chaqueta", {"abrigo", "chaqueta", "cazadora", "bomber", "gabardina", "capa", "poncho", "chaleco", "blazer", "cardigan", "parka"}),
    ("vestido", {"vestido", "mono"}),
    ("pantalón/falda", {"pantalon", "vaqueros", "leggings", "falda", "mallas", "short"}),
    ("parte de arriba", {"jersey", "camiseta", "blusa", "sudadera", "top", "camisa", "body"}),
]
MIN_VENTANA = 3      # días por debajo de los cuales «0 ventas» no dice nada
UMBRAL_REPE = 3      # mismo producto en N carruseles o más = repetición


def categoria(texto: str) -> str:
    pal = set(qv.normalizar(texto).split()) | qv.fichas(texto)
    for nombre, claves in CATEGORIAS:
        if pal & claves:
            return nombre
    return "otra"


def _hora(ts) -> int:
    return dt.datetime.fromtimestamp(float(ts), qv.ZONA).hour


def _franja(h: int) -> str:
    if 6 <= h < 14:
        return "mañana (6-14)"
    return "tarde (14-19)" if 14 <= h < 19 else "noche (19-6)"


def url_valida(url: str) -> bool:
    return bool(re.search(r"/(?:product|pdp)/\d+", url or "")) or "vm.tiktok.com" in (url or "")


def leer_fases(lineas) -> dict[str, bool]:
    """id → True si en la subida se llegó a «producto_anadir» (el carrito quedó enlazado)."""
    out: dict[str, bool] = {}
    for l in lineas:
        l = l.strip()
        if not l:
            continue
        try:
            d = json.loads(l)
        except ValueError:
            continue
        fases = {k for f in (d.get("fases") or {}).values() if isinstance(f, dict) for k in f}
        cid = d.get("id")
        if cid:
            out[cid] = out.get(cid, False) or ("producto_anadir" in fases)
    return out


def vendedores(datos: dict) -> list[dict]:
    """Vídeos subidos que tienen pedidos en `ventas.contenidos` (por caption), con su hora y categoría."""
    vids = [v for v in datos.get("videos", []) if v.get("uploaded") and v.get("uploaded_at")]
    out = []
    for cont in (datos.get("ventas") or {}).get("contenidos", []) or []:
        if not cont.get("pedidos"):
            continue
        v = qv.mejor_pareja(cont.get("caption", ""), vids, campos=("caption",))
        if v:
            out.append({"id": v.get("id"), "pedidos": cont["pedidos"], "hora": _hora(v["uploaded_at"]),
                        "dia": dt.datetime.fromtimestamp(float(v["uploaded_at"]), qv.ZONA).strftime("%a"),
                        "categoria": categoria(v.get("titulo") or v.get("caption", ""))})
    return out


def cat_ventas(datos: dict) -> Counter:
    """Ventas por categoría según los títulos de `ventas.meses[].productos` (incluye otros países)."""
    c: Counter = Counter()
    for mes in (datos.get("ventas") or {}).get("meses", []) or []:
        for p in mes.get("productos", []) or []:
            c[categoria(p.get("titulo", ""))] += int(p.get("ventas") or 0)
    return c


def diagnosticar(datos: dict, fases: dict[str, bool] | None = None, studio: list[dict] | None = None) -> dict:
    fases = fases or {}
    corte = qv._fecha((datos.get("ventas") or {}).get("actualizado"))
    subidos = [c for c in datos.get("carruseles", []) if c.get("subido") and c.get("subido_at")]
    filas = []
    vistas = {}
    for s in studio or []:
        if s.get("id"):
            vistas[s["id"]] = s.get("vistas")
    for c in subidos:
        dia = qv._dia(c["subido_at"])
        v = vistas.get(c.get("id"))
        if v is None and studio:
            m = qv.mejor_pareja(c.get("caption", ""), [s for s in studio if s.get("caption")], campos=("caption",))
            v = m.get("vistas") if m else None
        filas.append({
            "id": c.get("id"), "titulo": (c.get("titulo") or "").replace("\n", " "),
            "tienda": c.get("tienda", ""), "producto": qv.clave(c), "categoria": categoria(c.get("titulo") or c.get("caption", "")),
            "dia": dia, "hora": _hora(c["subido_at"]),
            "ventana": (corte - dia).days if corte else None,
            "url_ok": url_valida(c.get("product_url", "")),
            "carrito": fases.get(c.get("id")),          # True / False / None (sin registro)
            "vistas": v,
        })

    vend = vendedores(datos)
    cv = cat_ventas(datos)
    total_v = sum(cv.values())
    cats = Counter(f["categoria"] for f in filas)
    causas = []

    con_ventana = [f for f in filas if f["ventana"] is not None and f["ventana"] >= MIN_VENTANA]
    if filas and len(con_ventana) < max(1, len(filas) // 2):
        causas.append({"peso": 100, "causa": "sin datos todavía",
                       "detalle": f"solo {len(con_ventana)} de {len(filas)} carruseles llevan ≥{MIN_VENTANA} días antes del corte de ventas "
                                  f"({corte or 'sin fecha'}): el «0 ventas» aún no es un dato. Actualiza las ventas (Paso 3) y repite.",
                       "accion": "leer pedidos por contenido de Seller/Studio de los días después de la subida"})

    if total_v and filas:
        top_cat, n_top = cv.most_common(1)[0]
        frac_top = n_top / total_v
        frac_car = cats.get(top_cat, 0) / len(filas)
        if frac_top >= 0.5 and frac_car < 0.25:
            causas.append({"peso": round(60 + 40 * (frac_top - frac_car)), "causa": "categoría distinta de la que vende",
                           "detalle": f"«{top_cat}» hace {n_top}/{total_v} ventas ({frac_top:.0%}) pero solo {cats.get(top_cat, 0)}/{len(filas)} "
                                      f"carruseles son de eso; lo más subido: {', '.join(f'{k} {n}' for k, n in cats.most_common(3))}.",
                           "accion": f"pasar parte de los carruseles a {top_cat} (variantes del que vende)"})

    sin_url = [f for f in filas if not f["url_ok"]]
    sin_carrito = [f for f in filas if f["carrito"] is False]
    sin_reg = [f for f in filas if f["carrito"] is None]
    if sin_url or sin_carrito:
        causas.append({"peso": 90, "causa": "carrito sin enlazar",
                       "detalle": f"{len(sin_url)} sin enlace de producto válido y {len(sin_carrito)} subidos sin llegar a «Añadir producto».",
                       "accion": "revisar en el perfil que lleven la bolsa naranja; republicar los que no"})

    franjas_v = Counter(_franja(v["hora"]) for v in vend)
    franjas_c = Counter(_franja(f["hora"]) for f in filas)
    if franjas_v and filas:
        fv, nv = franjas_v.most_common(1)[0]
        if franjas_c.get(fv, 0) / len(filas) < 0.25:
            causas.append({"peso": 40, "causa": "hora distinta de la que vende",
                           "detalle": f"los vídeos con pedidos salieron sobre todo por la {fv} ({nv}/{len(vend)}); "
                                      f"los carruseles: {', '.join(f'{k} {n}' for k, n in franjas_c.most_common())}.",
                           "accion": f"probar parte de los carruseles en la franja de {fv}"})

    rep = Counter(f["producto"] for f in filas)
    repes = {k: n for k, n in rep.items() if n >= UMBRAL_REPE}
    tiendas = Counter(f["tienda"] for f in filas if f["tienda"])
    if repes or (tiendas and tiendas.most_common(1)[0][1] >= max(5, len(filas) // 4)):
        nombres = {f["producto"]: f["titulo"] for f in filas}
        det = [f"{nombres[k][:40]} ×{n}" for k, n in sorted(repes.items(), key=lambda x: -x[1])]
        t, nt = tiendas.most_common(1)[0] if tiendas else ("", 0)
        causas.append({"peso": 30, "causa": "repetición",
                       "detalle": ("productos repetidos: " + "; ".join(det) + ". " if det else "") + (f"tienda más repetida: {t} ×{nt}." if t else ""),
                       "accion": "variar producto y tienda; el algoritmo reparte menos al contenido parecido"})

    con_vistas = [f for f in filas if isinstance(f["vistas"], (int, float))]
    if con_vistas:
        med = sorted(f["vistas"] for f in con_vistas)[len(con_vistas) // 2]
        if med < 300:
            causas.append({"peso": 70, "causa": "poca distribución",
                           "detalle": f"mediana de {med} vistas en {len(con_vistas)} carruseles: no llegan a gente suficiente para vender.",
                           "accion": "mejorar el gancho de la 1.ª foto y el sonido; menos carruseles y más cuidados"})

    causas.sort(key=lambda c: -c["peso"])
    return {"carruseles": filas, "corte": corte, "causas": causas, "vendedores": vend,
            "categorias_venta": dict(cv), "categorias_carrusel": dict(cats),
            "carrito_sin_registro": len(sin_reg)}


def informe_md(r: dict, cuenta: str = "") -> str:
    f = r["carruseles"]
    l = [f"# Por qué no venden los carruseles{' de ' + cuenta if cuenta else ''}", "",
         f"{len(f)} carruseles subidos · ventas guardadas hasta {r['corte'] or '?'} · "
         f"carrito sin registro de subida: {r['carrito_sin_registro']}.", "", "## Causas probables (de más a menos)", ""]
    if not r["causas"]:
        l.append("- Nada claro con estos datos.")
    for i, c in enumerate(r["causas"], 1):
        l += [f"{i}. **{c['causa']}** — {c['detalle']}", f"   → {c['accion']}"]
    l += ["", "## Ventas por categoría", "", "| Categoría | Ventas | Carruseles subidos |", "|---|---:|---:|"]
    cats = sorted(set(r["categorias_venta"]) | set(r["categorias_carrusel"]),
                  key=lambda k: (-r["categorias_venta"].get(k, 0), -r["categorias_carrusel"].get(k, 0)))
    for k in cats:
        l.append(f"| {k} | {r['categorias_venta'].get(k, 0)} | {r['categorias_carrusel'].get(k, 0)} |")
    if r["vendedores"]:
        l += ["", "## Vídeos con pedidos (hora de subida)", ""]
        for v in sorted(r["vendedores"], key=lambda v: -v["pedidos"]):
            l.append(f"- {v['id']} · {v['pedidos']} pedidos · {v['dia']} {v['hora']:02d}h · {v['categoria']}")
    return "\n".join(l) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("usuario", nargs="?", default="ana")
    ap.add_argument("--desde-fichero")
    ap.add_argument("--fases")
    ap.add_argument("--studio")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    datos = json.loads(Path(a.desde_fichero).read_text(encoding="utf-8")) if a.desde_fichero else qv.recoger(a.usuario)
    fases = leer_fases(Path(a.fases).read_text(encoding="utf-8").splitlines()) if a.fases and Path(a.fases).exists() else {}
    studio = json.loads(Path(a.studio).read_text(encoding="utf-8")) if a.studio else None
    r = diagnosticar(datos, fases, studio)
    md = informe_md(r, datos.get("usuario") or a.usuario)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str) if a.json else md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
