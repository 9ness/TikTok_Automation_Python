"""genaigen.py <prompt.txt> <start.png> [end.png] — un vídeo en GenAI Pro (Veo · Frames · 9:16 · 1 · Original)."""
import sys
from playwright.sync_api import sync_playwright
ptxt, ini = sys.argv[1], sys.argv[2]
fin = sys.argv[3] if len(sys.argv) > 3 else None
prompt = open(ptxt, encoding="utf-8").read().strip()
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    pg = [x for c in b.contexts for x in c.pages if "genaipro" in x.url][0]
    pg.bring_to_front()
    pg.get_by_text("Frames", exact=True).first.click(); pg.wait_for_timeout(600)
    # Quitar los fotogramas del vídeo anterior (la ✕ de cada miniatura).
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    pg.evaluate("""() => { for (const b of [...document.querySelectorAll('button')]) {
        const r = b.getBoundingClientRect(); const im = b.parentElement && b.parentElement.querySelector('img');
        if (r.x > 80 && r.x < 430 && r.width < 40 && !b.innerText.trim() && im && im.naturalWidth > 300) b.click(); } }""")
    pg.wait_for_timeout(800)
    ta = pg.locator("textarea").first
    ta.fill(prompt); pg.wait_for_timeout(400)
    files = pg.locator("input[type=file]")
    files.nth(0).set_input_files(ini); pg.wait_for_timeout(2500)
    if fin:
        files = pg.locator("input[type=file]")
        files.nth(files.count() - 1 if files.count() > 1 else 0).set_input_files(fin); pg.wait_for_timeout(2500)
    pg.get_by_text("Portrait", exact=False).first.click(); pg.wait_for_timeout(400)
    pg.get_by_role("button", name="1", exact=True).first.click(); pg.wait_for_timeout(300)
    pg.get_by_text("Original", exact=True).first.click(); pg.wait_for_timeout(300)
    coste = pg.get_by_text("Cost:").first.locator("xpath=..").inner_text()
    print("coste:", coste.replace("\n", " "))
    if "1 credit" not in coste:
        print("ERROR coste inesperado"); sys.exit(3)
    pg.get_by_role("button", name="Generate video").first.click(); pg.wait_for_timeout(3000)
    print("enviado", ptxt)
