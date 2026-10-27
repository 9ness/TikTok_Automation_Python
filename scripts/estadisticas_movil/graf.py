# lee una gráfica de Tendencias (captura completa 1440x3168) → valor por día
import subprocess, re, sys
import os as _os
W = _os.environ.get("EST_DIR", "/tmp/est"); _os.makedirs(W, exist_ok=True)
import numpy as np
from PIL import Image
Y0, Y1, XA, XB = 2150, 2960, 180, 1420
def leer1(pngs, ndias):
    ims = [np.asarray(Image.open(p).convert("RGB")).astype(int) for p in pngs]
    im = ims[0]
    R, G, B = (np.stack([i[..., c] for i in ims]) for c in range(3))
    roja = ((R > 200) & (G < 140) & (B < 170)).any(0)
    roja[:Y0] = False; roja[Y1:] = False; roja[:, :128] = False; roja[:, XB:] = False
    # rejilla: filas grises claras
    gris = (np.abs(im[..., 0] - 246) < 4) & (np.abs(im[..., 2] - 249) < 4) & (im[..., 1] < 252)
    filas = [y for y in range(Y0, Y1) if gris[y, XA:XB].sum() > 150]
    eje = [y for y in range(Y0, Y1) if (np.abs(im[y, XA:XB] - [110, 116, 142]).sum(1) < 40).sum() > 300]
    filas_u = []
    for y in filas:
        if not filas_u or y - filas_u[-1] > 5: filas_u.append(y)
    lineas = filas_u + [eje[0]]
    pares = []
    for y in lineas:
        g = im[y - 35:y + 35, 10:135].astype(int).sum(2) / 3
        bw = np.where(g < 200, 0, 255).astype("uint8")
        bw = np.pad(bw, 30, constant_values=255)
        Image.fromarray(bw).resize((bw.shape[1] * 2, bw.shape[0] * 2)).save(f"{W}/ax.png")
        t = subprocess.run(["tesseract", f"{W}/ax.png", "-", "--psm", "7", "-c", "tessedit_char_whitelist=0123456789,.K€"],
                           capture_output=True, text=True).stdout.strip().replace("€", "")
        m = re.fullmatch(r"(\d+(?:[.,]\d+)?)(K?)", t)
        if m: pares.append((y, float(m.group(1).replace(",", ".")) * (1000 if m.group(2) else 1)))
    # rejilla equiespaciada (el eje no siempre es 0): progresión que case con más etiquetas
    paso_px = np.median(np.diff(sorted(filas_u))) if len(filas_u) > 1 else 0
    if not paso_px or not pares: pares = []
    eje_y = lineas[-1]
    k_de = {y: round((eje_y - y) / paso_px) for y, _ in pares} if pares else {}
    mejor = None
    for i, (ya, va) in enumerate(pares):
        for yb, vb in pares[i + 1:]:
            if k_de[ya] == k_de[yb]: continue
            paso = (va - vb) / (k_de[ya] - k_de[yb]); base = va - paso * k_de[ya]
            if paso <= 0: continue
            n = sum(abs(base + paso * k_de[y] - v) <= max(0.02 * paso, 0.01) for y, v in pares)
            if not mejor or n > mejor[0]: mejor = (n, paso, base)
    if not mejor: mejor = (0, 1, 0)
    _, paso, base = mejor
    a, b = (-paso / paso_px, base + paso * eje_y / paso_px) if paso_px else (-1, 0)
    cols = np.where(roja.any(0))[0]
    x0, x1 = cols.min() + 4, cols.max() - 4
    xs = [int(round(x0 + d * (x1 - x0) / max(ndias - 1, 1))) for d in range(ndias)]
    col = [np.where(roja[:, x - 1:x + 2].any(1))[0] for x in xs]
    grosor = min(len(c) for c in col if len(c)) or 1
    med = [c.mean() if len(c) else None for c in col]
    out = []; ypix = []
    for d, c in enumerate(col):
        if not len(c): out.append(None); ypix.append((xs[d], None, False)); continue
        vec = [med[k] for k in (d - 1, d + 1) if 0 <= k < ndias and med[k] is not None]
        n = np.mean(vec) if vec else med[d]
        y = c.min() + grosor / 2 if med[d] < n - 3 else c.max() - grosor / 2 if med[d] > n + 3 else med[d]
        out.append(round(max(a * y + b, 0), 2)); ypix.append((xs[d], y, all(abs(med[k] - med[d]) <= 3 for k in (d - 1, d + 1) if 0 <= k < ndias and med[k] is not None)))
    return out, pares, ypix
def leer(pngs, ndias, taps=(400, 1100)):
    r = [leer1([p], ndias) for p in pngs]
    out, ypix = [], []
    for d in range(ndias):
        x = r[0][2][d][0]
        k = max(range(len(pngs)), key=lambda i: abs(taps[i] - x))
        out.append(r[k][0][d]); ypix.append(r[k][2][d])
    return out, r[0][1], ypix
if __name__ == "__main__":
    v, p, _ = leer(sys.argv[2:], int(sys.argv[1])); print(p); print(v)
