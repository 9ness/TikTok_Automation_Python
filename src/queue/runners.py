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

    MAX_ATTEMPTS = p.get("calibration_max_attempts", 3)
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
                on_log(
                    f"⚠️ Máximo de intentos alcanzado. Continuando con "
                    f"{total_dur:.1f}s. Calibrador actualizó target a "
                    f"{next_target} para próximas ejecuciones."
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
                    }
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
            except Exception as e:
                on_log(f"❌ Error subs: {e}")
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
        words = transcribe_with_reference(
            tmp_audio,
            reference_script=ref,
            model_size=p.get("model_size", "small"),
            language=p.get("language"),
            audio_type=p.get("audio_type", "speech"),
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
    )
    on_progress(1.0, "✅ Limpieza completada")
    return final


# ============================================================
# Dispatch
# ============================================================
_RUNNERS: dict[JobMode, Callable[[Job, OnLog, OnProgress], str]] = {
    JobMode.PRESIDENTS: run_presidents,
    JobMode.PRONOSTICOS: run_pronosticos,
    JobMode.SUBS_AUTO: run_subs_auto,
    JobMode.COPYRIGHT: run_copyright,
}


def dispatch_job(job: Job) -> None:
    """Llamado por el worker thread del JobQueue. Orquesta el runner
    y rellena `job.result_path` o lanza excepción (que el worker
    captura y marca como FAILED)."""
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

    result_path = runner(job, _on_log, _on_progress)
    job.result_path = result_path
