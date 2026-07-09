"""Deja un vídeo generado (Flow/Kling) LISTO para subir a TikTok Shop:

1. **Zoom** para sacar la marca de agua del borde fuera de cuadro (lo que el
   operador hacía a mano) → escala + recorte centrado a 1080x1920 (9:16).
2. Quema el **gancho** (arriba) y el **CTA** (abajo) con estética TikTok
   (Montserrat ExtraBold, blanco con borde negro grueso, legible sobre todo).

Sin coste (ffmpeg/MoviePy local). Los emojis se quitan del texto quemado
(no se rasterizan bien); el texto va limpio.
"""

from __future__ import annotations

import os
import re
from typing import Callable

import numpy as np
from moviepy.editor import CompositeVideoClip, ImageClip, VideoFileClip
from moviepy.video.fx.all import crop
from PIL import Image, ImageDraw, ImageFont

from src.font_resolver import _bundled_fonts_dir

_noop: Callable[[str], None] = lambda _m: None

TARGET_W, TARGET_H = 1080, 1920

# Emojis / pictogramas fuera del BMP → fuera del texto quemado.
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿⬀-⯿️]+"
)


def _font_path(name: str = "Montserrat-ExtraBold.ttf") -> str:
    p = os.path.join(_bundled_fonts_dir(), name)
    return p if os.path.exists(p) else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _clean(text: str) -> str:
    return _EMOJI_RE.sub("", text or "").strip()


def _wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
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


def _render_text_png(text: str, *, font_size: int, max_w: int) -> Image.Image | None:
    """Texto blanco con borde negro grueso (estilo TikTok) sobre transparente."""
    text = _clean(text)
    if not text:
        return None
    font = ImageFont.truetype(_font_path(), font_size)
    stroke = max(3, int(font_size * 0.14))
    scratch = Image.new("RGBA", (10, 10))
    d0 = ImageDraw.Draw(scratch)
    lines = _wrap(d0, text, font, max_w)
    line_h = int(font_size * 1.18)
    pad = stroke + 8
    w = int(max((d0.textlength(ln, font=font) for ln in lines), default=0)) + pad * 2
    h = line_h * len(lines) + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        lw = d.textlength(ln, font=font)
        x = (w - lw) / 2
        y = pad + i * line_h
        d.text((x, y), ln, font=font, fill="white",
               stroke_width=stroke, stroke_fill="black")
    return img


def _text_clip(text: str, *, font_size: int, y_center_pct: float, duration: float):
    png = _render_text_png(text, font_size=font_size, max_w=int(TARGET_W * 0.86))
    if png is None:
        return None
    clip = ImageClip(np.array(png)).set_duration(duration)
    y = int(TARGET_H * y_center_pct - png.height / 2)
    return clip.set_position(("center", y))


def process_ready_video(
    input_path: str,
    output_path: str,
    *,
    hook_text: str = "",
    cta_text: str = "",
    zoom: float = 1.12,
    log: Callable[[str], None] = _noop,
) -> str:
    """Procesa el vídeo → 1080x1920 con zoom (quita marca) + gancho + CTA."""
    zoom = max(1.0, min(1.6, float(zoom)))
    log(f"🎬 Procesando (zoom {zoom:.2f}) → 1080x1920…")
    base = VideoFileClip(input_path)

    # Cover-fit a 1080x1920, luego zoom, luego recorte centrado.
    if base.w / base.h > TARGET_W / TARGET_H:
        fitted = base.resize(height=TARGET_H)
    else:
        fitted = base.resize(width=TARGET_W)
    zoomed = fitted.resize(zoom)
    core = crop(zoomed, x_center=zoomed.w / 2, y_center=zoomed.h / 2,
                width=TARGET_W, height=TARGET_H)

    layers = [core]
    hk = _text_clip(hook_text, font_size=64, y_center_pct=0.16, duration=core.duration)
    if hk is not None:
        layers.append(hk)
        log("  📌 Gancho quemado (arriba)")
    ct = _text_clip(cta_text, font_size=46, y_center_pct=0.82, duration=core.duration)
    if ct is not None:
        layers.append(ct)
        log("  🛒 CTA quemado (abajo)")

    final = CompositeVideoClip(layers, size=(TARGET_W, TARGET_H))
    if base.audio is not None:
        final = final.set_audio(base.audio)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final.write_videofile(
        output_path, codec="libx264", audio_codec="aac", fps=30,
        preset="medium", ffmpeg_params=["-pix_fmt", "yuv420p"],
        logger=None, threads=4,
    )
    for c in (base, final):
        try:
            c.close()
        except Exception:
            pass
    log(f"✅ Listo: {os.path.basename(output_path)}")
    return output_path
