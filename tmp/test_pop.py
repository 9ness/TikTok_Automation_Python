"""Render de prueba del pop de entrada (una palabra) sobre el sample."""
from __future__ import annotations
import os
from dotenv import load_dotenv
load_dotenv()

from src.subtitles_only import render_subtitles_on_video

IN = "tmp/subtitulos_ejemplo.mp4"
OUT = "tmp/pop_test.mp4"

# Palabras sintéticas, 1 por chunk (modo "una palabra").
words = [
    {"word": "HOLA",  "start": 0.40, "end": 0.80},
    {"word": "ESTO",  "start": 0.85, "end": 1.20},
    {"word": "SE",    "start": 1.25, "end": 1.55},
    {"word": "HACE",  "start": 1.60, "end": 1.95},
    {"word": "VIRAL", "start": 2.00, "end": 2.60},
]
style = {
    "font_path": r"assets/fonts/anton.ttf" if os.path.exists("assets/fonts/anton.ttf") else None,
    "highlight_mode": "none",
    "text_color": "#FFFFFF",
    "stroke_color": "#000000",
    "stroke_width": 2,
    "case_mode": "UPPERCASE",
    "font_scale": 0.06,
    "max_words_per_chunk": 1,
    "y_position_pct": 0.5,
    "entrance_anim": "pop",
}
# Quita font_path None para que use default.
if not style["font_path"]:
    style.pop("font_path")

render_subtitles_on_video(
    IN, words, style, OUT,
    quality_settings={"preset": "ultrafast", "crf": 23, "max_long_side": 720},
    log_callback=lambda m: print(str(m).encode("ascii", "ignore").decode(), flush=True),
)
print("DONE", OUT, os.path.getsize(OUT))
