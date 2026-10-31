"""Montaje y comprobaciones de los clips Veo aprobados de esta ronda.
No genera clips, no publica y no modifica el repositorio.
"""
import ast
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
REPO=Path.home()/'proyectos/TikTok_Automation_Python'
FONT=REPO/'assets/fonts/Tajawal-ExtraBold.ttf'
W,H=1080,1920
SAFE=(54,288,842,1440)

def run(args):
    return subprocess.run(args,check=True,capture_output=True).stdout

def probe(path):
    return json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))

def overlay(lines, output):
    """Cada bloque declara texto, recuadro, colores y tamaño máximo.
    El bbox de tinta real se centra y se verifica con margen.
    """
    canvas=Image.new('RGBA',(W,H));draw=ImageDraw.Draw(canvas);checks=[]
    for block in lines:
        x0,y0,x1,y1=block['box']; margin=block.get('margin',18)
        assert SAFE[0]<=x0<x1<=SAFE[2] and SAFE[1]<=y0<y1<=SAFE[3]
        text=block['text'];rtl=any('\u0600'<=c<='\u06ff' for c in text)
        options={'direction':'rtl' if rtl else 'ltr'}
        for size in range(block.get('size',64),17,-1):
            font=ImageFont.truetype(str(FONT),size)
            bbox=draw.textbbox((0,0),text,font=font,**options)
            tw,th=bbox[2]-bbox[0],bbox[3]-bbox[1]
            if tw<=x1-x0-2*margin and th<=y1-y0-2*margin: break
        else: raise ValueError('Texto no cabe: '+text)
        draw.rectangle((x0,y0,x1,y1),fill=block.get('background','#c41e26'))
        px=x0+(x1-x0-tw)/2-bbox[0];py=y0+(y1-y0-th)/2-bbox[1]
        ink=draw.textbbox((px,py),text,font=font,**options)
        assert x0+margin<=ink[0] and ink[2]<=x1-margin
        assert y0+margin<=ink[1] and ink[3]<=y1-margin
        draw.text((px,py),text,font=font,fill=block.get('color','white'),**options)
        checks.append({'text':text,'box':block['box'],'ink':ink,'font_size':size})
    canvas.save(output)
    Path(output).with_suffix('.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))

def clean_metadata(path):
    """Ejecuta la función exacta limpiar_metadatos del repo, sin imports ajenos."""
    source=(REPO/'src/nicho_pov_bof/pipeline/video_editor.py').read_text()
    tree=ast.parse(source)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='limpiar_metadatos')
    env={'Path':Path,'OnLog':object,'_noop':lambda *a:None,
         '_run':lambda args,on_log:run(args)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(REPO/'src/nicho_pov_bof/pipeline/video_editor.py'),'exec'),env)
    env['limpiar_metadatos'](Path(path),print)

def contact_sheet(path,output):
    meta=probe(path);duration=float(meta['format']['duration'])
    sheet=Image.new('RGB',(5*216,3*414),'#202020');draw=ImageDraw.Draw(sheet)
    for i in range(15):
        t=(duration-0.15)*i/14
        raw=run(['ffmpeg','-v','error','-ss',str(t),'-i',str(path),'-frames:v','1','-vf','scale=216:384','-f','image2pipe','-vcodec','png','-threads','1','-'])
        import io
        frame=Image.open(io.BytesIO(raw)).convert('RGB');x=(i%5)*216;y=(i//5)*414
        sheet.paste(frame,(x,y));draw.text((x+8,y+388),f'{i+1:02d} | {t:.2f}s',fill='white')
    sheet.save(output,quality=94)
    return meta

def assemble(clips, layers, output, voice=None, max_duration=7.3, zoom=1.0):
    """Clips reales de Veo, sin bucles ni fotos usadas como vídeo.
    layers: lista de (PNG, inicio, fin), previamente medida con overlay().
    """
    assert 1<=len(clips)<=2
    out=Path(output);out.parent.mkdir(exist_ok=True)
    args=['ffmpeg','-y','-v','error','-threads','2']
    for clip in clips: args+=['-i',str(clip)]
    for layer,start,end in layers: args+=['-loop','1','-i',str(layer)]
    if voice:
        args+=['-i',str(voice)]
    else:
        args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
    chains=[];total=0
    for i,clip in enumerate(clips):
        duration=min(max_duration,float(probe(clip)['format']['duration']))
        total+=duration
        sw,sh=2*round(W*zoom/2),2*round(H*zoom/2)
        chains.append(f'[{i}:v]trim=duration={duration},setpts=PTS-STARTPTS,scale={sw}:{sh}:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v{i}]')
    if len(clips)==2: chains.append('[v0][v1]concat=n=2:v=1:a=0[base]')
    else: chains.append('[v0]null[base]')
    previous='base'
    for j,(layer,start,end) in enumerate(layers):
        assert 0<=start<end<=total
        target=f'over{j}'
        chains.append(f"[{previous}][{len(clips)+j}:v]overlay=enable='between(t,{start},{end})':shortest=1[{target}]")
        previous=target
    audio_index=len(clips)+len(layers)
    if voice:
        assert float(probe(voice)['format']['duration'])<=total+0.05,'La voz no cabe sin cortarla'
        chains.append(f'[{audio_index}:a]aresample=48000,loudnorm=I=-14:TP=-2:LRA=11,apad[aout]')
        audio_map='[aout]'
    else:
        audio_map=f'{audio_index}:a'
    args+=['-filter_complex_threads','1','-filter_complex',';'.join(chains),'-map',f'[{previous}]','-map',audio_map,'-t',str(total),'-c:v','libx264','-threads','2','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-b:a','128k','-movflags','+faststart',str(out)]
    run(args);clean_metadata(out)
    meta=probe(out)
    video=next(s for s in meta['streams'] if s['codec_type']=='video')
    audio=next(s for s in meta['streams'] if s['codec_type']=='audio')
    assert (video['width'],video['height'])==(1080,1920)
    assert audio['sample_rate']=='48000'
    forbidden={'encoder','creation_time','comment','description','title'}
    assert not forbidden.intersection(meta['format'].get('tags',{}))
    return meta
