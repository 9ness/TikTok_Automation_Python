"""Tests del freeze frame extension (BUG 1, intento 4 — mayo 2026).

Estrategia nueva en `_compose_with_ffmpeg`:
  - audio == video → SYNCED, corte limpio.
  - audio < video  → trim video al audio (igual que antes).
  - audio > video  → FREEZE FRAME: en lugar de truncar audio (que perdía el
    CTA y dejaba pantalla negra), extendemos el video clonando el último
    frame del último clip mediante `tpad=stop_mode=clone:stop_duration=N`.
    El audio se mantiene íntegro; el video acaba 0.5s DESPUÉS del audio.
    NUNCA aparece pantalla negra.

Mock de FFmpeg/ffprobe — verifica el filter_complex sin ejecutar.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

import src.tiktok_shop.pipeline.editor as editor_mod
from src.tiktok_shop.pipeline.editor import compose_shop_video


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def editor_env(monkeypatch, tmp_path):
    voice_mp3 = tmp_path / "voice.mp3"
    voice_mp3.write_bytes(b"fake_mp3")
    clip_paths = []
    for i in range(3):
        p = tmp_path / f"clip_{i}.mp4"
        p.write_bytes(b"fake_mp4")
        clip_paths.append(str(p))

    state = {
        "audio_dur_raw": 17.5,
        "audio_dur_effective": 17.0,  # voz íntegra
        "clip_durs": [5.0, 5.0, 5.0],
        "ffmpeg_calls": [],
    }

    monkeypatch.setattr(editor_mod, "_has_ffmpeg", lambda: True)

    def fake_ffprobe(path: str) -> float:
        if str(voice_mp3) == path:
            return state["audio_dur_raw"]
        for i, cp in enumerate(clip_paths):
            if cp == path:
                return state["clip_durs"][i]
        # output: usar el `-t` pasado al ffmpeg para simular ffprobe
        for cmd in state["ffmpeg_calls"]:
            for j, arg in enumerate(cmd):
                if arg == "-t" and j + 1 < len(cmd):
                    try:
                        return float(cmd[j + 1])
                    except ValueError:
                        pass
        return 14.5

    monkeypatch.setattr(editor_mod, "_ffprobe_duration", fake_ffprobe)
    monkeypatch.setattr(
        editor_mod, "_measure_audio_without_tail_silence",
        lambda path, **kw: state["audio_dur_effective"],
    )

    def fake_run(cmd, **kw):
        state["ffmpeg_calls"].append(cmd)
        try:
            with open(cmd[-1], "wb") as f:
                f.write(b"fake_output")
        except Exception:
            pass
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    monkeypatch.setattr(editor_mod.subprocess, "run", fake_run)

    fake_subs = MagicMock()
    fake_subs.transcribe = lambda *a, **kw: []
    fake_subs.render_karaoke_on_video = (
        lambda *a, **kw: open(a[3], "wb").write(b"final")
    )
    monkeypatch.setitem(sys.modules, "src.subtitles", fake_subs)

    return {
        "voice_mp3": str(voice_mp3),
        "clip_paths": clip_paths,
        "tmp_path": tmp_path,
        "state": state,
    }


def _compose_cmd(state):
    for cmd in state["ffmpeg_calls"]:
        if "-filter_complex" in cmd:
            return cmd
    return []


def _filter_complex(cmd):
    for i, a in enumerate(cmd):
        if a == "-filter_complex" and i + 1 < len(cmd):
            return cmd[i + 1]
    return ""


def _t_value(cmd):
    for i, a in enumerate(cmd):
        if a == "-t" and i + 1 < len(cmd):
            return float(cmd[i + 1])
    return -1.0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestFreezeFrameNoBlack:
    def test_overflow_extends_video_with_tpad_clone(self, editor_env):
        """Audio 17s > video 13.95s → extiende video con tpad=stop_mode=clone
        durante 3.55s (= 17 - 13.95 + 0.5)."""
        # clips=[5,5,5], crossfade=0.3, trim=0.15 → video_dur = 13.95s
        editor_env["state"]["clip_durs"] = [5.0, 5.0, 5.0]
        editor_env["state"]["audio_dur_raw"] = 17.5
        editor_env["state"]["audio_dur_effective"] = 17.0

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.3,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        fc = _filter_complex(_compose_cmd(editor_env["state"]))
        assert "tpad=stop_mode=clone" in fc, (
            f"Falta freeze frame (tpad=stop_mode=clone). filter={fc[:300]}"
        )
        # extra = 17.0 - 13.95 + 0.5 = 3.55
        assert "stop_duration=3.550" in fc or "stop_duration=3.55" in fc, (
            f"Duración freeze incorrecta. filter={fc[:300]}"
        )

    def test_overflow_audio_intact_no_truncate(self, editor_env):
        """En overflow, el audio NO se trunca al video_dur — se mantiene
        íntegro hasta audio_dur (NO se corta el CTA)."""
        editor_env["state"]["clip_durs"] = [5.0, 5.0, 5.0]
        editor_env["state"]["audio_dur_raw"] = 17.5
        editor_env["state"]["audio_dur_effective"] = 17.0

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.3,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        fc = _filter_complex(_compose_cmd(editor_env["state"]))
        # atrim=0:17.000 (audio íntegro, no recortado a 13.95s)
        assert "atrim=0:17.000" in fc, (
            f"Audio debe estar íntegro. filter={fc[:300]}"
        )
        # SIN afade en overflow (silencio sobre frame estático en su lugar)
        assert "afade=t=out" not in fc, (
            "afade=t=out cortaba el CTA. Ahora freeze frame."
        )

    def test_overflow_total_duration_audio_plus_margin(self, editor_env):
        """Total final_dur = audio_dur + 0.5s (= video extendido).
        Asegura que NO hay pantalla negra: el video llega 0.5s más allá
        del final del audio."""
        editor_env["state"]["clip_durs"] = [5.0, 5.0, 5.0]
        editor_env["state"]["audio_dur_raw"] = 17.5
        editor_env["state"]["audio_dur_effective"] = 17.0

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.3,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        cmd = _compose_cmd(editor_env["state"])
        t_val = _t_value(cmd)
        # final_dur = audio_dur (17.0) + 0.5 = 17.5
        assert abs(t_val - 17.5) < 0.05, (
            f"-t debe ser audio+0.5 = 17.5s, fue {t_val}"
        )

    def test_underflow_keeps_video_no_freeze(self, editor_env):
        """Audio 8s < video 13.95s → mantener video completo, audio extiende
        con apad. NO freeze frame (el video real cubre la cola natural)."""
        editor_env["state"]["clip_durs"] = [5.0, 5.0, 5.0]
        editor_env["state"]["audio_dur_raw"] = 8.5
        editor_env["state"]["audio_dur_effective"] = 8.0

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.3,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        cmd = _compose_cmd(editor_env["state"])
        fc = _filter_complex(cmd)
        # En underflow NO hay freeze (los frames reales del clip cubren la cola)
        assert "tpad=stop_mode=clone" not in fc, (
            "Underflow no debe tener freeze frame."
        )
        # Audio cortado a audio_dur (8s) + apad para extender con silencio
        assert "atrim=0:8.000" in fc
        assert "apad" in fc, "Falta apad para extender audio con silencio"
        # `-t` debe ser video_dur (~13.95), NO audio_dur (8)
        t_val = _t_value(cmd)
        assert abs(t_val - 13.95) < 0.05, (
            f"-t debe ser video_dur 13.95s (mantener video completo), fue {t_val}"
        )

    def test_synced_no_freeze(self, editor_env):
        """Audio ≈ video → ambos coinciden → sin freeze."""
        # video_dur = 13.95 → audio_eff exacto
        editor_env["state"]["clip_durs"] = [5.0, 5.0, 5.0]
        editor_env["state"]["audio_dur_raw"] = 14.5
        editor_env["state"]["audio_dur_effective"] = 13.95

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.3,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        fc = _filter_complex(_compose_cmd(editor_env["state"]))
        assert "tpad=stop_mode=clone" not in fc

    def test_freeze_pad_chained_after_xfade(self, editor_env):
        """El paso final tpad debe encadenarse a [vmid] (output del último
        xfade), produciendo [vout] que se mapea al output."""
        editor_env["state"]["clip_durs"] = [5.0, 5.0, 5.0]
        editor_env["state"]["audio_dur_raw"] = 17.5
        editor_env["state"]["audio_dur_effective"] = 17.0

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.3,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        fc = _filter_complex(_compose_cmd(editor_env["state"]))
        # Cadena: ...xfade...[vmid];[vmid]tpad=...[vout]
        assert "[vmid]" in fc, "Falta etiqueta intermedia [vmid]"
        assert "[vmid]tpad=stop_mode=clone" in fc, (
            "tpad debe encadenarse desde [vmid]"
        )
        assert "[vout]" in fc, "Falta etiqueta final [vout]"

    def test_pro_singleshot_overflow_also_freezes(self, editor_env):
        """Pro singleshot (1 clip) con overflow también aplica freeze del
        último frame. El compose pasa por la misma rama de overflow."""
        editor_env["state"]["clip_durs"] = [15.0]
        editor_env["state"]["audio_dur_raw"] = 17.5
        editor_env["state"]["audio_dur_effective"] = 17.0

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"][:1],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="single_shot_multishot",
            add_captions=False,
            crossfade_s=0.0,  # ignorado en singleshot
            log_callback=lambda _: None,
        )

        fc = _filter_complex(_compose_cmd(editor_env["state"]))
        assert "tpad=stop_mode=clone" in fc
        # Audio íntegro
        assert "atrim=0:17.000" in fc

    def test_video_pad_extra_zero_when_not_overflow(self, editor_env):
        """Cuando NO hay overflow, el filter NO debe contener tpad clone."""
        # synced
        editor_env["state"]["clip_durs"] = [5.0, 5.0, 5.0]
        editor_env["state"]["audio_dur_raw"] = 14.5
        editor_env["state"]["audio_dur_effective"] = 13.95

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.3,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        fc = _filter_complex(_compose_cmd(editor_env["state"]))
        assert "tpad=stop_mode=clone" not in fc
        # En su lugar, el paso final es passthrough [vmid]null[vout]
        assert "[vmid]null[vout]" in fc, (
            "Sin overflow debe haber [vmid]null[vout] passthrough."
        )
