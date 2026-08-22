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
  - La legacy `GOOGLE_AI_API_KEY` / `GOOGLE_GEMINI_KEY` queda SIEMPRE la
    última de la cola (la comparte Creator Reward): es el paracaídas para
    cuando el proyecto de pago se pasa del tope mensual y el free ya gastó su
    cuota, que si no deja el módulo entero sin IA sin decir nada.

En la última key disponible, si vuelve a fallar con 429, se aplica retry
exponencial con el `retry_delay` exacto que devuelve el servidor.
"""

from __future__ import annotations

import base64
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
      3. `GOOGLE_AI_API_KEY` o `GOOGLE_GEMINI_KEY` → label "legacy", siempre
         la última: es la de Creator Reward y solo se usa si las otras dos
         están agotadas (o no existen).

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
    # La legacy va SIEMPRE al final de la cola, no solo cuando no hay otras: el
    # día que el proyecto de pago se pasó del tope mensual y el free agotó su
    # cuota, todo lo que usa Gemini (textos, filtro, mensajes, emparejado de
    # fotos) dejó de funcionar en silencio teniendo una key buena en el .env.
    legacy = os.getenv("GOOGLE_AI_API_KEY") or os.getenv("GOOGLE_GEMINI_KEY")
    if legacy and legacy not in {k for _, k in out}:
        out.append(("legacy", legacy))
    return out


def is_configured() -> bool:
    return bool(_get_gemini_keys())


# ---------------------------------------------------------------------------
# Llamada cruda a Gemini con UNA key
# ---------------------------------------------------------------------------
def _call_rest_grounded(
    api_key: str,
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
) -> str:
    """Llama Gemini via REST directo con google_search grounding habilitado.

    El SDK legacy `google.generativeai` NO soporta el tool `google_search`
    para modelos Gemini 2.x (solo `google_search_retrieval` para 1.5 que
    ya no existe). Como fallback, llamamos REST con el formato 2.x.

    Endpoint:
      POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}
    Body:
      {
        "contents": [{"role":"user", "parts":[{"text": ...}]}],
        "systemInstruction": {"parts":[{"text": ...}]},
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.4}
      }
    """
    import requests
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": user_prompt}]}
        ],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": temperature,
            # Sin response_mime_type: tools + JSON no son combinables.
        },
    }
    r = requests.post(url, json=payload, timeout=180)
    if r.status_code == 429:
        # Replica el error format del SDK para que _is_quota_error lo detecte
        raise RuntimeError(
            f"429 RESOURCE_EXHAUSTED: {r.text[:300]}"
        )
    if r.status_code >= 400:
        raise RuntimeError(
            f"Gemini REST {r.status_code}: {r.text[:500]}"
        )
    data = r.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))

    # Cost tracking via usageMetadata
    try:
        usage = data.get("usageMetadata") or {}
        input_tokens = int(usage.get("promptTokenCount") or 0)
        output_tokens = int(usage.get("candidatesTokenCount") or 0)
        if input_tokens or output_tokens:
            from src.cost_tracking import record_gemini
            record_gemini(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
            )
    except Exception as e:
        log_warning(_LOGGER_NAME, "cost tracking REST falló", error=str(e))

    return text.strip()


def _call_with_key(
    api_key: str,
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    expect_json: bool,
    images: list[str | bytes] | None,
    temperature: float,
    enable_web_search: bool = False,
    videos: list[str] | None = None,
    audios: list[str] | None = None,
    max_output_tokens: int = 8192,
) -> str:
    """Ejecuta UNA llamada a Gemini con la `api_key` indicada.

    NO maneja retries — el caller (`generate_text`) decide la estrategia
    de fallback entre keys + retry on quota dentro de la última key.

    Args:
        enable_web_search: si True, añade Google Search grounding tool —
            el modelo busca en internet y cita fuentes. Incompatible con
            `expect_json=True` (limitación de Gemini API).
        videos: lista de paths a archivos .mp4 para análisis visual.
        audios: lista de paths a audio (.wav/.mp3) para ESCUCHARLO. Se usa
            para saber si quien habla en un clip es hombre o mujer: el tono
            medido con numpy resuelve la mayoría, pero entre 165 y 180 Hz hay
            solapamiento y ahí hace falta que alguien escuche de verdad.
            Gemini 2.5 Pro acepta hasta 20 vídeos por request (cada uno
            counts como ~258 tokens/seg de duración).
    """
    # Si habilitamos Google Search grounding, NO podemos usar la library
    # legacy `google.generativeai` (no soporta el tool google_search para
    # Gemini 2.x; el SDK nuevo es `google-genai`). Como wrapper, llamamos
    # REST directo con el formato correcto. El cost tracking se hace
    # dentro del helper.
    if enable_web_search:
        return _call_rest_grounded(
            api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
        )

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    tools = None

    model_obj = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_prompt,
        tools=tools,
    )
    _ = tools  # tools queda en None al no haber web_search; el modelo se inicia sin tools

    parts: list = [user_prompt]
    if images:
        for img in images:
            if isinstance(img, str):
                parts.append({"mime_type": _guess_mime(img), "data": Path(img).read_bytes()})
            elif isinstance(img, bytes):
                parts.append({"mime_type": "image/jpeg", "data": img})
    if videos:
        for vid in videos:
            parts.append({"mime_type": "video/mp4", "data": Path(vid).read_bytes()})
    if audios:
        for aud in audios:
            mime = "audio/mpeg" if str(aud).lower().endswith(".mp3") else "audio/wav"
            parts.append({"mime_type": mime, "data": Path(aud).read_bytes()})

    response = model_obj.generate_content(
        parts,
        generation_config={
            "temperature": temperature,
            "response_mime_type": "application/json" if expect_json else "text/plain",
            # Sin esto, gemini-2.5-flash trunca el output a ~8K tokens por
            # defecto → respuestas JSON grandes (lotes de presets) salen
            # cortadas y json.loads peta. Es un CAP, no un objetivo: solo
            # se factura el output real.
            "max_output_tokens": max_output_tokens,
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
    videos: list[str] | None = None,
    audios: list[str] | None = None,
    enable_web_search: bool = False,
    temperature: float = 0.8,
    max_retries_on_quota: int = 3,
    max_output_tokens: int = 8192,
) -> str:
    """Gemini con fallback a OpenAI cuando Gemini se queda sin cuota.

    Intenta Gemini (free → paid → legacy). Si TODAS las keys de Gemini están
    agotadas (429/cap) o no hay ninguna definida, y hay `OPENAI_API_KEY`, cae a
    OpenAI (gpt-4o-mini por defecto). Excepción: si hay `videos` (análisis
    multimodal de vídeo), NO se puede usar OpenAI → propaga el error de Gemini.
    """
    # Si hay fallback OpenAI disponible (texto/imágenes, no vídeo/web), no
    # tiene sentido esperar los reintentos lentos de Gemini (15s+30s) cuando
    # está sin cuota: probamos cada key UNA vez y caemos a OpenAI al instante.
    can_openai = (
        _openai_available() and not videos and not audios and not enable_web_search
    )
    retries = 1 if can_openai else max_retries_on_quota
    try:
        return _generate_text_gemini(
            system_prompt, user_prompt, model=model, expect_json=expect_json,
            images=images, videos=videos, audios=audios,
            enable_web_search=enable_web_search,
            temperature=temperature, max_retries_on_quota=retries,
            max_output_tokens=max_output_tokens,
        )
    except Exception as e:
        # Fallback OpenAI: solo para texto/imágenes (vídeo no soportado) y solo
        # si Gemini falló por cuota/sin-keys (no por errores de request).
        fallback_ok = (_is_quota_error(e) or isinstance(e, EnvironmentError))
        if (
            fallback_ok and not videos and not audios
            and not enable_web_search and _openai_available()
        ):
            log_warning(_LOGGER_NAME, "Gemini agotado → fallback a OpenAI", error=str(e)[:120])
            return _call_openai_fallback(
                system_prompt, user_prompt, expect_json=expect_json,
                images=images, temperature=temperature,
            )
        raise


def _openai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _call_openai_fallback(
    system_prompt: str, user_prompt: str, *,
    expect_json: bool, images: list[str | bytes] | None, temperature: float,
) -> str:
    """Respaldo con OpenAI Chat (gpt-4o-mini por defecto). Soporta texto +
    imágenes (no vídeo). Mismo contrato que generate_text."""
    import openai

    model = os.getenv("TIKTOK_SHOP_OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
    for img in images or []:
        try:
            if isinstance(img, str):
                data, mime = Path(img).read_bytes(), _guess_mime(img)
            elif isinstance(img, (bytes, bytearray)):
                data, mime = bytes(img), "image/jpeg"
            else:
                continue
            b64 = base64.b64encode(data).decode("ascii")
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"}})
        except Exception:
            continue
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        "temperature": temperature,
    }
    if expect_json:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    text = (resp.choices[0].message.content or "").strip()
    try:
        from src.cost_tracking import record_openai_chat
        u = getattr(resp, "usage", None)
        if u is not None:
            record_openai_chat(
                input_tokens=int(getattr(u, "prompt_tokens", 0) or 0),
                output_tokens=int(getattr(u, "completion_tokens", 0) or 0),
                model=model,
            )
    except Exception:
        pass
    log_info(_LOGGER_NAME, "OpenAI fallback OK", model=model)
    return _strip_json_fences(text) if expect_json else text


def _generate_text_gemini(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    expect_json: bool = False,
    images: list[str | bytes] | None = None,
    videos: list[str] | None = None,
    audios: list[str] | None = None,
    enable_web_search: bool = False,
    temperature: float = 0.8,
    max_retries_on_quota: int = 3,
    max_output_tokens: int = 8192,
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
                    images=images, videos=videos, audios=audios,
                    enable_web_search=enable_web_search,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
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
    audios: list[str] | None = None,
    temperature: float = 0.7,
    max_output_tokens: int = 32768,
) -> Any:
    """Igual que `generate_text` pero parsea JSON y lo devuelve. Lanza
    `ValueError` si el modelo devuelve algo no parseable.

    `max_output_tokens` default alto (32K) porque los callers de JSON suelen
    pedir lotes grandes (presets, variantes) que con el cap default (8K) se
    truncaban y reventaban el parseo."""
    raw = generate_text(
        system_prompt, user_prompt,
        model=model, expect_json=True, images=images, audios=audios,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
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
