"""Flechas 3D hacia ABAJO roja y amarilla: cara con degradado + extrusion
(profundidad) + contorno. Animacion: leve empuje hacia abajo.
Salida /tmp/gen3d/flecha_3d_{roja,amarilla}.mov."""
from __future__ import annotations
import math, os, shutil, subprocess
from PIL import Image, ImageDraw, ImageFilter, ImageChops

OUT, TMP = "/tmp/gen3d", "/tmp/_af3d"
SS, OUT_SIZE, FRAMES, FPS, OUTLINE_R, DEPTH = 720, 360, 36, 30, 8, 20
os.makedirs(OUT, exist_ok=True)
RED, YELLOW = (228, 42, 42), (250, 205, 45)


def _down_arrow_mask(w, h):
    m = Image.new("L", (SS, SS), 0)
    d = ImageDraw.Draw(m)
    cx = cy = SS / 2
    x0, x1 = cx - w / 2, cx + w / 2
    y0, y1 = cy - h / 2, cy + h / 2
    ym = y1 - 0.55 * h           # la cabeza ocupa el 55% inferior
    sw = 0.16 * w                # medio ancho del asta
    d.polygon([(cx - sw, y0), (cx + sw, y0), (cx + sw, ym), (x1, ym),
               (cx, y1), (x0, ym), (cx - sw, ym)], fill=255)
    return m


def _shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def _lighten(c, a):
    return tuple(max(0, min(255, int(v + a))) for v in c)


def _vgrad(top, bot):
    g = Image.new("RGB", (1, SS))
    px = g.load()
    for y in range(SS):
        t = y / (SS - 1)
        px[0, y] = tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3))
    return g.resize((SS, SS))


def _sprite_3d(base):
    mask = _down_arrow_mask(int(0.42 * SS), int(0.58 * SS))
    ext = Image.new("L", (SS, SS), 0)
    for t in range(1, DEPTH + 1):
        ext = ImageChops.lighter(ext, ImageChops.offset(mask, t, t))
    total = ImageChops.lighter(mask, ext)
    grown = total
    for _ in range(OUTLINE_R):
        grown = grown.filter(ImageFilter.MaxFilter(3))
    transp = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
    out = Image.composite(Image.new("RGBA", (SS, SS), (15, 15, 15, 255)), transp, grown)
    dark = Image.composite(Image.new("RGBA", (SS, SS), (*_shade(base, 0.5), 255)), transp, ext)
    grad = _vgrad(_lighten(base, 75), _shade(base, 0.82)).convert("RGBA")
    face = Image.composite(grad, transp.copy(), mask)
    sprite = Image.alpha_composite(out, dark)
    sprite = Image.alpha_composite(sprite, face)
    return sprite.crop(sprite.getbbox())


def _render(name, sprite):
    if os.path.isdir(TMP):
        shutil.rmtree(TMP)
    os.makedirs(TMP, exist_ok=True)
    eh = int(0.80 * SS)
    ew = int(eh * sprite.width / sprite.height)
    sp = sprite.resize((ew, eh), Image.LANCZOS)
    amp = 0.05 * SS
    for i in range(FRAMES):
        p = i / FRAMES
        c = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
        dy = amp * (0.5 - 0.5 * math.cos(2 * math.pi * p))  # empuje hacia abajo
        c.alpha_composite(sp, (int((SS - ew) / 2), int((SS - eh) / 2 + dy)))
        c.save(os.path.join(TMP, f"f_{i:03d}.png"))
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(FPS), "-i", os.path.join(TMP, "f_%03d.png"),
        "-vf", f"scale={OUT_SIZE}:{OUT_SIZE}:flags=lanczos",
        "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
        "-an", os.path.join(OUT, f"{name}.mov"),
    ], check=True)


_render("flecha_3d_roja", _sprite_3d(RED))
_render("flecha_3d_amarilla", _sprite_3d(YELLOW))
print("DONE", sorted(os.listdir(OUT)))
