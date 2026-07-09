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

import os
import re
from typing import Callable

import numpy as np
from moviepy.editor import CompositeVideoClip, ImageClip, VideoFileClip
from moviepy.video.fx.all import crop, loop, resize
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


def _render_text_png(text: str, *, font_size: int, max_w: int):
    text = _clean(text)
    if not text:
        return None
    font = ImageFont.truetype(_font_path(), font_size)
    stroke = max(3, int(font_size * 0.15))
    d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    lines = _wrap(d0, text, font, max_w)
    line_h = int(font_size * 1.18)
    pad = stroke + 10
    w = int(max((d0.textlength(ln, font=font) for ln in lines), default=0)) + pad * 2
    h = line_h * len(lines) + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        x = (w - d.textlength(ln, font=font)) / 2
        d.text((x, pad + i * line_h), ln, font=font, fill="white",
               stroke_width=stroke, stroke_fill="black")
    return img


def _text_clip(text, *, font_size, y_center_pct, max_w_pct, duration):
    png = _render_text_png(text, font_size=font_size, max_w=int(TARGET_W * max_w_pct))
    if png is None:
        return None
    y = int(TARGET_H * y_center_pct - png.height / 2)
    return ImageClip(np.array(png)).set_duration(duration).set_position(("center", y))


# ── Flecha CTA (asset del Editor Auto, color adaptado por contraste) ─────
# Posición de la flecha (abajo-izq, apuntando al carrito de TikTok Shop).
_ARROW_X, _ARROW_Y = 0.12, 0.78


def _pick_arrow(core, folder: str):
    """Elige la flecha del Editor Auto que MÁS contrasta con el fondo de su
    zona (reusa la lógica WCAG de sticker_arrow). Fallback: blanca abajo."""
    from src.editor_auto.tools.sticker_arrow import _ARROW_COLORS, _best_contrast_arrow

    pool = [os.path.join(folder, f) for f in _ARROW_COLORS
            if os.path.exists(os.path.join(folder, f))]
    if not pool:
        return None
    # Color medio del fondo en la zona de la flecha.
    try:
        fr = core.get_frame((core.duration or 2) * 0.5)
        x0, y0 = int(TARGET_W * _ARROW_X), int(TARGET_H * _ARROW_Y)
        patch = fr[y0:y0 + int(TARGET_H * 0.12), x0:x0 + int(TARGET_W * 0.16)]
        bg = tuple(float(v) for v in patch.reshape(-1, 3).mean(axis=0))
    except Exception:
        bg = (0.0, 0.0, 0.0)
    return _best_contrast_arrow(pool, bg)


def _arrow_clip(core, duration, log=_noop):
    try:
        from src.editor_auto.config import arrows_folder
        folder = arrows_folder()
        if not os.path.isdir(folder):
            return None
        path = _pick_arrow(core, folder)
        if path is None or not os.path.exists(path):
            return None
        arr = VideoFileClip(path, has_mask=True)
        arr = loop(resize(arr, width=int(TARGET_W * 0.16)), duration=duration)
        log(f"  ➘ Flecha CTA: {os.path.basename(path)} (mejor contraste)")
        return arr.set_position((int(TARGET_W * _ARROW_X), int(TARGET_H * _ARROW_Y)))
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
    log: Callable[[str], None] = _noop,
) -> str:
    zoom = max(1.0, min(1.4, float(zoom)))
    log("🎬 Procesando vídeo → 1080x1920…")
    base = VideoFileClip(input_path)

    # Cover-fit a 9:16 sin zoom aún.
    fitted = base.resize(height=TARGET_H) if base.w / base.h > TARGET_W / TARGET_H \
        else base.resize(width=TARGET_W)
    fitted = crop(fitted, x_center=fitted.w / 2, y_center=fitted.h / 2,
                  width=TARGET_W, height=TARGET_H)

    # Zoom inteligente: detectar esquina de la marca y recortar dirigido.
    corner = detect_watermark_corner(fitted, log=log)
    zw, zh, xc, yc = _crop_params(corner, TARGET_W, TARGET_H, zoom)
    zoomed = resize(fitted, newsize=(int(zw), int(zh)))
    core = crop(zoomed, x_center=xc, y_center=yc, width=TARGET_W, height=TARGET_H)

    layers = [core]
    hk = _text_clip(hook_text, font_size=64, y_center_pct=0.17,
                    max_w_pct=0.84, duration=core.duration)
    if hk is not None:
        layers.append(hk)
        log("  📌 Gancho (zona segura arriba)")
    ct = _text_clip(cta_text, font_size=46, y_center_pct=0.70,
                    max_w_pct=0.60, duration=core.duration)
    if ct is not None:
        layers.append(ct)
        log("  🛒 CTA (zona segura)")
    if with_arrow:
        ar = _arrow_clip(core, core.duration, log=log)
        if ar is not None:
            layers.append(ar)

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
