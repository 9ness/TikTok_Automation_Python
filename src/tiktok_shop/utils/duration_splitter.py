"""Calcula cómo dividir una duración total en clips Atlas Cloud, según
estrategia elegida (cinematográfico vs dinámico TikTok).

Restricciones del backend (per doc Atlas):
  - Standard / Advanced: cada clip ∈ [4, 12] segundos.
  - Pro: hasta 15s en un solo clip multi-shot.

El usuario elige uno de los 2 presets:

  🎬 Cinematográfico — pocos clips largos, máxima continuidad.
  ⚡ Dinámico TikTok — muchos clips cortos, máxima retención.

Las tablas exactas vienen del brief; si la duración no está en la tabla
preset (caso edge de UI custom), caemos a un splitter automático que
respeta los límites del tier sin tener en cuenta la estrategia.
"""

from __future__ import annotations

from src.tiktok_shop.config import (
    DEFAULT_VIDEO_STRATEGY, TIER_DURATION_LIMITS, VIDEO_STRATEGIES,
)


# ---------------------------------------------------------------------------
# Tablas preset por estrategia (Standard/Advanced — ambos comparten límites)
# ---------------------------------------------------------------------------
# Margen de seguridad incorporado (mayo 2026 — fix duración corta):
# Atlas devuelve clips ~5.04s para 5s pedidos, pero los recortes posteriores
# (trim_head 0.15s × N + crossfade × (N-1)) reducen ~1s para 3 clips de 15s.
# Las tablas añaden ~1s extra distribuido en los primeros clips para que el
# MP4 final sea ≥ duración pedida por el usuario:
#
#   Dinámico (xfade 0.3): shrinkage = N×0.15 + (N-1)×0.3
#   Cinematográfico (xfade 0.5): shrinkage = N×0.15 + (N-1)×0.5
#
# Cada clip Atlas devuelve ~target+0.04s. Suma post-shrinkage debe ≥ target.
_CINEMATIC_TABLE: dict[int, list[int]] = {
    5:  [6],            # 6.04 - 0.15 = 5.89 ≥ 5
    10: [11],           # 11.04 - 0.15 = 10.89 ≥ 10
    12: [7, 6],         # 13.08 - 0.30 - 0.5 = 12.28 ≥ 12
    15: [11, 5],        # 16.08 - 0.30 - 0.5 = 15.28 ≥ 15
    20: [12, 9],        # 21.08 - 0.30 - 0.5 = 20.28 ≥ 20
    24: [12, 8, 6],     # 26.13 - 0.45 - 1.0 = 24.68 ≥ 24
    25: [12, 9, 6],     # 27.13 - 0.45 - 1.0 = 25.68 ≥ 25
    30: [12, 12, 8],    # 32.13 - 0.45 - 1.0 = 30.68 ≥ 30
}

_DYNAMIC_TABLE: dict[int, list[int]] = {
    5:  [6],                    # 5.89 ≥ 5
    10: [6, 5],                 # 11.08 - 0.30 - 0.3 = 10.48 ≥ 10
    12: [5, 4, 4],              # 13.13 - 0.45 - 0.6 = 12.08 ≥ 12
    15: [6, 5, 5],              # 16.13 - 0.45 - 0.6 = 15.08 ≥ 15
    20: [6, 6, 5, 5],           # 22.17 - 0.60 - 0.9 = 20.67 ≥ 20
    24: [6, 5, 5, 5, 5],        # 26.21 - 0.75 - 1.2 = 24.26 ≥ 24
    25: [6, 6, 5, 5, 5],        # 27.21 - 0.75 - 1.2 = 25.26 ≥ 25
    30: [6, 6, 6, 5, 5, 5],     # 33.25 - 0.90 - 1.5 = 30.85 ≥ 30
}


def _preset_table(strategy: str) -> dict[int, list[int]]:
    if strategy == "cinematic":
        return _CINEMATIC_TABLE
    if strategy == "dynamic":
        return _DYNAMIC_TABLE
    raise ValueError(f"Estrategia desconocida: {strategy}")


# ---------------------------------------------------------------------------
# split_duration — entry point
# ---------------------------------------------------------------------------
def split_duration(
    total_seconds: int,
    tier: str,
    strategy: str = DEFAULT_VIDEO_STRATEGY,
) -> list[int]:
    """Devuelve la lista de duraciones por clip que sumarán `total_seconds`.

    Args:
        total_seconds: duración total pedida por el usuario.
        tier: 'standard'/'advanced'/'pro'.
        strategy: 'cinematic' o 'dynamic' (default `dynamic`). Solo aplica a
            Standard/Advanced. Para Pro se ignora (devuelve [total] si cabe
            en 1 clip multi-shot, o split en chunks de 15s).
    """
    if strategy not in VIDEO_STRATEGIES:
        raise ValueError(
            f"Estrategia '{strategy}' no soportada. Usa: {VIDEO_STRATEGIES}"
        )
    limits = TIER_DURATION_LIMITS.get(tier)
    if limits is None:
        raise ValueError(f"Tier desconocido para duration_splitter: {tier}")
    min_clip = limits["min_per_clip"]
    max_clip = limits["max_per_clip"]

    if total_seconds <= 0:
        return []
    if total_seconds < min_clip:
        return [min_clip]

    # ---------- Pro: 1 clip nativo si cabe; chunks de 15s si excede ----------
    if tier == "pro":
        if total_seconds <= max_clip:
            return [total_seconds]
        n_full = total_seconds // max_clip
        rest = total_seconds % max_clip
        clips = [max_clip] * n_full
        if rest:
            if rest >= min_clip:
                clips.append(rest)
            elif clips:
                # absorbe el resto en el último para que no quede clip <min
                clips[-1] += rest
        return clips

    # ---------- Standard / Advanced: tabla preset por estrategia ----------
    table = _preset_table(strategy)
    if total_seconds in table:
        return list(table[total_seconds])

    # ---------- Fallback automático (duración no en tabla preset) ----------
    # Caso edge: la UI ofrece duraciones de la tabla, pero algún caller (test
    # E2E ad-hoc, regen-with-changes) podría pedir otra. Distribución uniforme
    # respetando los límites del tier; preferencia por nº de clips coherente
    # con la estrategia (cinematic = menos, dynamic = más).
    if total_seconds <= max_clip:
        return [total_seconds]

    if strategy == "dynamic":
        # Dinámico: prefer clips cortos. Probar 5, luego 4, luego 6...
        for unit in (5, 4, 6, 7, 8, 9, 10, 11, 12):
            if min_clip <= unit <= max_clip and total_seconds % unit == 0:
                return [unit] * (total_seconds // unit)
    else:
        # Cinematográfico: clips lo más largos posible.
        for unit in (12, 11, 10, 9, 8, 7, 6, 5, 4):
            if min_clip <= unit <= max_clip and total_seconds % unit == 0:
                return [unit] * (total_seconds // unit)

    # Sin divisor exacto — distribución manual con base + resto.
    n_clips = -(-total_seconds // max_clip)  # ceil
    while n_clips > 1 and total_seconds // n_clips < min_clip:
        n_clips -= 1
    base = total_seconds // n_clips
    rem = total_seconds - base * n_clips
    clips = [base] * n_clips
    for i in range(rem):
        clips[i] += 1
    # Sanity: forzar todos en [min, max]
    for c in clips:
        if not (min_clip <= c <= max_clip):
            # último recurso: max_clip × N + resto absorbido
            n = total_seconds // max_clip
            last = total_seconds - n * max_clip
            result = [max_clip] * n
            if last >= min_clip:
                result.append(last)
            elif result:
                result[-1] += last
            return result
    return clips


def describe_split(clips: list[int]) -> str:
    """Para mostrar en UI: 'Plan: 3 clips de 5s, 5s, 5s'."""
    if not clips:
        return "0 clips"
    if len(clips) == 1:
        return f"1 clip de {clips[0]}s"
    if len(set(clips)) == 1:
        return f"{len(clips)} clips de {clips[0]}s"
    return f"{len(clips)} clips: " + " + ".join(f"{c}s" for c in clips)
