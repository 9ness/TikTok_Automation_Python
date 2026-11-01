"""CDP directo a la pestaña propia (browser.json): Playwright se cuelga al enganchar
todo el Chrome cuando otra pestaña no responde (1/11)."""
import json,asyncio,base64,itertools,os,websockets
from pathlib import Path
TID=json.loads(Path(os.environ.get('BROWSER_JSON','browser.json')).read_text())['target_id']
class Tab:
    def __init__(s): s.n=itertools.count(1)
    async def __aenter__(s):
        s.w=await websockets.connect(f'ws://127.0.0.1:9222/devtools/page/{TID}',max_size=None,open_timeout=20); return s
    async def __aexit__(s,*a): await s.w.close()
    async def cmd(s,method,timeout=60,**params):
        i=next(s.n); await s.w.send(json.dumps({'id':i,'method':method,'params':params}))
        while True:
            r=json.loads(await asyncio.wait_for(s.w.recv(),timeout))
            if r.get('id')==i:
                if 'error' in r: raise RuntimeError(r['error'])
                return r.get('result',{})
    async def js(s,expr,timeout=60):
        r=await s.cmd('Runtime.evaluate',timeout,expression=expr,returnByValue=True,awaitPromise=True)
        if 'exceptionDetails' in r: raise RuntimeError(r['exceptionDetails'])
        return r['result'].get('value')
    async def shot(s,path):
        Path(path).write_bytes(base64.b64decode((await s.cmd('Page.captureScreenshot',format='png'))['data']))
    async def esperar(s,expr,t=90):
        for _ in range(t*2):
            if await s.js(expr): return True
            await asyncio.sleep(0.5)
        return False
