"""Tracking en Redis del progreso de la generación asíncrona de presets.

Cuando el frontend pulsa "Regenerar todos", el endpoint:
1. Crea un `gen_id` y guarda estado inicial en Redis (`preset_gen:{id}`).
2. Lanza la generación en BackgroundTasks de FastAPI.
3. Devuelve el `gen_id` al instante para que la UI muestre barra de
   progreso y persista el ID en localStorage.
4. El BackgroundTask va actualizando el estado en Redis por stages:
   `started` → `generating_music` (50%) → `generating_scripted` (100%)
   → `done` o `error`.
5. La UI consulta `GET /preset-gen-status/{id}` cada 2s para refrescar
   la barra. Cuando ve `done`, invalida la lista de presets y limpia
   el localStorage.

Si el navegador refresca durante la generación, la UI lee el `gen_id`
de localStorage y vuelve a consultar el estado — la generación sigue
corriendo en el servidor sin interrupción.

TTL: 30 minutos. Si pasa más, asumimos que algo falló y la key expira.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from src.tiktok_shop.repos.redis_base import get_shop_redis

logger = logging.getLogger("tiktok_shop.preset_gen_tracker")


# Stages del flujo
PresetGenStage = Literal[
    "started",
    "generating_music",
    "generating_scripted",
    "saving",
    "done",
    "error",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(gen_id: str) -> str:
    return f"preset_gen:{gen_id}"


def create(product_id: str, kind: str, expected_count: int) -> str:
    """Crea un tracker nuevo y devuelve el gen_id."""
    gen_id = uuid.uuid4().hex[:16]
    state: dict[str, Any] = {
        "gen_id": gen_id,
        "product_id": product_id,
        "kind": kind,                  # "music" | "scripted" | "both"
        "stage": "started",
        "percent": 0,
        "expected_count": expected_count,
        "created_count": 0,
        "warnings": [],
        "started_at": _now_iso(),
        "ended_at": None,
        "error": None,
        # Coste acumulado de llamadas a Gemini (USD). Se actualiza tras
        # cada stage leyendo `cost_tracking.get_active().total_usd`.
        "cost_usd": 0.0,
    }
    _write(gen_id, state)
    return gen_id


def update(
    gen_id: str,
    *,
    stage: PresetGenStage | None = None,
    percent: int | None = None,
    created_count: int | None = None,
    warnings: list[str] | None = None,
    error: str | None = None,
    cost_usd: float | None = None,
) -> None:
    """Update parcial. Si stage=done o error, marca ended_at."""
    state = get(gen_id)
    if state is None:
        return
    if stage is not None:
        state["stage"] = stage
    if percent is not None:
        state["percent"] = max(0, min(100, int(percent)))
    if created_count is not None:
        state["created_count"] = int(created_count)
    if warnings is not None:
        state["warnings"] = list(warnings)
    if error is not None:
        state["error"] = str(error)[:500]
    if cost_usd is not None:
        state["cost_usd"] = round(float(cost_usd), 6)
    if stage in ("done", "error"):
        state["ended_at"] = _now_iso()
    _write(gen_id, state)


def get(gen_id: str) -> dict[str, Any] | None:
    return get_shop_redis().get_json(_key(gen_id))


def _write(gen_id: str, state: dict[str, Any]) -> None:
    # ShopRedis no expone TTL directo; pasamos por la API REST con expire.
    # Si no soportado, se persiste sin TTL y queda hasta sobrescritura.
    try:
        get_shop_redis().set_json(_key(gen_id), state)
    except Exception as e:
        logger.warning("[preset_gen_tracker] write fail %s: %s", gen_id, e)
