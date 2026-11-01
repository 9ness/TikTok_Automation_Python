"""recoger_omni.py — baja a brutos/ los clips pendientes de GENERACIONES.json (busca por prompt exacto)."""
import asyncio,json,os,sys
from pathlib import Path
import requests
os.environ['BROWSER_JSON']='browser.json'
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from flowlib import Tab
URL='https://genaipro.io/video-image-ai?ws=video&mode=frames&model=omni'
JS='''(prompt=>{
  const matches=[...document.querySelectorAll('p,div,span')].filter(e=>e.textContent.trim()===prompt);
  matches.sort((a,b)=>a.querySelectorAll('*').length-b.querySelectorAll('*').length);
  for(let e of matches){
    for(let j=0;e&&j<8;j++,e=e.parentElement){
      const cards=(e.innerText.match(/\\d+\\/\\d+\\/\\d{4}, \\d+:\\d+:\\d+/g)||[]).length;
      if(cards>1)break;
      if(e.innerText.includes('Failed')&&e.innerText.includes('refunded'))return {failed:true,text:e.innerText};
      const v=[...e.querySelectorAll('video')];
      if(v.length===1&&cards===1)return {url:v[0].currentSrc||v[0].src,text:e.innerText};
      if(v.length>1)break;
    }
  }
  return null;})'''
async def main():
    p=Path('GENERACIONES.json'); led=json.loads(p.read_text())
    async with Tab() as t:
        await t.cmd('Page.navigate',url=URL); await asyncio.sleep(10)
        for e in led:
            if e['estado']!='pendiente': continue
            r=await t.js(f"{JS}({json.dumps(e['prompt'])})")
            if r and r.get('failed'): e.update(estado='fallido_reembolsado',coste_cargado=0,diagnostico=r['text'][:600])
            elif r and r.get('url','').startswith('https://files.genaipro.io/'):
                d=Path('brutos')/f"{e['clave']}_i{e['intento']}.mp4"; d.parent.mkdir(exist_ok=True)
                x=requests.get(r['url'],timeout=120); x.raise_for_status(); d.write_bytes(x.content)
                e.update(estado='descargado',archivo=str(d),url=r['url'])
    p.write_text(json.dumps(led,ensure_ascii=False,indent=1))
    print([(r['clave'],r['estado']) for r in led])
asyncio.run(main())
