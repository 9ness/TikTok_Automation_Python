"""subs8.py NN... — voz con 0,3 s de entrada → audio/NN_fish.mp3, y subtítulos audio/NN_subs.json:
cada trozo del guion entre las pausas más largas de la voz (silencedetect)."""
import json,re,subprocess,sys
from pathlib import Path
G=json.loads(Path('audio/guiones.json').read_text()); D=0.3
def dur(p): return float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(p)],capture_output=True,text=True).stdout)
for n in sys.argv[1:]:
    raw=Path(f'audio/{n}_fish_raw.mp3'); T=dur(raw); trozos=G[n]
    err=subprocess.run(['ffmpeg','-i',str(raw),'-af','silencedetect=n=-35dB:d=0.15','-f','null','-'],capture_output=True,text=True).stderr
    ini=[float(x) for x in re.findall(r'silence_start: ([\d.]+)',err)]; fin=[float(x) for x in re.findall(r'silence_end: ([\d.]+)',err)]
    pausas=[((a+b)/2,b-a) for a,b in zip(ini,fin) if 0.3<a<T-0.3]
    # cortes: las k-1 pausas más largas, en orden; si faltan, reparto por caracteres
    k=len(trozos); cortes=sorted(p for p,_ in sorted(pausas,key=lambda x:-x[1])[:k-1])
    if len(cortes)<k-1:
        tot=sum(map(len,trozos)); acc=0; cortes=[]
        for t in trozos[:-1]: acc+=len(t); cortes.append(T*acc/tot)
    lim=[0.0]+cortes+[T]
    subs=[[round(lim[i]+D,2),round(lim[i+1]+D,2),trozos[i]] for i in range(k)]
    Path(f'audio/{n}_subs.json').write_text(json.dumps(subs,ensure_ascii=False))
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(raw),'-af',f'adelay={int(D*1000)}|{int(D*1000)}','-ar','48000',f'audio/{n}_fish.mp3'],check=True)
    print(n,[(a,b) for a,b,_ in subs],'pausas',len(pausas))
