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
