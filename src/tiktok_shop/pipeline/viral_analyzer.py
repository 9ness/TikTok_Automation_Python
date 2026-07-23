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


def _map_to_video_preset(
    raw_preset: dict,
    *,
    product: Any,
    available_photos: list[str],
) -> dict:
    """Convierte el bloque `video_preset` del JSON de Gemini en un dict
    listo para crear un `VideoPreset` (mismo formato que el preset_generator).
    Aplica los mismos sanitizers para garantizar consistencia con los
    presets autogenerados.
    """
    # Importes locales para evitar circular imports en tests.
    from src.tiktok_shop.pipeline.preset_generator import (
        _parse_cta_arrow_style,
        _parse_overlay_style,
        _parse_subtitle_style,
        _resolve_shot_strategy,
        _sanitize_tiers,
        _sanitize_veo3_photo_filenames,
        _safe_tone,
    )

    if not isinstance(raw_preset, dict):
        raw_preset = {}

    kind = _safe_str(raw_preset.get("kind"), "scripted")
    if kind not in ("music", "scripted"):
        kind = "scripted"

    style = _safe_str(raw_preset.get("style"), "voiceover")
    if style not in ("voiceover", "creator_pov"):
        style = "voiceover"

    duration_s = max(5, min(60, _safe_int(raw_preset.get("duration_s"), 12)))

    # veo3_prompt_segments: si duration > 10s, Flow Gemini exige
    # encadenar N clips de ~8-10s. Saneamos la lista cruda de Gemini
    # (string → strip + cap) y la usamos como flag para que
    # `_sanitize_tiers` mantenga `veo3_prompt_only` compatible aunque
    # `duration_s` > 10.
    raw_segments = raw_preset.get("veo3_prompt_segments")
    veo3_segments: list[str] = []
    if isinstance(raw_segments, list):
        for seg in raw_segments:
            txt = _safe_str(seg, "")[:2500]
            if txt:
                veo3_segments.append(txt)
    veo3_segments = veo3_segments[:6]  # safety cap (60s / 10s)

    # compatible_tiers: confiamos en lo que Gemini dijo, pero saneamos
    # contra las reglas duras (Veo3 ≤10s salvo segments, creator_pov no Std/Adv).
    proposed_tiers = raw_preset.get("compatible_tiers")
    if not isinstance(proposed_tiers, list):
        proposed_tiers = ["standard", "advanced", "pro", "veo3_prompt_only"]
    tiers = _sanitize_tiers(
        [str(t) for t in proposed_tiers],
        duration_s=duration_s,
        style=style,
        has_veo3_segments=bool(veo3_segments),
    )

    # shot_style + strategy con failsafes del modelo
    shot_style, strategy_val = _resolve_shot_strategy(
        duration_s=duration_s,
        kind=kind,
        style=style,
        raw_shot_style=raw_preset.get("shot_style"),
        raw_strategy=raw_preset.get("strategy"),
        compatible_tiers=tiers,
    )

    # Sanea sub-objetos (overlay, subs, cta_arrow) con los helpers que
    # ya usa el preset_generator → garantiza coherencia visual con el
    # resto del producto.
    text_overlay_style = _parse_overlay_style(raw_preset.get("text_overlay_style"))
    # Música → subs OFF por defecto; scripted → respeta lo que dijo Gemini
    subtitle_raw = raw_preset.get("subtitle_style")
    if kind == "music" and (not isinstance(subtitle_raw, dict) or "enabled" not in subtitle_raw):
        from src.tiktok_shop.models.video_preset import SubtitleStyle
        subtitle_style = SubtitleStyle(enabled=False)
    else:
        subtitle_style = _parse_subtitle_style(subtitle_raw)
    cta_arrow_style = _parse_cta_arrow_style(raw_preset.get("cta_arrow_style"))

    veo3_photos = _sanitize_veo3_photo_filenames(
        raw_preset.get("veo3_photo_filenames"),
        available=available_photos,
    )

    name = _safe_str(raw_preset.get("name"), f"Réplica · {kind} {duration_s}s")[:120]
    angle = _safe_str(raw_preset.get("angle"), "")[:30]

    return {
        "name": name,
        "kind": kind,
        "angle": "" if kind == "music" else angle,
        "style": style,
        "shot_style": shot_style,
        "strategy": strategy_val,
        "duration_s": duration_s,
        "compatible_tiers": tiers,
        "text_overlay": _safe_str(raw_preset.get("text_overlay"), "")[:200],
        "text_overlay_style": text_overlay_style.model_dump(),
        "subtitle_style": subtitle_style.model_dump(),
        "cta_arrow_style": cta_arrow_style.model_dump(),
        "music_mood": _safe_str(raw_preset.get("music_mood"), "trendy_uplifting")[:60],
        "voice_id": None,
        "voice_tone": _safe_tone(raw_preset.get("voice_tone")),
        "title": _safe_str(raw_preset.get("title"), "")[:200],
        "voice_script": _safe_str(raw_preset.get("voice_script"), "")[:3000],
        "hooks_alternatives": [
            str(h)[:200] for h in (raw_preset.get("hooks_alternatives") or [])
        ][:8],
        "cta": _safe_str(raw_preset.get("cta"), "")[:200],
        "oratory_tips": _safe_str(raw_preset.get("oratory_tips"), "")[:500],
        "keywords": [
            str(k)[:60] for k in (raw_preset.get("keywords") or [])
        ][:10],
        "seedance_prompt": _safe_str(raw_preset.get("seedance_prompt"), "")[:500],
        "veo3_prompt": _safe_str(raw_preset.get("veo3_prompt"), "")[:2500],
        "veo3_prompt_segments": veo3_segments,
        "veo3_photo_filenames": veo3_photos,
        "source": "viral_replica",
    }


def _hook_price_suggestion(product: Any) -> str:
    """Mismo helper que preset_generator: 30% off del precio real,
    redondeado a barrera psicológica. Si no hay precio → string vacío."""
    p = getattr(getattr(product, "tiktok_shop", None), "price_eur", None)
    if p is None or p <= 0:
        return ""
    real = float(p)
    target = real * 0.70
    if target < 5:
        s = max(2, int(target))
    elif target < 10:
        s = max(5, int(target))
    elif target < 50:
        s = max(10, (int(target) // 5) * 5)
    elif target < 200:
        s = (int(target) // 10) * 10
    else:
        s = (int(target) // 50) * 50
    return f"{s}€ (real: {real:.2f}€)"


def analyze_viral_video(
    video_path: str,
    *,
    target_kind: PresetKind,
    same_product: bool,
    gemini_model: str = "gemini-3.5-flash",
    temp_folder: str = "./temp_work",
    log_callback: LogCallback = _noop,
    product: Any = None,
) -> dict:
    """Analiza un vídeo viral y devuelve `{config, detected, video_preset,
    cost_breakdown}`.

    - `config`: preset LEGACY ShopPreset (formato viejo "configuraciones
      guardadas") — kept for backward compat.
    - `detected`: respuesta cruda de Gemini con la "receta" detectada.
    - `video_preset`: dict listo para crear un VideoPreset NUEVO en
      `product.video_presets[]` (replica completa: prompts Seedance/Veo3,
      fotos elegidas, overlays, subs, voz, etc.). Solo se genera si
      `product` se pasa y `target_kind` es `auto_video` o `veo3`.
    - `cost_breakdown`: `{gemini_usd, total_usd}` (Whisper local = $0).

    Args:
        product: objeto Product (opcional). Si se pasa, Gemini recibe
            contexto del producto (nombre, marca, categoría, precio,
            fotos source) y genera un VideoPreset completo adaptado.
            Sin product, solo se hace análisis básico (config legacy).
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

    # Contexto del producto destino — el video_preset generado adapta la
    # fórmula viral al producto del user (no copia el original).
    product_block = ""
    available_photo_filenames: list[str] = []
    if product is not None:
        try:
            product_name = getattr(product, "name", "") or ""
            product_brand = getattr(product, "brand", "") or ""
            product_category = getattr(product, "category", "") or ""
            tiktok_meta = getattr(product, "tiktok_shop", None)
            price = getattr(tiktok_meta, "price_eur", None) if tiktok_meta else None
            price_str = f"{float(price):.2f}€" if price else "(sin definir)"
            hook_price = _hook_price_suggestion(product)
            audiences = getattr(product, "target_audience", []) or []
            features = getattr(product, "key_features", []) or []
            selling = getattr(product, "selling_points", []) or []

            # Source photos del producto — para que Gemini elija filenames
            # reales en `veo3_photo_filenames`. Fallback Win/Linux: si
            # local_path no existe (Redis compartido entre entornos),
            # reconstruimos desde slug + filename.
            from src.tiktok_shop.config import product_photos_source_folder
            source_photos = getattr(getattr(product, "photos", None), "source", []) or []
            for p in source_photos:
                if getattr(p, "deleted", False):
                    continue
                local = getattr(p, "local_path", None)
                resolved = None
                if local and os.path.exists(local):
                    resolved = local
                else:
                    candidate = os.path.join(
                        product_photos_source_folder(product.slug),
                        p.filename,
                    )
                    if os.path.exists(candidate):
                        resolved = candidate
                if resolved is None:
                    continue
                available_photo_filenames.append(p.filename)
                if len(available_photo_filenames) >= 6:
                    break

            # Bloque de idioma — reusamos el helper del preset_generator
            # para garantizar la misma instrucción de "Spoken language"
            # injection en los prompts Veo 3 / Seedance.
            from src.tiktok_shop.pipeline.preset_generator import _language_block
            lang_instr = _language_block(product)
            product_block = (
                f"\n\n=== USER'S PRODUCT CONTEXT (adapt the formula to this) ===\n"
                f"- Name: {product_name}\n"
                f"- Brand: {product_brand or '(no brand)'}\n"
                f"- Category: {product_category}\n"
                f"- Real price: {price_str}\n"
                f"- Hook price (for savings/comparison angles): {hook_price or '(N/A)'}\n"
                f"- Target audiences: {', '.join(audiences) or '(generic)'}\n"
                f"- Key features: {', '.join(features) or '(none defined)'}\n"
                f"- Selling points: {', '.join(selling) or '(none defined)'}\n"
                f"{lang_instr}\n"
                f"\nAvailable source photos for veo3_photo_filenames "
                f"(pick filenames EXACTLY from this list, max 3):\n"
                + ("\n".join(f"  - {fn}" for fn in available_photo_filenames)
                   if available_photo_filenames
                   else "  (no photos available — return [])")
            )
        except Exception as e:
            log_callback(f"⚠️ No pude leer contexto del producto ({e}). Sigo sin él.")

    user_msg = (
        f"Total duration: {duration_s:.1f} seconds\n"
        f"Same product as user's: {'yes' if same_product else 'no — competitor reference'}\n"
        f"Target preset kind: {target_kind}\n"
        f"Word-level transcript ({n_words} words): {transcript[:3000]}\n\n"
        f"Frames are attached, sampled at ~1 fps in chronological order."
        f"{product_block}"
    )

    log_callback(f"🤖 Llamando a Gemini '{gemini_model}' con {len(frame_paths)} frames…")
    try:
        gemini_raw = generate_json(
            system_prompt, user_msg,
            model=gemini_model,
            images=frame_paths,
            temperature=0.4,
        )
    except Exception as e:
        # Cleanup antes de propagar
        _cleanup(tmp_dir)
        raise RuntimeError(f"Gemini falló al analizar el vídeo: {e}")

    if not isinstance(gemini_raw, dict):
        log_callback(f"⚠️ Gemini devolvió tipo inesperado ({type(gemini_raw).__name__}), usando dict vacío.")
        gemini_raw = {}

    # El nuevo schema devuelve {detected: {...}, video_preset: {...}}.
    # Backward compat: si Gemini devuelve los campos planos (schema viejo),
    # los tomamos como `detected`.
    detected_raw = gemini_raw.get("detected") if "detected" in gemini_raw else gemini_raw
    if not isinstance(detected_raw, dict):
        detected_raw = {}
    raw_video_preset = gemini_raw.get("video_preset") if isinstance(gemini_raw.get("video_preset"), dict) else None

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

    # 5. Mapping al config del modo objetivo (legacy ShopPreset format)
    if target_kind == "auto_video":
        config = _map_to_auto_video(detected_raw)
    elif target_kind == "veo3":
        config = _map_to_veo3(detected_raw)
    else:
        config = _map_to_nano_banana(detected_raw)

    # 5b. Mapping al NUEVO VideoPreset si tenemos product context.
    # Solo aplica a auto_video / veo3 (nano_banana es solo prompt de fotos,
    # no encaja en el modelo VideoPreset).
    video_preset_dict: dict | None = None
    if (
        product is not None
        and target_kind in ("auto_video", "veo3")
        and raw_video_preset is not None
    ):
        try:
            video_preset_dict = _map_to_video_preset(
                raw_video_preset,
                product=product,
                available_photos=available_photo_filenames,
            )
            log_callback(
                f"🎯 VideoPreset construido: {video_preset_dict['name']} "
                f"({video_preset_dict['kind']}, {video_preset_dict['duration_s']}s, "
                f"{len(video_preset_dict['veo3_photo_filenames'])} fotos)"
            )
        except Exception as e:
            log_callback(f"⚠️ Fallo construyendo VideoPreset: {e}")
            video_preset_dict = None

    # 6. Cleanup
    _cleanup(tmp_dir)

    return {
        "config": config,
        "detected": {
            **detected_raw,
            "duration_seconds": duration_s,
            "n_words": n_words,
        },
        "video_preset": video_preset_dict,
        "cost_breakdown": {
            "gemini_usd": round(cost_usd, 4),
            "whisper_usd": 0.0,
            "total_usd": round(cost_usd, 4),
            "gemini_model": gemini_model,
            "input_tokens_est": est_input_tokens,
            "output_tokens_est": est_output_tokens,
        },
    }


_REPLICA_KEYS = (
    "concept", "format", "emotion", "angle", "image_prompt",
    "animate_prompt", "spoken_line", "hook_text", "cta_text", "caption",
)


def _normalize_segment(s: Any, idx: int) -> dict:
    """Sanea un segmento de la réplica.

    `transition`: "cut" = plano/ángulo nuevo (foto Nano Banana propia) ·
    "continue" = mismo plano que se alarga (extiende desde el último fotograma,
    sin foto). `is_extend` se deriva de `transition` (continue → True)."""
    if not isinstance(s, dict):
        s = {}
    transition = _safe_str(s.get("transition"), "").lower()
    if transition == "continue":
        is_extend = True
    elif transition == "cut":
        is_extend = False
    else:
        # Sin transition explícita: compat con is_extend; el 1º siempre es corte.
        is_extend = bool(s.get("is_extend", False)) and idx > 0
        transition = "continue" if is_extend else "cut"
    return {
        "transition": transition,
        "is_extend": is_extend,
        "label": _safe_str(s.get("label"), f"Plano {idx + 1}"),
        # Corte → foto Nano Banana propia; continuación → extiende (sin foto).
        "image_prompt": "" if is_extend else _safe_str(s.get("image_prompt"), ""),
        "animate_prompt": _safe_str(s.get("animate_prompt"), ""),
        "spoken_line": _safe_str(s.get("spoken_line"), ""),
    }


def _normalize_replica(v: Any, idx: int) -> dict:
    """Sanea una versión de réplica al schema 2-step de problem_videos.
    Soporta `segments` (modo réplica larga encadenada)."""
    if not isinstance(v, dict):
        v = {}
    out = {k: _safe_str(v.get(k), "") for k in _REPLICA_KEYS}
    out["veo3_prompt"] = ""  # nunca texto→vídeo
    if not out["concept"]:
        out["concept"] = f"Réplica v{idx + 1}"
    raw_segs = v.get("segments")
    segs = (
        [_normalize_segment(s, i) for i, s in enumerate(raw_segs)]
        if isinstance(raw_segs, list) else []
    )
    # Segmento 1 SIEMPRE es un corte con foto (aunque Gemini lo marque mal).
    if segs:
        segs[0]["is_extend"] = False
        segs[0]["transition"] = "cut"
    out["segments"] = segs
    return out


def replicate_viral_2step(
    video_path: str,
    *,
    product: Any = None,
    reference_photo_path: str | None = None,
    same_product: bool = True,
    n: int = 1,
    language: str = "es",
    gemini_model: str = "gemini-2.5-flash",
    temp_folder: str = "./temp_work",
    log_callback: LogCallback = _noop,
) -> dict:
    """Ingeniería inversa de un vídeo VIRAL → réplica 2-step (foto→vídeo) para
    el producto del operador.

    Reutiliza el pipeline del analyzer (ffprobe + Whisper + frames) pero llama
    al prompt `viral_replica_director.md` y devuelve el schema de problem_videos
    (image_prompt + animate_prompt + textos) + un bloque `why_viral`.

    - `reference_photo_path`: foto del producto NUEVO al que se traslada la
      fórmula. Si se pasa, se adjunta como ÚLTIMA imagen y el image_prompt se
      ancla a ella. Si es None, se usa la primera foto source del producto (o,
      si no hay, se replica el producto tal como sale en el viral).
    """
    log_callback(f"📐 Probing duración de '{video_path}'…")
    duration_s = _probe_duration_seconds(video_path)
    log_callback(f"⏱️ Duración: {duration_s:.1f}s")

    # Modo decidido por GEMINI (ve los planos): segmentos si el viral tiene
    # varios PLANOS/cortes (aunque sea corto) O dura más que un clip (~8s);
    # versiones (A/B) solo si es un plano continuo corto. Veo 3.1 i2v ≈ 8s y
    # UN plano por clip → meter varios ángulos en un clip rompe la consistencia.
    # Aquí solo calculamos el CAP de segmentos; el modo real sale de la respuesta.
    import math
    _CLIP_S = 8.0
    max_segments = min(5, max(2, math.ceil(duration_s / _CLIP_S) + 1))
    log_callback(
        f"🎬 Duración {duration_s:.1f}s → Gemini decide modo "
        f"(segmentos por planos/cortes o duración, máx {max_segments})."
    )

    ts = int(time.time())
    tmp_dir = Path(temp_folder) / f"replica_{ts}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 1. Whisper
    audio_path = str(tmp_dir / "audio.wav")
    log_callback("🎙️ Extrayendo audio…")
    transcript = ""
    hook_text = ""
    n_words = 0
    try:
        _extract_audio(video_path, audio_path)
        log_callback("🎙️ Transcribiendo (Whisper small, local)…")
        from src.subtitles import transcribe
        words = transcribe(audio_path, model_size="small", language=None)
        n_words = len(words)
        transcript = " ".join(w.get("word", "") for w in words).strip()
        hook_text = " ".join(
            w["word"] for w in words
            if isinstance(w.get("start"), (int, float)) and float(w["start"]) < 3.0
        ).strip() or transcript[:80]
        log_callback(f"📝 {n_words} palabras detectadas.")
    except Exception as e:
        log_callback(f"⚠️ Sin audio/transcripción ({e}). Sigo solo con frames.")

    # 2. Frames del viral (orden cronológico)
    log_callback("🎞️ Muestreando frames (1/s, max 30)…")
    frames_dir = tmp_dir / "frames"
    frame_paths = _sample_frames(video_path, frames_dir, max_frames=30)
    if not frame_paths:
        _cleanup(tmp_dir)
        raise RuntimeError("No se pudieron extraer frames del vídeo.")
    log_callback(f"🖼️ {len(frame_paths)} frames listos.")

    # 3. Foto de referencia del producto (ancla) → última imagen
    ref_path = reference_photo_path
    has_reference = False
    if ref_path and os.path.exists(ref_path):
        has_reference = True
    else:
        ref_path = None
        try:
            from src.tiktok_shop.config import product_photos_source_folder
            source_photos = getattr(getattr(product, "photos", None), "source", []) or []
            for p in source_photos:
                if getattr(p, "deleted", False):
                    continue
                local = getattr(p, "local_path", None)
                if local and os.path.exists(local):
                    ref_path = local
                    break
                cand = os.path.join(product_photos_source_folder(product.slug), p.filename)
                if os.path.exists(cand):
                    ref_path = cand
                    break
            if ref_path:
                has_reference = True
        except Exception:
            ref_path = None

    images = list(frame_paths)
    if ref_path:
        images.append(ref_path)

    # 4. Contexto del producto
    product_name = getattr(product, "name", "") or ""
    product_brand = getattr(product, "brand", "") or ""
    product_category = getattr(product, "category", "") or ""
    tiktok_meta = getattr(product, "tiktok_shop", None)
    price = getattr(tiktok_meta, "price_eur", None) if tiktok_meta else None
    price_str = f"{float(price):.2f}€" if price else "(sin definir)"
    selling = getattr(product, "selling_points", []) or []
    features = getattr(product, "key_features", []) or []

    lang_label = "español de España (es_ES)" if language.startswith("es") else language
    if has_reference:
        same_note = (
            "This reference IS the same product shown in the viral."
            if same_product else
            "This is a DIFFERENT product than the one in the viral — transfer the "
            "winning formula/structure to THIS product (adapt hooks/claims to it)."
        )
        ref_note = (
            f"The LAST attached image (image #{len(images)}) is the PRODUCT REFERENCE "
            f"— reproduce THAT exact product in every image_prompt. {same_note}"
        )
    else:
        ref_note = (
            "No product reference photo attached — replicate the SAME product as it "
            "appears in the viral frames."
        )

    # 5. Gemini
    from src.tiktok_shop.api.gemini import generate_json, is_configured, load_system_prompt
    if not is_configured():
        _cleanup(tmp_dir)
        raise RuntimeError(
            "Gemini no configurado — define GOOGLE_GEMINI_KEY_FREE o "
            "GOOGLE_GEMINI_KEY_PAID en .env para usar replicar viral."
        )
    system_prompt = load_system_prompt("viral_replica_director.md")
    fits_one_clip = duration_s <= 10.0
    mode_line = (
        f"DECIDE MODE yourself and set `mode` in the output. Veo 3.1 makes ONE clip "
        f"of up to ~10s, and it CAN do hard cuts to new shots/angles INSIDE a single "
        f"clip.\n"
        f"- The viral is {duration_s:.1f}s → it {'FITS in one Veo generation' if fits_one_clip else 'is TOO LONG for one Veo generation'}.\n"
        f"- If it FITS (<=~10s): use MODE: versions and generate {n} A/B version(s), "
        f"each ONE clip, `segments: []`. If the original has camera-angle changes/cuts, "
        f"reproduce them as HARD CUTS described INSIDE the single animate_prompt "
        f"(e.g. 'front shot ... then a clean hard cut to a side-profile shot of the "
        f"SAME person and outfit ...') — NOT a continuous rotation or morph.\n"
        f"- Only if it is TOO LONG (> ~10s): use MODE: segments (max {max_segments} "
        f"segments), one segment per shot with transition=\"cut\" (its own image_prompt, "
        f"same person across shots) or transition=\"continue\" to extend a long shot. "
        f"Replicate the SAME cuts as the original.\n"
    )
    user_msg = (
        f"OUTPUT LANGUAGE: {lang_label}\n"
        f"{mode_line}"
        f"Viral video total duration: {duration_s:.1f} seconds.\n"
        f"Viral audio transcript ({n_words} words): {transcript[:3000] or '(no speech / music only)'}\n"
        f"The first {len(frame_paths)} attached images are the viral video frames "
        f"in chronological order (~1 fps). {ref_note}\n\n"
        f"=== USER'S PRODUCT (the replica must feature THIS product) ===\n"
        f"- Name: {product_name}\n"
        f"- Brand: {product_brand or '(no brand)'}\n"
        f"- Category: {product_category}\n"
        f"- Real price: {price_str}\n"
        f"- Key features: {', '.join(features) or '(none)'}\n"
        f"- Selling points: {', '.join(selling) or '(none)'}\n"
    )

    log_callback(f"🤖 Gemini '{gemini_model}' con {len(images)} imágenes…")
    try:
        raw = generate_json(
            system_prompt, user_msg,
            model=gemini_model, images=images, temperature=0.5,
        )
    except Exception as e:
        _cleanup(tmp_dir)
        raise RuntimeError(f"Gemini falló al replicar el vídeo: {e}")

    if not isinstance(raw, dict):
        raw = {}
    why_viral = raw.get("why_viral") if isinstance(raw.get("why_viral"), dict) else {}
    videos_raw = raw.get("videos") if isinstance(raw.get("videos"), list) else []
    # El modo REAL lo decidió Gemini: por el campo `mode` o porque devolvió
    # segmentos en el primer objeto.
    returned_mode = _safe_str(raw.get("mode"), "").lower()
    has_segments = bool(
        videos_raw and isinstance(videos_raw[0], dict) and videos_raw[0].get("segments")
    )
    segment_mode = returned_mode == "segments" or has_segments
    limit = 1 if segment_mode else max(1, n)
    videos = [_normalize_replica(v, i) for i, v in enumerate(videos_raw[:limit])]
    if not videos:
        _cleanup(tmp_dir)
        raise RuntimeError("Gemini no devolvió ninguna versión de réplica.")
    # Cap de segmentos por seguridad.
    if segment_mode and videos[0].get("segments"):
        videos[0]["segments"] = videos[0]["segments"][:max_segments]
    n_segments = len(videos[0].get("segments", [])) if segment_mode else 0
    log_callback(
        f"🎬 Modo {'SEGMENTOS' if segment_mode else 'VERSIONES'}"
        + (f" · {n_segments} planos" if segment_mode else f" · {len(videos)} clip(s)")
    )

    # 6. Coste (estimación local, mismo criterio que analyze_viral_video)
    from src.cost_tracking import _resolve_gemini_rates
    est_input_tokens = len(images) * 258 + len(system_prompt) // 4 + len(user_msg) // 4
    est_output_tokens = 400 * len(videos) + 300
    in_rate, out_rate = _resolve_gemini_rates(gemini_model)
    cost_usd = (
        (est_input_tokens / 1_000_000) * in_rate
        + (est_output_tokens / 1_000_000) * out_rate
    )
    try:
        from src.cost_tracking import record_gemini
        record_gemini(
            input_tokens=est_input_tokens, output_tokens=est_output_tokens,
            model=gemini_model, detail="viral_replica",
        )
    except Exception:
        pass

    _cleanup(tmp_dir)
    log_callback(f"✅ {len(videos)} versión(es) de réplica listas.")
    return {
        "ok": True,
        "why_viral": why_viral,
        "videos": videos,
        "mode": "segments" if segment_mode else "versions",
        "n_segments": n_segments,
        "language": language,
        "duration_s": round(duration_s, 1),
        "used_reference_photo": has_reference,
        "cost_breakdown": {
            "gemini_usd": round(cost_usd, 4),
            "whisper_usd": 0.0,
            "total_usd": round(cost_usd, 4),
            "gemini_model": gemini_model,
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
