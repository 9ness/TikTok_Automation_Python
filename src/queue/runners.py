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
import hashlib
import os
import shutil
import time
import traceback
from datetime import datetime
from pathlib import Path
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
) -> tuple[str, list[dict]]:
    """Versión sin Streamlit de generate_video_pipeline. Devuelve la ruta del
    MP4 generado + `reveals` (lista {puesto, name, reveal_time} para la
    variante números, con el instante en que arranca cada segmento)."""
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
    reveals: list[dict] = []
    cum_dur = 0.0
    n_segments = max(1, len(final_audio_order))

    # Construcción de segmentos: 60% del rango destinado a esta fase
    seg_lo = progress_lo
    seg_hi = progress_lo + (progress_hi - progress_lo) * 0.6

    for i, aud in enumerate(final_audio_order):
        try:
            name = os.path.splitext(os.path.basename(aud))[0]
            is_intro = "intro" in name.lower()
            try:
                parts = name.split("_")
                if is_intro:
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
                # Reveal de la variante números: el nombre aparece cuando
                # arranca su segmento (la intro no cuenta como presidente).
                if not is_intro and puesto and puesto >= 1:
                    reveals.append({
                        "puesto": int(puesto),
                        "name": presi,
                        "reveal_time": float(cum_dur),
                    })
                cum_dur += seg.duration
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
    return out_path, reveals


# ============================================================
# RUNNER: PRESIDENTES (auto factory: guion → audio → vídeo → subs → hook)
# ============================================================
def run_presidents(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    p = job.params
    config = p["config"]

    # La variante números sustituye al hook box animado.
    numbers_variant = bool(p.get("numbers_variant"))
    hook_active = bool(p.get("hook_enabled")) and not numbers_variant

    # Pesos de los pasos
    w_script = 0.05
    w_audio = 0.15
    w_video = 0.50
    w_subs = 0.20 if p.get("subs_enabled") else 0.0
    w_hook = 0.10 if hook_active else 0.0
    w_numbers = 0.10 if numbers_variant else 0.0
    w_total = w_script + w_audio + w_video + w_subs + w_hook + w_numbers
    cum = []
    acc = 0.0
    for w in (w_script, w_audio, w_video, w_subs, w_hook, w_numbers):
        acc += w / w_total
        cum.append(acc)
    # cum[0..5] = pct acumulado tras: guion, audio, video, subs, hook, números

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
    cps = wc.get_cps(type_key)
    on_log(
        f"🎯 Calibración tipo='{type_key}' → target inicial: {target_words} "
        f"palabras · cps≈{cps:.1f} (gate {wc.EST_GATE_LO_S:.0f}-{wc.EST_GATE_HI_S:.0f}s "
        f"estimados antes de gastar TTS)"
    )

    # Reintentos de TTS (caro) — el gate de guion ya deja la longitud cerca,
    # así que con 2 basta. Reintentos de GUION (barato, ~$0.0004) hasta 8.
    MAX_TTS_ATTEMPTS = p.get("calibration_max_attempts", 2)
    MAX_SCRIPT_TRIES = p.get("calibration_script_tries", 8)
    script_data = None
    txt_output = None
    audio_output_folder = None
    total_dur = 0.0
    success_in_range = False

    def _count_script_chars(folder: str) -> int:
        """Suma de caracteres de los .txt (lo que MiniMax facturará)."""
        total = 0
        try:
            for fn in os.listdir(folder):
                if fn.lower().endswith(".txt"):
                    with open(os.path.join(folder, fn), "r", encoding="utf-8") as fh:
                        total += len(fh.read().strip())
        except Exception:
            pass
        return total

    try:
        for tts_attempt in range(1, MAX_TTS_ATTEMPTS + 1):
            # ----- Búsqueda BARATA de guion (sin TTS): regenera hasta que la
            # duración ESTIMADA por nº de caracteres caiga en la banda gate.
            best = None     # (script_data, txt_output, chars, est) más cercano
            chosen = None   # guion que cae dentro del gate
            for s_try in range(1, MAX_SCRIPT_TRIES + 1):
                sd = guionista.generate_script(
                    user_topic=p.get("topic"),
                    creative_mode=p.get("creative_mode", False),
                    title_prefix=p.get("title_prefix", "The 5"),
                    include_history=p.get("include_history", True),
                    include_hook=p.get("include_hook", True),
                    top_count=p.get("top_count", 5),
                    target_total_words=target_words,
                )
                to = guionista.save_scripts_to_txt(sd, top_count=p.get("top_count", 5))
                chars = _count_script_chars(to)
                est = wc.estimate_duration_s(chars, cps)
                on_log(
                    f"📝 [TTS {tts_attempt}/{MAX_TTS_ATTEMPTS} · guion "
                    f"{s_try}/{MAX_SCRIPT_TRIES}] {chars} chars ≈ {est:.0f}s "
                    f"(cps {cps:.1f}, target {target_words}w)"
                )
                if wc.estimate_in_gate(est):
                    if best is not None and best[1] != to:
                        shutil.rmtree(best[1], ignore_errors=True)
                    chosen = (sd, to, chars, est)
                    break
                # Guarda el más cercano al medio; descarta el resto al vuelo.
                if best is None or abs(est - wc.TARGET_MID_S) < abs(best[3] - wc.TARGET_MID_S):
                    if best is not None:
                        shutil.rmtree(best[1], ignore_errors=True)
                    best = (sd, to, chars, est)
                else:
                    shutil.rmtree(to, ignore_errors=True)
                # Nudge barato del target de palabras usando la estimación.
                target_words = wc.adjust_target_words(target_words, est)

            sel = chosen or best
            if not sel:
                raise RuntimeError("No se pudo generar guion para calibración")
            script_data, txt_output, sel_chars, sel_est = sel
            on_log(
                (f"✅ Guion en rango estimado ({sel_est:.0f}s)"
                 if chosen else
                 f"⚠️ Ningún guion cayó en banda; uso el más cercano ({sel_est:.0f}s)")
                + " — sintetizando audio"
            )
            on_progress(cum[0], f"🎙️ TTS (intento {tts_attempt})…")

            # ----- AUDIO (caro) — una sola tanda por intento de TTS -----
            audio_output_folder = locutor.generate_audios_from_text_folder(
                txt_output, config["paths"]["resources_library"]
            )
            if not audio_output_folder:
                raise RuntimeError("No se generaron audios MiniMax")
            total_dur = wc.measure_audio_folder_duration(audio_output_folder)
            # Auto-ajuste del cps con la medición REAL → mejora el gate futuro.
            cps = wc.save_cps(type_key, sel_chars, total_dur)
            on_log(
                f"⏱️ Duración real: {total_dur:.1f}s (estimada {sel_est:.0f}s) "
                f"· cps→{cps:.1f}"
            )

            in_range, next_target = wc.calibration_decision(
                type_key, target_words, total_dur
            )
            # Aceptamos cualquier vídeo ≥ mínimo (60s) — el gate ya lo dejó
            # cerca del minuto. Solo re-sintetizamos si quedó CORTO (no monetiza).
            if total_dur >= wc.TARGET_MIN_S:
                success_in_range = in_range
                on_log(
                    f"✅ Duración OK ({total_dur:.1f}s). "
                    + ("En sweet spot 60-65s." if in_range else "Aceptable (≥60s).")
                )
                break

            if tts_attempt == MAX_TTS_ATTEMPTS:
                on_log(
                    f"❌ Tras {MAX_TTS_ATTEMPTS} tandas TTS, duración "
                    f"{total_dur:.1f}s < {wc.TARGET_MIN_S:.0f}s mínimo. "
                    f"Calibrador guardó target {next_target}."
                )
                raise RuntimeError(
                    f"Duración final {total_dur:.1f}s < {wc.TARGET_MIN_S:.0f}s mínimo "
                    f"tras {MAX_TTS_ATTEMPTS} tandas TTS. Reintenta — el calibrador "
                    f"ha aprendido y debería converger."
                )

            on_log(
                f"🔄 Vídeo corto ({total_dur:.1f}s). Reajustando "
                f"{target_words}→{next_target} palabras y regenerando…"
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
        final_video_path, numbers_reveals = _render_presidents_video_headless(
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

        # ----- 5. HOOK (opcional; se omite en la variante números) -----
        if hook_active:
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

        # ----- 6. VARIANTE NÚMEROS (opcional; sustituye al hook box) -----
        if numbers_variant:
            on_progress(cum[4], "🔢 Aplicando variante números…")
            try:
                from src.numbers_overlay import (
                    DEFAULT_NUMBERS_STYLE, add_numbers_overlay_to_video,
                )

                # Header de la variante números: preferimos el título COMPLETO
                # ("The 5 Worst Presidents…") sobre el hook_box_text corto
                # ("Worst Presidents"), que quedaba pobre como cabecera.
                header_text = (
                    (p.get("numbers_header_text") or "").strip()
                    or (script_data.get("video_title") or "").strip()
                    or (script_data.get("hook_box_text") or "").strip()
                    or "Top US Presidents"
                )
                numbers_style = {
                    **DEFAULT_NUMBERS_STYLE,
                    "mystery_text": p.get("numbers_mystery_text", "???"),
                    "header_text": p.get("numbers_header_text", ""),
                    "header_mode": p.get("numbers_header_mode", "all"),
                    "header_duration": p.get("numbers_header_duration", 5.0),
                    "header_animation": p.get("numbers_header_animation", "none"),
                    "header_y_position": p.get("numbers_header_y_position", 0.07),
                    "header_font_scale": p.get("numbers_header_font_scale", 0.024),
                    "header_text_color": p.get("numbers_header_text_color", "#0B0B0B"),
                    "header_box_color": p.get("numbers_header_box_color", "#FFFFFF"),
                    "header_shadow_color": p.get("numbers_header_shadow_color", "#1E01C4"),
                    "list_x_position": p.get("numbers_list_x_position", 0.07),
                    "list_y_position": p.get("numbers_list_y_position", 0.32),
                    "list_line_spacing": p.get("numbers_list_line_spacing", 0.105),
                    "number_font_scale": p.get("numbers_number_font_scale", 0.044),
                    "name_font_scale": p.get("numbers_name_font_scale", 0.036),
                    "number_color": p.get("numbers_number_color", "#FFFFFF"),
                    "number_medal_colors": p.get("numbers_number_medal_colors", True),
                    "number_color_gold": p.get("numbers_number_color_gold", "#FFD700"),
                    "number_color_silver": p.get("numbers_number_color_silver", "#C0C0C0"),
                    "number_color_bronze": p.get("numbers_number_color_bronze", "#CD7F32"),
                    "name_color": p.get("numbers_name_color", "#FFFFFF"),
                    "name_stroke_color": p.get("numbers_name_stroke_color", "#000000"),
                    "name_stroke_width": p.get("numbers_name_stroke_width", 3),
                }
                if p.get("numbers_font_path"):
                    numbers_style["font_path"] = p["numbers_font_path"]

                on_log(
                    f"🔢 Variante números: {len(numbers_reveals)} nombres, "
                    f"top {p.get('top_count', 5)}"
                )
                tmp_out = final_video_path + ".tmp.mp4"
                add_numbers_overlay_to_video(
                    final_video_path, header_text, numbers_reveals,
                    p.get("top_count", 5), numbers_style, tmp_out,
                    log_callback=on_log,
                )
                os.replace(tmp_out, final_video_path)
                on_log("✅ Variante números aplicada")
            except Exception as e:
                on_log(f"❌ Error variante números: {e}")
                print(f"[Presidents/NUMBERS] {traceback.format_exc()}")
            on_progress(cum[5], "🎉 Finalizando…")

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
        video_style=p.get("video_style", "standard"),
        photo_overrides=p.get("photo_overrides") or None,
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

    clean_mode = p.get("clean_mode", "Subtítulos Virales")

    if clean_mode == "Limpiar Metadata (Sin Tocar Subtítulos)":
        # No toca los subs originales ni añade texto → ni OCR ni Whisper.
        on_progress(0.10, "🧹 Anti-copy (zoom + metadatos), sin tocar subtítulos…")
        on_log("🧹 Modo limpiar metadata: sin OCR ni transcripción (no toca subs).")
        traj = []
        words = []
    else:
        on_progress(0.05, "🔍 Analizando subtítulos originales…")
        on_log("🔍 Mapeando trayectoria del texto original…")
        traj = cleaner.map_text_trajectory(p["input_path"], log_callback=on_log)
        # "Solo Limpiar" tapa subs originales pero no añade texto → sin Whisper.
        if clean_mode == "Solo Limpiar (Sin Subtítulos)":
            words = []
            on_log("🧼 Modo solo limpiar: sin transcripción ni subtítulos.")
        else:
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
        clean_mode=clean_mode,
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
        original_audio_volume=float(p.get("original_audio_volume", 0.60)),
        narration_volume=float(p.get("narration_volume", 1.20)),
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
    # `local_path` de Redis es la ruta absoluta del entorno DONDE se subió
    # la foto (Windows local en dev, Linux VPS en prod). Si Redis está
    # compartido entre entornos (Upstash) el path no existe en el otro
    # → reconstruimos desde slug + filename usando los helpers de config
    # que respetan el `TIKTOK_SHOP_ROOT_PATH` del entorno actual.
    from src.tiktok_shop.config import (
        product_photos_generated_folder,
        product_photos_source_folder,
    )

    def _resolve_photo_path(ph, source: str) -> str | None:
        # 1) Probamos el local_path persistido tal cual (caso mismo entorno).
        if ph.local_path and os.path.exists(ph.local_path):
            return ph.local_path
        # 2) Reconstruimos desde slug + filename + carpeta del entorno actual.
        folder = (
            product_photos_generated_folder(product.slug)
            if source == "generated"
            else product_photos_source_folder(product.slug)
        )
        candidate = os.path.join(folder, ph.filename)
        if os.path.exists(candidate):
            return candidate
        return None

    photo_paths = []
    for ph in photos_list:
        resolved = _resolve_photo_path(ph, photos_source)
        if resolved:
            photo_paths.append(resolved)
    if not photo_paths:
        raise RuntimeError(
            f"El producto {product.slug} no tiene fotos válidas en "
            f"photos_source ni photos_generated. Verifica que Drive Desktop "
            f"está sincronizando TIKTOK_SHOP/_products/{product.slug}/."
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
    # Link el gen_id al job → la UI de cola lo usa para hacer lookup
    # del Generation (cubre clips_renderer y otros campos persistidos).
    try:
        if isinstance(job.params, dict):
            job.params["gen_id"] = gen.id
    except Exception:
        pass

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

        # ── Pre-flight Atlas Cloud ──
        # Abortamos ANTES de gastar Gemini/MiniMax si Atlas está caído o
        # nuestra key está mal. Solo ~200ms de overhead, se ahorra ~$0.03
        # de Gemini+TTS en cada job en caso de Atlas down.
        on_progress(0.05, "🔌 Verificando Atlas Cloud…")
        from src.tiktok_shop.api.atlas_cloud import AtlasCloudClient
        _atlas_check = AtlasCloudClient()
        _atlas_ok, _atlas_msg = _atlas_check.healthcheck()
        on_log(f"🔌 Atlas: {_atlas_msg}")
        if not _atlas_ok:
            raise RuntimeError(
                f"Atlas Cloud no disponible: {_atlas_msg}. "
                f"Reintenta cuando vuelva a responder. No se ha gastado nada."
            )

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

        # Voz MiniMax — solo si voice_enabled=True (presets `kind=music`
        # piden voice_enabled=false desde el front; el vídeo sale MUDO y
        # el user añade trending audio al subir a TikTok, que da mejor
        # alcance que cualquier música embebida).
        voice_dir = os.path.join(p.get("temp_folder", "./temp_work"), f"shop_{gen.id}")
        os.makedirs(voice_dir, exist_ok=True)
        voice_mp3: str | None = None
        # El payload del enqueue mapea `voice_enabled` del frontend a la
        # clave `with_voice` en la cola (ver generations.py:_build_params).
        voice_enabled = bool(p.get("with_voice", True))
        if voice_enabled and (gen.voiceover_script or "").strip():
            on_progress(0.42, "🎙️ Generando voz MiniMax…")
            on_log("🎙️ Generando voz con MiniMax TTS…")
            from src.locutor import generate_single_audio
            voice_mp3 = os.path.join(voice_dir, "voice.mp3")
            generate_single_audio(
                gen.voiceover_script,
                voice_mp3,
                voice_id_override=gen.voice_used.voice_id,
            )
        else:
            on_progress(0.42, "🔇 Vídeo sin voz (preset música)…")
            on_log(
                "🔇 Skip MiniMax TTS — voice_enabled=false. El vídeo saldrá "
                "mudo; añade trending audio al subirlo a TikTok."
            )
            # Generamos un MP3 silencioso de la duración objetivo para que
            # `compose_shop_video` no rompa (su pipeline asume voice_mp3
            # como track principal). Whisper sobre silencio devuelve 0
            # palabras → no se renderizan subs (correcto para music preset).
            import subprocess
            voice_mp3 = os.path.join(voice_dir, "voice_silent.mp3")
            silence_dur = int(gen.duration_seconds or 10)
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-f", "lavfi",
                        "-i", f"anullsrc=channel_layout=mono:sample_rate=44100",
                        "-t", str(silence_dur),
                        "-q:a", "9", "-acodec", "libmp3lame", voice_mp3,
                    ],
                    check=True, capture_output=True,
                )
                on_log(f"🔇 Silencio {silence_dur}s generado → {voice_mp3}")
            except Exception as e:
                on_log(f"⚠️ No pude generar silencio: {e}. Compose puede fallar.")
                voice_mp3 = None

        # Video render — música → chain Hailuo→Kling→Wan; scripted → Seedance
        preset_kind = "music" if not voice_enabled else "scripted"
        if preset_kind == "music":
            on_progress(0.55, "🎵 Renderizando clips musicales (chain Hailuo/Kling/Wan)…")
            from src.tiktok_shop.pipeline.seedance_renderer import render_music_clips
            clip_paths, clip_renderers = render_music_clips(
                clip_specs=seedance_specs,
                photo_paths=photo_paths,
                resolution=gen.resolution,
                output_dir=voice_dir,
                log_callback=on_log,
            )
            # Persistimos qué modelo acabó renderizando cada clip — UI
            # de la cola lo muestra como badge ("🎵 Hailuo 02" o el que sea).
            try:
                gen.clips_renderer = clip_renderers
                from src.tiktok_shop.repos.generation_repo import GenerationRepo
                GenerationRepo().save(gen)
            except Exception:
                pass
            on_log(f"📦 Modelos usados por clip: {', '.join(clip_renderers)}")
        else:
            on_progress(0.55, "🎥 Renderizando clips i2v (Seedance)…")
            from src.tiktok_shop.pipeline.seedance_renderer import render_seedance_clips
            clip_paths = render_seedance_clips(
                tier=tier,
                clip_specs=seedance_specs,
                photo_paths=photo_paths,
                resolution=gen.resolution,
                output_dir=voice_dir,
                log_callback=on_log,
                kind=preset_kind,
            )

        # Compose
        on_progress(0.80, "🎬 Componiendo vídeo final…")
        res_def = RESOLUTIONS.get(gen.resolution, RESOLUTIONS["720p"])
        target_size = (res_def["width"], res_def["height"])
        composed_path = os.path.join(voice_dir, "composed.mp4")
        # Mapeo subtitle_style (formato VideoPreset) → captions_style
        # (formato editor.render_karaoke). Si el preset no manda subs
        # custom, dejamos None → editor usa `_default_caption_style`.
        # Conversión:
        #   size_px (sobre 1920px baseline) → font_scale = size_px / 1920
        #   color → text_color
        #   uppercase=True → case_mode "UPPERCASE", else "NONE"
        #   max_words_per_line → max_words_per_chunk
        #   position bottom_center → y_position_pct 0.70
        #   margin_x_pct → max_width_pct = 100 - 2*margin_x_pct (en frac)
        subs_raw = p.get("subtitle_style") or None
        captions_style_dict = None
        if subs_raw and bool(subs_raw.get("enabled", True)):
            size_px = int(subs_raw.get("size_px", 42))
            font_scale = max(0.018, min(0.080, size_px / 1920.0))
            margin_x = float(subs_raw.get("margin_x_pct", 8.0))
            max_w_pct = max(0.50, min(0.96, (100.0 - 2 * margin_x) / 100.0))
            pos = str(subs_raw.get("position") or "bottom_center")
            y_pct = {
                "top_center": 0.18, "top_left": 0.18, "top_right": 0.18,
                "middle_center": 0.50, "middle_left": 0.50, "middle_right": 0.50,
                "bottom_center": 0.70, "bottom_left": 0.70, "bottom_right": 0.70,
            }.get(pos, 0.70)
            captions_style_dict = {
                # Mantenemos default font_path; si el preset trae font
                # custom (path absoluto), lo respetamos.
                "font_path": str(subs_raw.get("font") or r"C:\Windows\Fonts\impact.ttf"),
                "font_scale": font_scale,
                "text_color": str(subs_raw.get("color") or "#FFFFFF"),
                "stroke_color": str(subs_raw.get("stroke_color") or "#000000"),
                "stroke_width": int(subs_raw.get("stroke_width", 5)),
                "pill_enabled": False,  # preset no usa pill por defecto
                "case_mode": "UPPERCASE" if subs_raw.get("uppercase") else "NONE",
                "max_words_per_chunk": int(subs_raw.get("max_words_per_line", 3)),
                "y_position_pct": y_pct,
                "highlight_color": str(subs_raw.get("highlight_color") or "#FFE066"),
                "max_width_pct": max_w_pct,  # respeta margen lateral safe zone
            }

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
            # Fase 3: overlays (hook box + CTA flecha) — sin overlays, dict
            # vacío hace que compose_shop_video los salte transparentemente.
            overlays=p.get("overlays") or None,
            captions_style=captions_style_dict,
            hook_text_fallback=strategy.get("hook_text", "") if isinstance(strategy, dict) else "",
            job_id=job.id,
            temp_folder=p.get("temp_folder", "./temp_work"),
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
    # Retoque MANUAL (editor de retoque): tramos a conservar + output a pisar.
    manual_keep_intervals = p.get("manual_keep_intervals")
    output_override = p.get("output_override")
    # Subida web: subcarpeta de salida por día + nombre limpio del original.
    output_subdir = p.get("output_subdir")
    web_source_filename = p.get("source_filename") if source != "entrada" else None

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
            # `<stem>_editado.mp4` en lugar del timestamped legacy. Para la
            # subida web (source != "entrada") usamos `web_source_filename`.
            source_filename=(source_filename if source == "entrada" else web_source_filename),
            manual_keep_intervals=manual_keep_intervals,
            output_override=output_override,
            output_subdir=output_subdir,
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
# RUNNER: VIRALIZACIÓN (Programa 4)
# ============================================================
def run_viralizacion_batch(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    """Genera un batch de vídeos POV/reacción (gancho + paisajes) para uno
    o varios ponentes y los sube a Drive al terminar.

    Params esperados en job.params:
      - ponentes: list[str] (slugs, ej ["pablo", "victor"])
      - cantidad: dict[str, int] (total de vídeos pedidos por ponente)
      - nombre_cuenta: str (carpeta destino en Drive)
      - music_rounds: int (rondas con música de fondo por audio, default 1)

    Sin cost tracking: no hay ninguna API de pago en este pipeline (todo
    ffmpeg + Whisper local + rclone) — ver VIRALIZACION_MODULE.md.
    """
    on_progress(0.0, "🚀 Cargando pipeline de Viralización…")
    from src.viralizacion.pipeline.batch import run_batch

    p = job.params
    result = run_batch(
        ponentes=list(p.get("ponentes") or []),
        cantidad=dict(p.get("cantidad") or {}),
        nombre_cuenta=p.get("nombre_cuenta") or "sin_nombre",
        music_rounds=int(p.get("music_rounds", 1)),
        round_styles=list(p.get("round_styles") or []) or None,
        styles_pool=list(p.get("styles_pool") or []) or None,
        on_log=on_log,
        on_progress=on_progress,
    )
    on_log(
        f"[viralizacion] batch {result['batch_id']} · {result['total_videos']} vídeos · "
        f"subidos a {result['remote_dirs']}"
    )
    # Un batch "partial" tenía el mismo aspecto que uno perfecto: sin esto, 14
    # de 15 vídeos fallidos se veían como job verde.
    failed = result.get("failed") or []
    upload_failed = result.get("upload_failed") or []
    if failed or upload_failed:
        if failed:
            on_log(f"[viralizacion] ⚠️ {len(failed)} vídeo(s) fallaron: {failed[:5]}")
        if upload_failed:
            on_log(
                f"[viralizacion] ⚠️ {len(upload_failed)} vídeo(s) NO llegaron a "
                f"Drive: {upload_failed[:5]}"
            )
        raise RuntimeError(
            f"Batch {result.get('status')}: {result['total_videos']} vídeo(s) OK "
            f"(ya en {result['remote_dirs'] or 'ningún destino'}), "
            f"{len(failed)} fallidos, {len(upload_failed)} sin subir. "
            f"Staging local: {result['staging_root']}. Revisa el log del job."
        )
    # No hay un único "archivo final" (son N vídeos por ponente). Se devuelve
    # la CARPETA DE DRIVE, no la de staging: la UI usa el último tramo del
    # `result_path` para buscar en Drive, y el staging lleva un uuid aleatorio
    # que allí no existe — el botón de Drive no encontraba nada.
    remotes = result.get("remote_dirs") or {}
    return next(iter(remotes.values()), result["staging_root"])


# ============================================================
# RUNNER: NICHO POV BOF — BACKUP / SYNC DEL DRIVE COMPARTIDO
# ============================================================
def run_nicho_pov_bof_backup(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    """Copia versionada de "Productos España" (Drive de un tercero).

    El admin de ese Drive borra todo periódicamente, así que esto detecta qué
    cambió desde la última copia y guarda solo la diferencia — o una copia
    completa nueva si cambió demasiado. Las copias son server-side.
    """
    from src.nicho_pov_bof.services import backup_sync

    p = job.params or {}
    result = backup_sync.run_sync(
        force_full=bool(p.get("force_full")),
        on_log=on_log,
        on_progress=on_progress,
    )

    on_log(
        f"[backup] modo={result['mode']} ({result['reason']}) · "
        f"+{result['n_added']} nuevos · ~{result['n_modified']} modificados · "
        f"-{result['n_deleted']} borrados en origen"
    )
    if result.get("dest"):
        on_log(f"[backup] destino: {result['dest']}")

    if result.get("failed"):
        raise RuntimeError(
            f"Backup incompleto: {result['copied']} copiados pero "
            f"{result['failed']} fallaron. Destino: {result.get('dest')}. "
            f"Primeros errores: {result.get('errors', [])[:3]}"
        )

    return result.get("dest") or "sin-cambios"


# ============================================================
# RUNNER: NICHO POV BOF — MONTAJE DE VÍDEO POR PRODUCTO
# ============================================================
def run_nicho_pov_bof_video(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    """Monta el vídeo final de UN producto (Fase 2 del Nicho POV BOF) y lo
    publica en Drive.

    Params esperados en job.params:
      - source, folder, producto: identifican el producto (carpeta del Drive
        compartido "Productos España" + número de producto dentro de ella).
      - raw_path: vídeo bruto subido por el operador (Veo3/Kling), en
        API_TEMP_ROOT.
      - sexo: "hombre" | "mujer" — el operador solo elige esto, la frase/voz
        salen sorteadas del banco de audios.
      - origen: "veo3" | "kling" — determina si hay que quitar marca de agua.
    """
    from src.nicho_pov_bof import config
    from src.nicho_pov_bof.pipeline import video_editor
    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import audio_bank

    p = job.params
    source = p["source"]
    folder = p["folder"]
    producto = p["producto"]
    raw_path = Path(p["raw_path"])
    sexo = p["sexo"]
    origen = p.get("origen", "")

    on_progress(0.02, "📝 Leyendo textos guardados…")
    textos = product_repo.get_product(source, folder, producto)
    if not textos:
        on_log(
            f"[nicho_pov_bof] sin textos guardados para producto {producto!r} "
            f"en {folder!r} — el bloque de texto saldrá vacío (¿faltó pulsar "
            "'Obtener textos'?)"
        )

    on_progress(0.06, "🔊 Preparando audio…")
    audio_raw = audio_bank.pick_random(sexo)
    audio_ready = audio_bank.prepare(audio_raw, on_log=on_log)
    on_log(f"[nicho_pov_bof] audio elegido: {audio_raw.name} → {audio_ready.name}")

    work_dir = raw_path.parent / f"work_{producto}_{raw_path.stem}"
    output_local = work_dir / "output.mp4"

    def _pipeline_progress(pct: float, label: str) -> None:
        # Reserva 0-0.08 para la prep de arriba y 0.92-1.0 para publicar en
        # Drive; el 84% restante es lo que reporta `video_editor.build_video`.
        on_progress(0.08 + pct * 0.84, label)

    video_editor.build_video(
        raw_video=raw_path,
        audio_path=audio_ready,
        textos=textos,
        origen=origen,
        output_path=output_local,
        work_dir=work_dir,
        layout=video_editor.layout_for_producto(producto, textos.get("cta", "")),
        con_gancho=bool(p.get("con_gancho", p.get("con_textos", True))),
        con_titulo=bool(p.get("con_titulo", p.get("con_textos", True))),
        con_cta=bool(p.get("con_cta", p.get("con_textos", True))),
        con_flecha=bool(p.get("con_flecha", p.get("con_textos", True))),
        semilla=f"{producto} {folder}",
        on_log=on_log,
        on_progress=_pipeline_progress,
    )

    on_progress(0.94, "☁️ Publicando en Drive…")
    root = audio_bank.mount_root()
    if root is None:
        raise RuntimeError(
            "No se encontró el mount de Drive (DRIVE_MOUNT_ROOT / /mnt/drive / "
            "~/gdrive) — no se puede publicar el vídeo final."
        )
    # Nombre literal pedido por el módulo: "<producto> <folder>.mp4"
    # (p. ej. "1 Pront Flow.mp4"), agrupado bajo la carpeta de origen.
    dest_dir = root / config.DRIVE_UPLOAD_ROOT / "videos" / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{producto} {folder}.mp4"
    tmp_dest = dest_path.with_name(dest_path.name + ".part")
    shutil.copy2(output_local, tmp_dest)
    tmp_dest.replace(dest_path)
    on_log(f"[nicho_pov_bof] publicado en Drive: {dest_path}")

    # Copia LOCAL para servir las descargas. Bajarlo del mount de Drive la
    # primera vez cuesta ~36s para 17 MB (hay que traerlo entero de Google
    # antes del primer byte); desde disco es instantáneo. Se limpia sola a
    # los `VIDEO_CACHE_DIAS`.
    try:
        cache = Path(config.video_cache_path(folder, producto))
        cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output_local, cache)
        borradas = config.limpiar_video_cache()
        if borradas:
            on_log(f"[nicho_pov_bof] caché de vídeos: {borradas} antigua(s) borrada(s)")
    except OSError as e:
        # Sin copia local se sigue sirviendo desde Drive: más lento, pero
        # funciona. No es motivo para tumbar el montaje.
        on_log(f"[nicho_pov_bof] ⚠️ no pude guardar la copia local: {e}")

    # `video_listo_at` es la marca de versión: el fichero se sobrescribe con
    # el mismo nombre en cada montaje, así que sin esto el navegador seguiría
    # sirviendo el vídeo viejo de su caché.
    product_repo.update_product(
        source, folder, producto, uploaded=True, video_path=str(dest_path),
        video_listo_at=int(time.time()),
    )

    # El bruto subido y el work_dir de escalones intermedios ya no hacen
    # falta una vez publicado — no se conservan (a diferencia del audio
    # original, que SIEMPRE se conserva en audio_bank).
    try:
        raw_path.unlink(missing_ok=True)
        shutil.rmtree(work_dir, ignore_errors=True)
    except OSError as cleanup_err:
        on_log(f"[nicho_pov_bof] ⚠️ no pude limpiar temporales: {cleanup_err}")

    on_progress(1.0, "✅ Listo")
    return str(dest_path)


# ============================================================
# RUNNER: TIKTOK SHOP WATERMARK REMOVER
# ============================================================
def run_tiktok_shop_watermark(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    """Quita marca de agua Veo 3 / Gemini de un vídeo y lo guarda en
    `<user>/products/<slug>/videos/sin_marca/<N>_clean.mp4`.

    Params requeridos:
      - input_path: path absoluto al vídeo (en temp_root)
      - user_id: TikTok user id (para resolver folder destino)
      - product_id: product id (para resolver folder destino)
      - watermark_type: "veo_flow" | "gemini_chat" | "auto"
      - quality: "fast" (delogo) | "magic" (ProPainter)
    """
    from src.tiktok_shop.config import user_videos_folder
    from src.tiktok_shop.pipeline.watermark_remover import (
        next_clean_filename,
        remove_watermark,
        remove_watermark_magic,
    )
    from src.tiktok_shop.repos import ProductRepo, UserRepo, get_shop_redis

    p = job.params
    input_path = p["input_path"]
    user_id = p["user_id"]
    product_id = p["product_id"]
    watermark_type = p.get("watermark_type", "auto")
    quality = p.get("quality", "magic")

    on_progress(0.05, "🔎 Resolviendo destino…")
    redis = get_shop_redis()
    user = UserRepo(redis).get(user_id)
    if user is None:
        raise RuntimeError(f"Usuario '{user_id}' no existe")
    product = ProductRepo(redis).get(product_id)
    if product is None:
        raise RuntimeError(f"Producto '{product_id}' no existe")

    dest_folder = Path(user_videos_folder(user.username, product.slug)) / "sin_marca"
    dest_folder.mkdir(parents=True, exist_ok=True)
    filename = next_clean_filename(dest_folder)
    dest_path = dest_folder / filename
    on_log(f"📁 Destino: {dest_path}")

    # Procesado a temp (para borrar el input local tras OK)
    import tempfile as _tmp
    tmp_out = _tmp.NamedTemporaryFile(
        prefix="wm_out_", suffix=".mp4", delete=False,
    )
    tmp_out.close()
    tmp_out_path = tmp_out.name

    try:
        if quality == "magic":
            on_progress(0.10, "🪄 ProPainter (Replicate)…")
            on_log("🪄 Magic Eraser via Replicate ProPainter — esto puede tardar 1-2min")

            def _hb(elapsed: int, status: str) -> None:
                # Progreso aproximado entre 0.10 y 0.90 según tiempo
                # esperado (~90s)
                pct = 0.10 + min(0.80, elapsed / 120.0)
                on_progress(pct, f"🪄 ProPainter {elapsed}s ({status})")

            # remove_watermark_magic ya hace log internamente; nuestro
            # on_log lo recibe directamente. Para heartbeat de progreso
            # usamos un wrapper si fuera necesario — por ahora delegamos.
            _, gpu_seconds = remove_watermark_magic(
                input_path, tmp_out_path,
                watermark_type=watermark_type,
                log_callback=on_log,
            )

            # Cost tracking
            try:
                from src.cost_tracking import record_replicate_propainter
                # Estimación duración del vídeo (cara, omitimos por ahora)
                vid_dur = float(p.get("video_duration_s") or 10.0)
                record_replicate_propainter(
                    gpu_seconds=gpu_seconds,
                    video_duration_s=vid_dur,
                    detail=f"{watermark_type} · {Path(input_path).name}",
                )
            except Exception as e:
                on_log(f"⚠️ cost tracking falló: {e}")
        else:
            on_progress(0.20, "⚡ ffmpeg delogo…")
            remove_watermark(
                input_path, tmp_out_path,
                watermark_type=watermark_type,
                log_callback=on_log,
            )

        on_progress(0.92, "📤 Copiando a Drive…")
        shutil.copy2(tmp_out_path, dest_path)
        on_log(f"✅ Guardado en {dest_path}")
        on_progress(1.0, "✅ Listo")
        return str(dest_path)
    finally:
        # Limpia temp output
        try:
            Path(tmp_out_path).unlink(missing_ok=True)
        except OSError:
            pass
        # Limpia input temp (ya no lo necesitamos)
        try:
            Path(input_path).unlink(missing_ok=True)
        except OSError:
            pass


# ============================================================
# Dispatch
# ============================================================
def run_tiktok_shop_pack(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    """Radar: construye el pack completo de UN producto (fotos + research +
    estilos de vídeo + carruseles + carpeta). Los prompts quedan en el
    Product (Redis) para verlos en el calendario sin abrir Drive."""
    from src.tiktok_shop.repos import ProductRepo
    from src.tiktok_shop.services.creation_pack import PackOptions, build_pack

    product_id = job.params["product_id"]
    options = PackOptions(**(job.params.get("options") or {}))
    on_progress(0.05, "📦 Cargando producto…")
    product = ProductRepo().get(product_id)
    if product is None:
        raise RuntimeError(f"Producto {product_id} no existe")

    # build_pack hace fotos→análisis→research→presets→carruseles→archivos.
    # Mapeamos sus logs a progreso aproximado por palabras clave.
    def _log(msg: str) -> None:
        on_log(msg)
        if "fotos" in msg.lower():
            on_progress(0.2, "🖼️ Fotos…")
        elif "research" in msg.lower() or "vídeos ganadores" in msg.lower():
            on_progress(0.4, "🎬 Investigando vídeos ganadores…")
        elif "estilos de vídeo" in msg.lower() or "presets" in msg.lower():
            on_progress(0.6, "🎥 Estilos de vídeo…")
        elif "carrusel" in msg.lower():
            on_progress(0.8, "🎠 Carruseles…")

    res = build_pack(product, options=options, log_callback=_log)
    on_progress(1.0, f"✅ Pack listo · 🎠 {res.carousels_generated} · 🎥 {res.presets_generated}")
    return res.folder or product.slug


def run_tiktok_shop_plan(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    """Radar: plan N productos/día — importa los top candidatos y construye
    el pack de cada uno + escribe el WeekPlan (calendario)."""
    from src.tiktok_shop.services.creation_pack import PackOptions, plan_week

    n_products = int(job.params.get("n_products", 14))
    per_day = int(job.params.get("per_day", 2))
    days = int(job.params.get("days", 7))
    options = PackOptions(**(job.params.get("options") or {}))

    done = {"n": 0}

    def _log(msg: str) -> None:
        on_log(msg)
        if msg.strip().startswith("✅ Pack de"):
            done["n"] += 1
            on_progress(min(0.98, done["n"] / max(1, n_products)),
                        f"📦 {done['n']}/{n_products} productos…")

    on_progress(0.02, f"🗓️ Preparando {n_products} productos ({per_day}/día)…")
    results = plan_week(
        n_products=n_products, options=options, days=days, per_day=per_day,
        log_callback=_log,
    )
    ok = sum(1 for r in results if r.slug)
    on_progress(1.0, f"✅ {ok} productos preparados")
    return f"plan:{ok}/{len(results)}"


def run_tiktok_shop_auto_day(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    """Radar v2: llena UN día del calendario solo, con los mejores productos
    que están recibiendo inyección de ADS AHORA.

    Escanea la inyección fresca (`fresh_ads_discovery`), se queda con el top N
    tras filtros, los importa como Product, los cuelga de la FECHA pedida en el
    calendario y genera sus prompts. El operador abre el día y tiene con qué
    grabar.

    Params: region, date (YYYY-MM-DD, default hoy), top_n, days_window,
            video_pages, max_influencers, min_commission_eur, gens, options.
    """
    from src.tiktok_shop.models.month_plan import DayEntry, today_iso
    from src.tiktok_shop.repos.month_plan_repo import MonthPlanRepo
    from src.tiktok_shop.services import discovery_service
    from src.tiktok_shop.services.creation_pack import PackOptions, build_pack
    from src.tiktok_shop.services.fresh_ads_discovery import (
        FreshAdsFilters,
        commission_eur,
        discover_fresh_ad_products,
        real_influencers,
    )

    region = str(job.params.get("region") or "ES")
    # Fecha REAL, no un "día 1..N". Default: hoy.
    date = str(job.params.get("date") or today_iso())
    top_n = max(1, int(job.params.get("top_n", 5)))
    window = float(job.params.get("days_window", 3))
    pages = int(job.params.get("video_pages", 8))
    options = PackOptions(**(job.params.get("options") or {}))

    filters = FreshAdsFilters(
        max_influencers=job.params.get("max_influencers", 250),
        min_commission_pct=float(job.params.get("min_commission_pct", 0.0)),
    )
    min_eur = float(job.params.get("min_commission_eur", 0.0))

    # ── 1. Escanear la inyección fresca ──────────────────────────────
    on_progress(0.05, f"📡 Buscando inyección de ADS en {region}…")
    cands = discover_fresh_ad_products(
        region=region, days=window, video_pages=pages,
        max_products=max(20, top_n * 4), deep_ads_top_n=max(top_n, 8),
        filters=filters, persist=True, log_callback=on_log,
    )
    if not cands:
        on_progress(1.0, "∅ Sin productos con ADS frescos")
        return "auto_day:0 (sin candidatos — ¿cuota de EchoTik agotada?)"

    # Suelo en EUROS por venta: un 12% de un producto de 10€ son 1,20€ — no
    # compensa grabar por eso. Se filtra aquí y no en FreshAdsFilters porque
    # necesita el precio ya resuelto.
    if min_eur > 0:
        before = len(cands)
        cands = [c for c in cands if commission_eur(c) >= min_eur]
        on_log(f"💰 {len(cands)}/{before} con ≥{min_eur:.2f}€ por venta")
    if not cands:
        on_progress(1.0, "∅ Ninguno llega al mínimo por venta")
        return "auto_day:0 (ninguno supera min_commission_eur)"

    chosen = cands[:top_n]
    on_log(f"🏆 Top {len(chosen)} para el {date}:")
    for i, c in enumerate(chosen, 1):
        on_log(f"   {i}. [{c.score.total:.0f}] {c.name[:44]} · "
               f"~{real_influencers(c)} creadores · {c.units_sold} ventas · "
               f"{commission_eur(c):.2f}€/venta")

    # ── 2. Importar + colgar del día + generar prompts ───────────────
    repo = MonthPlanRepo()
    added = 0
    for i, cand in enumerate(chosen):
        base = 0.15 + (i / len(chosen)) * 0.80
        on_progress(base, f"📦 {i + 1}/{len(chosen)}: {cand.name[:34]}…")
        try:
            product = discovery_service.import_candidate(cand, language="es")
        except Exception as e:  # noqa: BLE001
            on_log(f"  ⚠️ no se pudo importar {cand.name[:34]!r}: {e}")
            continue
        # add_entry es idempotente por (fecha, producto) → re-lanzar el
        # mismo día no duplica.
        repo.add_entry(DayEntry(
            date=date, product_id=product.id, slug=product.slug,
            name=product.name, score=cand.score.total,
            ads_verdict=cand.ads.verdict,
            # El REAL estimado, no el crudo de EchoTik (infravalora 2.6x):
            # es el número que el operador verá en la ficha de TikTok.
            influencer_count=real_influencers(cand),
            commission_eur=round(commission_eur(cand), 2),
            seller_name=cand.seller_name,
        ))
        added += 1
        try:
            build_pack(product, options=options, log_callback=on_log)
        except Exception as e:  # noqa: BLE001
            # El producto ya está en el calendario: mejor sin prompts que
            # perderlo. El operador puede regenerar desde la tarjeta.
            on_log(f"  ⚠️ pack falló para {product.name[:34]!r}: {e}")

    on_progress(1.0, f"✅ {added} productos el {date}")
    return f"auto_day:{added}/{len(chosen)} fecha={date}"


def run_tiktok_shop_ready_video(job: Job, on_log: OnLog, on_progress: OnProgress) -> str:
    """Procesa un vídeo subido (Flow/Kling) → lo deja LISTO para TikTok:
    zoom quita-marca + gancho/CTA + flecha. Guarda en videos_ready y marca
    el concepto. El original NO se borra si falla (para depurar)."""
    import os
    import re
    from datetime import datetime

    from src.tiktok_shop.config import product_drive_folder
    from src.tiktok_shop.pipeline.ready_video import process_ready_video
    from src.tiktok_shop.repos import ProductRepo

    raw_path = job.params["raw_path"]
    zoom = float(job.params.get("zoom", 1.18))

    # ── Modo GENÉRICO (editor libre): sin producto ni concepto. Se pasa el
    # `out_path` ya resuelto + gancho/CTA directos. Sirve para editar cualquier
    # vídeo (plantillas ⚡, subidas sueltas) con la misma edición que los
    # vídeos-problema, sin depender de un concepto guardado. ──
    if job.params.get("out_path"):
        out_path = job.params["out_path"]
        on_progress(0.1, "🎬 Procesando vídeo…")
        seed = int(hashlib.md5(out_path.encode()).hexdigest(), 16) % 420
        process_ready_video(
            raw_path, out_path,
            hook_text=str(job.params.get("hook_text", "")),
            cta_text=str(job.params.get("cta_text", "")),
            zoom=zoom, style=seed, log=on_log,
        )
        try:
            os.remove(raw_path)
        except OSError:
            pass
        on_progress(1.0, "✅ Vídeo listo para descargar")
        return out_path

    product_id = job.params["product_id"]
    idx = int(job.params["concept_index"])
    # Lista destino: problem_videos (default) o viral_replicas (replicar viral).
    # Mismo schema 2-step, misma maquinaria de render; solo cambia el campo.
    concept_field = job.params.get("concept_field", "problem_videos")

    repo = ProductRepo()
    product = repo.get(product_id)
    concepts = getattr(product, concept_field, None) if product is not None else None
    if product is None or not isinstance(concepts, list) or idx < 0 or idx >= len(concepts):
        raise RuntimeError("Producto o concepto no encontrado")
    concept = concepts[idx]

    ready_dir = os.path.join(product_drive_folder(product.slug), "videos_ready")
    # Nombre único: producto + versión + fecha/hora → sin duplicados al bajar.
    short = re.sub(r"[^a-z0-9]+", "_", product.name.lower())[:40].strip("_") or "video"
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    tag = "rep" if concept_field == "viral_replicas" else "v"
    fname = f"{short}_{tag}{idx + 1}_{ts}.mp4"
    out_path = os.path.join(ready_dir, fname)
    on_progress(0.1, "🎬 Procesando vídeo…")
    # Desfase por PRODUCTO: sin esto, todo producto empieza en el estilo/flecha 0
    # y las 3 versiones salen SIEMPRE la misma tripleta. Sumando un hash estable
    # del producto, cada producto arranca en un punto distinto de la rotación
    # (7 estilos de texto × 12 flechas reales × 4 modos) → variedad real entre
    # productos, y las 3 versiones siguen distintas entre sí (idx 0/1/2).
    seed = int(hashlib.md5(product_id.encode()).hexdigest(), 16) % 420  # lcm(7,12,4,5)
    process_ready_video(
        raw_path, out_path,
        hook_text=concept.get("hook_text", ""),
        cta_text=concept.get("cta_text", ""),
        zoom=zoom, style=seed + idx, log=on_log,
    )
    # Re-leer FRESCO justo antes de guardar. El procesado tarda minutos y otro
    # job de OTRA versión del MISMO producto pudo terminar y guardar mientras
    # tanto. Si guardáramos el `product` leído al inicio, machacaríamos el
    # ready_video que ese otro job acaba de poner (race read-modify-write: el
    # operador veía V1 volver a "Subir vídeo" tras subir V2/V3). Tocamos solo
    # el índice de esta versión sobre la copia más reciente.
    fresh = repo.get(product_id) or product
    fresh_list = getattr(fresh, concept_field, None)
    if isinstance(fresh_list, list) and 0 <= idx < len(fresh_list):
        fresh_list[idx]["ready_video"] = fname
        fresh_list[idx]["ready_at"] = ts
    fresh.touch()
    repo.save(fresh)
    try:
        os.remove(raw_path)   # solo si el procesado fue bien
    except OSError:
        pass
    on_progress(1.0, "✅ Vídeo listo para descargar")
    return out_path


_RUNNERS: dict[JobMode, Callable[[Job, OnLog, OnProgress], str]] = {
    JobMode.PRESIDENTS: run_presidents,
    JobMode.PRONOSTICOS: run_pronosticos,
    JobMode.SUBS_AUTO: run_subs_auto,
    JobMode.COPYRIGHT: run_copyright,
    JobMode.CONSTRUCCION_POV: run_construccion_pov,
    JobMode.TIKTOK_SHOP: run_tiktok_shop,
    JobMode.TIKTOK_SHOP_WATERMARK: run_tiktok_shop_watermark,
    JobMode.TIKTOK_SHOP_PACK: run_tiktok_shop_pack,
    JobMode.TIKTOK_SHOP_PLAN: run_tiktok_shop_plan,
    JobMode.TIKTOK_SHOP_AUTO_DAY: run_tiktok_shop_auto_day,
    JobMode.TIKTOK_SHOP_READY_VIDEO: run_tiktok_shop_ready_video,
    JobMode.EDITOR_AUTO: run_editor_auto,
    JobMode.VIRALIZACION_BATCH: run_viralizacion_batch,
    JobMode.NICHO_POV_BOF_BACKUP: run_nicho_pov_bof_backup,
    JobMode.NICHO_POV_BOF_VIDEO: run_nicho_pov_bof_video,
}


_MODE_TO_PROGRAM: dict[JobMode, str] = {
    JobMode.PRESIDENTS: "creator_reward",
    JobMode.PRONOSTICOS: "creator_reward",
    JobMode.SUBS_AUTO: "creator_reward",
    JobMode.COPYRIGHT: "creator_reward",
    JobMode.CONSTRUCCION_POV: "creator_reward",
    JobMode.TIKTOK_SHOP: "tiktok_shop",
    JobMode.TIKTOK_SHOP_WATERMARK: "tiktok_shop",
    JobMode.TIKTOK_SHOP_PACK: "tiktok_shop",
    JobMode.TIKTOK_SHOP_PLAN: "tiktok_shop",
    JobMode.TIKTOK_SHOP_AUTO_DAY: "tiktok_shop",
    JobMode.TIKTOK_SHOP_READY_VIDEO: "tiktok_shop",
    JobMode.EDITOR_AUTO: "editor_auto",
    JobMode.VIRALIZACION_BATCH: "viralizacion",
    JobMode.NICHO_POV_BOF_BACKUP: "viralizacion",
    JobMode.NICHO_POV_BOF_VIDEO: "viralizacion",
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
