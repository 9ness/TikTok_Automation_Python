"""Variante NÚMEROS para Presidentes Top 5.

Overlay persistente estilo "lista que se rellena":
- Header fijo arriba con el gancho durante TODO el vídeo (no animado).
- Lista vertical de números 1..N a la izquierda (se adapta a top_count 3/4/5).
- Cada nombre se rellena justo cuando suena su segmento (orden countdown
  5→1) y permanece en pantalla (acumula). Al final se ve la lista completa.

Se aplica como pasada final sobre el vídeo (igual que subs/hook). En esta
variante el header SUSTITUYE al hook box animado.

`reveals` es una lista de dicts {puesto:int, name:str, reveal_time:float} que
el runner calcula a partir de las duraciones acumuladas de cada segmento.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip

from src.text_hook import _load_font, render_hook_box


DEFAULT_NUMBERS_STYLE = {
    "font_path": r"C:\Windows\Fonts\impact.ttf",
    # El #1 (puesto 1) es el misterio: en la lista se muestra como incógnita,
    # nunca el nombre real. Es el último en revelarse (countdown 5→1).
    "mystery_text": "???",
    # Header (gancho fijo todo el vídeo)
    "header_text": "",                 # vacío → usa el hook_box_text del guion
    "header_y_position": 0.07,         # centro vertical del header (0=arriba)
    "header_font_scale": 0.024,        # relativo al alto del vídeo
    "header_text_color": "#0B0B0B",
    "header_box_color": "#FFFFFF",
    "header_shadow_color": "#1E01C4",
    # Lista de números
    "list_x_position": 0.07,           # X del número (0=izquierda) — centro col.
    "list_y_position": 0.32,           # Y del centro de la primera fila
    "list_line_spacing": 0.105,        # separación vertical entre filas (pct alto)
    "number_font_scale": 0.044,
    "name_font_scale": 0.036,
    # Color base de los números (puestos 4,5,…). Los puestos 1/2/3 usan
    # oro/plata/bronce si `number_medal_colors` está activo.
    "number_color": "#FFFFFF",
    "number_medal_colors": True,
    "number_color_gold": "#FFD700",     # #1
    "number_color_silver": "#C0C0C0",   # #2
    "number_color_bronze": "#CD7F32",   # #3
    "name_color": "#FFFFFF",
    "name_stroke_color": "#000000",
    "name_stroke_width": 3,
}


def _render_text(
    text: str,
    size: int,
    color: str,
    font_path: str,
    stroke_color: str,
    stroke_width: int,
) -> Image.Image:
    """Renderiza `text` en un PNG-RGBA ajustado (con stroke perimetral)."""
    font = _load_font(font_path, size)
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    bbox = d.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    w = max(1, bbox[2] - bbox[0])
    h = max(1, bbox[3] - bbox[1])
    pad = stroke_width + 4
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    dd = ImageDraw.Draw(img)
    dd.text(
        (pad - bbox[0], pad - bbox[1]),
        text,
        font=font,
        fill=color,
        stroke_width=stroke_width,
        stroke_fill=stroke_color,
    )
    return img


def add_numbers_overlay_to_video(
    video_path: str,
    header_text: str,
    reveals: list[dict],
    top_count: int,
    style: dict,
    output_path: str,
    log_callback=None,
) -> str:
    """Superpone el header fijo + la lista numerada que se rellena y escribe
    output_path."""
    s = {**DEFAULT_NUMBERS_STYLE, **(style or {})}

    video = VideoFileClip(video_path)
    W, H = video.size
    dur = float(video.duration)
    font_path = s["font_path"]

    layers = [video]

    # ----- Header fijo (todo el vídeo) -----
    header_txt = (s.get("header_text") or "").strip() or (header_text or "").strip()
    if header_txt:
        header_style = {
            "y_position_pct": s["header_y_position"],
            "font_scale": s["header_font_scale"],
            "text_color": s["header_text_color"],
            "box_color": s["header_box_color"],
            "shadow_color": s["header_shadow_color"],
            "font_path": font_path,
            "max_lines": 2,
        }
        header_img = render_hook_box(header_txt, header_style, (W, H))
        header_np = np.array(header_img)
        hh = header_np.shape[0]
        y_center = int(H * float(s["header_y_position"]))
        y_top = max(0, y_center - hh // 2)
        header_clip = (
            ImageClip(header_np, transparent=True)
            .set_duration(dur)
            .set_position((0, y_top))
        )
        layers.append(header_clip)
        if log_callback:
            log_callback(f"🔢 Header fijo: \"{header_txt[:40]}\"")

    # ----- Lista de números + nombres -----
    list_x = int(W * float(s["list_x_position"]))
    list_y = int(H * float(s["list_y_position"]))
    spacing = int(H * float(s["list_line_spacing"]))
    num_size = max(20, int(H * float(s["number_font_scale"])))
    name_size = max(20, int(H * float(s["name_font_scale"])))
    name_gap = int(W * 0.02)

    reveal_by_puesto = {int(r["puesto"]): r for r in (reveals or [])}

    medal = {
        1: s.get("number_color_gold", "#FFD700"),
        2: s.get("number_color_silver", "#C0C0C0"),
        3: s.get("number_color_bronze", "#CD7F32"),
    }

    for slot in range(1, int(top_count) + 1):
        row_center_y = list_y + (slot - 1) * spacing

        # Color del número: medalla (1/2/3) o color base (4,5,…).
        num_color = s["number_color"]
        if s.get("number_medal_colors") and slot in medal:
            num_color = medal[slot]

        # Número (persistente, visible desde el inicio)
        num_img = _render_text(
            f"{slot}.", num_size, num_color, font_path,
            s["name_stroke_color"], int(s["name_stroke_width"]),
        )
        num_np = np.array(num_img)
        num_y = row_center_y - num_np.shape[0] // 2
        layers.append(
            ImageClip(num_np, transparent=True)
            .set_duration(dur)
            .set_position((list_x, num_y))
        )

        # Nombre (aparece en reveal_time y permanece). El #1 es el misterio
        # del vídeo → se muestra como incógnita, nunca el nombre real.
        r = reveal_by_puesto.get(slot)
        if r:
            if slot == 1:
                name_txt = str(s.get("mystery_text") or "???").strip() or "???"
            else:
                name_txt = str(r["name"]).replace("_", " ").strip()
            name_img = _render_text(
                name_txt, name_size, s["name_color"], font_path,
                s["name_stroke_color"], int(s["name_stroke_width"]),
            )
            name_np = np.array(name_img)
            name_x = list_x + num_np.shape[1] + name_gap
            name_y = row_center_y - name_np.shape[0] // 2
            start = max(0.0, min(dur - 0.05, float(r.get("reveal_time", 0.0))))
            layers.append(
                ImageClip(name_np, transparent=True)
                .set_start(start)
                .set_duration(max(0.1, dur - start))
                .set_position((name_x, name_y))
            )

    final = CompositeVideoClip(layers, size=(W, H))
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
