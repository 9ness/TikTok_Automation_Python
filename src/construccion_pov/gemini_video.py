"""Cliente Gemini con soporte de vídeo (Files API).

El módulo `src/tiktok_shop/api/gemini.py` solo soporta imágenes inline.
Aquí extendemos el patrón para subir vídeos vía `genai.upload_file()` con
polling de estado (ACTIVE) — necesario porque Gemini procesa el vídeo
asíncronamente antes de poder pasarlo a `generate_content`.

Reusa el patrón dual-key fallback (FREE → PAID → legacy) y el cost
tracking del proyecto. Tarifa Gemini 2.5 Pro (entrada / salida) se registra
con `record_custom` porque no hay helper específico todavía.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

# Tarifas Gemini 2.5 (precios públicos enero 2026; subir si cambian).
# Aproximación por tokens reportados en `usage_metadata`.
GEMINI_2_5_PRO_INPUT_PER_1M = 1.25
GEMINI_2_5_PRO_OUTPUT_PER_1M = 10.0
GEMINI_2_5_FLASH_INPUT_PER_1M = 0.075   # ~16× más barato que Pro
GEMINI_2_5_FLASH_OUTPUT_PER_1M = 0.30   # ~33× más barato que Pro


def _rates_for(model: str) -> tuple[float, float]:
    """Devuelve `(in_per_1m, out_per_1m)` para el modelo dado.

    Default → Flash (más barato). Cualquier id con "pro" usa tarifa Pro.
    """
    m = (model or "").lower()
    if "pro" in m:
        return GEMINI_2_5_PRO_INPUT_PER_1M, GEMINI_2_5_PRO_OUTPUT_PER_1M
    return GEMINI_2_5_FLASH_INPUT_PER_1M, GEMINI_2_5_FLASH_OUTPUT_PER_1M


def _get_gemini_keys() -> list[tuple[str, str]]:
    """Mismo orden que `tiktok_shop.api.gemini` — FREE → PAID → legacy."""
    out: list[tuple[str, str]] = []
    free = os.getenv("GOOGLE_GEMINI_KEY_FREE")
    paid = os.getenv("GOOGLE_GEMINI_KEY_PAID")
    if free:
        out.append(("free", free))
    if paid:
        out.append(("paid", paid))
    if not out:
        legacy = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GOOGLE_GEMINI_KEY")
        if legacy:
            out.append(("legacy", legacy))
    return out


def is_configured() -> bool:
    return bool(_get_gemini_keys())


def _is_quota_error(exc: Exception) -> bool:
    type_name = type(exc).__name__
    err_str = str(exc)
    return (
        "ResourceExhausted" in type_name
        or "429" in err_str
        or "quota" in err_str.lower()
    )


def _guess_video_mime(path: str) -> str:
    p = path.lower()
    if p.endswith(".mov"):
        return "video/quicktime"
    if p.endswith(".webm"):
        return "video/webm"
    if p.endswith(".mkv"):
        return "video/x-matroska"
    return "video/mp4"


def _call_with_key(
    api_key: str,
    *,
    video_path: str,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    log_callback=None,
) -> str:
    """UNA llamada a Gemini con UNA key: upload vídeo, poll, generate."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)

    mime = _guess_video_mime(video_path)
    if log_callback:
        log_callback(f"📤 Subiendo vídeo a Gemini ({Path(video_path).name})…")
    uploaded = genai.upload_file(path=video_path, mime_type=mime)

    # Poll hasta ACTIVE (o FAILED). Gemini procesa video unos segundos antes
    # de aceptarlo en generate_content; sin esperar, falla con "file is not
    # in active state".
    max_wait = 180
    waited = 0
    while uploaded.state.name == "PROCESSING" and waited < max_wait:
        time.sleep(2)
        waited += 2
        uploaded = genai.get_file(uploaded.name)
    if uploaded.state.name != "ACTIVE":
        raise RuntimeError(
            f"Gemini no procesó el vídeo ({uploaded.state.name}). "
            f"Verifica formato/duración."
        )
    if log_callback:
        log_callback("✅ Vídeo procesado por Gemini, generando guion…")

    model_obj = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_prompt,
    )
    response = model_obj.generate_content(
        [uploaded, user_prompt],
        generation_config={
            "temperature": temperature,
            "response_mime_type": "text/plain",
        },
    )

    # Cost tracking — usa los tokens reales del usage_metadata si están.
    try:
        from src import cost_tracking
        usage = getattr(response, "usage_metadata", None)
        if usage:
            in_tok = int(getattr(usage, "prompt_token_count", 0) or 0)
            out_tok = int(getattr(usage, "candidates_token_count", 0) or 0)
            in_rate, out_rate = _rates_for(model)
            cost = (
                (in_tok / 1_000_000) * in_rate
                + (out_tok / 1_000_000) * out_rate
            )
            cost_tracking.record_custom(
                kind="gemini_video",
                units=in_tok + out_tok,
                unit_label="tokens",
                cost_usd=cost,
                detail=f"{model} video {in_tok}+{out_tok}",
            )
    except Exception:
        pass

    # Cleanup del archivo subido (no acumular en Files API).
    try:
        genai.delete_file(uploaded.name)
    except Exception:
        pass

    text = (response.text or "").strip()
    return text


def analyze_video(
    video_path: str,
    *,
    system_prompt: str,
    user_prompt: str = "Analyze the construction video and produce the narration.",
    model: str = "gemini-2.5-pro",
    temperature: float = 0.7,
    max_retries_on_quota: int = 2,
    log_callback=None,
) -> str:
    """Llama a Gemini con un vídeo + prompt. Devuelve texto plano del guion.

    Sube el vídeo a la Files API de Gemini, espera ACTIVE, llama a
    generate_content con `[video, user_prompt]` y un system_instruction.
    Aplica fallback dual-key FREE → PAID → legacy.
    """
    keys = _get_gemini_keys()
    if not keys:
        raise EnvironmentError(
            "Sin API key Gemini. Define GOOGLE_GEMINI_KEY_FREE y/o "
            "GOOGLE_GEMINI_KEY_PAID en .env."
        )

    last_err: Exception | None = None
    for key_idx, (label, api_key) in enumerate(keys):
        is_last_key = key_idx == len(keys) - 1
        max_attempts = max_retries_on_quota if is_last_key else 1
        for attempt in range(max_attempts):
            try:
                if log_callback:
                    log_callback(f"🤖 Gemini key={label} model={model}…")
                return _call_with_key(
                    api_key,
                    video_path=video_path,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    model=model,
                    temperature=temperature,
                    log_callback=log_callback,
                )
            except Exception as e:
                if not _is_quota_error(e):
                    raise
                last_err = e
                if not is_last_key:
                    if log_callback:
                        log_callback(
                            f"⚠️ Quota Gemini en {label}, probando siguiente key…"
                        )
                    break
                if attempt < max_attempts - 1:
                    delay = 15 * (attempt + 1)
                    if log_callback:
                        log_callback(
                            f"⏳ Última key con quota, espero {delay}s…"
                        )
                    time.sleep(delay)
                else:
                    raise
    if last_err:
        raise last_err
    raise RuntimeError("Gemini video falló sin información de error.")
