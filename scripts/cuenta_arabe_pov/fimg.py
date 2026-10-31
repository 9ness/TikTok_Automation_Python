"""flow_img.py <prompt.txt> <ref1.jpg> [ref2.jpg ...] — adjunta refs (por nombre, subiéndolas si no están), pega prompt y genera."""
import sys, os
from playwright.sync_api import sync_playwright
ptxt, refs = sys.argv[1], sys.argv[2:]
prompt = open(ptxt, encoding="utf-8").read().strip()
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    pg = [x for c in b.contexts for x in c.pages if os.environ.get('FLOW_PROYECTO', '069b39d9') in x.url][0]
    pg.bring_to_front(); pg.keyboard.press("Escape"); pg.wait_for_timeout(500)
    while pg.locator("button[aria-label='Borrar petición']").count():
        pg.locator("button[aria-label='Borrar petición']").first.click(); pg.wait_for_timeout(800)
    for f in refs:
        buscar = os.path.splitext(os.path.basename(f))[0]; nom = buscar + ".jpg"
        pg.locator("button[aria-label^='Añadir ingredientes']").first.click()
        caja = pg.get_by_placeholder("Buscar recursos"); caja.wait_for(timeout=10000)
        caja.fill(buscar); pg.wait_for_timeout(1500)
        item = pg.locator(f"text='{nom}' >> visible=true")
        if not item.count():
            with pg.expect_file_chooser(timeout=15000) as fc:
                pg.locator("text=Subir archivo >> visible=true").first.click()
            fc.value.set_files(f); pg.wait_for_timeout(12000)
            caja.fill(""); caja.fill(buscar); pg.wait_for_timeout(2000)
            item = pg.locator(f"text='{nom}' >> visible=true")
        antes = pg.locator("button[aria-label='Ingrediente']").count()
        item.first.click(); pg.wait_for_timeout(1200)
        if pg.locator("button[aria-label='Ingrediente']").count() == antes:
            bt = pg.locator("text='Añadir a petición' >> visible=true")
            if bt.count(): bt.first.click(); pg.wait_for_timeout(1500)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(500)
        if pg.locator("button[aria-label='Ingrediente']").count() != antes + 1:
            print("ERROR no se adjuntó", nom); pg.screenshot(path="/tmp/flowerr.png"); sys.exit(4)
    ed = pg.locator("[contenteditable=true]").last
    ed.click(); pg.keyboard.insert_text(prompt); pg.wait_for_timeout(800)
    s = pg.locator("button[aria-label='Ajustes de generación'], button[aria-label='Activador de ajustes']").first.inner_text()
    print("ajustes:", s.replace("\n", " "))
    if os.getenv("GO") == "1":
        pg.locator("button[aria-label='Iniciar generación']").first.click(); print("enviado")
    pg.screenshot(path="/tmp/flowpre.png")
