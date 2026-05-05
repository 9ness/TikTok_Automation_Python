"""Gancho de texto (hook box) estilo titular de noticias para TikToks.

Caja blanca con texto oscuro centrado + sombra coloreada offset que simula un
efecto 3D (como en las capturas de referencia del usuario).

Aparece al inicio del vídeo durante `duration` segundos y sale con una animación
configurable (swipe_left, news_flash, slide_in_out, fade).

El texto por defecto es el video_title del script — pero es editable por vídeo.
"""

from __future__ import annotations


import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip


DEFAULT_HOOK_STYLE = {
    "duration": 5.0,
    "y_position_pct": 0.40,          # centro-alto (arriba del centro, como el ejemplo del usuario)
    "text_color": "#0B0B0B",
    "box_color": "#FFFFFF",
    "shadow_color": "#1E01C4",       # azul por defecto (coincide con preset subs)
    "shadow_offset_x_pct": -0.016,   # -17px en 1080 (izquierda) — sombra más notoria
    "shadow_offset_y_pct": 0.012,    # +23px (abajo) — sombra más notoria
    "padding_x_pct": 0.028,
    "padding_y_pct": 0.012,
    "border_radius": 0,              # rectángulo puro — esquinas 90° sin redondeo
    "font_path": r"C:\Windows\Fonts\arialbd.ttf",
    "font_scale": 0.018,             # relativo al alto del vídeo — discreto, no invade
    "max_width_pct": 0.90,
    "max_lines": 2,                  # max 2 líneas; auto-shrink de la fuente si hace falta
    "animation": "swipe_left",       # swipe_left | news_flash | slide_in_out | fade
    "exit_time": 0.35,
    "enter_time": 0.30,
}

# Zonas seguras de TikTok (heredadas de subtitles.py — mantener coherencia)
TIKTOK_SAFE_Y = (0.15, 0.80)


def _load_font(font_path: str, size: int):
    from src.font_resolver import resolve_font
    try:
        return ImageFont.truetype(resolve_font(font_path), size)
    except Exception:
        for fallback in [
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\impact.ttf",
        ]:
            try:
                return ImageFont.truetype(resolve_font(fallback), size)
            except Exception:
                continue
        return ImageFont.load_default()


def _wrap_text_to_lines(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Envuelve el texto en líneas respetando max_width. Intenta partir por palabras."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current: list[str] = []
    current_w = 0
    space_w = draw.textlength(" ", font=font)
    for w in words:
        ww = draw.textlength(w, font=font)
        add_w = ww + (space_w if current else 0)
        if current and current_w + add_w > max_width:
            lines.append(" ".join(current))
            current = [w]
            current_w = ww
        else:
            current.append(w)
            current_w += add_w
    if current:
        lines.append(" ".join(current))
    return lines


def render_hook_box(text: str, style: dict, video_size: tuple[int, int]) -> Image.Image:
    """Devuelve un PNG-RGBA con la caja blanca + sombra azul + texto centrado.

    Si el texto no cabe en `max_lines` al font_scale pedido, auto-reduce la fuente
    iterativamente hasta que quepa (o alcance un mínimo de 20px).
    El ancho de la imagen es el del vídeo (para permitir swipes); la caja queda centrada.
    """
    W, H = video_size
    s = {**DEFAULT_HOOK_STYLE, **style}

    initial_size = max(20, int(H * s["font_scale"]))
    max_lines = int(s.get("max_lines", 3))

    # Canvas temporal para medir
    tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tmp)

    max_box_w = int(W * s["max_width_pct"])
    pad_x = int(W * s["padding_x_pct"])
    pad_y = int(H * s["padding_y_pct"])
    max_text_w = max_box_w - 2 * pad_x

    # Auto-shrink: baja la fuente de 2 en 2 px hasta que el texto quepa en max_lines.
    font_size = initial_size
    font = _load_font(s["font_path"], font_size)
    lines = _wrap_text_to_lines(draw, text, font, max_text_w)
    while len(lines) > max_lines and font_size > 20:
        font_size -= 2
        font = _load_font(s["font_path"], font_size)
        lines = _wrap_text_to_lines(draw, text, font, max_text_w)

    # Medir cada línea
    line_heights: list[int] = []
    line_widths: list[int] = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, anchor="lt")
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    # Usar altura probe "Mg" para espaciado consistente
    probe = draw.textbbox((0, 0), "Mg", font=font, anchor="lt")
    line_h_std = probe[3] - probe[1]
    line_spacing = int(line_h_std * 0.25)

    text_block_h = len(lines) * line_h_std + max(0, len(lines) - 1) * line_spacing
    text_block_w = max(line_widths) if line_widths else 0

    box_w = text_block_w + 2 * pad_x
    box_h = text_block_h + 2 * pad_y

    # Offset de sombra
    shadow_dx = int(W * s["shadow_offset_x_pct"])
    shadow_dy = int(H * s["shadow_offset_y_pct"])

    # Canvas final: ancho del vídeo, alto = caja + margen para que la sombra no se recorte
    canvas_h = box_h + abs(shadow_dy) * 2 + abs(shadow_dx) * 0  # vertical pad solo
    canvas = Image.new("RGBA", (W, canvas_h), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(canvas)

    # Centrar la caja horizontalmente
    box_x = (W - box_w) // 2
    box_y = abs(shadow_dy) if shadow_dy < 0 else 0

    # 1. Sombra (caja desplazada)
    shadow_x0 = box_x + shadow_dx
    shadow_y0 = box_y + shadow_dy
    cdraw.rounded_rectangle(
        [shadow_x0, shadow_y0, shadow_x0 + box_w, shadow_y0 + box_h],
        radius=s["border_radius"],
        fill=s["shadow_color"],
    )

    # 2. Caja principal
    cdraw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=s["border_radius"],
        fill=s["box_color"],
    )

    # 3. Texto
    y_text = box_y + pad_y
    for i, line in enumerate(lines):
        x_text = box_x + (box_w - line_widths[i]) // 2
        cdraw.text(
            (x_text, y_text),
            line,
            font=font,
            fill=s["text_color"],
            anchor="lt",
        )
        y_text += line_h_std + line_spacing

    return canvas


def render_preview_image(
    text: str,
    style: dict,
    video_size: tuple[int, int] = (1080, 1920),
) -> Image.Image:
    """Preview del hook para mostrar en Streamlit."""
    return render_hook_box(text, style, video_size)


# ---------------------------------------------------------------------
# Animaciones
# ---------------------------------------------------------------------

def _make_position_func(animation: str, video_size: tuple[int, int], hook_size: tuple[int, int],
                        y_center_px: int, duration: float, enter_time: float, exit_time: float):
    """Devuelve un callable t -> (x, y) según la animación seleccionada."""
    W, H = video_size
    hw, hh = hook_size
    center_x = (W - hw) // 2
    y_top = y_center_px - hh // 2

    if animation == "swipe_left":
        def pos(t):
            if t <= duration - exit_time:
                return (center_x, y_top)
            # Fase de salida: easing cuadrático
            p = (t - (duration - exit_time)) / exit_time
            p = p * p
            x = int(center_x - p * (center_x + hw + 60))
            return (x, y_top)
        return pos

    if animation == "slide_in_out":
        def pos(t):
            if t < enter_time:
                p = t / enter_time
                p = 1 - (1 - p) ** 3  # ease-out
                x = int(-hw + p * (center_x + hw))
                return (x, y_top)
            if t <= duration - exit_time:
                return (center_x, y_top)
            p = (t - (duration - exit_time)) / exit_time
            p = p * p
            x = int(center_x - p * (center_x + hw + 60))
            return (x, y_top)
        return pos

    if animation == "news_flash":
        # Pequeña vibración al entrar + swipe al salir
        def pos(t):
            if t < enter_time:
                shake = int(6 * np.sin(t * 40) * (1 - t / enter_time))
                return (center_x + shake, y_top)
            if t <= duration - exit_time:
                return (center_x, y_top)
            p = (t - (duration - exit_time)) / exit_time
            p = p * p
            x = int(center_x - p * (center_x + hw + 60))
            return (x, y_top)
        return pos

    # fade: posición estática; la opacidad se maneja aparte con .set_opacity()
    def pos(_t):
        return (center_x, y_top)
    return pos


def _apply_news_flash_scale(clip, enter_time: float):
    """Pop-in escala 1.15 → 1.0 en los primeros enter_time segundos."""
    def scale_func(t):
        if t >= enter_time:
            return 1.0
        p = t / enter_time
        p = 1 - (1 - p) ** 3
        return 1.15 - 0.15 * p
    return clip.resize(scale_func)


def _apply_fade(clip, duration: float, enter_time: float, exit_time: float):
    """Fade in + fade out vía opacidad."""
    def opacity(t):
        if t < enter_time:
            return max(0.0, min(1.0, t / enter_time))
        if t > duration - exit_time:
            return max(0.0, min(1.0, (duration - t) / exit_time))
        return 1.0
    # moviepy set_opacity en ImageClip no acepta función directamente; usamos fl_image
    # Trick: aplicar fade con crossfadein + crossfadeout, que es lo que usa moviepy por dentro.
    return clip.crossfadein(enter_time).crossfadeout(exit_time)


# ---------------------------------------------------------------------
# Pipeline: overlay sobre el vídeo
# ---------------------------------------------------------------------

def add_text_hook_to_video(
    video_path: str,
    hook_text: str,
    style: dict,
    output_path: str,
    log_callback=None,
) -> str:
    """Superpone el gancho de texto sobre un vídeo existente y escribe output_path."""
    s = {**DEFAULT_HOOK_STYLE, **style}

    video = VideoFileClip(video_path)
    W, H = video.size

    hook_img = render_hook_box(hook_text, s, (W, H))
    hook_np = np.array(hook_img)

    duration = min(float(s["duration"]), video.duration)
    enter_time = float(s["enter_time"])
    exit_time = float(s["exit_time"])

    clip = ImageClip(hook_np, transparent=True).set_duration(duration).set_start(0)

    # Altura visual del hook (incluye margen para la sombra)
    hook_h = hook_np.shape[0]
    # Y central respetando zonas seguras de TikTok
    y_pct = max(TIKTOK_SAFE_Y[0], min(TIKTOK_SAFE_Y[1], s["y_position_pct"]))
    y_center_px = int(H * y_pct)

    animation = s["animation"]

    if animation == "news_flash":
        clip = _apply_news_flash_scale(clip, enter_time)

    pos_func = _make_position_func(
        animation, (W, H), (W, hook_h), y_center_px, duration, enter_time, exit_time,
    )
    clip = clip.set_position(pos_func)

    if animation == "fade":
        clip = _apply_fade(clip, duration, enter_time, exit_time)

    if log_callback:
        log_callback(f"🎣 Overlay hook: '{hook_text[:40]}...' duración={duration}s animación={animation}")

    final = CompositeVideoClip([video, clip], size=(W, H))

    final.write_videofile(
        output_path,
        fps=video.fps,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=8,
        logger=None,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )
    video.close()
    return output_path
