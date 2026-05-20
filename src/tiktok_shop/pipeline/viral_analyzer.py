"""Analizador de vídeo viral — Fase 5 del módulo TikTok Shop.

Entrada: un MP4 de referencia (vídeo que ya funciona en TikTok).
Salida: una `ShopPresetConfig` rellena con la mejor aproximación posible
        + un breakdown de coste para mostrar al usuario en UI.

Pipeline (síncrono, ~10-30s típico):

  1. ffprobe duración real.
  2. ffmpeg extrae audio (.wav 16kHz mono) → Whisper transcribe → word
     timings. De ahí salen: `hook_text` (texto de los primeros 3s),
     `voiceover_script` (transcript completo), `n_words`.
  3. ffmpeg muestrea N frames del vídeo a JPG en temp/. N = min(30,
     duración_seg). Se mantienen en disco hasta enviarlos a Gemini, luego
     se borran.
  4. Gemini (default `gemini-2.5-flash`) recibe TODOS los frames + el
     transcript + duración + flags (same_product) y devuelve un JSON
     estructurado con la "receta" del vídeo (ver `prompts/viral_analyzer.md`).
  5. El JSON de Gemini se mappea a `ShopPresetConfig` según el modo objetivo
     (`auto_video` / `veo3` / `nano_banana`) — campos irrelevantes para el
     modo se omiten.
  6. Se registra el coste en `cost_tracking.record_gemini` (Whisper local
     no se cobra).

NUNCA aborta por falta de un input opcional. Si Gemini falla, devuelve un
config "best effort" con los datos del transcript + flags de fallback.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Literal

import cv2

LogCallback = Callable[[str], None]


def _noop(_: str) -> None:
    pass


PresetKind = Literal["auto_video", "veo3", "nano_banana"]


def _probe_duration_seconds(video_path: str) -> float:
    """Reusa el helper de Construcción POV (más rápido que moviepy)."""
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


def _extract_audio(video_path: str, out_wav: str) -> str:
    """Extrae audio mono 16kHz a WAV (formato óptimo para Whisper)."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        out_wav,
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    return out_wav


def _sample_frames(
    video_path: str, out_dir: Path, *, max_frames: int = 30,
) -> list[str]:
    """Muestrea ~1 frame por segundo (cap a `max_frames`). Devuelve paths
    JPG ordenados. Usa OpenCV (ya en requirements) para evitar otra
    invocación a ffmpeg con filtros complejos."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_s = total_frames / fps if fps > 0 else 0.0
    if duration_s <= 0:
        cap.release()
        return []

    target_n = min(max_frames, max(3, int(duration_s)))
    # Repartir uniformemente en el rango [0.2s, duration - 0.2s]
    timestamps = [
        0.2 + (duration_s - 0.4) * i / max(1, target_n - 1)
        for i in range(target_n)
    ]
    paths: list[str] = []
    for i, t in enumerate(timestamps):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        # Reescala a max 720px lado largo para reducir tokens de imagen.
        h, w = frame.shape[:2]
        long_side = max(h, w)
        if long_side > 720:
            scale = 720.0 / long_side
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        out_path = out_dir / f"frame_{i:02d}.jpg"
        cv2.imwrite(str(out_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        paths.append(str(out_path))
    cap.release()
    return paths


def _safe_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_str(v: Any, default: str) -> str:
    if isinstance(v, str) and v.strip():
        return v.strip()
    return default


def _map_to_auto_video(detected: dict) -> dict:
    """Mapea el JSON de Gemini a un preset de modo `auto_video`."""
    tier = _safe_str(detected.get("tier_recommendation"), "standard")
    if tier not in ("standard", "advanced", "pro"):
        tier = "standard"
    strategy = _safe_str(detected.get("strategy_recommendation"), "dynamic")
    if strategy not in ("dynamic", "cinematic"):
        strategy = "dynamic"
    duration = _safe_int(detected.get("duration_seconds_recommendation"), 15)
    duration = min(30, max(5, duration))
    resolution = _safe_str(detected.get("resolution_recommendation"), "720p")
    if tier == "standard" and resolution != "720p":
        resolution = "720p"

    overlays = {
        "hook_box": {
            "enabled": bool(detected.get("has_text_hook_at_start", False)),
            "text": _safe_str(detected.get("hook_text"), ""),
            "animation": _safe_str(detected.get("text_hook_animation"), "swipe_left"),
            "duration": 5.0,
        },
        "cta_arrow": {
            "enabled": bool(detected.get("has_cta_arrow_at_end", False)),
            "fallback_last_seconds": float(
                _safe_int(detected.get("cta_seconds_from_end"), 4) or 4
            ),
            # sticker_file lo deja en blanco — el user lo elige al guardar
            "sticker_file": "",
        },
    }
    if overlays["hook_box"]["animation"] not in (
        "swipe_left", "news_flash", "slide_in_out", "fade",
    ):
        overlays["hook_box"]["animation"] = "swipe_left"

    return {
        "tier": tier,
        "strategy": strategy,
        "duration_seconds": duration,
        "resolution": resolution,
        "hook_category": _safe_str(detected.get("hook_category"), "curiosity"),
        "hook_custom": _safe_str(detected.get("hook_text"), ""),
        "target_audience": _safe_str(detected.get("target_audience"), "Generalista"),
        "voice_enabled": True,
        "voice_id": "Spanish_EnergeticBoy",
        "shoppable": bool(detected.get("shoppable_signals", False)),
        "overlays": overlays,
    }


def _map_to_veo3(detected: dict) -> dict:
    """Veo3 modo prompt-only — solo necesita hook + audience."""
    return {
        "hook_category": _safe_str(detected.get("hook_category"), "curiosity"),
        "hook_custom": _safe_str(detected.get("hook_text"), ""),
        "target_audience": _safe_str(detected.get("target_audience"), "Generalista"),
    }


def _map_to_nano_banana(detected: dict) -> dict:
    """Nano Banana — n_angles + use_cases derivados del style detectado."""
    use_cases = ["packshot", "lifestyle", "macro"]
    camera_style = _safe_str(detected.get("camera_style"), "static").lower()
    if "macro" in camera_style or "asmr" in camera_style:
        use_cases = ["macro", "packshot", "studio"]
    elif "handheld" in camera_style or "lifestyle" in camera_style:
        use_cases = ["lifestyle", "in_hand", "outdoor"]

    return {
        "n_angles": 5,
        "use_cases": use_cases,
    }


def analyze_viral_video(
    video_path: str,
    *,
    target_kind: PresetKind,
    same_product: bool,
    gemini_model: str = "gemini-2.5-flash",
    temp_folder: str = "./temp_work",
    log_callback: LogCallback = _noop,
) -> dict:
    """Devuelve `{"config": dict, "detected": dict, "cost_breakdown": dict}`.

    El campo `config` es el preset listo para `useSaveShopPreset`.
    `detected` contiene la respuesta cruda de Gemini para mostrar en UI.
    `cost_breakdown` contiene `{gemini_usd, total_usd}` (Whisper local = $0).
    """
    log_callback(f"📐 Probing duración de '{video_path}'…")
    duration_s = _probe_duration_seconds(video_path)
    log_callback(f"⏱️ Duración: {duration_s:.1f}s")

    ts = int(time.time())
    tmp_dir = Path(temp_folder) / f"viral_{ts}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 1. Whisper sobre audio extraído
    audio_path = str(tmp_dir / "audio.wav")
    log_callback("🎙️ Extrayendo audio…")
    try:
        _extract_audio(video_path, audio_path)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"ffmpeg no pudo extraer audio del vídeo: "
            f"{(e.stderr or b'').decode('utf-8', errors='ignore')[:200]}"
        )

    log_callback("🎙️ Transcribiendo (Whisper small, local)…")
    from src.subtitles import transcribe
    words = transcribe(audio_path, model_size="small", language=None)
    n_words = len(words)
    log_callback(f"📝 {n_words} palabras detectadas.")

    transcript = " ".join(w.get("word", "") for w in words).strip()
    # Hook = todo lo dicho en los primeros 3s
    hook_text = " ".join(
        w["word"] for w in words
        if isinstance(w.get("start"), (int, float)) and float(w["start"]) < 3.0
    ).strip() or transcript[:80]

    # 2. Frames
    log_callback("🎞️ Muestreando frames (1/s, max 30)…")
    frames_dir = tmp_dir / "frames"
    frame_paths = _sample_frames(video_path, frames_dir, max_frames=30)
    log_callback(f"🖼️ {len(frame_paths)} frames listos para Gemini.")
    if not frame_paths:
        raise RuntimeError("No se pudieron extraer frames del vídeo.")

    # 3. Llamada a Gemini
    from src.tiktok_shop.api.gemini import generate_json, is_configured, load_system_prompt
    if not is_configured():
        raise RuntimeError(
            "Gemini no configurado — define GOOGLE_GEMINI_KEY_FREE o "
            "GOOGLE_GEMINI_KEY_PAID en .env para usar replicar viral."
        )

    system_prompt = load_system_prompt("viral_analyzer.md")
    user_msg = (
        f"Total duration: {duration_s:.1f} seconds\n"
        f"Same product as user's: {'yes' if same_product else 'no — competitor reference'}\n"
        f"Target preset kind: {target_kind}\n"
        f"Word-level transcript ({n_words} words): {transcript[:3000]}\n\n"
        f"Frames are attached, sampled at ~1 fps in chronological order."
    )

    log_callback(f"🤖 Llamando a Gemini '{gemini_model}' con {len(frame_paths)} frames…")
    try:
        detected_raw = generate_json(
            system_prompt, user_msg,
            model=gemini_model,
            images=frame_paths,
            temperature=0.4,
        )
    except Exception as e:
        # Cleanup antes de propagar
        _cleanup(tmp_dir)
        raise RuntimeError(f"Gemini falló al analizar el vídeo: {e}")

    if not isinstance(detected_raw, dict):
        log_callback(f"⚠️ Gemini devolvió tipo inesperado ({type(detected_raw).__name__}), usando dict vacío.")
        detected_raw = {}

    # Aseguramos que el hook_text del transcript se usa si Gemini no lo extrajo bien.
    if not detected_raw.get("hook_text"):
        detected_raw["hook_text"] = hook_text

    # 4. Cost tracking — `record_gemini` consume contextvar; si no hay
    # tracker activo (caso típico: endpoint síncrono fuera de un job),
    # falla silenciosamente. Para cubrir ambos casos calculamos el coste
    # localmente y lo devolvemos en cost_breakdown, además del registro.
    from src.cost_tracking import _resolve_gemini_rates
    # Estimación de tokens — Gemini cuenta ~258 tokens/imagen a baja
    # resolución, +overhead del prompt. Es una aproximación; el coste real
    # se logueará si hay tracker activo.
    est_input_tokens = len(frame_paths) * 258 + len(system_prompt) // 4 + len(user_msg) // 4
    est_output_tokens = 600
    in_rate, out_rate = _resolve_gemini_rates(gemini_model)
    cost_usd = (
        (est_input_tokens / 1_000_000) * in_rate
        + (est_output_tokens / 1_000_000) * out_rate
    )
    try:
        from src.cost_tracking import record_gemini
        record_gemini(
            input_tokens=est_input_tokens,
            output_tokens=est_output_tokens,
            model=gemini_model,
            detail="viral_analyzer",
        )
    except Exception:
        pass  # contextvar no activo, ok

    # 5. Mapping al config del modo objetivo
    if target_kind == "auto_video":
        config = _map_to_auto_video(detected_raw)
    elif target_kind == "veo3":
        config = _map_to_veo3(detected_raw)
    else:
        config = _map_to_nano_banana(detected_raw)

    # 6. Cleanup
    _cleanup(tmp_dir)

    return {
        "config": config,
        "detected": {
            **detected_raw,
            "duration_seconds": duration_s,
            "n_words": n_words,
        },
        "cost_breakdown": {
            "gemini_usd": round(cost_usd, 4),
            "whisper_usd": 0.0,
            "total_usd": round(cost_usd, 4),
            "gemini_model": gemini_model,
            "input_tokens_est": est_input_tokens,
            "output_tokens_est": est_output_tokens,
        },
    }


def _cleanup(tmp_dir: Path) -> None:
    """Borra el subdir temporal del análisis. Errores se ignoran (cosmético)."""
    try:
        for f in tmp_dir.rglob("*"):
            if f.is_file():
                f.unlink(missing_ok=True)
        for d in sorted(tmp_dir.rglob("*"), reverse=True):
            if d.is_dir():
                d.rmdir()
        tmp_dir.rmdir()
    except OSError:
        pass
