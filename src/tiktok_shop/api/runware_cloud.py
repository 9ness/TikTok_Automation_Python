"""Cliente Runware — provider primario de la chain musical TikTok Shop.

Runware es un agregador AI con infraestructura PROPIA (no comparte cola
con fal.ai). Hostea los mismos modelos i2v (Hailuo 02, Kling 2.1, Wan
2.5, Seedance) y cobra solo al completar exitosamente — clave para
limitar el daño cuando un modelo está saturado globalmente.

Doc oficial: https://runware.ai/docs/video-inference/api-reference
  Endpoint:  POST https://api.runware.ai/v1
  Auth:      Authorization: Bearer {RUNWARE_API_KEY}
  Payload:   array de tasks. Cada task con taskType + taskUUID + params.
  Polling:   POST mismo endpoint con taskType="getResponse" y taskUUID.

Pricing aproximado (a 2026-05-26):
  - Hailuo 02 Std (5s):   ~$0.10 (precio fijo)
  - Hailuo 02 Std (10s):  ~$0.20
  - Kling 2.1 Std (5s):   ~$0.14
  - Wan 2.5 (5s):         ~$0.10 estimado

Comparado con fal.ai: ~mismo precio pero cola distinta y solo cobra
al completar. Si Runware se atasca, hacemos failover a fal.ai.
"""

from __future__ import annotations

import base64
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests


RUNWARE_API_URL = "https://api.runware.ai/v1"
SUBMIT_TIMEOUT_S = 30
POLL_INTERVAL_S = 3.0
# Timeout default 15min. Runware cobra al COMPLETAR (no al encolar
# según sus docs — pendiente de verificación empírica), así que un
# timeout aquí en teoría no cuesta dinero. Veo 3.1 Lite normalmente
# tarda 1-3min pero en horas pico puede subir a 5-10min.
try:
    POLL_TIMEOUT_S = int(os.environ.get("RUNWARE_POLL_TIMEOUT_S", "900"))
except ValueError:
    POLL_TIMEOUT_S = 900
MAX_RETRIES_TRANSIENT = 3


# Mapeo nuestro tier → model_id en Runware. Identificadores AIR
# verificados desde docs oficiales de Runware (no inventar).
# https://runware.ai/docs/models/google-veo-3-1-lite
# https://runware.ai/docs/models/minimax-hailuo-02

# Veo 3.1 Lite — PRIMARIO para music TikTok. Soporta 9:16 portrait
# nativo, baratísimo ($0.05/s a 720p), 4-8s, image-to-video.
VEO_31_LITE_MODEL_ID = "google:veo@3.1-lite"

# Hailuo 02 Std — INUTILIZABLE para TikTok porque solo soporta 16:9
# horizontal (1366x768 o 1920x1080). Lo mantenemos como constante por
# si Runware añade portrait en el futuro.
HAILUO_02_STD_MODEL_ID = "minimax:3@1"

# Kling 2.1 / Wan 2.5 — AIRs pendientes de verificar. Sí soportan 9:16
# nativamente según docs de Kuaishou/Alibaba, pero el modelAIR exacto
# en Runware aún no se ha encontrado en sus docs.
KLING_21_STD_MODEL_ID = "klingai:5@3"  # placeholder, NO confirmado
WAN_25_MODEL_ID = "alibaba:wan@2-5"     # placeholder, NO confirmado

MUSIC_RENDERER_LABELS_RUNWARE: dict[str, str] = {
    HAILUO_02_STD_MODEL_ID: "Hailuo 02 (Runware)",
    KLING_21_STD_MODEL_ID:  "Kling 2.1 (Runware)",
    WAN_25_MODEL_ID:        "Wan 2.5 (Runware)",
}


class RunwareError(RuntimeError):
    """Error Runware NO retryable (401, 402, mal request)."""
    def __init__(self, message: str, *, status_code: int | None = None, kind: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind


class RunwareTransient(RuntimeError):
    """Error transitorio (timeout/5xx/cola atascada)."""


@dataclass
class RunwareJob:
    task_uuid: str
    status: str = "processing"   # processing | success | error
    output_url: str | None = None
    error: str | None = None
    model_id: str = ""


def runware_is_configured() -> bool:
    return bool(os.environ.get("RUNWARE_API_KEY", "").strip())


def runware_api_key() -> str:
    return os.environ.get("RUNWARE_API_KEY", "").strip()


def _photo_to_data_url(image_path_or_url: str) -> str:
    """Convierte un path local o URL HTTPS a data: base64 inline. Si
    ya es URL HTTPS o data:, lo devuelve tal cual (Runware acepta ambos
    en `frameImages.inputImage`)."""
    if image_path_or_url.startswith(("http://", "https://", "data:")):
        return image_path_or_url
    p = Path(image_path_or_url)
    if not p.is_file():
        raise RunwareError(f"Foto no encontrada: {image_path_or_url}")
    suffix = p.suffix.lower().lstrip(".") or "jpeg"
    if suffix == "jpg":
        suffix = "jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/{suffix};base64,{b64}"


class RunwareClient:
    def __init__(self) -> None:
        self.api_key = runware_api_key()
        self.base_url = RUNWARE_API_URL

    def is_available(self) -> bool:
        return runware_is_configured()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def healthcheck(self, *, timeout_s: float = 8.0) -> tuple[bool, str]:
        """Pre-flight: confirma API key válida sin gastar créditos."""
        if not self.api_key:
            return False, "RUNWARE_API_KEY no configurada"
        try:
            # Hacemos una request mínima — sin task válida — solo para
            # validar auth. Runware responderá con 400 (bad request) o
            # 200 con errores. 401/402 indican auth/credits.
            r = requests.post(
                self.base_url, headers=self._headers(), json=[],
                timeout=timeout_s,
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            return False, f"runware no responde — {str(e)[:120]}"
        if r.status_code in (401, 403):
            return False, "Runware API key inválida o expirada"
        if r.status_code == 402:
            return False, "Runware sin saldo — recarga créditos"
        return True, f"Runware OK (HTTP {r.status_code})"

    # ----------------------------------------------------------------
    # SUBMIT — image-to-video
    # ----------------------------------------------------------------
    def submit_i2v(
        self,
        *,
        model_id: str,
        image_ref: str,
        prompt: str,
        duration_s: int,
        width: int = 1080,
        height: int = 1920,
    ) -> RunwareJob:
        """Encola un job i2v en Runware. `image_ref` acepta path local
        (se convierte a data:base64), URL HTTPS o data: directo.

        Args:
            model_id: ej. "minimax:hailuo@02" o "klingai:kling-video@2-1-standard"
            image_ref: path local, URL HTTPS o data:base64
            prompt: descripción de la escena (positive_prompt en Runware)
            duration_s: duración del clip en segundos
            width / height: dimensiones del vídeo (9:16 → 1080x1920)
        """
        task_uuid = str(uuid.uuid4())
        input_image = _photo_to_data_url(image_ref)
        task: dict = {
            "taskType": "videoInference",
            "taskUUID": task_uuid,
            "model": model_id,
            "positivePrompt": prompt,
            "duration": duration_s,
            "width": width,
            "height": height,
            "frameImages": [{"inputImage": input_image}],
        }
        result = self._post_with_retry([task])
        # Runware devuelve { data: [...], errors: [...] }
        errors = result.get("errors") or []
        if errors:
            err = errors[0] if isinstance(errors[0], dict) else {"message": str(errors[0])}
            raise RunwareError(
                f"Runware submit error: {err.get('message', err)}",
                kind=err.get("code") or "submit_failed",
            )
        return RunwareJob(task_uuid=task_uuid, status="processing", model_id=model_id)

    def submit_veo31_lite_i2v(
        self,
        *,
        image_ref: str,
        prompt: str,
        duration_s: int = 6,
        resolution: str = "720p",
        aspect_ratio: str = "9:16",
    ) -> RunwareJob:
        """Encola un job i2v con Google Veo 3.1 Lite en Runware.

        Soporta 9:16 vertical nativo — perfecto para TikTok. Mucho más
        barato que Hailuo o Kling ($0.05/s a 720p vs $0.10+/clip de
        otros modelos) y calidad equivalente o superior.

        Schema (https://runware.ai/docs/models/google-veo-3-1-lite):
          - model:        google:veo@3.1-lite
          - duration:     4 | 6 | 8 (segundos)
          - resolution:   "720p" | "1080p"
          - frameImages:  [{inputImage: url|base64}] o
                          [{image: ..., frame: "first"|"last"|"0"|"-1"}]

        Para 9:16 vertical pasamos `width`/`height` 720x1280 (720p) o
        1080x1920 (1080p) — el modelo respeta orientación.
        """
        if duration_s not in (4, 6, 8):
            # Redondeamos al más cercano de los 3 valores soportados
            duration_s = min((4, 6, 8), key=lambda v: abs(v - duration_s))
        if resolution not in ("720p", "1080p"):
            resolution = "720p"
        is_portrait = aspect_ratio == "9:16"
        # Veo Lite acepta SOLO width+height (no resolution string como
        # creía). El docstring genérico mostraba `resolution: "720p"`
        # pero el modelo concreto exige las dimensiones reales.
        # `conflictPa` aparecía cuando mandábamos ambos a la vez.
        if resolution == "720p":
            w, h = (720, 1280) if is_portrait else (1280, 720)
        else:
            w, h = (1080, 1920) if is_portrait else (1920, 1080)

        task_uuid = str(uuid.uuid4())
        input_image = _photo_to_data_url(image_ref)
        task: dict = {
            "taskType": "videoInference",
            "taskUUID": task_uuid,
            "model": VEO_31_LITE_MODEL_ID,
            "positivePrompt": prompt,
            "duration": duration_s,
            # SOLO width+height (no `resolution` para evitar conflictPa).
            "width": w,
            "height": h,
            "frameImages": [{"inputImage": input_image}],
            "outputType": "URL",
            "outputFormat": "MP4",
            "deliveryMethod": "async",
            # Sin audio nativo (lo añade el user en TikTok con trending audio)
            "providerSettings": {
                "google": {
                    "generateAudio": False,
                },
            },
        }
        result = self._post_with_retry([task])
        errors = result.get("errors") or []
        if errors:
            err = errors[0] if isinstance(errors[0], dict) else {"message": str(errors[0])}
            raise RunwareError(
                f"Runware Veo submit error: {err.get('message', err)}",
                kind=err.get("code") or "submit_failed",
            )
        return RunwareJob(
            task_uuid=task_uuid,
            status="processing",
            model_id=VEO_31_LITE_MODEL_ID,
        )

    def _post_with_retry(self, tasks: list[dict]) -> dict:
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES_TRANSIENT):
            try:
                r = requests.post(
                    self.base_url, headers=self._headers(), json=tasks,
                    timeout=SUBMIT_TIMEOUT_S,
                )
            except (requests.Timeout, requests.ConnectionError) as e:
                last_exc = e
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code == 401:
                raise RunwareError("Runware API key inválida (401)", status_code=401, kind="auth")
            if r.status_code == 402:
                raise RunwareError("Runware sin saldo (402)", status_code=402, kind="credits")
            if r.status_code in (429,) or r.status_code >= 500:
                last_exc = RunwareTransient(f"HTTP {r.status_code}: {r.text[:200]}")
                time.sleep(2 ** (attempt + 1))
                continue
            if r.status_code >= 400:
                raise RunwareError(
                    f"Runware bad request {r.status_code}: {r.text[:300]}",
                    status_code=r.status_code, kind="invalid_request",
                )
            try:
                return r.json()
            except ValueError as e:
                raise RunwareError(f"Runware respuesta no-JSON: {e}", kind="invalid_response")
        raise RunwareTransient(
            f"Runware submit falló tras {MAX_RETRIES_TRANSIENT} intentos: {last_exc}"
        )

    # ----------------------------------------------------------------
    # POLL
    # ----------------------------------------------------------------
    def poll(self, job: RunwareJob) -> RunwareJob:
        """Consulta el status del job vía getResponse. Actualiza job
        y lo devuelve."""
        poll_task = {
            "taskType": "getResponse",
            "taskUUID": str(uuid.uuid4()),
            "responseTaskUUID": job.task_uuid,
        }
        result = self._post_with_retry([poll_task])
        # Buscamos en data el item con nuestro taskUUID original
        data = result.get("data") or []
        for item in data:
            if not isinstance(item, dict):
                continue
            # El item de respuesta puede llevar nuestro taskUUID original
            # o un nuevo UUID. Filtramos por taskType y video.
            if item.get("taskType") == "videoInference":
                status = (item.get("status") or "processing").lower()
                job.status = status
                if status == "success":
                    # Output suele estar en `videoURL` o `video.url`
                    job.output_url = (
                        item.get("videoURL")
                        or (item.get("video") or {}).get("url") if isinstance(item.get("video"), dict) else None
                        or item.get("outputURL")
                    )
                elif status == "error":
                    job.error = item.get("error") or "unknown"
                return job
        # Si no encontramos el item, seguimos en processing
        errors = result.get("errors") or []
        if errors:
            err = errors[0] if isinstance(errors[0], dict) else {"message": str(errors[0])}
            # Si el error es "task not found yet" probablemente sigue procesando
            msg = (err.get("message") or "").lower()
            if "not found" in msg or "pending" in msg:
                return job
            raise RunwareError(
                f"Runware poll error: {err.get('message', err)}",
                kind=err.get("code") or "poll_failed",
            )
        return job

    def wait(
        self,
        job: RunwareJob,
        *,
        timeout_s: int = POLL_TIMEOUT_S,
        poll_interval: float = POLL_INTERVAL_S,
        on_heartbeat: Callable[[int, str], None] | None = None,
    ) -> RunwareJob:
        """Polling hasta status terminal."""
        started = time.time()
        deadline = started + timeout_s
        last_log_t = started
        while time.time() < deadline:
            try:
                self.poll(job)
            except RunwareTransient as e:
                print(f"[runware poll] transient: {e}, retry…")
                time.sleep(poll_interval)
                continue
            if job.status == "success":
                return job
            if job.status == "error":
                raise RunwareError(
                    f"Runware job {job.task_uuid} falló: {job.error or 'unknown'}",
                    kind="model_failed",
                )
            now = time.time()
            if now - last_log_t >= 60:
                elapsed = int(now - started)
                print(
                    f"[runware poll] task {job.task_uuid[:8]} status={job.status} "
                    f"elapsed={elapsed}s timeout={timeout_s}s"
                )
                if on_heartbeat is not None:
                    try:
                        on_heartbeat(elapsed, job.status)
                    except Exception:
                        pass
                last_log_t = now
            time.sleep(poll_interval)
        raise RunwareTransient(
            f"Runware task {job.task_uuid} no terminó en {timeout_s//60}min "
            f"(último status: {job.status})."
        )

    # ----------------------------------------------------------------
    # DOWNLOAD
    # ----------------------------------------------------------------
    def download(self, output_url: str, dest_path: str) -> str:
        """Descarga el MP4 a `dest_path`."""
        if not output_url:
            raise RunwareError("download: output_url vacío")
        try:
            r = requests.get(output_url, timeout=120, stream=True)
        except (requests.Timeout, requests.ConnectionError) as e:
            raise RunwareTransient(f"runware download fallo de red: {e}")
        if r.status_code >= 400:
            raise RunwareTransient(f"runware download HTTP {r.status_code}")
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)) or ".", exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(64 * 1024):
                if chunk:
                    f.write(chunk)
        return dest_path
