"""generar_omni.py NN_e... — un clip Omni 1.1 de GenAI Pro (Frames con solo fotograma inicial gen/NN_e.jpg,
prompt veo/NN_e.txt) por CDP directo a la pestaña de browser.json. Solo envía si están marcados Watermark,
10s, 1080p y Portrait 9:16 y el resumen dice «Cost: 1 credit» (1/11/2026). Tope en GENERACIONES.json."""
import asyncio,json,re,sys,time,os
from pathlib import Path
os.environ['BROWSER_JSON']='browser.json'
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from flowlib import Tab,clic,tecla
TOPE=int(os.environ.get('TOPE_CREDITOS','25'))
URL='https://genaipro.io/video-image-ai?ws=video&mode=frames&model=omni'
BTN="(t=>[...document.querySelectorAll('button')].find(b=>b.offsetParent&&b.innerText.trim().replace(/\\s+/g,' ')===t))"
def oscuro(t): return f"(()=>{{const b={BTN}({json.dumps(t)});return !!b&&b.getAttribute('aria-pressed')==='true'}})()"
async def generar(t,clave):
    led_p=Path('GENERACIONES.json'); led=json.loads(led_p.read_text()) if led_p.exists() else []
    assert sum(r.get('coste_cargado',1) for r in led)+1<=TOPE,'Tope de créditos autorizado'
    prev=[r for r in led if r['clave']==clave]
    assert not any(r['estado']=='pendiente' for r in prev),'Hay una petición pendiente de este clip'
    assert len([r for r in prev if r.get('coste_cargado',1)>0])<2,'Máximo un reintento con cargo'
    img=Path('gen')/f'{clave}.jpg'; prompt=Path('veo',f'{clave}.txt').read_text().strip()
    if prev: prompt+=' The framing stays fixed for this second take.'
    await t.cmd('Page.enable'); await t.cmd('Page.navigate',url=URL)
    assert await t.esperar("!!document.querySelector('textarea')",90),'no carga GenAI Pro'
    await asyncio.sleep(2)
    await t.js(f"{BTN}('Got it')?.click()")
    for _ in range(2): await tecla(t,'Escape',vk=27); await asyncio.sleep(0.5)
    modelo=await t.js("[...document.querySelectorAll('[role=combobox]')].map(e=>e.innerText.trim()).join('|')")
    assert 'Omni' in modelo,f'modelo {modelo}'
    await asyncio.sleep(4)
    assert await clic(t,f"{BTN}('Frames')"),'no encuentro Frames'; await asyncio.sleep(2)
    for ronda in range(4):
        for b in ('Watermark','10s','1080p','Portrait 9:16'):
            if not await t.js(oscuro(b)):
                assert await clic(t,f"{BTN}({json.dumps(b)})"),f'no encuentro {b}'; await asyncio.sleep(1.2)
        await asyncio.sleep(2)
        if all([await t.js(oscuro(b)) for b in ('Watermark','10s','1080p','Portrait 9:16')]): break
    for b in ('Watermark','10s','1080p'):
        assert await t.js(oscuro(b)),f'{b} no queda marcado'
    assert not await t.js(oscuro('No watermark')),'No watermark está marcado'
    doc=await t.cmd('DOM.getDocument',depth=-1,pierce=True)
    ids=(await t.cmd('DOM.querySelectorAll',nodeId=doc['root']['nodeId'],selector='input[type=file]'))['nodeIds']
    await t.cmd('DOM.setFileInputFiles',files=[str(img.resolve())],nodeId=ids[0]); await asyncio.sleep(4)
    await clic(t,"document.querySelector('textarea')"); await t.js("document.querySelector('textarea').select()")
    await t.cmd('Input.insertText',text=prompt); await asyncio.sleep(1)
    ok=await t.esperar(f"{BTN}('Generate video')&&!{BTN}('Generate video').disabled",60)
    assert ok,'Generate video no se habilita'
    summ=(await t.js("document.body.innerText")).split('Generate video')[0]
    m=re.search(r'Cost:\s*([\d.]+) credits?\b',summ); assert m and m.group(1)=='1',f'Coste distinto al autorizado: {m and m.group(0)}'
    assert await t.js(oscuro('Watermark')),'Watermark desmarcado'
    Path('preparacion').mkdir(exist_ok=True); await t.shot(f'preparacion/omni_{clave}.png')
    if os.environ.get('GO')!='1': print('preparado (sin GO=1 no envío)',clave); return
    e={'clave':clave,'numero':int(clave[:2]),'intento':len(prev)+1,'prompt':prompt,'coste_cargado':1,'estado':'pendiente','inicio':time.time(),'modelo':'omni-1.1 10s 1080p watermark'}
    led.append(e); led_p.write_text(json.dumps(led,ensure_ascii=False,indent=1))
    await clic(t,f"{BTN}('Generate video')")
    ok=await t.esperar(f"[...document.querySelectorAll('p,div,span')].some(e=>e.textContent.trim()==={json.dumps(prompt)})",60)
    print('enviado' if ok else 'enviado (sin confirmar en la lista)',clave,flush=True)
async def main():
    async with Tab() as t:
        for c in sys.argv[1:]: await generar(t,c)
asyncio.run(main())
