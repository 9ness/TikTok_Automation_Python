"""alinear8.py NN... — subtítulos por palabras: Whisper small (ar) con tiempos de palabra sobre la voz Fish;
cada trozo del guion acaba en la palabra que toca por proporción de palabras. Escribe audio/NN_subs.json."""
import json,subprocess,sys,numpy as np
from pathlib import Path
from faster_whisper import WhisperModel
G=json.loads(Path('audio/guiones.json').read_text()); D=0.3
m=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=2)
for n in sys.argv[1:]:
    a=subprocess.run(['ffmpeg','-v','error','-i',f'audio/{n}_fish_raw.mp3','-ar','16000','-ac','1','-f','f32le','-'],capture_output=True,check=True).stdout
    segs,_=m.transcribe(np.frombuffer(a,np.float32),language='ar',word_timestamps=True,vad_filter=False)
    w=[x for s in segs for x in s.words]; tr=G[n]; nw=[len(t.split()) for t in tr]; tot=sum(nw)
    subs=[]; acc=0; t0=w[0].start
    for i,t in enumerate(tr):
        acc+=nw[i]; j=min(len(w)-1,max(0,round(len(w)*acc/tot)-1))
        t1=w[j].end if i<len(tr)-1 else w[-1].end
        subs.append([round(t0+D,2),round(t1+D,2),t]); t0=t1
    Path(f'audio/{n}_subs.json').write_text(json.dumps(subs,ensure_ascii=False))
    print(n,len(w),'palabras',[(a,b) for a,b,_ in subs],'|',' '.join(x.word for x in w)[:120],flush=True)
