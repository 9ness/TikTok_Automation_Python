#!/usr/bin/env python3
"""Plan del día de una cuenta TikTok Shop: qué subir hoy y qué producir mañana.

Solo lectura (Mis tandas + ranking de ventas_atribuidas.py). No sube, no genera, no escribe en Redis.

Uso:  python3 scripts/estadisticas_movil/planificar_dia.py [usuario=nestor2] [--n 10] [--json]
Salida: /mnt/HC_Volume_106974679/agentes/trabajo/ana_nestor2/plan_<usuario>_<fecha>.md (+ .json)
Lógica pura: candidatos / ordenar / seleccionar / plan_produccion. Lectura: leer_fuentes (ventas_atribuidas).
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


def _cargar(nombre: str, fichero: str):
    spec = importlib.util.spec_from_file_location(nombre, Path(__file__).with_name(fichero))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod


va = _cargar("ventas_atribuidas_plan", "ventas_atribuidas.py")

OUT_DIR = va.OUT_DIR
TEMAS_PRIORITARIOS = re.compile(r"\b(celo|reno|renos)\b", re.I)
STOCK_TOTAL = 12
MIN_PROD, MAX_PROD = 2, 4
MAX_VENDEN = 8  # tope de productos que venden a reponer cada día
FORMATOS_PROD = ["genjutsu", "con_ia"]  # orden de preferencia; nunca sin_ia
URL_MP4 = "/api/v1/mis-tandas/video?id={id}&descargar=true"


# ---------------------------------------------------------------- lógica pura
def producto_de(item: dict) -> str:
    return (item.get("titulo") or item.get("producto") or "?").strip()[:70]


def es_verde(item: dict) -> bool:
    s = item.get("semaforo")
    return isinstance(s, dict) and s.get("color") == "verde"


def candidatos(items: list[dict]) -> list[dict]:
    """Verdes no subidos, con stock y sin marca de rehacer."""
    return [i for i in items if es_verde(i) and not i.get("uploaded")
            and not i.get("sin_stock") and not i.get("rehacer")]


def productos_dejar(ranking_prod: list[dict]) -> set[str]:
    return {f["clave"] for f in ranking_prod if f.get("veredicto") == "dejar"}


def _tema(item: dict) -> int:
    """0 celo/renos, 1 Navidad, 2 resto."""
    if TEMAS_PRIORITARIOS.search(item.get("titulo") or ""):
        return 0
    return 1 if item.get("epoca") == "navidad" else 2


def ordenar(cands: list[dict], ranking_prod: list[dict]) -> list[dict]:
    vpv = {f["clave"]: f.get("ventas_por_video", 0) for f in ranking_prod}
    return sorted(cands, key=lambda i: (_tema(i), -vpv.get(producto_de(i), 0),
                                        i.get("video_listo_at") or 0, str(i.get("id"))))


MAX_POR_PRODUCTO = 2  # al día: más del mismo producto satura el feed


def seleccionar(ordenados: list[dict], n: int, dejar: set[str],
                max_por_producto: int = MAX_POR_PRODUCTO) -> list[dict]:
    """Primeros n por orden, sin los de «dejar», sin dos del mismo producto seguidos
    y como mucho `max_por_producto` vídeos de cada producto."""
    pool = [i for i in ordenados if producto_de(i) not in dejar]
    out: list[dict] = []
    while pool and len(out) < n:
        ultimo = producto_de(out[-1]) if out else None
        usados = Counter(producto_de(i) for i in out)
        pos = next((k for k, i in enumerate(pool) if producto_de(i) != ultimo
                    and usados[producto_de(i)] < max_por_producto), None)
        if pos is None:
            break  # solo quedan del mismo producto que el último: no se repite seguido
        out.append(pool.pop(pos))
    return out


_PRECIO = re.compile(r"\d+(?:[.,]\d+)?\s?(?:€|eur\w*|euros?)|(?:€|\$)\s?\d+(?:[.,]\d+)?", re.I)
_CUPON = re.compile(r"[^.!?\n]*\b(?:cup[oó]n\w*|descuento\w*|oferta\w*|chollo\w*|rebaja\w*)\b[^.!?\n]*[.!?]?", re.I)


def caption_de(item: dict) -> str:
    """Caption de la app (o título) sin precios ni cupones, con 3-4 hashtags."""
    base = (item.get("caption") or "").strip()
    if not base:
        base = producto_de(item)
    tags = re.findall(r"#\w+", base)
    texto = re.sub(r"#\w+", "", base)
    texto = _PRECIO.sub("", texto)
    texto = _CUPON.sub("", texto)
    texto = re.sub(r"\s+", " ", texto).strip() or producto_de(item)
    vistos: list[str] = []
    for t in tags + (["#navidad"] if item.get("epoca") == "navidad" else []) + ["#tiktokshop", "#regalos", "#parati", "#españa"]:
        if t.lower() not in [v.lower() for v in vistos]:
            vistos.append(t)
    vistos = [t for t in vistos if not re.search(r"cup|oferta|descuento|chollo", t, re.I)]
    return f"{texto} {' '.join(vistos[:4])}".strip()


def fila_plan(item: dict, pos: int) -> dict:
    return {"orden": pos, "id": item["id"], "producto": producto_de(item),
            "formato": f"{item.get('nicho')}/{item.get('modo')}", "epoca": item.get("epoca"),
            "mp4": URL_MP4.format(id=item["id"]), "product_url": item.get("product_url") or "",
            "caption": caption_de(item)}


def formato_produccion(por_formato: list[dict]) -> str:
    """Genjutsu primero; si el ranking lo marca «dejar», réplica con IA. Nunca sin IA."""
    ver = {f["clave"]: f.get("veredicto") for f in por_formato}
    for f in FORMATOS_PROD:
        if ver.get(f"rv/{f}") != "dejar":
            return f
    return FORMATOS_PROD[-1]


_NO_PROBAR = re.compile(r"sof[aá]|colch[oó]n", re.I)


_GENERICAS = {"navidad", "navideña", "navideñas", "navideño", "navideños", "regalo", "regalos", "decoración"}


def _raiz(nombre: str) -> set[str]:
    """Palabras distintivas (con cifras o de 6+ letras, no genéricas), para no «probar» una variante de un producto a dejar."""
    return {w for w in re.findall(r"\w+", nombre.lower())
            if (any(c.isdigit() for c in w) or len(w) >= 6) and w not in _GENERICAS}


def plan_produccion(items: list[dict], ranking_prod: list[dict], por_formato: list[dict],
                    stock_total: int = STOCK_TOTAL) -> dict:
    stock = Counter(producto_de(i) for i in candidatos(items))
    total_items = Counter(producto_de(i) for i in items)
    fmt = formato_produccion(por_formato)
    dejar = productos_dejar(ranking_prod)
    filas = []
    nvende = 0
    # primero los de datos sólidos (≥4 vídeos), cada grupo ya viene por ventas/vídeo
    for f in sorted(ranking_prod, key=lambda x: x.get("videos", 0) < 4):
        p = f["clave"]
        if p in dejar:
            continue
        vende = f.get("ventas", 0) > 0 and f.get("veredicto") in ("producir más", "mantener")
        # Productos caros (sofás, colchones) solo si ya venden (regla 22/10) y nada parecido a «dejar».
        probar = not _NO_PROBAR.search(p) and not any(_raiz(p) & _raiz(d) for d in dejar) and (
                 (f.get("veredicto") == "pocos datos" and total_items.get(p, 0) == 1) or \
                 (f.get("videos", 0) == 1 and f.get("ventas", 0) == 0 and total_items.get(p, 0) <= 1))
        if vende:
            if nvende >= MAX_VENDEN:
                continue
            nvende += 1
            fuerte = f["veredicto"] == "producir más" and f.get("videos", 0) >= 4
            objetivo, motivo = (MAX_PROD if fuerte else 3 if f["veredicto"] == "mantener" else MIN_PROD), "vende"
        elif probar:
            objetivo, motivo = MIN_PROD, "probar (solo 1 vídeo)"
        else:
            continue
        hay = stock.get(p, 0)
        if vende:
            falta = max(0, objetivo - hay)
        else:  # probar: llegar a 2 vídeos del producto
            falta = max(0, MIN_PROD - total_items.get(p, 0))
        if falta:
            filas.append({"producto": p, "formato": fmt, "cantidad": falta, "stock_verde": hay,
                          "motivo": motivo, "ventas_por_video": f.get("ventas_por_video", 0)})
    # stock total hacia el objetivo: si tras lo anterior sigue corto, sumar a los que más venden
    total_stock = sum(stock.values())
    previsto = total_stock + sum(r["cantidad"] for r in filas)
    extra = max(0, stock_total - previsto)
    for r in filas:
        if extra <= 0:
            break
        if r["motivo"] == "vende":
            suma = min(extra, MAX_PROD - (r["stock_verde"] + r["cantidad"]))
            if suma > 0:
                r["cantidad"] += suma
                extra -= suma
    return {"stock_total": total_stock, "objetivo_total": stock_total, "formato": fmt,
            "stock_por_producto": dict(stock.most_common()), "producir": filas,
            "sin_cubrir_para_objetivo_total": extra}


# ---------------------------------------------------------------- salida
def informe(usuario: str, fecha: str, subida: list[dict], prod: dict, ndejar: set[str]) -> str:
    p = [f"# Plan del día {fecha} · {usuario}", "", "## 1. Subir hoy", ""]
    for r in subida:
        p += [f"{r['orden']}. **{r['producto']}** · `{r['id']}` · {r['formato']}",
              f"   - MP4: {r['mp4']}", f"   - Caption: {r['caption']}"]
    p += ["", f"Excluidos por «dejar»: {', '.join(sorted(ndejar)) or '-'}", "",
          "## 2. Producir para mañana", "",
          f"Stock verde: {prod['stock_total']} / objetivo {prod['objetivo_total']} · formato: {prod['formato']} (nunca sin IA)", "",
          "| producto | formato | hacer | stock verde | motivo |", "|---|---|--:|--:|---|"]
    for r in prod["producir"]:
        p.append(f"| {r['producto']} | {r['formato']} | {r['cantidad']} | {r['stock_verde']} | {r['motivo']} |")
    if prod["sin_cubrir_para_objetivo_total"]:
        p.append(f"\nFaltan {prod['sin_cubrir_para_objetivo_total']} para el stock total (sin más productos que vendan).")
    p += ["", "Stock verde por producto: " + "; ".join(f"{k} {v}" for k, v in prod["stock_por_producto"].items()), ""]
    return "\n".join(p)


def construir(usuario: str, ventas: dict, items: list[dict], n: int = 10, fecha: str | None = None) -> dict:
    fecha = fecha or dt.date.today().isoformat()
    r = va.analizar(ventas, items)
    dejar = productos_dejar(r["por_producto"])
    sel = seleccionar(ordenar(candidatos(items), r["por_producto"]), n, dejar)
    subida = [fila_plan(i, k) for k, i in enumerate(sel, 1)]
    prod = plan_produccion(items, r["por_producto"], r["por_formato"])
    return {"usuario": usuario, "fecha": fecha, "subir_hoy": subida, "producir": prod,
            "dejar": sorted(dejar), "_dejar": dejar}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("usuario", nargs="?", default="nestor2")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    ventas, items = va.leer_fuentes(a.usuario)
    plan = construir(a.usuario, ventas, items, a.n)
    txt = informe(a.usuario, plan["fecha"], plan["subir_hoy"], plan["producir"], plan.pop("_dejar"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = OUT_DIR / f"plan_{a.usuario}_{plan['fecha']}"
    base.with_suffix(".md").write_text(txt, encoding="utf-8")
    if a.json:
        base.with_suffix(".json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
