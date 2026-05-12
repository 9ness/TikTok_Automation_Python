"""Métricas de duración de jobs para ETA inteligente.

Cada job que termina con éxito deposita un sample
`(dimension_opcional, elapsed_seconds)` en una lista Redis indexada por
`(mode, bucket)`. Cuando un job está corriendo, predecimos su duración
total combinando:

  1. ETA self-based (`elapsed / progress`) — fiable solo a partir de ~15%.
  2. ETA histórico = media de `elapsed/dim` × `dim_actual` (si el modo
     define una dimension escalar significativa, p. ej. duración del audio
     para subs_auto). Si no hay dimension, se usa la media de elapsed.

`smart_eta_seconds()` hace el blend ponderado por progreso: a poca
progresión confiamos en el histórico, a mucha en el self-based. Esto evita
el "ETA absurdo" típico de los primeros segundos y a la vez se ajusta
finamente al final.

Las claves Redis viven bajo el prefijo de `ShopRedis` (`tiktok_shop:`) en
`metrics:duration:{mode}[:{bucket}]`. Cada lista está capada a 50 samples
con LTRIM tras cada lpush.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

from src.queue.models import Job, JobMode, JobStatus


_MAX_SAMPLES = 50
# Cache ffprobe por path absoluto: una sola llamada por archivo durante
# toda la vida del worker. Los inputs son inmutables (snapshots en disco).
_FFPROBE_CACHE: dict[str, float] = {}
# Cache de predicción por job_id: evita golpear Redis en cada tick del WS
# (1Hz). Se invalida automáticamente al desaparecer el job de la cola.
_PREDICTION_CACHE: dict[str, float | None] = {}


def _video_duration(path: str | None) -> float | None:
    """Devuelve la duración del archivo via ffprobe (cacheado). None si falla."""
    if not path or not os.path.exists(path):
        return None
    if path in _FFPROBE_CACHE:
        return _FFPROBE_CACHE[path]
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            timeout=10,
            stderr=subprocess.DEVNULL,
        )
        v = float(out.strip())
        _FFPROBE_CACHE[path] = v
        return v
    except Exception:
        return None


def _bucket_signature(job: Job) -> tuple[str, float | None]:
    """Devuelve (sufijo_bucket, dimension_opcional) para indexar y escalar."""
    mode = job.mode
    p = job.params or {}
    if mode == JobMode.SUBS_AUTO:
        model = str(p.get("model_size", "small"))
        return (f"m={model}", _video_duration(p.get("input_path")))
    if mode == JobMode.COPYRIGHT:
        clean_mode = "cam" if "Camuflaje" in str(p.get("clean_mode", "")) else "subs"
        upscale = ",up" if p.get("upscale_1080p") else ""
        return (f"c={clean_mode}{upscale}", _video_duration(p.get("input_path")))
    if mode == JobMode.TIKTOK_SHOP:
        tier = str(p.get("tier", "")) or "default"
        return (f"t={tier}", None)
    if mode == JobMode.PRONOSTICOS_DIARIOS:
        return ("", None)
    if mode == JobMode.PRESIDENTS_TOP5:
        n = p.get("num_presidents", 5)
        return (f"n={n}", None)
    return ("", None)


def _key(mode: JobMode, bucket_suffix: str) -> str:
    base = f"metrics:duration:{mode.value}"
    return f"{base}:{bucket_suffix}" if bucket_suffix else base


def _get_redis():
    try:
        from src.tiktok_shop.repos.redis_base import get_shop_redis
        r = get_shop_redis()
        return r if r.is_available() else None
    except Exception:
        return None


def record_job_metric(job: Job) -> None:
    """Persiste el sample del job recién finalizado. Solo guarda runs
    COMPLETED (fallidos/cancelados no son señal útil)."""
    if job.status != JobStatus.COMPLETED:
        return
    elapsed = job.elapsed_s
    if elapsed < 5:  # demasiado corto para ser señal fiable
        return
    redis = _get_redis()
    if redis is None:
        return
    bucket, dim = _bucket_signature(job)
    key = _key(job.mode, bucket)
    sample = {"dim": dim, "elapsed": round(elapsed, 2), "ts": time.time()}
    try:
        redis.lpush(key, json.dumps(sample, ensure_ascii=False))
        redis.ltrim(key, 0, _MAX_SAMPLES - 1)
    except Exception as e:
        print(f"[metrics] lpush/ltrim {key} fallo: {e}")


def _load_samples(redis, key: str) -> list[dict[str, Any]]:
    raw = redis.lrange(key, 0, _MAX_SAMPLES - 1)
    out = []
    for s in raw or []:
        try:
            out.append(json.loads(s) if isinstance(s, str) else s)
        except Exception:
            continue
    return out


def predict_total_seconds(job: Job) -> float | None:
    """Estima duración total del job vía histórico Redis (cacheado por job_id)."""
    cached = _PREDICTION_CACHE.get(job.id)
    if cached is not None or job.id in _PREDICTION_CACHE:
        return cached
    redis = _get_redis()
    if redis is None:
        _PREDICTION_CACHE[job.id] = None
        return None
    bucket, dim = _bucket_signature(job)
    key = _key(job.mode, bucket)
    samples = _load_samples(redis, key)
    if not samples:
        # Fallback: probar el bucket sin sufijo (datos generales del mode).
        if bucket:
            samples = _load_samples(redis, _key(job.mode, ""))
    if not samples:
        _PREDICTION_CACHE[job.id] = None
        return None

    pred: float | None = None
    if dim and dim > 0:
        ratios = [s["elapsed"] / s["dim"] for s in samples if (s.get("dim") or 0) > 0]
        if ratios:
            avg = sum(ratios) / len(ratios)
            pred = avg * dim
    if pred is None:
        elapsed_vals = [s["elapsed"] for s in samples if "elapsed" in s]
        if elapsed_vals:
            pred = sum(elapsed_vals) / len(elapsed_vals)
    _PREDICTION_CACHE[job.id] = pred
    return pred


def smart_eta_seconds(job: Job) -> float | None:
    """ETA inteligente: blend self-based + histórico ponderado por progreso.

    - progress=0:      100% histórico
    - progress=0.5:    100% self-based (siempre que progress haya sido >0.05)
    - intermedio:      blend lineal
    """
    if job.status != JobStatus.RUNNING:
        return None
    elapsed = job.elapsed_s
    if elapsed <= 0:
        return None

    # Self-based: necesita un mínimo de progreso para no ser ruido absoluto.
    self_eta: float | None = None
    if job.progress > 0.05:
        total_est = elapsed / job.progress
        self_eta = max(0.0, total_est - elapsed)

    # Histórico
    pred_total = predict_total_seconds(job)
    hist_eta: float | None = None
    if pred_total is not None and pred_total > 0:
        hist_eta = max(0.0, pred_total - elapsed)

    if self_eta is None and hist_eta is None:
        return None
    if self_eta is None:
        return hist_eta
    if hist_eta is None:
        # Sin histórico: usar self-based solo si ya es mínimamente fiable.
        return self_eta if job.progress >= 0.15 else None

    # Blend lineal: weight_self pasa de 0 a 1 entre progress 0.05 y 0.50.
    w_self = max(0.0, min(1.0, (job.progress - 0.05) / 0.45))
    return w_self * self_eta + (1 - w_self) * hist_eta


def forget_prediction(job_id: str) -> None:
    """Limpia la cache de predicción cuando el job desaparece de la cola."""
    _PREDICTION_CACHE.pop(job_id, None)
