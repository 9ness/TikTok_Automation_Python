"""Tests del router 🎬 Subs sobre Vídeo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _fake_video_bytes() -> bytes:
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16


def _parse_ndjson(text: str) -> list[dict]:
    """Parsea cada línea no vacía como JSON. Útil para el stream de /transcribe."""
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _extract_result(text: str) -> dict:
    """Devuelve el primer evento `result` del stream NDJSON."""
    for ev in _parse_ndjson(text):
        if ev.get("type") == "result":
            return ev
    raise AssertionError(f"No se encontró evento 'result' en el stream:\n{text}")


@pytest.fixture
def fake_whisper(monkeypatch: pytest.MonkeyPatch):
    """Stub de subtitles_only para no correr Whisper real."""
    import src.subtitles_only as mod

    def _fake_extract(video_path: str, output_audio: str) -> str:
        Path(output_audio).write_bytes(b"fake-audio")
        return output_audio

    def _fake_transcribe(audio_path, *, reference_script=None, model_size="small",
                         language=None, audio_type="speech", progress_callback=None):
        if progress_callback:
            progress_callback(0.5, "fake midway")
            progress_callback(1.0, "fake done")
        return [
            {"word": "hola", "start": 0.0, "end": 0.5},
            {"word": "mundo", "start": 0.5, "end": 1.0},
        ]

    monkeypatch.setattr(mod, "extract_audio_from_video", _fake_extract)
    monkeypatch.setattr(mod, "transcribe_with_reference", _fake_transcribe)


# ---------------------------------------------------------------------------
# POST /transcribe
# ---------------------------------------------------------------------------
class TestSubsAutoTranscribe:
    def test_transcribe_happy_path(self, app_client: TestClient, fake_whisper):
        r = app_client.post(
            "/api/v1/creator-reward/subs-auto/transcribe",
            files={"file": ("song.mp4", _fake_video_bytes(), "video/mp4")},
            data={
                "model_size": "small",
                "language": "es",
                "audio_type": "music",
                "quality_label": "1080p (Lento)",
            },
        )
        assert r.status_code == 200, r.text
        events = _parse_ndjson(r.text)
        # Debe haber al menos un evento progress y exactamente un result.
        assert any(ev.get("type") == "progress" for ev in events)
        body = _extract_result(r.text)
        assert body["input_path_relative"].startswith("api_uploads/subs_auto/")
        assert body["out_path_relative"].startswith("api_uploads/subs_auto/")
        assert len(body["words"]) == 2
        assert body["words"][0]["word"] == "hola"
        assert body["model_size"] == "small"
        assert body["language"] == "es"
        assert body["audio_type"] == "music"

    def test_transcribe_invalid_extension(self, app_client: TestClient, fake_whisper):
        r = app_client.post(
            "/api/v1/creator-reward/subs-auto/transcribe",
            files={"file": ("song.txt", b"text", "text/plain")},
            data={"model_size": "small", "audio_type": "speech"},
        )
        assert r.status_code == 422

    def test_transcribe_empty_file(self, app_client: TestClient, fake_whisper):
        r = app_client.post(
            "/api/v1/creator-reward/subs-auto/transcribe",
            files={"file": ("song.mp4", b"", "video/mp4")},
            data={"model_size": "small", "audio_type": "speech"},
        )
        assert r.status_code == 422

    def test_transcribe_no_words(self, app_client: TestClient, monkeypatch):
        import src.subtitles_only as mod

        def _empty_extract(v, o):
            Path(o).write_bytes(b"")
            return o

        def _empty_transcribe(*args, **kwargs):
            return []

        monkeypatch.setattr(mod, "extract_audio_from_video", _empty_extract)
        monkeypatch.setattr(mod, "transcribe_with_reference", _empty_transcribe)

        r = app_client.post(
            "/api/v1/creator-reward/subs-auto/transcribe",
            files={"file": ("song.mp4", _fake_video_bytes(), "video/mp4")},
            data={"model_size": "small", "audio_type": "speech"},
        )
        # El stream arranca con 200 OK (cabeceras ya enviadas); el fallo viaja
        # como evento `error` en el cuerpo NDJSON.
        assert r.status_code == 200, r.text
        events = _parse_ndjson(r.text)
        errors = [ev for ev in events if ev.get("type") == "error"]
        assert len(errors) == 1, events
        assert "no detect" in errors[0]["message"].lower()
        assert not any(ev.get("type") == "result" for ev in events)


# ---------------------------------------------------------------------------
# POST /enqueue
# ---------------------------------------------------------------------------
class TestSubsAutoEnqueue:
    def _full_style(self) -> dict:
        return {
            "font_path": r"C:\Windows\Fonts\impact.ttf",
            "highlight_mode": "pill",
            "highlight_color": "#BB0808",
            "text_color": "#FFFFFF",
            "stroke_color": "#000000",
            "stroke_width": 3,
            "case_mode": "UPPERCASE",
            "font_scale": 0.045,
            "max_words": 3,
            "y_position": 0.78,
            "pill_enabled": True,
            "max_width": 0.85,
            "sync_offset": 0,
        }

    def test_enqueue_after_transcribe(
        self, app_client: TestClient, fake_whisper, fake_job_queue
    ):
        # Primero transcribe para obtener paths
        t = app_client.post(
            "/api/v1/creator-reward/subs-auto/transcribe",
            files={"file": ("song.mp4", _fake_video_bytes(), "video/mp4")},
            data={"model_size": "small", "audio_type": "speech"},
        )
        assert t.status_code == 200
        result = _extract_result(t.text)
        in_path = result["input_path_relative"]
        out_path = result["out_path_relative"]

        r = app_client.post(
            "/api/v1/creator-reward/subs-auto/enqueue",
            json={
                "input_path": in_path,
                "out_path": out_path,
                "edited_text": "hola mundo editado",
                "model_size": "small",
                "audio_type": "speech",
                "quality_label": "1080p (Lento)",
                "style": self._full_style(),
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["job_id"]
        assert "✏️ editado" in body["title"]

        from src.queue.models import JobMode
        all_jobs = fake_job_queue.get_all()
        assert len(all_jobs) == 1
        assert all_jobs[0].mode == JobMode.SUBS_AUTO
        params = all_jobs[0].params
        assert params["edited_text"] == "hola mundo editado"
        assert params["highlight_mode"] == "pill"
        assert Path(params["input_path"]).exists()

    def test_enqueue_path_traversal_rejected(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/creator-reward/subs-auto/enqueue",
            json={
                "input_path": "../../../etc/passwd",
                "out_path": "api_uploads/subs_auto/out.mp4",
                "style": self._full_style(),
            },
        )
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_temp_path"

    def test_enqueue_absolute_path_rejected(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/creator-reward/subs-auto/enqueue",
            json={
                "input_path": "C:/windows/system32/cmd.exe",
                "out_path": "api_uploads/subs_auto/out.mp4",
                "style": self._full_style(),
            },
        )
        assert r.status_code == 422

    def test_enqueue_nonexistent_input(self, app_client: TestClient):
        r = app_client.post(
            "/api/v1/creator-reward/subs-auto/enqueue",
            json={
                "input_path": "api_uploads/subs_auto/never_uploaded.mp4",
                "out_path": "api_uploads/subs_auto/out.mp4",
                "style": self._full_style(),
            },
        )
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_temp_path"
