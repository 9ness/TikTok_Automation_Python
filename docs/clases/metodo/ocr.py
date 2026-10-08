# OCR de las franjas: salta las vacías, invierte (texto negro sobre blanco) y paraleliza
import glob, os, subprocess
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from PIL import Image, ImageOps
def uno(f):
    n = os.path.basename(f)[:-4]; o = f'ocr2/{n}.txt'
    if os.path.exists(o): return
    im = Image.open(f).convert('L').crop((140, 0, 1080, 430))  # fuera el lápiz
    if (np.asarray(im) > 180).sum() < 400: open(o, 'w').close(); return
    tmp = f'/tmp/ocr_{n}.png'; ImageOps.invert(im).save(tmp)
    try:
        r = subprocess.run(['tesseract', tmp, '-', '-l', 'spa', '--psm', '6'], capture_output=True, text=True, timeout=20, env={**os.environ, 'OMP_THREAD_LIMIT': '1'})
        open(o, 'w').write(r.stdout)
    except subprocess.TimeoutExpired: open(o, 'w').close()
    os.unlink(tmp)
if __name__ == '__main__':
    with ProcessPoolExecutor(4) as ex: list(ex.map(uno, sorted(glob.glob('subs/*.png')), chunksize=8))
