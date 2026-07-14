"""Deja un vídeo generado (Flow/Kling) LISTO para subir a TikTok Shop, con
edición de CALIDAD (no cutre):

1. **Zoom inteligente**: detecta en qué esquina está la marca de agua (analiza
   frames: región estática + con bordes = logo) y hace un recorte DIRIGIDO con
   el mínimo zoom para sacarla de cuadro. Fallback: zoom central manual.
2. **Textos en zona segura de TikTok** (no tapan el centro del vídeo ni los
   iconos laterales): gancho arriba, CTA abajo, Montserrat ExtraBold blanco con
   borde negro grueso.
3. **Flecha CTA** animada (asset del Editor) apuntando al carrito (abajo-izq).

Sin coste (MoviePy/ffmpeg local). Emojis se quitan del texto quemado.
"""

from __future__ import annotations

import math
import os
import re
from typing import Callable

import numpy as np
from moviepy.editor import CompositeVideoClip, ImageClip, VideoFileClip
from moviepy.video.fx.all import crop, resize
from PIL import Image, ImageDraw, ImageFont

from src.font_resolver import _bundled_fonts_dir

_noop: Callable[[str], None] = lambda _m: None

TARGET_W, TARGET_H = 1080, 1920
# Zonas seguras TikTok (de subtitles.py): evitar iconos laterales + UI inferior.
SAFE_Y = (0.15, 0.75)
SAFE_X = (0.05, 0.78)

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE0F]+"
)


def _font_path(name: str = "Montserrat-ExtraBold.ttf") -> str:
    p = os.path.join(_bundled_fonts_dir(), name)
    return p if os.path.exists(p) else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _clean(text: str) -> str:
    return _EMOJI_RE.sub("", text or "").strip()


# ── Detección de la marca de agua ────────────────────────────────────────
def _edge_energy(a: np.ndarray) -> float:
    g = a.mean(axis=2) if a.ndim == 3 else a
    gx = np.abs(np.diff(g, axis=1)).mean()
    gy = np.abs(np.diff(g, axis=0)).mean()
    return float(gx + gy)


def detect_watermark_corner(clip, log=_noop):
    """Devuelve ('bl'|'br'|'tl'|'tr', frac_w, frac_h) de la esquina con marca de
    agua, o None. Heurística: esquina estática (poca varianza temporal) pero con
    bordes (logo/texto) = marca de agua."""
    try:
        dur = clip.duration or 2.0
        ts = [dur * f for f in (0.1, 0.3, 0.5, 0.7, 0.9)]
        frames = [clip.get_frame(t).astype(np.float32) for t in ts]
        H, W = frames[0].shape[:2]
        cw, ch = int(W * 0.24), int(H * 0.14)
        regions = {
            "tl": (slice(0, ch), slice(0, cw)),
            "tr": (slice(0, ch), slice(W - cw, W)),
            "bl": (slice(H - ch, H), slice(0, cw)),
            "br": (slice(H - ch, H), slice(W - cw, W)),
        }
        best, best_score = None, 0.0
        for name, (ys, xs) in regions.items():
            stack = np.stack([f[ys, xs] for f in frames])   # T,h,w,3
            temporal_std = stack.std(axis=0).mean()          # bajo = estático
            mean_region = stack.mean(axis=0)
            edges = _edge_energy(mean_region)                # alto = tiene logo
            score = edges / (1.0 + temporal_std)             # estático + edgy
            if score > best_score:
                best, best_score = name, score
        # Umbral: la esquina candidata debe destacar sobre el ruido base.
        if best and best_score > 3.5:
            log(f"  🔎 Marca de agua detectada en esquina '{best}'")
            return best, 0.22, 0.13
        log("  🔎 Sin marca clara detectada — zoom central")
        return None
    except Exception:
        return None


def _crop_params(corner, base_w, base_h, manual_zoom):
    """Params de recorte dirigido para quitar la esquina `corner`. Devuelve
    (crop_w, crop_h, x_center, y_center) sobre un frame ya escalado a
    (base_w, base_h)*zoom."""
    if corner is None:
        z = manual_zoom
        zw, zh = base_w * z, base_h * z
        return zw, zh, zw / 2, zh / 2
    name, fw, fh = corner
    # Zoom mínimo para poder desplazar el recorte y tapar la esquina.
    z = max(manual_zoom, 1.0 + 2 * max(fw, fh) * 0.5)
    z = min(z, 1.4)
    zw, zh = TARGET_W * z, TARGET_H * z
    dx = (zw - TARGET_W) / 2      # margen recortable a cada lado
    dy = (zh - TARGET_H) / 2
    # Desplazar el centro del recorte LEJOS de la esquina con marca.
    x_center = zw / 2 + (dx if "l" in name else -dx)
    y_center = zh / 2 + (dy if "t" in name else -dy)
    return zw, zh, x_center, y_center


# ── Texto estilo TikTok ──────────────────────────────────────────────────
def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# Estilos de texto para dar VARIEDAD entre las 3 versiones de un producto
# (se rota por índice de concepto). fuente + color relleno + color borde.
_TEXT_STYLES = [
    {"font": "Montserrat-ExtraBold.ttf", "fill": (255, 255, 255), "stroke": (0, 0, 0)},
    {"font": "anton.ttf", "fill": (255, 221, 0), "stroke": (0, 0, 0)},          # amarillo viral
    {"font": "LuckiestGuy-Regular.ttf", "fill": (255, 255, 255), "stroke": (18, 18, 60)},
    {"font": "Rubik-Bold.ttf", "fill": (255, 255, 255), "stroke": (214, 20, 90)},  # rosa
]


def _style(idx: int) -> dict:
    return _TEXT_STYLES[idx % len(_TEXT_STYLES)]


# Modo de texto por versión (rota): "single" = 1 texto fijo (valor directo,
# estilo chica) · "sequence" = gancho SIN flecha → cambia a CTA + flecha
# (historia/POV, estilo perro). Alternar entre versiones para testear.
_TEXT_MODES = ["single", "sequence", "single", "sequence"]


def _text_mode(idx: int) -> str:
    return _TEXT_MODES[idx % len(_TEXT_MODES)]


# ── Emojis en color (Noto Color Emoji, CBDT a 109px → escalado) ──────────
_EMOJI_FONT_CACHE: dict = {}


def _emoji_font():
    if "f" not in _EMOJI_FONT_CACHE:
        try:
            _EMOJI_FONT_CACHE["f"] = ImageFont.truetype(
                _font_path("NotoColorEmoji.ttf"), 109)
        except Exception:
            _EMOJI_FONT_CACHE["f"] = None
    return _EMOJI_FONT_CACHE["f"]


def _split_runs(s: str):
    """Parte la línea en tramos ('text'|'emoji', substring)."""
    runs, cur, kind = [], "", None
    for ch in s:
        k = "emoji" if _EMOJI_RE.match(ch) else "text"
        if k == kind:
            cur += ch
        else:
            if cur:
                runs.append((kind, cur))
            cur, kind = ch, k
    if cur:
        runs.append((kind, cur))
    return runs


def _emoji_run_img(run: str, size: int):
    ef = _emoji_font()
    if ef is None:
        return None
    try:
        canvas = Image.new("RGBA", (180 * (len(run) + 1), 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(canvas)
        d.text((4, 4), run, font=ef, embedded_color=True)
        bbox = canvas.getbbox()
        if not bbox:
            return None
        img = canvas.crop(bbox)
        w, h = img.size
        return img.resize((max(1, int(w * size / h)), size), Image.LANCZOS)
    except Exception:
        return None


def _seg_width(runs, font, d0, emoji_size, gap):
    total = 0.0
    for k, t in runs:
        if k == "emoji":
            im = _emoji_run_img(t, emoji_size)
            total += (im.width + gap) if im else 0
        else:
            total += d0.textlength(t, font=font)
    return total


def _render_text_png(text: str, *, font_size: int, max_w: int,
                     style: dict | None = None, use_emoji: bool = True):
    if not use_emoji:
        text = _clean(text)
    text = (text or "").strip()
    if not text:
        return None
    st = style or _TEXT_STYLES[0]
    font = ImageFont.truetype(_font_path(st["font"]), font_size)
    stroke = max(3, int(font_size * 0.15))
    emoji_size = int(font_size * 0.92)
    gap = int(font_size * 0.06)
    d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))

    # Wrap por palabras midiendo texto + emojis.
    def w_of(s):
        return _seg_width(_split_runs(s), font, d0, emoji_size, gap)

    words, lines, cur = text.split(), [], ""
    for word in words:
        test = (cur + " " + word).strip()
        if w_of(test) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)

    line_h = int(font_size * 1.24)
    pad = stroke + 12
    line_ws = [w_of(ln) for ln in lines]
    W = int(max(line_ws, default=0)) + pad * 2
    H = line_h * len(lines) + pad * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        x = (W - line_ws[i]) / 2
        y = pad + i * line_h
        for k, t in _split_runs(ln):
            if k == "emoji":
                im = _emoji_run_img(t, emoji_size)
                if im is not None:
                    ey = int(y + (font_size - emoji_size) / 2 + font_size * 0.10)
                    img.paste(im, (int(x), ey), im)
                    x += im.width + gap
            else:
                d.text((x, y), t, font=font, fill=tuple(st["fill"]),
                       stroke_width=stroke, stroke_fill=tuple(st["stroke"]))
                x += d0.textlength(t, font=font)
    return img


def _text_clip(text, *, font_size, y_center_pct, max_w_pct, duration, x_center_pct=0.5,
               style: dict | None = None, use_emoji: bool = True):
    png = _render_text_png(text, font_size=font_size, max_w=int(TARGET_W * max_w_pct),
                           style=style, use_emoji=use_emoji)
    if png is None:
        return None
    x = int(TARGET_W * x_center_pct - png.width / 2)
    y = int(TARGET_H * y_center_pct - png.height / 2)
    return ImageClip(np.array(png)).set_duration(duration).set_position((x, y))


# ── Flecha CTA (dibujada con PIL, color adaptado — sin depender de .mov) ──
# Nota: leer las flechas .mov del Editor desde el drive de red fallaba de forma
# intermitente en MoviePy ("failed to read first frame") y tumbaba el render.
# La dibujamos con PIL: siempre funciona, sin I/O del drive lento.
# La flecha va SOLA en la zona media-izquierda apuntando al carrito naranja de
# TikTok Shop (como los vídeos que venden). ROJA con borde blanco. Coordenadas
# = CENTRO del elemento. 3 tipos para variar entre versiones.
_ARROW_CX, _ARROW_CY = 0.22, 0.60
_ARROW_RED = (228, 30, 30, 255)
_ARROW_OUTLINE = (255, 255, 255, 255)
_ARROW_KINDS = ["down", "double", "fat"]


def _arrow_kind(idx: int) -> str:
    return _ARROW_KINDS[idx % len(_ARROW_KINDS)]


def _draw_arrow_png(kind: str, w: int, fill=_ARROW_RED, outline=_ARROW_OUTLINE):
    """Flecha roja apuntando abajo (al carrito). kind: down|double|fat."""
    h = int(w * 1.4)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = w / 2
    ow = max(4, int(w * 0.09))

    def _solid_arrow(sw_f, hw_f, top_f, mid_f, tip_f):
        sw, hw = w * sw_f, w * hw_f
        top, mid, tip = h * top_f, h * mid_f, h * tip_f
        pts = [
            (cx - sw / 2, top), (cx + sw / 2, top),
            (cx + sw / 2, mid), (cx + hw / 2, mid),
            (cx, tip),
            (cx - hw / 2, mid), (cx - sw / 2, mid),
        ]
        d.polygon(pts, fill=fill)
        d.line(pts + [pts[0]], fill=outline, width=ow, joint="curve")

    if kind == "fat":
        _solid_arrow(0.46, 0.98, 0.16, 0.50, 0.92)
    elif kind == "double":
        hw = w * 0.80
        lw = max(7, int(w * 0.16))
        for off in (0.0, 0.40):
            y1, y2 = h * (0.06 + off), h * (0.44 + off)
            for col, wd in ((outline, lw + ow * 2), (fill, lw)):
                d.line([(cx - hw / 2, y1), (cx, y2)], fill=col, width=wd, joint="curve")
                d.line([(cx + hw / 2, y1), (cx, y2)], fill=col, width=wd, joint="curve")
    else:  # down
        _solid_arrow(0.32, 0.82, 0.05, 0.52, 0.95)
    return img


def _arrow_clip(core, duration, kind="down", log=_noop):
    try:
        png = _draw_arrow_png(kind, int(TARGET_W * 0.13))
        w, h = png.size
        x0 = int(TARGET_W * _ARROW_CX - w / 2)
        y0 = int(TARGET_H * _ARROW_CY - h / 2)
        amp = int(TARGET_H * 0.012)   # bob suave
        clip = ImageClip(np.array(png)).set_duration(duration)
        clip = clip.set_position(
            lambda t: (x0, y0 + int(amp * math.sin(t * 2 * math.pi * 1.2)))
        )
        log(f"  ➘ Flecha CTA roja ({kind}) apuntando al carrito")
        return clip
    except Exception:
        return None


def process_ready_video(
    input_path: str,
    output_path: str,
    *,
    hook_text: str = "",
    cta_text: str = "",
    zoom: float = 1.12,
    with_arrow: bool = True,
    style: int = 0,
    log: Callable[[str], None] = _noop,
) -> str:
    zoom = max(1.0, min(1.4, float(zoom)))
    st = _style(int(style))
    log(f"🎬 Procesando vídeo → 1080x1920… (estilo {int(style) % len(_TEXT_STYLES)}: {st['font']})")
    base = VideoFileClip(input_path)

    # Cover-fit a 9:16 sin zoom aún.
    fitted = base.resize(height=TARGET_H) if base.w / base.h > TARGET_W / TARGET_H \
        else base.resize(width=TARGET_W)
    fitted = crop(fitted, x_center=fitted.w / 2, y_center=fitted.h / 2,
                  width=TARGET_W, height=TARGET_H)

    # Zoom inteligente: detectar esquina de la marca y recortar dirigido.
    # Si no se detecta nada, por defecto quitamos la esquina INFERIOR-DERECHA
    # (Flow/Veo pone ahí su destello ✦).
    corner = detect_watermark_corner(fitted, log=log)
    if corner is None:
        corner = ("br", 0.22, 0.14)
        log("  🔎 Sin marca clara → recorto esquina inferior-derecha (Flow)")
    zw, zh, xc, yc = _crop_params(corner, TARGET_W, TARGET_H, zoom)
    zoomed = resize(fitted, newsize=(int(zw), int(zh)))
    core = crop(zoomed, x_center=xc, y_center=yc, width=TARGET_W, height=TARGET_H)

    layers = [core]
    # Layout tipo "vídeo que vende": texto arriba + flecha roja sola al carrito.
    # single = 1 texto fijo + flecha; sequence = gancho SIN flecha → CTA + flecha.
    dur = core.duration
    akind = _arrow_kind(int(style))
    mode = _text_mode(int(style))
    # Variedad: la versión 0 va LIMPIA (sin emoji); las demás con emoji.
    use_emoji = (int(style) % len(_TEXT_STYLES)) != 0
    if mode == "sequence" and (cta_text or "").strip():
        split = dur * 0.45
        hk = _text_clip(hook_text, font_size=62, y_center_pct=0.26,
                        max_w_pct=0.86, duration=split, style=st, use_emoji=use_emoji)
        if hk is not None:
            layers.append(hk)
        ct = _text_clip(cta_text, font_size=58, y_center_pct=0.26,
                        max_w_pct=0.86, duration=dur - split, style=st, use_emoji=use_emoji)
        if ct is not None:
            layers.append(ct.set_start(split))
        if with_arrow:
            ar = _arrow_clip(core, dur - split, kind=akind, log=log)
            if ar is not None:
                layers.append(ar.set_start(split))
        log(f"  📌 Secuencia: gancho → CTA + flecha (emoji={use_emoji})")
    else:
        hk = _text_clip(hook_text, font_size=62, y_center_pct=0.26,
                        max_w_pct=0.86, duration=dur, style=st, use_emoji=use_emoji)
        if hk is not None:
            layers.append(hk)
        if with_arrow:
            ar = _arrow_clip(core, dur, kind=akind, log=log)
            if ar is not None:
                layers.append(ar)
        log(f"  📌 Texto único + flecha (emoji={use_emoji})")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    def _render(lys):
        comp = CompositeVideoClip(lys, size=(TARGET_W, TARGET_H))
        if base.audio is not None:
            comp = comp.set_audio(base.audio)
        comp.write_videofile(
            output_path, codec="libx264", audio_codec="aac", fps=30,
            preset="medium", ffmpeg_params=["-pix_fmt", "yuv420p"],
            logger=None, threads=4,
        )
        return comp

    final = None
    try:
        final = _render(layers)
    except Exception as e:
        # Belt-and-suspenders: si algún overlay peta, saca al menos el vídeo
        # con zoom + textos (sin lo que sobre) para no dejar al operador sin nada.
        log(f"  ⚠️ Render con overlays falló ({str(e)[:80]}) — reintento sin flecha")
        safe = [core] + [x for x in (hk,) if x is not None]
        final = _render(safe)

    for c in (base, final):
        try:
            c.close()
        except Exception:
            pass
    log(f"✅ Listo: {os.path.basename(output_path)}")
    return output_path
