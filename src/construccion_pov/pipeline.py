"""Pipeline Construcción POV — orquestador end-to-end.

Etapas (con franjas de progreso):
  0.00 → 0.05   probe duración
  0.05 → 0.30   Gemini analiza vídeo → guion narrado EN
  0.30 → 0.50   MiniMax TTS → narración MP3
  0.50 → 0.60   ffmpeg: combinar vídeo + narración (audio nuevo, vídeo orig)
  0.60 → 0.75   Whisper sobre la narración → words[]
  0.75 → 1.00   Visuales anti-copy (zoom/pulse/metadata) + subs karaoke

NUNCA aborta por falta de un asset opcional. Si Gemini falla, propaga.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


def _probe_duration_seconds(video_path: str) -> float:
    """Lee duración del vídeo con ffprobe (más rápido y robusto que moviepy)."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", video_path,
            ],
            check=True, capture_output=True, text=True, timeout=30,
        )
        return max(1.0, float(out.stdout.strip()))
    except Exception:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(video_path)
        try:
            return float(clip.duration)
        finally:
            clip.close()


def _detect_tail_echo(
    words: list[dict],
    script: str,
) -> int | None:
    """Detecta si MiniMax repitió en bucle las últimas palabras del guion.

    Estrategias en cascada (devuelve el índice tras el FINAL legítimo):

      1) Firma de las últimas 3 palabras del guion → si aparece 2+ veces
         en la transcripción, hay eco; cut tras la primera aparición.
      2) Firma de las últimas 2 palabras del guion → idem.
      3) Última palabra "significativa" (≥4 chars) del guion → si en la
         transcripción aparece 2+ veces (y la última ocurrencia está
         visiblemente después de la primera), cut tras la primera.

    Esto cubre los casos:
      - MiniMax repite la frase final entera ("the completed survival cabin." x N)
      - MiniMax repite solo el final ("survival cabin survival cabin")
      - MiniMax repite solo la última palabra ("cabin. cabin. cabin.")

    Sanity check final: no devolver un cut tan temprano que dejaría el
    audio en < 30% de su longitud actual (eso indicaría falso positivo).
    """
    if not words or not script:
        return None

    script_tokens = [
        t.strip(".!?,;:\"'").lower()
        for t in script.split()
        if t.strip(".!?,;:\"'")
    ]
    whisper_norm = [
        w["word"].strip(".!?,;:\"'").lower()
        for w in words
    ]
    if len(script_tokens) < 1 or len(whisper_norm) < 2:
        return None

    def _safe_cut(idx: int) -> int | None:
        """Solo aceptar el cut si conserva >30% de las palabras totales.
        Evita falsos positivos cuando la "firma" matchea muy al inicio."""
        if idx <= 0 or idx >= len(whisper_norm):
            return None
        if idx / max(1, len(whisper_norm)) < 0.3:
            return None
        return idx

    # 1) Firma de 3 palabras
    if len(script_tokens) >= 3 and len(whisper_norm) >= 3:
        sig3 = tuple(script_tokens[-3:])
        matches = [
            i for i in range(len(whisper_norm) - 2)
            if tuple(whisper_norm[i : i + 3]) == sig3
        ]
        if len(matches) >= 2:
            cut = _safe_cut(matches[0] + 3)
            if cut is not None:
                return cut

    # 2) Firma de 2 palabras
    if len(script_tokens) >= 2 and len(whisper_norm) >= 2:
        sig2 = tuple(script_tokens[-2:])
        matches = [
            i for i in range(len(whisper_norm) - 1)
            if tuple(whisper_norm[i : i + 2]) == sig2
        ]
        if len(matches) >= 2:
            cut = _safe_cut(matches[0] + 2)
            if cut is not None:
                return cut

    # 3) Última palabra significativa (≥4 chars) → contamos repeticiones
    last_meaningful: str | None = None
    for tok in reversed(script_tokens):
        if len(tok) >= 4:
            last_meaningful = tok
            break
    if last_meaningful is None:
        last_meaningful = script_tokens[-1]
    occurrences = [
        i for i, w in enumerate(whisper_norm)
        if w == last_meaningful
    ]
    if len(occurrences) >= 2:
        # Solo cut si las ocurrencias están suficientemente separadas
        # (>2 palabras) — eso indica eco, no una palabra que aparece
        # naturalmente repetida en el guion.
        if occurrences[-1] - occurrences[0] > 2:
            cut = _safe_cut(occurrences[0] + 1)
            if cut is not None:
                return cut

    return None


def _trim_audio_to(audio_path: str, max_seconds: float, log_callback=None) -> None:
    """Trunca el MP3 a `max_seconds` (in-place) con ffmpeg `-t`."""
    if max_seconds <= 0:
        return
    tmp = audio_path + ".tail_trim.mp3"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", audio_path, "-t", f"{max_seconds:.3f}",
        "-acodec", "libmp3lame", "-b:a", "128k", tmp,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError as e:
        if log_callback:
            stderr = (e.stderr or b"").decode("utf-8", errors="ignore")[:200]
            log_callback(f"⚠️ tail trim falló: {stderr} — uso audio original.")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return
    os.replace(tmp, audio_path)


def _trim_leading_silence(audio_path: str, log_callback=None) -> None:
    """Trim silencio inicial del MP3 in-place con ffmpeg `silenceremove`.

    Necesario porque MiniMax `speech-2.5-turbo-preview` puede meter varios
    segundos de silencio al inicio del MP3 (a veces 1-2s, a veces 15-20s
    según voice_id y contenido). Sin trim, Whisper transcribe correctamente
    pero los subs aparecen empezando ese offset → desincronización con
    el vídeo. Tras el trim, audio empieza en t=0 y subs en t=0.

    Threshold -45dB es conservador (un susurro es ~30dB; silencio digital
    es < -60dB). Si silenceremove falla, deja el audio original.
    """
    if not os.path.exists(audio_path):
        return
    tmp = audio_path + ".trim.mp3"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", audio_path,
        "-af",
        "silenceremove=start_periods=1:start_silence=0:start_threshold=-45dB",
        "-acodec", "libmp3lame", "-b:a", "128k",
        tmp,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError as e:
        if log_callback:
            stderr = (e.stderr or b"").decode("utf-8", errors="ignore")[:200]
            log_callback(f"⚠️ silenceremove falló: {stderr} — uso audio sin trim.")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return
    # Sanity check muy laxo: solo revertir si el trim deja menos de 1s
    # de audio (caso patológico donde silenceremove se come todo).
    # Caso real del usuario: 15s silencio + 3s habla = trim quita 83%
    # del archivo, lo cual es el comportamiento DESEADO.
    try:
        before = _probe_duration_seconds(audio_path)
        after = _probe_duration_seconds(tmp)
    except Exception:
        before, after = 0.0, 0.0
    if after < 1.0:
        if log_callback:
            log_callback(
                f"⚠️ silenceremove dejó audio < 1s "
                f"({before:.1f}s → {after:.1f}s) — revierto."
            )
        try:
            os.remove(tmp)
        except OSError:
            pass
        return
    os.replace(tmp, audio_path)
    if log_callback and (before - after) > 0.5:
        log_callback(
            f"✂️ Silencio inicial trimeado: {before:.1f}s → {after:.1f}s "
            f"(quitados {before - after:.1f}s)."
        )


_ORIGINAL_AUDIO_VOLUME = 0.85  # ~-1.4 dB → casi idéntico, lo justo para romper el match exacto de TikTok


def _has_audio_stream(video_path: str) -> bool:
    """True si el vídeo tiene al menos una pista de audio (ffprobe)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", video_path],
            check=True, capture_output=True, text=True, timeout=15,
        )
        return bool(out.stdout.strip())
    except Exception:
        return False


def _mux_audio_over_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    *,
    log_callback=None,
) -> str:
    """Mezcla la narración con el audio original del vídeo (bajado en dB).

    Si el vídeo no tiene audio, cae a comportamiento clásico: solo narración
    paddeada con silencio.

    Diseño del filtro (cuando hay audio original):
      - `[0:a]volume=0.20` → atenúa el original a ~-14dB (de fondo, no se
        confunde con la narración pero sigue oyéndose).
      - `[1:a]apad` → la narración rellena con silencio hasta el fin del
        vídeo. Sin esto, MoviePy en la pasada de subs repite el último
        buffer audio al pedir samples más allá del fin → última palabra
        loopeada hasta el final del clip.
      - `amix=inputs=2:duration=first` → toma la duración del primer
        input (vídeo original) y mezcla.
      - `dynaudnorm` opcional: NO se aplica para no aplastar la dinámica.
    `-shortest` se mantiene como salvavidas si la narración resulta más
    larga por bug del trim.
    """
    try:
        video_dur = _probe_duration_seconds(video_path)
    except Exception:
        video_dur = 0.0

    if _has_audio_stream(video_path):
        filter_complex = (
            f"[0:a]volume={_ORIGINAL_AUDIO_VOLUME}[bg];"
            "[1:a]apad[voice];"
            "[bg][voice]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
        )
        if log_callback:
            log_callback(
                f"🔊 Mezclando narración + audio original a {_ORIGINAL_AUDIO_VOLUME * 100:.0f}% "
                f"(cap {video_dur:.1f}s)…"
            )
    else:
        filter_complex = "[1:a]apad[aout]"
        if log_callback:
            log_callback(
                f"🔊 Vídeo sin audio — solo narración (cap {video_dur:.1f}s, silencio al final)…"
            )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    return output_path


def _apply_visual_transforms(
    video_path: str,
    output_path: str,
    *,
    upscale_1080p: bool,
    saturation: float,
    pulse_zoom: bool,
    mirror: bool = False,
    log_callback=None,
) -> str:
    """Aplica las transformaciones visuales anti-copyright:
    - Zoom suave + pulso ligero (firma visual variable)
    - Saturación (+25% por defecto)
    - Strip de TODOS los metadatos
    - Opcional upscale a 1080p (Lanczos) si el vídeo es < 1080p de ancho

    Sin overlay de texto — los subtítulos se añaden en una pasada separada.
    Usa ffmpeg directo para que sea más rápido que moviepy.
    """
    # Detectar ancho actual
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0:s=x", video_path],
            check=True, capture_output=True, text=True, timeout=15,
        )
        w_str, h_str = probe.stdout.strip().split("x")[:2]
        src_w = int(w_str)
        src_h = int(h_str)
    except Exception:
        src_w, src_h = 720, 1280

    vf_parts: list[str] = []
    # Espejo horizontal (anti-copy + cambio de orientación visual).
    # Va primero para que cualquier scale/crop posterior trabaje sobre
    # el frame ya volteado.
    if mirror:
        vf_parts.append("hflip")
        if log_callback:
            log_callback("🪞 Modo espejo activo (volteo horizontal).")
    # Zoom + crop centrado. 1.12x es visible a simple vista (~12% recorte
    # por lado) y rompe el alineamiento de hashes pHash/dHash que TikTok
    # usa para detectar reuploads. 1.08x previo era imperceptible.
    if pulse_zoom:
        vf_parts.append("scale=iw*1.12:ih*1.12:flags=lanczos")
        vf_parts.append(f"crop={src_w}:{src_h}")
        if log_callback:
            log_callback("🔍 Zoom + crop centrado 1.12x activo.")
    # EQ combinado: saturación + brillo/contraste sutil + gamma. Cambia
    # la firma tonal del frame sin notarse mucho al ojo. La saturación
    # +25% sí es perceptible.
    sat = saturation if saturation > 0 else 1.0
    vf_parts.append(
        f"eq=saturation={sat:.2f}:brightness=0.02:contrast=1.04:gamma=0.98"
    )
    # Ruido sutil por frame — varía cada frame de forma pseudoaleatoria
    # (`t+u` = temporal + uniforme). Defeat de SSIM/perceptual hashing
    # sin que el ojo lo perciba a tamaño TikTok.
    vf_parts.append("noise=c0s=3:c0f=t+u")
    # Upscale 1080p (si <1080 ancho)
    target_bitrate = "4500k"
    if upscale_1080p and src_w < 1080:
        vf_parts.append("scale=1080:-2:flags=lanczos")
        target_bitrate = "6500k"
        if log_callback:
            log_callback(f"⬆️ Upscale 1080p activo ({src_w}x{src_h} → 1080p)")

    vf = ",".join(vf_parts) if vf_parts else "null"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-b:v", target_bitrate,
        "-c:a", "copy",
        # Metadata strip — clave para evadir hashing simple
        "-map_metadata", "-1",
        "-map_chapters", "-1",
        "-flags", "+bitexact",
        "-fflags", "+bitexact",
        output_path,
    ]
    if log_callback:
        log_callback(f"🎨 Visuales anti-copy (zoom + sat + meta strip)…")
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    return output_path


def _next_output_name(out_dir: Path) -> str:
    """Devuelve `Construccion_<N>.mp4` con N = #archivos+1 en la carpeta.

    Mismo patrón que Presidentes (`TikTok_AUTO_N.mp4`). Si por race
    condition ya existiera, añade timestamp HHMMSS al final.
    """
    try:
        existing = [
            f for f in os.listdir(out_dir)
            if f.endswith(".mp4") and f.startswith("Construccion_")
        ]
        name = f"Construccion_{len(existing) + 1}.mp4"
    except Exception:
        from datetime import datetime
        name = f"Construccion_{datetime.now().strftime('%H%M%S')}.mp4"
    if (out_dir / name).exists():
        from datetime import datetime
        stem = Path(name).stem
        name = f"{stem}_{datetime.now().strftime('%H%M%S')}.mp4"
    return name


def run_pipeline(
    *,
    input_path: str,
    output_folder: str,
    config: dict,
    voice_id: str,
    subs_style: dict,
    upscale_1080p: bool = False,
    saturation: float = 1.25,
    pulse_zoom: bool = True,
    mirror: bool = False,
    whisper_model_size: str = "small",
    quality_label: str = "1080p (Lento)",
    gemini_model: str = "gemini-2.5-pro",
    manual_script: str | None = None,
    output_name: str | None = None,
    on_log=None,
    on_progress=None,
) -> str:
    """Orquestador completo del nicho Construcción POV.

    Devuelve la ruta del MP4 final.

    Si se pasa `manual_script`, se omite la llamada a Gemini (coste $0).
    `gemini_model` permite elegir Flash (default, barato) o Pro (más caro).
    """
    log = on_log or (lambda _msg: None)
    prog = on_progress or (lambda _p, _l: None)

    from src.construccion_pov.script_generator import generate_script
    from src.locutor import generate_single_audio
    from src.subtitles_only import (
        QUALITY_FROM_SIDEBAR,
        render_subtitles_on_video,
    )

    out_dir = Path(output_folder) / "CONSTRUCCION_POV"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())

    temp_dir = Path(config.get("paths", {}).get("temp_folder", "./temp_work"))
    temp_dir.mkdir(parents=True, exist_ok=True)

    narration_path = temp_dir / f"pov_narration_{ts}.mp3"
    muxed_path = temp_dir / f"pov_muxed_{ts}.mp4"
    visual_path = temp_dir / f"pov_visual_{ts}.mp4"
    # Si el caller pasó un `output_name` proyectado en el enqueue (para
    # que coincida con el título de la cola), lo respetamos. Si por race
    # condition ya existe, añadimos timestamp como fallback. Sin
    # `output_name` (jobs viejos en cola) usamos el contador automático.
    if output_name:
        candidate = out_dir / output_name
        if candidate.exists():
            from datetime import datetime as _dt
            stem = Path(output_name).stem
            candidate = out_dir / f"{stem}_{_dt.now().strftime('%H%M%S')}.mp4"
        final_path = candidate
    else:
        final_path = out_dir / _next_output_name(out_dir)

    # 0) Probe duración
    prog(0.02, "🔎 Leyendo duración del vídeo…")
    duration_s = _probe_duration_seconds(input_path)
    log(f"📐 Duración detectada: {duration_s:.1f}s")
    prog(0.05, f"⏱️ {duration_s:.1f}s")

    # 1) Guion: manual o Gemini
    if manual_script and manual_script.strip():
        script_text = manual_script.strip()
        log(f"📝 Guion manual pegado por el usuario ({len(script_text)} chars) — Gemini omitido (ahorro $).")
        prog(0.30, f"📝 Guion manual {len(script_text)}c")
    else:
        prog(0.08, f"🤖 Gemini ({gemini_model}) analizando vídeo…")
        log(f"🤖 Llamando a Gemini {gemini_model} para generar el guion narrado…")
        script_text = generate_script(
            input_path,
            video_duration_s=duration_s,
            model=gemini_model,
            log_callback=log,
        )
        log(f"📝 Guion generado ({len(script_text)} chars).")
        prog(0.30, f"📝 Guion {len(script_text)}c")

    # 2) MiniMax TTS
    prog(0.32, "🎙️ MiniMax sintetizando voz…")
    log(f"🎙️ TTS MiniMax (voice={voice_id})…")
    generate_single_audio(
        script_text,
        str(narration_path),
        voice_id_override=voice_id,
    )
    _trim_leading_silence(str(narration_path), log_callback=log)
    prog(0.50, "✅ Voz lista")
    log(f"✅ Narración MP3 → {narration_path}")

    # 3) Whisper transcribe la narración (ANTES del mux). Usamos sus
    # timestamps tanto para los subs como para detectar y trimear el eco
    # de cola que MiniMax mete a veces (repite las últimas 2-3 palabras
    # del guion en bucle hasta llenar). Patrón idéntico a Pronósticos
    # (transcribe() simple, sin initial_prompt, sin VAD custom).
    from src.subtitles import transcribe
    prog(0.55, "🎙️ Whisper alineando palabras…")
    words = transcribe(
        str(narration_path),
        model_size=whisper_model_size,
        language="en",
    )
    if not words:
        raise RuntimeError(
            "Whisper no detectó palabras. Prueba un modelo más grande."
        )
    log(f"✅ {len(words)} palabras (whisper {whisper_model_size}).")

    # 3.5) Trim por ANCHOR del SCRIPT (técnica simple y fiable).
    #
    # Idea: buscamos las últimas N palabras del SCRIPT como una secuencia
    # (anchor) en la transcripción de Whisper. La PRIMERA aparición de
    # ese anchor es donde termina la narración legítima. Todo lo posterior
    # es eco (MiniMax repite el final por bug del modelo TTS).
    #
    # Probamos anchors de 3 → 2 → 1 palabra(s) en cascada para tolerar
    # casos donde Whisper transcriba ligeramente distinto al script.
    #
    # Cortamos en: `anchor_last_word.start + (chars / rate_medido) + 0.3s`
    # — usamos START del último anchor word (fiable) + duración esperada
    # de esa palabra (también fiable porque medimos la tasa real).
    audio_dur = _probe_duration_seconds(str(narration_path))
    last_word_end = float(words[-1]["end"]) if words else 0.0
    log(f"📊 [trim] MP3: {audio_dur:.2f}s · última palabra Whisper @ {last_word_end:.2f}s · {len(words)} palabras")

    # Medir SPEECH RATE real: chars/segundo solo dentro de palabras
    # (excluyendo pausas inter-palabra). El rate global subestima la
    # velocidad real porque mete pausas en el denominador → palabras
    # parecen más largas de lo que son → buffer demasiado generoso →
    # eco se cuela. Speech rate típico MiniMax EN: 16-20 c/s.
    speech_rate = 18.0  # fallback MiniMax EN típico
    if len(words) >= 8:
        sample_n = max(5, int(len(words) * 0.7))
        sample = words[:sample_n]
        sample_chars = sum(len(w["word"].strip(".,!?;:'\"")) for w in sample)
        # Sumamos la duración INTERNA de cada palabra (no el span total
        # que incluye pausas).
        sample_word_durs = sum(
            float(w["end"]) - float(w["start"]) for w in sample
        )
        if sample_word_durs > 0.5 and sample_chars > 20:
            speech_rate = sample_chars / sample_word_durs
    log(f"📊 [trim] speech rate medido: {speech_rate:.2f} chars/s (solo speech, sin pausas)")

    # Anchor matching
    script_clean = [
        t.strip(".,!?;:'\"").lower()
        for t in script_text.split()
        if t.strip(".,!?;:'\"")
    ]
    whisper_clean = [
        w["word"].strip(".,!?;:'\"").lower()
        for w in words
    ]

    cut_time: float | None = None
    matched_at: int | None = None
    matched_anchor: str | None = None

    for anchor_len in (3, 2, 1):
        if len(script_clean) < anchor_len or len(whisper_clean) < anchor_len:
            continue
        anchor = tuple(script_clean[-anchor_len:])
        # FIRST match = legitimate end (cualquier match posterior es eco)
        for i in range(len(whisper_clean) - anchor_len + 1):
            if tuple(whisper_clean[i : i + anchor_len]) == anchor:
                matched_at = i + anchor_len - 1  # índice del último word del anchor
                last_anchor_word = words[matched_at]
                # Cut: start de la palabra anchor + duración esperada al
                # speech_rate real (sin pausas) + 150ms buffer mínimo.
                # Buffer pequeño porque speech_rate ya refleja la velocidad
                # interna real de pronunciación → no necesitamos compensar.
                anchor_word_chars = max(1, len(
                    last_anchor_word["word"].strip(".,!?;:'\"")
                ))
                expected_word_dur = anchor_word_chars / speech_rate
                cut_time = float(last_anchor_word["start"]) + expected_word_dur + 0.15
                matched_anchor = " ".join(anchor)
                break
        if cut_time is not None:
            break

    if cut_time is None:
        log(
            f"⚠️ [trim] No se encontró el anchor del script ({' '.join(script_clean[-3:])}) "
            f"en la transcripción → no se aplica trim (algo raro pasó con Whisper)."
        )
    else:
        log(
            f"🎯 [trim] anchor '{matched_anchor}' encontrado en posición "
            f"{matched_at}/{len(words)} · palabra '{words[matched_at]['word']}' "
            f"@ start={float(words[matched_at]['start']):.2f}s "
            f"→ cut calculado = {cut_time:.2f}s"
        )

        # Trim SIEMPRE que haya anchor (sin threshold). Si cut_time >
        # audio_dur, ffmpeg `-t` simplemente no recorta más allá del fin
        # del archivo — es seguro llamar siempre.
        _trim_audio_to(str(narration_path), cut_time, log_callback=log)
        new_dur = _probe_duration_seconds(str(narration_path))
        delta = audio_dur - new_dur
        log(
            f"✂️ [trim] MP3 trimeado: {audio_dur:.2f}s → {new_dur:.2f}s "
            f"({delta:+.2f}s {'eco eliminado' if delta > 0 else 'sin cambios'})"
        )
        # Cap el end de la última palabra legítima para que su sub
        # no se prolongue en el eco trimeado.
        if matched_at is not None and matched_at < len(words):
            words[matched_at]["end"] = min(
                float(words[matched_at]["end"]),
                cut_time - 0.05,
            )
        # Filtrar palabras posteriores al anchor (son eco)
        original_n = len(words)
        words = words[: matched_at + 1]
        if len(words) < original_n:
            log(f"⌫ [trim] {original_n - len(words)} palabras posteriores al anchor filtradas (eco)")

    prog(0.62, f"✅ {len(words)} palabras")

    # 4) Mux audio (ya trimeado si había eco) sobre vídeo. Sin -shortest,
    # el vídeo conserva su duración; si la narración acaba antes, el
    # resto reproduce silencio.
    prog(0.65, "🔊 Mezclando audio nuevo con vídeo…")
    _mux_audio_over_video(
        input_path, str(narration_path), str(muxed_path),
        log_callback=log,
    )
    prog(0.75, "✅ Audio reemplazado")

    # 5) Transformaciones visuales anti-copy
    prog(0.78, "🎨 Aplicando visuales anti-copy…")
    _apply_visual_transforms(
        str(muxed_path), str(visual_path),
        upscale_1080p=upscale_1080p,
        saturation=saturation,
        pulse_zoom=pulse_zoom,
        mirror=mirror,
        log_callback=log,
    )
    prog(0.85, "✅ Visuales aplicadas")

    # 6) Render karaoke subs
    prog(0.88, "🎬 Renderizando subtítulos…")
    quality = QUALITY_FROM_SIDEBAR.get(
        quality_label,
        {"preset": "medium", "crf": 20, "max_long_side": 1280},
    )
    # Cap del último sub al final real de la narración + 0.3s. Sin esto
    # la última palabra (p.ej. "CABIN") quedaría congelada en pantalla
    # durante la cola silenciosa del vídeo (5-6 segundos típicamente).
    last_word_end_time = float(words[-1]["end"]) + 0.3 if words else None
    render_subtitles_on_video(
        str(visual_path),
        words,
        subs_style,
        str(final_path),
        quality_settings=quality,
        log_callback=log,
        last_chunk_max_end=last_word_end_time,
    )
    prog(1.0, "✅ Construcción POV listo")
    log(f"✅ Salida → {final_path}")

    # Cleanup intermedios (no críticos)
    for p in (narration_path, muxed_path, visual_path):
        try:
            os.remove(p)
        except OSError:
            pass

    return str(final_path)
