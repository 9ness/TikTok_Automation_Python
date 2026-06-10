"""Genera flechas CTA animadas (alpha limpio, trazo uniforme) en ProRes 4444.

Estilos: avanza (nudge), pulse (late), bob (rebote), triple (3 chevrons cascada).
Colores: blanca, roja. Salida en /tmp/genarrows/*.mov.
"""
from __future__ import annotations
import math, os, shutil, subprocess
from PIL import Image, ImageDraw, ImageFilter

SS = 720            # canvas supersampleado
OUT_SIZE = 360      # tamaño final
FRAMES = 36
FPS = 30
OUTLINE_R = 9       # px de trazo @720 (~4.5 @360)
OUT_DIR = "/tmp/genarrows"
TMP = "/tmp/_arrowframes"

WHITE = (245, 245, 245)
RED = (230, 40, 40)
BLACK = (15, 15, 15)
COLORS = {"blanca": WHITE, "roja": RED}


def _shape_rgba(draw_fn, fill) -> Image.Image:
    """Construye la forma con trazo NEGRO uniforme (dilatacion del alpha)."""
    mask = Image.new("L", (SS, SS), 0)
    draw_fn(ImageDraw.Draw(mask))
    grown = mask
    for _ in range(OUTLINE_R):
        grown = grown.filter(ImageFilter.MaxFilter(3))
    out = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
    blk = Image.new("RGBA", (SS, SS), (*BLACK, 255))
    out = Image.composite(blk, out, grown)
    fc = Image.new("RGBA", (SS, SS), (*fill, 255))
    fillimg = Image.composite(fc, Image.new("RGBA", (SS, SS), (0, 0, 0, 0)), mask)
    return Image.alpha_composite(out, fillimg)


def _arrow_draw(cx, cy, w, h):
    def fn(d):
        x0, x1 = cx - w / 2, cx + w / 2
        y0, y1 = cy - h / 2, cy + h / 2
        xm = x0 + 0.55 * w
        sh = 0.16 * h
        d.polygon([
            (x0, cy - sh), (xm, cy - sh), (xm, y0), (x1, cy),
            (xm, y1), (xm, cy + sh), (x0, cy + sh),
        ], fill=255)
    return fn


def _chevron_draw(cx, cy, w, h):
    def fn(d):
        x0, x1 = cx - w / 2, cx + w / 2
        y0, y1 = cy - h / 2, cy + h / 2
        d.line([(x0, y0), (x1, cy), (x0, y1)], fill=255,
               width=int(0.22 * h), joint="curve")
    return fn


def _paste_centered(canvas, img, dx=0.0, dy=0.0, scale=1.0, alpha=1.0):
    if scale != 1.0:
        nw = max(2, int(img.width * scale))
        nh = max(2, int(img.height * scale))
        img = img.resize((nw, nh), Image.LANCZOS)
    if alpha < 1.0:
        a = img.split()[3].point(lambda v: int(v * alpha))
        img = img.copy(); img.putalpha(a)
    x = int((canvas.width - img.width) / 2 + dx)
    y = int((canvas.height - img.height) / 2 + dy)
    canvas.alpha_composite(img, (x, y))


def _encode(name):
    out = os.path.join(OUT_DIR, f"{name}.mov")
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(FPS), "-i", os.path.join(TMP, "f_%03d.png"),
        "-vf", f"scale={OUT_SIZE}:{OUT_SIZE}:flags=lanczos",
        "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
        "-an", out,
    ], check=True)
    return out


def _render(name, frame_fn):
    if os.path.isdir(TMP):
        shutil.rmtree(TMP)
    os.makedirs(TMP, exist_ok=True)
    for i in range(FRAMES):
        p = i / FRAMES  # 0..1 (periodico → loop perfecto)
        canvas = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
        frame_fn(canvas, p)
        canvas.save(os.path.join(TMP, f"f_{i:03d}.png"))
    _encode(name)


os.makedirs(OUT_DIR, exist_ok=True)
AW, AH = int(0.52 * SS), int(0.40 * SS)   # arrow size
amp = 0.07 * SS

for cname, col in COLORS.items():
    arrow = _shape_rgba(_arrow_draw(SS / 2, SS / 2, AW, AH), col)

    # avanza: empuje hacia delante (derecha) y vuelta
    def avanza(canvas, p, _a=arrow):
        dx = amp * (0.5 - 0.5 * math.cos(2 * math.pi * p))
        _paste_centered(canvas, _a, dx=dx)
    _render(f"flecha_avanza_{cname}", avanza)

    # pulse: late (escala)
    def pulse(canvas, p, _a=arrow):
        s = 1.0 + 0.12 * math.sin(2 * math.pi * p)
        _paste_centered(canvas, _a, scale=s)
    _render(f"flecha_pulse_{cname}", pulse)

    # bob: sube y baja
    def bob(canvas, p, _a=arrow):
        dy = amp * math.sin(2 * math.pi * p)
        _paste_centered(canvas, _a, dy=dy)
    _render(f"flecha_bob_{cname}", bob)

    # triple: 3 chevrons marchando (cascada de opacidad), apuntan derecha
    chev = _shape_rgba(_chevron_draw(SS / 2, SS / 2, int(0.20 * SS), int(0.42 * SS)), col)
    gap = int(0.19 * SS)

    def triple(canvas, p, _c=chev, _gap=gap):
        for i in range(3):
            ph = (p - i / 3.0) % 1.0
            a = 0.3 + 0.7 * (0.5 + 0.5 * math.cos(2 * math.pi * ph))
            _paste_centered(canvas, _c, dx=(i - 1) * _gap, alpha=a)
    _render(f"flecha_triple_{cname}", triple)

print("DONE", sorted(os.listdir(OUT_DIR)))
