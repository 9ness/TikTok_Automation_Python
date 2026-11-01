"""Utilidades CDP para Flow (pestaña de flow_browser.json)."""
import asyncio,json,os
os.environ.setdefault('BROWSER_JSON','flow_browser.json')
from cdp import Tab
async def caja(t,sel_js):
    return await t.js(f"(()=>{{const e={sel_js};if(!e)return null;e.scrollIntoView({{block:'center'}});const r=e.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]}})()")
async def clic_xy(t,x,y):
    for ty in ('mouseMoved','mousePressed','mouseReleased'):
        await t.cmd('Input.dispatchMouseEvent',type=ty,x=x,y=y,button='left',clickCount=1)
async def clic(t,sel_js):
    c=await caja(t,sel_js)
    if not c: return False
    await clic_xy(t,*c); return True
def q(css): return f"document.querySelector({json.dumps(css)})"
def txt(t_,tag='*'):
    return f"[...document.querySelectorAll({json.dumps(tag)})].filter(e=>e.offsetParent&&e.innerText&&e.innerText.trim()==={json.dumps(t_)}).pop()"
async def tecla(t,key,code=None,vk=0):
    for ty in ('keyDown','keyUp'):
        await t.cmd('Input.dispatchKeyEvent',type=ty,key=key,code=code or key,windowsVirtualKeyCode=vk)

class TabEv(Tab):
    """Tab que guarda los eventos CDP que llegan mientras espera respuestas."""
    async def cmd(s,method,timeout=60,**params):
        import itertools
        if not hasattr(s,'ev'): s.ev=[]
        i=next(s.n); await s.w.send(json.dumps({'id':i,'method':method,'params':params}))
        while True:
            r=json.loads(await asyncio.wait_for(s.w.recv(),timeout))
            if r.get('id')==i:
                if 'error' in r: raise RuntimeError(r['error'])
                return r.get('result',{})
            if 'method' in r: s.ev.append(r)
    async def evento(s,nombre,t=20):
        if not hasattr(s,'ev'): s.ev=[]
        fin=asyncio.get_event_loop().time()+t
        while asyncio.get_event_loop().time()<fin:
            for e in s.ev:
                if e['method']==nombre: s.ev.remove(e); return e['params']
            try:
                r=json.loads(await asyncio.wait_for(s.w.recv(),1))
                if 'method' in r: s.ev.append(r)
            except asyncio.TimeoutError: pass
        return None

JS_CARDS="""JSON.stringify([...document.querySelectorAll('img[src*="/asb/"]')].map(i=>[i.src, i.closest('[aria-label]')?.getAttribute('aria-label')||'']))"""
