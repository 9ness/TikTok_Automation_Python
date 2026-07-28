"""Cuadra la duración del vídeo con la del audio.

Los vídeos que genera Veo3/Kling duran ~10s y las frases locutadas rondan
12-14s, así que lo habitual es que FALTE vídeo.

- **Audio más corto** → se recorta el final del vídeo.
- **Audio más largo** → se alarga el vídeo rebobinando su tramo final: se pega
  el último trozo invertido (ida y vuelta) y se repite hasta cubrir. Se hace
  así en vez de ralentizar porque estirar un 20-40% deforma el gesto de la
  mano y se nota mucho; el rebobinado mantiene la velocidad natural del
  movimiento y en un POV pasa desapercibido.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof import config

OnLog = Callable[[str], None]
_noop: OnLog = lambda _: None


def _run(cmd: list[str], on_log: OnLog = _noop) -> None:
    on_log("+ " + " ".join(cmd[:8]) + (" …" if len(cmd) > 8 else ""))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {proc.stderr[-400:]}")


def probe_duration(path: Path | str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _build_pingpong(video: Path, work: Path, needed: float, on_log: OnLog) -> Path:
    """Alarga el vídeo pegando su tramo final invertido, tantas veces como haga falta."""
    src_dur = probe_duration(video)
    # Tramo a rebobinar: ni tan corto que se note el rebote, ni más largo que
    # el propio vídeo.
    tail = min(config.REVERSE_TAIL_MAX_S, max(1.0, src_dur * 0.4))
    tail_path = work / "tail_rev.mp4"
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-sseof", f"-{tail:.3f}", "-i", str(video),
        "-vf", "reverse", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        str(tail_path),
    ], on_log)

    # Cuántos pares ida+vuelta hacen falta para cubrir lo que falta.
    segments = [video]
    have = src_dur
    forward = None
    while have < needed:
        segments.append(tail_path)
        have += tail
        if have >= needed:
            break
        # Tras el rebobinado, volver hacia delante para no encadenar dos
        # marchas atrás seguidas (se vería como un tirón).
        if forward is None:
            forward = work / "tail_fwd.mp4"
            _run([
                "ffmpeg", "-y", "-v", "error",
                "-sseof", f"-{tail:.3f}", "-i", str(video),
                "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                str(forward),
            ], on_log)
        segments.append(forward)
        have += tail

    listfile = work / "concat.txt"
    listfile.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in segments), encoding="utf-8"
    )
    out = work / "extended.mp4"
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an",
        str(out),
    ], on_log)
    on_log(
        f"[duracion] vídeo alargado {src_dur:.1f}s → {probe_duration(out):.1f}s "
        f"rebobinando {tail:.1f}s ({len(segments) - 1} tramos)"
    )
    return out


def match_video_to_audio(
    video: Path,
    audio_dur: float,
    work: Path,
    *,
    on_log: OnLog = _noop,
) -> Path:
    """Devuelve un vídeo que dura EXACTAMENTE `audio_dur`."""
    work.mkdir(parents=True, exist_ok=True)
    video_dur = probe_duration(video)
    on_log(f"[duracion] vídeo {video_dur:.2f}s · audio {audio_dur:.2f}s")

    source = video
    if video_dur < audio_dur - 0.05:
        source = _build_pingpong(video, work, audio_dur, on_log)

    # Recorte final exacto (vale tanto si sobraba de origen como si el
    # rebobinado se pasó un poco).
    out = work / "matched.mp4"
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(source), "-t", f"{audio_dur:.3f}",
        "-vf", f"fps={config.TARGET_FPS}",
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-movflags", "+faststart", str(out),
    ], on_log)
    on_log(f"[duracion] resultado {probe_duration(out):.2f}s")
    return out
