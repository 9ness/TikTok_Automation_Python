"""Cola muda al final del audio (Viralización).

Un audio del banco de Pablo dura 51s pero deja de hablar en el 41: el vídeo
salía de 51s con los últimos diez mudos y parecía roto. Se detecta midiendo el
FICHERO con `silencedetect`.

El detector ya falló una vez de forma sutil —daba 0 siempre— porque
`silencedetect` CIERRA el último tramo al acabar el fichero e imprime su
`silence_end`, así que "el silencio sin `silence_end`" no identifica la cola.
De ahí que estos tests generen audios de verdad con ffmpeg en vez de fingir la
salida del comando: el fallo estaba justo en leerla.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.viralizacion.pipeline.ffmpeg_utils import ffprobe_duration, trailing_silence


def _audio(destino: Path, *, habla_s: float, silencio_s: float) -> Path:
    """Tono de `habla_s` seguido de `silencio_s` de nada."""
    partes = [f"sine=frequency=350:duration={habla_s}"]
    if silencio_s > 0:
        partes.append(f"anullsrc=r=44100:cl=mono:d={silencio_s}")
    entradas: list[str] = []
    for p in partes:
        entradas += ["-f", "lavfi", "-i", p]
    filtro = "".join(f"[{i}:a]" for i in range(len(partes)))
    subprocess.run(
        ["ffmpeg", "-y", *entradas,
         "-filter_complex", f"{filtro}concat=n={len(partes)}:v=0:a=1[a]",
         "-map", "[a]", str(destino)],
        check=True, capture_output=True,
    )
    return destino


class TestTrailingSilence:
    def test_detecta_la_cola_muda(self, tmp_path: Path):
        a = _audio(tmp_path / "con_cola.wav", habla_s=6.0, silencio_s=8.0)
        cola = trailing_silence(a, ffprobe_duration(a))
        assert 7.0 <= cola <= 8.5, f"cola detectada: {cola}"

    def test_audio_que_acaba_hablando_no_se_toca(self, tmp_path: Path):
        a = _audio(tmp_path / "sin_cola.wav", habla_s=8.0, silencio_s=0.0)
        assert trailing_silence(a, ffprobe_duration(a)) == 0.0

    def test_una_pausa_en_medio_no_cuenta_como_cola(self, tmp_path: Path):
        """Lo que se recorta es la cola, no una pausa dramática."""
        trozos = tmp_path / "pausa.wav"
        subprocess.run(
            ["ffmpeg", "-y",
             "-f", "lavfi", "-i", "sine=frequency=350:duration=4",
             "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=3",
             "-f", "lavfi", "-i", "sine=frequency=350:duration=4",
             "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[a]",
             "-map", "[a]", str(trozos)],
            check=True, capture_output=True,
        )
        assert trailing_silence(trozos, ffprobe_duration(trozos)) == 0.0

    @pytest.mark.parametrize("silencio", [0.4, 0.8])
    def test_el_aire_normal_de_una_frase_no_dispara(self, tmp_path: Path, silencio: float):
        """Por debajo del umbral se deja: es el respiro de cierre, no un fallo."""
        from src.viralizacion.pipeline.renderer import COLA_MUDA_MIN_S

        a = _audio(tmp_path / f"aire_{silencio}.wav", habla_s=6.0, silencio_s=silencio)
        assert trailing_silence(a, ffprobe_duration(a)) <= COLA_MUDA_MIN_S
