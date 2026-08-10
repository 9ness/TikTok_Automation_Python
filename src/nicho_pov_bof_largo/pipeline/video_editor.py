"""Montaje del Nicho POV BOF Largo.

Capa fina: se cuadran los DOS clips con la voz y se pegan; de ahí en adelante es
el montador del Nicho POV BOF sin tocar nada — mismo bloque de gancho/título/CTA,
misma flecha, mismo mux de audio.

**No se toca la velocidad ni se recorta el guion** (el prompt del curso va tal
cual). La duración la manda SIEMPRE la voz, y como los guiones salen de ~18 a
~25s según la voz, el vídeo se ajusta a esa duración.

Reparto entre clips (lo que pidió el operador): en vez de cuadrar el vídeo
entero contra el audio —que dejaba TODO el alargue al final, sobre el segundo
clip— cada clip se cuadra a SU parte del audio (`audio/2` cada uno). Así, con
una voz de 25s, en vez de un clip de 10s y otro de 15s salen dos de ~12,5s: el
rebobinado se reparte y se nota menos. La técnica de alargar/recortar es la
misma de siempre (`match_video_to_audio`: rebobina el tramo final si falta,
recorta si sobra); solo cambia que se aplica por clip.
"""

from __future__ import annotations

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


def _concatenar_cuadrado(
    clips: list[Path], audio_path: Path, work_dir: Path, on_log: OnLog = _noop,
) -> Path:
    """Cuadra cada clip con SU parte del audio y luego los pega.

    Reparte la duración de la voz a partes iguales entre los clips (`audio/N`).
    Cada clip se alarga o recorta a su objetivo con `match_video_to_audio` —el
    mismo rebobinado de tramo final que usa el POV BOF—, así que el alargue no
    cae entero sobre el último clip. La suma da la duración del audio; el
    `match_video_to_audio` que hace `build_video` después ya solo recorta al
    milímetro.

    Si no se puede medir el audio (raro), se cae al pegado directo de siempre y
    que `build_video` cuadre el conjunto.
    """
    try:
        audio_dur = probe_duration(audio_path)
    except Exception as e:
        on_log(f"[pov_bof_largo] no se pudo medir el audio ({e}); pego sin cuadrar por clip")
        return concatenar(clips, work_dir / "00_pegado.mp4", on_log)

    n = max(1, len(clips))
    objetivo = audio_dur / n
    on_log(
        f"[pov_bof_largo] voz {audio_dur:.2f}s repartida entre {n} clips → "
        f"~{objetivo:.2f}s cada uno"
    )
    cuadrados: list[Path] = []
    for i, clip in enumerate(clips, start=1):
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
