"""Fetch del catálogo real de voces system de MiniMax.

Endpoint: POST https://api.minimax.io/v1/get_voice

Body soportado:
    {"voice_type": "all" | "system" | "voice_cloning" | "voice_generation"}

Respuesta (shape relevante):
    {
        "system_voice": [{"voice_id": "...", "voice_name": "...", "description": [...]}],
        "voice_cloning": [...],
        "base_resp": {"status_code": 0, "status_msg": ""}
    }

Implementamos también un cache Redis (24h) para evitar pegar a MiniMax en
cada render de la página de voces. `force_refresh=True` ignora el cache.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import requests


GET_VOICE_URL = "https://api.minimax.io/v1/get_voice"

# Cache Redis: namespace `tiktok_shop:` ya existe (repos/redis_base.py)
_CACHE_KEY = "voice:minimax_system_catalog"
_CACHE_TTL_SECONDS = 24 * 3600  # 24h


def is_available() -> bool:
    return bool(os.getenv("MINIMAX_API_KEY"))


def _fetch_live(timeout: int = 30) -> list[dict[str, Any]]:
    """Llama a /v1/get_voice con voice_type=system y devuelve la lista
    bruta de voces system del catálogo MiniMax."""
    api_key = os.getenv("MINIMAX_API_KEY")
    if not api_key:
        raise EnvironmentError("Falta MINIMAX_API_KEY en .env")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {"voice_type": "system"}
    group_id = os.getenv("MINIMAX_GROUP_ID")
    if group_id:
        body["group_id"] = group_id

    r = requests.post(GET_VOICE_URL, headers=headers, json=body, timeout=timeout)
    r.raise_for_status()
    payload = r.json()
    base = payload.get("base_resp", {})
    if base.get("status_code") not in (0, None):
        raise RuntimeError(
            f"MiniMax get_voice error: {base.get('status_msg')} ({base})"
        )
    voices = payload.get("system_voice") or []
    if not isinstance(voices, list):
        raise RuntimeError(f"system_voice no es lista: {type(voices)}")
    return voices


def _classify(voice_id: str, voice_name: str | None) -> tuple[str, str | None]:
    """Heurística: devuelve `(language, gender_or_none)` a partir del id/nombre.

    - Prefijos de MiniMax: `Spanish_`, `English_`, `Chinese_`, etc.
    - Si no se reconoce el prefijo cae a "en".
    """
    vid = voice_id or ""
    prefix = vid.split("_", 1)[0].lower() if "_" in vid else ""
    lang_map = {
        "english": "en",
        "spanish": "es",
        "chinese": "zh",
        "japanese": "ja",
        "korean": "ko",
        "french": "fr",
        "german": "de",
        "italian": "it",
        "portuguese": "pt",
        "russian": "ru",
        "arabic": "ar",
    }
    language = lang_map.get(prefix, "en")
    # gender_hint best-effort sobre el nombre crudo
    name = (voice_name or vid).lower()
    if any(k in name for k in ("girl", "woman", "lady", "queen", "female")):
        gender = "female"
    elif any(k in name for k in ("boy", "man", "male", "warrior", "boss",
                                  "scholar", "leader", "debator", "partner",
                                  "comedian", "youngman", "person")):
        gender = "male"
    else:
        gender = None
    return language, gender


def normalize_voices(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convierte la respuesta cruda en `[{id, name, language, gender}]`."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for v in raw:
        vid = v.get("voice_id") or v.get("id")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        vname = v.get("voice_name") or v.get("name") or vid
        lang, gender = _classify(vid, vname)
        out.append({
            "id": vid,
            "name": vname,
            "language": lang,
            "gender": gender,
        })
    return out


def _cache_get():
    """Devuelve `(voices_normalized, age_seconds)` o `None` si no hay cache."""
    try:
        from src.tiktok_shop.repos.redis_base import get_shop_redis
        r = get_shop_redis()
        if not r.is_available():
            return None
        raw = r.get_json(_CACHE_KEY)
        if not raw:
            return None
        ts = float(raw.get("ts", 0))
        voices = raw.get("voices") or []
        if not voices:
            return None
        age = time.time() - ts
        if age > _CACHE_TTL_SECONDS:
            return None
        return voices, age
    except Exception:
        return None


def _cache_set(voices: list[dict[str, Any]]) -> None:
    try:
        from src.tiktok_shop.repos.redis_base import get_shop_redis
        r = get_shop_redis()
        if not r.is_available():
            return
        r.set_json(_CACHE_KEY, {"ts": time.time(), "voices": voices})
    except Exception:
        pass


def get_system_voices(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    """Devuelve la lista normalizada de voces system MiniMax.

    - Si hay cache fresca (<24h) y `force_refresh=False`, la usa.
    - Si no, pega a MiniMax, normaliza y cachea.
    - Si MiniMax falla y hay cache (aunque vieja), devuelve la cache.
    - Si todo falla y no hay cache, lanza la excepción.
    """
    if not force_refresh:
        cached = _cache_get()
        if cached is not None:
            return cached[0]

    try:
        raw = _fetch_live()
        normalized = normalize_voices(raw)
        if normalized:
            _cache_set(normalized)
            return normalized
    except Exception as e:
        # Fallback a cache aunque esté vieja
        try:
            from src.tiktok_shop.repos.redis_base import get_shop_redis
            r = get_shop_redis()
            if r.is_available():
                raw_cache = r.get_json(_CACHE_KEY)
                if raw_cache and raw_cache.get("voices"):
                    return raw_cache["voices"]
        except Exception:
            pass
        raise e

    return []


def get_cache_meta() -> dict[str, Any] | None:
    """Devuelve `{ts, age_seconds, count}` de la cache, o None si vacía."""
    cached = _cache_get()
    if cached is None:
        return None
    voices, age = cached
    return {"age_seconds": age, "count": len(voices)}
