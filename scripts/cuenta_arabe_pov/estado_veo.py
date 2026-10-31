import os,json,re;os.environ['BROWSER_JSON']='browser.json'
from browser import own_page,sync_playwright
L=json.load(open('GENERACIONES.json'))
with sync_playwright() as p:
  pg=own_page(p.chromium.connect_over_cdp('http://127.0.0.1:9222'))
  pg.goto('https://genaipro.io/video-image-ai?ws=video&mode=frames&model=veo',wait_until='domcontentloaded',timeout=90000);pg.wait_for_timeout(5000);pg.keyboard.press('Escape');pg.wait_for_timeout(1000)
  t=pg.locator('body').inner_text()
  for r in L:
    if r['estado']!='pendiente':continue
    i=t.find(r['prompt'][:100]); seg=re.split(r'\d+/\d+/\d{4}, [\d:]+ [AP]M',t[:i])[-1] if i>=0 else 'NOENC'
    print(r['clave'],r['intento'],'FALLO' if 'Failed' in seg else 'GENERANDO' if 'Generating' in seg else 'NOENC' if seg=='NOENC' else 'LISTO')
