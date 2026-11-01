"""montar8.py N — 2 clips Veo (CONTROL_CALIDAD[N]) + cabecera animada (fundido + deslizamiento),
cierre con fundido, flecha naranja que rebota, whoosh/pop suaves. Sin voz: mudo salvo los efectos (el sonido comercial se pone al subir). Con voz (el viral la lleva):
audio/NN_fish.mp3 + audio/NN_subs.json [[ini,fin,texto],...] → voz al 100 %, efectos al 40 %, subtítulos."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))   # repo: detección de la marca de Omni
from src.nicho_pov_bof.config import es_clip_omni,filtro_encuadre,ZOOM_MARCA_OMNI,ESQUINA_MARCA_OMNI
from PIL import Image,ImageDraw
from produccion import overlay,contact_sheet,probe,run,clean_metadata,SAFE
def partir(subs,maxp=6):
    """Trozos de más de maxp palabras → dos subtítulos (por la coma o por la mitad), tiempo según palabras."""
    out=[]
    for ini,fin,txt in subs:
        w=txt.split()
        if len(w)<=maxp: out.append([ini,fin,txt]); continue
        cut=next((j+1 for j,x in enumerate(w[:-1]) if x.endswith('،') and 2<=j+1<=len(w)-2),len(w)//2)
        a,b=' '.join(w[:cut]).rstrip('،'),' '.join(w[cut:]); m=round(ini+(fin-ini)*cut/len(w),2)
        out+= [[ini,m,a],[m,fin,b]]
    return out

def mount(n):
    plan=next(r for r in json.loads(Path('PLAN.json').read_text()) if r['numero']==n)
    ctl=json.loads(Path('CONTROL_CALIDAD.json').read_text())[str(n)]; assert ctl['aceptado']
    clips=ctl['brutos']; durs=ctl['duraciones']; total=sum(durs)
    f=Path('capas')/f'{n:02d}'; f.mkdir(parents=True,exist_ok=True)
    head=f/'cabecera.png'; overlay(plan['bloques'],head)
    tail=f/'cierre.png'; overlay(plan['cierre_bloques'],tail)
    arrow=Image.new('RGBA',(1080,1920)); pts=[(122,1360),(148,1360),(148,1391),(167,1391),(135,1422),(103,1391),(122,1391)]
    ImageDraw.Draw(arrow).polygon(pts,fill='#f17620'); arrow.save(f/'flecha.png')
    tc=round(total-2.8,2)
    voz=Path(f'audio/{n:02d}_fish.mp3'); subs=[]
    if voz.exists():
        for i,(ini,fin,txt) in enumerate(partir(json.loads(Path(f'audio/{n:02d}_subs.json').read_text()))):
            sp=f/f'sub_{i}.png'; overlay([{'text':txt,'box':[64,1020,820,1135],'size':54,'background':'#171717'}],sp); subs.append((sp,ini,min(fin,total)))
    a=['ffmpeg','-y','-v','error','-threads','2']
    for c in clips: a+=['-i',c]
    for p in (head,tail,f/'flecha.png'): a+=['-loop','1','-t',str(total),'-i',str(p)]
    for sp,_,_ in subs: a+=['-loop','1','-t',str(total),'-i',str(sp)]
    a+=['-i','sfx/whoosh.wav','-i','sfx/pop.wav','-i','sfx/pop.wav','-f','lavfi','-t',str(total),'-i','anullsrc=r=48000:cl=stereo']
    if subs: a+=['-i',str(voz)]
    k=len(clips); ch=[]; ns=len(subs); kk=k+3+ns  # índice del primer sfx
    for i,(c,d) in enumerate(zip(clips,durs)):
        # Omni 1 cr lleva la estrella abajo a la derecha: se amplía un 14 % tirando la franja de abajo.
        # `omni: true` en CONTROL_CALIDAD lo fuerza (la detección falla en fondos con mucha textura)
        enc=filtro_encuadre(1080,1920,30,zoom=ZOOM_MARCA_OMNI,esquina=ESQUINA_MARCA_OMNI,acabado=False) if ctl.get('omni') or es_clip_omni(c) else 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30'
        ch.append(f'[{i}:v]trim=duration={d},setpts=PTS-STARTPTS,{enc}[v{i}]')
    ch.append(''.join(f'[v{i}]' for i in range(k))+f'concat=n={k}:v=1:a=0[base]')
    ch.append(f'[{k}:v]format=rgba,fade=t=in:st=0.1:d=0.35:alpha=1[h]')
    ch.append(f'[{k+1}:v]format=rgba,fade=t=in:st={tc}:d=0.3:alpha=1[t]')
    ch.append(f'[{k+2}:v]format=rgba,fade=t=in:st={tc+0.3}:d=0.2:alpha=1[ar]')
    ch.append("[base][h]overlay=x=0:y='if(lt(t,0.45),30*(1-t/0.45),0)':eval=frame[o1]")
    ch.append(f"[o1][t]overlay=enable='gte(t,{tc})'[o2]")
    last='o3' if subs else 'vout'
    ch.append(f"[o2][ar]overlay=x=0:y='10*abs(sin(2*PI*1.6*t))':eval=frame:enable='gte(t,{tc+0.3})'[{last}]")
    for i,(sp,ini,fin) in enumerate(subs):
        nxt='vout' if i==ns-1 else f'q{i}'
        ch.append(f"[{last}][{k+3+i}:v]overlay=enable='between(t,{ini},{fin})'[{nxt}]"); last=nxt
    g=0.4 if subs else 1.0
    ch.append(f'[{kk}:a]adelay=80|80,volume={g}[s1];[{kk+1}:a]adelay=350|350,volume={g}[s2];[{kk+2}:a]adelay={int((tc+0.3)*1000)}|{int((tc+0.3)*1000)},volume={g}[s3]')
    if subs:
        ch.append(f'[{kk+4}:a]aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-14:TP=-2.0:LRA=7,apad[vz]')
        ch.append(f'[{kk+3}:a][vz][s1][s2][s3]amix=inputs=5:normalize=0:duration=first[aout]')
    else:
        ch.append(f'[{kk+3}:a][s1][s2][s3]amix=inputs=4:normalize=0:duration=first[aout]')
    out=Path(plan['archivo']); out.parent.mkdir(exist_ok=True)
    a+=['-filter_complex',';'.join(ch),'-map','[vout]','-map','[aout]','-t',str(total),'-c:v','libx264','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-b:a','128k','-movflags','+faststart',str(out)]
    run(a); clean_metadata(out); m=probe(out)
    assert not {'encoder','creation_time','comment'}&set(m['format'].get('tags',{}))
    contact_sheet(out,Path('revision')/f'{n:02d}.jpg'); print(f'{n:02d} montado {total:.1f}s')
if __name__=='__main__':
    for x in sys.argv[1:]: mount(int(x))
