"""maggen.py <prompt.txt> <start.png> — un vídeo en el Video Generator de Magnific (Kling 2.5 · 720 · 10s · 9:16 · ilimitado)."""
import sys
from playwright.sync_api import sync_playwright
ptxt, ini = sys.argv[1], sys.argv[2]
prompt = open(ptxt, encoding="utf-8").read().strip()
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    pg = [x for c in b.contexts for x in c.pages if "ai-video-generator" in x.url][0]
    pg.bring_to_front()
    if not pg.get_by_text("Upload media").count() or not pg.get_by_text("Upload media").first.is_visible():
        pg.get_by_text("Start image").first.click(); pg.wait_for_timeout(1500)
    with pg.expect_file_chooser(timeout=15000) as fc:
        pg.get_by_text("Upload media").first.click()
    fc.value.set_files(ini); pg.wait_for_timeout(8000)
    pg.get_by_role("button", name="Add", exact=True).first.click(); pg.wait_for_timeout(2500)
    ta = pg.locator("[contenteditable=true], textarea").first
    ta.click(); pg.keyboard.press("Control+A"); pg.keyboard.press("Delete")
    pg.keyboard.insert_text(prompt); pg.wait_for_timeout(800)
    barra = pg.locator("text=Kling 2.5").first.inner_text()
    print("modelo:", barra)
    pg.screenshot(path="/tmp/mag_antes.png")
    pg.get_by_role("button", name="Generate").first.click(); pg.wait_for_timeout(4000)
    print("enviado", ptxt)
