"""Montaje del Nicho POV BOF Largo.

Capa fina: se cuadran los DOS clips con la voz y se pegan; de ahí en adelante es
el montador del Nicho POV BOF sin tocar nada — mismo bloque de gancho/título/CTA,
misma flecha, mismo mux de audio.

**No se toca la velocidad ni se recorta el guion** (el prompt del curso va tal
cual). La duración la manda SIEMPRE la voz, y como los guiones salen de ~18 a
~25s según la voz, el vídeo se ajusta a esa duración.

Reparto entre clips (lo que pidió el operador): en vez de cuadrar el vídeo
entero contra el audio —que dejaba TODO el alargue al final, sobre el segundo
clip— cada clip se cuadra a SU parte del audio. Así, con una voz de 25s, en vez
de un clip de 10s y otro de 15s salen dos de ~12,5s: el rebobinado se reparte y
se nota menos. La técnica de alargar/recortar es la misma de siempre
(`match_video_to_audio`: rebobina el tramo final si falta, recorta si sobra);
solo cambia que se aplica por clip.

El PUNTO de reparto no es la mitad exacta: se busca una **minipausa** de la voz
cerca del centro (`_punto_de_corte` con `silencedetect`) para que el cambio de
vídeo caiga en un silencio y quede orgánico, no a mitad de palabra. Si no hay
pausa aprovechable, se parte por la mitad.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof.pipeline.duration_match import (
    match_video_to_audio,
    probe_duration,
)
from src.nicho_pov_bof.pipeline.video_editor import build_video, layout_for_producto

OnLog = Callable[[str], None]
OnProgress = Callable[[float, str], None]

_noop: OnLog = lambda _msg: None
_noop_progress: OnProgress = lambda _p, _m: None


def _run(cmd: list[str], on_log: OnLog) -> None:
    on_log("+ " + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {proc.stderr[-500:]}")


def concatenar(clips: list[Path], destino: Path, on_log: OnLog = _noop) -> Path:
    """Pega los clips uno detrás de otro, re-codificando.

    Se re-codifica en vez de copiar el flujo porque los clips vienen de
    generaciones distintas y pueden traer fps o codificación distintos; con
    `-c copy` eso da saltos o directamente un fichero roto.
    """
    entradas: list[str] = []
    for c in clips:
        entradas += ["-i", str(c)]
    filtro = (
        "".join(f"[{i}:v:0]" for i in range(len(clips)))
        + f"concat=n={len(clips)}:v=1:a=0[v]"
    )
    _run([
        "ffmpeg", "-y", "-v", "error", *entradas,
        "-filter_complex", filtro, "-map", "[v]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(destino),
    ], on_log)
    return destino


def _detectar_silencios(audio_path: Path) -> list[tuple[float, float]]:
    """Tramos de silencio (inicio, fin) de la voz, vía `silencedetect`.

    Umbral -35 dB y 0,12s: las pausas naturales entre frases (la voz ya viene
    con los silencios capados a ~0,3s en `voz.py`) se detectan sin contar como
    silencio los tramos suaves dentro de una palabra.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(audio_path),
         "-af", "silencedetect=noise=-35dB:d=0.12", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    silencios: list[tuple[float, float]] = []
    inicio: float | None = None
    for linea in proc.stderr.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", linea)
        if m:
            inicio = float(m.group(1))
            continue
        m = re.search(r"silence_end:\s*(-?[\d.]+)", linea)
        if m and inicio is not None:
            silencios.append((inicio, float(m.group(1))))
            inicio = None
    return silencios


def _punto_de_corte(audio_path: Path, dur: float, on_log: OnLog) -> float | None:
    """Instante donde partir los DOS clips para que el cambio caiga en una
    minipausa de la voz, no a mitad de palabra.

    Busca el silencio cuyo centro esté MÁS cerca de la mitad del audio, pero sin
    salirse de [30%, 70%] para que los dos clips no queden demasiado desiguales.
    Devuelve `None` si no hay ninguna pausa aprovechable (voz muy seguida) → se
    parte por la mitad como antes.
    """
    objetivo = dur / 2
    lo, hi = dur * 0.30, dur * 0.70
    mejor: float | None = None
    mejor_dist = 0.0
    for inicio, fin in _detectar_silencios(audio_path):
        centro = (inicio + fin) / 2
        if centro < lo or centro > hi:
            continue
        dist = abs(centro - objetivo)
        if mejor is None or dist < mejor_dist:
            mejor, mejor_dist = centro, dist
    if mejor is not None:
        on_log(
            f"[pov_bof_largo] corte en pausa a {mejor:.2f}s "
            f"(mitad exacta era {objetivo:.2f}s)"
        )
    else:
        on_log("[pov_bof_largo] sin pausa aprovechable cerca de la mitad; parto por la mitad")
    return mejor


def _concatenar_cuadrado(
    clips: list[Path], audio_path: Path, work_dir: Path, on_log: OnLog = _noop,
) -> Path:
    """Cuadra cada clip con SU parte del audio y luego los pega.

    Reparte la duración de la voz entre los clips y cuadra cada uno a su objetivo
    con `match_video_to_audio` —el mismo rebobinado de tramo final que usa el
    POV BOF—, así que el alargue no cae entero sobre el último clip. La suma da
    la duración del audio; el `match_video_to_audio` de `build_video` ya solo
    recorta al milímetro.

    Con DOS clips, el punto de reparto se busca en una minipausa de la voz
    (`_punto_de_corte`) para que el cambio de vídeo quede orgánico y no a mitad
    de palabra; si no hay pausa, se parte por la mitad. Con otro número de clips
    se reparte a partes iguales.

    Si no se puede medir el audio (raro), se cae al pegado directo de siempre y
    que `build_video` cuadre el conjunto.
    """
    try:
        audio_dur = probe_duration(audio_path)
    except Exception as e:
        on_log(f"[pov_bof_largo] no se pudo medir el audio ({e}); pego sin cuadrar por clip")
        return concatenar(clips, work_dir / "00_pegado.mp4", on_log)

    n = max(1, len(clips))
    if n == 2:
        corte = _punto_de_corte(audio_path, audio_dur, on_log)
        primero = corte if corte is not None else audio_dur / 2
        objetivos = [primero, audio_dur - primero]
    else:
        objetivos = [audio_dur / n] * n
    on_log(
        f"[pov_bof_largo] voz {audio_dur:.2f}s → clips de "
        + ", ".join(f"{o:.2f}s" for o in objetivos)
    )
    cuadrados: list[Path] = []
    for i, (clip, objetivo) in enumerate(zip(clips, objetivos), start=1):
        destino = work_dir / f"clip{i}_cuadrado"
        cuadrados.append(
            match_video_to_audio(clip, objetivo, destino, on_log=on_log)
        )
    return concatenar(cuadrados, work_dir / "00_pegado.mp4", on_log)


def montar(
    *,
    clips: list[Path],
    audio_path: Path,
    textos: dict,
    output_path: Path,
    work_dir: Path,
    producto: str = "",
    semilla: str = "",
    con_gancho: bool = True,
    con_titulo: bool = True,
    con_cta: bool = True,
    con_flecha: bool = True,
    on_log: OnLog = _noop,
    on_progress: OnProgress = _noop_progress,
) -> Path:
    """Monta el vídeo final de un producto a partir de sus clips."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    on_progress(0.02, f"🔗 Cuadrando y uniendo {len(clips)} clips…")
    pegado = _concatenar_cuadrado(
        [Path(c) for c in clips], Path(audio_path), work_dir, on_log,
    )

    def _progreso(pct: float, label: str) -> None:
        on_progress(0.05 + pct * 0.95, label)

    return build_video(
        raw_video=pegado,
        audio_path=Path(audio_path),
        textos=textos or {},
        output_path=Path(output_path),
        work_dir=work_dir,
        layout=layout_for_producto(producto or semilla, (textos or {}).get("cta", "")),
        con_gancho=con_gancho,
        con_titulo=con_titulo,
        con_cta=con_cta,
        con_flecha=con_flecha,
        semilla=semilla or Path(output_path).stem,
        on_log=on_log,
        on_progress=_progreso,
    )
