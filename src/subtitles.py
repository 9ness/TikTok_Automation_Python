"""Generación de subtítulos karaoke estilo TikTok.

Pipeline:
1. transcribe(audio_path) — usa faster-whisper local (gratis, ~10-30s por vídeo de 60s).
2. render_preview(style) — genera una PNG de muestra para mostrar en Streamlit.
3. render_karaoke_on_video(video_path, words, style, output_path) — overlay final.

El estilo es palabra-a-palabra con "píldora" coloreada detrás de la palabra que se está
pronunciando (igual que la captura de referencia del usuario).

Zonas seguras de TikTok (TIKTOK_SAFE_ZONE) evitan solaparse con los iconos laterales,
el nombre de usuario, la descripción y los botones.
"""

from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip


# ---------------------------------------------------------------------
# Zonas seguras de TikTok (porcentajes del frame)
# ---------------------------------------------------------------------
# Basado en la UI estándar de TikTok vertical (9:16):
#   - Top 0-12%: nombre de usuario, info de audio
#   - Right 80-100%: stack de acciones (like, comment, share, bookmark, perfil)
#   - Bottom 78-100%: descripción, audio, creador
# Por eso el slot "seguro" para texto queda: y ∈ [0.15, 0.75], x ∈ [0.05, 0.78].
TIKTOK_SAFE_Y = (0.15, 0.75)
TIKTOK_SAFE_X = (0.05, 0.78)


# ---------------------------------------------------------------------
# Modelo Whisper (lazy load, cacheado en memoria)
# ---------------------------------------------------------------------
_WHISPER_MODEL = None
_WHISPER_MODEL_SIZE = None


def _get_whisper_model(model_size: str = "base"):
    global _WHISPER_MODEL, _WHISPER_MODEL_SIZE
    if _WHISPER_MODEL is not None and _WHISPER_MODEL_SIZE == model_size:
        return _WHISPER_MODEL
    from faster_whisper import WhisperModel

    # Intento GPU primero (si hay CUDA), fallback a CPU
    try:
        _WHISPER_MODEL = WhisperModel(model_size, device="cuda", compute_type="float16")
        print(f"🎙️ faster-whisper cargado en GPU (modelo: {model_size})")
    except Exception:
        _WHISPER_MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
        print(f"🎙️ faster-whisper cargado en CPU (modelo: {model_size})")
    _WHISPER_MODEL_SIZE = model_size
    return _WHISPER_MODEL


def _clean_whisper_tokens(words: list[dict]) -> list[dict]:
    """Limpia y fusiona tokens problemáticos de Whisper.

    - Elimina puntos, comas y puntuación interna → 'U.S.' se convierte en 'US'.
    - Descarta tokens que son SOLO puntuación.
    - Fusiona tokens cortos (1-3 chars) consecutivos y temporalmente cercanos:
      Whisper a veces parte 'U.S.' en ['U','.','S','.'] — esta lógica los vuelve a juntar en 'US'.
    """
    # Paso 1: limpiar cada token individual
    cleaned: list[dict] = []
    for w in words:
        text = (w["word"] or "").strip()
        if not text:
            continue
        # Si el token es solo puntuación, lo descartamos
        if all(c in ".,?!:;-\"'()" for c in text):
            continue
        # Quitamos puntos y comas internos (abreviaturas tipo U.S. / D.C. / Ph.D.)
        cleaned_text = text.replace(".", "").replace(",", "")
        if not cleaned_text:
            continue
        cleaned.append({"word": cleaned_text, "start": w["start"], "end": w["end"]})

    # Paso 2: fusionar SOLO tokens de 1 carácter consecutivos y temporalmente cercanos (<120ms).
    # Esto cubre el patrón de abreviatura 'U.S.' → tras quitar puntos quedan 'U' y 'S' que
    # se fusionan en 'US'. NO fusiona palabras normales como 'IN' + 'US' (ambas 2 chars).
    merged: list[dict] = []
    i = 0
    while i < len(cleaned):
        cur = dict(cleaned[i])
        while i + 1 < len(cleaned) and len(cur["word"]) == 1 and cur["word"].isalpha():
            nxt = cleaned[i + 1]
            if (
                len(nxt["word"]) == 1
                and nxt["word"].isalpha()
                and (nxt["start"] - cur["end"]) < 0.12
            ):
                cur["word"] = cur["word"] + nxt["word"]
                cur["end"] = nxt["end"]
                i += 1
            else:
                break
        merged.append(cur)
        i += 1
    return merged


def transcribe(audio_path: str, model_size: str = "base", language: str | None = "en") -> list[dict]:
    """Transcribe un audio y devuelve lista de {word, start, end} por palabra.

    Aplica _clean_whisper_tokens para corregir casos como 'U.S.' → 'US'.
    """
    model = _get_whisper_model(model_size)
    segments, _info = model.transcribe(audio_path, word_timestamps=True, language=language)
    raw_words: list[dict] = []
    for segment in segments:
        if not getattr(segment, "words", None):
            continue
        for w in segment.words:
            text = (w.word or "").strip()
            if not text:
                continue
            raw_words.append({"word": text, "start": float(w.start), "end": float(w.end)})
    return _clean_whisper_tokens(raw_words)


# ---------------------------------------------------------------------
# Renderizado PIL
# ---------------------------------------------------------------------

DEFAULT_STYLE = {
    "font_path": r"C:\Windows\Fonts\impact.ttf",
    "font_scale": 0.040,  # relativo a la altura del vídeo — compacto
    "text_color": "#FFFFFF",
    "stroke_color": "#000000",
    "stroke_width": 1,
    "highlight_color": "#1E01C4",  # azul preset del usuario; rojo preset alternativo: #BB0808
    "pill_enabled": True,           # legacy: False fuerza highlight_mode="none"
    # Cómo se marca la palabra activa. Modos:
    #   "pill"        — píldora rellena detrás (default — TikTok style)
    #   "color_swap"  — la palabra activa cambia a highlight_color, sin fondo
    #   "underline"   — barra horizontal de highlight_color debajo de la palabra
    #   "box_outline" — recuadro hueco redondeado alrededor (sin relleno)
    #   "glow"        — halo difuminado de highlight_color alrededor del texto
    #   "none"        — sin marcado (texto estático, la sincronización viene del cambio de chunk)
    # IMPORTANTE: dejar None aquí para que `_resolve_highlight_mode` aplique el
    # fallback legacy basado en `pill_enabled` cuando un caller no fija highlight_mode
    # explícitamente (p.ej. PRONOSTICOS_SUB_STYLE define pill_enabled=False y espera
    # comportamiento "none" sin tener que conocer la nueva API).
    "highlight_mode": None,
    "case_mode": "UPPERCASE",  # UPPERCASE | lowercase | Title Case | original
    "max_words_per_chunk": 4,
    "y_position_pct": 0.62,  # margen amplio bajo el hook, lejos de la UI TikTok
    "pill_radius": 10,
    "pill_pad_x_pct": 0.010,  # padding horizontal relativo al ancho del vídeo
    "pill_pad_y_pct": 0.005,  # padding vertical relativo al alto del vídeo
    "line_spacing_pct": 0.015,  # gap visible entre líneas (además del padding de la píldora)
    "word_spacing_multiplier": 0.65,  # <1.0 = palabras más juntas; >1.0 = más separadas
    # Ancho máximo del bloque de texto como fracción del ancho del vídeo.
    # None = comportamiento legacy (zona segura TikTok = 0.73). Útil para nicho
    # SUBS_AUTO (vídeos no 9:16) donde quieres controlar márgenes laterales.
    "max_width_pct": None,
}


def _resolve_highlight_mode(s: dict) -> str:
    """Resuelve el modo de highlight respetando legacy `pill_enabled`.
    Si highlight_mode está fijado explícitamente, gana. Si no, deriva del legacy.
    """
    mode = s.get("highlight_mode")
    if mode:
        return mode
    return "pill" if s.get("pill_enabled", True) else "none"


def _apply_case(text: str, case_mode: str) -> str:
    if case_mode == "UPPERCASE":
        return text.upper()
    if case_mode == "lowercase":
        return text.lower()
    if case_mode == "Title Case":
        return text.title()
    return text  # "original"


def _load_font(font_path: str, size: int):
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        for fallback in [
            r"C:\Windows\Fonts\impact.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\arial.ttf",
        ]:
            if os.path.exists(fallback):
                try:
                    return ImageFont.truetype(fallback, size)
                except Exception:
                    continue
        return ImageFont.load_default()


def _measure_word(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def render_chunk_image(
    chunk_words: list[dict],
    highlight_idx: int,
    style: dict,
    video_size: tuple[int, int],
) -> Image.Image:
    """Renderiza un frame PNG-RGBA con las palabras del chunk, resaltando highlight_idx.

    Usa anchor='lt' (top-left del glifo visible) para que la píldora se pinte
    exactamente sobre la caja real de cada palabra, sin dejar huecos vacíos.
    """
    W, H = video_size
    s = {**DEFAULT_STYLE, **style}

    font_size = max(16, int(H * s["font_scale"]))
    font = _load_font(s["font_path"], font_size)
    stroke_w = s["stroke_width"]

    tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tmp)

    words_display = [_apply_case(w["word"], s["case_mode"]) for w in chunk_words]

    # Ancho de espacio: advance width del font × multiplicador configurable.
    # Sin el multiplicador las palabras quedan muy separadas (sobre todo en fuentes anchas).
    space_mul = s.get("word_spacing_multiplier", 0.65)
    space_w = max(1, int(font.getlength(" ") * space_mul))

    # line_h uniforme basado en "Mg" (cubre cap_height + descender → altura máxima posible).
    probe_bbox = draw.textbbox((0, 0), "Mg", font=font, anchor="lt", stroke_width=stroke_w)
    line_h = probe_bbox[3] - probe_bbox[1]

    # Medir cada palabra (ancho horizontal real)
    word_widths: list[int] = []
    for w in words_display:
        bb = draw.textbbox((0, 0), w, font=font, anchor="lt", stroke_width=stroke_w)
        word_widths.append(bb[2] - bb[0])

    line_spacing = int(H * s["line_spacing_pct"])
    pad_x = int(W * s["pill_pad_x_pct"])
    pad_y = int(H * s["pill_pad_y_pct"])

    # Wrap a líneas. max_width_pct prevalece si está; si no, zona segura TikTok.
    _mw_pct = s.get("max_width_pct")
    if _mw_pct is None:
        _mw_pct = TIKTOK_SAFE_X[1] - TIKTOK_SAFE_X[0]
    _mw_pct = max(0.20, min(1.0, float(_mw_pct)))
    max_line_w = int(W * _mw_pct - pad_x * 4)
    lines: list[list[tuple[int, str, int]]] = []
    current: list[tuple[int, str, int]] = []
    current_w = 0
    for i, w in enumerate(words_display):
        add_w = word_widths[i] + (space_w if current else 0)
        if current and current_w + add_w > max_line_w:
            lines.append(current)
            current = []
            current_w = 0
            add_w = word_widths[i]
        current.append((i, w, word_widths[i]))
        current_w += add_w
    if current:
        lines.append(current)

    if len(lines) > 2:
        flat = [entry for line in lines for entry in line]
        half = len(flat) // 2
        lines = [flat[:half], flat[half:]]

    # Cada row reserva line_h + padding píldora arriba y abajo.
    row_h = line_h + 2 * pad_y
    total_h = len(lines) * row_h + max(0, len(lines) - 1) * line_spacing + pad_y * 2
    canvas = Image.new("RGBA", (W, total_h), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(canvas)

    mode = _resolve_highlight_mode(s)

    y = pad_y * 2
    for line in lines:
        line_text_w = sum(w[2] for w in line) + space_w * (len(line) - 1)
        x = (W - line_text_w) // 2

        for idx, word_text, ww in line:
            is_active = (idx == highlight_idx)
            actual = cdraw.textbbox((x, y), word_text, font=font, anchor="lt", stroke_width=stroke_w)

            # ─── Capa BAJO el texto: pill / box_outline / glow ───
            if is_active and mode == "pill":
                cdraw.rounded_rectangle(
                    [actual[0] - pad_x, actual[1] - pad_y,
                     actual[2] + pad_x, actual[3] + pad_y],
                    radius=s["pill_radius"],
                    fill=s["highlight_color"],
                )
            elif is_active and mode == "box_outline":
                cdraw.rounded_rectangle(
                    [actual[0] - pad_x, actual[1] - pad_y,
                     actual[2] + pad_x, actual[3] + pad_y],
                    radius=s["pill_radius"],
                    outline=s["highlight_color"],
                    width=max(2, stroke_w + 2),
                )
            elif is_active and mode == "glow":
                # Capa aparte con stroke MUY grueso del highlight_color → blur Gaussiano
                glow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                gdraw = ImageDraw.Draw(glow_layer)
                glow_stroke = max(stroke_w + 8, int(font_size * 0.18))
                gdraw.text(
                    (x, y), word_text, font=font,
                    fill=s["highlight_color"],
                    stroke_width=glow_stroke,
                    stroke_fill=s["highlight_color"],
                    anchor="lt",
                )
                glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=max(4, font_size // 12)))
                canvas.alpha_composite(glow_layer)

            # ─── Texto principal (color depende del modo) ───
            # Override por palabra: si chunk_words[idx] trae 'color', se respeta
            # (lo usa el nicho Pronósticos para pintar de verde el texto del pick
            # y la cifra del bote — ver src/pronosticos/pick_locator.py).
            per_word_color = chunk_words[idx].get("color") if idx < len(chunk_words) else None
            if is_active and mode == "color_swap":
                text_fill = s["highlight_color"]
            elif per_word_color:
                text_fill = per_word_color
            else:
                text_fill = s["text_color"]
            cdraw.text(
                (x, y),
                word_text,
                font=font,
                fill=text_fill,
                stroke_width=stroke_w,
                stroke_fill=s["stroke_color"],
                anchor="lt",
            )

            # ─── Capa SOBRE el texto: underline ───
            if is_active and mode == "underline":
                ul_thick = max(3, int(font_size * 0.10))
                ul_y = actual[3] + max(2, pad_y // 2)
                cdraw.rounded_rectangle(
                    [actual[0] - 2, ul_y, actual[2] + 2, ul_y + ul_thick],
                    radius=ul_thick // 2,
                    fill=s["highlight_color"],
                )

            x += ww + space_w

        y += row_h + line_spacing

    return canvas


def render_preview_image(
    style: dict,
    sample_text: str = "MORE FRAGILE THAN EVER",
    highlight_word_index: int = 2,
    video_size: tuple[int, int] = (1080, 1920),
) -> Image.Image:
    """Devuelve una imagen RGBA lista para mostrar en Streamlit como preview del estilo.

    El tamaño del preview será del ancho del vídeo (escalado por Streamlit).
    """
    words = [{"word": w, "start": 0.0, "end": 1.0} for w in sample_text.split()]
    if not words:
        words = [{"word": "PREVIEW", "start": 0.0, "end": 1.0}]
    idx = min(highlight_word_index, len(words) - 1)
    return render_chunk_image(words, idx, style, video_size)


# ---------------------------------------------------------------------
# Chunking y overlay en vídeo
# ---------------------------------------------------------------------

def _chunk_words(
    words: list[dict],
    max_words_per_chunk: int = 3,
    max_duration: float = 2.5,
    pause_threshold: float = 0.6,
) -> list[list[dict]]:
    """Agrupa palabras en chunks. Corta cuando se da CUALQUIERA de:
       - Se alcanza `max_words_per_chunk` palabras.
       - El chunk excede `max_duration` segundos desde su primera palabra.
       - Hay una pausa ≥ `pause_threshold` segundos entre palabras consecutivas
         (límite natural de frase: respeta el fraseo real del audio y evita
         que un chunk arrastre tras un silencio largo).
    """
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for w in words:
        if current:
            time_since_start = w["end"] - current[0]["start"]
            pause_before = w["start"] - current[-1]["end"]
            if (
                len(current) >= max_words_per_chunk
                or time_since_start > max_duration
                or pause_before > pause_threshold
            ):
                chunks.append(current)
                current = []
        current.append(w)
    if current:
        chunks.append(current)
    return chunks


def render_karaoke_on_video(
    video_path: str,
    words: list[dict],
    style: dict,
    output_path: str,
    log_callback=None,
) -> str:
    """Overlay de subtítulos karaoke sobre un vídeo existente.

    Para cada palabra genera un ImageClip con el chunk renderizado y la palabra destacada,
    colocado en la posición Y configurada dentro de la zona segura.
    """
    s = {**DEFAULT_STYLE, **style}
    y_pct = max(TIKTOK_SAFE_Y[0], min(TIKTOK_SAFE_Y[1], s["y_position_pct"]))

    video = VideoFileClip(video_path)
    W, H = video.size

    chunks = _chunk_words(words, max_words_per_chunk=s["max_words_per_chunk"])
    if log_callback:
        log_callback(f"🔤 {len(words)} palabras en {len(chunks)} chunks")

    overlays: list[ImageClip] = []
    video_duration = float(video.duration)

    for chunk_idx, chunk in enumerate(chunks):
        # Inicio del próximo chunk (para extender el último word y cubrir pausas)
        if chunk_idx + 1 < len(chunks):
            next_chunk_start = chunks[chunk_idx + 1][0]["start"]
        else:
            # Último chunk: extender hasta el final del vídeo
            next_chunk_start = video_duration

        for i, word in enumerate(chunk):
            img = render_chunk_image(chunk, i, s, (W, H))
            arr = np.array(img)
            clip = ImageClip(arr, transparent=True)

            # Posición vertical: centro del chunk en y_pct del frame
            chunk_h = arr.shape[0]
            y_center_px = int(H * y_pct)
            y_top_px = y_center_px - chunk_h // 2
            y_top_px = max(0, min(H - chunk_h, y_top_px))

            # Duración inteligente para evitar huecos entre palabras y cubrir pausas:
            #  - Palabra intermedia: termina cuando empieza la siguiente palabra del chunk.
            #  - Última palabra del chunk: termina cuando empieza el siguiente chunk
            #    (así la frase NO desaparece durante pausas en el audio).
            word_start = word["start"]
            if i + 1 < len(chunk):
                word_end_display = chunk[i + 1]["start"]
            else:
                word_end_display = next_chunk_start

            dur = max(0.05, word_end_display - word_start)
            clip = (
                clip.set_start(word_start)
                .set_duration(dur)
                .set_position(("center", y_top_px))
            )
            overlays.append(clip)

    if log_callback:
        log_callback(f"🎞️ Componiendo overlay con {len(overlays)} sub-clips...")

    final = CompositeVideoClip([video] + overlays, size=(W, H))

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
