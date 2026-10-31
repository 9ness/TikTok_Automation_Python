"""voz8.py NN... — locución Fish (s2.1-pro-free, voz automática) del guion darija de audio/guiones.json.
La clave se lee de .env solo en memoria; no se imprime. Coste registrado con cost_tracking (0 $)."""
import os,sys,json,time,requests,subprocess
from pathlib import Path
REPO=Path.home()/'proyectos/TikTok_Automation_Python'
for line in (REPO/'.env').read_text().splitlines():
    k,sep,v=line.partition('=')
    if sep and k.strip() in {'FISH_API_KEY','UPSTASH_REDIS_REST_URL','UPSTASH_REDIS_REST_TOKEN','FABRICA_REDIS_REST_URL','FABRICA_REDIS_REST_TOKEN'}:
        os.environ.setdefault(k.strip(),v.strip().strip('"\''))
sys.dont_write_bytecode=True; sys.path.insert(0,str(REPO))
from src import cost_tracking
G=json.loads(Path('audio/guiones.json').read_text())
def dur(p): return float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(p)],capture_output=True,text=True).stdout)
def voz(n):
    dest=Path(f'audio/{n}_fish_raw.mp3')
    texto='، '.join(G[n])+'.'
    if not dest.exists():
        cost_tracking.start_job(f'hmizat_r8_fish_{n}_{int(time.time())}','ai_pro','hmizat_r8',user='nes_bugallo',title=f'Ronda 8 vídeo {n}')
        r=requests.post('https://api.fish.audio/v1/tts',headers={'Authorization':f"Bearer {os.environ['FISH_API_KEY']}",'Content-Type':'application/json','model':'s2.1-pro-free'},json={'text':texto,'format':'mp3'},timeout=180)
        if r.status_code!=200: raise RuntimeError(f'Fish HTTP {r.status_code}')
        dest.write_bytes(r.content)
        cost_tracking.record_custom(kind='fish_tts',units=len(texto.encode()),unit_label='bytes',cost_usd=0.0,detail='s2.1-pro-free · voz automática, guion darija ronda 8')
        cost_tracking.finalize_and_persist()
    print(n,round(dur(dest),2),'s',flush=True)
for n in sys.argv[1:]: voz(n)
