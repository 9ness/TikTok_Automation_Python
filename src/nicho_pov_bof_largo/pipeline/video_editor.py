"""Montaje del Nicho POV BOF Largo.

Capa fina: se pegan los DOS clips y de ahí en adelante es el montador del Nicho
POV BOF sin tocar nada — mismo bloque de gancho/título/CTA, misma flecha, mismo
mux de audio.

Lo que NO se hace aquí, a diferencia del BOF Cinematográfico: **no se toca la
velocidad**. Allí hay que estirar porque el plano es un paneo continuo y el
rebobinado canta; aquí sobra vídeo casi siempre (dos clips de 10s contra un
guion de ~18-20s), y lo que pidió el operador es justamente que *"si el audio
son 18 segundos pues se corta el vídeo al final"*. De eso ya se encarga
`match_video_to_audio` dentro de `build_video`: recorta a la duración exacta de
la voz, y si por lo que sea faltara vídeo lo alarga rebobinando.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

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

    on_progress(0.02, f"🔗 Uniendo {len(clips)} clips…")
    pegado = concatenar([Path(c) for c in clips], work_dir / "00_pegado.mp4", on_log)

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
