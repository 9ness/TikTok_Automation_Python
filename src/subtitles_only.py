"""Nicho 4 — Subtítulos automáticos sobre vídeo input.

Pipeline:
1. Usuario sube vídeo (.mp4/.mov/.webm) — cualquier aspect ratio.
2. Se extrae el audio (mp3 temporal).
3. faster-whisper transcribe palabra-a-palabra.
   - Modo "ear-only": Whisper escucha el audio sin pista.
   - Modo "guion ref.": el guion/letra se pasa como `initial_prompt` para
     guiar a Whisper (mejora vocabulario raro, nombres propios, letras de canción).
4. Se overlay-an subtítulos karaoke palabra-a-palabra (mismo motor que Presidentes).
5. Render con calidad seleccionable (codec + crf + preset).

NO depende de Redis ni de assets externos. Reutiliza `src/subtitles.py` para el render.
"""

from __future__ import annotations

from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
import numpy as np


# ---------------------------------------------------------------------
# Audio extraction
# ---------------------------------------------------------------------

def extract_audio_from_video(video_path: str, output_audio_path: str) -> str:
    """Extrae la pista de audio de un vídeo a MP3 (mono o estéreo, lo que tenga)."""
    clip = VideoFileClip(video_path)
    if clip.audio is None:
        clip.close()
        raise ValueError("El vídeo no tiene pista de audio.")
    clip.audio.write_audiofile(output_audio_path, logger=None)
    clip.close()
    return output_audio_path


# ---------------------------------------------------------------------
# Transcription with optional reference script (initial_prompt)
# ---------------------------------------------------------------------

def transcribe_with_reference(
    audio_path: str,
    reference_script: str | None = None,
    model_size: str = "base",
    language: str | None = None,
    audio_type: str = "speech",
) -> list[dict]:
    """Transcribe audio con faster-whisper.

    Args:
        audio_path: ruta al MP3/WAV.
        reference_script: si se pasa, se usa como `initial_prompt` (máx ~224
            tokens internos) para sesgar a Whisper hacia el vocabulario esperado.
        model_size: "tiny" | "base" | "small" | "medium" | "large-v3".
        language: ISO-639-1 ("es", "en", "fr"...). None = auto-detect.
        audio_type:
            - "speech": VAD ON con silencios ≥2s (default real de faster-whisper),
              `condition_on_previous_text=True`. Bueno para podcasts, voz hablada.
            - "music": VAD OFF + `condition_on_previous_text=False`. CRUCIAL para
              canciones: el VAD agresivo trata interludios como silencio y corta
              la transcripción a mitad de la canción; el condicionamiento previo
              hace que Whisper se atasque si pierde el hilo en un puente musical.

    Returns:
        Lista de dicts {word, start, end} con timestamps por palabra.
    """
    from src.subtitles import _get_whisper_model, _clean_whisper_tokens

    model = _get_whisper_model(model_size)
    is_music = (audio_type == "music")

    transcribe_kwargs: dict = {
        "word_timestamps": True,
        "language": language,
        "vad_filter": not is_music,
        "condition_on_previous_text": not is_music,
    }
    if not is_music:
        # Default real de faster-whisper. Antes tenía 300ms, demasiado agresivo
        # → cortaba canciones a las primeras estrofas.
        transcribe_kwargs["vad_parameters"] = {"min_silence_duration_ms": 2000}

    if reference_script and reference_script.strip():
        # initial_prompt acepta como contexto previo. Si la letra es muy larga,
        # cortamos a 1000 chars (Whisper trunca internamente a ~224 tokens).
        transcribe_kwargs["initial_prompt"] = reference_script.strip()[:1000]

    segments, _info = model.transcribe(audio_path, **transcribe_kwargs)
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
# Render: overlay karaoke conservando la resolución original del vídeo
# ---------------------------------------------------------------------

# Mapping de la 'Calidad' del sidebar (compartida con el resto de nichos) a
# la combinación ffmpeg `preset + crf` y al cap de altura. Etiquetas idénticas
# a las de res_options en main.py.
QUALITY_FROM_SIDEBAR = {
    "1080p (Lento)":       {"preset": "slow",      "crf": 18, "max_long_side": 1920},
    "720p (Medio)":        {"preset": "medium",    "crf": 20, "max_long_side": 1280},
    "480p (Rápido)":       {"preset": "fast",      "crf": 23, "max_long_side": 854},
    "240p (Ultra Rápido)": {"preset": "ultrafast", "crf": 28, "max_long_side": 426},
}


# ---------------------------------------------------------------------
# Fuentes disponibles (TTF instalados en Windows por defecto)
# ---------------------------------------------------------------------
FONT_OPTIONS = {
    "Impact (TikTok default)": r"C:\Windows\Fonts\impact.ttf",
    "Arial Black (heavy bold)": r"C:\Windows\Fonts\ariblk.ttf",
    "Bahnschrift (modern condensed)": r"C:\Windows\Fonts\bahnschrift.ttf",
    "Comic Sans Bold (memes)": r"C:\Windows\Fonts\comicbd.ttf",
    "Verdana Bold (clean)": r"C:\Windows\Fonts\verdanab.ttf",
    "Tahoma Bold": r"C:\Windows\Fonts\tahomabd.ttf",
    "Trebuchet MS Bold": r"C:\Windows\Fonts\trebucbd.ttf",
    "Georgia Bold (serif)": r"C:\Windows\Fonts\georgiab.ttf",
    "Rockwell Extra Bold (slab)": r"C:\Windows\Fonts\ROCKEB.TTF",
    "Consolas Bold (mono)": r"C:\Windows\Fonts\consolab.ttf",
}

# ---------------------------------------------------------------------
# Modos de marcar la palabra activa (highlight_mode)
# ---------------------------------------------------------------------
HIGHLIGHT_MODES = {
    "🔴 Píldora rellena (default)": "pill",
    "🎨 Color swap (cambia color)":  "color_swap",
    "📏 Subrayado":                  "underline",
    "🟦 Recuadro hueco":             "box_outline",
    "💫 Glow (halo difuminado)":      "glow",
    "⚪ Sin marca":                   "none",
}

# ---------------------------------------------------------------------
# Presets de estilo (botones rápidos en la UI)
# ---------------------------------------------------------------------
# Mezclan fuente + modo de highlight + colores + tamaño/posición.
# Cada preset es una combinación distinta de los 3 ejes — no solo cambia color.
STYLE_PRESETS = {
    "🔴 TikTok Classic (Impact + píldora)": {
        "font_path": FONT_OPTIONS["Impact (TikTok default)"],
        "highlight_mode": "pill",
        "highlight_color": "#BB0808", "text_color": "#FFFFFF",
        "stroke_color": "#000000", "stroke_width": 3, "case_mode": "UPPERCASE",
        "font_scale": 0.045, "max_words_per_chunk": 3, "pill_enabled": True,
        "y_position_pct": 0.78,
    },
    "🎤 Karaoke Color Swap (Arial Black)": {
        # Cambia el color de la palabra activa, sin fondo. Estilo karaoke clásico.
        "font_path": FONT_OPTIONS["Arial Black (heavy bold)"],
        "highlight_mode": "color_swap",
        "highlight_color": "#FDE047", "text_color": "#FFFFFF",
        "stroke_color": "#000000", "stroke_width": 4, "case_mode": "UPPERCASE",
        "font_scale": 0.050, "max_words_per_chunk": 4, "pill_enabled": True,
        "y_position_pct": 0.78,
    },
    "📏 Underline News (Bahnschrift)": {
        # Subrayado deportivo limpio, fuente moderna condensed
        "font_path": FONT_OPTIONS["Bahnschrift (modern condensed)"],
        "highlight_mode": "underline",
        "highlight_color": "#EF4444", "text_color": "#FFFFFF",
        "stroke_color": "#000000", "stroke_width": 2, "case_mode": "Title Case",
        "font_scale": 0.045, "max_words_per_chunk": 5, "pill_enabled": True,
        "y_position_pct": 0.85,
    },
    "🟦 Box Outline (Impact)": {
        # Recuadro hueco cyan alrededor de la palabra activa
        "font_path": FONT_OPTIONS["Impact (TikTok default)"],
        "highlight_mode": "box_outline",
        "highlight_color": "#22D3EE", "text_color": "#FFFFFF",
        "stroke_color": "#000000", "stroke_width": 3, "case_mode": "UPPERCASE",
        "font_scale": 0.045, "max_words_per_chunk": 3, "pill_enabled": True,
        "y_position_pct": 0.78,
    },
    "💫 Neon Glow (Impact halo)": {
        # Halo difuminado cyan alrededor de la palabra activa
        "font_path": FONT_OPTIONS["Impact (TikTok default)"],
        "highlight_mode": "glow",
        "highlight_color": "#22D3EE", "text_color": "#FFFFFF",
        "stroke_color": "#000814", "stroke_width": 2, "case_mode": "UPPERCASE",
        "font_scale": 0.052, "max_words_per_chunk": 3, "pill_enabled": True,
        "y_position_pct": 0.50,
    },
    "🎮 Comic Pop (rosa)": {
        # Comic Sans + píldora rosa fluo, vibe meme/pop
        "font_path": FONT_OPTIONS["Comic Sans Bold (memes)"],
        "highlight_mode": "pill",
        "highlight_color": "#FF1493", "text_color": "#FFFFFF",
        "stroke_color": "#000000", "stroke_width": 4, "case_mode": "UPPERCASE",
        "font_scale": 0.048, "max_words_per_chunk": 3, "pill_enabled": True,
        "y_position_pct": 0.78,
    },
    "⚽ Stadium Yellow (Impact swap)": {
        # Amarillo deportivo con color swap (la palabra activa cambia a amarillo)
        "font_path": FONT_OPTIONS["Impact (TikTok default)"],
        "highlight_mode": "color_swap",
        "highlight_color": "#FDD002", "text_color": "#FFFFFF",
        "stroke_color": "#000000", "stroke_width": 5, "case_mode": "UPPERCASE",
        "font_scale": 0.058, "max_words_per_chunk": 3, "pill_enabled": True,
        "y_position_pct": 0.78,
    },
    "🟫 Slab Heritage (Rockwell)": {
        # Fuente slab serif (Rockwell Extra Bold) + glow blanco — vibe documental retro
        "font_path": FONT_OPTIONS["Rockwell Extra Bold (slab)"],
        "highlight_mode": "underline",
        "highlight_color": "#FFFFFF", "text_color": "#FFFFFF",
        "stroke_color": "#000000", "stroke_width": 4, "case_mode": "UPPERCASE",
        "font_scale": 0.045, "max_words_per_chunk": 4, "pill_enabled": True,
        "y_position_pct": 0.78,
    },
    "📃 Phrase Static (sin marca por palabra)": {
        # SIN marca de palabra activa — la frase entera aparece estática.
        # Tolerante a desfases: como nada cambia dentro del chunk, el ojo no
        # detecta micro-desincronizaciones de Whisper. Recomendado para
        # canciones donde la sincronía exacta es difícil.
        "font_path": FONT_OPTIONS["Impact (TikTok default)"],
        "highlight_mode": "none",
        "highlight_color": "#FFFFFF", "text_color": "#FFFFFF",
        "stroke_color": "#000000", "stroke_width": 4, "case_mode": "UPPERCASE",
        "font_scale": 0.050, "max_words_per_chunk": 4, "pill_enabled": True,
        "y_position_pct": 0.78,
    },
}


def render_video_frame_with_subtitle(
    video_path: str,
    style: dict,
    sample_text: str = "PRUEBA DE SUBTITULO",
    highlight_word_index: int = 1,
    frame_time: float = 1.0,
    draw_width_guides: bool = False,
):
    """Devuelve un PIL.Image RGB con un frame del vídeo + el subtítulo de muestra
    overlay-eado en la posición/estilo configurados. Sirve de WYSIWYG en la UI.

    Si `draw_width_guides=True`, dibuja dos líneas amarillas verticales que
    marcan los límites laterales del `max_width_pct` configurado.
    """
    import cv2
    from PIL import Image, ImageDraw
    from src.subtitles import DEFAULT_STYLE, render_chunk_image

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1
    target_frame = int(max(0, min(total_frames - 1, frame_time * fps)))
    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    ret, frame = cap.read()
    if not ret:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise ValueError("No se pudo leer ningún frame del vídeo.")

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    base = Image.fromarray(frame_rgb).convert("RGBA")
    W, H = base.size

    s = {**DEFAULT_STYLE, **style}
    all_words = [{"word": w, "start": 0.0, "end": 1.0} for w in (sample_text or "PREVIEW").split()]
    if not all_words:
        return base.convert("RGB")

    # Respetar max_words_per_chunk: el preview muestra exactamente lo que vería
    # el usuario en pantalla en un instante (un chunk, no toda la frase).
    max_w = max(1, int(s.get("max_words_per_chunk", 4)))
    idx_global = max(0, min(highlight_word_index, len(all_words) - 1))
    chunk_start = (idx_global // max_w) * max_w
    chunk_words = all_words[chunk_start: chunk_start + max_w]
    idx_in_chunk = idx_global - chunk_start

    sub_canvas = render_chunk_image(chunk_words, idx_in_chunk, s, (W, H))

    y_pct = max(0.02, min(0.98, s["y_position_pct"]))
    sub_h = sub_canvas.size[1]
    y_top = int(H * y_pct) - sub_h // 2
    y_top = max(0, min(H - sub_h, y_top))

    base.alpha_composite(sub_canvas, (0, y_top))

    # Guías visuales del ancho máximo (líneas verticales en los márgenes)
    if draw_width_guides:
        mw_pct = s.get("max_width_pct")
        if mw_pct is None:
            mw_pct = 0.73  # default legacy zona segura TikTok
        mw_pct = max(0.20, min(1.0, float(mw_pct)))
        margin_px = int(W * (1.0 - mw_pct) / 2.0)
        line_w = max(3, W // 250)

        guide_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(guide_layer)
        guide_color = (255, 215, 0, 180)  # amarillo translúcido

        # Línea vertical izquierda + derecha (de arriba a abajo)
        gdraw.rectangle([margin_px, 0, margin_px + line_w, H], fill=guide_color)
        gdraw.rectangle([W - margin_px - line_w, 0, W - margin_px, H], fill=guide_color)

        # "Cornijas" horizontales para que sean más visibles
        cap_h = max(line_w, 8)
        cap_len = int(W * 0.04)
        for y_anchor in (int(H * 0.05), int(H * 0.5), int(H * 0.95) - cap_h):
            gdraw.rectangle([margin_px, y_anchor, margin_px + cap_len, y_anchor + cap_h], fill=guide_color)
            gdraw.rectangle([W - margin_px - cap_len, y_anchor, W - margin_px, y_anchor + cap_h], fill=guide_color)

        base = Image.alpha_composite(base, guide_layer)

    return base.convert("RGB")


def _normalize_word_for_match(w: str) -> str:
    """Normaliza una palabra para la comparación de alineación: lowercase + sin puntuación."""
    import re
    return re.sub(r"[^\w]", "", (w or "").lower())


def merge_edited_text_with_timings(
    edited_text: str,
    original_words: list[dict],
) -> list[dict]:
    """Fusiona el texto editado con los timestamps de Whisper de forma INTELIGENTE
    usando alineación de secuencias (difflib.SequenceMatcher).

    Estrategia:
      1. **Palabras que coinciden** (mismo texto, ignorando case + puntuación) →
         conservan su timestamp ORIGINAL EXACTO.
      2. **Palabras sustituidas 1:1** (typo fix tipo 'arano'→'araño') → conservan
         el timestamp de la palabra original que reemplazaron.
      3. **Palabras INSERTADAS** (añadidas, sin equivalente en el original) →
         se interpolan UNIFORMEMENTE en el hueco entre sus vecinas matched.
      4. **Palabras ELIMINADAS** → desaparecen sin afectar a las demás.

    Esto evita el desfase progresivo del enfoque ingenuo (distribuir todo
    uniformemente cuando difiere el número de palabras).

    Args:
        edited_text: texto editado por el usuario (palabras separadas por espacio).
        original_words: salida de Whisper con {word, start, end}.

    Returns:
        Lista nueva de {word, start, end}.
    """
    import difflib

    if not original_words:
        return []
    new_words = [w for w in (edited_text or "").split() if w.strip()]
    if not new_words:
        return list(original_words)

    # Fast path: mismo número → match 1:1 directo (no requiere alineación)
    if len(new_words) == len(original_words):
        return [
            {"word": new_words[i], "start": float(ow["start"]), "end": float(ow["end"])}
            for i, ow in enumerate(original_words)
        ]

    # Alineación con SequenceMatcher sobre versiones normalizadas
    orig_norm = [_normalize_word_for_match(w["word"]) for w in original_words]
    new_norm = [_normalize_word_for_match(w) for w in new_words]
    matcher = difflib.SequenceMatcher(a=orig_norm, b=new_norm, autojunk=False)

    # mapping[j] = índice en original_words al que se alinea new_words[j], o None si insertado
    mapping: list[int | None] = [None] * len(new_words)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                mapping[j1 + k] = i1 + k
        elif tag == "replace" and (i2 - i1) == (j2 - j1):
            # Sustitución 1:1 (typo fix) → preserva timestamp del original
            for k in range(i2 - i1):
                mapping[j1 + k] = i1 + k
        # 'insert', 'delete' y 'replace' con cardinalidades distintas → quedan None
        # (las inserciones se interpolarán; las deleciones simplemente se omiten)

    # Construir output con timestamps preservados o marcados para interpolar
    out: list[dict] = []
    for j, w in enumerate(new_words):
        idx = mapping[j]
        if idx is not None:
            ow = original_words[idx]
            out.append({"word": w, "start": float(ow["start"]), "end": float(ow["end"])})
        else:
            out.append({"word": w, "start": None, "end": None})  # marcador

    # Interpolación de palabras insertadas: por runs consecutivos.
    # REGLA CLAVE: nunca modificar el timestamp de una palabra matched.
    # Las inserciones se acomodan en el hueco [prev_end, next_start). Si no hay
    # hueco real (Whisper puso las palabras back-to-back), se apilan con micro-
    # incrementos en el instante del límite — aparecerán brevemente, pero el
    # resto de la canción mantiene su sincronía exacta.
    n = len(out)
    audio_t0 = float(original_words[0]["start"])
    audio_t1 = float(original_words[-1]["end"])
    i = 0
    while i < n:
        if out[i]["start"] is not None:
            i += 1
            continue
        # Run de inserciones [run_start, run_end)
        run_start = i
        while i < n and out[i]["start"] is None:
            i += 1
        run_end = i
        run_len = run_end - run_start

        # Anclajes temporales — extraídos de palabras matched o del rango de audio.
        prev_end = float(out[run_start - 1]["end"]) if run_start > 0 else audio_t0
        if run_end < n:
            next_start = float(out[run_end]["start"])
        else:
            # Inserciones al final (después de la última matched): permitimos
            # extender hasta audio_t1, o un poco más si hace falta. Esto es
            # seguro porque NO hay siguiente matched que se vaya a desincronizar.
            next_start = max(prev_end + run_len * 0.3, audio_t1)

        gap = next_start - prev_end
        if gap > 0.01:
            # Distribución uniforme en el hueco real
            each = gap / run_len
            for k in range(run_len):
                s = prev_end + each * k
                e = prev_end + each * (k + 1)
                out[run_start + k] = {
                    "word": out[run_start + k]["word"],
                    "start": s,
                    "end": e,
                }
        else:
            # Sin hueco real: apilar en el límite con micro-incrementos.
            # Aparecerán brevemente pero NO desplazan la siguiente palabra matched,
            # que mantiene su timestamp exacto y por tanto su sincronía con el audio.
            for k in range(run_len):
                s = prev_end + k * 0.001
                e = s + 0.001
                out[run_start + k] = {
                    "word": out[run_start + k]["word"],
                    "start": s,
                    "end": e,
                }

    return out


def get_video_duration(video_path: str) -> float:
    """Devuelve la duración del vídeo en segundos (o 0.0 si falla)."""
    import cv2
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    if fps <= 0 or frames <= 0:
        return 0.0
    return float(frames / fps)


def render_subtitles_on_video(
    video_path: str,
    words: list[dict],
    style: dict,
    output_path: str,
    quality_settings: dict | None = None,
    log_callback=None,
    logger=None,
) -> str:
    """Compone los subtítulos karaoke sobre el vídeo y exporta.

    `quality_settings` espera dict con keys: preset, crf, max_long_side.
    Si `max_long_side` es menor que el lado largo del vídeo, se downscalea
    proporcionalmente (nunca upscale). Si es None, conserva resolución original.
    """
    from src.subtitles import (
        DEFAULT_STYLE,
        render_chunk_image,
        _chunk_words,
        _resolve_highlight_mode,
    )

    if quality_settings is None:
        quality_settings = {"preset": "medium", "crf": 20, "max_long_side": None}

    s = {**DEFAULT_STYLE, **style}
    mode = _resolve_highlight_mode(s)
    # En este nicho la zona segura TikTok es opcional: si el usuario sube un vídeo
    # 16:9 / 1:1 quizá quiera subs muy abajo. Permitimos rango más amplio (0.02–0.98)
    # pero clampeamos para no salirse del frame.
    y_pct = max(0.02, min(0.98, s["y_position_pct"]))

    video = VideoFileClip(video_path)
    W, H = video.size

    # Downscale si excede el cap (no upscale)
    cap_long = quality_settings.get("max_long_side")
    if cap_long and max(W, H) > cap_long:
        scale = cap_long / max(W, H)
        new_w = int(W * scale)
        new_h = int(H * scale)
        if new_w % 2 != 0: new_w -= 1
        if new_h % 2 != 0: new_h -= 1
        video = video.resize(newsize=(new_w, new_h))
        W, H = new_w, new_h
        if log_callback:
            log_callback(f"📐 Downscale a {W}x{H} (cap {cap_long}px lado largo)")

    chunks = _chunk_words(words, max_words_per_chunk=s["max_words_per_chunk"])
    if log_callback:
        log_callback(f"🔤 {len(words)} palabras en {len(chunks)} chunks")

    # Offset global de sincronización (en ms): negativo = adelantar el highlight,
    # positivo = retrasarlo. Compensa el sesgo típico de Whisper en canciones
    # (palabras estimadas 100-300ms antes de su pronunciación real).
    sync_offset = float(s.get("sync_offset_ms", 0)) / 1000.0

    overlays: list[ImageClip] = []
    video_duration = float(video.duration)

    for chunk_idx, chunk in enumerate(chunks):
        if chunk_idx + 1 < len(chunks):
            next_chunk_start = chunks[chunk_idx + 1][0]["start"]
        else:
            next_chunk_start = video_duration

        if mode == "none":
            # 1 imagen estática por chunk → cero transiciones por palabra.
            # Más rápido y, sobre todo, hace invisible cualquier micro-desfase
            # de Whisper en palabras concretas: como nada cambia dentro del
            # chunk, el ojo no tiene referencia para detectar el desfase.
            img = render_chunk_image(chunk, -1, s, (W, H))  # idx=-1 → ninguna activa
            arr = np.array(img)
            clip = ImageClip(arr, transparent=True)

            chunk_h = arr.shape[0]
            y_center_px = int(H * y_pct)
            y_top_px = y_center_px - chunk_h // 2
            y_top_px = max(0, min(H - chunk_h, y_top_px))

            chunk_start = chunk[0]["start"] + sync_offset
            chunk_end = next_chunk_start + sync_offset
            chunk_start = max(0.0, min(video_duration - 0.05, chunk_start))
            chunk_end = max(chunk_start + 0.05, min(video_duration, chunk_end))

            clip = (
                clip.set_start(chunk_start)
                .set_duration(chunk_end - chunk_start)
                .set_position(("center", y_top_px))
            )
            overlays.append(clip)
            continue

        # Modo con highlight per-palabra: 1 imagen por palabra.
        for i, word in enumerate(chunk):
            img = render_chunk_image(chunk, i, s, (W, H))
            arr = np.array(img)
            clip = ImageClip(arr, transparent=True)

            chunk_h = arr.shape[0]
            y_center_px = int(H * y_pct)
            y_top_px = y_center_px - chunk_h // 2
            y_top_px = max(0, min(H - chunk_h, y_top_px))

            word_start = word["start"] + sync_offset
            if i + 1 < len(chunk):
                word_end_display = chunk[i + 1]["start"] + sync_offset
            else:
                word_end_display = next_chunk_start + sync_offset

            # Clamp para no salirse de la duración del vídeo
            word_start = max(0.0, min(video_duration - 0.05, word_start))
            word_end_display = max(word_start + 0.05, min(video_duration, word_end_display))

            dur = max(0.05, word_end_display - word_start)
            clip = (
                clip.set_start(word_start)
                .set_duration(dur)
                .set_position(("center", y_top_px))
            )
            overlays.append(clip)

    if log_callback:
        log_callback(f"🎞️ Componiendo {len(overlays)} sub-clips sobre {W}x{H}…")

    final = CompositeVideoClip([video] + overlays, size=(W, H))

    ffmpeg_extra = ["-pix_fmt", "yuv420p", "-crf", str(quality_settings.get("crf", 20))]

    final.write_videofile(
        output_path,
        fps=video.fps,
        codec="libx264",
        audio_codec="aac",
        preset=quality_settings.get("preset", "medium"),
        threads=8,
        logger=logger,
        ffmpeg_params=ffmpeg_extra,
    )
    video.close()
    return output_path
