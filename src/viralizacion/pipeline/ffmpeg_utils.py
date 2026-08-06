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


def trailing_silence(
    path: Path | str,
    end: float,
    probe: float = 20.0,
    noise_db: int = -35,
    min_dur: float = 0.35,
) -> float:
    """Segundos de silencio REAL pegados al final de `end` en el audio.

    El hermano de `leading_silence`, y hace falta por lo mismo: hay audios del
    banco que traen una cola muda larga. `..._la_vida_es_para_vivirla_c2.mp3`
    dura 51,2s pero Pablo deja de hablar en el 41 — el vídeo salía de 51s con
    los últimos 10 mudos, y desde fuera parece que el vídeo se ha roto.

    Se mide el FICHERO en vez de fiarse de los timings de Whisper: Whisper se
    come palabras sueltas del final igual que del principio, y cortar por su
    última palabra se llevaría habla real por delante.

    Devuelve 0.0 si el audio acaba hablando o si ffmpeg no dice nada.
    """
    end = float(end)
    inicio = max(0.0, end - max(1.0, probe))
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", f"{inicio:.3f}",
         "-t", f"{end - inicio:.3f}", "-i", str(path),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    # Interesa el ÚLTIMO tramo de silencio, y solo si llega hasta el final: una
    # pausa a media frase (dramática) no se toca.
    #
    # OJO: no vale con "el silencio que no tiene `silence_end`". Al acabar el
    # fichero, `silencedetect` CIERRA el tramo abierto e imprime su
    # `silence_end` igual — así que hay que comparar ese final con el final de
    # la ventana, no dar por hecho que falta.
    ultimo_inicio: float | None = None
    ultimo_fin: float | None = None
    for linea in out.stderr.splitlines():
        if "silence_start:" in linea:
            try:
                ultimo_inicio = inicio + float(linea.split("silence_start:")[1].split()[0])
                ultimo_fin = None
            except (IndexError, ValueError):
                ultimo_inicio = None
        elif "silence_end:" in linea and ultimo_inicio is not None:
            try:
                ultimo_fin = inicio + float(
                    linea.split("silence_end:")[1].split()[0].rstrip("|")
                )
            except (IndexError, ValueError):
                ultimo_fin = None
    if ultimo_inicio is None:
        return 0.0
    # Sin cerrar, o cerrado justo al borde del fichero → es la cola.
    if ultimo_fin is not None and ultimo_fin < end - 0.25:
        return 0.0
    return max(0.0, end - ultimo_inicio)


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
