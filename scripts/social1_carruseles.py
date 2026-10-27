"""Recoge los carruseles (slideshows) virales de un país en Social1.

Usa el Chrome remoto del VPS (CDP 9222, el que tiene la cuenta de PAGO de
Social1) en una pestaña propia. Guía: src/agente_mcp/guias/replicar-carrusel.md §1.

    ~/nav-venv/bin/python scripts/social1_carruseles.py fr --dias 30 --paginas 25 \
        --salida /tmp/s1_fr.json

Países de Social1 que nos sirven: es, fr, de, it, ie, uk (us/mx/br no venden
en nuestro carrito). Deja un JSON con una fila por carrusel, ordenado por GMV y
luego por visitas ganadas, con el enlace de TikTok listo para
`replicar_carrusel(url=…)`. Recoger tarda (~10 s por página): en segundo plano.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
PAISES = {"es": "Spain", "fr": "France", "de": "Germany", "it": "Italy",
          "ie": "Ireland", "uk": "United Kingdom"}

# Las tarjetas guardan su dato en las props de React: más fiable que leer el HTML.
JS = """() => { const res={};
  for (const el of document.querySelectorAll('div,img')) {
    const k=Object.keys(el).find(k=>k.startsWith('__reactFiber')); if(!k) continue;
    let f=el[k], d=0;
    while(f && d<8){ const pr=f.memoizedProps||{};
      for (const v of Object.values(pr)) {
        if (v && typeof v==='object' && v.video_id && v.ranking!==undefined) res[v.video_id]=v;
        if (Array.isArray(v)) for (const x of v) if (x && x.video_id) res[x.video_id]=x; }
      f=f.return; d++; } }
  return Object.values(res); }"""


def fila(r: dict) -> dict:
    prod = r.get("product_data") or {}
    return {
        "video_id": r.get("video_id"),
        "url": f"https://www.tiktok.com/@{r.get('handle')}/video/{r.get('video_id')}",
        "handle": r.get("handle"),
        "publicado": r.get("time_posted"),
        "views": r.get("views"),
        "view_gain": r.get("view_gain"),
        "gmv": r.get("gmv"),
        "is_ad": r.get("is_ad"),
        "is_ai": r.get("is_ai"),
        "is_slideshow": r.get("is_slideshow"),
        "producto": prod.get("name"),
        "product_id": r.get("product_id") or prod.get("product_id"),
        "tienda": r.get("shop_name"),
        "precio": prod.get("price"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pais", choices=sorted(PAISES))
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--paginas", type=int, default=25)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()

    hoy = dt.date.today()
    ini = (hoy - dt.timedelta(days=a.dias)).isoformat()
    url = (f"https://www.social1.ai/?isSlideshow=true&postedTsStart={ini}"
           f"&postedTsEnd={hoy}&tsStart={ini}&tsEnd={hoy}&page=1")

    res: dict[str, dict] = {}
    with sync_playwright() as p:
        ctx = p.chromium.connect_over_cdp(CDP).contexts[0]
        pg = ctx.new_page()  # pestaña PROPIA: el navegador es compartido
        try:
            pg.goto(url, wait_until="domcontentloaded")
            pg.wait_for_timeout(8000)
            boton = pg.locator("button[aria-haspopup=menu]").filter(
                has_text=re.compile(r"^(US|UK|DE|MX|BR|ES|FR|IT|IE)")).first
            boton.click()
            pg.wait_for_timeout(1500)
            pg.get_by_role("menuitem").filter(has_text=PAISES[a.pais]).first.click()
            pg.wait_for_timeout(8000)
            if "unlock social1" in pg.content().lower():
                sys.exit("Social1 sin la cuenta de pago (¿Chrome 9222 con sesión?)")
            for n in range(a.paginas):
                for _ in range(4):
                    pg.mouse.wheel(0, 5000)
                    pg.wait_for_timeout(1000)
                for r in pg.evaluate(JS):
                    res[r["video_id"]] = r
                print("página", n + 1, len(res), flush=True)
                nxt = pg.locator("button[aria-label='Next page']")
                if not nxt.count() or nxt.is_disabled():
                    break
                nxt.click()
                pg.wait_for_timeout(7000)
        finally:
            pg.close()

    filas = [fila(r) for r in res.values() if r.get("is_slideshow") in (1, True, None)]
    filas.sort(key=lambda f: (-(f["gmv"] or 0), -(f["view_gain"] or 0)))
    for f in filas:
        f["pais"] = a.pais.upper().replace("UK", "GB")
    with open(a.salida, "w", encoding="utf-8") as fh:
        json.dump(filas, fh, ensure_ascii=False, indent=1)
    print("total", len(filas), "→", a.salida)


if __name__ == "__main__":
    main()
