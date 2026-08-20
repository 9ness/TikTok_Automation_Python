"""El reparto de la voz entre los dos clips no puede pedir metraje que no hay."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.nicho_pov_bof.pipeline.duration_match import probe_duration
from src.nicho_pov_bof_largo.pipeline import video_editor


def _clip(destino: Path, segundos: float) -> Path:
    """Un vídeo de color de `segundos`, que es lo que mide el reparto."""
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", f"color=c=black:s=64x64:d={segundos}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(destino),
    ], check=True)
    return destino


def _voz(destino: Path, segundos: float) -> Path:
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=mono:d={segundos}", str(destino),
    ], check=True)
    return destino


class TestReparto:
    def test_no_le_pide_a_un_clip_mas_de_lo_que_dura(self, tmp_path, monkeypatch):
        """Con la pausa al 20% y clips de 8s, un audio de 12s pedía 9,6s al
        segundo clip: 1,6s los ponía el rebobinado, teniendo de sobra en el
        otro. Ahora el corte se mueve lo justo."""
        clips = [_clip(tmp_path / "c1.mp4", 8), _clip(tmp_path / "c2.mp4", 8)]
        audio = _voz(tmp_path / "v.mp3", 12)
        # La pausa más larga cae al 20% del audio.
        monkeypatch.setattr(video_editor, "_punto_de_corte", lambda *a, **k: 2.4)

        objetivos: list[float] = []
        real = video_editor.match_video_to_audio

        def espia(video, objetivo, work, **kw):
            objetivos.append(objetivo)
            return real(video, objetivo, work, **kw)

        monkeypatch.setattr(video_editor, "match_video_to_audio", espia)
        video_editor._concatenar_cuadrado(clips, audio, tmp_path / "w")

        assert len(objetivos) == 2
        assert sum(objetivos) == pytest.approx(probe_duration(audio), abs=0.05)
        for o in objetivos:
            assert o <= 8.01, f"le pide {o:.2f}s a un clip de 8s"

    def test_si_la_pausa_ya_cabe_no_se_toca(self, tmp_path, monkeypatch):
        clips = [_clip(tmp_path / "c1.mp4", 8), _clip(tmp_path / "c2.mp4", 8)]
        audio = _voz(tmp_path / "v.mp3", 12)
        monkeypatch.setattr(video_editor, "_punto_de_corte", lambda *a, **k: 6.5)

        objetivos: list[float] = []
        real = video_editor.match_video_to_audio

        def espia(video, objetivo, work, **kw):
            objetivos.append(objetivo)
            return real(video, objetivo, work, **kw)

        monkeypatch.setattr(video_editor, "match_video_to_audio", espia)
        video_editor._concatenar_cuadrado(clips, audio, tmp_path / "w")

        assert objetivos[0] == pytest.approx(6.5, abs=0.01)


class TestClipsDeDistintaDuracion:
    """La herramienta que genera los clips ha dado vídeos de 10s antes y de 8s
    ahora, así que un vídeo de 3 o 4 clips puede llevarlos mezclados."""

    def test_reparte_en_proporcion_a_lo_que_dura_cada_uno(self, tmp_path, monkeypatch):
        clips = [
            _clip(tmp_path / "c1.mp4", 8),
            _clip(tmp_path / "c2.mp4", 10),
            _clip(tmp_path / "c3.mp4", 8),
        ]
        audio = _voz(tmp_path / "v.mp3", 25)

        objetivos: list[float] = []
        real = video_editor.match_video_to_audio

        def espia(video, objetivo, work, **kw):
            objetivos.append(objetivo)
            return real(video, objetivo, work, **kw)

        monkeypatch.setattr(video_editor, "match_video_to_audio", espia)
        video_editor._concatenar_cuadrado(clips, audio, tmp_path / "w")

        assert sum(objetivos) == pytest.approx(probe_duration(audio), abs=0.05)
        # A partes iguales serían 8,33s a cada uno y habría que rebobinar los
        # dos de 8s teniendo 1,7s sin usar en el de 10s.
        for objetivo, dura in zip(objetivos, (8, 10, 8)):
            assert objetivo <= dura + 0.01, f"pide {objetivo:.2f}s a un clip de {dura}s"
        assert objetivos[1] > objetivos[0], "al más largo le toca más voz"

    def test_si_no_hay_metraje_suficiente_se_reparte_igual_de_mal(self, tmp_path, monkeypatch):
        """Con menos vídeo que voz hay que estirar sí o sí; que el estirón se
        reparta y no caiga entero sobre uno."""
        clips = [
            _clip(tmp_path / "c1.mp4", 4),
            _clip(tmp_path / "c2.mp4", 4),
            _clip(tmp_path / "c3.mp4", 4),
        ]
        audio = _voz(tmp_path / "v.mp3", 18)

        objetivos: list[float] = []
        real = video_editor.match_video_to_audio

        def espia(video, objetivo, work, **kw):
            objetivos.append(objetivo)
            return real(video, objetivo, work, **kw)

        monkeypatch.setattr(video_editor, "match_video_to_audio", espia)
        video_editor._concatenar_cuadrado(clips, audio, tmp_path / "w")

        assert sum(objetivos) == pytest.approx(probe_duration(audio), abs=0.05)
        assert max(objetivos) - min(objetivos) < 0.1
