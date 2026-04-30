"""Orquestador del nicho 'Pronósticos Diarios' v2.

Cambio crítico vs v1: el guion YA viene hecho desde Redis (key
`daily_bets_tiktok_video:YYYY-MM`). Lo escribe un workflow separado en
bet-ai-master con OpenAI gpt-5.4 + datos verificables de API-Sports. Aquí
solo lo consumimos.

Pipeline:
  Redis (script) → TTS único (MiniMax) → Whisper (word_timings)
                → detección CTA "linkcito" → carruseles por pick
                → stock por equipo → composición MoviePy con perfil.png en CTA
                → MP4 vertical 9:16 con duración real del audio
"""

from __future__ import annotations

import json
import os
import random
import shutil
import tempfile
from datetime import date, timedelta
from typing import Callable

from moviepy.editor import (
    AudioFileClip, ColorClip, CompositeAudioClip, CompositeVideoClip, ImageClip,
    VideoFileClip,
)

from src import locutor

import numpy as np

from .carousel_renderer import render_pick_card
from .data_loader import get_picks, load_chosen_version, publish_video_url
from .league_overlay import (
    build_league_overlay_image, find_league_overlay_anchor, resolve_league_logos,
)
from .segment_locator import find_money_anchor, find_segments
from .stock_search import get_clips_pool, parse_match, search_clip


def _noop(_msg: str) -> None: ...


# Estilo de subtítulos específico del nicho Pronósticos:
# - Una palabra a la vez (max_words_per_chunk=1)
# - Sin píldora de fondo (pill_enabled=False) — solo texto blanco con borde negro grueso
# - Posición Y baja (78%) — replica el estilo del vídeo de referencia
# - Lowercase para tono coloquial/insider
PRONOSTICOS_SUB_STYLE = {
    "font_path": r"C:\Windows\Fonts\impact.ttf",
    "font_scale": 0.055,
    "text_color": "#FFFFFF",
    "stroke_color": "#000000",
    "stroke_width": 8,
    "pill_enabled": False,
    "case_mode": "lowercase",
    "max_words_per_chunk": 1,
    "y_position_pct": 0.78,
    "pill_radius": 10,
    "pill_pad_x_pct": 0.010,
    "pill_pad_y_pct": 0.005,
    "line_spacing_pct": 0.015,
    "word_spacing_multiplier": 0.65,
    "highlight_color": "#000000",   # ignorado al estar pill_enabled=False
}


def _tomorrow() -> str:
    return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")


def _resolve_asset(*relative_parts: str) -> str | None:
    """Localiza un asset dentro de BIBLIOTECA_PRONOSTICOS_CLIPS.

    Ej: `_resolve_asset("fotos", "perfil.png")` →
        {TIKTOK_ROOT_PATH}/BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/perfil.png
    """
    root = os.environ.get("TIKTOK_ROOT_PATH")
    if not root:
        return None
    folder = "BIBLIOTECA_PRONOSTICOS_CLIPS"
    cfg_path = os.path.join("config", "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
            folder = cfg.get("folder_structure", {}).get("pronosticos_clips_folder", folder)
        except Exception:
            pass
    candidate = os.path.join(root, folder, *relative_parts)
    return candidate if os.path.exists(candidate) else None


def _resolve_perfil_png() -> str | None:
    """Captura del perfil TikTok para el overlay del CTA midroll.

    Path canónico: BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/perfil.png
    """
    return _resolve_asset("fotos", "perfil.png")


def _resolve_background_music() -> str | None:
    """Localiza el archivo de música de fondo.

    Acepta varias ubicaciones para flexibilidad:
      - BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/fondo.mp3        (default — junto a SFX)
      - BIBLIOTECA_PRONOSTICOS_CLIPS/musica/fondo.mp3
      - BIBLIOTECA_PRONOSTICOS_CLIPS/bgm/fondo.mp3
      También acepta nombres `background.mp3` y `bgm.mp3`.
    """
    candidates = [
        ("sfx", "fondo.mp3"),
        ("sfx", "background.mp3"),
        ("sfx", "bgm.mp3"),
        ("musica", "fondo.mp3"),
        ("bgm", "fondo.mp3"),
    ]
    for parts in candidates:
        path = _resolve_asset(*parts)
        if path:
            return path
    return None


def _mix_background_music(audio_clip, bgm_path: str, volume: float,
                           audio_duration: float, log) -> "object":
    """Mezcla la BGM con el audio TTS bajo el volumen indicado.

    Recorta la BGM a la duración del audio + aplica fade-out de 0.5s al final
    para evitar corte abrupto.
    """
    try:
        bgm = AudioFileClip(bgm_path).volumex(volume)
        if bgm.duration > audio_duration:
            bgm = bgm.subclip(0, audio_duration)
        # Fade-out 0.5s al final (o lo que dure si la BGM es más corta)
        fade_dur = min(0.5, bgm.duration * 0.1)
        if fade_dur > 0.05:
            from moviepy.audio.fx.audio_fadeout import audio_fadeout
            bgm = bgm.fx(audio_fadeout, fade_dur)
        composed = (
            CompositeAudioClip([audio_clip, bgm])
            .set_duration(audio_duration)
        )
        log(f"🎵 Música de fondo: {os.path.basename(bgm_path)} mezclada al {volume*100:.0f}% "
            f"({bgm.duration:.1f}s)")
        return composed
    except Exception as e:
        log(f"⚠️ No se pudo mezclar la música de fondo: {e}")
        return audio_clip


def _resolve_sfx(*candidates: str) -> str | None:
    """Localiza un SFX dentro de BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/.

    Para cada candidato `name.mp3`, también prueba la variante `.wav`. Esto
    permite usar SFX sintetizados con numpy (sin dependencia de codec mp3).
    """
    for filename in candidates:
        path = _resolve_asset("sfx", filename)
        if path:
            return path
        # Intentar variante .wav del mismo nombre
        if filename.lower().endswith(".mp3"):
            wav_alt = filename[:-4] + ".wav"
            path = _resolve_asset("sfx", wav_alt)
            if path:
                return path
    return None


def _mix_sfx_at_timestamps(audio_clip, sfx_path: str, timestamps: list[float],
                           volume: float, audio_duration: float, log,
                           label: str = "SFX") -> "object":
    """Mezcla un SFX en cada timestamp dado y devuelve el audio compuesto.

    Si la lista está vacía o el sfx_path es None, devuelve audio_clip sin tocar.
    """
    if not sfx_path or not timestamps:
        return audio_clip
    try:
        sfx_layers = []
        for ts in timestamps:
            offset = max(0.0, ts - 0.05)  # 50ms de adelanto para sincronía perceptual
            if offset >= audio_duration:
                continue
            layer = AudioFileClip(sfx_path).volumex(volume).set_start(offset)
            sfx_layers.append(layer)
        if not sfx_layers:
            return audio_clip
        composed = (
            CompositeAudioClip([audio_clip] + sfx_layers)
            .set_duration(audio_duration)
        )
        log(f"🔊 {label}: mezclado en {len(sfx_layers)} momento(s) (vol={volume:.2f})")
        return composed
    except Exception as e:
        log(f"⚠️ No se pudo mezclar {label}: {e}")
        return audio_clip


def _apply_saturation(input_path: str, output_path: str, saturation: float,
                      log) -> bool:
    """Re-codifica el vídeo aplicando un filtro de saturación con ffmpeg.

    `saturation`: 1.0 = sin cambios, 1.2-1.4 = colores más vivos sin pasarse,
    >1.5 = exagerado (riesgo de "horneado").

    Devuelve True si tuvo éxito.
    """
    import subprocess
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"eq=saturation={saturation:.2f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            log(f"⚠️ ffmpeg saturación falló: {result.stderr[-300:]}")
            return False
        return True
    except Exception as e:
        log(f"⚠️ ffmpeg saturación excepción: {e}")
        return False


def _resize_cover(clip, W: int, H: int):
    if clip.h != H:
        clip = clip.resize(height=H)
    if clip.w > W:
        clip = clip.crop(x1=(clip.w - W) / 2, width=W, height=H)
    elif clip.w < W:
        clip = clip.resize(width=W)
        if clip.h > H:
            clip = clip.crop(y1=(clip.h - H) / 2, width=W, height=H)
    return clip


def _stock_visual(stock_path: str | None, duration: float, W: int, H: int):
    """Devuelve un VideoClip silente cubriendo `duration` (loop si hace falta)."""
    if not stock_path or not os.path.exists(stock_path):
        return ColorClip(size=(W, H), color=(8, 12, 28), duration=duration)
    try:
        v = VideoFileClip(stock_path).without_audio()
        v = _resize_cover(v, W, H)
        if v.duration < duration:
            from moviepy.editor import vfx
            v = v.fx(vfx.loop, duration=duration)
        else:
            v = v.subclip(0, duration)
        return v.set_duration(duration)
    except Exception:
        return ColorClip(size=(W, H), color=(8, 12, 28), duration=duration)


def _ken_burns_image_silent(image_path: str, duration: float, W: int, H: int):
    img = ImageClip(image_path).set_duration(duration).resize((W, H))

    def zoom(t):
        return 1.0 + 0.06 * (t / max(duration, 0.01))

    img = img.resize(zoom)
    return CompositeVideoClip([img.set_position("center")], size=(W, H)).set_duration(duration)


def _league_overlay_clip(logo_paths: list[str], duration: float,
                          video_size: tuple[int, int],
                          y_position_pct: float = 0.30) -> "ImageClip | None":
    """Construye el ImageClip del overlay de ligas posicionado en y_position_pct.

    Devuelve None si no hay logos.
    """
    canvas = build_league_overlay_image(logo_paths, video_size)
    if canvas is None:
        return None
    W, H = video_size
    arr = np.array(canvas)
    clip = ImageClip(arr, transparent=True).set_duration(duration)
    clip_h = arr.shape[0]
    y_top = int(H * y_position_pct) - clip_h // 2
    y_top = max(0, min(H - clip_h, y_top))
    return clip.set_position(("center", y_top))


def _perfil_visual_silent(perfil_path: str, duration: float, W: int, H: int,
                           height_pct: float = 0.32,
                           y_position_pct: float = 0.36):
    """Renderiza perfil.png como overlay transparente del tamaño de los logos de liga.

    NO tapa el vídeo de stock detrás (sin bg_color negro). Posicionado en zona
    media tirando arriba para que no choque con los subtítulos (78% Y) ni con
    el header de la liga (12% Y).

    `height_pct` = altura del overlay como % del frame (default 32% ≈ 614px en 1920).
    `y_position_pct` = centro vertical del overlay como % del frame (default 36%).
    """
    img = ImageClip(perfil_path)
    target_h = max(120, int(H * height_pct))
    img = img.resize(height=target_h)
    # Si la imagen es desproporcionadamente ancha, cap horizontal al 85% del frame
    if img.w > W * 0.85:
        img = img.resize(width=int(W * 0.85))
    # Centro vertical en y_position_pct del alto
    y_top = int(H * y_position_pct) - img.h // 2
    y_top = max(0, min(H - img.h, y_top))
    return img.set_position(("center", y_top)).set_duration(duration)


def _plan_clips_for_segment(segment_dur: float, available_clips: list[str],
                            target_clip_dur: float = 12.0,
                            min_clip_dur: float = 8.0,
                            max_clip_dur: float = 18.0) -> list[tuple[str, float]]:
    """Decide cuántos clips usar dentro de un segmento y cuánto dura cada uno.

    Reglas:
      - Apunta a clips de ~`target_clip_dur` segundos (default 12s).
      - Mínimo `min_clip_dur` por clip (8s) — clips más cortos cansan al ojo.
      - Máximo `max_clip_dur` por clip (18s) — más largos aburren.
      - Si solo hay 1 clip o el segmento es muy corto, usa 1 solo clip.
      - No repite clips dentro de un segmento si la pool tiene suficientes.

    Returns: lista [(clip_path, duration), ...] cuya suma == segment_dur.
    Si no hay clips, devuelve []  (caller usa fondo sólido).
    """
    if not available_clips or segment_dur <= 0:
        return []

    # Caso trivial: segmento corto → 1 solo clip
    if segment_dur < min_clip_dur * 1.25:
        return [(random.choice(available_clips), segment_dur)]

    # Cuántos clips encajan apuntando a target_clip_dur
    n_ideal = max(1, round(segment_dur / target_clip_dur))
    # No más clips que los disponibles (evita repeticiones)
    n_clips = min(n_ideal, len(available_clips))
    # Bajar n_clips hasta que cada uno supere min_clip_dur
    while n_clips > 1 and (segment_dur / n_clips) < min_clip_dur:
        n_clips -= 1
    # Subir n_clips si cada uno excede max_clip_dur (y hay disponibilidad)
    while (segment_dur / n_clips) > max_clip_dur and n_clips < len(available_clips):
        n_clips += 1

    dur_each = segment_dur / n_clips
    pool = list(available_clips)
    random.shuffle(pool)
    selected = pool[:n_clips]
    return [(clip, dur_each) for clip in selected]


def _build_visual_timeline(audio_duration: float, picks: list[dict],
                           segments: dict, carousels: dict[int, str],
                           clip_pools: dict[str, list[str]],
                           perfil_path: str | None,
                           league_overlay: dict | None,
                           W: int, H: int,
                           show_pick_carousel: bool = False,
                           carousel_lead_s: float = 4.0) -> list:
    """Construye el timeline de visuales usando segmentos detectados.

    Estructura por pick:
      - 0..carousel_lead_s: carrusel Ken Burns con la card del pick (~4s).
      - resto del segmento: clips de stock múltiples planificados con _plan_clips_for_segment.

    Para la intro: solo clips de stock (sin carrusel).
    Para el CTA: overlay perfil.png encima del visual base que toque.

    `clip_pools` mapea claves a listas de rutas:
      - "intro" → pool para la intro
      - str(idx) → pool para el pick idx (1, 2, 3, ...)
    """
    timeline = []

    # ── INTRO ──
    intro_start, intro_end = segments["intro"]
    intro_dur = max(0.0, intro_end - intro_start)
    if intro_dur > 0:
        intro_pool = clip_pools.get("intro") or clip_pools.get("1") or []
        plan = _plan_clips_for_segment(intro_dur, intro_pool)
        if plan:
            cursor = intro_start
            for clip_path, d in plan:
                timeline.append({
                    "start": cursor, "duration": d,
                    "clip_factory": lambda dur=d, p=clip_path: _stock_visual(p, dur, W, H),
                })
                cursor += d
        else:
            # Sin pool → fondo sólido
            timeline.append({
                "start": intro_start, "duration": intro_dur,
                "clip_factory": lambda dur=intro_dur: _stock_visual(None, dur, W, H),
            })

    # ── PICKS ──
    for i, (s_start, s_end) in enumerate(segments["picks"], start=1):
        seg_dur = max(0.0, s_end - s_start)
        if seg_dur <= 0:
            continue

        # Carrusel al inicio del pick (opcional, OFF por defecto — el usuario
        # prefiere ver vídeo de stock continuo). Si se activa, ocupa los primeros
        # `carousel_lead_s` segundos del pick.
        carousel_path = carousels.get(i) if show_pick_carousel else None
        lead = min(carousel_lead_s, seg_dur * 0.4) if show_pick_carousel else 0.0
        if carousel_path and lead >= 1.5:
            timeline.append({
                "start": s_start, "duration": lead,
                "clip_factory": lambda dur=lead, p=carousel_path: (
                    _ken_burns_image_silent(p, dur, W, H)
                ),
            })
            stock_start = s_start + lead
            stock_dur = seg_dur - lead
        else:
            stock_start = s_start
            stock_dur = seg_dur

        # Stock múltiple para el resto del segmento
        if stock_dur > 0:
            pool = clip_pools.get(str(i)) or []
            plan = _plan_clips_for_segment(stock_dur, pool)
            if plan:
                cursor = stock_start
                for clip_path, d in plan:
                    timeline.append({
                        "start": cursor, "duration": d,
                        "clip_factory": lambda dur=d, p=clip_path: _stock_visual(p, dur, W, H),
                    })
                    cursor += d
            else:
                timeline.append({
                    "start": stock_start, "duration": stock_dur,
                    "clip_factory": lambda dur=stock_dur: _stock_visual(None, dur, W, H),
                })

    # ── Cap final: si los segmentos no cubren toda la duración del audio
    covered = max((e["start"] + e["duration"] for e in timeline), default=0.0)
    if covered < audio_duration - 0.05:
        pad = audio_duration - covered
        last_pool = clip_pools.get(str(len(picks))) or clip_pools.get("1") or []
        plan = _plan_clips_for_segment(pad, last_pool)
        if plan:
            cursor = covered
            for clip_path, d in plan:
                timeline.append({
                    "start": cursor, "duration": d,
                    "clip_factory": lambda dur=d, p=clip_path: _stock_visual(p, dur, W, H),
                })
                cursor += d
        else:
            timeline.append({
                "start": covered, "duration": pad,
                "clip_factory": lambda dur=pad: _stock_visual(None, dur, W, H),
            })

    # ── CTA overlay (perfil.png) ──
    cta_window = segments.get("cta")
    if cta_window and perfil_path:
        cta_start, cta_end = cta_window
        timeline.append({
            "start": cta_start, "duration": cta_end - cta_start,
            "clip_factory": lambda dur=(cta_end - cta_start), p=perfil_path: (
                _perfil_visual_silent(p, dur, W, H)
            ),
            "is_overlay": True,
            "label": "perfil_overlay",
        })
    elif cta_window and not perfil_path:
        # Diagnóstico: tenemos ventana del CTA pero no archivo perfil → marcar
        # con un label para que el caller pueda loggearlo.
        pass

    # ── Overlay logos de ligas (al detectar 'ligas'/'champions'/...) ──
    if league_overlay and league_overlay.get("logos") and league_overlay.get("anchor") is not None:
        anchor = float(league_overlay["anchor"])
        dur = float(league_overlay.get("duration", 3.0))
        # Cap si el anchor + duración se sale del audio
        dur = min(dur, max(0.5, audio_duration - anchor))
        logos = league_overlay["logos"]
        timeline.append({
            "start": anchor, "duration": dur,
            "clip_factory": lambda d=dur, lg=logos: _league_overlay_clip(lg, d, (W, H)),
            "is_overlay": True,
        })

    return timeline


def _compose_video(audio_clip, timeline: list, W: int, H: int):
    """Convierte el timeline plano en un CompositeVideoClip final con el audio."""
    base_clips = []
    overlay_clips = []
    for entry in timeline:
        clip = entry["clip_factory"]().set_start(entry["start"])
        if entry.get("is_overlay"):
            overlay_clips.append(clip)
        else:
            base_clips.append(clip)

    # base_clips se renderizan en orden temporal (cubren toda la duración)
    # overlay_clips van encima (perfil.png durante el CTA)
    all_clips = base_clips + overlay_clips
    final = CompositeVideoClip(all_clips, size=(W, H))
    final = final.set_duration(audio_clip.duration).set_audio(audio_clip)
    return final


def run_pronosticos_pipeline(
    target_date: str | None = None,
    output_folder: str | None = None,
    log_callback: Callable[[str], None] | None = None,
    video_size: tuple[int, int] = (1080, 1920),
    fps: int = 30,
    voice_id_override: str | None = None,
    publish_to_redis: bool = False,
    add_subtitles: bool = True,
    use_intro_folder: bool = True,
    add_money_sfx: bool = True,
    sfx_volume: float = 0.55,
    add_clink_sfx: bool = True,
    clink_volume: float = 0.35,
    add_camera_sfx: bool = True,
    camera_volume: float = 0.45,
    add_league_overlay: bool = True,
    league_overlay_duration: float = 3.0,
    saturation: float = 1.25,
    show_pick_carousel: bool = False,
    version_id: str | None = None,
    script_override: str | None = None,
    add_background_music: bool = True,
    bgm_volume: float = 0.20,
    progress_callback: Callable[[float, str], None] | None = None,
) -> str:
    """Genera el MP4 final y devuelve la ruta.

    `target_date` = `YYYY-MM-DD`. Por defecto, mañana.
    `version_id`  = id de la versión del guion a usar (cuando el payload trae
                    `versions[]`). Si es None, usa `selected_version_id` del
                    payload o cae a la última.
    `script_override` = si se pasa, sustituye al `script` del payload (solo en
                    memoria, NO se guarda en Redis). Útil para que la UI edite
                    el guion ad-hoc antes de generar.
    """
    log = log_callback or _noop
    target_date = target_date or _tomorrow()
    voice_id_override = voice_id_override or os.environ.get("PRONOSTICOS_VOICE_ID")

    # Reporter de progreso (no-op si no se pasa callback)
    def _progress(pct: float, msg: str) -> None:
        if progress_callback:
            try:
                progress_callback(max(0.0, min(1.0, pct)), msg)
            except Exception:
                pass

    log(f"📅 Procesando vídeo para {target_date}"
        + (f" (versión {version_id})" if version_id else "") + "...")
    _progress(0.02, "Conectando con Redis...")

    # 1. Cargar guion ya hecho desde Redis
    log("📡 Conectando con Redis (Upstash)...")
    payload = load_chosen_version(target_date, version_id=version_id)
    chosen_id = payload.get("id", "legacy")
    chosen_trigger = payload.get("trigger", "?")
    mode = payload.get("mode", "?")
    picks = get_picks(payload)
    competition_focus = payload.get("competition_focus")

    # Override del script: edición efímera de la UI. Mantiene mode/picks/etc del payload.
    if script_override and script_override.strip() and script_override != payload.get("script"):
        script = script_override.strip()
        words_in_override = len(script.split())
        log(f"✏️ Guion EDITADO en UI (no se persiste): {words_in_override} palabras "
            f"(original: {payload.get('word_count', '?')})")
    else:
        script = payload["script"]
        log(f"✅ Guion v{chosen_id} ({chosen_trigger}) cargado: mode={mode}, picks={len(picks)}, "
            f"~{payload.get('word_count', '?')} palabras, "
            f"~{payload.get('estimated_duration_s', '?')}s estimados")
    if competition_focus:
        log(f"🏆 competition_focus: {competition_focus}")

    work_dir = tempfile.mkdtemp(prefix="pronosticos_")

    # 2. TTS único (MiniMax) — todo el script en una sola pieza
    _progress(0.05, "Sintetizando voz (MiniMax)...")
    log("🎙️ Sintetizando audio con MiniMax (script completo, una sola pasada)...")
    audio_path = os.path.join(work_dir, "voice.mp3")
    locutor.generate_single_audio(script, audio_path, voice_id_override=voice_id_override)
    _progress(0.20, "Voz sintetizada")

    # 3. Whisper local para word_timings
    _progress(0.22, "Transcribiendo audio (Whisper)...")
    log("📝 Transcribiendo audio con Whisper para sincronizar visuales...")
    from src.subtitles import transcribe
    word_timings = transcribe(audio_path, model_size="base", language="es")
    if not word_timings:
        log("⚠️ Whisper no devolvió palabras — el CTA no se detectará.")
    _progress(0.40, "Audio transcrito")

    # 4. Detectar segmentos (intro + picks + ventana CTA) en el audio
    audio_clip = AudioFileClip(audio_path)
    audio_duration = float(audio_clip.duration)
    segments = find_segments(word_timings, audio_duration, log_callback=log)

    # 4.b SFX de dinero sincronizado con la cifra del bote en la intro
    if add_money_sfx and word_timings:
        money_path = _resolve_sfx("money.mp3", "cha-ching.mp3", "dinero.mp3")
        if money_path:
            money_t = find_money_anchor(word_timings, intro_end=segments["intro"][1])
            if money_t is not None:
                # 150ms de adelanto sobre el ataque vocal (sensación de pre-cue)
                audio_clip = _mix_sfx_at_timestamps(
                    audio_clip, money_path, [max(0.0, money_t - 0.10)],
                    sfx_volume, audio_duration, log, label="💰 dinero",
                )
            else:
                log("ℹ️ No se halló palabra-número en la intro; SFX dinero omitido.")
        else:
            log("ℹ️ SFX dinero no encontrado en BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/")

    # 4.c SFX clink cada vez que arranca el pick textual ("más", "ambos"...)
    if add_clink_sfx and word_timings:
        clink_path = _resolve_sfx("clink.mp3", "notification.mp3", "pick.mp3")
        if clink_path:
            from .segment_locator import find_pick_anchors, find_pick_starts
            pick_starts = find_pick_starts(word_timings)
            log(f"🔔 Clink: {len(pick_starts)} transiciones detectadas")
            anchors = find_pick_anchors(word_timings, pick_starts, log_callback=log)
            audio_clip = _mix_sfx_at_timestamps(
                audio_clip, clink_path, anchors,
                clink_volume, audio_duration, log, label="🔔 clink picks",
            )
        else:
            log("ℹ️ SFX clink no encontrado en BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/")

    # 4.d Overlay de logos de ligas en la intro (al detectar 'ligas/champions/europa...')
    league_overlay_anchor: float | None = None
    league_logos: list[str] = []
    if add_league_overlay and word_timings and picks:
        league_overlay_anchor = find_league_overlay_anchor(
            word_timings, intro_end=segments["intro"][1],
        )
        if league_overlay_anchor is not None:
            league_logos = resolve_league_logos(picks, _resolve_asset, max_logos=3)
            if league_logos:
                log(f"🏆 Overlay de ligas: {len(league_logos)} logos a los "
                    f"{league_overlay_anchor:.2f}s ({league_overlay_duration:.1f}s en pantalla)")
            else:
                log("ℹ️ Trigger detectado pero ninguna liga del payload tiene logo en /fotos/")
                league_overlay_anchor = None
        else:
            log("ℹ️ No se halló trigger de ligas en la intro; sin overlay.")

    # 4.e SFX cámara — unificado: dispara cuando aparece perfil.png (CTA) y/o logos de ligas
    if add_camera_sfx:
        camera_path = _resolve_sfx("camera.mp3", "shutter.mp3", "foto.mp3")
        if camera_path:
            camera_timestamps: list[float] = []
            if segments.get("cta"):
                camera_timestamps.append(segments["cta"][0])
            if league_overlay_anchor is not None and league_logos:
                camera_timestamps.append(league_overlay_anchor)
            if camera_timestamps:
                audio_clip = _mix_sfx_at_timestamps(
                    audio_clip, camera_path, camera_timestamps,
                    camera_volume, audio_duration, log, label="📸 cámara",
                )
        else:
            log("ℹ️ SFX cámara no encontrado en BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/")

    # 4.f Música de fondo — última capa (la voz y SFX van por encima)
    if add_background_music:
        bgm_path = _resolve_background_music()
        if bgm_path:
            audio_clip = _mix_background_music(
                audio_clip, bgm_path, bgm_volume, audio_duration, log,
            )
        else:
            log("ℹ️ Música de fondo no encontrada (busca fondo.mp3 en sfx/, musica/ o bgm/)")
    n_detected = len(segments["picks"])
    log(f"🎯 Segmentos detectados: intro {segments['intro'][0]:.1f}-{segments['intro'][1]:.1f}s "
        f"+ {n_detected} picks (esperados: {len(picks)})")
    if segments["cta"]:
        log(f"🎯 CTA midroll: {segments['cta'][0]:.1f}s → {segments['cta'][1]:.1f}s")
    else:
        log("⚠️ Sin anchor 'linkcito' — sin overlay perfil.png.")

    # Si Whisper detectó menos picks que los del payload, fallback a reparto uniforme
    if n_detected != len(picks) and len(picks) > 0:
        log(f"⚠️ Whisper no detectó todas las transiciones ({n_detected}/{len(picks)}). "
            f"Cayendo a reparto uniforme.")
        intro_end = audio_duration * 0.07  # ~7% para intro
        slot = (audio_duration - intro_end) / len(picks)
        segments["intro"] = (0.0, intro_end)
        segments["picks"] = [(intro_end + i * slot, intro_end + (i + 1) * slot)
                             for i in range(len(picks))]

    # 5. Renderizar carruseles (solo si el flag está activo — por defecto OFF)
    carousels: dict[int, str] = {}
    if show_pick_carousel:
        log(f"🖼️ Renderizando carruseles ({len(picks)} picks)...")
        carousel_dir = os.path.join(work_dir, "carousels")
        os.makedirs(carousel_dir, exist_ok=True)
        for i, pick in enumerate(picks, start=1):
            path = os.path.join(carousel_dir, f"carousel_{i}.png")
            render_pick_card(pick, i, path, video_size=video_size,
                             competition_focus=competition_focus)
            carousels[i] = path
    else:
        log("🖼️ Carrusel del pick desactivado — se mostrará solo vídeo de stock.")

    # 6. Pools de clips: por cada segmento, lista COMPLETA de la carpeta apropiada
    _progress(0.45, "Buscando clips de stock...")
    log("🎞️ Construyendo pools de clips (con caché jerárquica)...")
    clip_pools: dict[str, list[str]] = {}

    # Intro: si está activado el flag, prioriza carpeta 'intro'; si no, usa la del pick 1
    if use_intro_folder:
        intro_pool = get_clips_pool(prefer_labels=["intro"])
        if intro_pool:
            log(f"🎬 Intro: carpeta dedicada — {len(intro_pool)} clips")
        else:
            log("ℹ️ No hay carpeta 'intro' poblada — la intro hereda del pick 1")
        clip_pools["intro"] = intro_pool

    for i, pick in enumerate(picks, start=1):
        home_team, away_team = parse_match(pick.get("match", ""))
        pool = get_clips_pool(
            home_team=home_team,
            away_team=away_team,
            league=pick.get("league"),
        )
        # Si la carpeta no tiene clips locales, intentar Pexels para descargar al menos 1
        if not pool:
            single = search_clip(
                league=pick.get("league"),
                country=pick.get("country"),
                sport=pick.get("sport"),
                home_team=home_team,
                away_team=away_team,
            )
            pool = [single] if single else []
        clip_pools[str(i)] = pool
        log(f"  pick #{i} ({pick.get('match', '?')}): {len(pool)} clips")

    # 7. perfil.png para CTA
    perfil_path = _resolve_perfil_png()
    if perfil_path:
        log(f"📸 perfil.png localizado: {perfil_path}")
        if not segments.get("cta"):
            log("⚠️ perfil.png existe pero no se detectó la ventana del CTA → "
                "el overlay NO se mostrará. Revisa los tokens de Whisper más arriba.")
    else:
        log("⚠️ perfil.png no encontrado en BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/. "
            "Durante el CTA se mostrará el stock que toque.")

    # 8. Composición
    _progress(0.55, "Componiendo timeline visual...")
    log(f"🎬 Componiendo vídeo ({audio_duration:.1f}s)...")
    W, H = video_size
    league_overlay_data = None
    if league_overlay_anchor is not None and league_logos:
        league_overlay_data = {
            "anchor": league_overlay_anchor,
            "duration": league_overlay_duration,
            "logos": league_logos,
        }

    timeline = _build_visual_timeline(
        audio_duration=audio_duration,
        picks=picks,
        segments=segments,
        carousels=carousels,
        clip_pools=clip_pools,
        perfil_path=perfil_path,
        league_overlay=league_overlay_data,
        W=W, H=H,
        show_pick_carousel=show_pick_carousel,
    )

    # Log resumen del timeline (debug del overlay perfil + ligas)
    overlays = [e for e in timeline if e.get("is_overlay")]
    if overlays:
        for e in overlays:
            label = e.get("label") or "overlay"
            log(f"  ✓ {label}: {e['start']:.2f}s → {e['start']+e['duration']:.2f}s")
    elif segments.get("cta"):
        log("⚠️ Hay ventana CTA pero ningún overlay se añadió al timeline "
            "(¿perfil.png faltante o ruta mal resuelta?).")
    final = _compose_video(audio_clip, timeline, W, H)

    # 9. Guardar (nombre incluye version_id si hay varias)
    if not output_folder:
        output_folder = os.path.join(os.getcwd(), "VIDEOS_TERMINADOS")
    # Cada nicho guarda en su subcarpeta dentro de VIDEOS_TERMINADOS
    output_folder = os.path.join(output_folder, "PRONOSTICOS")
    os.makedirs(output_folder, exist_ok=True)
    suffix = f"_v{chosen_id}" if chosen_id != "legacy" else ""
    out_name = f"Pronosticos_{target_date}{suffix}.mp4"
    out_path = os.path.join(output_folder, out_name)
    if os.path.exists(out_path):
        from datetime import datetime as _dt
        out_path = os.path.join(
            output_folder,
            f"Pronosticos_{target_date}{suffix}_{_dt.now().strftime('%H%M%S')}.mp4",
        )

    _progress(0.60, "Renderizando MP4 base...")
    final.write_videofile(
        out_path, fps=fps, codec="libx264", audio_codec="aac",
        preset="ultrafast", threads=8, logger=None,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )
    duration_s = float(final.duration)
    _progress(0.80, "MP4 base renderizado")

    # 10. Subtítulos karaoke palabra-a-palabra (estilo del nicho)
    if add_subtitles and word_timings:
        _progress(0.82, "Quemando subtítulos...")
        log("🔤 Quemando subtítulos palabra a palabra (estilo Pronósticos)...")
        try:
            from src.subtitles import render_karaoke_on_video
            from .number_parser import collapse_spanish_numbers
            # Convierte 'cuatro mil quinientos' → '4.500' SOLO en los subtítulos
            # (los anchors del audio ya están detectados desde los timings originales)
            sub_words = collapse_spanish_numbers(word_timings)
            collapsed = len(word_timings) - len(sub_words)
            if collapsed > 0:
                log(f"🔢 Cifras colapsadas en subtítulos: {collapsed} tokens fusionados a dígitos")
            tmp_subs = out_path + ".subs.mp4"
            render_karaoke_on_video(out_path, sub_words, PRONOSTICOS_SUB_STYLE, tmp_subs,
                                    log_callback=lambda m: log(m))
            os.replace(tmp_subs, out_path)
        except Exception as e:
            log(f"⚠️ No se quemaron subtítulos: {e}")

    # 10.b Saturación de color (post-render, ffmpeg directo)
    if saturation and abs(saturation - 1.0) > 0.01:
        _progress(0.92, "Aplicando saturación...")
        log(f"🎨 Aplicando saturación ×{saturation:.2f}...")
        tmp_sat = out_path + ".sat.mp4"
        if _apply_saturation(out_path, tmp_sat, saturation, log):
            os.replace(tmp_sat, out_path)
        else:
            try: os.remove(tmp_sat)
            except OSError: pass

    # 11. (Opcional) publicar URL
    if publish_to_redis:
        try:
            publish_video_url(target_date, out_path, duration_s,
                              version_id=str(chosen_id) if chosen_id != "legacy" else None)
            log(f"📤 URL publicada en betai:tiktokfactory_video_tomorrow (v{chosen_id})")
        except Exception as e:
            log(f"⚠️ No se pudo publicar en Redis: {e}")

    try:
        shutil.rmtree(work_dir)
    except Exception:
        pass

    _progress(1.0, "Listo")
    log(f"✨ Vídeo listo en {out_path} ({duration_s:.1f}s)")
    return out_path
