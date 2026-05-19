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
    progress_callback=None,
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
            - "tts": VAD OFF + `condition_on_previous_text=True`. Específico
              para audio TTS limpio (MiniMax, Eleven, etc.) — sabemos que el
              archivo entero es speech, no hay silencios reales. Con VAD on
              algunas voces TTS hacen que el VAD marque regiones como silencio
              erróneamente, descuadrando timestamps de los subs (subs aparecen
              después de que la voz ya está hablando).

    Returns:
        Lista de dicts {word, start, end} con timestamps por palabra.
    """
    from src.subtitles import _get_whisper_model, _clean_whisper_tokens

    model = _get_whisper_model(model_size)
    is_music = (audio_type == "music")
    is_tts = (audio_type == "tts")
    # VAD off cuando sabemos que TODO el audio es speech (música o TTS).
    vad_off = is_music or is_tts

    transcribe_kwargs: dict = {
        "word_timestamps": True,
        "language": language,
        "vad_filter": not vad_off,
        # TTS mantiene `condition_on_previous_text=True` para coherencia entre
        # chunks (todo el guion es una narración continua). Música lo desactiva
        # porque el VAD off + condicionamiento puede atascar a Whisper en bridges.
        "condition_on_previous_text": not is_music,
    }
    if not vad_off:
        # Default real de faster-whisper. Antes tenía 300ms, demasiado agresivo
        # → cortaba canciones a las primeras estrofas.
        transcribe_kwargs["vad_parameters"] = {"min_silence_duration_ms": 2000}

    if reference_script and reference_script.strip():
        # initial_prompt acepta como contexto previo. Si la letra es muy larga,
        # cortamos a 1000 chars (Whisper trunca internamente a ~224 tokens).
        transcribe_kwargs["initial_prompt"] = reference_script.strip()[:1000]

    segments, info = model.transcribe(audio_path, **transcribe_kwargs)
    total_duration = float(getattr(info, "duration", 0.0)) or 0.0

    raw_words: list[dict] = []
    import time as _time
    last_emit = 0.0
    for segment in segments:
        if getattr(segment, "words", None):
            for w in segment.words:
                text = (w.word or "").strip()
                if not text:
                    continue
                raw_words.append({"word": text, "start": float(w.start), "end": float(w.end)})

        # Reportar progreso ~cada 0.5s wallclock para no saturar el WS.
        # Mensaje minimalista: el cliente ya tiene su propio % + ETA, aquí
        # solo informamos del punto del audio en el que va Whisper. Sin
        # porcentajes ni ETAs duplicados.
        if progress_callback and total_duration > 0:
            now = _time.time()
            if now - last_emit >= 0.5:
                seg_end = float(getattr(segment, "end", 0.0))
                frac = max(0.0, min(1.0, seg_end / total_duration))
                msg = f"🎙️ Transcribiendo audio ({seg_end:.0f}s / {total_duration:.0f}s)"
                try:
                    progress_callback(frac, msg)
                except Exception:
                    pass
                last_emit = now

    if progress_callback:
        try:
            progress_callback(1.0, "🎙️ Transcripción completa")
        except Exception:
            pass

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
# Fuentes disponibles — derivado del registry universal del proyecto.
# Se mantiene el dict {label: path} para back-compat con los STYLE_PRESETS
# de abajo y con código que indexa por label fijo. Las claves siguen
# correspondiendo a las fuentes Windows estándar; las bundled adicionales
# (`assets/fonts/*.ttf`) aparecen en `GET /api/v1/fonts` aunque no estén
# aquí (los presets usan paths concretos; el selector pinta el registry).
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


_PHRASE_PAUSE_S = 0.30
_MAX_PHRASE_DUR_S = 6.0


def _split_original_into_phrases(
    original_words: list[dict],
    pause_threshold: float = _PHRASE_PAUSE_S,
    max_phrase_dur: float = _MAX_PHRASE_DUR_S,
) -> list[tuple[int, int]]:
    """Agrupa palabras originales en frases naturales separadas por pausas
    ≥ `pause_threshold` segundos. Devuelve una lista de (i_start, i_end_inclusive).

    Las pausas son las anclas temporales fiables tras una edición manual: dentro
    de una frase Whisper puede tener timestamps imprecisos (especialmente con
    audio_type=music), pero los huecos entre frases sí se corresponden con
    silencios reales del audio.

    Adicionalmente, **limita la duración máxima de cada frase** (`max_phrase_dur`)
    partiendo recursivamente por el hueco interno mayor. Esto previene el
    síntoma "subs congelados 4s + race de 3 frases en 1s" cuando Whisper no
    detecta ninguna pausa en un tramo largo (típico en canciones sin silencios
    o con voz continua sobre música)."""
    if not original_words:
        return []
    # Paso 1: split inicial por pausa explícita.
    raw: list[tuple[int, int]] = []
    start = 0
    for i in range(1, len(original_words)):
        gap = float(original_words[i]["start"]) - float(original_words[i - 1]["end"])
        if gap >= pause_threshold:
            raw.append((start, i - 1))
            start = i
    raw.append((start, len(original_words) - 1))

    # Paso 2: partir recursivamente frases > max_phrase_dur por su hueco mayor.
    def split_if_long(pi0: int, pi1: int) -> list[tuple[int, int]]:
        dur = float(original_words[pi1]["end"]) - float(original_words[pi0]["start"])
        if dur <= max_phrase_dur or pi1 - pi0 < 1:
            return [(pi0, pi1)]
        # Encontrar el hueco interno mayor (start[k] - end[k-1]).
        best_k = pi0 + 1
        best_gap = -1.0
        for k in range(pi0 + 1, pi1 + 1):
            gap = float(original_words[k]["start"]) - float(original_words[k - 1]["end"])
            if gap > best_gap:
                best_gap = gap
                best_k = k
        # Si el hueco mayor es despreciable, partir por la mitad (índice central)
        # para evitar bucle infinito en flujos sin silencios.
        if best_gap < 0.01:
            best_k = pi0 + (pi1 - pi0 + 1) // 2
            best_k = max(pi0 + 1, min(pi1, best_k))
        return split_if_long(pi0, best_k - 1) + split_if_long(best_k, pi1)

    phrases: list[tuple[int, int]] = []
    for pi0, pi1 in raw:
        phrases.extend(split_if_long(pi0, pi1))
    return phrases


def merge_edited_text_with_timings(
    edited_text: str,
    original_words: list[dict],
) -> list[dict]:
    """Fusiona el texto editado con los timestamps de Whisper, manteniendo la
    SINCRONÍA con el audio incluso cuando el usuario añade o elimina palabras.

    Estrategia (sin forced-alignment, sin reinvocar a Whisper):

      1. Detectar **frases naturales** en el original separadas por pausas
         ≥ 0.35s. Los límites de frase son las únicas anclas temporales que
         realmente se corresponden con silencios del audio.
      2. Alinear edited↔original con `difflib.SequenceMatcher` para mapear
         qué palabra editada cae en qué frase. El primer/último índice editado
         que se alinea dentro de la frase fija sus bordes; las palabras no
         alineadas (insertadas/eliminadas) se reparten al vecino más cercano.
      3. Dentro de cada frase, distribuir las palabras editadas con peso por
         **número de caracteres** sobre el rango [phrase_t0, phrase_t1].
         Esto da duraciones realistas (palabras largas → más tiempo) y
         elimina los micro-stacks de 1ms del enfoque anterior.

    Por qué el enfoque anterior fallaba con muchas inserciones:
      - Conservaba timestamps de palabras matched exactamente. Cuando entre
        dos palabras consecutivas no había hueco real, las inserciones se
        apilaban con incrementos de 1ms → los subtítulos "saltaban" varias
        palabras de golpe. Y si Whisper tenía drift dentro de una frase
        (común en modo music), el drift se acumulaba en los siguientes
        chunks → "se quedan congelados y después corren muy rápido".

    Args:
        edited_text: texto editado por el usuario (palabras separadas por espacio).
        original_words: salida de Whisper con {word, start, end}.

    Returns:
        Lista nueva de {word, start, end} totalmente sincronizada por frase.
    """
    import difflib

    if not original_words:
        return []
    new_words = [w for w in (edited_text or "").split() if w.strip()]
    if not new_words:
        return list(original_words)

    # Fast path: mismo número de palabras → match 1:1 (preserva timing exacto).
    if len(new_words) == len(original_words):
        return [
            {"word": new_words[i], "start": float(ow["start"]), "end": float(ow["end"])}
            for i, ow in enumerate(original_words)
        ]

    phrases = _split_original_into_phrases(original_words)

    # Mapeo original_idx → new_idx para anclas (matched o sustitución 1:1).
    orig_norm = [_normalize_word_for_match(w["word"]) for w in original_words]
    new_norm = [_normalize_word_for_match(w) for w in new_words]
    matcher = difflib.SequenceMatcher(a=orig_norm, b=new_norm, autojunk=False)
    o2n: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or (tag == "replace" and (i2 - i1) == (j2 - j1)):
            for k in range(i2 - i1):
                o2n[i1 + k] = j1 + k

    # Determinar el rango de new_words [nj0, nj1] que cae en cada frase.
    # Estrategia: para frase p, recoger anclas mapeadas dentro de [pi0, pi1];
    # usar min/max como pista. Las palabras editadas sin ancla (insertadas)
    # se asignan a la frase cuyo borde quede más cerca.
    n_new = len(new_words)
    phrase_anchors: list[tuple[int | None, int | None]] = []
    for pi0, pi1 in phrases:
        mapped = [o2n[i] for i in range(pi0, pi1 + 1) if i in o2n]
        if mapped:
            phrase_anchors.append((min(mapped), max(mapped)))
        else:
            phrase_anchors.append((None, None))

    # Fallback degenerado: si NO hay ninguna ancla (reescritura total),
    # repartir new_words entre frases en proporción a su duración de audio.
    if not o2n and len(phrases) > 1:
        phrase_durs = [
            float(original_words[pi1]["end"]) - float(original_words[pi0]["start"])
            for pi0, pi1 in phrases
        ]
        total_dur = sum(phrase_durs) or 1.0
        nj_cursor = 0
        for p_idx, dur in enumerate(phrase_durs):
            share = max(1, round(n_new * (dur / total_dur)))
            nj0 = nj_cursor
            nj1 = min(n_new - 1, nj_cursor + share - 1)
            if p_idx == len(phrase_durs) - 1:
                nj1 = n_new - 1
            phrase_anchors[p_idx] = (nj0, nj1)
            nj_cursor = nj1 + 1

    # Resolver rangos [nj0, nj1] cubriendo TODAS las new_words, sin huecos
    # ni solapes, respetando las anclas en el orden de las frases.
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for p_idx, (a0, a1) in enumerate(phrase_anchors):
        if p_idx == len(phrase_anchors) - 1:
            nj1 = n_new - 1
        else:
            # Buscar la primera ancla en frases posteriores para fijar el límite.
            next_anchor: int | None = None
            for q in range(p_idx + 1, len(phrase_anchors)):
                if phrase_anchors[q][0] is not None:
                    next_anchor = phrase_anchors[q][0]
                    break
            if next_anchor is not None:
                # Las palabras [cursor, next_anchor-1] caen entre esta frase y
                # la siguiente con ancla. Damos a esta frase su ancla derecha
                # (a1) si la tiene; si no, partimos el rango proporcionalmente
                # por número de frases sin anclas restantes.
                if a1 is not None:
                    nj1 = a1
                else:
                    # Repartir uniformemente hasta next_anchor entre frases
                    # consecutivas sin anclas.
                    unanchored_count = 1
                    for q in range(p_idx + 1, len(phrase_anchors)):
                        if phrase_anchors[q][0] is not None:
                            break
                        unanchored_count += 1
                    span = max(0, next_anchor - cursor)
                    nj1 = cursor + (span // unanchored_count) - 1
                    if nj1 < cursor:
                        nj1 = cursor  # garantiza ≥1 palabra
            else:
                # No quedan anclas → resto del rango actual hasta el final.
                nj1 = n_new - 1
        nj0 = cursor
        nj1 = max(nj0, min(nj1, n_new - 1))
        ranges.append((nj0, nj1))
        cursor = nj1 + 1
    # Si quedaron palabras sueltas al final (no debería, pero por seguridad),
    # añadirlas a la última frase.
    if cursor < n_new and ranges:
        last_pi = len(ranges) - 1
        ranges[last_pi] = (ranges[last_pi][0], n_new - 1)

    # Distribución por SUB-SEGMENTOS dentro de cada frase usando las palabras
    # matched como anclas internas. Esto preserva la sincronía exacta de las
    # palabras que Whisper SÍ acertó, y reparte las insertadas en los huecos
    # entre anclas con peso por carácter. Si un hueco es demasiado pequeño
    # para meter las inserciones (mín 80ms por palabra), absorbe el ancla
    # contigua y reparte sobre un sub-segmento más ancho. Así se mantiene
    # coordinación incluso con muchas inserciones.
    MIN_WORD_DUR = 0.08
    out: list[dict] = [None] * n_new  # type: ignore[list-item]

    # Mapeo inverso: new_idx → (orig_idx, orig_start, orig_end) para identificar
    # anclas dentro de cada frase.
    n2anchor: dict[int, tuple[float, float]] = {}
    for orig_idx, new_idx in o2n.items():
        ow = original_words[orig_idx]
        n2anchor[new_idx] = (float(ow["start"]), float(ow["end"]))

    for (pi0, pi1), (nj0, nj1) in zip(phrases, ranges):
        phrase_t0 = float(original_words[pi0]["start"])
        phrase_t1 = float(original_words[pi1]["end"])
        words_in_phrase = new_words[nj0:nj1 + 1]
        if not words_in_phrase:
            continue

        # Anclas dentro de la frase: lista ordenada de (new_idx_relativo, ts_start, ts_end).
        # Forzamos anclas virtuales en los extremos de la frase para acotar.
        local_anchors: list[tuple[int, float, float]] = []
        for j_local, _w in enumerate(words_in_phrase):
            j_global = nj0 + j_local
            if j_global in n2anchor:
                t_s, t_e = n2anchor[j_global]
                # Solo aceptar la ancla si su timestamp cae dentro del span de la
                # frase (sanity check ante mappings cross-frase ocasionales).
                if phrase_t0 - 0.05 <= t_s <= phrase_t1 + 0.05:
                    local_anchors.append((j_local, t_s, t_e))

        # Sub-segmentos: [(start_local, end_local_exclusive, t_start, t_end)].
        # Cada segmento va de una "frontera" (ancla o borde de frase) a la siguiente.
        boundaries: list[tuple[int, float]] = [(0, phrase_t0)]
        for j_local, t_s, _t_e in local_anchors:
            # El ancla j_local arranca en t_s (su start). El segmento previo
            # termina en t_s. El siguiente segmento empieza en t_s con la propia
            # palabra ancla incluida.
            boundaries.append((j_local, t_s))
        boundaries.append((len(words_in_phrase), phrase_t1))

        # Eliminar boundaries duplicadas en índice o en tiempo (raro pero seguro).
        cleaned: list[tuple[int, float]] = []
        for b in boundaries:
            if cleaned and cleaned[-1][0] == b[0]:
                continue
            cleaned.append(b)
        boundaries = cleaned

        # Merge greedy bidireccional: si un segmento tiene N palabras y
        # N*MIN_WORD_DUR > duración, absorber un vecino (siguiente si existe,
        # en su defecto el anterior). Se ejecuta hasta que todos los segmentos
        # quepan o solo quede el segmento-frase completo. Bidireccional para
        # cubrir el caso del ÚLTIMO segmento de la frase, que no tiene siguiente
        # con quien fusionarse.
        changed = True
        while changed and len(boundaries) > 2:
            changed = False
            for i in range(len(boundaries) - 1):
                s_idx, s_t = boundaries[i]
                e_idx, e_t = boundaries[i + 1]
                n_words = e_idx - s_idx
                dur = e_t - s_t
                if n_words > 0 and n_words * MIN_WORD_DUR > dur:
                    # Preferir absorber al siguiente (boundary i+1 interna).
                    if i + 1 < len(boundaries) - 1:
                        boundaries.pop(i + 1)
                    elif i > 0:
                        # Es el último segmento — absorber al anterior eliminando
                        # la boundary i (que pasa a unirse con el segmento previo).
                        boundaries.pop(i)
                    else:
                        # Solo queda 1 segmento (la frase entera) — no se puede merge.
                        break
                    changed = True
                    break

        # Distribuir dentro de cada sub-segmento: reservar primero MIN_WORD_DUR
        # para cada palabra (floor), después repartir el remanente char-weighted.
        # Si la duración total es menor que N*MIN_WORD_DUR (caso degenerado tras
        # merging exhaustivo), cae en distribución uniforme — peor que el ideal
        # pero al menos sin micro-stacks invisibles.
        for i in range(len(boundaries) - 1):
            s_idx, s_t = boundaries[i]
            e_idx, e_t = boundaries[i + 1]
            seg_words = words_in_phrase[s_idx:e_idx]
            if not seg_words:
                continue
            dur = max(0.05, e_t - s_t)
            n_seg = len(seg_words)
            floor_total = n_seg * MIN_WORD_DUR
            if dur >= floor_total:
                # Floor garantizado + remanente char-weighted.
                remaining = dur - floor_total
                weights = [len(w) + 1 for w in seg_words]
                total_w = sum(weights) or 1
                durs = [MIN_WORD_DUR + remaining * (weights[k] / total_w) for k in range(n_seg)]
            else:
                # Sin espacio ni para el floor → uniforme (último recurso).
                durs = [dur / n_seg] * n_seg
            t = s_t
            for k, w in enumerate(seg_words):
                out[nj0 + s_idx + k] = {"word": w, "start": t, "end": t + durs[k]}
                t += durs[k]

    # Defensive fill — no debería quedar ningún None.
    for j in range(n_new):
        if out[j] is None:
            prev_end = out[j - 1]["end"] if j > 0 and out[j - 1] else 0.0
            out[j] = {"word": new_words[j], "start": prev_end, "end": prev_end + 0.2}

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
    last_chunk_max_end: float | None = None,
) -> str:
    """Compone los subtítulos karaoke sobre el vídeo y exporta.

    `quality_settings` espera dict con keys: preset, crf, max_long_side.
    Si `max_long_side` es menor que el lado largo del vídeo, se downscalea
    proporcionalmente (nunca upscale). Si es None, conserva resolución original.

    `last_chunk_max_end`: si se pasa (segundos), el ÚLTIMO chunk no se
    extiende hasta `video_duration` sino hasta ese valor. Útil para nichos
    donde el audio acaba antes que el vídeo (Construcción POV: narración
    ~55s + cola silenciosa hasta 60s) y no queremos que la última palabra
    quede congelada en pantalla durante el silencio.
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
    # Para el último chunk: por defecto extiende hasta el fin del vídeo
    # (Pronósticos y Subs Auto necesitan esto). POV pasa `last_chunk_max_end`
    # para que el último sub no quede congelado en la cola silenciosa.
    last_end_cap = (
        min(float(last_chunk_max_end), video_duration)
        if last_chunk_max_end is not None
        else video_duration
    )

    for chunk_idx, chunk in enumerate(chunks):
        if chunk_idx + 1 < len(chunks):
            next_chunk_start = chunks[chunk_idx + 1][0]["start"]
        else:
            next_chunk_start = last_end_cap

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
