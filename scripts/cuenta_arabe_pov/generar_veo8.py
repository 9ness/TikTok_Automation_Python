"""generar_veo8.py NN_e — un clip Veo (Frames, solo fotograma inicial gen/NN_e.jpg, prompt veo/NN_e.txt) en la pestaña propia."""
import json,re,sys,time,os
from pathlib import Path
os.environ.setdefault('BROWSER_JSON','browser.json')
from browser import own_page,sync_playwright
from playwright.sync_api import expect, TimeoutError as PT
TOPE=25
def generate(clave):
    led_p=Path('GENERACIONES.json'); led=json.loads(led_p.read_text()) if led_p.exists() else []
    assert sum(r.get('coste_cargado',1) for r in led)+1<=TOPE,'Tope de créditos autorizado'
    prev=[r for r in led if r['clave']==clave]
    assert not any(r['estado']=='pendiente' for r in prev),'Hay una petición pendiente de este clip'
    assert len([r for r in prev if r.get('coste_cargado',1)>0])<2,'Máximo un reintento con cargo'
    img=Path('gen')/f'{clave}.jpg'; prompt=Path('veo',f'{clave}.txt').read_text().strip()
    if prev: prompt+=' The framing stays fixed for this second take.'
    with sync_playwright() as p:
        pg=own_page(p.chromium.connect_over_cdp('http://127.0.0.1:9222')); pg.set_default_timeout(20000)
        pg.goto('https://genaipro.io/video-image-ai?ws=video&mode=frames&model=veo',wait_until='commit',timeout=120000)
        pg.locator('textarea').wait_for(timeout=90000)
        try: pg.get_by_role('button',name='Got it',exact=True).click(timeout=5000)
        except PT: pass
        for _ in range(2):
            pg.keyboard.press('Escape'); pg.wait_for_timeout(800)
        assert pg.get_by_role('combobox').inner_text().strip()=='Veo'
        pg.locator('button').filter(has_text=re.compile('^Frames$')).click()
        pg.locator('button').filter(has_text=re.compile('^Portrait')).click()
        pg.locator('button').filter(has_text=re.compile('^Original$')).click()
        pg.locator('input[type=file]').nth(0).set_input_files(str(img.resolve()))
        pg.locator('textarea').fill(prompt)
        btn=pg.get_by_role('button',name='Generate video',exact=True); expect(btn).to_be_enabled(timeout=60000)
        summ=pg.locator('body').inner_text().split('Generate video')[0]
        assert re.search(r'Cost:\s*1 credit\b',summ),'Coste distinto al autorizado'
        pg.screenshot(path=f'preparacion/veo_{clave}.png')
        e={'clave':clave,'numero':int(clave[:2]),'intento':len(prev)+1,'prompt':prompt,'coste_cargado':1,'estado':'pendiente','inicio':time.time()}
        led.append(e); led_p.write_text(json.dumps(led,ensure_ascii=False,indent=1))
        btn.click(); pg.get_by_text(prompt,exact=True).first.wait_for(state='visible',timeout=60000)
        print('enviado',clave,flush=True)
if __name__=='__main__':
    for c in sys.argv[1:]: generate(c)
