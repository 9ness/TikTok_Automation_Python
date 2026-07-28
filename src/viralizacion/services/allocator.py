"""Asigna candidatos de gancho/paisaje SIN repetir nunca (por ponente),
combinando el banco de candidatos (`pipeline/resource_scanner.py`) con el
tracking de uso persistente en Redis (`repos/usage_repo.py`).

Los índices se marcan como usados en Redis EN CUANTO se asignan (antes de
que termine el render) — si el render falla después, el caller debe llamar
a `release_hook/release_paisajes` para no perder el hueco definitivamente.
"""

from __future__ import annotations

import random

from src.viralizacion.pipeline.resource_scanner import (
    load_hook_candidates_cached,
    load_paisaje_candidates_cached,
    scan_hook_candidates,
    scan_paisaje_candidates,
)
from src.viralizacion.repos import usage_repo
from src.viralizacion.services import clip_library


class PoolExhaustedError(RuntimeError):
    """Se agotaron los candidatos disponibles (gancho o paisaje) para un ponente."""


def count_available_hooks(ponente: str, *, cache_only: bool = False) -> tuple[int, int]:
    """Devuelve (disponibles, total) de candidatos de gancho para `ponente`.

    `cache_only=True` (UI): no dispara escaneo de cara — solo lee JSON cache.
    """
    candidates = (
        load_hook_candidates_cached(ponente)
        if cache_only
        else scan_hook_candidates(ponente)
    )
    used = usage_repo.get_used_hook_indices(ponente)
    available = [c for c in candidates if c["index"] not in used]
    return len(available), len(candidates)


def count_available_paisajes(ponente: str, *, cache_only: bool = False) -> tuple[int, int]:
    """Devuelve (disponibles, total) de candidatos de paisaje para `ponente`
    (el pool es compartido entre ponentes, pero el uso se rastrea por
    separado — por eso el resultado es específico de `ponente`).

    `cache_only=True` (UI): no trocea el vídeo — solo lee JSON cache.
    """
    candidates = (
        load_paisaje_candidates_cached()
        if cache_only
        else scan_paisaje_candidates()
    )
    used = usage_repo.get_used_paisaje_indices(ponente)
    available = [c for c in candidates if c["index"] not in used]
    return len(available), len(candidates)


def allocate_hook(ponente: str) -> dict:
    """Asigna (y marca como usado) un candidato de gancho no usado para
    `ponente`. Lanza `PoolExhaustedError` si no queda ninguno."""
    candidates = scan_hook_candidates(ponente)
    used = usage_repo.get_used_hook_indices(ponente)
    available = [c for c in candidates if c["index"] not in used]
    if not available:
        raise PoolExhaustedError(
            f"Pool de gancho agotado para '{ponente}': hacían falta 1 más, "
            f"quedan 0 de {len(candidates)} candidatos totales "
            f"({len(used)} ya usados)."
        )
    chosen = available[0]
    usage_repo.mark_hook_used(ponente, chosen["index"])
    return chosen


def release_hook(ponente: str, index: int) -> None:
    usage_repo.release_hook_used(ponente, index)


def allocate_paisaje_clips(ponente: str, n: int) -> list[dict]:
    """Asigna `n` clips de la biblioteca, uno por LUGAR distinto.

    Cada clip es un plano entero del original, así que el sitio no cambia a
    mitad de clip. Se elige una ventana aleatoria dentro de cada uno para que
    el mismo clip nunca salga con el mismo encuadre temporal.

    Los clips agrupados en el mismo `location` (mismo sitio desde otro ángulo)
    no se mezclan dentro del mismo vídeo: sería volver al bug de "transición
    pero mismo lugar".
    """
    clips = clip_library.all_clips()
    if not clips:
        raise PoolExhaustedError(
            "La biblioteca de clips de paisaje está vacía. Genera los clips "
            "antes de renderizar (ver VIRALIZACION_MODULE.md)."
        )
    used = usage_repo.get_used_paisaje_indices(ponente)
    available = [c for c in clips if c["index"] not in used]

    # Ciclo nuevo: cuando se agota la vuelta, se reinicia el marcador en vez
    # de bloquear la generación. NO es repetir material tal cual — de cada
    # clip se saca una ventana temporal distinta y un zoom distinto, así que
    # el vídeo resultante no coincide con el de la vuelta anterior. Es lo que
    # permite seguir generando indefinidamente con un banco finito.
    if len(available) < n:
        if len(clips) < n:
            raise PoolExhaustedError(
                f"Solo hay {len(clips)} clips en la biblioteca y hacen falta "
                f"{n} para un vídeo. Añade más material."
            )
        usage_repo.reset_paisaje_used(ponente)
        available = list(clips)

    random.shuffle(available)
    chosen: list[dict] = []
    seen_locations: set = set()
    for c in available:
        loc = c.get("location", c["index"])
        if loc in seen_locations:
            continue
        seen_locations.add(loc)
        chosen.append(c)
        if len(chosen) == n:
            break
    # Si los lugares distintos no dan para `n`, se completa con lo que queda
    # (mejor repetir lugar que fallar el vídeo entero).
    if len(chosen) < n:
        for c in available:
            if c not in chosen:
                chosen.append(c)
                if len(chosen) == n:
                    break

    out: list[dict] = []
    for c in chosen:
        start, dur = clip_library.random_window(c)
        usage_repo.mark_paisaje_used(ponente, c["index"])
        out.append({
            "index": c["index"],
            "path": str(clip_library.clip_path(c)),
            "start": start,
            "dur": dur,
        })
    return out


def allocate_paisaje_segments(ponente: str, n: int) -> list[dict]:
    """Asigna (y marca como usados) `n` candidatos de paisaje no usados por
    `ponente`. Lanza `PoolExhaustedError` con el déficit exacto si no hay
    suficientes."""
    candidates = scan_paisaje_candidates()
    used = usage_repo.get_used_paisaje_indices(ponente)
    available = [c for c in candidates if c["index"] not in used]
    if len(available) < n:
        raise PoolExhaustedError(
            f"Pool de paisaje agotado para '{ponente}': hacían falta {n}, "
            f"quedan {len(available)} de {len(candidates)} candidatos totales "
            f"({len(used)} ya usados)."
        )
    # Los candidatos son trozos CONTIGUOS de 4,5s del mismo vídeo fuente, así
    # que `available[:n]` daba n tramos seguidos: el corte se veía pero el
    # plano era el mismo sitio (misma fachada, misma plaza…). Repartimos los
    # n tramos en n bloques a lo largo de todo el vídeo y sacamos uno al azar
    # de cada bloque → clips consecutivos quedan a minutos de distancia en el
    # origen, que es lo que hace que se vean lugares distintos.
    chosen: list[dict] = []
    bucket = len(available) / n
    for i in range(n):
        lo = int(i * bucket)
        hi = max(lo + 1, min(int((i + 1) * bucket), len(available)))
        chosen.append(random.choice(available[lo:hi]))

    for c in chosen:
        usage_repo.mark_paisaje_used(ponente, c["index"])
    return chosen


def release_paisajes(ponente: str, indices: list[int]) -> None:
    for idx in indices:
        usage_repo.release_paisaje_used(ponente, idx)
