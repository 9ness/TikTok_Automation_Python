"""Cliente Atlas Cloud — image-to-video y reference-to-video.

Doc oficial:
  Base URL: https://api.atlascloud.ai/api/v1
  Auth:     Authorization: Bearer ATLASCLOUD_API_KEY
  Submit:   POST /model/generateVideo
  Poll:     GET  /model/prediction/{prediction_id}

Mismo endpoint para los 3 tiers — el campo `model` decide qué motor correr.
Status final del polling: "completed" o "succeeded" → outputs[0].

Errores manejados:
  401: API key inválida → no retry, mensaje claro
  402: Sin saldo (INSUFFICIENT_CREDITS) → no retry, mensaje claro
  429: Rate limit → retry exponencial (max 3)
  5xx: Server error → retry exponencial (max 3)
  Timeout submit: 30s, 1 retry
  Timeout polling total: 5 min → cancela job
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

import requests

from src.tiktok_shop.config import atlas_api_key, atlas_base_url, atlas_is_configured


SUBMIT_TIMEOUT_S = 30
POLL_INTERVAL_S = 3.0
# Hard cap del polling. Atlas Standard en horas pico EU puede tardar
# 20-40 min por clip cuando la cola está saturada — preferimos esperar
# antes que cancelar (que cobra crédito sin entregar resultado). Default
# 2h, configurable con ATLAS_POLL_TIMEOUT_S env var. Si el user quiere
# cancelar antes, puede hacerlo manualmente desde la UI de cola.
try:
    POLL_TIMEOUT_S = int(os.environ.get("ATLAS_POLL_TIMEOUT_S", "7200"))
except ValueError:
    POLL_TIMEOUT_S = 7200
MAX_RETRIES_TRANSIENT = 3       # 429 / 5xx


class AtlasCloudError(RuntimeError):
    """Error de Atlas Cloud que NO debe reintentarse (401, 402, mal request).
    El runner debería propagarlo al usuario sin maquillarlo."""

    def __init__(self, message: str, *, status_code: int | None = None, kind: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind  # "auth" | "credits" | "invalid_request" | "model_failed"


class AtlasCloudTransient(RuntimeError):
    """Error transitorio (429/5xx/timeout) — retry exponencial aplicable."""


@dataclass
class AtlasJob:
    job_id: str
    status: str = "pending"
    output_url: str | None = None
    error: str | None = None


class AtlasCloudClient:
    def __init__(self) -> None:
        self.api_key = atlas_api_key() or ""
        self.base_url = atlas_base_url()

    def is_available(self) -> bool:
        return atlas_is_configured()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def healthcheck(self, *, timeout_s: float = 8.0) -> tuple[bool, str]:
        """Pre-flight rápido: confirma que la API responde + nuestra key
        es válida ANTES de submitir un job (que tarda 5-20 min).

        Devuelve `(ok, message)`. `ok=False` se da en:
          - sin API key configurada
          - timeout/conn refused (Atlas API caída)
          - 401/403 (API key inválida o expirada)
          - 402 (sin saldo)
        Otros 4xx/5xx se consideran "respondiendo, no bloqueante" → ok=True
        para no abortar generaciones por errores transitorios del endpoint
        de healthcheck (que no es el de submit). El de submit ya maneja
        sus propios errores con reintentos.
        """
        if not self.api_key:
            return False, "Atlas API key no configurada (ATLASCLOUD_API_KEY vacío)"
        # Hacemos una GET ligera al base_url — Atlas devuelve 404/405 si
        # el path no existe, pero CON nuestra auth header en una conexión
        # real. Eso basta para diagnosticar caída total vs key bloqueada.
        try:
            r = requests.get(
                self.base_url.rstrip("/") + "/",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=timeout_s,
            )
        except requests.Timeout:
            return False, f"Atlas Cloud timeout ({timeout_s}s) — API caída o muy lenta"
        except requests.ConnectionError as e:
            return False, f"Atlas Cloud no responde — {str(e)[:120]}"
        if r.status_code in (401, 403):
            return False, "Atlas API key inválida o expirada (HTTP 401/403)"
        if r.status_code == 402:
            return False, "Atlas sin saldo (HTTP 402) — recarga créditos"
        # Cualquier otro código (200, 404, 405, 5xx) → la API responde,
        # no bloqueamos. El error real saldrá en el submit.
        return True, f"Atlas OK (HTTP {r.status_code})"

    def cancel(self, job_id: str) -> bool:
        """Best-effort cancel del job — útil al pillar timeout para que
        Atlas no siga "renderizando" en background y consumiendo crédito.
        No conozco con certeza el endpoint exacto que Atlas expone; probamos
        DELETE /model/prediction/{id} (convención REST). Si falla, no
        propagamos — es best-effort, no rompe el flow."""
        if not self.api_key or not job_id:
            return False
        try:
            r = requests.delete(
                f"{self.base_url}/model/prediction/{job_id}",
                headers=self._headers(),
                timeout=10,
            )
            return r.status_code < 400
        except Exception:
            return False

    # ----------------------------------------------------------------
    # SUBMIT helpers internos
    # ----------------------------------------------------------------
    def _post_with_retry(self, url: str, payload: dict) -> dict:
        """POST con retry exponencial en 429/5xx. No retry en 4xx no-rate."""
        attempt = 0
        last_err: Exception | None = None
        while attempt < MAX_RETRIES_TRANSIENT:
            attempt += 1
            try:
                r = requests.post(
                    url, headers=self._headers(), json=payload, timeout=SUBMIT_TIMEOUT_S,
                )
            except requests.Timeout as e:
                last_err = e
                if attempt < MAX_RETRIES_TRANSIENT:
                    time.sleep(2 ** attempt)
                    continue
                raise AtlasCloudTransient(f"Timeout submit tras {attempt} intentos") from e
            except requests.RequestException as e:
                raise AtlasCloudTransient(f"Error de red Atlas: {e}") from e

            # Errores no-retryable: 401, 402, 4xx (excepto 429)
            if r.status_code == 401:
                raise AtlasCloudError(
                    "Atlas Cloud 401: API key inválida o expirada.",
                    status_code=401, kind="auth",
                )
            if r.status_code == 402:
                raise AtlasCloudError(
                    "Atlas Cloud 402: saldo insuficiente (INSUFFICIENT_CREDITS). "
                    "Recarga la cuenta antes de seguir generando.",
                    status_code=402, kind="credits",
                )
            if r.status_code == 429:
                # rate limit → retry
                if attempt < MAX_RETRIES_TRANSIENT:
                    backoff = 2 ** attempt
                    time.sleep(backoff)
                    continue
                raise AtlasCloudTransient(f"429 rate limit tras {attempt} intentos")
            if 500 <= r.status_code < 600:
                if attempt < MAX_RETRIES_TRANSIENT:
                    time.sleep(2 ** attempt)
                    continue
                raise AtlasCloudTransient(f"{r.status_code} server error tras {attempt} intentos")
            if r.status_code >= 400:
                raise AtlasCloudError(
                    f"Atlas Cloud {r.status_code}: {r.text[:300]}",
                    status_code=r.status_code, kind="invalid_request",
                )

            try:
                return r.json()
            except ValueError as e:
                raise AtlasCloudTransient(f"Respuesta no-JSON: {e}") from e

        raise AtlasCloudTransient(f"Submit Atlas falló: {last_err}")

    @staticmethod
    def _extract_job_id(payload: dict) -> str:
        """La doc no especifica nombre exacto del campo. Probamos los más comunes."""
        for key in ("id", "prediction_id", "job_id"):
            if key in payload and payload[key]:
                return str(payload[key])
            if isinstance(payload.get("data"), dict) and payload["data"].get(key):
                return str(payload["data"][key])
        raise AtlasCloudTransient(
            f"No se encontró id de predicción en la respuesta: {payload}"
        )

    # ----------------------------------------------------------------
    # IMAGE-TO-VIDEO (Standard / Advanced)
    # ----------------------------------------------------------------
    def submit_image_to_video(
        self,
        *,
        model_id: str,
        image_url: str,
        prompt: str,
        duration: int,
        resolution: str = "720p",
        last_image_url: str | None = None,
        aspect_ratio: str = "9:16",
        camera_fixed: bool = False,
        generate_audio: bool = False,
        seed: int = -1,
    ) -> AtlasJob:
        """Encola un job image-to-video (Standard o Advanced).

        Args:
          model_id: 'bytedance/seedance-v1.5-pro/image-to-video-fast' (standard)
                    o 'bytedance/seedance-v1.5-pro/image-to-video' (advanced).
          image_url: URL pública (https://...) accesible para Atlas Cloud.
                     Doc no confirma soporte de base64 inline para i2v — usar URL.
          last_image_url: opcional — URL del frame final para anchoring entre clips.
          duration: 4..12 segundos (Standard/Advanced).
          resolution: "720p" (Standard) | "720p"/"480p" (Advanced).

        Returns:
          AtlasJob con el job_id devuelto por Atlas.
        """
        if not self.is_available():
            raise AtlasCloudError(
                "Atlas Cloud no configurado: define ATLASCLOUD_API_KEY en .env.",
                kind="auth",
            )

        body: dict = {
            "model": model_id,
            "aspect_ratio": aspect_ratio,
            "camera_fixed": camera_fixed,
            "duration": duration,
            "generate_audio": generate_audio,
            "image": image_url,
            "prompt": prompt,
            "resolution": resolution,
            "seed": seed,
        }
        if last_image_url:
            body["last_image"] = last_image_url

        url = f"{self.base_url}/model/generateVideo"
        payload = self._post_with_retry(url, body)
        return AtlasJob(job_id=self._extract_job_id(payload))

    # ----------------------------------------------------------------
    # REFERENCE-TO-VIDEO (Pro)
    # ----------------------------------------------------------------
    def submit_reference_to_video(
        self,
        *,
        reference_images: list[str],
        prompt: str,
        duration: int,
        resolution: str = "720p",
        ratio: str = "9:16",
        reference_videos: list[str] | None = None,
        reference_audios: list[str] | None = None,
        generate_audio: bool = False,
        watermark: bool = False,
        return_last_frame: bool = False,
        model_id: str = "bytedance/seedance-2.0-fast/reference-to-video",
    ) -> AtlasJob:
        """Encola 1 job reference-to-video (Pro tier, multi-shot interno).

        Args:
          reference_images: hasta 9 URLs/base64/asset:// — el modelo decide
            cómo combinarlas para el multi-shot.
          duration: 4..15 (más amplio que Standard/Advanced).
          resolution: '480p' | '720p' | '1080p-SR' | '1440p-SR'.
          ratio: '9:16' (default) — la doc avisa que el campo es `ratio`,
            NO `aspect_ratio`. Si la API rechaza '9:16' fall back a 'adaptive'
            es responsabilidad del caller (logear y retry con adaptive).

        Returns:
          AtlasJob — un único job (no array).
        """
        if not self.is_available():
            raise AtlasCloudError(
                "Atlas Cloud no configurado: define ATLASCLOUD_API_KEY en .env.",
                kind="auth",
            )
        if not reference_images:
            raise ValueError("reference_images vacío — Pro requiere al menos 1.")
        if len(reference_images) > 9:
            raise ValueError(f"Pro acepta máximo 9 reference_images, recibidas {len(reference_images)}.")

        body: dict = {
            "model": model_id,
            "prompt": prompt,
            "reference_images": reference_images,
            "reference_videos": reference_videos or [],
            "reference_audios": reference_audios or [],
            "duration": duration,
            "resolution": resolution,
            "ratio": ratio,
            "generate_audio": generate_audio,
            "watermark": watermark,
            "return_last_frame": return_last_frame,
        }

        url = f"{self.base_url}/model/generateVideo"
        payload = self._post_with_retry(url, body)
        return AtlasJob(job_id=self._extract_job_id(payload))

    # ----------------------------------------------------------------
    # POLLING (común a los 3 tiers)
    # ----------------------------------------------------------------
    def poll(self, job_id: str) -> AtlasJob:
        """Una sola consulta del estado. Devuelve el job actualizado."""
        if not self.is_available():
            raise AtlasCloudError("Atlas Cloud no configurado.", kind="auth")

        url = f"{self.base_url}/model/prediction/{job_id}"
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
        except requests.RequestException as e:
            raise AtlasCloudTransient(f"Error de red en poll: {e}") from e

        if r.status_code == 401:
            raise AtlasCloudError("Atlas 401 en poll: API key inválida.", status_code=401, kind="auth")
        if r.status_code >= 400:
            raise AtlasCloudTransient(f"Poll {r.status_code}: {r.text[:200]}")

        try:
            payload = r.json()
        except ValueError as e:
            raise AtlasCloudTransient(f"Poll respuesta no-JSON: {e}") from e

        data = payload.get("data") or payload
        status = (data.get("status") or "pending").lower()
        outputs = data.get("outputs") or data.get("output") or []
        output_url = outputs[0] if isinstance(outputs, list) and outputs else None
        error_msg = data.get("error") if isinstance(data.get("error"), str) else None
        return AtlasJob(job_id=job_id, status=status, output_url=output_url, error=error_msg)

    def wait(
        self,
        job_id: str,
        *,
        timeout_s: int = POLL_TIMEOUT_S,
        poll_interval: float = POLL_INTERVAL_S,
        on_heartbeat: Callable[[int, str], None] | None = None,
    ) -> AtlasJob:
        """Polling síncrono hasta status terminal o timeout.

        `on_heartbeat(elapsed_s, status)` se llama cada 60s para que el
        runner pueda actualizar el progress_label del job (que se ve en
        la UI de cola). Sin esto, los Standard tier saturados se veían
        bloqueados en "🎥 Atlas renderizando" sin pista de tiempo.
        """
        started = time.time()
        deadline = started + timeout_s
        last: AtlasJob | None = None
        last_log_t = started
        while time.time() < deadline:
            try:
                last = self.poll(job_id)
            except AtlasCloudTransient as e:
                # Loguear, esperar y reintentar
                print(f"[Atlas poll] transient: {e}, reintentando…")
                time.sleep(poll_interval)
                continue

            if last.status in ("completed", "succeeded"):
                if not last.output_url:
                    raise AtlasCloudError(
                        f"Atlas job {job_id} completado pero sin output_url.",
                        kind="model_failed",
                    )
                return last
            if last.status in ("failed", "error"):
                raise AtlasCloudError(
                    f"Atlas job {job_id} falló: {last.error or 'sin detalle'}",
                    kind="model_failed",
                )
            # Heartbeat cada 60s — útil para diagnosticar jobs que se
            # quedan en "processing" mucho tiempo (en lugar de fail
            # silencioso al timeout). También notifica al runner para
            # que actualice el progress_label de la UI.
            now = time.time()
            if now - last_log_t >= 60:
                elapsed = int(now - started)
                print(
                    f"[Atlas poll] job {job_id[:8]} status={last.status} "
                    f"elapsed={elapsed}s timeout={timeout_s}s"
                )
                if on_heartbeat is not None:
                    try:
                        on_heartbeat(elapsed, last.status if last else "?")
                    except Exception:
                        pass  # heartbeat es cosmético, no debe romper el wait
                last_log_t = now
            time.sleep(poll_interval)
        # Best-effort cancel para no dejar el job consumiendo crédito en
        # background. Si Atlas no soporta DELETE, esto es no-op (ver `cancel`).
        try:
            cancelled = self.cancel(job_id)
        except Exception:
            cancelled = False
        cancel_msg = (
            "Cancelado correctamente en Atlas." if cancelled
            else "Cancel del job en Atlas no confirmado — puede seguir cobrando crédito."
        )
        raise AtlasCloudTransient(
            f"Atlas job {job_id} no terminó en {timeout_s/60:.0f}min "
            f"(último status: {last.status if last else 'sin respuesta'}). "
            f"{cancel_msg} Posible causa: cola Standard saturada en hora pico — "
            f"reintenta más tarde, o cambia al tier Advanced (~3x más rápido)."
        )

    def download(self, output_url: str, dest_path: str) -> str:
        """Descarga el MP4 final a `dest_path`.

        La doc no especifica si las URLs son presigned/TTL. Asumimos URL pública
        directa (la URL sale del campo `outputs[0]` del polling). Si requiere
        auth header en el futuro, ajustar aquí.
        """
        try:
            r = requests.get(output_url, timeout=120, stream=True)
            r.raise_for_status()
        except requests.RequestException as e:
            raise AtlasCloudTransient(f"Error descargando MP4: {e}") from e
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        return dest_path
