"""Cliente Replicate ProPainter — magic eraser real para vídeos.

ProPainter (NeurIPS 2023, S-Lab NTU) hace video inpainting con optical flow
temporal. Reconstruye lo que había DETRÁS del objeto removido tomando
información de frames vecinos — calidad estado-del-arte para watermark
removal, mucho mejor que `delogo` que solo difumina.

Doc oficial: https://replicate.com/cjwbw/propainter/api
  Endpoint:   POST https://api.replicate.com/v1/models/cjwbw/propainter/predictions
  Files API:  POST https://api.replicate.com/v1/files (subir vídeo + máscara)
  Auth:       Authorization: Bearer {REPLICATE_API_TOKEN}

Pricing (verificado en replicate.com/cjwbw/propainter):
  - Hardware: Nvidia A40 ($0.000725/sec)
  - Velocidad: ~2× realtime (clip de 10s → ~20s GPU)
  - Coste típico 10s clip 720×1280: ~$0.015
  - Coste 30s clip:                 ~$0.045
  Mucho más barato que LaMa per-frame (~$0.20/10s) o fal video-inpainting
  (~$0.10+).

Modelo configurable via env `REPLICATE_PROPAINTER_MODEL` (default
"cjwbw/propainter") por si necesitamos cambiar a `zsxkib/propainter` u
otro fork futuro.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests


REPLICATE_API_URL = "https://api.replicate.com/v1"
SUBMIT_TIMEOUT_S = 30
POLL_INTERVAL_S = 3.0
# ProPainter en 10s tarda 30-60s; capamos 15min para vídeos largos.
try:
    POLL_TIMEOUT_S = int(os.environ.get("REPLICATE_PROPAINTER_TIMEOUT_S", "900"))
except ValueError:
    POLL_TIMEOUT_S = 900

PROPAINTER_MODEL = os.environ.get(
    "REPLICATE_PROPAINTER_MODEL", "jd7h/propainter",
)
# Cache de version hash del modelo (Replicate community models requieren
# version explícita en /predictions). Fetcheamos on-demand y cacheamos.
_VERSION_CACHE: dict[str, str] = {}

UPLOAD_TIMEOUT_S = 300  # vídeos pueden ser hasta 200MB


class ReplicateProPainterError(RuntimeError):
    """Error NO retryable (401, 402, payload inválido)."""
    def __init__(self, message: str, *, status_code: int | None = None, kind: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind


class ReplicateProPainterTransient(RuntimeError):
    """Error transitorio (timeout/5xx)."""


@dataclass
class ProPainterJob:
    prediction_id: str
    status: str = "starting"
    output_url: str | None = None
    error: str | None = None
    gpu_seconds: float | None = None


def _api_token() -> str:
    return os.environ.get("REPLICATE_API_TOKEN", "").strip()


def replicate_propainter_is_configured() -> bool:
    return bool(_api_token())


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_token()}",
        "Content-Type": "application/json",
    }


def _files_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_token()}"}


def upload_file(path: str) -> str:
    """Sube un archivo a Replicate Files API y devuelve la URL pública
    temporal (24h). Necesario porque ProPainter no acepta data:base64 en
    inputs por el tamaño del vídeo."""
    p = Path(path)
    if not p.is_file():
        raise ReplicateProPainterError(f"Archivo no existe: {path}")
    url = f"{REPLICATE_API_URL}/files"
    with open(p, "rb") as fh:
        try:
            r = requests.post(
                url, headers=_files_headers(),
                files={"content": (p.name, fh, _guess_mime(p.suffix))},
                timeout=UPLOAD_TIMEOUT_S,
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            raise ReplicateProPainterTransient(f"upload Replicate: {e}")
    if r.status_code in (401, 403):
        raise ReplicateProPainterError(
            "Replicate API token inválido (401)",
            status_code=r.status_code, kind="auth",
        )
    if r.status_code >= 400:
        raise ReplicateProPainterError(
            f"Replicate upload HTTP {r.status_code}: {r.text[:300]}",
            status_code=r.status_code, kind="upload_failed",
        )
    try:
        data = r.json()
    except ValueError:
        raise ReplicateProPainterError("Replicate upload respuesta no-JSON")
    file_url = data.get("urls", {}).get("get") or data.get("url")
    if not file_url:
        raise ReplicateProPainterError(
            f"Replicate upload sin URL: {data}",
        )
    return file_url


def _guess_mime(suffix: str) -> str:
    s = suffix.lower().lstrip(".")
    return {
        "mp4": "video/mp4",
        "mov": "video/quicktime",
        "mkv": "video/x-matroska",
        "webm": "video/webm",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }.get(s, "application/octet-stream")


def _fetch_latest_version(model_slug: str) -> str:
    """Obtiene el hash de la última versión del modelo. Cachea para
    no consultar en cada submit. Community models REQUIEREN version
    hash al crear predictions (a diferencia de modelos oficiales)."""
    cached = _VERSION_CACHE.get(model_slug)
    if cached:
        return cached
    url = f"{REPLICATE_API_URL}/models/{model_slug}"
    try:
        r = requests.get(url, headers=_headers(), timeout=SUBMIT_TIMEOUT_S)
    except (requests.Timeout, requests.ConnectionError) as e:
        raise ReplicateProPainterTransient(f"fetch version network: {e}")
    if r.status_code == 404:
        raise ReplicateProPainterError(
            f"Modelo '{model_slug}' no existe en Replicate. Verifica el "
            f"slug — prueba 'zsxkib/propainter' o configura "
            f"REPLICATE_PROPAINTER_MODEL en .env del VPS.",
            status_code=404, kind="model_not_found",
        )
    if r.status_code in (401, 403):
        raise ReplicateProPainterError(
            f"Replicate auth fallo al fetch model ({r.status_code})",
            status_code=r.status_code, kind="auth",
        )
    if r.status_code >= 400:
        raise ReplicateProPainterError(
            f"Replicate fetch model {r.status_code}: {r.text[:300]}",
            status_code=r.status_code, kind="invalid_request",
        )
    data = r.json()
    version = (data.get("latest_version") or {}).get("id")
    if not version:
        raise ReplicateProPainterError(
            f"Modelo '{model_slug}' sin latest_version — posiblemente sin "
            f"build publicado."
        )
    _VERSION_CACHE[model_slug] = version
    return version


def submit_propainter(
    *,
    video_url: str,
    mask_url: str,
    mask_dilation: int = 4,
    neighbor_length: int = 10,
    ref_stride: int = 10,
    resize_ratio: float = 1.0,
    fp16: bool = True,
    subvideo_length: int = 80,
) -> ProPainterJob:
    """Crea una prediction ProPainter. Devuelve job con prediction_id.

    Params (defaults seguros para watermark removal en GPU A40 40GB):
      - mask_dilation: cuánto expandir la máscara (4px = padding seguro)
      - neighbor_length: frames vecinos para coherencia temporal (5 =
        equilibrio entre calidad y VRAM — antes 10 daba CUDA OOM)
      - ref_stride: stride para frames de referencia (10 = balance)
      - resize_ratio: 1.0 mantiene resolución original
      - fp16: True usa float16 (halva VRAM, calidad casi idéntica)
      - subvideo_length: procesa en chunks de N frames (40 = stable
        para 720p; ProPainter por defecto 80 y suele dar OOM con
        masks complejas en 1080p o vídeos >10s).
    """
    # Community models en Replicate requieren version hash explícita.
    # /v1/models/{owner}/{name}/predictions solo funciona para modelos
    # OFICIALES (los publicados por @replicate). Para community usamos
    # /v1/predictions con `version` field.
    version = _fetch_latest_version(PROPAINTER_MODEL)
    payload = {
        "version": version,
        "input": {
            "video": video_url,
            "mask": mask_url,
            "mask_dilation": mask_dilation,
            "neighbor_length": neighbor_length,
            "ref_stride": ref_stride,
            "resize_ratio": resize_ratio,
            "fp16": fp16,
            "subvideo_length": subvideo_length,
        }
    }
    url = f"{REPLICATE_API_URL}/predictions"
    # Replicate limita a 6 req/min (ráfaga 1) si la cuenta tiene <$5 de
    # crédito. Reintentamos el 429 esperando el `retry-after` (o ~12s) en
    # vez de fallar — así la cola procesa los vídeos en serie, más lento
    # pero sin perder ninguno. SOLUCIÓN REAL: recargar ≥$5 en Replicate.
    _MAX_429_RETRIES = 8
    r = None
    for attempt in range(_MAX_429_RETRIES + 1):
        try:
            r = requests.post(
                url, headers=_headers(), json=payload, timeout=SUBMIT_TIMEOUT_S,
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            raise ReplicateProPainterTransient(f"submit network: {e}")
        if r.status_code != 429:
            break
        if attempt >= _MAX_429_RETRIES:
            raise ReplicateProPainterTransient(
                f"submit HTTP 429 tras {_MAX_429_RETRIES} reintentos "
                f"(¿cuenta Replicate con <$5 de crédito?): {r.text[:150]}"
            )
        wait_s = _retry_after_seconds(r) or 12
        time.sleep(min(wait_s, 30))
    if r.status_code == 401:
        raise ReplicateProPainterError(
            "Replicate token inválido (401)",
            status_code=401, kind="auth",
        )
    if r.status_code == 402:
        raise ReplicateProPainterError(
            "Replicate sin saldo (402)",
            status_code=402, kind="credits",
        )
    if r.status_code == 422:
        raise ReplicateProPainterError(
            f"ProPainter validation: {r.text[:300]}",
            status_code=422, kind="invalid_request",
        )
    if r.status_code >= 500:
        raise ReplicateProPainterTransient(
            f"submit HTTP {r.status_code}: {r.text[:200]}"
        )
    if r.status_code >= 400:
        raise ReplicateProPainterError(
            f"ProPainter submit bad request {r.status_code}: {r.text[:300]}",
            status_code=r.status_code, kind="invalid_request",
        )
    data = r.json()
    return ProPainterJob(
        prediction_id=data["id"],
        status=data.get("status", "starting"),
    )


def _retry_after_seconds(resp: "requests.Response") -> float | None:
    """Lee el header Retry-After (segundos) de una respuesta 429. None si
    no viene o no es parseable."""
    val = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    if not val:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def poll(job: ProPainterJob) -> ProPainterJob:
    url = f"{REPLICATE_API_URL}/predictions/{job.prediction_id}"
    try:
        r = requests.get(url, headers=_headers(), timeout=15)
    except (requests.Timeout, requests.ConnectionError) as e:
        raise ReplicateProPainterTransient(f"poll network: {e}")
    if r.status_code in (401, 403):
        raise ReplicateProPainterError(
            "Replicate auth expirada durante poll",
            status_code=r.status_code, kind="auth",
        )
    if r.status_code >= 500:
        raise ReplicateProPainterTransient(f"poll HTTP {r.status_code}")
    if r.status_code >= 400:
        raise ReplicateProPainterError(
            f"poll error {r.status_code}: {r.text[:200]}",
            status_code=r.status_code, kind="poll_failed",
        )
    data = r.json()
    job.status = data.get("status", job.status)
    if job.status == "succeeded":
        out = data.get("output")
        if isinstance(out, list) and out:
            job.output_url = out[0]
        elif isinstance(out, str):
            job.output_url = out
        # Métricas opcionales (Replicate las incluye en `metrics.predict_time`)
        metrics = data.get("metrics") or {}
        predict_time = metrics.get("predict_time")
        if isinstance(predict_time, (int, float)):
            job.gpu_seconds = float(predict_time)
    elif job.status in ("failed", "canceled"):
        job.error = data.get("error") or job.status
    return job


def wait(
    job: ProPainterJob,
    *,
    timeout_s: int = POLL_TIMEOUT_S,
    poll_interval: float = POLL_INTERVAL_S,
    on_heartbeat: Callable[[int, str], None] | None = None,
) -> ProPainterJob:
    started = time.time()
    deadline = started + timeout_s
    last_log = started
    while time.time() < deadline:
        try:
            poll(job)
        except ReplicateProPainterTransient as e:
            print(f"[propainter poll] transient: {e}")
            time.sleep(poll_interval)
            continue
        if job.status == "succeeded":
            return job
        if job.status in ("failed", "canceled"):
            raise ReplicateProPainterError(
                f"ProPainter {job.prediction_id} {job.status}: "
                f"{job.error or 'unknown'}",
                kind="model_failed",
            )
        now = time.time()
        if now - last_log >= 30:
            elapsed = int(now - started)
            print(
                f"[propainter] {job.prediction_id[:8]} status={job.status} "
                f"elapsed={elapsed}s timeout={timeout_s}s"
            )
            if on_heartbeat:
                try:
                    on_heartbeat(elapsed, job.status)
                except Exception:
                    pass
            last_log = now
        time.sleep(poll_interval)
    # Timeout — cancel best-effort
    try:
        cancel(job)
    except Exception:
        pass
    raise ReplicateProPainterTransient(
        f"ProPainter {job.prediction_id} no terminó en {timeout_s//60}min"
    )


def cancel(job: ProPainterJob) -> None:
    url = f"{REPLICATE_API_URL}/predictions/{job.prediction_id}/cancel"
    try:
        requests.post(url, headers=_headers(), timeout=10)
    except Exception:
        pass


def download(output_url: str, dest_path: str) -> str:
    if not output_url:
        raise ReplicateProPainterError("download: output_url vacío")
    try:
        r = requests.get(output_url, timeout=300, stream=True)
    except (requests.Timeout, requests.ConnectionError) as e:
        raise ReplicateProPainterTransient(f"download network: {e}")
    if r.status_code >= 400:
        raise ReplicateProPainterTransient(f"download HTTP {r.status_code}")
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)) or ".", exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(64 * 1024):
            if chunk:
                f.write(chunk)
    return dest_path
