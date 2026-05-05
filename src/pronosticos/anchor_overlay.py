"""Overlay 'palabra-ancla GIGANTE' estilo el vídeo de referencia.

Genera un ImageClip con una sola palabra/número en pantalla, blanco con borde
negro grueso (estilo bold TikTok). Se usa para destacar números clave o
nombres durante la narración de cada combinada.

Patrón de aparición: cada anchor_word se muestra ~1.5-2.0s repartidos a lo
largo de la duración del segmento (centrado vertical-bajo).
"""

from __future__ import annotations


import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip


def _load_font(size: int):
    from src.font_resolver import resolve_font
    for path in (r"C:\Windows\Fonts\impact.ttf", r"C:\Windows\Fonts\arialbd.ttf"):
        try:
            return ImageFont.truetype(resolve_font(path), size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_anchor_image(text: str, video_size: tuple[int, int],
                        font_scale: float = 0.10,
                        text_color: str = "#FFFFFF",
                        stroke_color: str = "#000000",
                        stroke_width: int = 14) -> Image.Image:
    """Renderiza una PNG transparente con la palabra-ancla centrada horizontalmente."""
    W, H = video_size
    base_size = max(60, int(H * font_scale))

    # Auto-shrink si el texto excede 90% del ancho
    size = base_size
    while size > 40:
        font = _load_font(size)
        tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(tmp)
        bbox = d.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        tw = bbox[2] - bbox[0]
        if tw <= int(W * 0.90):
            break
        size -= 4
    font = _load_font(size)

    bbox = ImageDraw.Draw(Image.new("RGBA", (W, H))).textbbox(
        (0, 0), text, font=font, stroke_width=stroke_width
    )
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    canvas_h = th + stroke_width * 4
    canvas = Image.new("RGBA", (W, canvas_h), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(canvas)
    x = (W - tw) // 2
    y = stroke_width * 2
    cdraw.text(
        (x, y), text, font=font,
        fill=text_color, stroke_width=stroke_width, stroke_fill=stroke_color,
        anchor="lt",
    )
    return canvas


def build_anchor_clips(anchor_words: list[str], total_duration: float,
                       video_size: tuple[int, int],
                       y_position_pct: float = 0.78) -> list:
    """Devuelve una lista de ImageClips temporizados para el segmento.

    Reparto: cada anchor_word ocupa el slot proporcional (con un mini-gap),
    centrado en `y_position_pct` del frame. Las palabras NO se solapan.
    """
    if not anchor_words or total_duration < 0.5:
        return []

    W, H = video_size
    n = len(anchor_words)
    # Empezamos a 0.5s del inicio del segmento, dejamos 0.3s al final
    start_offset = min(0.5, total_duration * 0.1)
    end_offset = min(0.3, total_duration * 0.05)
    usable = max(0.5, total_duration - start_offset - end_offset)
    slot = usable / n

    clips = []
    for i, word in enumerate(anchor_words):
        if not word or not word.strip():
            continue
        img = render_anchor_image(word.strip().upper(), video_size)
        arr = np.array(img)
        clip_h = arr.shape[0]
        y_top = int(H * y_position_pct) - clip_h // 2
        y_top = max(0, min(H - clip_h, y_top))

        clip = (
            ImageClip(arr, transparent=True)
            .set_start(start_offset + i * slot)
            .set_duration(max(0.4, slot * 0.85))  # 15% gap entre palabras
            .set_position(("center", y_top))
        )
        clips.append(clip)

    return clips
