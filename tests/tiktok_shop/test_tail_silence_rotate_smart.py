"""Tests de los 3 fixes adicionales:

1. **tail silence**: `_measure_audio_without_tail_silence` detecta silencio
   final con `silencedetect` y devuelve duración efectiva.
2. **rotate_smart**: `_rotate_smart_assignment` evita repetición adyacente
   y matchea purpose del clip con tipo de plano de la foto.
3. **ffprobe estricta**: `_compose_with_ffmpeg` ABORTA si la duración del
   output difiere >2s de la objetivo.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

import src.queue.runners as runners_mod
import src.tiktok_shop.pipeline.editor as editor_mod
from src.queue.runners import _rotate_smart_assignment
from src.tiktok_shop.pipeline.editor import (
    _measure_audio_without_tail_silence,
    compose_shop_video,
)


# ===========================================================================
# Fix 1 — tail silence detection
# ===========================================================================
class TestMeasureAudioWithoutTailSilence:
    def _mock_ffmpeg_silencedetect(self, monkeypatch, stderr_lines: list[str], rc: int = 0):
        """Mocks `subprocess.run` para devolver un stderr con líneas de
        silencedetect simuladas. Necesita también _ffprobe_duration."""
        result = MagicMock()
        result.returncode = rc
        result.stderr = "\n".join(stderr_lines)
        monkeypatch.setattr(
            editor_mod.subprocess, "run",
            lambda *a, **kw: result,
        )

    def test_no_silence_detected_returns_raw(self, monkeypatch):
        monkeypatch.setattr(editor_mod, "_ffprobe_duration", lambda p: 15.0)
        self._mock_ffmpeg_silencedetect(monkeypatch, [
            "[silencedetect @ 0x...] silence_end: 5.0 | silence_duration: 0.5",
            # No hay silence_start cerca del final
        ])
        assert _measure_audio_without_tail_silence("fake.mp3") == 15.0

    def test_tail_silence_trimmed(self, monkeypatch):
        """Audio raw 15.5s con silence_start=14.7 → devuelve 14.7s."""
        monkeypatch.setattr(editor_mod, "_ffprobe_duration", lambda p: 15.5)
        self._mock_ffmpeg_silencedetect(monkeypatch, [
            "[silencedetect @ 0x...] silence_start: 14.7",
            "[silencedetect @ 0x...] silence_end: 15.5 | silence_duration: 0.8",
        ])
        result = _measure_audio_without_tail_silence("fake.mp3")
        assert result == 14.7

    def test_silence_in_middle_ignored(self, monkeypatch):
        """Pausa natural en medio (10s) NO debe recortar audio de 15s."""
        monkeypatch.setattr(editor_mod, "_ffprobe_duration", lambda p: 15.0)
        self._mock_ffmpeg_silencedetect(monkeypatch, [
            "[silencedetect @ 0x...] silence_start: 10.0",
            "[silencedetect @ 0x...] silence_end: 10.5 | silence_duration: 0.5",
        ])
        # last silence_start=10 está a 5s del final (>2s proximity) → no recorta
        result = _measure_audio_without_tail_silence("fake.mp3")
        assert result == 15.0

    def test_multiple_silences_uses_last(self, monkeypatch):
        """Si hay varios silence_start, usa el último (más cercano al final)."""
        monkeypatch.setattr(editor_mod, "_ffprobe_duration", lambda p: 15.0)
        self._mock_ffmpeg_silencedetect(monkeypatch, [
            "silence_start: 5.0",
            "silence_end: 5.5 | silence_duration: 0.5",
            "silence_start: 14.5",
            "silence_end: 15.0 | silence_duration: 0.5",
        ])
        # Último silence_start=14.5, raw=15.0 → diff=0.5 < 2.0 → recorta
        assert _measure_audio_without_tail_silence("fake.mp3") == 14.5

    def test_ffmpeg_error_returns_raw(self, monkeypatch):
        monkeypatch.setattr(editor_mod, "_ffprobe_duration", lambda p: 12.0)
        self._mock_ffmpeg_silencedetect(monkeypatch, ["error msg"], rc=1)
        # rc != 0 → devuelve raw sin parsear
        assert _measure_audio_without_tail_silence("fake.mp3") == 12.0

    def test_subprocess_exception_returns_raw(self, monkeypatch):
        monkeypatch.setattr(editor_mod, "_ffprobe_duration", lambda p: 8.0)

        def boom(*a, **kw):
            raise OSError("fake error")

        monkeypatch.setattr(editor_mod.subprocess, "run", boom)
        assert _measure_audio_without_tail_silence("fake.mp3") == 8.0

    def test_minimum_duration_floor(self, monkeypatch):
        """Si silence_start es muy pequeño (≈0), nunca devuelve 0 (floor 0.5s)."""
        monkeypatch.setattr(editor_mod, "_ffprobe_duration", lambda p: 0.6)
        self._mock_ffmpeg_silencedetect(monkeypatch, [
            "silence_start: 0.05",
            "silence_end: 0.6",
        ])
        # last=0.05, raw=0.6, proximity=0.55 < 2.0 → recorta pero no a <0.5
        result = _measure_audio_without_tail_silence("fake.mp3")
        assert result == 0.5  # floor


# ===========================================================================
# Fix 2 — rotate_smart_assignment
# ===========================================================================
class TestRotateSmartAssignment:
    def _make_specs(self, n: int) -> list[dict]:
        return [{"clip_idx": i, "ref_photo_index": 0, "duration": 5} for i in range(n)]

    def test_empty_photos_no_changes(self):
        specs = self._make_specs(3)
        original = [s["ref_photo_index"] for s in specs]
        _rotate_smart_assignment(specs, photos=[], video_structure=[])
        assert [s["ref_photo_index"] for s in specs] == original

    def test_match_purpose_to_type(self):
        """purpose='hook' → busca foto type='packshot' o 'macro'."""
        specs = self._make_specs(2)
        photos = [
            {"type": "lifestyle", "filename": "a"},  # idx 0
            {"type": "packshot", "filename": "b"},   # idx 1 ← debe usarse
        ]
        structure = [
            {"clip_number": 1, "purpose": "hook"},
            {"clip_number": 2, "purpose": "demo"},
        ]
        _rotate_smart_assignment(specs, photos=photos, video_structure=structure)
        assert specs[0]["ref_photo_index"] == 1  # packshot para hook

    def test_demo_prefers_in_use(self):
        specs = self._make_specs(2)
        photos = [
            {"type": "packshot", "filename": "a"},   # 0
            {"type": "in_use", "filename": "b"},     # 1 ← demo
            {"type": "lifestyle", "filename": "c"},  # 2
        ]
        structure = [
            {"clip_number": 1, "purpose": "hook"},
            {"clip_number": 2, "purpose": "demo"},
        ]
        _rotate_smart_assignment(specs, photos=photos, video_structure=structure)
        assert specs[1]["ref_photo_index"] == 1  # in_use para demo

    def test_cta_prefers_lifestyle(self):
        specs = self._make_specs(3)
        photos = [
            {"type": "packshot", "filename": "a"},
            {"type": "in_use", "filename": "b"},
            {"type": "lifestyle", "filename": "c"},  # 2 ← cta
        ]
        structure = [
            {"clip_number": 1, "purpose": "hook"},
            {"clip_number": 2, "purpose": "demo"},
            {"clip_number": 3, "purpose": "cta"},
        ]
        _rotate_smart_assignment(specs, photos=photos, video_structure=structure)
        assert specs[2]["ref_photo_index"] == 2

    def test_no_repetition_adjacent(self):
        """Si solo hay 2 fotos del mismo tipo, no las repite consecutivas
        cuando sea posible."""
        specs = self._make_specs(4)
        photos = [
            {"type": "packshot", "filename": "a"},  # 0
            {"type": "packshot", "filename": "b"},  # 1
            {"type": "in_use", "filename": "c"},    # 2
            {"type": "lifestyle", "filename": "d"}, # 3
        ]
        # Todos los purposes apuntan a packshot
        structure = [
            {"clip_number": 1, "purpose": "hook"},
            {"clip_number": 2, "purpose": "hook"},
            {"clip_number": 3, "purpose": "hook"},
            {"clip_number": 4, "purpose": "hook"},
        ]
        _rotate_smart_assignment(specs, photos=photos, video_structure=structure)
        chosen = [s["ref_photo_index"] for s in specs]
        # No 2 consecutivos iguales (por lo menos en los primeros 2 clips
        # tenemos 2 packshots distintos: 0 y 1)
        assert chosen[0] != chosen[1]

    def test_unknown_purpose_fallback(self):
        """purpose desconocido → cae a 'cualquier foto distinta de la previa'."""
        specs = self._make_specs(3)
        photos = [
            {"type": "lifestyle", "filename": "a"},
            {"type": "packshot", "filename": "b"},
            {"type": "in_use", "filename": "c"},
        ]
        structure = [
            {"clip_number": 1, "purpose": "alien_purpose"},
            {"clip_number": 2, "purpose": "weird"},
            {"clip_number": 3, "purpose": "xxx"},
        ]
        _rotate_smart_assignment(specs, photos=photos, video_structure=structure)
        chosen = [s["ref_photo_index"] for s in specs]
        # Sin purpose conocido, evita repetición adyacente
        assert chosen[0] != chosen[1]
        assert chosen[1] != chosen[2]

    def test_no_video_structure(self):
        """Sin video_structure, asigna evitando repetición adyacente."""
        specs = self._make_specs(3)
        photos = [
            {"type": "packshot", "filename": "a"},
            {"type": "lifestyle", "filename": "b"},
            {"type": "in_use", "filename": "c"},
        ]
        _rotate_smart_assignment(specs, photos=photos, video_structure=None)
        chosen = [s["ref_photo_index"] for s in specs]
        assert chosen[0] != chosen[1]
        assert chosen[1] != chosen[2]

    def test_only_one_photo_repeats(self):
        """Si solo hay 1 foto, todos los clips la usan (sin alternativa)."""
        specs = self._make_specs(3)
        photos = [{"type": "packshot", "filename": "only"}]
        _rotate_smart_assignment(specs, photos=photos, video_structure=None)
        assert all(s["ref_photo_index"] == 0 for s in specs)


# ===========================================================================
# Fix 3 — ffprobe estricta (post-export validation)
# ===========================================================================
class TestStrictFfprobeValidation:
    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        """Setup: clips fake + voice fake + subprocess.run mockeado."""
        voice_mp3 = tmp_path / "voice.mp3"
        voice_mp3.write_bytes(b"fake")
        clip_paths = []
        for i in range(2):
            p = tmp_path / f"clip_{i}.mp4"
            p.write_bytes(b"fake")
            clip_paths.append(str(p))

        state = {
            "audio_dur": 9.5,
            "clip_durs": [5.0, 5.0],
            "output_dur_override": None,  # tests pueden simular drift del output
        }

        monkeypatch.setattr(editor_mod, "_has_ffmpeg", lambda: True)
        monkeypatch.setattr(
            editor_mod, "_measure_audio_without_tail_silence",
            lambda p, **kw: state["audio_dur"],
        )

        def fake_ffprobe(path):
            if path == str(voice_mp3):
                return state["audio_dur"]
            for i, cp in enumerate(clip_paths):
                if cp == path:
                    return state["clip_durs"][i]
            # Es el output
            if state["output_dur_override"] is not None:
                return state["output_dur_override"]
            # Por defecto: el `-t` del comando ffmpeg
            return state.get("last_t", 9.5)

        monkeypatch.setattr(editor_mod, "_ffprobe_duration", fake_ffprobe)

        def fake_run(cmd, **kwargs):
            # Crear archivo output fake
            for i, a in enumerate(cmd):
                if a == "-t" and i + 1 < len(cmd):
                    state["last_t"] = float(cmd[i + 1])
                    break
            output_path = cmd[-1]
            with open(output_path, "wb") as f:
                f.write(b"fake")
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            return r

        monkeypatch.setattr(editor_mod.subprocess, "run", fake_run)

        # Stub subtitles (no se usa con add_captions=False)
        monkeypatch.setitem(sys.modules, "src.subtitles", MagicMock())

        return {"voice_mp3": str(voice_mp3), "clip_paths": clip_paths,
                "state": state, "tmp_path": tmp_path}

    def test_normal_drift_warning_only(self, env):
        """Diff de ~0.4s (entre 0.3 y 2.0) → log warning, NO aborta."""
        # video_dur = (5.15-0.15)*2 - 0.5 = 9.5 → final_dur = video (mantener
        # video completo en underflow, mayo 2026)
        env["state"]["output_dur_override"] = 9.9  # target 9.5 → diff 0.4
        env["state"]["audio_dur"] = 9.2
        env["state"]["clip_durs"] = [5.15, 5.15]
        logs = []
        out = env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=env["clip_paths"],
            voice_mp3=env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.5,
            trim_head_s=0.15,
            log_callback=logs.append,
        )
        # No debe haber abortado
        assert any("Vídeo final" in line for line in logs)

    def test_grave_drift_aborts(self, env):
        """Diff >2s → RuntimeError con mensaje claro."""
        env["state"]["output_dur_override"] = 50.0  # target ~9.2 → diff +40s
        env["state"]["audio_dur"] = 9.2
        env["state"]["clip_durs"] = [5.15, 5.15]

        out = env["tmp_path"] / "out.mp4"
        with pytest.raises(RuntimeError, match="discrepancia grave"):
            compose_shop_video(
                clip_paths=env["clip_paths"],
                voice_mp3=env["voice_mp3"],
                output_path=str(out),
                strategy="multi_clip_anchor",
                add_captions=False,
                crossfade_s=0.5,
                trim_head_s=0.15,
                log_callback=lambda _: None,
            )

    def test_within_tolerance_no_warning(self, env):
        """Diff <0.3s → silencioso, sin log de warning."""
        # video_dur = (5.15-0.15)*2 - 0.5 = 9.5 → final_dur = video
        env["state"]["output_dur_override"] = 9.5  # exact match a final_dur
        env["state"]["audio_dur"] = 9.2
        env["state"]["clip_durs"] = [5.15, 5.15]
        logs = []
        out = env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=env["clip_paths"],
            voice_mp3=env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.5,
            trim_head_s=0.15,
            log_callback=logs.append,
        )
        # NO debe haber log de warning de diff
        assert not any("vs target" in line and "diff=" in line for line in logs)
