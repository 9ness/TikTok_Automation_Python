"""fwait2.py snap | fwait2.py out.jpg [timeout_s] — para el Flow nuevo (flow.google.com, 30/10/2026).
La cuadrícula solo carga miniaturas de 512 px: se espera a una tarjeta NUEVA que no sea una subida
(las subidas se llaman como el fichero, .jpg/.png) y se baja con el botón «Descargar» → 2K.
Hacer el snap ANTES de enviar con fimg.py."""
import sys, json, os, time, re
from playwright.sync_api import sync_playwright
SNAP = os.path.abspath('snap.json')  # en la carpeta de la ronda
JS = """()=>[...document.querySelectorAll('img[src*="/asb/"]')].map(i=>[i.src, i.closest('[aria-label]')?.getAttribute('aria-label')||''])"""
with sync_playwright() as p:
    pg = [x for c in p.chromium.connect_over_cdp("http://127.0.0.1:9222").contexts for x in c.pages if os.environ.get('FLOW_PROYECTO', '069b39d9') in x.url][0]
    if '/edit/' in pg.url:
        pg.go_back(); pg.wait_for_timeout(3000)
    if sys.argv[1] == "snap":
        json.dump([a[1] for a in pg.evaluate(JS)][:8], open(SNAP, "w")); print("snap ok"); sys.exit()
    viejas = json.load(open(SNAP)); fin = time.time() + float(sys.argv[2] if len(sys.argv) > 2 else 300)
    while time.time() < fin:
        pg.mouse.move(700, 300); pg.mouse.wheel(0, -5000); pg.wait_for_timeout(4000)
        cur = pg.evaluate(JS); labs = [a[1] for a in cur]
        # nueva = la lista se ha corrido una posición (las URL firmadas cambian al recargar: no sirven)
        # las referencias subidas (.jpg/.png) también entran arriba: se ignoran al comparar
        es_sub = lambda l: re.search(r'\.(jpe?g|png|webp)$', l, re.I)
        k = next((i for i in range(1, 8) if labs[i:i+4] == viejas[:4]), 0) if len(labs) > 6 else 0
        if len(viejas) < 8:
            k = len(cur) - len(viejas) if len(cur) > len(viejas) else 0
        gen = [c for c in cur[:k] if not es_sub(c[1])]
        nuevas = gen[:1]
        if nuevas:
            pg.wait_for_timeout(2000)
            import base64
            u = nuevas[0][0].rsplit('=', 1)[0] + '=s0'
            b64 = pg.evaluate("""async(s)=>{const r=await fetch(s);const b=new Uint8Array(await r.arrayBuffer());let t='';for(let k=0;k<b.length;k+=32768)t+=String.fromCharCode(...b.subarray(k,k+32768));return btoa(t)}""", u)
            d = base64.b64decode(b64)
            if len(d) < 20000: print("VACIA", len(d)); sys.exit(3)
            open(sys.argv[1], 'wb').write(d)
            print("ok", sys.argv[1], nuevas[0][1]); sys.exit()
    print("TIMEOUT"); sys.exit(2)
