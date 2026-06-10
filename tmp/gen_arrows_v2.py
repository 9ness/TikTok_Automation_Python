"""Genera: flecha izquierda roja/amarilla (espejo de las existentes) y
triple-abajo blanca (3 flechas hacia abajo, cascada). Salida /tmp/genarrows2."""
from __future__ import annotations
import math, os, shutil, subprocess
from PIL import Image, ImageDraw, ImageFilter

SRC = "/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_EDITOR/Assets/flechas"
OUT = "/tmp/genarrows2"
TMP = "/tmp/_arrowframes2"
SS, OUT_SIZE, FRAMES, FPS, OUTLINE_R = 720, 360, 36, 30, 9
WHITE, BLACK = (245, 245, 245), (15, 15, 15)
os.makedirs(OUT, exist_ok=True)

# 1) Flechas de lado = espejo horizontal de las existentes (conserva trazo+anim)
def hflip(src_name, out_name):
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", os.path.join(SRC, src_name), "-vf", "hflip",
        "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
        "-an", os.path.join(OUT, out_name),
    ], check=True)

hflip("flecha_roja.mov", "flecha_izq_roja.mov")
hflip("flecha_amarilla.mov", "flecha_izq_amarilla.mov")

# 2) Triple-abajo blanca (3 flechas hacia abajo, cascada de opacidad)
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

# flecha hacia ABAJO = flecha derecha rotada 90º CW
arrow = _shape_rgba(_arrow_right(SS / 2, SS / 2, int(0.46 * SS), int(0.30 * SS)), WHITE)
down = arrow.rotate(-90, expand=True)
# reducir para que quepan 3
dw = int(0.26 * SS)
down = down.resize((dw, int(dw * down.height / down.width)), Image.LANCZOS)
gap = int(0.30 * SS)

if os.path.isdir(TMP):
    shutil.rmtree(TMP)
os.makedirs(TMP, exist_ok=True)
for i in range(FRAMES):
    p = i / FRAMES
    canvas = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
    for k in range(3):
        ph = (p - k / 3.0) % 1.0
        a = 0.35 + 0.65 * (0.5 + 0.5 * math.cos(2 * math.pi * ph))
        dy = 0.04 * SS * math.sin(2 * math.pi * ph)  # leve goteo
        img = down.copy()
        img.putalpha(img.split()[3].point(lambda v: int(v * a)))
        x = int(SS / 2 + (k - 1) * gap - img.width / 2)
        y = int(SS / 2 - img.height / 2 + dy)
        canvas.alpha_composite(img, (x, y))
    canvas.save(os.path.join(TMP, f"f_{i:03d}.png"))

subprocess.run([
    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
    "-framerate", str(FPS), "-i", os.path.join(TMP, "f_%03d.png"),
    "-vf", f"scale={OUT_SIZE}:{OUT_SIZE}:flags=lanczos",
    "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
    "-an", os.path.join(OUT, "flecha_abajo_triple_blanca.mov"),
], check=True)

print("DONE", sorted(os.listdir(OUT)))
