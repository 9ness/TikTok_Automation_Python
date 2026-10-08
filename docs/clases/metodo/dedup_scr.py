# Se queda con los fotogramas de pantalla que cambian de verdad
import glob, numpy as np
from PIL import Image
prev=None; keep=[]
for f in sorted(glob.glob('scr/*.jpg')):
    a=np.asarray(Image.open(f).convert('L').resize((96,62)),dtype=np.int16)
    if prev is None or np.abs(a-prev).mean()>6:
        keep.append(f); prev=a
open('scr_keep.txt','w').write('\n'.join(keep))
print(len(keep))
