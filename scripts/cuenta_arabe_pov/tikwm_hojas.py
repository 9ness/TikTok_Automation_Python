import json, subprocess, time, urllib.request, urllib.parse, os
usados=set(open("usados.txt").read().split())
filas=json.load(open("todas.json"))
# mejor publicación por producto (más GMV, luego visitas), solo con señal
mejor={}
for f in filas:
    pid=f["product_id"]
    if not pid or pid in usados: continue
    if (f["gmv"] or 0)<1 and (f["views"] or 0)<3000: continue
    mejor.setdefault(pid,[]).append(f)
cands=[v for vs in mejor.values() for v in vs[:2]]
out=[]
for f in cands:
    vid=f["video_id"]; url=f["url"]
    try:
        q=urllib.request.Request("https://www.tikwm.com/api/?hd=1&url="+urllib.parse.quote(url),headers={"User-Agent":"Mozilla/5.0"})
        d=json.load(urllib.request.urlopen(q,timeout=30)).get("data") or {}
    except Exception as e:
        print("ERR",vid,e); time.sleep(2); continue
    f["tipo"]="foto" if d.get("images") else "video"; f["dur"]=d.get("duration"); f["titulo_tt"]=d.get("title")
    f["musica"]=(d.get("music_info") or {}).get("title")
    if f["tipo"]=="video" and d.get("play"):
        mp4=f"media/{vid}.mp4"
        if not os.path.exists(mp4):
            subprocess.run(["curl","-sL","-m","120","-o",mp4,d["play"]])
        dur=float(d.get("duration") or 10)
        sel="+".join(f"eq(n\\,{0})" for _ in [0])
        # 8 fotogramas repartidos
        subprocess.run(["ffmpeg","-v","error","-y","-i",mp4,"-vf",f"fps=8/{max(dur,1)},scale=180:-1,tile=8x1","-frames:v","1",f"hojas/{vid}.jpg"])
    out.append(f); print(f["tipo"],f["dur"],vid,(f["producto"] or "")[:50],flush=True)
    time.sleep(1.2)
json.dump(out,open("candidatos.json","w"),ensure_ascii=False,indent=1)
