"""Cliente fal.ai — provider universal para vídeo i2v.

Soporta dos familias de modelos:
1. **Seedance Bytedance** (Lite + Pro) — usado en presets `kind=scripted`
   con tiers std/adv/pro. Failover de Atlas Cloud cuando se satura.
2. **MiniMax Hailuo 02 Standard** — usado en presets `kind=music`.
   Multi-shot vía clips independientes (sin necesidad de continuidad
   de personaje). $0.10 fijo por clip de 6s. Cola más ligera que
   Seedance Lite.

Doc oficial:
  Seedance: https://fal.ai/models/fal-ai/bytedance/seedance
  Hailuo:   https://fal.ai/models/fal-ai/minimax/hailuo-02/standard

  Base URL:  https://queue.fal.run
  Auth:      Authorization: Key {FAL_API_KEY}
  Submit:    POST /{model_id}              → { request_id }
  Status:    GET  /{model_id}/requests/{id}/status
  Result:    GET  /{model_id}/requests/{id}

Pricing (a 2026-05-25):
  - Seedance Lite i2v: $0.018 / seg
  - Seedance Pro  i2v: $0.062 / seg
  - Hailuo 02 Std 6s : $0.10  fijo / clip
  - Hailuo 02 Std 10s: $0.17  fijo / clip (estimado)

Acepta `image_url` en formato HTTPS público o data: base64 inline.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

import requests


FAL_BASE_URL = "https://queue.fal.run"
SUBMIT_TIMEOUT_S = 30
POLL_INTERVAL_S = 3.0
# 15min default (era 30min). Si fal.ai no arranca el job en 15min,
# la cola está muerta — fail-fast para que el user reintente luego
# en vez de esperar 30min en vano. Override con FAL_POLL_TIMEOUT_S.
try:
    POLL_TIMEOUT_S = int(os.environ.get("FAL_POLL_TIMEOUT_S", "900"))
except ValueError:
    POLL_TIMEOUT_S = 900
MAX_RETRIES_TRANSIENT = 3


# Mapeo tier → model_id en fal.ai. Lite cubre standard/advanced; Pro cubre pro.
TIER_TO_FAL_MODEL: dict[str, str] = {
    "standard": "fal-ai/bytedance/seedance/v1/lite/image-to-video",
    "advanced": "fal-ai/bytedance/seedance/v1/lite/image-to-video",
    "pro":      "fal-ai/bytedance/seedance/v1/pro/image-to-video",
}

# Hailuo 02 Standard — modelo dedicado a presets musicales (sin voz).
# Devuelve clips de 6s o 10s con camera moves TikTok-style.
HAILUO_STANDARD_MODEL_ID = "fal-ai/minimax/hailuo-02/standard/image-to-video"


class FalCloudError(RuntimeError):
    """Error fal.ai NO retryable (401, 402, mal request)."""

    def __init__(self, message: str, *, status_code: int | None = None, kind: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind


class FalCloudTransient(RuntimeError):
    """Error transitorio (timeout/5xx/queue stuck) — retry/fallback aplicable."""


@dataclass
class FalJob:
    request_id: str
    status: str = "IN_QUEUE"
    output_url: str | None = None
    error: str | None = None
    # Endpoint del modelo en fal.ai. Hace falta para polling/result
    # porque cada modelo tiene su sub-path. Si vacío, `wait()` lo
    # resuelve por tier (backwards-compat con código que no lo set).
    model_id: str = ""


def fal_is_configured() -> bool:
    return bool(os.environ.get("FAL_API_KEY", "").strip())


def fal_api_key() -> str:
    return os.environ.get("FAL_API_KEY", "").strip()


class FalCloudClient:
    def __init__(self) -> None:
        self.api_key = fal_api_key()
        self.base_url = FAL_BASE_URL.rstrip("/")

    def is_available(self) -> bool:
        return fal_is_configured()

    def _headers(self, *, content_type: bool = True) -> dict[str, str]:
        h = {"Authorization": f"Key {self.api_key}"}
        if content_type:
            h["Content-Type"] = "application/json"
        return h

    def healthcheck(self, *, timeout_s: float = 8.0) -> tuple[bool, str]:
        """Pre-flight: confirma API key válida + servicio alive."""
        if not self.api_key:
            return False, "FAL_API_KEY no configurada"
        try:
            # fal.ai no expone /health pero un GET al base devuelve 200/404.
            r = requests.get(
                self.base_url + "/",
                headers={"Authorization": f"Key {self.api_key}"},
                timeout=timeout_s,
            )
        except requests.Timeout:
            return False, f"fal.ai timeout ({timeout_s}s)"
        except requests.ConnectionError as e:
            return False, f"fal.ai no responde — {str(e)[:120]}"
        if r.status_code in (401, 403):
            return False, "fal.ai API key inválida o expirada"
        if r.status_code == 402:
            return False, "fal.ai sin saldo — recarga créditos"
        return True, f"fal.ai OK (HTTP {r.status_code})"

    # ----------------------------------------------------------------
    # SUBMIT
    # ----------------------------------------------------------------
    def submit_image_to_video(
        self,
        *,
        tier: str,
        image_url: str,
        prompt: str,
        duration: int,
        resolution: str = "720p",
        aspect_ratio: str = "9:16",
        last_image_url: str | None = None,
    ) -> FalJob:
        """Encola un job i2v Seedance en fal.ai.

        Acepta `image_url` como data: base64 o HTTPS público. Para
        consistencia con Atlas, usa el mismo helper `get_atlas_image_refs`
        del proyecto (que ya devuelve data: base64).
        """
        model_id = TIER_TO_FAL_MODEL.get(tier, TIER_TO_FAL_MODEL["standard"])
        payload: dict = {
            "prompt": prompt,
            "image_url": image_url,
            "duration": str(duration),  # fal.ai espera string "5","6",etc para Seedance
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
        }
        if last_image_url:
            payload["end_image_url"] = last_image_url

        url = f"{self.base_url}/{model_id}"
        payload_json = self._post_with_retry(url, payload)
        request_id = payload_json.get("request_id") or payload_json.get("requestId")
        if not request_id:
            raise FalCloudError(
                f"fal.ai submit no devolvió request_id: {payload_json}",
                kind="invalid_response",
            )
        return FalJob(request_id=request_id, status="IN_QUEUE", model_id=model_id)

    def submit_hailuo_i2v(
        self,
        *,
        image_url: str,
        prompt: str,
        duration: int = 6,
        resolution: str = "768P",
        end_image_url: str | None = None,
        prompt_optimizer: bool = True,
    ) -> FalJob:
        """Encola un job i2v Hailuo 02 Standard en fal.ai. Pensado para
        presets `kind=music`: cada clip es independiente, no necesita
        continuidad de personaje (los vídeos musicales saltan entre
        planos del producto, no hay personaje).

        Schema (oficial fal.ai):
          - prompt        (str, requerido)
          - image_url     (str, requerido)
          - duration      ("6" | "10")
          - resolution    ("512P" | "768P")  ← Hailuo usa P mayúscula
          - prompt_optimizer (bool)
          - end_image_url (str opcional, continuidad si la quieres)
        """
        if duration not in (6, 10):
            duration = 6
        if resolution not in ("512P", "768P"):
            resolution = "768P"
        payload: dict = {
            "prompt": prompt,
            "image_url": image_url,
            "duration": str(duration),
            "resolution": resolution,
            "prompt_optimizer": prompt_optimizer,
        }
        if end_image_url:
            payload["end_image_url"] = end_image_url

        url = f"{self.base_url}/{HAILUO_STANDARD_MODEL_ID}"
        payload_json = self._post_with_retry(url, payload)
        request_id = payload_json.get("request_id") or payload_json.get("requestId")
        if not request_id:
            raise FalCloudError(
                f"fal.ai Hailuo submit no devolvió request_id: {payload_json}",
                kind="invalid_response",
            )
        return FalJob(
            request_id=request_id,
            status="IN_QUEUE",
            model_id=HAILUO_STANDARD_MODEL_ID,
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
                raise FalCloudError("fal.ai API key inválida (401)", status_code=401, kind="auth")
            if r.status_code == 402:
                raise FalCloudError("fal.ai sin saldo (402)", status_code=402, kind="credits")
            if r.status_code in (429,) or r.status_code >= 500:
                last_exc = FalCloudTransient(f"HTTP {r.status_code}: {r.text[:200]}")
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code >= 400:
                raise FalCloudError(
                    f"fal.ai bad request {r.status_code}: {r.text[:300]}",
                    status_code=r.status_code,
                    kind="invalid_request",
                )
            try:
                return r.json()
            except ValueError as e:
                raise FalCloudError(f"fal.ai respuesta no-JSON: {e}", kind="invalid_response")
        raise FalCloudTransient(
            f"fal.ai submit falló tras {MAX_RETRIES_TRANSIENT} intentos: {last_exc}"
        )

    # ----------------------------------------------------------------
    # POLL
    # ----------------------------------------------------------------
    def poll(self, job: FalJob) -> FalJob:
        """Consulta el status del job. Actualiza `job` y lo devuelve."""
        model_id = TIER_TO_FAL_MODEL.get("standard")  # cualquier model_id válido sirve
        # fal.ai necesita el model_id real para el endpoint. Lo guardamos
        # en el FalJob ... pero esto es un caveat: por simplicidad
        # buscamos via /requests/{id}/status que NO requiere model_id?
        # Realmente sí lo requiere. Mejor guardar model_id en el job.
        raise NotImplementedError(
            "Usa `wait_with_model` directamente — fal.ai requiere model_id en el poll URL."
        )

    def _poll_with_model(self, model_id: str, request_id: str) -> tuple[str, str | None, str | None]:
        """Devuelve `(status, output_url, error)`. status en mayúsculas
        según fal: IN_QUEUE, IN_PROGRESS, COMPLETED, ERROR."""
        # status endpoint
        status_url = f"{self.base_url}/{model_id}/requests/{request_id}/status"
        try:
            r = requests.get(status_url, headers=self._headers(content_type=False), timeout=15)
        except (requests.Timeout, requests.ConnectionError) as e:
            raise FalCloudTransient(f"fal.ai poll fallo de red: {e}")
        if r.status_code >= 400:
            raise FalCloudTransient(f"fal.ai poll HTTP {r.status_code}: {r.text[:200]}")
        try:
            data = r.json()
        except ValueError as e:
            raise FalCloudTransient(f"fal.ai poll respuesta no-JSON: {e}")

        status = (data.get("status") or "IN_QUEUE").upper()
        if status not in ("COMPLETED", "OK", "SUCCESS"):
            return status, None, data.get("error") if isinstance(data.get("error"), str) else None

        # COMPLETED → pedir el resultado real
        result_url = f"{self.base_url}/{model_id}/requests/{request_id}"
        try:
            r2 = requests.get(result_url, headers=self._headers(content_type=False), timeout=30)
        except (requests.Timeout, requests.ConnectionError) as e:
            raise FalCloudTransient(f"fal.ai result fallo de red: {e}")
        if r2.status_code >= 400:
            raise FalCloudTransient(f"fal.ai result HTTP {r2.status_code}: {r2.text[:200]}")
        try:
            result = r2.json()
        except ValueError as e:
            raise FalCloudTransient(f"fal.ai result no-JSON: {e}")
        # fal.ai Seedance devuelve { "video": { "url": "..." } }
        output_url: str | None = None
        video = result.get("video")
        if isinstance(video, dict):
            output_url = video.get("url")
        elif isinstance(result.get("video_url"), str):
            output_url = result["video_url"]
        if not output_url:
            raise FalCloudError(
                f"fal.ai completed pero sin video_url: {result}",
                kind="invalid_response",
            )
        return "COMPLETED", output_url, None

    def wait(
        self,
        job: FalJob,
        tier: str = "standard",
        *,
        timeout_s: int = POLL_TIMEOUT_S,
        poll_interval: float = POLL_INTERVAL_S,
        on_heartbeat: Callable[[int, str], None] | None = None,
    ) -> FalJob:
        """Polling hasta status terminal. Heartbeat cada 60s para UI.

        Si `job.model_id` está poblado, lo usa (cubre Hailuo + cualquier
        modelo futuro). Sino cae al mapeo TIER_TO_FAL_MODEL por
        backwards-compat con código viejo que no setea model_id.
        """
        model_id = job.model_id or TIER_TO_FAL_MODEL.get(tier, TIER_TO_FAL_MODEL["standard"])
        started = time.time()
        deadline = started + timeout_s
        last_log_t = started
        last_status = "IN_QUEUE"
        while time.time() < deadline:
            try:
                status, output_url, error_msg = self._poll_with_model(model_id, job.request_id)
            except FalCloudTransient as e:
                print(f"[fal poll] transient: {e}, retry…")
                time.sleep(poll_interval)
                continue
            last_status = status
            if status == "COMPLETED":
                job.status = "COMPLETED"
                job.output_url = output_url
                return job
            if status == "ERROR" or (error_msg and status != "IN_QUEUE" and status != "IN_PROGRESS"):
                raise FalCloudError(
                    f"fal.ai job {job.request_id} falló: {error_msg or status}",
                    kind="model_failed",
                )
            now = time.time()
            if now - last_log_t >= 60:
                elapsed = int(now - started)
                print(
                    f"[fal poll] req {job.request_id[:8]} status={status} "
                    f"elapsed={elapsed}s timeout={timeout_s}s"
                )
                if on_heartbeat is not None:
                    try:
                        on_heartbeat(elapsed, status.lower())
                    except Exception:
                        pass
                last_log_t = now
            time.sleep(poll_interval)
        raise FalCloudTransient(
            f"fal.ai req {job.request_id} no terminó en {timeout_s/60:.0f}min "
            f"(último status: {last_status})."
        )

    # ----------------------------------------------------------------
    # DOWNLOAD
    # ----------------------------------------------------------------
    def download(self, output_url: str, dest_path: str) -> str:
        """Descarga el MP4 a `dest_path`."""
        if not output_url:
            raise FalCloudError("download: output_url vacío")
        try:
            r = requests.get(output_url, timeout=120, stream=True)
        except (requests.Timeout, requests.ConnectionError) as e:
            raise FalCloudTransient(f"fal.ai download fallo de red: {e}")
        if r.status_code >= 400:
            raise FalCloudTransient(f"fal.ai download HTTP {r.status_code}")
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)) or ".", exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(64 * 1024):
                if chunk:
                    f.write(chunk)
        return dest_path
