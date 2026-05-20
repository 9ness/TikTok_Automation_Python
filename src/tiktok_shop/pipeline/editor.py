"""Composer final del vídeo TikTok Shop con FFmpeg directo.

⚠️ Refactor v4 (mayo 2026): el compose multi-clip se hace con FFmpeg
`xfade` + `afade` directamente, NO con moviepy. Razón: moviepy
`concatenate_videoclips(padding=-crossfade_s)` con `fadein`/`fadeout`
generaba **flash negro de ~1s entre clips** porque cuando los 2 clips
están bajando alpha simultáneamente, el fondo (negro) queda visible.
FFmpeg `xfade=transition=fade` hace dissolve REAL pixel-a-pixel sin
nunca exponer pixels negros.

Validación estricta de duraciones:
  - `ffprobe` mide cada clip + audio reales (no la duración pedida).
  - Si `audio > video`: truncate audio con `afade=t=out` 0.3s.
  - Si `audio < video`: trim video al audio (mantiene la voz completa,
    elimina segundos de "pantalla negra al final" que reportó BUG B).
  - Si `audio ≈ video`: ambos quedan iguales.
NUNCA se extiende video con loops o frames negros.

Captions karaoke siguen renderizándose con moviepy/PIL sobre el MP4
ya compuesto — eso no tiene los problemas del compose principal.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Literal


LogCallback = Callable[[str], None]

# Default de trim del primer frame "fotografía" — overrideable desde
# strategy_cfg (FUNC 5 cinematic/dynamic ambos usan 0.15s).
TRIM_HEAD_S = 0.15


def _noop(_msg: str) -> None: ...


# ---------------------------------------------------------------------------
# Utilidades FFmpeg
# ---------------------------------------------------------------------------
def _ffprobe_duration(path: str) -> float:
    """Devuelve la duración en segundos de un archivo de media usando ffprobe."""
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        text=True,
    )
    return float(out.strip())


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _measure_audio_without_tail_silence(
    audio_path: str,
    *,
    threshold_db: float = -50.0,
    min_silence_s: float = 0.3,
    proximity_s: float = 2.0,
) -> float:
    """Devuelve la duración efectiva del audio descartando silencio final.

    Usa el filtro `silencedetect` de FFmpeg (reporta silencios en stderr).
    Si el ÚLTIMO `silence_start` detectado está dentro de `proximity_s`
    segundos del final del archivo, asume que es el tail silence de
    MiniMax y devuelve esa posición. Si no, devuelve la duración raw.

    Defaults conservadores (-50dB, 0.3s) para detectar silencio real
    sin recortar pausas naturales del speaker.
    """
    import re as _re

    raw_dur = _ffprobe_duration(audio_path)
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-nostats",
                "-i", audio_path,
                "-af", f"silencedetect=noise={threshold_db}dB:duration={min_silence_s}",
                "-f", "null", "-",
            ],
            capture_output=True, text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return raw_dur

    if proc.returncode != 0:
        return raw_dur

    silence_starts: list[float] = []
    pattern = _re.compile(r"silence_start:\s*([0-9]*\.?[0-9]+)")
    for m in pattern.finditer(proc.stderr or ""):
        try:
            silence_starts.append(float(m.group(1)))
        except ValueError:
            continue

    if not silence_starts:
        return raw_dur

    last = silence_starts[-1]
    # Solo recortamos si el último silencio detectado está cerca del final;
    # si está en medio (pausa natural larga), respetamos la duración raw.
    if 0 < last < raw_dur and (raw_dur - last) < proximity_s:
        return max(last, 0.5)  # nunca devolver duración casi-cero
    return raw_dur


# ---------------------------------------------------------------------------
# Compose principal con FFmpeg
# ---------------------------------------------------------------------------
def _compose_with_ffmpeg(
    *,
    clip_paths: list[str],
    voice_mp3: str,
    output_path: str,
    trim_head_s: float,
    crossfade_s: float,
    target_size: tuple[int, int],
    fps: int,
    log_callback: LogCallback,
) -> float:
    """Compone los clips con `xfade` real + audio sincronizado al video.

    Returns:
        Duración final del MP4 en segundos.
    """
    n = len(clip_paths)
    if n == 0:
        raise RuntimeError("compose: lista de clips vacía")

    # 1. Duración real de cada clip POST-trim
    clip_durs: list[float] = []
    for i, cp in enumerate(clip_paths):
        d = _ffprobe_duration(cp)
        post = max(0.0, d - trim_head_s)
        clip_durs.append(post)
        log_callback(f"  📏 clip {i}: {d:.3f}s → {post:.3f}s tras trim head {trim_head_s}s")

    # 2. Duración objetivo del video tras crossfade
    overlap_total = max(0, n - 1) * (crossfade_s if crossfade_s > 0 else 0)
    video_dur = sum(clip_durs) - overlap_total
    if video_dur <= 0:
        raise RuntimeError(f"compose: video_dur calculado <=0 ({video_dur:.3f}s)")

    # 3. Duración real del audio + trim de silencio final con `silenceremove`
    # ----------------------------------------------------------------
    # MiniMax añade ~200-800ms de silencio al final de cada MP3. ffprobe
    # los cuenta y nuestra `audio_dur` queda inflada → dispara `truncate`
    # innecesariamente (recortando el final de la voz en lugar del silencio).
    # Medimos la duración EFECTIVA de la voz quitando silencios <-50dB
    # antes de comparar con `video_dur`.
    audio_dur_raw = _ffprobe_duration(voice_mp3)
    audio_dur = _measure_audio_without_tail_silence(voice_mp3)
    tail_silence = audio_dur_raw - audio_dur
    if tail_silence > 0.1:
        log_callback(
            f"  🎙️ audio raw: {audio_dur_raw:.3f}s · sin silencio final: {audio_dur:.3f}s "
            f"(trim {tail_silence*1000:.0f}ms) · 🎞️ video target: {video_dur:.3f}s"
        )
    else:
        log_callback(f"  🎙️ audio: {audio_dur:.3f}s · 🎞️ video target: {video_dur:.3f}s")

    # 4. Decidir final_dur + estrategia para los 3 casos.
    #
    # Estrategia desde mayo 2026 (BUG 1, intento 4):
    #   - audio == video  → SYNCED: corte limpio
    #   - audio < video   → trim video al audio (evita pantalla negra final)
    #   - audio > video   → 🆕 FREEZE FRAME: en lugar de truncar audio
    #     (que perdía el CTA), EXTENDEMOS el video clonando el último frame
    #     del último clip mediante `tpad=stop_mode=clone:stop_duration=N`.
    #     El audio se mantiene íntegro; el video acaba 0.5s DESPUÉS del audio
    #     (frame estático con audio en silencio). NUNCA aparece pantalla negra.
    #
    # Reemplaza la estrategia anterior de truncar audio + fade-out, que no era
    # robusta cuando la medición de tail silence variaba o el codec rounding
    # aumentaba la duración real del MP4 por encima del `-t` solicitado.
    #
    # `audio_dur` es la voz EFECTIVA (sin tail silence) — calculada arriba.
    # Pausas internas del speaker quedan intactas (NO usamos `silenceremove`).
    audio_filter_chain: str
    video_pad_extra: float = 0.0  # segundos a clonar del último frame
    if audio_dur > video_dur + 0.05:
        # Overflow audio → freeze frame para extender video.
        # margen 0.5s al final = frame estático con silencio.
        video_pad_extra = (audio_dur - video_dur) + 0.5
        final_dur = video_dur + video_pad_extra  # = audio_dur + 0.5
        audio_filter_chain = (
            f"[{n}:a]atrim=0:{audio_dur:.3f},asetpts=PTS-STARTPTS[aout]"
        )
        log_callback(
            f"  🧊 Audio sobra +{audio_dur - video_dur:.2f}s → freeze del último "
            f"frame +{video_pad_extra:.2f}s (evita pantalla negra; total "
            f"{final_dur:.2f}s; audio íntegro {audio_dur:.2f}s)"
        )
    elif audio_dur < video_dur - 0.05:
        # Audio más corto → MANTENEMOS la duración completa del video.
        # Estrategia mayo 2026 (intento 6 — fix pantalla negra final):
        # NO recortar el video al audio. El audio termina y los últimos
        # frames del último clip Atlas (vídeo real, no negro) se ven con
        # silencio sobre ellos.
        #
        # ⚠️ `apad=whole_dur=<final_dur>` (con duración explícita) en lugar
        # del antiguo `apad` solo: éste último deja la duración del stream
        # de audio indefinida y moviepy/ffmpeg pueden interpretar la
        # duración del MP4 como min(video, audio_explícito) cortando la
        # cola del video a negro. Con `whole_dur` el audio queda EXPLÍCI-
        # TAMENTE a `final_dur` segundos, evitando ese corte.
        final_dur = video_dur
        audio_filter_chain = (
            f"[{n}:a]atrim=0:{audio_dur:.3f},asetpts=PTS-STARTPTS,"
            f"apad=whole_dur={final_dur:.3f}[aout]"
        )
        log_callback(
            f"  ℹ️ Audio corto -{video_dur - audio_dur:.2f}s → mantenemos video "
            f"{video_dur:.2f}s; audio íntegro {audio_dur:.2f}s + silencio "
            f"{video_dur - audio_dur:.2f}s sobre últimos frames"
        )
    else:
        final_dur = min(audio_dur, video_dur)
        audio_filter_chain = (
            f"[{n}:a]atrim=0:{final_dur:.3f},asetpts=PTS-STARTPTS[aout]"
        )
        log_callback(f"  ✅ Audio y vídeo sincronizados ({final_dur:.2f}s)")

    # 5. Construir filter_complex
    w, h = target_size
    parts: list[str] = []

    # Trim + scale + setsar para cada clip
    for i in range(n):
        parts.append(
            f"[{i}:v]trim=start={trim_head_s},setpts=PTS-STARTPTS,"
            f"scale={w}:{h}:flags=lanczos,setsar=1,fps={fps}[v{i}]"
        )

    # Concatenación: 1 clip = passthrough; 2+ = xfade encadenado.
    # Etiqueta final intermedia = `vmid`; un paso adicional la convierte
    # en `vout` aplicando freeze pad si hace falta.
    if n == 1:
        parts.append("[v0]null[vmid]")
    else:
        accumulated = clip_durs[0]
        prev_label = "v0"
        for i in range(1, n):
            offset = accumulated - crossfade_s if crossfade_s > 0 else accumulated
            out_label = f"vx{i}" if i < n - 1 else "vmid"
            if crossfade_s > 0:
                parts.append(
                    f"[{prev_label}][v{i}]xfade=transition=fade:"
                    f"duration={crossfade_s}:offset={offset:.3f}[{out_label}]"
                )
                accumulated += clip_durs[i] - crossfade_s
            else:
                # Sin crossfade: concat puro (no debería usar este path en
                # FUNC 5 porque ambas estrategias tienen crossfade>0, pero
                # lo dejamos defensivo).
                parts.append(
                    f"[{prev_label}][v{i}]concat=n=2:v=1:a=0[{out_label}]"
                )
                accumulated += clip_durs[i]
            prev_label = out_label

    # Paso final video: freeze del último frame si overflow, sino passthrough.
    # `tpad=stop_mode=clone:stop_duration=N` clona el último frame N segundos
    # → eliminamos pantalla negra al final cuando audio > video.
    if video_pad_extra > 0:
        parts.append(
            f"[vmid]tpad=stop_mode=clone:stop_duration={video_pad_extra:.3f}[vout]"
        )
    else:
        parts.append("[vmid]null[vout]")

    # Audio
    parts.append(audio_filter_chain)

    filter_complex = ";".join(parts)

    # 6. Comando ffmpeg
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        *[arg for cp in clip_paths for arg in ("-i", cp)],
        "-i", voice_mp3,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-t", f"{final_dur:.3f}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-c:a", "aac",
        "-b:a", "128k",
        output_path,
    ]
    log_callback(
        f"🎞️ FFmpeg compose: {n} clips, crossfade={crossfade_s}s, "
        f"trim_head={trim_head_s}s, target={final_dur:.2f}s"
    )
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log_callback(f"❌ FFmpeg falló:\n{proc.stderr[-1500:]}")
        raise RuntimeError(f"FFmpeg compose falló (rc={proc.returncode})")

    # 7. Validación post-export ESTRICTA: duración real DEBE coincidir con
    # final_dur dentro de tolerancia, sino abortamos.
    #   - ±0.3s OK silencioso
    #   - ±0.3 a ±2.0s WARNING (codec rounding, no crítico)
    #   - >±2.0s ABORT (síntoma de bug catastrófico — clips no concatenados,
    #     audio desincronizado, etc.)
    actual = _ffprobe_duration(output_path)
    diff = actual - final_dur
    if abs(diff) > 2.0:
        raise RuntimeError(
            f"FFmpeg compose: discrepancia grave entre duración objetivo "
            f"({final_dur:.2f}s) y output real ({actual:.2f}s). "
            f"Diff={diff:+.2f}s. Aborto para evitar subir a Drive un MP4 corrupto."
        )
    elif abs(diff) > 0.3:
        log_callback(
            f"⚠️ Duración output {actual:.2f}s vs target {final_dur:.2f}s "
            f"(diff={diff:+.2f}s — dentro de tolerancia)"
        )
    return actual


# ---------------------------------------------------------------------------
# API pública: compose_shop_video
# ---------------------------------------------------------------------------
def compose_shop_video(
    *,
    clip_paths: list[str],
    voice_mp3: str,
    output_path: str,
    strategy: str = "multi_clip_anchor",
    size: tuple[int, int] = (720, 1280),
    fps: int = 30,
    add_captions: bool = True,
    captions_style: dict | None = None,
    language: str = "es",
    audio_overflow_strategy: Literal["truncate", "speedup"] = "truncate",
    trim_head_each_clip: bool = True,
    trim_head_s: float | None = None,
    crossfade_s: float = 0.0,
    overlays: dict | None = None,
    hook_text_fallback: str = "",
    job_id: str = "shop",
    temp_folder: str = "./temp_work",
    log_callback: LogCallback = _noop,
) -> str:
    """Compone el vídeo final usando FFmpeg directo (xfade real, sin negro).

    Args:
        clip_paths: lista de MP4 ya renderizados.
            - `multi_clip_anchor` (Standard/Advanced): N clips → xfade.
            - `single_shot_multishot` (Pro): 1 clip → passthrough.
        voice_mp3: voz MiniMax (obligatoria).
        strategy: la estrategia del tier — define si concat o no.
        size: resolución 9:16 (720×1280 default, 1080×1920 alternativa).
        language: idioma para Whisper transcribir captions ("es", "en", ...).
        crossfade_s: duración del xfade entre clips (0 = corte duro).
        trim_head_s: cuántos segundos quitar al inicio de cada clip
            (default `TRIM_HEAD_S` = 0.15).
        audio_overflow_strategy: ahora informativo — el FFmpeg path siempre
            trunca con fade-out si audio > video. `speedup` no está
            implementado en el path FFmpeg (era moviepy-only).
    """
    log_callback("🎬 Componiendo vídeo TikTok Shop (FFmpeg)…")

    if not voice_mp3 or not os.path.exists(voice_mp3):
        raise FileNotFoundError(f"Voz MP3 no encontrada: {voice_mp3}")
    if not clip_paths:
        raise RuntimeError(
            "No hay clips renderizados. Asegúrate de que Atlas Cloud está "
            "configurado y los clips se descargaron correctamente."
        )
    valid_clips = [c for c in clip_paths if os.path.exists(c)]
    if not valid_clips:
        raise RuntimeError("Ningún clip Seedance utilizable tras filtrar inexistentes.")
    if len(valid_clips) < len(clip_paths):
        log_callback(f"⚠️ {len(clip_paths) - len(valid_clips)} clips no encontrados, se omiten.")

    if not _has_ffmpeg():
        raise RuntimeError(
            "ffmpeg/ffprobe no encontrados en PATH. Instálalos para componer "
            "el vídeo final."
        )

    # `audio_overflow_strategy` se mantiene en la firma pública por compat;
    # el FFmpeg path siempre trunca con fade-out (no implementa speedup).
    del audio_overflow_strategy  # documentar intent: consumido sin uso

    effective_trim_head = trim_head_s if trim_head_s is not None else TRIM_HEAD_S
    is_pro_singleshot = strategy == "single_shot_multishot" and len(valid_clips) == 1
    if is_pro_singleshot or not trim_head_each_clip:
        # Pro: 1 clip ya editado por el modelo — sin trim head ni xfade.
        # `trim_head_each_clip=False` desactiva todo trim (algunos tests lo usan).
        effective_trim_head = 0.0
        if is_pro_singleshot:
            crossfade_s = 0.0

    # 1. Compose vídeo + audio con FFmpeg (genera mp4 base)
    base_path = output_path + ".base.mp4"
    final_dur = _compose_with_ffmpeg(
        clip_paths=valid_clips,
        voice_mp3=voice_mp3,
        output_path=base_path,
        trim_head_s=effective_trim_head,
        crossfade_s=crossfade_s,
        target_size=size,
        fps=fps,
        log_callback=log_callback,
    )
    log_callback(f"📐 Base compuesto: {final_dur:.2f}s. Pasando a captions…")

    # 2. Captions karaoke (opcional). Render con moviepy/PIL sobre el mp4
    # base — eso no tiene problemas porque trabaja sobre 1 solo video ya
    # compuesto.
    if add_captions:
        try:
            from src.subtitles import render_karaoke_on_video, transcribe

            # Pre-trim del voice_mp3 al boundary efectivo (sin tail silence)
            # ANTES de Whisper. MiniMax añade ~200-800ms de silencio al final
            # con artefactos de compresión que Whisper a veces transcribe como
            # palabras fantasma → captions flotan más allá del audio real.
            audio_dur_eff = _measure_audio_without_tail_silence(voice_mp3)
            voice_for_captions = base_path + ".voice_trimmed.mp3"
            try:
                proc = subprocess.run(
                    [
                        "ffmpeg", "-y", "-loglevel", "error",
                        "-i", voice_mp3,
                        "-t", f"{audio_dur_eff:.3f}",
                        "-c:a", "copy",
                        voice_for_captions,
                    ],
                    capture_output=True, text=True,
                )
                if proc.returncode != 0 or not os.path.exists(voice_for_captions):
                    voice_for_captions = voice_mp3  # fallback
            except (OSError, subprocess.SubprocessError):
                voice_for_captions = voice_mp3

            log_callback(
                f"🎙️ Whisper transcribiendo voz para captions (lang={language}, "
                f"trim a {audio_dur_eff:.2f}s sin tail silence)…"
            )
            words = transcribe(
                voice_for_captions, model_size="small", language=language,
            )

            style = captions_style or _default_caption_style()
            log_callback("✏️ Quemando subtítulos karaoke…")
            render_karaoke_on_video(base_path, words, style, output_path)
            try:
                os.remove(base_path)
            except OSError:
                pass
            if voice_for_captions != voice_mp3:
                try:
                    os.remove(voice_for_captions)
                except OSError:
                    pass
        except Exception as e:
            log_callback(f"⚠️ No se pudieron quemar subtítulos: {e}. Vídeo base devuelto sin captions.")
            os.replace(base_path, output_path)
    else:
        os.replace(base_path, output_path)

    # 3. Validación final: el output debe existir y tener duración válida.
    if not os.path.exists(output_path):
        raise RuntimeError(f"Output no se generó: {output_path}")
    actual_final = _ffprobe_duration(output_path)
    if actual_final < 1.0:
        raise RuntimeError(
            f"Output con duración inválida ({actual_final:.2f}s). Abortando."
        )

    # 4. Overlays componibles (Fase 3): hook box al inicio + CTA flecha al
    # final. Aplicados secuencialmente sobre el MP4 ya con captions.
    if overlays:
        output_path = _apply_shop_overlays(
            video_path=output_path,
            overlays=overlays,
            hook_text_fallback=hook_text_fallback,
            job_id=job_id,
            temp_folder=temp_folder,
            log_callback=log_callback,
        )
        actual_final = _ffprobe_duration(output_path)

    log_callback(f"✅ Vídeo final: {output_path} ({actual_final:.2f}s)")
    return output_path


def _apply_shop_overlays(
    *,
    video_path: str,
    overlays: dict,
    hook_text_fallback: str,
    job_id: str,
    temp_folder: str,
    log_callback: LogCallback,
) -> str:
    """Aplica hook_box y/o cta_arrow sobre `video_path` y devuelve el path
    del MP4 con los overlays aplicados. Cualquier overlay con `enabled=False`
    se omite. Si los dos están deshabilitados, devuelve `video_path` sin
    tocar nada.

    Errores en overlays NO abortan: log warning y se devuelve el último MP4
    válido (los overlays son cosméticos, no críticos para el render).
    """
    current = video_path
    tmp_dir = Path(temp_folder)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # --- Hook box al inicio ---
    hook_cfg = overlays.get("hook_box") or {}
    if hook_cfg.get("enabled"):
        try:
            from src.text_hook import add_text_hook_to_video
            hook_text = (hook_cfg.get("text") or hook_text_fallback or "").strip()
            if not hook_text:
                log_callback("⚠️ Hook box habilitado pero sin texto — saltando.")
            else:
                style: dict = {
                    k: v for k, v in hook_cfg.items()
                    if k != "enabled" and v is not None
                }
                hook_out = str(tmp_dir / f"shop_hook_{job_id}.mp4")
                log_callback(f"🎣 Aplicando hook box: '{hook_text[:50]}'…")
                add_text_hook_to_video(
                    current, hook_text, style, hook_out,
                    log_callback=log_callback,
                )
                # Si nos cargamos el archivo intermedio anterior libera disco.
                if current != video_path:
                    try:
                        os.remove(current)
                    except OSError:
                        pass
                current = hook_out
        except Exception as e:
            log_callback(f"⚠️ Hook box overlay falló ({e}). Continuando sin hook.")

    # --- CTA flecha al final ---
    cta_cfg = overlays.get("cta_arrow") or {}
    if cta_cfg.get("enabled"):
        try:
            from src.editor_auto.tools.base import ToolContext
            from src.editor_auto.tools.sticker_arrow import StickerArrowTool

            sticker_file = (cta_cfg.get("sticker_file") or "").strip()
            if not sticker_file:
                log_callback("⚠️ CTA flecha habilitada pero sin sticker_file — saltando.")
            else:
                arrow_out = str(tmp_dir / f"shop_cta_{job_id}.mp4")
                # Skip Whisper — usamos siempre fallback_last_seconds para
                # TikTok Shop (la voz ya la conocemos, no hace falta detectar
                # keywords y ahorra ~5-10s por render).
                tool_cfg: dict = {
                    "sticker_file": sticker_file,
                    "position_x_pct": float(cta_cfg.get("position_x_pct", 50.0)),
                    "position_y_pct": float(cta_cfg.get("position_y_pct", 78.0)),
                    "scale_width_pct": float(cta_cfg.get("scale_width_pct", 25.0)),
                    "rotation_deg": int(cta_cfg.get("rotation_deg", 0)),
                    "flip_horizontal": bool(cta_cfg.get("flip_horizontal", False)),
                    "flip_vertical": bool(cta_cfg.get("flip_vertical", False)),
                    "duration_seconds": float(cta_cfg.get("duration_seconds", 3.5)),
                    "fallback_last_seconds": float(cta_cfg.get("fallback_last_seconds", 4.0)),
                    "transcribe_for_detection": False,
                    "lead_seconds": 0.0,
                }
                ctx = ToolContext(
                    user_id="shop",
                    user_name="shop",
                    job_id=job_id,
                    temp_folder=str(tmp_dir),
                    on_log=log_callback,
                    on_progress=lambda _f, _m: None,
                )
                log_callback(f"➡️ Aplicando CTA flecha: {sticker_file}…")
                StickerArrowTool().run(
                    input_path=current,
                    output_path=arrow_out,
                    config=tool_cfg,
                    ctx=ctx,
                )
                if current != video_path:
                    try:
                        os.remove(current)
                    except OSError:
                        pass
                current = arrow_out
        except Exception as e:
            log_callback(f"⚠️ CTA flecha overlay falló ({e}). Continuando sin CTA.")

    # Si aplicamos algún overlay, mover el último resultado al output_path.
    if current != video_path:
        try:
            os.replace(current, video_path)
            return video_path
        except OSError:
            # Si replace falla (filesystem cross-device), devolver el path nuevo.
            return current
    return current


def _default_caption_style() -> dict:
    """Estilo karaoke default para TikTok Shop (más conservador que Pronósticos)."""
    return {
        "font_path": r"C:\Windows\Fonts\impact.ttf",
        "font_scale": 0.045,
        "text_color": "#FFFFFF",
        "stroke_color": "#000000",
        "stroke_width": 6,
        "pill_enabled": True,
        "pill_color": "#000000",
        "pill_radius": 12,
        "pill_pad_x_pct": 0.012,
        "pill_pad_y_pct": 0.006,
        "case_mode": "UPPERCASE",
        "max_words_per_chunk": 3,
        "y_position_pct": 0.65,
        "highlight_color": "#3CD05E",
    }
