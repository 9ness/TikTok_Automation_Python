"""Efecto «clon» del modo Conversación (17/11/2026).

Una persona graba con trípode haciendo de DOS personajes por turnos: uno a la izquierda y
otro a la derecha (el duelo «mío vs tuyo» de la bici). En el bruto solo sale uno a la vez;
el resultado que queremos tiene a los DOS en el plano: la mitad de quien habla va en directo
y la del otro sale de una toma suya (ida y vuelta, para que no salte), unidas con un borde suave.

Solo se usa cuando `hablantes.detectar` separó a las personas POR IMAGEN (cámara fija y un
lado para cada una). Nunca lanza: si algo falla se devuelve None y se sigue sin efecto.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

FUNDIDO_PX = 70      # anchura del borde suave entre las dos mitades (sobre 1080)
MARGEN_S = 0.5       # se quita de cada lado de la toma del otro (ahí cruza el plano)
TOMA_MAX_S = 3.0     # toma del que escucha: hasta 3 s, en ida y vuelta
TOMA_MIN_S = 0.8


def _sh(cmd: list[str], timeout: int = 900) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "ffmpeg falló")[-300:])


def _info(path: str) -> tuple[int, int, float, float, bool]:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", path],
                       capture_output=True, text=True, timeout=60)
    d = json.loads(r.stdout or "{}")
    v = next(s for s in d["streams"] if s.get("codec_type") == "video")
    num, den = (v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den or 1) if float(num) else 30.0
    audio = any(s.get("codec_type") == "audio" for s in d["streams"])
    return int(v["width"]), int(v["height"]), fps, float(d["format"]["duration"]), audio


def _toma_del_otro(tramos: list[list], i: int) -> tuple[float, float] | None:
    """Trozo (s0, s1) de la otra persona para rellenar su mitad durante el turno i:
    el turno suyo más largo entre los vecinos (si no hay, el más largo de todos)."""
    yo = tramos[i][2]
    otros = [(j, a, b) for j, (a, b, p) in enumerate(tramos) if p != yo]
    if not otros:
        return None
    vecinos = [o for o in otros if abs(o[0] - i) == 1] or otros
    _, a, b = max(vecinos, key=lambda o: o[2] - o[1])
    if b - a < TOMA_MIN_S + 0.2:
        _, a, b = max(otros, key=lambda o: o[2] - o[1])
    m = MARGEN_S if b - a > TOMA_MIN_S + 2 * MARGEN_S else 0.1
    s0, s1 = a + m, b - m
    if s1 - s0 > TOMA_MAX_S:
        c = (s0 + s1) / 2
        s0, s1 = c - TOMA_MAX_S / 2, c + TOMA_MAX_S / 2
    return (s0, s1) if s1 - s0 >= TOMA_MIN_S else None


def componer(path: str, salida: str, tramos: list[list], izquierda: int, corte: float,
             on_log: Callable[[str], None] = lambda _: None) -> str | None:
    """Vídeo con los dos personajes a la vez, o None si no se pudo."""
    try:
        path, salida = str(Path(path).resolve()), str(Path(salida).resolve())
        w, h, fps, dur, audio = _info(path)
        xs = int(round(max(0.3, min(0.7, corte)) * w))
        tmp = Path(tempfile.mkdtemp(prefix="clon_", dir=str(Path(salida).parent)))
        # Máscaras (blanco = se ve la toma del otro): una si el otro está a la izquierda, otra a la derecha.
        mascaras = {}
        for lado in ("izq", "der"):
            m = tmp / f"m_{lado}.png"
            f = FUNDIDO_PX * w / 1080
            expr = (f"255*clip(({xs}+{f / 2}-X)/{f},0,1)" if lado == "izq"
                    else f"255*clip((X-{xs}+{f / 2})/{f},0,1)")
            _sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={w}x{h}:d=0.1",
                 "-vf", f"format=gray,geq=lum='{expr}'", "-frames:v", "1", str(m)])
            mascaras[lado] = m
        tomas: dict[tuple, Path] = {}
        partes: list[Path] = []
        enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", f"{fps:.3f}"]
        for i, (t0, t1, p) in enumerate(tramos):
            t1 = min(t1, dur)
            if t1 - t0 < 1 / fps:
                continue
            toma = _toma_del_otro(tramos, i)
            parte = tmp / f"p{i:03d}.mp4"
            if toma is None:
                _sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", path,
                     *enc, *(["-c:a", "aac", "-b:a", "192k"] if audio else ["-an"]), str(parte)])
                partes.append(parte)
                continue
            if toma not in tomas:  # ida y vuelta de la toma del otro (sin saltos al repetir)
                tp = tmp / f"t{len(tomas):03d}.mp4"
                _sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{toma[0]:.3f}", "-t", f"{toma[1] - toma[0]:.3f}",
                     "-i", path, "-an", "-filter_complex", "[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0",
                     *enc, str(tp)])
                tomas[toma] = tp
            otro = 1 - p if p in (0, 1) else 1
            lado = "izq" if otro == izquierda else "der"
            _sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", path,
                 "-stream_loop", "-1", "-i", str(tomas[toma]), "-loop", "1", "-i", str(mascaras[lado]),
                 "-filter_complex", "[2:v]format=gray[m];[1:v][m]alphamerge[o];[0:v][o]overlay=0:0:shortest=1[v]",
                 "-map", "[v]", *(["-map", "0:a", "-c:a", "aac", "-b:a", "192k"] if audio else []),
                 "-t", f"{t1 - t0:.3f}", *enc, str(parte)])
            partes.append(parte)
        if not partes:
            return None
        lista = tmp / "lista.txt"
        lista.write_text("".join(f"file '{x}'\n" for x in partes), encoding="utf-8")
        _sh(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy",
             "-movflags", "+faststart", salida])
        on_log(f"[clon] {len(partes)} turnos con los dos personajes en el plano")
        return salida
    except Exception as e:  # noqa: BLE001 — el efecto nunca rompe la edición
        on_log(f"[clon] ⚠️ No se pudo juntar a los dos personajes: {str(e)[:200]}")
        return None
    finally:
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)  # type: ignore[possibly-undefined]
        except Exception:  # noqa: BLE001
            pass
