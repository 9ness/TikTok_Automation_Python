"""Cliente Replicate — provider adicional para chain musical TikTok Shop.

Replicate hostea Hailuo 02 oficial (minimax/hailuo-02) en su propia
infraestructura GPU — independiente de fal.ai y Runware. Cuando fal está
saturado globalmente (jobs IN_QUEUE indefinidos) Replicate puede correr.

Pricing oficial Hailuo 02 en Replicate (2026):
  - 6s 768p:  $0.27 por prediction
  - 10s 768p: $0.45 por prediction
  - 1080p:    +60% aprox (usamos 768p siempre — TikTok-ready y barato)

Modelo de cobro: Replicate cobra por GPU-second. Para modelos oficiales
(minimax/hailuo-02 es oficial) el precio es flat por prediction. Jobs que
fallan ANTES de empezar a correr no cobran. Jobs que arrancan pero
fallan en runtime SÍ cobran los segundos consumidos. Mejor que fal (que
cobra al encolar) pero peor que Runware (que solo cobra al completar).

Doc oficial: https://replicate.com/minimax/hailuo-02/api
  Endpoint:  POST https://api.replicate.com/v1/models/minimax/hailuo-02/predictions
  Auth:      Authorization: Bearer {REPLICATE_API_TOKEN}
  Polling:   GET https://api.replicate.com/v1/predictions/{id}
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests


REPLICATE_API_URL = "https://api.replicate.com/v1"
SUBMIT_TIMEOUT_S = 30
POLL_INTERVAL_S = 3.0
# Hailuo 02 normalmente tarda 1-3 min, picos hasta 8min.
try:
    POLL_TIMEOUT_S = int(os.environ.get("REPLICATE_POLL_TIMEOUT_S", "900"))
except ValueError:
    POLL_TIMEOUT_S = 900
MAX_RETRIES_TRANSIENT = 3


# Modelos oficiales Replicate — slugs `owner/name` para el endpoint
# /models/{owner}/{name}/predictions (no requiere version hash).
HAILUO_02_MODEL = "minimax/hailuo-02"

MUSIC_RENDERER_LABELS_REPLICATE: dict[str, str] = {
    HAILUO_02_MODEL: "Hailuo 02 (Replicate)",
}


class ReplicateError(RuntimeError):
    """Error Replicate NO retryable (401, 402, mal request)."""
    def __init__(self, message: str, *, status_code: int | None = None, kind: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind


class ReplicateTransient(RuntimeError):
    """Error transitorio (timeout/5xx/cola atascada)."""


@dataclass
class ReplicateJob:
    prediction_id: str
    status: str = "starting"   # starting | processing | succeeded | failed | canceled
    output_url: str | None = None
    error: str | None = None
    model_slug: str = ""


def replicate_is_configured() -> bool:
    return bool(os.environ.get("REPLICATE_API_TOKEN", "").strip())


def replicate_api_token() -> str:
    return os.environ.get("REPLICATE_API_TOKEN", "").strip()


def _photo_to_data_url(image_path_or_url: str) -> str:
    """Convierte un path local a data: base64 inline, o devuelve URL/data:
    tal cual. Replicate acepta ambos en `first_frame_image`."""
    if image_path_or_url.startswith(("http://", "https://", "data:")):
        return image_path_or_url
    p = Path(image_path_or_url)
    if not p.is_file():
        raise ReplicateError(f"Foto no encontrada: {image_path_or_url}")
    suffix = p.suffix.lower().lstrip(".") or "jpeg"
    if suffix == "jpg":
        suffix = "jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/{suffix};base64,{b64}"


class ReplicateClient:
    def __init__(self) -> None:
        self.api_token = replicate_api_token()
        self.base_url = REPLICATE_API_URL

    def is_available(self) -> bool:
        return replicate_is_configured()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def healthcheck(self, *, timeout_s: float = 8.0) -> tuple[bool, str]:
        """Pre-flight: confirma API token válido sin gastar créditos.
        GET /account devuelve datos del usuario si auth OK."""
        if not self.api_token:
            return False, "REPLICATE_API_TOKEN no configurada"
        try:
            r = requests.get(
                f"{self.base_url}/account", headers=self._headers(),
                timeout=timeout_s,
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            return False, f"replicate no responde — {str(e)[:120]}"
        if r.status_code in (401, 403):
            return False, "Replicate API token inválido o expirado"
        if r.status_code == 402:
            return False, "Replicate sin saldo — recarga"
        if r.status_code >= 400:
            return False, f"Replicate health HTTP {r.status_code}"
        return True, "Replicate OK"

    # ----------------------------------------------------------------
    # SUBMIT — Hailuo 02 i2v
    # ----------------------------------------------------------------
    def submit_hailuo02_i2v(
        self,
        *,
        image_ref: str,
        prompt: str,
        duration_s: int = 6,
        resolution: str = "768p",
        prompt_optimizer: bool = True,
    ) -> ReplicateJob:
        """Encola un job i2v con Hailuo 02 oficial en Replicate.

        Soporta 9:16 vertical, durations 6 o 10s, resoluciones 512p/768p/1080p.
        768p es el sweet spot (TikTok-ready, $0.27/6s).

        Schema (https://replicate.com/minimax/hailuo-02/api):
          - prompt:            string
          - first_frame_image: URL HTTPS o data:base64
          - duration:          6 | 10
          - resolution:        "512p" | "768p" | "1080p"
          - prompt_optimizer:  bool (default true — mejora calidad)
        """
        if duration_s not in (6, 10):
            duration_s = 6 if duration_s <= 7 else 10
        if resolution not in ("512p", "768p", "1080p"):
            resolution = "768p"
        first_frame = _photo_to_data_url(image_ref)
        payload = {
            "input": {
                "prompt": prompt,
                "first_frame_image": first_frame,
                "duration": duration_s,
                "resolution": resolution,
                "prompt_optimizer": prompt_optimizer,
            }
        }
        # Endpoint específico para modelo oficial — sin version hash.
        url = f"{self.base_url}/models/{HAILUO_02_MODEL}/predictions"
        data = self._post_with_retry(url, payload)
        return ReplicateJob(
            prediction_id=data["id"],
            status=data.get("status", "starting"),
            model_slug=HAILUO_02_MODEL,
        )

    def _post_with_retry(self, url: str, payload: dict) -> dict:
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES_TRANSIENT):
            try:
                r = requests.post(
                    url, headers=self._headers(), json=payload,
                    timeout=SUBMIT_TIMEOUT_S,
                )
            except (requests.Timeout, requests.ConnectionError) as e:
                last_exc = e
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code == 401:
                raise ReplicateError(
                    "Replicate API token inválido (401)",
                    status_code=401, kind="auth",
                )
            if r.status_code == 402:
                raise ReplicateError(
                    "Replicate sin saldo (402)",
                    status_code=402, kind="credits",
                )
            if r.status_code == 422:
                # Validation error — datos malformados, NO retry
                raise ReplicateError(
                    f"Replicate validation error: {r.text[:300]}",
                    status_code=422, kind="invalid_request",
                )
            if r.status_code in (429,) or r.status_code >= 500:
                last_exc = ReplicateTransient(f"HTTP {r.status_code}: {r.text[:200]}")
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code >= 400:
                raise ReplicateError(
                    f"Replicate bad request {r.status_code}: {r.text[:300]}",
                    status_code=r.status_code, kind="invalid_request",
                )
            try:
                return r.json()
            except ValueError as e:
                raise ReplicateError(
                    f"Replicate respuesta no-JSON: {e}",
                    kind="invalid_response",
                )
        raise ReplicateTransient(
            f"Replicate submit falló tras {MAX_RETRIES_TRANSIENT} intentos: {last_exc}"
        )

    # ----------------------------------------------------------------
    # POLL
    # ----------------------------------------------------------------
    def poll(self, job: ReplicateJob) -> ReplicateJob:
        """Consulta status del prediction. Actualiza job y lo devuelve."""
        url = f"{self.base_url}/predictions/{job.prediction_id}"
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
        except (requests.Timeout, requests.ConnectionError) as e:
            raise ReplicateTransient(f"replicate poll network: {e}")
        if r.status_code in (401, 403):
            raise ReplicateError(
                "Replicate auth expirada durante poll",
                status_code=r.status_code, kind="auth",
            )
        if r.status_code == 404:
            raise ReplicateError(
                f"Prediction {job.prediction_id} no existe (404)",
                status_code=404, kind="not_found",
            )
        if r.status_code >= 500:
            raise ReplicateTransient(f"replicate poll HTTP {r.status_code}")
        if r.status_code >= 400:
            raise ReplicateError(
                f"replicate poll error {r.status_code}: {r.text[:200]}",
                status_code=r.status_code, kind="poll_failed",
            )
        try:
            data = r.json()
        except ValueError:
            raise ReplicateTransient("replicate poll no-JSON")
        job.status = data.get("status", job.status)
        if job.status == "succeeded":
            # output puede ser string (URL) o lista
            out = data.get("output")
            if isinstance(out, list) and out:
                job.output_url = out[0]
            elif isinstance(out, str):
                job.output_url = out
        elif job.status in ("failed", "canceled"):
            job.error = data.get("error") or job.status
        return job

    def wait(
        self,
        job: ReplicateJob,
        *,
        timeout_s: int = POLL_TIMEOUT_S,
        poll_interval: float = POLL_INTERVAL_S,
        on_heartbeat: Callable[[int, str], None] | None = None,
    ) -> ReplicateJob:
        """Polling hasta status terminal."""
        started = time.time()
        deadline = started + timeout_s
        last_log_t = started
        while time.time() < deadline:
            try:
                self.poll(job)
            except ReplicateTransient as e:
                print(f"[replicate poll] transient: {e}, retry…")
                time.sleep(poll_interval)
                continue
            if job.status == "succeeded":
                return job
            if job.status in ("failed", "canceled"):
                raise ReplicateError(
                    f"Replicate prediction {job.prediction_id} {job.status}: "
                    f"{job.error or 'unknown'}",
                    kind="model_failed",
                )
            now = time.time()
            if now - last_log_t >= 60:
                elapsed = int(now - started)
                print(
                    f"[replicate poll] {job.prediction_id[:8]} status={job.status} "
                    f"elapsed={elapsed}s timeout={timeout_s}s"
                )
                if on_heartbeat is not None:
                    try:
                        on_heartbeat(elapsed, job.status)
                    except Exception:
                        pass
                last_log_t = now
            time.sleep(poll_interval)
        # Timeout — intentar cancel best-effort para no seguir gastando GPU-s
        try:
            self.cancel(job)
        except Exception:
            pass
        raise ReplicateTransient(
            f"Replicate prediction {job.prediction_id} no terminó en "
            f"{timeout_s//60}min (último status: {job.status})."
        )

    def cancel(self, job: ReplicateJob) -> None:
        """Best-effort cancel para no gastar GPU-seconds en timeouts."""
        url = f"{self.base_url}/predictions/{job.prediction_id}/cancel"
        try:
            requests.post(url, headers=self._headers(), timeout=10)
        except Exception:
            pass

    # ----------------------------------------------------------------
    # DOWNLOAD
    # ----------------------------------------------------------------
    def download(self, output_url: str, dest_path: str) -> str:
        """Descarga el MP4 a `dest_path`."""
        if not output_url:
            raise ReplicateError("download: output_url vacío")
        try:
            r = requests.get(output_url, timeout=120, stream=True)
        except (requests.Timeout, requests.ConnectionError) as e:
            raise ReplicateTransient(f"replicate download fallo de red: {e}")
        if r.status_code >= 400:
            raise ReplicateTransient(f"replicate download HTTP {r.status_code}")
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)) or ".", exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(64 * 1024):
                if chunk:
                    f.write(chunk)
        return dest_path
