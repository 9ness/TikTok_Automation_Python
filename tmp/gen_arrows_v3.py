"""Regenera las 2 triples con MARCHA en su direccion (no solo opacidad):
- flecha_triple_blanca: 3 chevrons que avanzan a la derecha en cascada.
- flecha_abajo_triple_blanca: 3 flechas que avanzan hacia abajo en cascada.
Salida /tmp/genarrows3."""
from __future__ import annotations
import math, os, shutil, subprocess
from PIL import Image, ImageDraw, ImageFilter

OUT, TMP = "/tmp/genarrows3", "/tmp/_af3"
SS, OUT_SIZE, FRAMES, FPS, OUTLINE_R = 720, 360, 36, 30, 9
WHITE, BLACK = (245, 245, 245), (15, 15, 15)
os.makedirs(OUT, exist_ok=True)


def _shape_rgba(draw_fn, fill):
    mask = Image.new("L", (SS, SS), 0)
    draw_fn(ImageDraw.Draw(mask))
    grown = mask
    for _ in range(OUTLINE_R):
        grown = grown.filter(ImageFilter.MaxFilter(3))
    out = Image.composite(Image.new("RGBA", (SS, SS), (*BLACK, 255)),
                          Image.new("RGBA", (SS, SS), (0, 0, 0, 0)), grown)
    fillimg = Image.composite(Image.new("RGBA", (SS, SS), (*fill, 255)),
                              Image.new("RGBA", (SS, SS), (0, 0, 0, 0)), mask)
    return Image.alpha_composite(out, fillimg)


def _arrow_right(cx, cy, w, h):
    def fn(d):
        x0, x1 = cx - w / 2, cx + w / 2
        y0, y1 = cy - h / 2, cy + h / 2
        xm = x0 + 0.55 * w
        sh = 0.16 * h
        d.polygon([(x0, cy - sh), (xm, cy - sh), (xm, y0), (x1, cy),
                   (xm, y1), (xm, cy + sh), (x0, cy + sh)], fill=255)
    return fn


def _chevron(cx, cy, w, h):
    def fn(d):
        x0, x1 = cx - w / 2, cx + w / 2
        y0, y1 = cy - h / 2, cy + h / 2
        d.line([(x0, y0), (x1, cy), (x0, y1)], fill=255, width=int(0.22 * h), joint="curve")
    return fn


def _paste(canvas, img, dx=0.0, dy=0.0, alpha=1.0):
    if alpha < 1.0:
        img = img.copy()
        img.putalpha(img.split()[3].point(lambda v: int(v * alpha)))
    x = int((canvas.width - img.width) / 2 + dx)
    y = int((canvas.height - img.height) / 2 + dy)
    canvas.alpha_composite(img, (x, y))


def _render(name, frame_fn):
    if os.path.isdir(TMP):
        shutil.rmtree(TMP)
    os.makedirs(TMP, exist_ok=True)
    for i in range(FRAMES):
        c = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
        frame_fn(c, i / FRAMES)
        c.save(os.path.join(TMP, f"f_{i:03d}.png"))
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(FPS), "-i", os.path.join(TMP, "f_%03d.png"),
        "-vf", f"scale={OUT_SIZE}:{OUT_SIZE}:flags=lanczos",
        "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
        "-an", os.path.join(OUT, f"{name}.mov"),
    ], check=True)


AMP = 0.06 * SS

def _wave(p, k):
    """Cascada: empuje 0→AMP→0 desfasado por chevron/flecha."""
    ph = (p - k / 3.0) % 1.0
    return AMP * (0.5 - 0.5 * math.cos(2 * math.pi * ph))

def _crop(img):
    return img.crop(img.getbbox())


def _row(name, sprite, vertical):
    """3 sprites en fila que LLENAN el frame (recorta al contenido y escala
    para que el grupo ocupe ~88% del ancho). `vertical`=motion hacia abajo."""
    sp = _crop(sprite)
    fill = 0.88 * SS
    gap = int(0.02 * SS)
    ew = int((fill - 2 * gap) / 3)
    eh = int(ew * sp.height / sp.width)
    # límite vertical (deja sitio al wave) para que no se salga
    maxh = int(0.80 * SS)
    if eh > maxh:
        eh = maxh; ew = int(eh * sp.width / sp.height)
    sp = sp.resize((ew, eh), Image.LANCZOS)
    step = ew + gap

    def frame_fn(c, p):
        for k in range(3):
            d = _wave(p, k)
            cx = SS / 2 + (k - 1) * step + (0 if vertical else d)
            cy = SS / 2 + (d if vertical else 0)
            c.alpha_composite(sp, (int(cx - ew / 2), int(cy - eh / 2)))
    _render(name, frame_fn)


# Triple derecha (chevrons marchando a la derecha) y triple abajo (flechas abajo)
chev = _shape_rgba(_chevron(SS / 2, SS / 2, int(0.30 * SS), int(0.64 * SS)), WHITE)
_row("flecha_triple_blanca", chev, vertical=False)

arrow = _shape_rgba(_arrow_right(SS / 2, SS / 2, int(0.46 * SS), int(0.30 * SS)), WHITE)
down = arrow.rotate(-90, expand=True)
_row("flecha_abajo_triple_blanca", down, vertical=True)

print("DONE", sorted(os.listdir(OUT)))
