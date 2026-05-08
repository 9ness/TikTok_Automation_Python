"""Mock de AtlasCloudClient — sin requests, output MP4 placeholder local.

Implementa la misma interfaz pública que el cliente real:
  - is_available()
  - submit_image_to_video(...)
  - submit_reference_to_video(...)
  - poll(job_id)
  - wait(job_id, ...)
  - download(output_url, dest_path)

Cada `submit_*` devuelve un AtlasJob con job_id determinístico. `poll` y
`wait` devuelven status="completed" inmediatamente con `output_url` mock.
`download` escribe los `MOCK_VIDEO_BYTES` (un fragmento mp4 mínimo) al path.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass


MOCK_ATLAS_OUTPUT_URL = "https://mock-atlas.example/videos/mockfile.mp4"

# Bytes mínimos de un MP4 — no es un MP4 reproducible pero MoviePy detecta
# el formato lo suficiente para los tests de fluidez. Si un test necesita un
# MP4 real para concat, puede sobrescribir con un fixture explícito.
MOCK_VIDEO_BYTES = bytes.fromhex(
    "0000001866747970"           # ftyp box header (24 bytes)
    "69736f6d0000020069736f6d6d703431"
)


@dataclass
class MockAtlasJob:
    job_id: str
    status: str = "completed"
    output_url: str | None = MOCK_ATLAS_OUTPUT_URL
    error: str | None = None


class MockAtlasCloudClient:
    """Drop-in replacement de `AtlasCloudClient`. Permite que tests E2E
    corran el runner completo sin tocar Atlas Cloud."""

    def __init__(self) -> None:
        self.api_key = "mock-key"
        self.base_url = "https://mock-atlas.example/api/v1"
        # Recordar las llamadas para asserts de los tests
        self.calls: list[dict] = []

    def is_available(self) -> bool:
        return True

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
    ) -> MockAtlasJob:
        self.calls.append({
            "endpoint": "image_to_video", "model_id": model_id,
            "duration": duration, "resolution": resolution,
            "has_last_image": bool(last_image_url),
            "image_url_prefix": image_url[:30],
        })
        return MockAtlasJob(job_id=uuid.uuid4().hex)

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
    ) -> MockAtlasJob:
        self.calls.append({
            "endpoint": "reference_to_video", "model_id": model_id,
            "duration": duration, "resolution": resolution, "ratio": ratio,
            "n_refs": len(reference_images),
        })
        return MockAtlasJob(job_id=uuid.uuid4().hex)

    def poll(self, job_id: str) -> MockAtlasJob:
        return MockAtlasJob(job_id=job_id)  # always completed

    def wait(self, job_id: str, *, timeout_s: int = 600, poll_interval: float = 5.0) -> MockAtlasJob:
        return MockAtlasJob(job_id=job_id)  # immediate

    def download(self, output_url: str, dest_path: str) -> str:
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(MOCK_VIDEO_BYTES)
        return dest_path
