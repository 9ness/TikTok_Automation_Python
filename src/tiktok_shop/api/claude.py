"""Cliente Claude para los textos y guiones de Tiktok Shop AI Pro.

Mismo contrato que `gemini.generate_text` / `gemini.generate_json`, más un
`tarea` que elige el modelo:

  - "texto" → Haiku 5.5, sin pensamiento: clasificar, mensajes, todo lo que
    sea solo texto. Si la llamada lleva FOTOS pasa sola a "lectura".
  - "lectura" → Sonnet 5.5, esfuerzo bajo: leer capturas y fotos (fichas,
    emparejado, mano, colores). Medido con una carpeta real (22/10/2026):
    Haiku se comía la marca y la gama del título («Gazebo emergente blanco»
    por «YITAHOME Gazebo»); Sonnet bajo las clavó en 9 de 10, ~0,08 $ la
    carpeta de diez.
  - "guion" → Sonnet 5.5, esfuerzo medio: lo que vende (guiones, escenas).

Gemini sigue siendo el respaldo, y lo único que hace con vídeo, audio o
búsqueda web (Claude no los recibe). Cualquier fallo de Claude (sin clave,
cuota, red, rechazo, JSON roto dos veces) cae a Gemini con el mismo prompt:
cambiar de proveedor nunca deja un trabajo sin hacer.

Interruptor: `AI_PRO_LLM=gemini` en el `.env` vuelve a Gemini sin tocar
código. La clave es `ANTHROPIC_API_KEY_AI_PRO` (una por parte de la app, para
ver su gasto aparte en la Console).
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from src.tiktok_shop.api import gemini
from src.tiktok_shop.utils.logging_setup import log_info, log_warning

# Los modelos van aquí y solo aquí: al salir otro se cambia esta línea.
MODELOS: dict[str, str] = {
    "texto": "claude-haiku-5-5",
    "lectura": "claude-sonnet-5-5",
    "guion": "claude-sonnet-5-5",
}
ESFUERZO: dict[str, str] = {"lectura": "low", "guion": "medium"}

Tarea = Literal["texto", "lectura", "guion"]

_LOGGER_NAME = "tiktok_shop.claude"
_ENV_CLAVE = "ANTHROPIC_API_KEY_AI_PRO"
# Claude rechaza imágenes de más de 5 MB, y por encima de ~2.500 px las
# reduce él igualmente: se mandan ya reducidas y en JPEG.
_LADO_MAX = 2000
_BYTES_MAX = 4_500_000
# El pensamiento de Sonnet cuenta para max_tokens: margen aparte del texto.
_MARGEN_PENSAR = 16000
_PIDE_JSON = (
    "\n\nResponde SOLO con un JSON válido: sin texto antes ni después y sin "
    "bloques ```."
)

_cliente = None


def activo() -> bool:
    return bool(os.getenv(_ENV_CLAVE)) and os.getenv("AI_PRO_LLM", "claude").lower() != "gemini"


def _client():
    global _cliente
    if _cliente is None:
        import anthropic

        _cliente = anthropic.Anthropic(api_key=os.getenv(_ENV_CLAVE), max_retries=2, timeout=600)
    return _cliente


def _imagen(img: str | bytes) -> dict | None:
    """Bloque de imagen para Claude; reducida si pasa de tamaño o de lado."""
    try:
        data = Path(img).read_bytes() if isinstance(img, str) else bytes(img)
    except OSError:
        return None
    mime = _mime(data)
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(data))
        if len(data) > _BYTES_MAX or max(im.size) > _LADO_MAX or mime is None:
            im = im.convert("RGB")
            im.thumbnail((_LADO_MAX, _LADO_MAX))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=88)
            data, mime = buf.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 — si PIL no la abre, se manda tal cual
        if mime is None:
            return None
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": mime,
                   "data": base64.standard_b64encode(data).decode("ascii")},
    }


def _mime(data: bytes) -> str | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def _llamar(system_prompt: str, user_prompt: str, *, tarea: Tarea, expect_json: bool,
            images: list[str | bytes] | None, max_output_tokens: int) -> str:
    contenido: list[dict] = [b for b in (_imagen(i) for i in images or []) if b]
    if tarea == "texto" and contenido:
        tarea = "lectura"
    modelo = MODELOS[tarea]
    # Algunos callers mandan todo en el system y el usuario vacío: la API no
    # acepta un mensaje de usuario sin contenido.
    contenido.append({"type": "text", "text": user_prompt or "Adelante."})
    sistema = (system_prompt or "") + (_PIDE_JSON if expect_json else "")
    kwargs: dict[str, Any] = {
        "model": modelo,
        # Caché del prompt del sistema: en una tanda de diez productos el
        # prompt del curso se repite y la relectura cuesta una décima parte.
        "system": [{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": contenido}],
    }
    if tarea in ESFUERZO:
        kwargs["max_tokens"] = max_output_tokens + _MARGEN_PENSAR
        kwargs["output_config"] = {"effort": ESFUERZO[tarea]}
    else:
        kwargs["max_tokens"] = max_output_tokens
        kwargs["thinking"] = {"type": "disabled"}

    with _client().messages.stream(**kwargs) as stream:
        resp = stream.get_final_message()

    _apuntar_coste(resp, modelo, tarea)
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Claude rechazó la petición ({getattr(resp, 'stop_details', None)})")
    texto = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Claude cortó la respuesta por max_tokens")
    if not texto:
        raise RuntimeError("Claude devolvió una respuesta vacía")
    log_info(_LOGGER_NAME, "Claude OK", model=modelo, tarea=tarea)
    return _extraer_json(texto) if expect_json else texto


def _apuntar_coste(resp, modelo: str, tarea: str) -> None:
    try:
        from src.cost_tracking import record_claude

        u = resp.usage
        record_claude(
            input_tokens=int(u.input_tokens or 0),
            output_tokens=int(u.output_tokens or 0),
            cache_write_tokens=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
            cache_read_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
            model=modelo,
            detail=tarea,
        )
    except Exception as e:  # noqa: BLE001 — el coste nunca rompe la llamada
        log_warning(_LOGGER_NAME, "cost tracking falló (ignorando)", error=str(e))


def _extraer_json(texto: str) -> str:
    texto = gemini._strip_json_fences(texto)
    if texto[:1] in "{[":
        return texto
    m = re.search(r"[\[{]", texto)
    return texto[m.start():] if m else texto


def generate_text(
    system_prompt: str,
    user_prompt: str,
    *,
    tarea: Tarea = "texto",
    expect_json: bool = False,
    images: list[str | bytes] | None = None,
    videos: list[str] | None = None,
    audios: list[str] | None = None,
    enable_web_search: bool = False,
    max_output_tokens: int | None = None,
    **gemini_kwargs: Any,
) -> str:
    """Claude, y Gemini si Claude no puede (vídeo/audio/web, sin clave o error).

    `gemini_kwargs` (model, temperature, max_retries_on_quota…) solo se usan
    en el respaldo: los modelos 5.5 no aceptan temperatura."""
    if activo() and not videos and not audios and not enable_web_search:
        try:
            return _llamar(system_prompt, user_prompt, tarea=tarea, expect_json=expect_json,
                           images=images, max_output_tokens=max_output_tokens or 8192)
        except Exception as e:  # noqa: BLE001
            log_warning(_LOGGER_NAME, "Claude falló → respaldo Gemini", error=str(e)[:200])
    return gemini.generate_text(
        system_prompt, user_prompt,
        **_solo_dados(expect_json=expect_json, images=images, videos=videos, audios=audios,
                      enable_web_search=enable_web_search, max_output_tokens=max_output_tokens),
        **gemini_kwargs,
    )


def generate_json(
    system_prompt: str,
    user_prompt: str,
    *,
    tarea: Tarea = "texto",
    images: list[str | bytes] | None = None,
    audios: list[str] | None = None,
    max_output_tokens: int | None = None,
    **gemini_kwargs: Any,
) -> Any:
    """Como `gemini.generate_json`: JSON ya parseado. Dos intentos con Claude
    y, si los dos salen rotos o falla la llamada, el de Gemini entero."""
    if activo() and not audios:
        for intento in range(2):
            try:
                raw = _llamar(system_prompt, user_prompt, tarea=tarea, expect_json=True,
                              images=images, max_output_tokens=max_output_tokens or 32768)
                return json.loads(raw)
            except json.JSONDecodeError as e:
                log_warning(_LOGGER_NAME, f"JSON inválido de Claude (intento {intento + 1}/2): {e}")
            except Exception as e:  # noqa: BLE001
                log_warning(_LOGGER_NAME, "Claude falló → respaldo Gemini", error=str(e)[:200])
                break
    return gemini.generate_json(
        system_prompt, user_prompt,
        **_solo_dados(images=images, audios=audios, max_output_tokens=max_output_tokens),
        **gemini_kwargs,
    )


def _solo_dados(**kw: Any) -> dict[str, Any]:
    """Al respaldo solo va lo que el caller pasó: así se queda con SUS
    valores por defecto, igual que si lo hubiera llamado directamente."""
    return {k: v for k, v in kw.items() if v not in (None, False)}
