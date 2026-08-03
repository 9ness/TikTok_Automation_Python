"""Asigna candidatos de gancho/paisaje SIN repetir nunca (por ponente),
combinando el banco de candidatos (`pipeline/resource_scanner.py`) con el
tracking de uso persistente en Redis (`repos/usage_repo.py`).

Los índices se marcan como usados en Redis EN CUANTO se asignan (antes de
que termine el render) — si el render falla después, el caller debe llamar
a `release_hook/release_paisajes` para no perder el hueco definitivamente.
"""

from __future__ import annotations

import random

from src.viralizacion import config

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
    """Devuelve (disponibles, total) de candidatos de paisaje para `ponente`.

    El pool es compartido entre ponentes DEL MISMO PAÍS, pero el uso se
    rastrea por separado — por eso el resultado es específico de `ponente`.
    España y Estados Unidos tienen bibliotecas distintas: con una sola, los
    vídeos de Billy Graham saldrían con paisajes de España.

    `cache_only=True` (UI): no trocea el vídeo — solo lee JSON cache.
    """
    pais = config.pais_de(ponente)
    candidates = (
        load_paisaje_candidates_cached(pais)
        if cache_only
        else scan_paisaje_candidates(pais)
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

    # Ciclo nuevo al agotarse, igual que con los paisajes: el gancho se
    # reencuadra con un zoom aleatorio distinto y acompaña a otro audio, otros
    # subtítulos y otro estilo, así que reutilizarlo NO produce el mismo vídeo.
    # Sin esto la generación se bloqueaba al llegar al nº de ganchos del banco.
    if not available:
        if not candidates:
            raise PoolExhaustedError(
                f"No hay ningún candidato de gancho para '{ponente}'."
            )
        usage_repo.reset_hook_used(ponente)
        available = list(candidates)

    # Al azar, no `available[0]`: si no, dos tandas seguidas empiezan por el
    # mismo gancho.
    chosen = random.choice(available)
    usage_repo.mark_hook_used(ponente, chosen["index"])
    return chosen


def release_hook(ponente: str, index: int) -> None:
    usage_repo.release_hook_used(ponente, index)


def allocate_paisaje_clips(ponente: str, n: int, min_total_dur: float = 0.0) -> list[dict]:
    """Asigna `n` clips de la biblioteca, uno por LUGAR distinto.

    Cada clip es un plano entero del original, así que el sitio no cambia a
    mitad de clip. Se elige una ventana aleatoria dentro de cada uno para que
    el mismo clip nunca salga con el mismo encuadre temporal.

    Los clips agrupados en el mismo `location` (mismo sitio desde otro ángulo)
    no se mezclan dentro del mismo vídeo: sería volver al bug de "transición
    pero mismo lugar".
    """
    clips = clip_library.all_clips(config.pais_de(ponente))
    if not clips:
        raise PoolExhaustedError(
            "La biblioteca de clips de paisaje está vacía. Genera los clips "
            "antes de renderizar (ver VIRALIZACION_MODULE.md)."
        )
    def _usable(c: dict) -> float:
        """Material aprovechable del clip: hay que reservar el solape de la
        transición, que el renderer extrae por fuera de la ventana."""
        return max(0.0, float(c.get("dur") or 0.0) - config.CLIP_TRANSITION_PAD_S)

    used = usage_repo.get_used_paisaje_indices(ponente)
    available = [c for c in clips if c["index"] not in used]

    # Ciclo nuevo: cuando se agota la vuelta, se reinicia el marcador en vez
    # de bloquear la generación. NO es repetir material tal cual — de cada
    # clip se saca una ventana temporal distinta y un zoom distinto, así que
    # el vídeo resultante no coincide con el de la vuelta anterior. Es lo que
    # permite seguir generando indefinidamente con un banco finito.
    #
    # Se mira el nº de clips Y LOS SEGUNDOS que suman: mirando solo el número
    # quedaban vueltas con clips de sobra pero cortos (24 clips = 48,9s) para
    # un vídeo que pedía 63s, y el ciclo no se reiniciaba — el lote moría con
    # PoolExhaustedError teniendo la biblioteca entera sin usar.
    quedan_segundos = sum(_usable(c) for c in available)
    if len(available) < n or quedan_segundos < min_total_dur:
        total_segundos = sum(_usable(c) for c in clips)
        if len(clips) < n or total_segundos < min_total_dur:
            raise PoolExhaustedError(
                f"La biblioteca tiene {len(clips)} clips con {total_segundos:.0f}s "
                f"útiles, pero un vídeo pide {n} clips y {min_total_dur:.0f}s. "
                f"Añade más material de paisaje."
            )
        usage_repo.reset_paisaje_used(ponente)
        available = list(clips)

    random.shuffle(available)

    def _enough(sel: list[dict]) -> bool:
        """`n` clips Y material suficiente.

        Los planos duran lo que duran (3,3s a 17s), así que `n` calculado a
        4,5s/clip se queda corto con los planos cortos. Se siguen añadiendo
        clips hasta cubrir la duración pedida.
        """
        if len(sel) < n:
            return False
        return sum(_usable(c) for c in sel) >= min_total_dur

    def _elegir(pool: list[dict]) -> list[dict]:
        """Un clip por LUGAR distinto hasta cubrir la duración (no mezclar el
        mismo sitio desde otro ángulo dentro de un vídeo)."""
        sel: list[dict] = []
        locs: set = set()
        for c in pool:
            if _enough(sel):
                break
            loc = c.get("location", c["index"])
            if loc in locs:
                continue
            locs.add(loc)
            sel.append(c)
        return sel

    chosen = _elegir(available)

    # Si el sorteo pide demasiados tramos, se rehace priorizando los planos
    # MÁS LARGOS. El renderer encadena todos los tramos en un solo `xfade`
    # con un input por clip: con 19 decodificadores de 1080x1920 abiertos a
    # la vez, ffmpeg murió por OOM (SIGKILL) en el VPS de 8 GB. Con planos
    # largos hacen falta muchos menos para los mismos segundos.
    if len(chosen) > config.MAX_PAISAJE_CLIPS:
        largos = _elegir(sorted(available, key=_usable, reverse=True))
        if largos and len(largos) < len(chosen):
            chosen = largos

    # Última pasada si aún falta material: mejor repetir lugar que fallar.
    if not _enough(chosen):
        for c in sorted(available, key=_usable, reverse=True):
            if c in chosen:
                continue
            chosen.append(c)
            if _enough(chosen):
                break

    if not _enough(chosen):
        raise PoolExhaustedError(
            f"Los {len(chosen)} clips disponibles para {ponente!r} dan "
            f"{sum(_usable(c) for c in chosen):.1f}s útiles pero hacen "
            f"falta {min_total_dur:.1f}s."
        )

    out: list[dict] = []
    for c in chosen:
        usage_repo.mark_paisaje_used(ponente, c["index"])
        out.append({
            "index": c["index"],
            "path": str(clip_library.clip_path(c, config.pais_de(ponente))),
            # Duración COMPLETA del plano: es el tope real. El renderer decide
            # cuánto usa de cada uno y sortea el desplazamiento dentro.
            "dur": float(c.get("dur") or 0.0),
        })
    return out


def allocate_paisaje_segments(ponente: str, n: int) -> list[dict]:
    """Asigna (y marca como usados) `n` candidatos de paisaje no usados por
    `ponente`. Lanza `PoolExhaustedError` con el déficit exacto si no hay
    suficientes."""
    candidates = scan_paisaje_candidates(config.pais_de(ponente))
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
