"""Tracking persistente (Redis) de qué candidatos de gancho/paisaje ya se
usaron, POR PONENTE, para que un vídeo generado NUNCA repita gancho ni
tramo de paisaje — ni siquiera entre ejecuciones de días distintos.

Schema (prefijo `viralizacion:`, ver `repos/redis_base.py`):
- `hook_used:<ponente>`     -> SET de índices (str) de `hook_candidates.json`
                               ya usados por ESE ponente.
- `paisaje_used:<ponente>`  -> SET de índices (str) de `paisaje_candidates.json`
                               ya usados por ESE ponente. El pool de paisajes
                               es COMPARTIDO entre ponentes (mismo vídeo
                               fuente) pero el uso se rastrea por separado
                               por ponente — así cada ponente tiene su propio
                               pool efectivo sin coordinar entre ellos.

Si Redis no está configurado, lanzamos `RuntimeError` en vez de degradar
silenciosamente: la garantía de "nunca repetir" no se puede mantener sin
persistencia, y generar de todos modos sería peor que fallar claro.
"""

from __future__ import annotations

from src.viralizacion.repos.redis_base import get_viralizacion_redis


def _require_redis():
    r = get_viralizacion_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede garantizar "
            "que gancho/paisaje no se repitan entre ejecuciones. Define "
            "UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN."
        )
    return r


def get_used_hook_indices(ponente: str) -> set[int]:
    r = _require_redis()
    members = r.smembers(f"hook_used:{ponente}")
    return {int(m) for m in members if m.isdigit()}


def get_used_paisaje_indices(ponente: str) -> set[int]:
    r = _require_redis()
    members = r.smembers(f"paisaje_used:{ponente}")
    return {int(m) for m in members if m.isdigit()}


def mark_hook_used(ponente: str, index: int) -> None:
    r = _require_redis()
    r.sadd(f"hook_used:{ponente}", str(index))


def release_hook_used(ponente: str, index: int) -> None:
    """Libera un índice de gancho (rollback si el render falla a mitad)."""
    r = get_viralizacion_redis()
    if r.is_available():
        r.srem(f"hook_used:{ponente}", str(index))


def mark_paisaje_used(ponente: str, index: int) -> None:
    r = _require_redis()
    r.sadd(f"paisaje_used:{ponente}", str(index))


def release_paisaje_used(ponente: str, index: int) -> None:
    r = get_viralizacion_redis()
    if r.is_available():
        r.srem(f"paisaje_used:{ponente}", str(index))


def reset_paisaje_used(ponente: str) -> int:
    """Empieza un ciclo nuevo: olvida qué clips de paisaje se han usado.

    No implica repetir material tal cual — de cada clip se saca una ventana
    temporal y un zoom distintos en cada uso, así que la vuelta siguiente no
    reproduce los vídeos de la anterior. Es lo que permite seguir generando
    con un banco finito de clips.
    """
    r = _require_redis()
    used = get_used_paisaje_indices(ponente)
    for idx in used:
        r.srem(f"paisaje_used:{ponente}", str(idx))
    return len(used)
