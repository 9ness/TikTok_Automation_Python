"""Runners por modo: ejecutan un Job sin tocar Streamlit.

Cada runner recibe `(job, on_log, on_progress)` donde:
- `on_log(msg: str)` añade una línea al log del job (visible en UI)
- `on_progress(pct: float, label: str)` actualiza el progreso 0.0→1.0

Las pipelines de bajo nivel ya aceptan callbacks, así que aquí solo
orquestamos. La única "pipeline pesada" que estaba inline en main.py es
la de Presidentes (`generate_video_pipeline`) — para ella reimplementamos
la versión headless aquí (`_render_presidents_video_headless`) sin
tocar `st.*`.
"""

from __future__ import annotations

import glob
import os
import shutil
import time
import traceback
from datetime import datetime
from typing import Callable

from proglog import ProgressBarLogger

from .models import Job, JobMode, JobStatus


OnLog = Callable[[str], None]
OnProgress = Callable[[float, str], None]


# ============================================================
# Progress logger genérico para moviepy (sin Streamlit)
# ============================================================
class CallbackProgressLogger(ProgressBarLogger):
    """Mapea el progreso de moviepy a un `(pct, label)` callback,
    escalado dentro de una franja [lo, hi] del progreso global."""

    def __init__(
        self,
        on_progress: OnProgress,
        label: str = "🎞️ Renderizando…",
        lo: float = 0.0,
        hi: float = 1.0,
    ):
        super().__init__(
            init_state=None, bars=None, ignored_bars=None,
            logged_bars="all", min_time_interval=0, ignore_bars_under=0,
        )
        self.on_progress = on_progress
        self.label = label
        self.lo = lo
        self.hi = hi
        self._last = -1

    def callback(self, **changes):
        for bar in changes.get("bars", []):
            info = self.bars[bar]
            if "total" in info and info["total"] > 0:
                frac = max(0.0, min(1.0, info["index"] / info["total"]))
                pct = self.lo + (self.hi - self.lo) * frac
                # Throttle a cambios de 1% para no saturar
                pct_int = int(pct * 100)
                if pct_int != self._last:
                    self._last = pct_int
                    try:
                        self.on_progress(pct, self.label)
                    except Exception:
                        pass


# ============================================================
# PRESIDENTES — render headless del vídeo (extracto de main.py:148)
# ============================================================
def _render_presidents_video_headless(
    src_folder: str,
    output_folder: str,
    config: dict,
    on_log: OnLog,
    on_progress: OnProgress,
    engine_version: str,
    progress_lo: float,
    progress_hi: float,
) -> str:
    """Versión sin Streamlit de generate_video_pipeline. Devuelve la
    ruta del MP4 generado."""
    from moviepy.editor import (
        AudioFileClip, CompositeAudioClip, concatenate_videoclips,
    )
    from src.logic import create_video_segment

    if not os.path.exists(src_folder):
        raise FileNotFoundError(f"No existe la carpeta fuente: {src_folder}")

    output_folder = os.path.join(output_folder, "PRESIDENTES")
    os.makedirs(output_folder, exist_ok=True)

    local_audios = glob.glob(os.path.join(src_folder, "*.mp3"))
    if not local_audios:
        raise ValueError("No se encontraron archivos .mp3 en la carpeta indicada.")

    intro_file = None
    body_files = []
    for aud in local_audios:
        if "intro" in os.path.basename(aud).lower():
            intro_file = aud
        else:
            body_files.append(aud)

    try:
        body_files.sort(
            key=lambda x: int(os.path.basename(x).split("_")[0]),
            reverse=True,
        )
    except Exception:
        body_files.sort(key=lambda x: os.path.basename(x), reverse=True)

    final_audio_order = []
    if intro_file:
        final_audio_order.append(intro_file)
    final_audio_order.extend(body_files)

    clips = []
    token = False
    revealed_presidents = []
    n_segments = max(1, len(final_audio_order))

    # Construcción de segmentos: 60% del rango destinado a esta fase
    seg_lo = progress_lo
    seg_hi = progress_lo + (progress_hi - progress_lo) * 0.6

    for i, aud in enumerate(final_audio_order):
        try:
            name = os.path.splitext(os.path.basename(aud))[0]
            try:
                parts = name.split("_")
                if "intro" in name.lower():
                    puesto, presi = 1, "Intro"
                elif len(parts) >= 2:
                    puesto = int(parts[0])
                    presi = "_".join(parts[1:])
                else:
                    puesto, presi = 0, name
            except Exception:
                puesto, presi = 0, name

            on_log(f"⚙️ Segmento {i+1}/{n_segments}: {name} ({presi})")
            pct = seg_lo + (seg_hi - seg_lo) * (i / n_segments)
            on_progress(pct, f"🎞️ Segmento {i+1}/{n_segments}")

            seg, token, _ = create_video_segment(
                aud, puesto, presi, config, token,
                log_callback=on_log,
                engine_version=engine_version,
                revealed_presidents=revealed_presidents,
            )
            revealed_presidents.append(presi)
            if seg:
                clips.append(seg)
        except Exception as e:
            on_log(f"❌ Error creando segmento {os.path.basename(aud)}: {e}")
            print(f"[Presidents] Detalle: {traceback.format_exc()}")

    if not clips:
        raise RuntimeError("No se generaron clips válidos.")

    on_log("⚙️ Montaje final…")
    on_progress(seg_hi, "🎬 Montando vídeo final")

    path_pagina = os.path.join(config["paths"]["resources_library"], "pagina.mp3")
    sound_effect = None
    if os.path.exists(path_pagina):
        try:
            sound_effect = AudioFileClip(path_pagina)
        except Exception:
            sound_effect = None

    final = concatenate_videoclips(clips, method="compose")

    if len(clips) > 1 and sound_effect:
        sfx_clips = []
        current_time = 0
        for i in range(len(clips) - 1):
            current_time += clips[i].duration
            start_t = max(0, current_time - 0.2)
            sfx_clips.append(sound_effect.set_start(start_t))
        if sfx_clips:
            global_audio = CompositeAudioClip([final.audio] + sfx_clips)
            global_audio = global_audio.set_duration(final.duration)
            final = final.set_audio(global_audio)

    if final.audio:
        final = final.set_audio(final.audio.set_duration(final.duration))

    # Naming secuencial
    try:
        existing = [
            f for f in os.listdir(output_folder)
            if f.endswith(".mp4") and "TikTok_AUTO_" in f
        ]
        out_name = f"TikTok_AUTO_{len(existing) + 1}.mp4"
    except Exception:
        out_name = f"TikTok_AUTO_{datetime.now().strftime('%H%M%S')}.mp4"

    if os.path.exists(os.path.join(output_folder, out_name)):
        ts = datetime.now().strftime("%H%M%S")
        out_name = f"{os.path.splitext(out_name)[0]}_{ts}.mp4"

    out_path = os.path.join(output_folder, out_name)

    sets = config["video_settings"]
    safe_w, safe_h = tuple(sets["resolution"])
    if safe_w % 2 != 0:
        safe_w -= 1
    if safe_h % 2 != 0:
        safe_h -= 1
    if final.w != safe_w or final.h != safe_h:
        final = final.resize(newsize=(safe_w, safe_h))

    # Render con logger callback
    render_logger = CallbackProgressLogger(
        on_progress,
        label="🎞️ Renderizando vídeo final",
        lo=seg_hi,
        hi=progress_hi,
    )
    final.write_videofile(
        out_path,
        fps=sets["fps"],
        codec="libx264",
        audio_codec="aac",
        logger=render_logger,
        threads=8,
        preset="ultrafast",
        remove_temp=True,
        ffmpeg_params=["-pix_fmt", "yuv420p"],
    )
    return out_path


# ============================================================
# RUNNER: PRESIDENTES (auto factory: guion → audio → vídeo → subs → hook)
# ============================================================
def run_presidents(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    p = job.params
    config = p["config"]

    # Pesos de los pasos
    w_script = 0.05
    w_audio = 0.15
    w_video = 0.50
    w_subs = 0.20 if p.get("subs_enabled") else 0.0
    w_hook = 0.10 if p.get("hook_enabled") else 0.0
    w_total = w_script + w_audio + w_video + w_subs + w_hook
    cum = []
    acc = 0.0
    for w in (w_script, w_audio, w_video, w_subs, w_hook):
        acc += w / w_total
        cum.append(acc)
    # cum[0..4] = pct acumulado tras: guion, audio, video, subs, hook

    # ----- 1+2. GUIÓN + AUDIO con auto-calibración de palabras -----
    # Calibra target_total_words por tipo de vídeo para clavar 60-65s.
    on_progress(0.0, "📝 Generando guion…")
    import src.guionista as guionista
    import src.locutor as locutor
    from src import word_calibrator as wc

    type_key = wc.build_type_key(
        top_count=p.get("top_count", 5),
        include_hook=p.get("include_hook", True),
        creative_mode=p.get("creative_mode", False),
    )
    target_words = wc.get_target_words(type_key)
    on_log(
        f"🎯 Calibración tipo='{type_key}' → target inicial: {target_words} "
        f"palabras (rango {wc.TARGET_MIN_S:.0f}-{wc.TARGET_MAX_S:.0f}s)"
    )

    MAX_ATTEMPTS = p.get("calibration_max_attempts", 5)
    script_data = None
    txt_output = None
    audio_output_folder = None
    total_dur = 0.0
    success_in_range = False

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            on_log(
                f"📝 [Intento {attempt}/{MAX_ATTEMPTS}] Generando guion "
                f"con OpenAI (target {target_words} palabras)…"
            )
            script_data = guionista.generate_script(
                user_topic=p.get("topic"),
                creative_mode=p.get("creative_mode", False),
                title_prefix=p.get("title_prefix", "The 5"),
                include_history=p.get("include_history", True),
                include_hook=p.get("include_hook", True),
                top_count=p.get("top_count", 5),
                target_total_words=target_words,
            )
            txt_output = guionista.save_scripts_to_txt(
                script_data, top_count=p.get("top_count", 5)
            )
            on_log("✅ Guion listo")
            on_progress(cum[0], f"🎙️ TTS (intento {attempt})…")

            # ----- AUDIO -----
            audio_output_folder = locutor.generate_audios_from_text_folder(
                txt_output, config["paths"]["resources_library"]
            )
            if not audio_output_folder:
                raise RuntimeError("No se generaron audios MiniMax")
            total_dur = wc.measure_audio_folder_duration(audio_output_folder)
            on_log(
                f"⏱️ Duración total audios: {total_dur:.1f}s "
                f"(objetivo {wc.TARGET_MIN_S:.0f}-{wc.TARGET_MAX_S:.0f}s)"
            )

            in_range, next_target = wc.calibration_decision(
                type_key, target_words, total_dur
            )
            if in_range:
                on_log(
                    f"✅ Duración OK ({total_dur:.1f}s). Calibración guardada "
                    f"({target_words} palabras para '{type_key}')."
                )
                success_in_range = True
                break

            if attempt == MAX_ATTEMPTS:
                # Si la duración final está POR DEBAJO del mínimo (60s) no se
                # acepta — un vídeo corto no monetiza. Si está por ENCIMA (66s+)
                # se tolera: videos largos son menos críticos.
                if total_dur < wc.TARGET_MIN_S:
                    on_log(
                        f"❌ Máximo de intentos ({MAX_ATTEMPTS}) alcanzado y "
                        f"duración {total_dur:.1f}s sigue debajo del mínimo "
                        f"({wc.TARGET_MIN_S:.0f}s). Calibrador guardó target "
                        f"{next_target} para futuros intentos."
                    )
                    raise RuntimeError(
                        f"Duración final {total_dur:.1f}s < {wc.TARGET_MIN_S:.0f}s mínimo "
                        f"tras {MAX_ATTEMPTS} intentos. Reintenta el job — el calibrador "
                        f"ha aprendido y debería converger."
                    )
                on_log(
                    f"⚠️ Máximo de intentos alcanzado. Duración {total_dur:.1f}s "
                    f"está por encima del rango pero es aceptable. Continuando."
                )
                break

            on_log(
                f"🔄 Fuera de rango. Reajustando {target_words} → {next_target} "
                f"palabras y regenerando…"
            )
            target_words = next_target
            # Limpia temporales del intento fallido antes de reintentar
            try:
                if txt_output and os.path.exists(txt_output):
                    shutil.rmtree(txt_output, ignore_errors=True)
                if audio_output_folder and os.path.exists(audio_output_folder):
                    shutil.rmtree(audio_output_folder, ignore_errors=True)
            except Exception:
                pass
            txt_output = None
            audio_output_folder = None

        if not script_data or not audio_output_folder:
            raise RuntimeError(
                "Falló la generación de guion/audios tras la calibración"
            )

        if not success_in_range:
            on_log(
                f"⚠️ Vídeo fuera del sweet spot 60-65s "
                f"({total_dur:.1f}s) — se mantiene el render."
            )

        on_log("✅ Audios MiniMax listos")
        on_progress(cum[1], "🎬 Renderizando vídeo…")

        # ----- 3. VÍDEO -----
        final_video_path = _render_presidents_video_headless(
            src_folder=audio_output_folder,
            output_folder=config["paths"]["output_folder"],
            config=config,
            on_log=on_log,
            on_progress=on_progress,
            engine_version=p.get("engine_version", "v2_estable"),
            progress_lo=cum[1],
            progress_hi=cum[2],
        )
        on_log(f"✅ Vídeo base: {os.path.basename(final_video_path)}")

        # ----- 4. SUBTÍTULOS (opcional) -----
        if p.get("subs_enabled"):
            on_progress(cum[2], "🔤 Generando subtítulos karaoke…")
            try:
                from src.subtitles import (
                    DEFAULT_STYLE, render_karaoke_on_video, transcribe,
                )
                from moviepy.editor import VideoFileClip

                tmp_audio = os.path.join(
                    config["paths"]["temp_folder"],
                    f"subs_audio_{int(time.time())}.mp3",
                )
                vc = VideoFileClip(final_video_path)
                vc.audio.write_audiofile(tmp_audio, logger=None)
                vc.close()

                on_log("🎙️ Whisper transcribiendo audio…")
                words = transcribe(tmp_audio, model_size="base", language="en")

                if words:
                    on_log(f"📝 Componiendo overlay ({len(words)} palabras)")
                    # Drop shadow CapCut → params de subtitles.py.
                    # distance (CapCut units, ~px sobre 1920) + angle → offsets
                    # relativos al W/H del frame.
                    import math
                    _dist = float(p.get("subs_shadow_distance", 8.0)) / 1920.0
                    _angle_rad = math.radians(float(p.get("subs_shadow_angle", -45.0)))
                    _sh_x = _dist * math.cos(_angle_rad)
                    _sh_y = _dist * abs(math.sin(_angle_rad))  # CSS Y/PIL Y baja
                    _sh_blur_px = int(float(p.get("subs_shadow_blur", 33.0)) / 8.0)

                    subs_style = {
                        **DEFAULT_STYLE,
                        "highlight_color": p.get("subs_highlight_color", "#BB0808"),
                        "text_color": p.get("subs_text_color", "#FFFFFF"),
                        "stroke_color": p.get("subs_stroke_color", "#000000"),
                        "stroke_width": p.get("subs_stroke_width", 3),
                        "case_mode": p.get("subs_case", "UPPERCASE"),
                        "font_scale": p.get("subs_font_scale", 0.040),
                        "max_words_per_chunk": p.get("subs_max_words", 4),
                        "y_position_pct": p.get("subs_y_position", 0.62),
                        "shadow_enabled": p.get("subs_shadow_enabled", False),
                        "shadow_color": p.get("subs_shadow_color", "#000000"),
                        "shadow_opacity": float(p.get("subs_shadow_opacity", 0.8)),
                        "shadow_offset_x_pct": _sh_x,
                        "shadow_offset_y_pct": _sh_y,
                        "shadow_blur_radius": _sh_blur_px,
                        "highlight_mode": p.get("subs_highlight_mode", "pill"),
                        "max_width_pct": p.get("subs_max_width", 0.85),
                    }
                    # Override del font_path solo si vino especificado (UI Presidentes
                    # ahora puede elegir Impact / Rubik Bold / Arial Bold).
                    if p.get("subs_font_path"):
                        subs_style["font_path"] = p["subs_font_path"]
                    tmp_out = final_video_path + ".tmp.mp4"
                    render_karaoke_on_video(
                        final_video_path, words, subs_style, tmp_out,
                        log_callback=on_log,
                    )
                    os.replace(tmp_out, final_video_path)
                    on_log("✅ Subtítulos karaoke aplicados")
                else:
                    on_log("⚠️ Whisper no detectó palabras — subs omitidos")

                try:
                    os.remove(tmp_audio)
                except Exception:
                    pass
            except ModuleNotFoundError as e:
                # Dependencia faltante — visible y específico para que se note
                on_log(
                    f"❌ Subs OMITIDOS — falta dependencia: {e.name}. "
                    f"Instala en el VPS con: venv/bin/pip install -r requirements.txt"
                )
                print(f"[Presidents/SUBS] ModuleNotFoundError: {e}")
                print(traceback.format_exc())
            except Exception as e:
                on_log(f"❌ Error subs (vídeo se entrega SIN subs): {e}")
                print(f"[Presidents/SUBS] Detalle: {traceback.format_exc()}")
            on_progress(cum[3], "🎣 Añadiendo hook…")

        # ----- 5. HOOK (opcional) -----
        if p.get("hook_enabled"):
            try:
                from src.text_hook import (
                    DEFAULT_HOOK_STYLE, add_text_hook_to_video,
                )

                hook_text = (
                    (script_data.get("hook_box_text") or "").strip()
                    or (script_data.get("video_title") or "").strip()
                    or "Top 5 US Presidents"
                )
                on_log(f"🎣 Hook: \"{hook_text}\"")
                hook_style = {
                    **DEFAULT_HOOK_STYLE,
                    "duration": p.get("hook_duration", 5.0),
                    "animation": p.get("hook_animation", "swipe_left"),
                    "y_position_pct": p.get("hook_y_position", 0.33),
                    "shadow_color": p.get("hook_shadow_color", "#BB0808"),
                    "box_color": p.get("hook_box_color", "#FFFFFF"),
                    "text_color": p.get("hook_text_color", "#0B0B0B"),
                    "font_scale": p.get("hook_font_scale", 0.020),
                }
                tmp_out = final_video_path + ".tmp.mp4"
                add_text_hook_to_video(
                    final_video_path, hook_text, hook_style, tmp_out,
                    log_callback=on_log,
                )
                os.replace(tmp_out, final_video_path)
                on_log("✅ Hook aplicado")
            except Exception as e:
                on_log(f"❌ Error hook: {e}")
            on_progress(cum[4], "🎉 Finalizando…")

        on_progress(1.0, "✅ Vídeo completado")
        return final_video_path
    finally:
        # Limpieza de carpetas temporales (txt + audios)
        try:
            if txt_output and os.path.exists(txt_output):
                shutil.rmtree(txt_output, ignore_errors=True)
            if audio_output_folder and os.path.exists(audio_output_folder):
                shutil.rmtree(audio_output_folder, ignore_errors=True)
        except Exception:
            pass


# ============================================================
# RUNNER: PRONÓSTICOS
# ============================================================
def run_pronosticos(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    p = job.params
    from src.pronosticos.pipeline import run_pronosticos_pipeline

    final_path = run_pronosticos_pipeline(
        target_date=p["target_date"],
        output_folder=p["output_folder"],
        log_callback=on_log,
        video_size=p.get("video_size", (1080, 1920)),
        voice_id_override=p.get("voice_id_override"),
        publish_to_redis=p.get("publish_to_redis", False),
        add_subtitles=p.get("add_subtitles", True),
        use_intro_folder=p.get("use_intro_folder", False),
        add_money_sfx=p.get("add_money_sfx", True),
        sfx_volume=p.get("sfx_volume", 0.55),
        add_clink_sfx=p.get("add_clink_sfx", True),
        clink_volume=p.get("clink_volume", 0.35),
        add_camera_sfx=p.get("add_camera_sfx", True),
        camera_volume=p.get("camera_volume", 0.45),
        add_league_overlay=p.get("add_league_overlay", True),
        league_overlay_duration=p.get("league_overlay_duration", 3.0),
        saturation=p.get("saturation", 1.25),
        show_pick_carousel=p.get("show_pick_carousel", False),
        version_id=p.get("version_id"),
        script_override=p.get("script_override"),
        add_background_music=p.get("add_background_music", True),
        bgm_volume=p.get("bgm_volume", 0.20),
        progress_callback=on_progress,
        subtitle_y_pct=p.get("subtitle_y_pct", 0.78),
        league_overlay_y_pct=p.get("league_overlay_y_pct", 0.30),
        league_logo_height_pct=p.get("league_logo_height_pct", 0.13),
        team_shield_y_pct=p.get("team_shield_y_pct", 0.43),
        team_shield_height_pct=p.get("team_shield_height_pct", 0.22),
        team_shield_x_inset_pct=p.get("team_shield_x_inset_pct", 0.06),
        profile_cta_y_pct=p.get("profile_cta_y_pct", 0.36),
        profile_cta_height_pct=p.get("profile_cta_height_pct", 0.32),
    )
    return final_path


# ============================================================
# RUNNER: SUBS AUTO
# ============================================================
def run_subs_auto(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    p = job.params
    from src.subtitles_only import (
        QUALITY_FROM_SIDEBAR,
        extract_audio_from_video,
        merge_edited_text_with_timings,
        render_subtitles_on_video,
        transcribe_with_reference,
    )

    input_path = p["input_path"]
    out_path = p["out_path"]
    config = p["config"]
    quality_label = p.get("quality_label", "1080p (Lento)")
    quality = QUALITY_FROM_SIDEBAR.get(
        quality_label,
        {"preset": "medium", "crf": 20, "max_long_side": 1280},
    )

    # 1. Extraer audio (0 → 12%)
    on_progress(0.02, "🔊 Extrayendo audio…")
    on_log("🔊 Extrayendo audio del vídeo…")
    tmp_audio = os.path.join(
        config["paths"]["temp_folder"],
        f"subs_audio_{int(time.time())}.mp3",
    )
    extract_audio_from_video(input_path, tmp_audio)
    on_progress(0.12, "✅ Audio extraído")

    # 2. Transcribir (12 → 55%)
    try:
        ref = (p.get("reference_text") or "").strip() or None
        on_progress(0.18, f"🎙️ Whisper '{p.get('model_size','small')}'…")
        on_log(f"🎙️ Transcribiendo con Whisper '{p.get('model_size','small')}'"
               f"{' (con guion ref.)' if ref else ''}")

        # Mapeo del progreso de transcripción [0..1] al rango overall [0.18..0.55].
        # faster-whisper emite progreso por segmento; aquí lo recibimos y lo
        # propagamos al WebSocket con ETA estimado.
        def _on_transcribe_progress(frac: float, msg: str) -> None:
            overall = 0.18 + (0.55 - 0.18) * frac
            on_progress(overall, msg)

        words = transcribe_with_reference(
            tmp_audio,
            reference_script=ref,
            model_size=p.get("model_size", "small"),
            language=p.get("language"),
            audio_type=p.get("audio_type", "speech"),
            progress_callback=_on_transcribe_progress,
        )

        # Si hay edited_text, fundir
        if p.get("edited_text"):
            words = merge_edited_text_with_timings(p["edited_text"], words)
            on_log(f"✏️ Aplicada edición manual de palabras "
                   f"({len(words)} finales)")

        if not words:
            raise RuntimeError(
                "Whisper no detectó palabras. Prueba un modelo más grande."
            )
        on_log(f"✅ {len(words)} palabras transcritas")
        on_progress(0.55, f"✅ {len(words)} palabras")
    finally:
        try:
            os.remove(tmp_audio)
        except Exception:
            pass

    # 3. Render overlay (55 → 100%)
    style = {
        "font_path": p["font_path"],
        "highlight_mode": p["highlight_mode"],
        "highlight_color": p["highlight_color"],
        "text_color": p["text_color"],
        "stroke_color": p["stroke_color"],
        "stroke_width": p["stroke_width"],
        "case_mode": p["case_mode"],
        "font_scale": p["font_scale"],
        "max_words_per_chunk": p["max_words"],
        "y_position_pct": p["y_position"],
        "pill_enabled": p.get("pill_enabled", True),
        "max_width_pct": p.get("max_width", 0.85),
        "sync_offset_ms": p.get("sync_offset", 0),
    }
    on_log(f"🎬 Render overlay (calidad {quality_label})…")
    on_progress(0.58, "🎞️ Renderizando overlay…")
    render_logger = CallbackProgressLogger(
        on_progress,
        label="🎞️ Renderizando overlay",
        lo=0.58,
        hi=1.0,
    )
    render_subtitles_on_video(
        input_path, words, style, out_path,
        quality_settings=quality,
        log_callback=on_log,
        logger=render_logger,
    )
    on_progress(1.0, "✅ Subtítulos listos")
    return out_path


# ============================================================
# RUNNER: COPYRIGHT CLEANER
# ============================================================
def run_copyright(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    p = job.params
    from src.video_remover import VideoRemover

    config = p["config"]
    cleaner = VideoRemover(config)

    on_progress(0.05, "🔍 Analizando subtítulos originales…")
    on_log("🔍 Mapeando trayectoria del texto original…")
    traj = cleaner.map_text_trajectory(p["input_path"], log_callback=on_log)
    on_progress(0.20, "🎙️ Transcribiendo audio…")
    on_log("🎙️ Transcribiendo audio…")
    words = cleaner.transcribe_video(p["input_path"], log_callback=on_log)
    on_progress(0.40, "🎬 Renderizando vídeo final…")

    render_logger = CallbackProgressLogger(
        on_progress,
        label="🎞️ Renderizando vídeo limpio",
        lo=0.40,
        hi=1.0,
    )
    final = cleaner.process(
        p["input_path"],
        config["paths"]["output_folder"],
        words=words,
        trajectory=traj,
        log_callback=on_log,
        logger=render_logger,
        clean_mode=p.get("clean_mode", "Subtítulos Virales"),
        hook_y_pct=p.get("hook_y_pct", 0.20),
        hook_color=p.get("hook_color", "#FDD002"),
        upscale_1080p=bool(p.get("upscale_1080p", False)),
        font_path=p.get("font_path"),
    )
    on_progress(1.0, "✅ Limpieza completada")
    return final


# ============================================================
# RUNNER: CONSTRUCCION POV (nicho 4 Creator Reward)
# ============================================================
def run_construccion_pov(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    """Construcción POV: vídeo input → Gemini guion → MiniMax voz →
    anti-copy + subs karaoke. Devuelve ruta del MP4 final."""
    p = job.params
    from src.construccion_pov.pipeline import run_pipeline

    config = p["config"]

    # Defense-in-depth: si el voice_id viene con prefijo `preset_*` (job
    # encolado por un path antiguo o tests), lo strippeamos para que
    # MiniMax lo acepte. El preflight del enqueue ya lo resuelve, esto
    # es solo red de seguridad.
    voice_id = p["voice_id"]
    if isinstance(voice_id, str) and voice_id.startswith("preset_"):
        voice_id = voice_id[len("preset_"):]
        on_log(f"⚠️ voice_id venía con prefijo preset_*, usando '{voice_id}'.")
    style = {
        "font_path": p["font_path"],
        "highlight_mode": p["highlight_mode"],
        "highlight_color": p["highlight_color"],
        "text_color": p["text_color"],
        "stroke_color": p["stroke_color"],
        "stroke_width": p["stroke_width"],
        "case_mode": p["case_mode"],
        "font_scale": p["font_scale"],
        "max_words_per_chunk": p["max_words"],
        "y_position_pct": p["y_position"],
        "pill_enabled": p.get("pill_enabled", True),
        "max_width_pct": p.get("max_width", 0.85),
        "sync_offset_ms": p.get("sync_offset", 0),
    }
    return run_pipeline(
        input_path=p["input_path"],
        output_folder=config["paths"]["output_folder"],
        config=config,
        voice_id=voice_id,
        subs_style=style,
        upscale_1080p=bool(p.get("upscale_1080p", False)),
        saturation=float(p.get("saturation", 1.25)),
        pulse_zoom=bool(p.get("pulse_zoom", True)),
        mirror=bool(p.get("mirror", False)),
        whisper_model_size=p.get("whisper_model_size", "small"),
        quality_label=p.get("quality_label", "1080p (Lento)"),
        gemini_model=p.get("gemini_model", "gemini-2.5-pro"),
        manual_script=p.get("manual_script"),
        output_name=p.get("output_name"),
        on_log=on_log,
        on_progress=on_progress,
    )


# ============================================================
# RUNNER: TIKTOK SHOP (Programa 2)
# ============================================================
def run_tiktok_shop(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    """Pipeline TikTok Shop con 5 tiers:

    - `standard` / `advanced`  → Atlas Seedance image-to-video, multi_clip_anchor
    - `pro`                    → Atlas Seedance reference-to-video, single_shot_multishot
    - `veo3_prompt_only`       → genera prompt Veo3 (8s) — no renderiza
    - `nano_banana_prompt_only`→ genera prompt fotos premium — no renderiza vídeo

    Voz MiniMax + captions Whisper se aplican en standard/advanced/pro.
    No hay fallback Ken Burns: si Atlas falla, el job falla con mensaje claro.
    """
    p = job.params
    tier = p.get("tier", "standard")
    video_strategy = p.get("strategy", "dynamic")

    on_progress(0.02, "📂 Cargando contexto…")
    from src.tiktok_shop.config import (
        DEFAULT_VIDEO_STRATEGY, STRATEGY_CONFIG, VIDEO_MODELS, VIDEO_STRATEGIES,
    )
    if video_strategy not in VIDEO_STRATEGIES:
        video_strategy = DEFAULT_VIDEO_STRATEGY
    strategy_cfg = STRATEGY_CONFIG[video_strategy]
    from src.tiktok_shop.models import (
        ClipPrompt, GenerationStatus, HookUsed, TikTokShopVideoMeta,
        VideoCost, VideoGeneration, VoiceUsed,
    )
    from src.tiktok_shop.pipeline import (
        analyze_product, generate_nano_banana_prompt, generate_seedance_prompts,
        generate_strategy, generate_veo3_prompt,
    )
    from src.tiktok_shop.pipeline.drive_uploader import upload_video
    from src.tiktok_shop.pipeline.editor import compose_shop_video
    from src.tiktok_shop.repos import GenerationRepo, ProductRepo, UserRepo
    from src.tiktok_shop.services import estimate_cost
    from src.tiktok_shop.services.pilot_tracker import update_pilot_progress
    from src.tiktok_shop.utils.logging_setup import log_error, log_info

    LOGGER = "tiktok_shop.runner"

    user_repo = UserRepo()
    product_repo = ProductRepo()
    gen_repo = GenerationRepo()

    user = user_repo.get(p["user_id"])
    product = product_repo.get(p["product_id"])
    if user is None or product is None:
        log_error(LOGGER, "Usuario o producto no encontrados",
                  job_id=job.id, user_id=p.get("user_id"), product_id=p.get("product_id"))
        raise RuntimeError("Usuario o producto no encontrados.")

    if tier not in VIDEO_MODELS:
        log_error(LOGGER, "Tier desconocido", job_id=job.id, tier=tier)
        raise ValueError(f"Tier desconocido: {tier}")

    log_info(LOGGER, "Job iniciado",
             job_id=job.id, tier=tier, duration=p.get("duration"),
             resolution=p.get("resolution"), user=user.username, product=product.slug,
             shoppable=p.get("is_shoppable"),
             strategy=video_strategy,
             camera_style=strategy_cfg.get("camera_style"),
             photo_strategy=strategy_cfg.get("photo_strategy"))

    # Selección de fotos: prefiere `generated`, fallback a `source`.
    photos_list, photos_source = product.photos.best_available()
    photo_paths = [
        ph.local_path for ph in photos_list
        if ph.local_path and os.path.exists(ph.local_path)
    ]
    if not photo_paths:
        raise RuntimeError(
            f"El producto {product.slug} no tiene fotos válidas en photos_source ni photos_generated."
        )

    model_def = VIDEO_MODELS[tier]
    is_prompt_only = model_def["type"] == "prompt_only"
    strategy_key = model_def["strategy"]

    # Crear registro inicial
    gen = VideoGeneration(
        user_id=user.id,
        product_id=product.id,
        tier_used=tier,
        model_used=model_def.get("model_id") or "",
        duration_seconds=int(p.get("duration", 15) if not is_prompt_only else (8 if tier == "veo3_prompt_only" else 0)),
        resolution=p.get("resolution", "720p"),
        clip_strategy=strategy_key,
        language=p.get("language", "es"),
        video_type="shoppable" if p.get("is_shoppable") else "normal",
        ai_disclosure=bool(p.get("ai_disclosure", True)),
        hook=HookUsed(category=p.get("hook_category", "general"), text=p.get("hook_text", "")),
        voice_used=VoiceUsed(
            type="tts_preset",
            voice_id=p.get("voice_id", "Spanish_EnergeticBoy"),
            name=p.get("voice_id"),
        ),
        photos_source=photos_source,
        photos_used=[ph.filename for ph in photos_list if ph.filename],
        generation_status=GenerationStatus.GENERATING,
    )
    gen_repo.save(gen)

    try:
        # ================================================================
        # Branch A: Nano Banana 2 (prompt-only, no usa strategist)
        # ================================================================
        if tier == "nano_banana_prompt_only":
            return _run_nano_banana(
                on_log=on_log, on_progress=on_progress,
                gen=gen, gen_repo=gen_repo, product=product,
                photo_paths=photo_paths, params=p,
                generate_nano_banana_prompt=generate_nano_banana_prompt,
            )

        # ================================================================
        # Resto de tiers usan strategist + analyzer
        # ================================================================
        on_progress(0.08, "🔬 Analizando producto…")
        on_log("🔬 Analizando producto con Gemini…")
        analysis = (
            {"key_features": product.key_features, "selling_points": product.selling_points}
            if product.key_features else analyze_product(photo_paths)
        )

        on_progress(0.20, "🧠 Generando estrategia…")
        on_log("🧠 Generando estrategia (hook + script + estructura)…")
        strategy = generate_strategy(
            analysis,
            audience=p.get("audience", "Generalista"),
            hook_category=p.get("hook_category", "curiosity"),
            duration_seconds=gen.duration_seconds,
            language=gen.language,
            product_name=product.name,
            extra_directives=p.get("hook_text", ""),
            video_strategy=video_strategy,   # FUNC 5
        )
        gen.voiceover_script = strategy.get("voiceover_script", "")
        gen.tiktok_shop_metadata = TikTokShopVideoMeta(
            caption_template=strategy.get("hook_text", ""),
            hashtags=strategy.get("tiktok_hashtags", []),
            human_presence=bool(strategy.get("human_presence_required", True)),
        )

        # ================================================================
        # Branch B: Veo3 prompt-only
        # ================================================================
        if tier == "veo3_prompt_only":
            on_progress(0.55, "📝 Generando prompt Veo 3…")
            on_log("📝 Generando prompt Veo 3 (8s, single shot)…")
            style = (product.video_config.preferred_styles or ["cinematic_premium"])[0]
            veo_prompt = generate_veo3_prompt(strategy, style=style)
            gen.veo3_prompt = veo_prompt
            gen.duration_seconds = 8
            gen.generation_status = GenerationStatus.MANUAL_PENDING
            gen.cost = VideoCost(video_generation=0.0, voice_tts=0.0, total=0.0)
            gen.completed_at = _iso_now()
            gen_repo.save(gen)

            txt_path = _save_prompt_txt(p, gen.id, "veo3", veo_prompt)
            on_progress(1.0, "✅ Prompt Veo 3 listo")
            on_log("✅ Prompt Veo 3 generado. Cópialo desde Histórico → 📋")
            return txt_path

        # ================================================================
        # Branch C: Seedance auto (standard / advanced / pro)
        # ================================================================
        from src.tiktok_shop.config import RESOLUTIONS
        from src.tiktok_shop.utils.duration_splitter import split_duration

        # Estimación inicial — se guarda en cost.estimated_at_creation
        est = estimate_cost(
            tier=tier, duration=gen.duration_seconds, resolution=gen.resolution,
            voice_chars=len(strategy.get("voiceover_script") or "") or gen.duration_seconds * 18,
        )
        gen.cost = VideoCost(
            video_generation=est["video_generation"],
            voice_tts=est["voice_tts"],
            total=est["total"],
            estimated_at_creation=est["total"],
        )
        gen_repo.save(gen)

        on_progress(0.30, "🎬 Generando prompts por clip…")
        on_log(f"🎬 Generando prompts Seedance ({tier} / {strategy_key})…")
        # FUNC 3: el usuario pudo asignar fotos manualmente a clips (i2v) o
        # elegir el subset de fotos referencia (pro). Si no hay overrides en
        # params, el director auto-asigna como antes.
        clip_overrides = p.get("clip_photo_overrides")
        pro_overrides = p.get("pro_ref_photo_overrides")
        if clip_overrides:
            on_log(f"📌 Asignación manual de fotos por clip: {clip_overrides}")
        if pro_overrides:
            on_log(f"📌 Subset manual de fotos referencia (Pro): {pro_overrides}")
        seedance_specs = generate_seedance_prompts(
            strategy,
            tier=tier,
            style=(product.video_config.preferred_styles or ["asmr_macro"])[0],
            photos_count=len(photo_paths),
            clip_photo_overrides=clip_overrides,
            pro_ref_photo_overrides=pro_overrides,
            camera_style=strategy_cfg.get("camera_style", "varied_contained"),
        )

        # Para Standard/Advanced, ajustamos la duración por clip a lo que
        # devuelva `split_duration(total, tier)`. El director ya devolvió
        # una lista con duraciones por clip, pero pueden no respetar los
        # límites Atlas — los normalizamos.
        if isinstance(seedance_specs, list):
            target_clips = split_duration(gen.duration_seconds, tier, video_strategy)
            if len(target_clips) != len(seedance_specs):
                on_log(
                    f"ℹ️ Director devolvió {len(seedance_specs)} clips, splitter "
                    f"sugiere {len(target_clips)}. Ajustando duraciones."
                )
                # Recortar o extender la lista al len correcto
                if len(seedance_specs) < len(target_clips):
                    last = seedance_specs[-1]
                    while len(seedance_specs) < len(target_clips):
                        clone = dict(last)
                        clone["clip_idx"] = len(seedance_specs)
                        seedance_specs.append(clone)
                else:
                    seedance_specs = seedance_specs[:len(target_clips)]
            for i, spec in enumerate(seedance_specs):
                spec["clip_idx"] = i
                spec["duration"] = target_clips[i]

            # FUNC 5: photo_strategy=smooth_transitions fuerza misma foto base
            # en todos los clips para máxima continuidad (Cinematográfico).
            # Solo se aplica si el usuario NO hizo override manual de fotos.
            if (
                strategy_cfg.get("photo_strategy") == "smooth_transitions"
                and not clip_overrides
            ):
                for spec in seedance_specs:
                    spec["ref_photo_index"] = 0
                on_log(
                    "🎬 Cinematográfico: todos los clips usan foto base 0 "
                    "(smooth transitions)"
                )
            elif (
                strategy_cfg.get("photo_strategy") == "rotate"
                and not clip_overrides
            ):
                # rotate_smart: en Dinámico, asigna fotos evitando repetición
                # adyacente y matcheando tipo de plano con purpose del clip
                # (hook→packshot/macro, demo→in_use/detail, cta→lifestyle).
                from src.queue.runners import _rotate_smart_assignment
                video_structure = strategy.get("video_structure", [])
                photos_for_assignment = [
                    {"type": ph.type, "filename": ph.filename}
                    for ph in photos_list
                    if not ph.deleted
                ]
                _rotate_smart_assignment(
                    seedance_specs,
                    photos=photos_for_assignment,
                    video_structure=video_structure,
                )
                on_log(
                    "⚡ Dinámico: rotate_smart — fotos asignadas por purpose "
                    f"({[s['ref_photo_index'] for s in seedance_specs]})"
                )

            gen.video_prompts = [ClipPrompt(**spec) for spec in seedance_specs]
            gen.num_clips = len(seedance_specs)
        else:
            # Pro: dict único; respetamos la duración total del usuario.
            spec = seedance_specs
            spec["duration"] = gen.duration_seconds
            gen.video_prompts = [ClipPrompt(
                clip_idx=0,
                duration=int(spec.get("duration", 15)),
                ref_photo_indices=list(spec.get("ref_photos_indices", [])),
                prompt=spec.get("prompt", ""),
            )]
            gen.num_clips = 1

        # Voz MiniMax
        on_progress(0.42, "🎙️ Generando voz MiniMax…")
        on_log("🎙️ Generando voz con MiniMax TTS…")
        from src.locutor import generate_single_audio
        voice_dir = os.path.join(p.get("temp_folder", "./temp_work"), f"shop_{gen.id}")
        os.makedirs(voice_dir, exist_ok=True)
        voice_mp3 = os.path.join(voice_dir, "voice.mp3")
        generate_single_audio(
            gen.voiceover_script,
            voice_mp3,
            voice_id_override=gen.voice_used.voice_id,
        )

        # Atlas render
        on_progress(0.55, "🎥 Atlas Cloud renderizando clips…")
        from src.tiktok_shop.pipeline.seedance_renderer import render_seedance_clips
        clip_paths = render_seedance_clips(
            tier=tier,
            clip_specs=seedance_specs,
            photo_paths=photo_paths,
            resolution=gen.resolution,
            output_dir=voice_dir,
            log_callback=on_log,
        )

        # Compose
        on_progress(0.80, "🎬 Componiendo vídeo final…")
        res_def = RESOLUTIONS.get(gen.resolution, RESOLUTIONS["720p"])
        target_size = (res_def["width"], res_def["height"])
        composed_path = os.path.join(voice_dir, "composed.mp4")
        compose_shop_video(
            clip_paths=clip_paths,
            voice_mp3=voice_mp3,
            output_path=composed_path,
            strategy=strategy_key,
            size=target_size,
            language=gen.language,           # BUG-3: idioma forzado en captions
            # FUNC 5: crossfade y trim_head desde la estrategia
            crossfade_s=float(strategy_cfg.get("crossfade_s", 0.0) or 0.0),
            trim_head_s=float(strategy_cfg.get("trim_head_s", 0.05) or 0.05),
            log_callback=on_log,
        )

        # Subir a Drive sincronizado
        on_progress(0.92, "☁️ Copiando a Drive…")
        actual_chars = len(gen.voiceover_script or "")
        cost = estimate_cost(
            tier=tier, duration=gen.duration_seconds,
            resolution=gen.resolution, voice_chars=actual_chars,
        )
        gen.cost.video_generation = cost["video_generation"]
        gen.cost.voice_tts = cost["voice_tts"]
        gen.cost.total = cost["total"]
        gen.cost.actual_after_completion = cost["total"]
        final_path, meta_path = upload_video(
            src_video_path=composed_path,
            username=user.username,
            product_slug=product.slug,
            hook_category=gen.hook.category if gen.hook else "general",
            metadata=_build_metadata(gen, user, product),
        )
        gen.local_path = final_path
        gen.metadata_path = meta_path
        gen.generation_status = GenerationStatus.COMPLETED
        gen.completed_at = _iso_now()
        gen_repo.save(gen)

        if user.status == "pilot":
            update_pilot_progress(user, video_was_shoppable=bool(p.get("is_shoppable")))
            user_repo.save(user)

        on_progress(1.0, "✅ Vídeo TikTok Shop listo")
        on_log(f"✅ Vídeo guardado en {final_path}")
        log_info(LOGGER, "Job completado",
                 job_id=job.id, gen_id=gen.id, tier=tier,
                 cost_total=gen.cost.total,
                 cost_estimated=gen.cost.estimated_at_creation,
                 final_path=final_path)
        return final_path

    except Exception as e:
        gen.generation_status = GenerationStatus.FAILED
        gen.error = str(e)
        gen.completed_at = _iso_now()
        gen_repo.save(gen)
        log_error(LOGGER, "Job falló",
                  job_id=job.id, gen_id=gen.id, tier=tier,
                  error_type=type(e).__name__, error=str(e))
        raise


def _run_nano_banana(*, on_log, on_progress, gen, gen_repo, product, photo_paths, params, generate_nano_banana_prompt) -> str:
    """Sub-runner para tier nano_banana_prompt_only."""
    from src.tiktok_shop.models import GenerationStatus, VideoCost

    on_progress(0.30, "🍌 Generando prompt Nano Banana 2…")
    on_log("🍌 Generando prompt Nano Banana 2 para fotos premium…")
    description = " ".join(filter(None, [
        product.brand or "",
        " · ".join(product.selling_points[:3]),
    ])) or product.name
    use_cases = product.video_config.preferred_styles or ["packshot", "lifestyle", "macro"]

    nb_prompt = generate_nano_banana_prompt(
        product_name=product.name,
        product_description=description,
        use_cases=use_cases,
        n_angles=int(params.get("n_angles", 5)),
        photo_paths=photo_paths,
    )
    gen.nano_banana_prompt = nb_prompt
    gen.generation_status = GenerationStatus.MANUAL_PENDING
    gen.cost = VideoCost(total=0.0)
    gen.completed_at = _iso_now()
    gen_repo.save(gen)

    txt_path = _save_prompt_txt(params, gen.id, "nano_banana", nb_prompt)
    on_progress(1.0, "✅ Prompt Nano Banana 2 listo")
    on_log("✅ Prompt Nano Banana 2 generado. Pega en Gemini chat con las fotos source.")
    return txt_path


def _save_prompt_txt(params: dict, gen_id: str, kind: str, prompt: str) -> str:
    txt_path = os.path.join(
        params.get("temp_folder", "./temp_work"),
        f"{kind}_prompt_{gen_id}.txt",
    )
    os.makedirs(os.path.dirname(txt_path), exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(prompt)
    return txt_path


def _build_metadata(gen, user, product) -> dict:
    return {
        "generation_id": gen.id,
        "user": user.username,
        "product": product.slug,
        "tier_used": gen.tier_used,
        "model_used": gen.model_used,
        "clip_strategy": gen.clip_strategy,
        "video_type": gen.video_type,
        "ai_disclosure": gen.ai_disclosure,
        "tiktok_shop": gen.tiktok_shop_metadata.model_dump(),
        "cost": gen.cost.model_dump(),
        "voiceover_script": gen.voiceover_script,
        "hook": gen.hook.model_dump() if gen.hook else None,
        "video_prompts": [cp.model_dump() for cp in gen.video_prompts],
        "photos_source": gen.photos_source,
        "photos_used": gen.photos_used,
        "created_at": gen.created_at,
    }


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# RUNNER: EDITOR AUTO (Programa 3)
# ============================================================
def run_editor_auto(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    """Pipeline Editor Auto: ejecuta el flujo de herramientas del usuario
    sobre un vídeo input subido manualmente.

    Params esperados en job.params:
      - user_id: id del EditorUser
      - input_path: ruta absoluta al MP4 subido
      - temp_folder: carpeta temporal para archivos intermedios
    """
    # Logs tempranos — confirman al usuario que el runner arrancó y que
    # los imports funcionaron. Sin esto, un ImportError silencioso aquí
    # dejaba el job en "Iniciando…" sin pistas.
    on_progress(0.005, "🚀 Cargando pipeline Editor Auto…")
    on_log("[editor_auto] Worker arrancado, importando pipeline…")
    from src.editor_auto.pipeline import run_editor_auto_pipeline

    p = job.params
    user_id = p["user_id"]
    input_path = p["input_path"]
    temp_folder = p.get("temp_folder", "./temp_work")
    script = (p.get("script") or "").strip() or None
    # Si el job vino del workflow "entrada→cola→…", `source` = "entrada"
    # y el runner gestiona el ciclo de vida del input tras la ejecución:
    #   éxito → mueve cola/<file> → recuperacion/<file>
    #   fallo → mueve cola/<file> → entrada/<file> (admin re-encola)
    # Para upload directo (campo `file` en /enqueue), `source` no existe
    # y no se toca nada (compat con flujo anterior).
    source = p.get("source")
    source_filename = p.get("source_filename")

    on_log(f"[editor_auto] user_id={user_id} · input={os.path.basename(input_path)}")
    if source == "entrada" and source_filename:
        on_log(f"[editor_auto] source=entrada · gestiono ciclo cola↔recuperacion/entrada")
    if script:
        on_log(f"[editor_auto] script · {len(script)} chars (modo scripted)")
    on_progress(0.01, "📂 Resolviendo usuario y carpetas…")

    try:
        result = run_editor_auto_pipeline(
            user_id=user_id,
            input_video_path=input_path,
            job_id=job.id,
            temp_folder=temp_folder,
            on_log=on_log,
            on_progress=on_progress,
            script=script,
            # Pasamos el filename original para que el output se llame
            # `<stem>_editado.mp4` en lugar del timestamped legacy.
            source_filename=source_filename
            if source == "entrada" else None,
        )
    except Exception:
        # Fallo del pipeline: devolver el input a `entrada/` para que el
        # admin pueda reencolarlo cuando quiera. Si la mudanza falla
        # (FS issues), no anulamos el error original.
        if source == "entrada" and source_filename:
            try:
                user_name = p.get("user_name") or ""
                from src.editor_auto.services import folder_manager
                folder_manager.move_file(
                    user_name, "cola", "entrada", source_filename,
                )
                on_log(
                    f"[editor_auto] ↩ Job fallido → input devuelto a entrada/"
                )
            except Exception as cleanup_err:
                on_log(
                    f"[editor_auto] ⚠️ no pude devolver cola→entrada: {cleanup_err}"
                )
        raise

    # Éxito: mover original a recuperacion/ (preserva por si re-editar).
    if source == "entrada" and source_filename:
        try:
            user_name = p.get("user_name") or ""
            from src.editor_auto.services import folder_manager
            folder_manager.move_file(
                user_name, "cola", "recuperacion", source_filename,
            )
            on_log(
                f"[editor_auto] 📦 Job OK → original cola → recuperacion/"
            )
        except Exception as cleanup_err:
            on_log(
                f"[editor_auto] ⚠️ no pude mover cola→recuperacion: {cleanup_err}"
            )
    return result


# ============================================================
# Dispatch
# ============================================================
_RUNNERS: dict[JobMode, Callable[[Job, OnLog, OnProgress], str]] = {
    JobMode.PRESIDENTS: run_presidents,
    JobMode.PRONOSTICOS: run_pronosticos,
    JobMode.SUBS_AUTO: run_subs_auto,
    JobMode.COPYRIGHT: run_copyright,
    JobMode.CONSTRUCCION_POV: run_construccion_pov,
    JobMode.TIKTOK_SHOP: run_tiktok_shop,
    JobMode.EDITOR_AUTO: run_editor_auto,
}


_MODE_TO_PROGRAM: dict[JobMode, str] = {
    JobMode.PRESIDENTS: "creator_reward",
    JobMode.PRONOSTICOS: "creator_reward",
    JobMode.SUBS_AUTO: "creator_reward",
    JobMode.COPYRIGHT: "creator_reward",
    JobMode.CONSTRUCCION_POV: "creator_reward",
    JobMode.TIKTOK_SHOP: "tiktok_shop",
    JobMode.EDITOR_AUTO: "editor_auto",
}


def dispatch_job(job: Job) -> None:
    """Llamado por el worker thread del JobQueue. Orquesta el runner
    y rellena `job.result_path` o lanza excepción (que el worker
    captura y marca como FAILED).

    Envuelve la ejecución en `cost_tracking.start_job` + `finalize_and_persist`
    para registrar el coste agregado del job en Redis. Las APIs externas
    (OpenAI, MiniMax, Atlas) escriben sus líneas dentro del tracker via
    contextvar."""
    runner = _RUNNERS.get(job.mode)
    if runner is None:
        raise RuntimeError(f"Modo desconocido: {job.mode}")

    def _on_log(msg: str) -> None:
        job.append_log(msg)

    def _on_progress(pct: float, label: str) -> None:
        # Si se solicitó cancelación, abortar limpio
        if job.params.get("_cancel_requested"):
            raise RuntimeError("Cancelado por el usuario")
        job.progress = max(0.0, min(1.0, float(pct)))
        if label:
            job.progress_label = label

    # Activar cost tracking. NUNCA falla — si Redis no está, simplemente
    # no persiste pero el runner sigue.
    try:
        from src import cost_tracking
        program = _MODE_TO_PROGRAM.get(job.mode, "creator_reward")
        # Para Editor Auto el "user" relevante es el EditorUser.name (lo que
        # configura el flujo), no el operador autenticado que encoló. Esto
        # permite filtrar costes por EditorUser en /costs y agrupar gasto
        # por persona/canal sin mezclar con operadores.
        if job.mode == JobMode.EDITOR_AUTO:
            cost_user = job.params.get("user_name") or job.enqueued_by
        else:
            cost_user = job.enqueued_by

        # Meta arbitraria que sobrevive en `cost:job:{id}` y aparece en
        # /costs. Para editor_auto guardamos las tools usadas + combo
        # ordenado para agrupar.
        meta: dict = {}
        if job.mode == JobMode.EDITOR_AUTO:
            tools_used = list(job.params.get("tools_used") or [])
            meta["tools"] = tools_used
            meta["tools_key"] = "+".join(sorted(tools_used)) if tools_used else "(empty)"
            meta["editor_user"] = job.params.get("user_name")

        cost_tracking.start_job(
            job_id=job.id,
            program=program,
            mode=job.mode.value,
            user=cost_user,
            product_id=job.params.get("product_id"),
            title=job.title,
            meta=meta,
        )
    except Exception as e:
        print(f"[dispatch] cost_tracking.start_job failed: {e}")

    try:
        result_path = runner(job, _on_log, _on_progress)
        job.result_path = result_path
    finally:
        try:
            from src import cost_tracking
            cost_tracking.finalize_and_persist()
        except Exception as e:
            print(f"[dispatch] cost_tracking.finalize failed: {e}")


# ============================================================
# rotate_smart helper — asignación inteligente de fotos por clip
# (estrategia "Dinámico TikTok" — FUNC 5 / fix tail-rotate-ffprobe)
# ============================================================
# Mapping purpose del clip → tipos de plano preferidos. Cada purpose
# del strategist se intenta matchear contra el `type` de las fotos.
_PURPOSE_TO_TYPE_PREFERENCE: dict[str, list[str]] = {
    "hook":         ["packshot", "macro"],
    "intro":        ["packshot", "macro"],
    "reveal":       ["packshot", "macro"],
    "demo":         ["in_use", "detail"],
    "use":          ["in_use", "detail"],
    "feature":      ["detail", "macro"],
    "social_proof": ["lifestyle", "in_use"],
    "lifestyle":    ["lifestyle"],
    "cta":          ["lifestyle", "packshot"],
    "outro":        ["lifestyle", "packshot"],
}


def _photos_by_type(photos: list[dict]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for i, ph in enumerate(photos):
        t = (ph.get("type") or "").lower()
        if t:
            out.setdefault(t, []).append(i)
    return out


def _rotate_smart_assignment(
    specs: list[dict],
    *,
    photos: list[dict],
    video_structure: list[dict] | None = None,
) -> None:
    """Asigna `ref_photo_index` a cada spec evitando repetición adyacente
    y matcheando `type` de la foto con `purpose` del clip cuando es posible.

    Mutates `specs` in-place. Si `photos` está vacío, no hace nada.
    """
    n_photos = len(photos)
    if n_photos == 0:
        return
    by_type = _photos_by_type(photos)
    structure = video_structure or []

    used_history: list[int] = []
    for i, spec in enumerate(specs):
        purpose_raw = (
            (structure[i].get("purpose") or "") if i < len(structure) else ""
        ).lower()
        # Buscar match: el primer purpose-keyword presente en `purpose_raw`
        preferred_types: list[str] = []
        for keyword, types in _PURPOSE_TO_TYPE_PREFERENCE.items():
            if keyword in purpose_raw:
                preferred_types = types
                break

        prev = used_history[-1] if used_history else None

        # 1ª preferencia: foto del tipo preferido y NO usada en clip anterior
        candidates: list[int] = []
        for t in preferred_types:
            for idx in by_type.get(t, []):
                if idx != prev:
                    candidates.append(idx)
        # 2ª: cualquier foto del tipo preferido (si solo hay 1, repetimos)
        if not candidates:
            for t in preferred_types:
                candidates.extend(by_type.get(t, []))
        # 3ª: cualquier foto distinta de la del clip anterior
        if not candidates:
            candidates = [j for j in range(n_photos) if j != prev]
        # 4ª: cualquier foto (último recurso)
        if not candidates:
            candidates = list(range(n_photos))

        chosen = candidates[0]
        spec["ref_photo_index"] = chosen
        used_history.append(chosen)
