"""Genera el guion narrado en 1ª persona analizando el vídeo con Gemini."""

from __future__ import annotations

import re
from pathlib import Path

from .gemini_video import analyze_video


# Caracteres por segundo de narración inglesa (ritmo TikTok normal).
# Empírico — voces MiniMax EN a velocidad 1.0 hacen ~14-16 chars/s.
CHARS_PER_SECOND_EN = 15.5

# Margen de silencio al final del vídeo (segundos) — el guion debe acabar
# antes para no comer los últimos frames.
TAIL_SILENCE_SECONDS = 4.0

# Tolerancia del char count vs target (Flash drifta, Pro suele cumplir).
# Si el output cae fuera de este rango, se intenta un reshape text-only.
TARGET_TOLERANCE_PCT = 0.15


def _load_prompt_template() -> str:
    path = Path(__file__).parent / "prompts" / "pov_script.md"
    return path.read_text(encoding="utf-8")


def estimate_target_chars(video_duration_s: float) -> tuple[int, float]:
    """Devuelve `(target_chars, target_narration_seconds)`.

    Se descuentan `TAIL_SILENCE_SECONDS` del final del vídeo y se
    multiplica por `CHARS_PER_SECOND_EN`. Mínimo 200 chars.
    """
    narration_s = max(8.0, video_duration_s - TAIL_SILENCE_SECONDS)
    chars = max(200, int(narration_s * CHARS_PER_SECOND_EN))
    return chars, narration_s


def build_system_prompt(video_duration_s: float) -> str:
    """Construye el system prompt completo con todos los placeholders del
    template sustituidos (calibrados a la duración real).

    Placeholders: TARGET_CHARS, TARGET_SECONDS, TARGET_CHARS_LO/HI,
    TARGET_SENTENCES.
    """
    target_chars, target_seconds = estimate_target_chars(video_duration_s)
    lo = int(target_chars * (1 - TARGET_TOLERANCE_PCT / 3))   # ±5% para el hint
    hi = int(target_chars * (1 + TARGET_TOLERANCE_PCT / 3))
    # ~3 frases medias EN por 10s
    target_sentences = max(3, int(target_seconds * 0.3))
    template = _load_prompt_template()
    return (
        template.replace("{{TARGET_CHARS_LO}}", str(lo))
        .replace("{{TARGET_CHARS_HI}}", str(hi))
        .replace("{{TARGET_CHARS}}", str(target_chars))
        .replace("{{TARGET_SECONDS}}", f"{target_seconds:.0f}")
        .replace("{{TARGET_SENTENCES}}", str(target_sentences))
    )


def _clean_output(raw: str) -> str:
    """Quita fences, comillas externas, espacios. Idempotente."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith(("text", "txt", "plaintext")):
            text = text.split("\n", 1)[1] if "\n" in text else ""
    return text.strip().strip('"').strip("'").strip()


def _truncate_to_sentence(text: str, max_chars: int) -> str:
    """Trunca a `max_chars` cortando en el último final de frase (. ! ?)
    anterior al límite. Si no hay puntuación, corta en el último espacio."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Buscar el último . ! ? del rango
    matches = list(re.finditer(r"[.!?](?:\s|$)", cut))
    if matches:
        end = matches[-1].end()
        return cut[:end].strip()
    # Fallback: último espacio
    last_space = cut.rfind(" ")
    if last_space > 0:
        return cut[:last_space].rstrip(",;: ").rstrip() + "."
    return cut.rstrip() + "."


def _reshape_to_length(
    text: str,
    target_chars: int,
    *,
    model: str,
    log_callback=None,
) -> str:
    """Pide a Gemini (text-only, sin re-subir vídeo) que reescriba el
    texto a EXACTAMENTE `target_chars` caracteres preservando el contenido
    técnico y el orden cronológico. Coste: ~$0.0001 con Flash.
    """
    from .gemini_video import _get_gemini_keys, _is_quota_error
    import google.generativeai as genai
    import time

    diff = len(text) - target_chars
    action = "shorten" if diff > 0 else "expand"
    system = (
        "You rewrite construction narration scripts to fit an EXACT target "
        "character count. Preserve technical vocabulary, first-person voice, "
        "and chronological order of the original. Return ONLY the rewritten "
        "narration, no commentary."
    )
    user = (
        f"Rewrite the following narration to EXACTLY {target_chars} characters "
        f"(spaces included; tolerance ±5%). Currently it has {len(text)} chars "
        f"— you must {action} it by {abs(diff)} characters.\n\n"
        f"Original:\n{text}\n\n"
        f"Output (target {target_chars} chars):"
    )

    keys = _get_gemini_keys()
    if not keys:
        raise EnvironmentError("Sin API key Gemini para reshape.")

    last_err = None
    for label, api_key in keys:
        try:
            genai.configure(api_key=api_key)
            model_obj = genai.GenerativeModel(
                model_name=model,
                system_instruction=system,
            )
            response = model_obj.generate_content(
                [user],
                generation_config={
                    "temperature": 0.4,
                    "response_mime_type": "text/plain",
                },
            )
            # Cost tracking
            try:
                from src import cost_tracking
                from .gemini_video import _rates_for
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    in_tok = int(getattr(usage, "prompt_token_count", 0) or 0)
                    out_tok = int(getattr(usage, "candidates_token_count", 0) or 0)
                    in_rate, out_rate = _rates_for(model)
                    cost = (in_tok / 1_000_000) * in_rate + (out_tok / 1_000_000) * out_rate
                    cost_tracking.record_custom(
                        kind="gemini_video",
                        units=in_tok + out_tok,
                        unit_label="tokens",
                        cost_usd=cost,
                        detail=f"{model} reshape {in_tok}+{out_tok}",
                    )
            except Exception:
                pass

            cleaned = _clean_output(response.text or "")
            if log_callback:
                log_callback(
                    f"✂️ Reshape ({label}): {len(text)} → {len(cleaned)} chars "
                    f"(target {target_chars})."
                )
            return cleaned
        except Exception as e:
            if _is_quota_error(e):
                last_err = e
                time.sleep(2)
                continue
            raise
    if last_err:
        raise last_err
    return text


def generate_script(
    video_path: str,
    *,
    video_duration_s: float,
    model: str = "gemini-2.5-pro",
    log_callback=None,
) -> str:
    """Pide a Gemini el guion narrado del vídeo (US English, 1ª persona).

    Pipeline de control de longitud (Flash drifta ~70% over en algunos casos):
      1. Llama con vídeo + prompt estricto.
      2. Si len está dentro de target ±15% → devuelve.
      3. Si fuera → llamada text-only (cost-effective ~$0.0001) pidiendo
         reshape a target exacto.
      4. Si sigue fuera → trunca a frontera de frase (hard cap).
    """
    target_chars, target_seconds = estimate_target_chars(video_duration_s)
    system_prompt = build_system_prompt(video_duration_s)
    user_prompt = (
        "Analyze the construction video and produce the first-person US "
        f"English narration described in your instructions. HARD target: "
        f"{target_chars} characters (±5%). Count before submitting. "
        f"Return ONLY the narration text."
    )
    raw = analyze_video(
        video_path,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        log_callback=log_callback,
    )
    text = _clean_output(raw)
    if not text:
        raise RuntimeError("Gemini devolvió un guion vacío.")

    # Validación de longitud — tolerancia ±15% del target.
    lo = int(target_chars * (1 - TARGET_TOLERANCE_PCT))
    hi = int(target_chars * (1 + TARGET_TOLERANCE_PCT))
    n = len(text)
    if lo <= n <= hi:
        if log_callback:
            log_callback(f"✅ Guion {n} chars (target {target_chars}, rango {lo}-{hi}).")
        return text

    # Fuera de rango → reshape text-only (no re-sube vídeo, casi $0).
    if log_callback:
        log_callback(
            f"⚠️ Guion fuera de rango: {n} chars (target {target_chars}, "
            f"rango {lo}-{hi}) — pidiendo reshape a Gemini…"
        )
    try:
        reshaped = _reshape_to_length(
            text, target_chars, model=model, log_callback=log_callback,
        )
        if reshaped and lo <= len(reshaped) <= hi:
            return reshaped
        # Reshape también drifta → seguir al hard cap
        text = reshaped or text
        if log_callback:
            log_callback(
                f"⚠️ Reshape también fuera de rango ({len(text)} chars) — truncando."
            )
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ Reshape falló ({e}) — truncando manualmente.")

    # Hard cap: si todavía es más largo que `hi`, truncar a frontera de frase
    if len(text) > hi:
        text = _truncate_to_sentence(text, hi)
        if log_callback:
            log_callback(f"✂️ Truncado a {len(text)} chars (frontera de frase).")
    # Si es demasiado corto, lo dejamos pasar — peor un silencio largo que
    # un vídeo que se corta. El usuario podrá regenerar manualmente.
    return text
