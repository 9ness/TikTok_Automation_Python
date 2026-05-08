"""Tests del fix BUG mayo 2026 (intento 6): pantalla negra al final en
caso underflow.

Síntoma anterior: cuando audio < video, el filter usaba `apad` (sin duración
explícita) → moviepy/ffmpeg interpretaban el stream de audio como ambiguo
y cortaban el MP4 final a la duración del audio explícito (atrim), dejando
los últimos segundos como pantalla negra con el caption flotando.

Fix: usar `apad=whole_dur=<final_dur>` para fijar EXPLÍCITAMENTE la duración
del stream de audio a la del video. Así no hay ambigüedad y los últimos
frames del último clip Atlas se conservan visibles bajo la cola del audio
en silencio.

Cubrimos:
1. Filter contiene `apad=whole_dur=<final_dur>` con valor correcto.
2. NO contiene `apad` solo (sin whole_dur) — el bug original.
3. Pre-trim del voice_mp3 para Whisper (evita captions fantasma).
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
    clip_paths = [str(tmp_path / f"clip_{i}.mp4") for i in range(3)]
    for p in clip_paths:
        with open(p, "wb") as f:
            f.write(b"fake")

    state = {
        "audio_dur_raw": 14.5,
        "audio_dur_effective": 12.9,
        "clip_durs": [5.04, 5.04, 5.04],
        "ffmpeg_calls": [],
    }

    monkeypatch.setattr(editor_mod, "_has_ffmpeg", lambda: True)

    def fake_ffprobe(path: str) -> float:
        if str(voice_mp3) == path:
            return state["audio_dur_raw"]
        for i, cp in enumerate(clip_paths):
            if cp == path:
                return state["clip_durs"][i]
        # output: usar el `-t` del último compose con -filter_complex
        for cmd in state["ffmpeg_calls"]:
            if "-filter_complex" not in cmd:
                continue
            for j, arg in enumerate(cmd):
                if arg == "-t" and j + 1 < len(cmd):
                    try:
                        return float(cmd[j + 1])
                    except ValueError:
                        pass
        return 14.07

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


# ---------------------------------------------------------------------------
# Tests del filter underflow
# ---------------------------------------------------------------------------
class TestUnderflowApadExplicit:
    def test_apad_with_whole_dur_explicit(self, editor_env):
        """Filter debe contener `apad=whole_dur=<final_dur>` (no `apad` solo)."""
        # video_dur = (5.04-0.15)*3 - 0.6 = 14.07
        # audio_dur_effective = 12.9 → underflow → final_dur = 14.07
        editor_env["state"]["clip_durs"] = [5.04, 5.04, 5.04]
        editor_env["state"]["audio_dur_raw"] = 14.5
        editor_env["state"]["audio_dur_effective"] = 12.9

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
        # final_dur ~ 14.07 (3 clips × 5.04 - 0.45 trim - 0.6 xfade = 14.07)
        # Comprobamos que apad lleva whole_dur≈14.07
        assert "apad=whole_dur=14.0" in fc or "apad=whole_dur=14.07" in fc, (
            f"Filter debe tener `apad=whole_dur=<final_dur>` explícito. filter={fc[:300]}"
        )

    def test_no_apad_alone_without_whole_dur(self, editor_env):
        """`apad` SIN `whole_dur` causaba el bug — debe estar SIEMPRE con whole_dur."""
        editor_env["state"]["clip_durs"] = [5.04, 5.04, 5.04]
        editor_env["state"]["audio_dur_raw"] = 14.5
        editor_env["state"]["audio_dur_effective"] = 12.9

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
        # Si aparece `apad` debe tener whole_dur. Buscamos `apad,` o `apad[`
        # (sin whole_dur) — el bug original.
        assert "apad," not in fc, (
            "❌ apad sin whole_dur en chain. Era el bug que cortaba el MP4."
        )
        assert "apad[aout]" not in fc, (
            "❌ apad sin whole_dur al final del chain. Era el bug original."
        )

    def test_t_value_equals_video_dur(self, editor_env):
        """`-t` final = video_dur (mantener video completo en underflow)."""
        editor_env["state"]["clip_durs"] = [5.04, 5.04, 5.04]
        editor_env["state"]["audio_dur_raw"] = 14.5
        editor_env["state"]["audio_dur_effective"] = 12.9

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
        for i, arg in enumerate(cmd):
            if arg == "-t" and i + 1 < len(cmd):
                t_val = float(cmd[i + 1])
                # video_dur = 14.07, audio_eff = 12.9 → underflow → t=14.07
                assert abs(t_val - 14.07) < 0.05, (
                    f"-t debe ser video_dur (14.07s), fue {t_val}"
                )
                return
        pytest.fail("No se encontró -t en el comando ffmpeg")


# ---------------------------------------------------------------------------
# Pre-trim del voice_mp3 antes de Whisper
# ---------------------------------------------------------------------------
class TestVoicePretrimForCaptions:
    def test_pretrim_voice_called_before_transcribe(self, editor_env, monkeypatch):
        """Antes de Whisper, debe llamarse a ffmpeg para pre-trimar el voice
        a `audio_dur_effective` segundos. Evita captions fantasma del tail
        silence MiniMax."""
        editor_env["state"]["clip_durs"] = [5.04, 5.04, 5.04]
        editor_env["state"]["audio_dur_raw"] = 14.5
        editor_env["state"]["audio_dur_effective"] = 12.9

        # Stub real de subtitles (porque queremos que captions corra)
        captured_voice_for_transcribe: list[str] = []

        def fake_transcribe(audio_path, model_size="small", language=None):
            captured_voice_for_transcribe.append(audio_path)
            return []

        fake_subs = MagicMock()
        fake_subs.transcribe = fake_transcribe
        fake_subs.render_karaoke_on_video = (
            lambda *a, **kw: open(a[3], "wb").write(b"final")
        )
        monkeypatch.setitem(sys.modules, "src.subtitles", fake_subs)

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=True,
            crossfade_s=0.3,
            trim_head_s=0.15,
            language="es",
            log_callback=lambda _: None,
        )

        # 1. Whisper recibió un voice DIFERENTE al voice_mp3 original
        # (= el voice trimmed)
        assert captured_voice_for_transcribe, "Whisper no fue llamado"
        voice_used_for_whisper = captured_voice_for_transcribe[0]
        assert voice_used_for_whisper != editor_env["voice_mp3"], (
            "Whisper debe recibir un voice pre-trimado, no el voice_mp3 original. "
            f"Recibió: {voice_used_for_whisper}"
        )
        assert "trimmed" in voice_used_for_whisper, (
            f"Voice trimmed debe llevar 'trimmed' en el nombre. "
            f"Got: {voice_used_for_whisper}"
        )

        # 2. Hubo una llamada a ffmpeg con `-t {audio_dur_effective}` y `-c:a copy`
        # para extraer el trimmed
        ffmpeg_calls = editor_env["state"]["ffmpeg_calls"]
        trim_cmd = next(
            (cmd for cmd in ffmpeg_calls
             if "-c:a" in cmd and "copy" in cmd),
            None,
        )
        assert trim_cmd is not None, (
            "No se encontró llamada ffmpeg de pre-trim. "
            f"calls={[' '.join(c[:6]) for c in ffmpeg_calls]}"
        )
        # El `-t` debe ser audio_dur_effective (12.9)
        for i, arg in enumerate(trim_cmd):
            if arg == "-t" and i + 1 < len(trim_cmd):
                t_val = float(trim_cmd[i + 1])
                assert abs(t_val - 12.9) < 0.05, (
                    f"Pre-trim debe usar -t {12.9}, fue {t_val}"
                )
                return
        pytest.fail("Pre-trim cmd no tiene flag -t")


# ---------------------------------------------------------------------------
# Splits compensan shrinkage (BUG video sale corto)
# ---------------------------------------------------------------------------
class TestSplitCompensatesShrinkage:
    """Verifica que las nuevas tablas (mayo 2026) producen splits cuyo MP4
    final dura ≥ duración pedida (con tolerancia ±0.3s de codec rounding).

    Modelo: Atlas devuelve ~target+0.04s por clip (drift observado en logs).
    Shrinkage = N × trim_head + (N-1) × crossfade.
    """

    # Drift observado en producción (logs E2E de mayo 2026): Atlas devuelve
    # 5.042s para clips de 5s pedidos. Modelado como +0.04s constante.
    ATLAS_DRIFT_PER_CLIP = 0.04
    # Tolerancia post-codec: el editor permite ±0.3s sin warning. Aplicamos
    # la misma tolerancia aquí (target - 0.3s ya se considera "≥ target").
    TOLERANCE = 0.3

    @pytest.mark.parametrize("total", [5, 10, 12, 15, 20, 24, 25, 30])
    def test_dynamic_split_produces_video_dur_ge_target(self, total):
        from src.tiktok_shop.utils.duration_splitter import split_duration
        clips = split_duration(total, "standard", "dynamic")
        n = len(clips)
        shrinkage = n * 0.15 + max(0, n - 1) * 0.3
        # Atlas real ≈ sum(clips) + drift × N
        atlas_total_real = sum(clips) + self.ATLAS_DRIFT_PER_CLIP * n
        video_dur = atlas_total_real - shrinkage
        assert video_dur >= total - self.TOLERANCE, (
            f"Dynamic {total}s: split={clips} → atlas_real={atlas_total_real:.2f}, "
            f"shrinkage={shrinkage:.2f}, video_dur={video_dur:.2f} < {total - self.TOLERANCE}"
        )

    @pytest.mark.parametrize("total", [5, 10, 12, 15, 20, 24, 25, 30])
    def test_cinematic_split_produces_video_dur_ge_target(self, total):
        from src.tiktok_shop.utils.duration_splitter import split_duration
        clips = split_duration(total, "standard", "cinematic")
        n = len(clips)
        shrinkage = n * 0.15 + max(0, n - 1) * 0.5
        atlas_total_real = sum(clips) + self.ATLAS_DRIFT_PER_CLIP * n
        video_dur = atlas_total_real - shrinkage
        assert video_dur >= total - self.TOLERANCE, (
            f"Cinematic {total}s: split={clips} → atlas_real={atlas_total_real:.2f}, "
            f"shrinkage={shrinkage:.2f}, video_dur={video_dur:.2f} < {total - self.TOLERANCE}"
        )

    def test_pro_no_margin_needed(self):
        """Pro singleshot no usa trim_head ni crossfade → no necesita margen."""
        from src.tiktok_shop.utils.duration_splitter import split_duration
        for total in [5, 10, 12, 15]:
            assert split_duration(total, "pro") == [total], (
                f"Pro {total}s debe ser [total] sin margen"
            )
