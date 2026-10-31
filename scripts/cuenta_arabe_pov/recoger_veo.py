"""Consulta solo resultados identificados por los prompts de esta ronda."""
import json
from pathlib import Path
import requests
from browser import own_page,sync_playwright

def collect():
    import os;path=Path(os.environ.get('LEDGER','GENERACIONES.json'))
    ledger=json.loads(path.read_text()) if path.exists() else []
    if not ledger:print('No hay peticiones enviadas.');return
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp('http://127.0.0.1:9222');page=own_page(browser);page.goto('https://genaipro.io/video-image-ai?ws=video&mode=frames&model=veo',wait_until='domcontentloaded',timeout=90000);page.wait_for_timeout(8000);page.keyboard.press('Escape');page.wait_for_timeout(1500)
        for entry in ledger:
            if entry['estado']!='pendiente':continue
            result=page.evaluate('''prompt=>{
              const matches=[...document.querySelectorAll('p,div,span')].filter(e=>e.textContent.trim()===prompt);
              matches.sort((a,b)=>a.querySelectorAll('*').length-b.querySelectorAll('*').length);
              for(let e of matches){
                for(let j=0;e&&j<8;j++,e=e.parentElement){
                  const cards=(e.innerText.match(/\d+\/\d+\/\d{4}, \d+:\d+:\d+/g)||[]).length;
                  if(cards>1)break;
                  if(e.innerText.includes('Failed')&&e.innerText.includes('refunded'))return {failed:true,text:e.innerText};
                  const videos=[...e.querySelectorAll('video')];
                  if(videos.length===1&&cards===1){const v=videos[0];return {url:v.currentSrc||v.src,text:e.innerText};}
                  if(videos.length>1)break;
                }
              }
              return null;
            }''',entry['prompt'])
            if result and result.get('failed'):
                entry.update(estado='fallido_reembolsado',coste_cargado=0,diagnostico=result['text'][:1200])
            elif result and result.get('url','').startswith('https://files.genaipro.io/'):
                dest=Path("brutos")/f"{entry['clave']}_i{entry['intento']}.mp4";dest.parent.mkdir(exist_ok=True)
                r=requests.get(result['url'],timeout=90);r.raise_for_status();dest.write_bytes(r.content)
                entry.update(estado='descargado',archivo=str(dest),url=result['url'])
    path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
    print([{k:r.get(k) for k in ['numero','intento','estado','coste_cargado']} for r in ledger])
if __name__=='__main__':collect()
