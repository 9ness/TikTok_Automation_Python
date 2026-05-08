"""Test: el editor NO usa silenceremove agresivo en el filter_complex.

Bug fix mayo 2026: el filter `silenceremove=stop_periods=-1:stop_duration=0.3:
stop_threshold=-50dB` eliminaba TODOS los silencios > 0.3s del audio,
incluidas las pausas naturales del speaker entre frases. Esto comprimía
el audio (~0.5-1.5s menos) y lo desincronizaba del video → frame final
congelado / pantalla negra al final.

Fix: en lugar de silenceremove, usamos `_measure_audio_without_tail_silence`
para detectar SOLO el tail silence (al final) y aplicamos `atrim=0:audio_dur`
en el filter_complex — un corte quirúrgico al final que NO toca pausas
internas.

Estos tests verifican:
1. El filter_complex NO contiene `silenceremove`.
2. El filter_complex contiene `atrim=0:<audio_dur>` con la duración medida
   por `_measure_audio_without_tail_silence`.
3. Pausas internas no se ven afectadas (el audio entre 0 y `audio_dur`
   pasa íntegro, sin filtros de eliminación de silencio).
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

import src.tiktok_shop.pipeline.editor as editor_mod
from src.tiktok_shop.pipeline.editor import compose_shop_video


# ---------------------------------------------------------------------------
# Fixture compartido — replica el de test_editor_fixes pero con control
# explícito sobre el resultado de _measure_audio_without_tail_silence.
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
        # raw audio_dur reportado por ffprobe (incluye tail silence)
        "audio_dur_raw": 16.0,
        # audio efectivo (sin tail silence) — lo que devuelve _measure_audio_without_tail_silence
        "audio_dur_effective": 14.5,
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
        # output: lo que se "rendió"
        for cmd in state["ffmpeg_calls"]:
            for j, arg in enumerate(cmd):
                if arg == "-t" and j + 1 < len(cmd):
                    try:
                        return float(cmd[j + 1])
                    except ValueError:
                        pass
        return 14.5

    monkeypatch.setattr(editor_mod, "_ffprobe_duration", fake_ffprobe)

    # Mock de _measure_audio_without_tail_silence — devuelve audio_dur_effective
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
    """Devuelve la llamada principal de ffmpeg (con -filter_complex)."""
    for cmd in state["ffmpeg_calls"]:
        if "-filter_complex" in cmd:
            return cmd
    return []


def _filter_complex(cmd):
    for i, a in enumerate(cmd):
        if a == "-filter_complex" and i + 1 < len(cmd):
            return cmd[i + 1]
    return ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestSilenceremovePreservesInternalPauses:
    def test_no_silenceremove_in_filter(self, editor_env):
        """El filter_complex NO debe contener `silenceremove`.

        `silenceremove=stop_periods=-1` elimina todos los periodos de silencio,
        incluidas pausas naturales del speaker → comprime audio.
        """
        editor_env["state"]["clip_durs"] = [5.0, 5.0, 5.0]
        editor_env["state"]["audio_dur_raw"] = 16.0
        editor_env["state"]["audio_dur_effective"] = 14.5

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
        assert "silenceremove" not in fc, (
            "❌ silenceremove agresivo sigue en filter_complex. "
            "Comprimirá pausas internas del speaker."
        )

    def test_atrim_at_effective_audio_dur(self, editor_env):
        """El filter debe tener `atrim=0:<audio_dur_effective>` — corte
        quirúrgico al boundary entre voz y tail silence.

        Esto elimina solo el tail, NO los silencios internos.
        """
        # clips=[6,6,6], trim=0.15, crossfade=0.3 →
        #   post_trim = 5.85 cada uno, total = 17.55
        #   overlap = 0.3 * 2 = 0.6 → video_dur = 16.95s
        # audio_dur_effective = 14.5 < 16.95 → underflow → final_dur = 14.5
        editor_env["state"]["clip_durs"] = [6.0, 6.0, 6.0]
        editor_env["state"]["audio_dur_raw"] = 16.0
        editor_env["state"]["audio_dur_effective"] = 14.5

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
        # underflow → final_dur = audio_dur_effective = 14.5
        assert "atrim=0:14.5" in fc, (
            f"Falta atrim=0:14.5 (audio efectivo). filter={fc[:300]}"
        )

    def test_tail_silence_trimmed_not_internal(self, editor_env):
        """Si raw=16s y efectivo=14s (= 2s de tail), el audio se corta a 14s
        pero el VIDEO mantiene su duración natural (16.95s).

        Estrategia mayo 2026 (intento 5): underflow ya NO recorta video.
        El audio termina y los últimos frames del clip Atlas se ven con
        silencio sobre ellos (no negro).
        """
        # clips=[6,6,6] → video_dur = 16.95
        editor_env["state"]["clip_durs"] = [6.0, 6.0, 6.0]
        editor_env["state"]["audio_dur_raw"] = 16.0
        editor_env["state"]["audio_dur_effective"] = 14.0

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
        # Audio chain: atrim corta el voice a audio_efectivo (14.0), apad
        # rellena con silencio hasta el final del video.
        assert "atrim=0:14.0" in fc
        assert "apad" in fc, "Falta apad para extender audio con silencio"

        # `-t` final = video_dur (16.95), NO audio_efectivo (14.0)
        for i, arg in enumerate(cmd):
            if arg == "-t" and i + 1 < len(cmd):
                t_val = float(cmd[i + 1])
                assert abs(t_val - 16.95) < 0.05, (
                    f"-t debe ser video_dur 16.95s (mantener video completo), "
                    f"fue {t_val}. Estrategia: NO recortar video al audio."
                )
                break
        else:
            pytest.fail("No se encontró flag -t en el comando ffmpeg")

    def test_overflow_uses_freeze_frame_not_truncate(self, editor_env):
        """Caso overflow (audio > video): audio íntegro + freeze del último
        frame del video con `tpad=stop_mode=clone`. NO silenceremove,
        NO afade (audio termina sobre frame estático con silencio)."""
        # audio efectivo = 19s (overflow incluso sin tail)
        # clips=[5,5,5], crossfade=0.3, trim=0.15 → video_dur = 13.95s
        editor_env["state"]["clip_durs"] = [5.0, 5.0, 5.0]
        editor_env["state"]["audio_dur_raw"] = 20.0
        editor_env["state"]["audio_dur_effective"] = 19.0

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
        # NO silenceremove (legacy aggressive filter)
        assert "silenceremove" not in fc
        # NO afade en overflow — freeze frame en lugar de fade-out
        assert "afade=t=out" not in fc, (
            "afade=t=out cortaba el CTA. Estrategia nueva: freeze frame."
        )
        # Audio íntegro = atrim=0:19.000 (no recortado al video_dur)
        assert "atrim=0:19.000" in fc, (
            f"Audio debe quedar íntegro. filter={fc[:300]}"
        )
        # Freeze frame: tpad=stop_mode=clone:stop_duration=N
        assert "tpad=stop_mode=clone" in fc

    def test_no_silenceremove_when_synced(self, editor_env):
        """Caso synced (|audio - video| ≤ 0.05): atrim al final_dur, no afade."""
        # clips=[6,6,6], crossfade=0.3, trim=0.15 → video_dur = 16.95s
        # audio_eff = 16.95 → diff=0 → synced → no afade
        editor_env["state"]["clip_durs"] = [6.0, 6.0, 6.0]
        editor_env["state"]["audio_dur_raw"] = 17.5
        editor_env["state"]["audio_dur_effective"] = 16.95

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
        assert "silenceremove" not in fc
        assert "atrim=0:" in fc
        # Synced: NO afade (solo overflow lo añade)
        assert "afade=t=out" not in fc
