"""Vídeos de cada creadora en Social1 (pestaña propia en Chrome 9222) → JSON."""
import sys, json, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, "/home/nebulabsai/proyectos/TikTok_Automation_Python/scripts")
from social1_carruseles import JS, fila
handles=sys.argv[1].split(","); out=sys.argv[2]
res={}
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp("http://127.0.0.1:9222"); pg=b.contexts[0].new_page()
    try:
        for h in handles:
            pg.goto(f"https://www.social1.ai/creators/{h}", timeout=60000); time.sleep(6)
            vistos={}
            for _ in range(12):
                for r in pg.evaluate(JS): vistos[r["video_id"]]=r
                pg.mouse.wheel(0,4000); time.sleep(2.5)
            filas=[]
            for r in vistos.values():
                f=fila(r); f["dur"]=r.get("duration") or r.get("video_duration"); filas.append(f)
            res[h]=filas; print(h,len(filas),flush=True)
            if filas and h==handles[0]: print(json.dumps(list(vistos.values())[0],ensure_ascii=False)[:1500])
    finally: pg.close()
json.dump(res,open(out,"w"),ensure_ascii=False,indent=1)
