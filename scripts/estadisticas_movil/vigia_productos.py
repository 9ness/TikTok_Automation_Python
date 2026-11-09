#!/usr/bin/env python3
"""Vigía de enlaces y stock de los productos de una cuenta (en cola o publicados). Solo lectura.

Sin móvil revisa los ENLACES de cada vídeo/carrusel:
  - sin enlace o con un enlace que no es de producto de TikTok Shop;
  - enlaces cortos vm.tiktok.com: los resuelve (redirección HTTP, sin abrir la ficha) para saber su id;
    con pausa y caché, porque tras una ráfaga TikTok redirige a la portada (eso queda «sin resolver»);
  - un mismo id de producto con títulos de categoría distinta → posible enlace cambiado
    (es justo la sanción de «promoción de producto incoherente»);
  - un mismo título con ids distintos (aviso: puede ser otra tienda o un enlace equivocado).
El STOCK no sale en la ficha web (pide captcha; ver scripts/stock_tiktok_movil.py), así que:
  - lista los ids a comprobar en el móvil, primero los que tienen contenido EN COLA (máx. --max, por
    la regla de no abrir fichas en bucle) y el comando para hacerlo en la ventana del móvil;
  - si se pasa `--stock` con la salida de stock_tiktok_movil.py (JSON por línea), marca qué
    vídeos/carruseles en cola NO deben subirse por producto agotado.

Uso:  python3 -I scripts/estadisticas_movil/vigia_productos.py ana --desde-fichero ana.json \
          [--stock stock.jsonl] [--no-resolver] [--cache cortos.json] [--max 6] [--out x.md] [--json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Callable


def _cargar(nombre: str, fichero: str):
    spec = importlib.util.spec_from_file_location(nombre, Path(__file__).with_name(fichero))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


qv = _cargar("que_vende_vigia", "que_vende.py")
dg = _cargar("diag_carr_vigia", "diagnostico_carruseles.py")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
RE_ID = re.compile(r"/(?:product|pdp)/(\d+)")


def tipo_enlace(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return "vacio"
    if RE_ID.search(url):
        return "producto"
    if re.match(r"https?://(vm|vt)\.tiktok\.com/\w+", url):
        return "corto"
    return "raro"


def resolver_http(url: str, timeout: int = 15) -> str:
    """URL final tras las redirecciones (no lee la ficha: TikTok responde con un control de seguridad)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-ES"})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (solo dominios de TikTok)
        return r.geturl()


def items(datos: dict) -> list[dict]:
    out = []
    for v in datos.get("videos", []):
        out.append({"id": v.get("id"), "tipo": "Vídeo", "titulo": (v.get("titulo") or v.get("caption") or "").replace("\n", " "),
                    "url": v.get("product_url") or "", "en_cola": not v.get("uploaded")})
    for c in datos.get("carruseles", []):
        out.append({"id": c.get("id"), "tipo": "Carrusel", "titulo": (c.get("titulo") or c.get("caption") or "").replace("\n", " "),
                    "url": c.get("product_url") or "", "en_cola": not c.get("subido")})
    return out


def con_ids(its: list[dict], resolver: Callable[[str], str] | None = None, cache: dict | None = None,
            pausa: float = 0) -> list[dict]:
    """Añade `tipo_enlace` y `pid` (id de producto; los cortos se resuelven si hay `resolver`)."""
    cache = cache if cache is not None else {}
    out = []
    for it in its:
        t = tipo_enlace(it["url"])
        pid = ""
        if t == "producto":
            pid = RE_ID.search(it["url"]).group(1)
        elif t == "corto" and resolver:
            final = cache.get(it["url"], "")
            if not RE_ID.search(final):
                try:
                    final = resolver(it["url"])
                except Exception as e:  # red caída o bloqueo: se avisa, no se aborta
                    final = f"error: {type(e).__name__}"
                if pausa:
                    time.sleep(pausa)
            m = RE_ID.search(final)
            if m:   # solo se guarda lo resuelto: tras una ráfaga TikTok manda a la portada y hay que reintentar
                cache[it["url"]] = final
                pid = m.group(1)
            else:
                t = "corto_sin_resolver"
        out.append({**it, "tipo_enlace": t, "pid": pid})
    return out


def leer_stock(lineas) -> dict[str, str]:
    out = {}
    for l in lineas:
        try:
            d = json.loads(l)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("product_id"):
            out[str(d["product_id"])] = d.get("estado", "")
    return out


def revisar(its: list[dict], stock: dict[str, str] | None = None, maximo: int = 6) -> dict:
    stock = stock or {}
    problemas = []
    for it in its:
        if it["tipo_enlace"] == "vacio":
            problemas.append({**it, "problema": "sin enlace", "grave": it["en_cola"]})
        elif it["tipo_enlace"] == "raro":
            problemas.append({**it, "problema": "enlace que no es de TikTok Shop", "grave": True})
        elif it["tipo_enlace"] == "corto_sin_resolver":
            problemas.append({**it, "problema": "enlace corto sin resolver (reintentar)", "grave": False})

    por_pid: dict[str, list[dict]] = defaultdict(list)
    for it in its:
        if it["pid"]:
            por_pid[it["pid"]].append(it)
    cambiados = []
    for pid, grupo in por_pid.items():
        cats = {dg.categoria(g["titulo"]) for g in grupo} - {"otra"}
        if len(cats) > 1:
            cambiados.append({"pid": pid, "categorias": sorted(cats),
                              "items": [(g["id"], g["titulo"][:50], g["en_cola"]) for g in grupo]})

    por_titulo: dict[str, set[str]] = defaultdict(set)
    for it in its:
        if it["pid"] and it["titulo"]:
            por_titulo[qv.normalizar(it["titulo"])].add(it["pid"])
    titulos_varios = {t: sorted(p) for t, p in por_titulo.items() if len(p) > 1}

    en_cola = defaultdict(int)
    titulo_pid = {}
    for it in its:
        if it["pid"]:
            titulo_pid.setdefault(it["pid"], it["titulo"])
            if it["en_cola"]:
                en_cola[it["pid"]] += 1
    pendientes = sorted((p for p in en_cola if p not in stock), key=lambda p: -en_cola[p])
    no_subir = [it for it in its if it["en_cola"] and stock.get(it["pid"]) == "agotado"]
    return {"problemas": problemas, "enlace_cambiado": cambiados, "titulo_con_varios_ids": titulos_varios,
            "comprobar_stock": [{"pid": p, "titulo": titulo_pid[p][:60], "en_cola": en_cola[p]} for p in pendientes[:maximo]],
            "stock_pendientes_total": len(pendientes), "stock": stock, "no_subir": no_subir,
            "total": len(its), "en_cola": sum(1 for it in its if it["en_cola"])}


def informe_md(r: dict, cuenta: str = "") -> str:
    l = [f"# Vigía de productos{' de ' + cuenta if cuenta else ''}", "",
         f"{r['total']} vídeos/carruseles · {r['en_cola']} en cola · {len(r['no_subir'])} en cola con producto AGOTADO.", ""]
    if r["no_subir"]:
        l += ["## ⛔ No subir (producto agotado)", ""] + [f"- {i['id']} · {i['titulo'][:60]} (producto {i['pid']})" for i in r["no_subir"]] + [""]
    if r["enlace_cambiado"]:
        l += ["## ⚠️ Mismo producto con títulos de otra categoría (posible enlace cambiado)", ""]
        for c in r["enlace_cambiado"]:
            l.append(f"- producto {c['pid']} ({', '.join(c['categorias'])}): " + "; ".join(f"{i} «{t}»{' [en cola]' if q else ''}" for i, t, q in c["items"]))
        l.append("")
    graves = [p for p in r["problemas"] if p["grave"]]
    if graves:
        l += ["## Enlaces a arreglar antes de subir", ""] + [f"- {p['id']} · {p['titulo'][:50]} · {p['problema']}" for p in graves] + [""]
    sin_res = sum(1 for p in r["problemas"] if p["tipo_enlace"] == "corto_sin_resolver")
    sin_enl = sum(1 for p in r["problemas"] if not p["grave"] and p["tipo_enlace"] == "vacio")
    if sin_enl:
        l += [f"Ya publicados sin enlace guardado: {sin_enl} (solo informativo).", ""]
    if sin_res:
        l += [f"Enlaces cortos sin resolver: {sin_res} (TikTok frena las ráfagas; vuelve a pasar el vigía con `--cache`).", ""]
    if r["titulo_con_varios_ids"]:
        l += ["## Mismo título con varios ids (revisar si es otra tienda)", ""]
        l += [f"- {t[:50]}: {', '.join(p)}" for t, p in list(r["titulo_con_varios_ids"].items())[:15]] + [""]
    if r["comprobar_stock"]:
        ids = " ".join(c["pid"] for c in r["comprobar_stock"])
        l += [f"## Stock por comprobar en el móvil ({len(r['comprobar_stock'])} de {r['stock_pendientes_total']}, los de más contenido en cola)", ""]
        l += [f"- {c['pid']} · {c['titulo']} · {c['en_cola']} en cola" for c in r["comprobar_stock"]]
        l += ["", "Solo en la ventana del móvil y con turno: `python3 scripts/stock_tiktok_movil.py " + ids + " > stock.jsonl`, "
              "luego vuelve a pasar el vigía con `--stock stock.jsonl`."]
    return "\n".join(l) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("usuario", nargs="?", default="ana")
    ap.add_argument("--desde-fichero")
    ap.add_argument("--stock")
    ap.add_argument("--no-resolver", action="store_true", help="no resolver enlaces cortos (sin red)")
    ap.add_argument("--cache", help="JSON con enlaces cortos ya resueltos (se actualiza)")
    ap.add_argument("--max", type=int, default=6)
    ap.add_argument("--pausa", type=float, default=1.0, help="segundos entre enlaces cortos")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    datos = json.loads(Path(a.desde_fichero).read_text(encoding="utf-8")) if a.desde_fichero else qv.recoger(a.usuario)
    cache = json.loads(Path(a.cache).read_text(encoding="utf-8")) if a.cache and Path(a.cache).exists() else {}
    its = con_ids(items(datos), None if a.no_resolver else resolver_http, cache, a.pausa)
    if a.cache:
        Path(a.cache).write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    stock = leer_stock(Path(a.stock).read_text(encoding="utf-8").splitlines()) if a.stock else {}
    r = revisar(its, stock, a.max)
    md = informe_md(r, datos.get("usuario") or a.usuario)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str) if a.json else md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
