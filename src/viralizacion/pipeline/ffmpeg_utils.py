"""Helpers ffmpeg/ffprobe compartidos por el pipeline de Viralización."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

OnLog = Callable[[str], None]


def run(cmd: list[str], on_log: OnLog | None = None, **kw) -> subprocess.CompletedProcess:
    line = "+ " + " ".join(str(c) for c in cmd)
    if on_log:
        on_log(line)
    else:
        print(line)
    return subprocess.run(cmd, check=True, **kw)


def ffprobe_duration(path: Path | str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def ffprobe_video_size(path: Path | str) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=s=x:p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    w, h = out.stdout.strip().split("x")
    return int(w), int(h)


def leading_silence(
    path: Path | str,
    start: float = 0.0,
    probe: float = 5.0,
    noise_db: int = -35,
    min_dur: float = 0.12,
) -> float:
    """Segundos de silencio REAL al principio de `start` en el audio.

    Hace falta además de los timings de Whisper porque Whisper redondea el
    arranque a 0: en `pablo3_full.mp3` daba la 1ª palabra en 0.00s cuando en
    el fichero hay 0.74s de aire. Esos 0.74s mudos al empezar un TikTok son
    scroll asegurado.

    Devuelve 0.0 si el audio arranca hablando o si ffmpeg no dice nada.
    """
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", f"{max(0.0, start):.3f}",
         "-t", f"{max(0.5, probe):.3f}", "-i", str(path),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    inicio_en_cero = False
    for linea in out.stderr.splitlines():
        if "silence_start:" in linea:
            try:
                t = float(linea.split("silence_start:")[1].split()[0])
            except (IndexError, ValueError):
                continue
            # Solo interesa el silencio pegado al principio de la ventana.
            inicio_en_cero = t < 0.05
        elif "silence_end:" in linea and inicio_en_cero:
            try:
                return max(0.0, float(linea.split("silence_end:")[1].split()[0]))
            except (IndexError, ValueError):
                return 0.0
    return 0.0


def is_valid_mp4(path: Path | str, min_duration: float = 5.0) -> bool:
    """True si el fichero existe, tiene moov y duración >= min_duration."""
    p = Path(path)
    if not p.is_file() or p.stat().st_size < 50_000:
        return False
    try:
        dur = ffprobe_duration(p)
    except (subprocess.CalledProcessError, ValueError):
        return False
    return dur >= min_duration
