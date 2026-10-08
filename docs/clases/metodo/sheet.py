# Hoja de fotogramas de pantalla (de los deduplicados) entre dos segundos
import sys
from PIL import Image, ImageDraw
a, b, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
fs = [l for l in open('scr_keep.txt').read().split() if a <= int(l[4:9]) <= b]
step = max(1, len(fs)//int(sys.argv[4] if len(sys.argv) > 4 else 6)); fs = fs[::step][:8]
ims = [Image.open(f) for f in fs]; w, h = 1080, 700
s = Image.new('RGB', (w*2, h*((len(ims)+1)//2)))
for i, (f, im) in enumerate(zip(fs, ims)):
    s.paste(im, ((i%2)*w, (i//2)*h)); t = int(f[4:9])
    ImageDraw.Draw(s).text(((i%2)*w+10, (i//2)*h+10), f'{t//60}:{t%60:02d}', fill='yellow')
s.save(out); print(len(fs), [f[4:9] for f in fs])
