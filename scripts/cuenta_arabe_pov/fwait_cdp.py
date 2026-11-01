"""fwait_cdp.py snap | fwait_cdp.py out.jpg [timeout_s] — espera la imagen NUEVA de Flow y la baja (CDP directo).
Flow (1/11/2026) sirve lo generado desde flow-content.google/image/<uuid>?Expires… (URL firmada, 768x1376 en 9:16):
nueva = uuid que no estaba en el snap. Las subidas siguen en /asb/ y no cuentan."""
import asyncio,os,sys,re,json,time
import requests
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from flowlib import *
SNAP=os.path.join(os.path.dirname(os.path.abspath(__file__)),'snap.json')
JS="JSON.stringify([...document.querySelectorAll('img[src*=\"flow-content.google/image/\"]')].map(i=>[i.src,i.closest('[aria-label]')?.getAttribute('aria-label')||'']))"
uid=lambda u: re.search(r'/image/([0-9a-f-]+)',u).group(1)
async def m():
    async with Tab() as t:
        if '/edit/' in await t.js('location.href'):
            await t.js('history.back()'); await asyncio.sleep(3)
        if sys.argv[1]=='snap':
            json.dump([uid(a[0]) for a in json.loads(await t.js(JS))],open(SNAP,'w')); print('snap ok'); return
        viejas=set(json.load(open(SNAP))); fin=time.time()+float(sys.argv[2] if len(sys.argv)>2 else 300)
        while time.time()<fin:
            await asyncio.sleep(4)
            nuevas=[c for c in json.loads(await t.js(JS)) if uid(c[0]) not in viejas]
            if nuevas:
                await asyncio.sleep(2)
                d=requests.get(nuevas[0][0],timeout=90).content
                if len(d)<20000: print('VACIA',len(d)); sys.exit(3)
                from PIL import Image; import io
                w,h=Image.open(io.BytesIO(d)).size
                if h<1.6*w: viejas.add(uid(nuevas[0][0])); print('descarto (no es 9:16)',w,h); continue
                open(sys.argv[1],'wb').write(d); print('ok',sys.argv[1],nuevas[0][1]); return
        print('TIMEOUT'); sys.exit(2)
asyncio.run(m())
