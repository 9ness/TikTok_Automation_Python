"""Cliente Gemini multimodal para analyzer / strategist / directors.

Usa la library `google-generativeai` que ya está en requirements.txt.

## Selección de API key (dual-key fallback)

El módulo TikTok Shop tiene 2 API keys propias para evitar interferir con
Creator Reward (que usa `GOOGLE_GEMINI_KEY` legacy):

  1. `GOOGLE_GEMINI_KEY_FREE` — proyecto Cloud sin billing (free tier 20 req/día).
  2. `GOOGLE_GEMINI_KEY_PAID` — proyecto Cloud con billing y límite mensual.

Estrategia de uso:
  - Intenta primero con FREE.
  - Si la llamada falla con `429 RESOURCE_EXHAUSTED` (cuota free agotada),
    cambia a PAID **inmediatamente** y reintenta UNA vez.
  - Si solo una de las dos está definida, usa esa sin fallback.
  - Si ninguna está definida, cae al legacy `GOOGLE_AI_API_KEY` /
    `GOOGLE_GEMINI_KEY` para compatibilidad (NO recomendado para producción
    — Creator Reward también las puede usar).

En la última key disponible, si vuelve a fallar con 429, se aplica retry
exponencial con el `retry_delay` exacto que devuelve el servidor.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from src.tiktok_shop.utils.logging_setup import log_info, log_warning


DEFAULT_MODEL = "gemini-2.5-flash"

_LOGGER_NAME = "tiktok_shop.gemini"


# ---------------------------------------------------------------------------
# Resolución de keys
# ---------------------------------------------------------------------------
def _get_gemini_keys() -> list[tuple[str, str]]:
    """Devuelve `[(label, key), ...]` en orden de prioridad de uso.

    Orden:
      1. `GOOGLE_GEMINI_KEY_FREE` → label "free"
      2. `GOOGLE_GEMINI_KEY_PAID` → label "paid"
      3. (Compat) `GOOGLE_AI_API_KEY` o `GOOGLE_GEMINI_KEY` → label "legacy"
         — solo se usa si NINGUNA de las dos anteriores está definida.

    El operador puede definir solo `_FREE`, solo `_PAID`, o ambas. Si ambas
    están vacías, intenta legacy. Si todo vacío, lista vacía.
    """
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


# ---------------------------------------------------------------------------
# Llamada cruda a Gemini con UNA key
# ---------------------------------------------------------------------------
def _call_with_key(
    api_key: str,
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    expect_json: bool,
    images: list[str | bytes] | None,
    temperature: float,
) -> str:
    """Ejecuta UNA llamada a Gemini con la `api_key` indicada.

    NO maneja retries — el caller (`generate_text`) decide la estrategia
    de fallback entre keys + retry on quota dentro de la última key.
    """
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model_obj = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_prompt,
    )

    parts: list = [user_prompt]
    if images:
        for img in images:
            if isinstance(img, str):
                parts.append({"mime_type": _guess_mime(img), "data": Path(img).read_bytes()})
            elif isinstance(img, bytes):
                parts.append({"mime_type": "image/jpeg", "data": img})

    response = model_obj.generate_content(
        parts,
        generation_config={
            "temperature": temperature,
            "response_mime_type": "application/json" if expect_json else "text/plain",
        },
    )
    text = (response.text or "").strip()
    if expect_json:
        text = _strip_json_fences(text)

    # Cost tracking — google-generativeai expone tokens en `usage_metadata`.
    # Si no hay job activo, `record_gemini` se ignora silenciosamente (eso
    # lo decide cost_tracking._add_line), así que llamar es seguro siempre.
    try:
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
            output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
            if input_tokens or output_tokens:
                from src.cost_tracking import record_gemini

                record_gemini(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=model,
                )
    except Exception as e:
        # Cost tracking nunca debe romper el call. Log y seguimos.
        log_warning(_LOGGER_NAME, "cost tracking falló (ignorando)", error=str(e))

    return text


def _is_quota_error(exc: Exception) -> bool:
    """Heurística para detectar 429 / ResourceExhausted / quota agotada."""
    type_name = type(exc).__name__
    err_str = str(exc)
    return (
        "ResourceExhausted" in type_name
        or "429" in err_str
        or "quota" in err_str.lower()
    )


# ---------------------------------------------------------------------------
# API pública: generate_text con fallback dual-key
# ---------------------------------------------------------------------------
def generate_text(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    expect_json: bool = False,
    images: list[str | bytes] | None = None,
    temperature: float = 0.8,
    max_retries_on_quota: int = 3,
) -> str:
    """Llama a Gemini con fallback automático entre keys (free → paid → legacy).

    Comportamiento:
      - Para cada key disponible (en orden), intenta UNA vez.
      - Si esa key falla con 429 y queda otra key, **switch inmediato** sin
        delay (la siguiente key tiene quota independiente).
      - Si la última key falla con 429, se aplican `max_retries_on_quota`
        reintentos respetando el `retry_delay` que devuelve el servidor.
      - Errores no-quota (auth, mal request, etc.) se propagan inmediatamente.
    """
    keys = _get_gemini_keys()
    if not keys:
        raise EnvironmentError(
            "Sin API key Gemini definida. Define `GOOGLE_GEMINI_KEY_FREE` y/o "
            "`GOOGLE_GEMINI_KEY_PAID` en .env (o el legacy `GOOGLE_GEMINI_KEY`)."
        )

    last_quota_err: Exception | None = None

    # Log inicial: qué modelo y qué keys vamos a probar (en orden).
    # Imprescindible para diagnosticar "qué modelo está corriendo realmente"
    # cuando hay caché de bytecode entre reinicios de Streamlit.
    log_info(_LOGGER_NAME, "Gemini call",
             model=model, keys_available=[lbl for lbl, _ in keys])

    for key_idx, (label, api_key) in enumerate(keys):
        is_last_key = key_idx == len(keys) - 1
        # Solo la última key reintenta on 429 con delay; el resto saltan
        # inmediatamente a la siguiente key (que tiene quota independiente).
        max_attempts = max_retries_on_quota if is_last_key else 1

        for attempt in range(max_attempts):
            try:
                result = _call_with_key(
                    api_key,
                    system_prompt=system_prompt, user_prompt=user_prompt,
                    model=model, expect_json=expect_json,
                    images=images, temperature=temperature,
                )
                # Loguea SIEMPRE qué key acabó devolviendo el resultado.
                # En éxitos sin fallback, este log permite verificar que se
                # está usando la key esperada (FREE en primera prioridad).
                log_info(_LOGGER_NAME, "Gemini OK",
                         key=label, model=model, attempt=attempt + 1)
                return result

            except Exception as e:
                if not _is_quota_error(e):
                    # Error no-quota → propagar inmediatamente sin probar otras keys
                    raise
                last_quota_err = e

                # Si NO es la última key → switch inmediato (siguiente key)
                if not is_last_key:
                    log_warning(_LOGGER_NAME,
                                "Quota agotada, cambiando a siguiente key",
                                key_used=label, next_key=keys[key_idx + 1][0])
                    break  # break del inner loop → for key

                # Última key con 429: si quedan attempts, esperar y reintentar
                if attempt < max_attempts - 1:
                    delay_s = _extract_retry_delay(str(e)) or (15 * (attempt + 1))
                    log_warning(_LOGGER_NAME,
                                "Quota última key, esperando antes de reintentar",
                                key=label, attempt=attempt + 1,
                                max_attempts=max_attempts, delay_s=delay_s)
                    time.sleep(delay_s + 1)
                else:
                    # Última key, agotó retries → propagar
                    raise

    # No debería alcanzarse — los caminos arriba ya re-lanzan o devuelven —
    # pero por defensiva propagamos el último error de quota visto.
    if last_quota_err is not None:
        raise last_quota_err
    raise RuntimeError("Gemini falló sin información de error (estado inesperado).")


def _strip_json_fences(text: str) -> str:
    """Algunos modelos devuelven el JSON envuelto en ```json...```. Lo quitamos."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_retry_delay(err_str: str) -> int | None:
    """Saca `seconds: N` del bloque retry_delay del error gRPC."""
    m = re.search(r"retry_delay\s*\{[^}]*seconds:\s*(\d+)", err_str)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    m = re.search(r"retry in (\d+)", err_str)
    return int(m.group(1)) if m else None


def generate_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    images: list[str | bytes] | None = None,
    temperature: float = 0.7,
) -> Any:
    """Igual que `generate_text` pero parsea JSON y lo devuelve. Lanza
    `ValueError` si el modelo devuelve algo no parseable."""
    raw = generate_text(
        system_prompt, user_prompt,
        model=model, expect_json=True, images=images, temperature=temperature,
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Gemini devolvió JSON inválido: {e}\nRespuesta: {raw[:500]}")


def _guess_mime(path: str) -> str:
    p = path.lower()
    if p.endswith(".png"):
        return "image/png"
    if p.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if p.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def load_system_prompt(filename: str) -> str:
    """Carga un .md de `src/tiktok_shop/prompts/` y devuelve su contenido."""
    base = Path(__file__).resolve().parent.parent / "prompts"
    path = base / filename
    if not path.exists():
        raise FileNotFoundError(f"System prompt no encontrado: {path}")
    return path.read_text(encoding="utf-8")
