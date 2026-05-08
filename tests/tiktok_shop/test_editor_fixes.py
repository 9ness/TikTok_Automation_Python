"""Tests del editor FFmpeg-based (BUG A xfade real, BUG B audio-no-overflow).

Mocks de `subprocess.check_output` (ffprobe) y `subprocess.run` (ffmpeg)
para verificar que se construye el `filter_complex` correcto SIN ejecutar
FFmpeg de verdad. Los tests miden:
  - BUG A: el filter_complex usa `xfade=transition=fade` (no `concat` con
    padding negativo, que generaba flash negro).
  - BUG B: con audio > video se inyecta `atrim` + `afade=t=out`. Con audio
    < video el `-t` final usa la duración del audio para evitar pantalla
    negra al final.
  - Pro singleshot: sin xfade ni trim head.
  - Validación post-export: ffprobe del output coincide con target ±0.5s.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

import src.tiktok_shop.pipeline.editor as editor_mod
from src.tiktok_shop.pipeline.editor import compose_shop_video


# ---------------------------------------------------------------------------
# Fixture: mock filesystem + subprocess
# ---------------------------------------------------------------------------
@pytest.fixture
def editor_env(monkeypatch, tmp_path):
    """Setup completo: archivos fake, ffmpeg/ffprobe mockeados, subtitles stub."""

    # 1. Archivos fake en disco
    voice_mp3 = tmp_path / "voice.mp3"
    voice_mp3.write_bytes(b"fake_mp3")
    clip_paths = []
    for i in range(3):
        p = tmp_path / f"clip_{i}.mp4"
        p.write_bytes(b"fake_mp4")
        clip_paths.append(str(p))

    # 2. State del mock — los tests pueden modificar aquí las duraciones
    mock_state = {
        "audio_dur": 14.5,            # default: audio cabe en video
        "clip_durs": [5.0, 5.0, 5.0], # default: 3 clips de 5s
        "output_dur": None,            # se rellena tras ffmpeg "fake-run"
        "ffmpeg_calls": [],
        "ffprobe_calls": [],
        "subtitles_called": False,
    }

    # 3. Mock de _has_ffmpeg — siempre True
    monkeypatch.setattr(editor_mod, "_has_ffmpeg", lambda: True)

    # 4. Mock de _ffprobe_duration — devuelve duraciones del state
    def fake_ffprobe(path: str) -> float:
        mock_state["ffprobe_calls"].append(path)
        if str(voice_mp3) == path:
            return mock_state["audio_dur"]
        for i, cp in enumerate(clip_paths):
            if cp == path:
                return mock_state["clip_durs"][i]
        # Es el output → devolver lo que se "rendió"
        if mock_state["output_dur"] is not None:
            return mock_state["output_dur"]
        return 14.5

    monkeypatch.setattr(editor_mod, "_ffprobe_duration", fake_ffprobe)

    # 5. Mock de subprocess.run — captura el comando ffmpeg, NO ejecuta
    def fake_run(cmd, **kwargs):
        mock_state["ffmpeg_calls"].append(cmd)
        # Crear un archivo output fake para que el OS lo encuentre después
        try:
            out_idx = -1  # último arg es el output_path
            output_path = cmd[out_idx]
            with open(output_path, "wb") as f:
                f.write(b"fake_output_mp4")
            # `output_dur` para validación final = la duración -t pasada al ffmpeg
            for i, arg in enumerate(cmd):
                if arg == "-t" and i + 1 < len(cmd):
                    mock_state["output_dur"] = float(cmd[i + 1])
                    break
        except Exception:
            pass
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    monkeypatch.setattr(editor_mod.subprocess, "run", fake_run)

    # 6. Stub de src.subtitles para captions
    fake_subtitles = MagicMock()

    def fake_transcribe(audio_path, model_size="small", language=None):
        mock_state["subtitles_called"] = True
        return [{"word": "hola", "start": 0.0, "end": 0.3}]

    fake_subtitles.transcribe = fake_transcribe
    fake_subtitles.render_karaoke_on_video = (
        lambda *a, **kw: open(a[3], "wb").write(b"final_with_captions")
    )
    monkeypatch.setitem(sys.modules, "src.subtitles", fake_subtitles)

    return {
        "voice_mp3": str(voice_mp3),
        "clip_paths": clip_paths,
        "tmp_path": tmp_path,
        "state": mock_state,
    }


# ---------------------------------------------------------------------------
# Helpers para inspeccionar los argumentos de ffmpeg
# ---------------------------------------------------------------------------
def _compose_cmd(state) -> list[str]:
    """Devuelve la llamada de compose principal (la que tiene -filter_complex).

    Hay otras llamadas a ffmpeg (silencedetect probe en
    `_measure_audio_without_tail_silence`) que NO tienen -filter_complex.
    """
    for cmd in state["ffmpeg_calls"]:
        if "-filter_complex" in cmd:
            return cmd
    return []


def _ffmpeg_filter_complex(cmd: list[str]) -> str:
    """Extrae el valor del flag `-filter_complex` del comando ffmpeg."""
    for i, a in enumerate(cmd):
        if a == "-filter_complex" and i + 1 < len(cmd):
            return cmd[i + 1]
    return ""


def _ffmpeg_t_value(cmd: list[str]) -> float:
    for i, a in enumerate(cmd):
        if a == "-t" and i + 1 < len(cmd):
            return float(cmd[i + 1])
    return -1.0


# ===========================================================================
# BUG A — xfade REAL, sin frames negros entre clips
# ===========================================================================
class TestNoBlackGaps:
    def test_filter_uses_xfade_not_concat(self, editor_env):
        """Con 2+ clips y crossfade>0, el filter_complex debe contener xfade."""
        editor_env["state"]["clip_durs"] = [10.0, 5.0]
        editor_env["state"]["audio_dur"] = 14.7

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"][:2],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.5,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        ffmpeg_cmd = _compose_cmd(editor_env["state"])
        fc = _ffmpeg_filter_complex(ffmpeg_cmd)
        # Debe haber xfade=transition=fade
        assert "xfade=transition=fade" in fc, (
            f"BUG A: filter NO usa xfade. filter_complex={fc[:200]}"
        )
        # NO debe usar el concat con padding negativo (el path moviepy buggy)
        assert "padding" not in fc

    def test_xfade_offset_calculation_2_clips(self, editor_env):
        """Para clips [10s, 5s] con trim 0.15 y crossfade 0.5, el offset
        del xfade debe ser ~9.35 (= 10 - 0.15 - 0.5)."""
        editor_env["state"]["clip_durs"] = [10.0, 5.0]
        editor_env["state"]["audio_dur"] = 14.5

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"][:2],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.5,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        fc = _ffmpeg_filter_complex(_compose_cmd(editor_env["state"]))
        # post-trim clip 0 = 9.85s; offset xfade = 9.85 - 0.5 = 9.35s
        assert "offset=9.350" in fc or "offset=9.35" in fc, (
            f"Offset xfade incorrecto. filter_complex contiene: {fc[fc.find('xfade'):fc.find('xfade')+100]}"
        )

    def test_xfade_chained_for_3_clips(self, editor_env):
        """3 clips deben generar 2 xfades encadenados (vx1 → vout)."""
        editor_env["state"]["clip_durs"] = [5.0, 5.0, 5.0]
        editor_env["state"]["audio_dur"] = 14.5

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

        fc = _ffmpeg_filter_complex(_compose_cmd(editor_env["state"]))
        # Debe haber 2 xfades (vx1 intermedio, vout final)
        n_xfades = fc.count("xfade=transition=fade")
        assert n_xfades == 2, f"Esperaba 2 xfades en 3 clips, encontró {n_xfades}"
        assert "[vx1]" in fc, "Falta etiqueta intermedia vx1"
        assert "[vout]" in fc

    def test_pro_singleshot_no_xfade(self, editor_env):
        """1 clip Pro: passthrough, sin xfade ni trim head."""
        editor_env["state"]["clip_durs"] = [15.0]
        editor_env["state"]["audio_dur"] = 14.8

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"][:1],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="single_shot_multishot",
            add_captions=False,
            crossfade_s=0.5,  # ignorado en singleshot
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        fc = _ffmpeg_filter_complex(_compose_cmd(editor_env["state"]))
        assert "xfade" not in fc
        # trim_head debe ser 0 → no hay trim=start=0.15
        assert "trim=start=0.15" not in fc


# ===========================================================================
# BUG B — Audio overflow → freeze frame, NUNCA pantalla negra ni audio truncado
# ===========================================================================
class TestNoBlackEnd:
    def test_audio_overflow_freezes_last_frame(self, editor_env):
        """Audio 19s, video 14.2s → audio íntegro + freeze del último frame
        para extender video hasta audio_dur+0.5s. NO se trunca audio."""
        editor_env["state"]["clip_durs"] = [10.0, 5.0]
        editor_env["state"]["audio_dur"] = 19.0  # overflow grave

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"][:2],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.5,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        fc = _ffmpeg_filter_complex(_compose_cmd(editor_env["state"]))
        # video_dur = (10-0.15) + (5-0.15) - 0.5 = 14.20s
        # Audio íntegro: atrim=0:19.000 (sin truncar)
        assert "atrim=0:19.000" in fc, (
            f"Audio debe estar íntegro (no truncado). filter={fc[:300]}"
        )
        # Freeze del último frame: tpad=stop_mode=clone:stop_duration=5.30
        # (= audio_dur 19 - video_dur 14.2 + 0.5 margen)
        assert "tpad=stop_mode=clone" in fc, (
            f"Falta tpad freeze frame. filter={fc[:300]}"
        )
        assert "stop_duration=5.300" in fc or "stop_duration=5.3" in fc, (
            f"Duración del freeze incorrecta. filter={fc[:300]}"
        )
        # NO afade en overflow (estrategia mayo 2026 — silencio sobre frame
        # estático en lugar de fade-out que cortaba el CTA)
        assert "afade=t=out" not in fc, (
            "Ya no usamos afade en overflow — freeze frame mantiene audio íntegro"
        )
        # `-t` final = audio_dur + 0.5 = 19.5s
        t_val = _ffmpeg_t_value(_compose_cmd(editor_env["state"]))
        assert abs(t_val - 19.5) < 0.1, f"-t debe ser ~19.5 (audio+0.5), fue {t_val}"

    def test_audio_underflow_keeps_video_duration(self, editor_env):
        """Audio 8s, video 14.2s → final_dur = 14.2s (mantiene video completo).

        Estrategia mayo 2026 (intento 5): NO recortamos el video al audio.
        El audio termina y los últimos frames del último clip se ven con
        silencio sobre ellos (no negro, video Atlas real). Profesional.
        """
        editor_env["state"]["clip_durs"] = [10.0, 5.0]
        editor_env["state"]["audio_dur"] = 8.0

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"][:2],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.5,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        # `-t` final = video_dur (14.2s), no audio_dur (8s)
        # video_dur = (10-0.15) + (5-0.15) - 0.5 = 14.20s
        t_val = _ffmpeg_t_value(_compose_cmd(editor_env["state"]))
        assert abs(t_val - 14.2) < 0.1, (
            f"-t debe ser video_dur 14.2s (mantener video completo), fue {t_val}"
        )

        fc = _ffmpeg_filter_complex(_compose_cmd(editor_env["state"]))
        assert "afade=t=out" not in fc
        assert "silenceremove" not in fc

        # Audio chain corta el voice a audio_dur (8s) y aplica `apad` para
        # rellenar con silencio hasta el final del video.
        assert "atrim=0:8.000" in fc, (
            f"Falta atrim=0:8.000 (audio cortado a audio_dur). filter={fc[:300]}"
        )
        assert "apad" in fc, (
            f"Falta `apad` (relleno de silencio sobre los últimos frames). filter={fc[:300]}"
        )

    def test_audio_synced_no_truncate(self, editor_env):
        """Audio y video casi iguales → ningún recorte de audio, atrim al final_dur."""
        editor_env["state"]["clip_durs"] = [10.0, 5.0]
        editor_env["state"]["audio_dur"] = 14.2  # match exacto

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"][:2],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.5,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )
        fc = _ffmpeg_filter_complex(_compose_cmd(editor_env["state"]))
        assert "afade=t=out" not in fc
        assert "silenceremove" not in fc, (
            "silenceremove agresivo NO debe estar — usar atrim quirúrgico al tail"
        )
        # final_dur = min(audio_dur, video_dur) ≈ 14.2; atrim al final_dur
        assert "atrim=0:14.2" in fc, f"Falta atrim=0:14.2. filter={fc[:300]}"
        assert "asetpts=PTS-STARTPTS[aout]" in fc


# ===========================================================================
# Validación post-export: ffprobe del output ≈ target_dur
# ===========================================================================
class TestPostExportValidation:
    def test_output_duration_logged(self, editor_env):
        """El `-t` pasado debe ≈ duración medida con ffprobe del output."""
        editor_env["state"]["clip_durs"] = [10.0, 5.0]
        editor_env["state"]["audio_dur"] = 14.2

        logs = []
        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"][:2],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.5,
            trim_head_s=0.15,
            log_callback=logs.append,
        )

        assert any("Vídeo final" in line and "s)" in line for line in logs)
        assert out.exists()

    def test_too_short_output_aborts(self, editor_env, monkeypatch):
        """Si el output queda <1s (síntoma de bug catastrófico), abortar."""
        editor_env["state"]["clip_durs"] = [10.0, 5.0]
        editor_env["state"]["audio_dur"] = 14.2

        # Sobrescribir _ffprobe_duration para devolver 0.5 cuando se llame
        # con el output_path (validación final)
        original = editor_mod._ffprobe_duration

        def short_output(path):
            if path.endswith("out.mp4") and not path.endswith(".base.mp4"):
                return 0.5
            return original(path)

        monkeypatch.setattr(editor_mod, "_ffprobe_duration", short_output)

        out = editor_env["tmp_path"] / "out.mp4"
        with pytest.raises(RuntimeError, match="duración inválida"):
            compose_shop_video(
                clip_paths=editor_env["clip_paths"][:2],
                voice_mp3=editor_env["voice_mp3"],
                output_path=str(out),
                strategy="multi_clip_anchor",
                add_captions=False,
                crossfade_s=0.5,
                trim_head_s=0.15,
                log_callback=lambda _: None,
            )


# ===========================================================================
# BUG-FIX 3 / FUNC 5 — language y trim_head_s configurables (regression)
# ===========================================================================
class TestLanguageAndTrim:
    def test_language_passed_to_whisper(self, editor_env):
        editor_env["state"]["clip_durs"] = [10.0, 5.0]
        editor_env["state"]["audio_dur"] = 14.2
        captured_lang = []

        # Reemplazar fake_transcribe para capturar
        import sys
        fs = sys.modules["src.subtitles"]

        def cap_transcribe(audio_path, model_size="small", language=None):
            captured_lang.append(language)
            return []

        fs.transcribe = cap_transcribe

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"][:2],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=True,
            language="es",
            crossfade_s=0.5,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )
        assert captured_lang == ["es"]

    def test_trim_head_15_in_filter(self, editor_env):
        """trim_head_s=0.15 debe aparecer en el filter de cada clip."""
        editor_env["state"]["clip_durs"] = [5.0, 5.0]
        editor_env["state"]["audio_dur"] = 9.5

        out = editor_env["tmp_path"] / "out.mp4"
        compose_shop_video(
            clip_paths=editor_env["clip_paths"][:2],
            voice_mp3=editor_env["voice_mp3"],
            output_path=str(out),
            strategy="multi_clip_anchor",
            add_captions=False,
            crossfade_s=0.3,
            trim_head_s=0.15,
            log_callback=lambda _: None,
        )

        fc = _ffmpeg_filter_complex(_compose_cmd(editor_env["state"]))
        assert fc.count("trim=start=0.15") == 2, (
            f"trim_head=0.15 debe aplicarse a los 2 clips. filter: {fc[:300]}"
        )
