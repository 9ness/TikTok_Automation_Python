"""flowgen.py <prompt.txt> <ref1.jpg> [ref2.jpg ...] — imagen en el proyecto de Flow del duelo.
Adjunta las referencias (subiéndolas si no están), pega el prompt y genera (Nano Banana 2 · 9:16 · x1)."""
import os, sys
from playwright.sync_api import sync_playwright
PROY = "a1507c84"
ptxt, refs = sys.argv[1], sys.argv[2:]
prompt = open(ptxt, encoding="utf-8").read().strip()
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    pg = [x for c in b.contexts for x in c.pages if PROY in x.url][0]
    pg.bring_to_front(); pg.keyboard.press("Escape"); pg.wait_for_timeout(500)
    borrar = pg.locator("button[aria-label='Borrar petición']")
    if borrar.count(): borrar.first.click(); pg.wait_for_timeout(800)
    def adjuntar(fichero):
        buscar = os.path.splitext(os.path.basename(fichero))[0]
        pg.locator("button[aria-label^='Añadir ingredientes']").first.click()
        caja = pg.get_by_placeholder("Buscar recursos"); caja.wait_for(timeout=10000)
        caja.fill(buscar); pg.wait_for_timeout(1500)
        nom = buscar + os.path.splitext(fichero)[1]
        item = pg.locator(f"text='{nom}' >> visible=true")
        if not item.count():
            with pg.expect_file_chooser(timeout=15000) as fc:
                pg.locator("text=Subir archivo >> visible=true").first.click()
            fc.value.set_files(fichero); pg.wait_for_timeout(6000)
            caja.fill(""); caja.fill(buscar); pg.wait_for_timeout(2000)
            item = pg.locator(f"text='{nom}' >> visible=true")
        antes = pg.locator("button[aria-label='Ingrediente']").count()
        item.first.click(); pg.wait_for_timeout(1200)
        if pg.locator("button[aria-label='Ingrediente']").count() == antes:
            boton = pg.locator("text='Añadir a petición' >> visible=true")
            if boton.count(): boton.first.click(); pg.wait_for_timeout(1500)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(500)
        if pg.locator("button[aria-label='Ingrediente']").count() != antes + 1:
            print("ERROR no se adjuntó", nom); sys.exit(4)
    for r in refs:
        adjuntar(r)
    n = pg.locator("button[aria-label='Ingrediente']").count()
    if n != len(refs):
        print(f"ERROR adjuntos={n} (esperaba {len(refs)})"); sys.exit(2)
    ed = pg.locator("[contenteditable=true]").last
    ed.click(); pg.keyboard.insert_text(prompt); pg.wait_for_timeout(800)
    s = pg.locator("button[aria-label='Ajustes de generación'], button[aria-label='Activador de ajustes']").first.inner_text()
    if "Nano Banana 2" not in s or "9_16" not in s or "x1" not in s:
        print("ERROR ajustes:", s); sys.exit(3)
    pg.locator("button[aria-label='Iniciar generación']").first.click()
    print("enviado", os.path.basename(ptxt), "adjuntos", n)
