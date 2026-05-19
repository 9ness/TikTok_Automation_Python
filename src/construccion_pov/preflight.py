"""Pre-flight checks de Construcción POV.

Se ejecutan SÍNCRONAMENTE en el handler `/enqueue` ANTES de meter el job
en la cola. Si algo falla → 422 estructurado → el cliente lo ve sin que
se gaste un céntimo en Gemini ni MiniMax.

Checks (en orden):
  1. Env vars: `MINIMAX_API_KEY` + al menos una key de Gemini
  2. Vídeo: existe, ext válida, peso > 0, ffprobe duración > 1s
  3. Fuente: `font_path` existe en el fonts registry
  4. Voz: `voice_id` (sea `preset_*` o id de clone Redis) resuelve a un
     `minimax_voice_id` que existe en:
        - El catálogo system live de MiniMax (cache 24h)
        - O un clone guardado en Redis
     Si la cache está vacía, se hace un sync silencioso. Si el `voice_id`
     llega "pelado" (sin `preset_` prefix y no es de un clone), se busca
     directamente contra el catálogo.

Devuelve `(minimax_voice_id_resuelto, duration_seconds)` si todo OK.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


class PreflightFailure(Exception):
    """Excepción interna. El router la traduce a 422."""

    def __init__(self, message: str, *, field: str | None = None,
                 hint: str | None = None, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = {}
        if field:
            self.details["field"] = field
        if hint:
            self.details["hint"] = hint
        if extra:
            self.details.update(extra)


def _check_env() -> None:
    if not os.getenv("MINIMAX_API_KEY"):
        raise PreflightFailure(
            "Falta MINIMAX_API_KEY en el entorno — sin TTS no se puede generar el vídeo.",
            field="env.MINIMAX_API_KEY",
            hint="Añade MINIMAX_API_KEY al .env y reinicia el API.",
        )
    has_gemini = (
        os.getenv("GOOGLE_GEMINI_KEY_FREE")
        or os.getenv("GOOGLE_GEMINI_KEY_PAID")
        or os.getenv("GOOGLE_AI_API_KEY")
        or os.getenv("GOOGLE_GEMINI_KEY")
    )
    if not has_gemini:
        raise PreflightFailure(
            "Sin API key de Gemini — no se puede generar el guion.",
            field="env.GOOGLE_GEMINI_KEY_*",
            hint="Define GOOGLE_GEMINI_KEY_FREE y/o GOOGLE_GEMINI_KEY_PAID en .env.",
        )


def _check_video(input_path: Path) -> float:
    if not input_path.exists():
        raise PreflightFailure(
            f"El vídeo no existe en disco: {input_path}",
            field="file",
        )
    if input_path.stat().st_size == 0:
        raise PreflightFailure("El vídeo está vacío (0 bytes).", field="file")

    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(input_path),
            ],
            check=True, capture_output=True, text=True, timeout=30,
        )
        duration = float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired) as e:
        raise PreflightFailure(
            f"ffprobe no pudo leer la duración del vídeo: {e}",
            field="file",
            hint="Verifica que el archivo no esté corrupto.",
        )
    if duration < 1.0:
        raise PreflightFailure(
            f"Duración demasiado corta ({duration:.2f}s) — mínimo 1s.",
            field="file",
            extra={"duration_seconds": duration},
        )
    if duration > 180.0:
        raise PreflightFailure(
            f"Duración demasiado larga ({duration:.0f}s) — máximo 180s.",
            field="file",
            extra={"duration_seconds": duration},
        )
    return duration


def _check_font(font_path: str) -> None:
    if not font_path or not font_path.strip():
        raise PreflightFailure(
            "Falta `font_path` (no se eligió fuente para subs).",
            field="font_path",
        )
    try:
        from src.fonts_registry import find_by_path
        entry = find_by_path(font_path)
    except Exception as e:
        raise PreflightFailure(
            f"Error resolviendo la fuente: {e}",
            field="font_path",
            extra={"font_path": font_path},
        )
    if entry is None:
        raise PreflightFailure(
            f"La fuente '{font_path}' no existe en el registry.",
            field="font_path",
            hint="Elige otra del selector o súbela en /fonts.",
            extra={"font_path": font_path},
        )


def _resolve_voice(voice_id: str) -> str:
    """Devuelve el `minimax_voice_id` real que se debe pasar a TTS.

    Estrategia:
      1. Si empieza con `preset_`, mira el catálogo live; si está, devuelve
         el id pelado (sin prefijo). Si la cache está vacía, hace sync.
      2. Si NO empieza con `preset_`, mira primero como clone (VoiceRepo)
         y, si no existe, comprueba si es un id system del catálogo directo.

    Lanza PreflightFailure si no se puede resolver.
    """
    if not voice_id or not voice_id.strip():
        raise PreflightFailure(
            "Falta `voice_id` (no se eligió voz).",
            field="voice_id",
        )

    raw_id = (
        voice_id[len("preset_"):]
        if voice_id.startswith("preset_")
        else voice_id
    )

    # 1) Si NO es preset, mira primero clones Redis (más rápido y sin red).
    if not voice_id.startswith("preset_"):
        try:
            from src.tiktok_shop.repos import VoiceRepo
            repo = VoiceRepo()
            v = repo.get(voice_id)
            if v is not None:
                return v.minimax_voice_id
        except Exception:
            pass

    # 2) Mira el catálogo system live. Cache 24h en Redis.
    try:
        from src.tiktok_shop.api.minimax_catalog import (
            get_cache_meta,
            get_system_voices,
        )
        if get_cache_meta() is None:
            # Primera vez tras deploy → sync silencioso.
            voices = get_system_voices(force_refresh=True)
        else:
            voices = get_system_voices(force_refresh=False)
    except Exception as e:
        raise PreflightFailure(
            f"No se pudo verificar el catálogo MiniMax: {e}",
            field="voice_id",
            hint="Comprueba MINIMAX_API_KEY y conectividad, o pulsa 'Sincronizar' en Herramientas · Voces.",
            extra={"voice_id": voice_id},
        )

    if any(v["id"] == raw_id for v in voices):
        return raw_id

    # 3) Último intento: por si llegó pelado pero es realmente un clone
    if voice_id.startswith("preset_"):
        # preset_* con id que no está en catálogo → casi seguro inventado
        raise PreflightFailure(
            f"La voz '{raw_id}' no existe en el catálogo MiniMax de tu cuenta.",
            field="voice_id",
            hint="Selecciona otra voz, sincroniza el catálogo o clona una.",
            extra={"voice_id": voice_id, "resolved_id": raw_id},
        )
    raise PreflightFailure(
        f"voice_id '{voice_id}' no es un clone guardado ni un preset MiniMax conocido.",
        field="voice_id",
        hint="Selecciona la voz desde el selector (no escribas el id manualmente).",
        extra={"voice_id": voice_id},
    )


def run_preflight(
    *,
    input_path: Path,
    voice_id: str,
    font_path: str,
) -> dict[str, Any]:
    """Ejecuta todos los checks. Devuelve dict con datos resueltos:
        {"duration_seconds": float, "minimax_voice_id": str}

    Si algún check falla, lanza `PreflightFailure` (el caller lo traduce
    a 422 con `code=invalid_enqueue_request`).
    """
    _check_env()
    duration = _check_video(input_path)
    _check_font(font_path)
    resolved_voice = _resolve_voice(voice_id)
    return {
        "duration_seconds": duration,
        "minimax_voice_id": resolved_voice,
    }
