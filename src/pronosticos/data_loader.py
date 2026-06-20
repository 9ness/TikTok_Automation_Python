"""Carga del guion de vídeo desde Redis (key `daily_bets_tiktok_video`).

El proyecto bet-ai-master persiste el guion del día como un payload con
**array de versiones**: cada vez que se regenera (cron o admin manual) se añade
una entry nueva con id incremental. El campo `selected_version_id` indica cuál
debe usar el agente del vídeo por defecto.

Este módulo:
  - Lee el payload bruto de Redis.
  - Devuelve la versión seleccionada (si existe) o la última como fallback.
  - Permite listar todas las versiones disponibles para que la UI muestre selector.
  - Mantiene compatibilidad con el formato antiguo sin `versions[]`.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from .redis_client import UpstashRedis


def tomorrow_iso() -> str:
    return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")


# ── API pública ─────────────────────────────────────────────────────────

def find_latest_available_date(redis: UpstashRedis | None = None,
                                max_lookback_days: int = 14) -> str | None:
    """Busca el field de fecha más reciente disponible en `daily_bets_tiktok_video:*`.

    Recorre desde hoy hacia atrás hasta `max_lookback_days`. Devuelve el
    primer `YYYY-MM-DD` que tenga payload (None si nada en el rango).

    Útil para el botón "Cargar último disponible" cuando el usuario no sabe
    qué fechas hay (p.ej. el cron de hoy aún no corrió o salta días).
    """
    redis = redis or UpstashRedis()
    today = date.today()
    for delta in range(0, max_lookback_days + 1):
        d = today - timedelta(days=delta)
        date_str = d.strftime("%Y-%m-%d")
        try:
            raw = redis.hget(f"daily_bets_tiktok_video:{date_str[:7]}", date_str)
            if raw is not None:
                return date_str
        except Exception:
            continue
    return None


def load_raw_payload(target_date: str | None = None,
                     redis: UpstashRedis | None = None) -> dict | None:
    """Devuelve el payload bruto de Redis (con `versions[]` o formato legacy).

    None si la key/field no existe.
    """
    if not target_date:
        target_date = tomorrow_iso()
    yyyy_mm = target_date[:7]
    redis = redis or UpstashRedis()
    raw = redis.hget(f"daily_bets_tiktok_video:{yyyy_mm}", target_date)
    if raw is None:
        return None
    return _coerce_json(raw)


def load_fixture_times(target_date: str | None = None,
                       redis: UpstashRedis | None = None) -> dict[str, str]:
    """{fixture_id(str): 'YYYY-MM-DD HH:MM' (Madrid)} desde `raw_matches_tiktok`.

    Los picks del guion NO traen la hora — está aquí, por `fixture_id`. El
    `timestamp` es UTC; lo pasamos a Madrid (verano CEST = UTC+2) para que el
    overlay lo convierta a Perú (−7h) como el resto."""
    from datetime import datetime, timedelta
    if not target_date:
        target_date = tomorrow_iso()
    redis = redis or UpstashRedis()
    raw = redis.hget(f"raw_matches_tiktok:{target_date[:7]}", target_date)
    out: dict[str, str] = {}
    if not raw:
        return out
    matches = _coerce_json(raw)
    if not isinstance(matches, list):
        return out
    for m in matches:
        fid = str(m.get("id") or "")
        ts = m.get("timestamp")
        if not fid or ts is None:
            continue
        try:
            madrid = datetime.utcfromtimestamp(int(ts)) + timedelta(hours=2)
            out[fid] = madrid.strftime("%Y-%m-%d %H:%M")
        except Exception:
            continue
    return out


def list_versions(payload: dict | None) -> list[dict]:
    """Devuelve la lista de versiones disponibles dentro de un payload.

    - Si trae `versions[]` (formato nuevo), las devuelve enriquecidas con un flag
      `is_selected` por cada una.
    - Si es formato legacy (la versión está en el nivel raíz), devuelve una lista
      con esa única entry pseudo-id="legacy".
    - Si payload es None o vacío, devuelve [].
    """
    if not payload:
        return []
    versions = payload.get("versions")
    selected_id = payload.get("selected_version_id")

    if isinstance(versions, list) and versions:
        out = []
        for v in versions:
            entry = dict(v)  # copia superficial para no mutar el payload
            entry["is_selected"] = (str(entry.get("id")) == str(selected_id))
            out.append(entry)
        return out

    # Formato legacy: el propio payload es la versión
    if payload.get("script"):
        legacy = dict(payload)
        legacy["id"] = "legacy"
        legacy["trigger"] = legacy.get("trigger", "legacy")
        legacy["is_selected"] = True
        return [legacy]
    return []


def load_chosen_version(target_date: str | None = None,
                         version_id: str | None = None,
                         redis: UpstashRedis | None = None) -> dict:
    """Devuelve UNA versión del guion lista para feed al pipeline.

    Prioridad:
      1. `version_id` explícito (si se pasa) — busca esa entry en `versions[]`.
      2. `selected_version_id` del payload (la marcada con ⭐ en el admin).
      3. Última versión del array (fallback robusto).
      4. Formato legacy: el payload entero.

    Levanta ValueError si no hay datos o ninguna versión válida.
    """
    payload = load_raw_payload(target_date, redis=redis)
    if payload is None:
        td = target_date or tomorrow_iso()
        raise ValueError(
            f"El guion de vídeo para {td} aún no está en Redis. "
            f"El workflow tiktok_video_script.yml debe haberse ejecutado en bet-ai-master "
            f"(corre tras el carrusel, sobre las 18:05 hora Madrid)."
        )

    versions = list_versions(payload)
    if not versions:
        raise ValueError("Payload sin versiones ni script raíz — no hay nada que reproducir.")

    chosen: dict | None = None

    # 1. version_id explícito
    if version_id is not None:
        chosen = next((v for v in versions if str(v.get("id")) == str(version_id)), None)
        if chosen is None:
            raise ValueError(
                f"Versión {version_id!r} no encontrada. IDs disponibles: "
                f"{[str(v.get('id')) for v in versions]}"
            )

    # 2. is_selected (selected_version_id del payload)
    if chosen is None:
        chosen = next((v for v in versions if v.get("is_selected")), None)

    # 3. Última como fallback
    if chosen is None:
        chosen = versions[-1]

    if not chosen.get("script"):
        raise ValueError(f"Versión {chosen.get('id')!r} sin campo `script`.")
    # 'viral' = estilo nuevo (gancho + 4 picks); misma estructura que multi_match
    # (selected_picks), así que el pipeline lo procesa igual.
    if chosen.get("mode") not in ("single_match", "multi_match", "viral"):
        raise ValueError(f"Modo desconocido en versión {chosen.get('id')!r}: {chosen.get('mode')}")

    return chosen


# ── Compat: alias antiguo ────────────────────────────────────────────────

def load_video_script(target_date: str | None = None,
                       redis: UpstashRedis | None = None,
                       version_id: str | None = None) -> dict:
    """Alias mantenido para compatibilidad — equivale a `load_chosen_version`."""
    return load_chosen_version(target_date=target_date, version_id=version_id, redis=redis)


def load_daily_bets(target_date: str | None = None, redis: UpstashRedis | None = None) -> dict:
    """Alias legacy aún más antiguo (apuntaba a daily_bets_tiktok antes de v2)."""
    return load_chosen_version(target_date=target_date, redis=redis)


# ── Picks helpers ────────────────────────────────────────────────────────

def get_picks(payload: dict) -> list[dict]:
    """Devuelve la lista de picks del payload, sea cual sea el modo.

    `single_match` → `focus_selections`
    `multi_match`  → `selected_picks`
    """
    if payload.get("mode") == "single_match":
        return payload.get("focus_selections") or []
    return payload.get("selected_picks") or []


# ── Caption + URL publishing ─────────────────────────────────────────────

def load_caption(redis: UpstashRedis | None = None) -> dict | None:
    """Caption viral generado por bet-ai-master (key string `tiktokfactory_tomorrow`)."""
    redis = redis or UpstashRedis()
    raw = redis.get("tiktokfactory_tomorrow")
    if not raw:
        return None
    try:
        return _coerce_json(raw)
    except Exception:
        return {"text": raw}


def publish_video_url(target_date: str, video_url: str, duration_s: float,
                      redis: UpstashRedis | None = None,
                      version_id: str | None = None) -> None:
    """Publica la URL del MP4 final en Redis.

    Si version_id se especifica, lo incluye en el payload para identificar qué
    versión del guion produjo el vídeo.
    """
    redis = redis or UpstashRedis()
    payload = {
        "date": target_date,
        "url": video_url,
        "duration_s": round(duration_s, 2),
        "generated_at": _now_iso(),
    }
    if version_id is not None:
        payload["version_id"] = str(version_id)
    redis.set("tiktokfactory_video_tomorrow", payload)


# ── Helpers internos ─────────────────────────────────────────────────────

def _coerce_json(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    raise ValueError(f"Tipo inesperado para JSON Redis: {type(raw)}")


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
