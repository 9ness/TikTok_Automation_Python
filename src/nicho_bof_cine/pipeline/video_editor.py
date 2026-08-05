"""Montaje del Nicho BOF Cinematográfico.

Dos diferencias con el Nicho POV BOF, y solo dos: la entrada son DOS clips en
vez de uno, y la duración se cuadra cambiando la VELOCIDAD en vez de rebobinando
el final. Lo demás (texto quemado, flecha, voz, nivelado) es el mismo montador,
llamado al final.

**Por qué velocidad y no rebobinado.** En el POV BOF, cuando falta vídeo se
pega el tramo final invertido (ida y vuelta) y en un plano de mano no se nota.
Aquí el plano es un paneo de cámara continuo alrededor del producto: si va y
vuelve, se ve clarísimo. Ralentizar un paneo un 5% no lo nota nadie, así que se
estira el vídeo hasta la duración de la voz.

El cambio de velocidad tiene tope (`VELOCIDAD_MIN/MAX`). Pasado ese punto el
movimiento empieza a arrastrarse, y entonces es mejor dejar que el montador de
siempre recorte o alargue como sabe.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from src.nicho_bof_cine import config
from src.nicho_pov_bof.pipeline.duration_match import probe_duration
from src.nicho_pov_bof.pipeline.video_editor import build_video

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

    Se re-codifica en vez de copiar el flujo porque los dos clips vienen de
    generaciones distintas y pueden traer fps o codificación distintos; con
    `-c copy` eso da saltos en el audio/vídeo o directamente un fichero roto.
    """
    entradas: list[str] = []
    for c in clips:
        entradas += ["-i", str(c)]
    filtro = "".join(f"[{i}:v:0]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[v]"
    _run([
        "ffmpeg", "-y", "-v", "error", *entradas,
        "-filter_complex", filtro, "-map", "[v]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(destino),
    ], on_log)
    return destino


def ajustar_velocidad(
    video: Path, objetivo_s: float, destino: Path, on_log: OnLog = _noop,
) -> tuple[Path, float]:
    """Estira o encoge el vídeo hasta `objetivo_s` cambiando la velocidad.

    Devuelve `(ruta, factor)`. Con factor 1.0 no se ha tocado nada — o porque
    ya cuadraba, o porque el ajuste se salía del rango razonable y es mejor
    dejárselo al montador de siempre.
    """
    dur = probe_duration(video)
    if dur <= 0 or objetivo_s <= 0:
        return video, 1.0

    # factor < 1 = más lento (el vídeo dura más).
    factor = dur / objetivo_s
    if not (config.VELOCIDAD_MIN <= factor <= config.VELOCIDAD_MAX):
        on_log(
            f"[cine] el ajuste pedía velocidad {factor:.2f} "
            f"(vídeo {dur:.1f}s, voz {objetivo_s:.1f}s): fuera de rango, "
            "se deja que el montador recorte o alargue"
        )
        return video, 1.0
    if abs(factor - 1.0) < 0.01:
        return video, 1.0

    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video),
        "-filter:v", f"setpts={1 / factor:.6f}*PTS",
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(destino),
    ], on_log)
    on_log(
        f"[cine] vídeo a velocidad {factor:.3f} "
        f"({dur:.1f}s → {probe_duration(destino):.1f}s para una voz de {objetivo_s:.1f}s)"
    )
    return destino, factor


def montar(
    *,
    clips: list[Path],
    audio_path: Path,
    textos: dict,
    output_path: Path,
    work_dir: Path,
    layout: str = "gancho_cta_titulo",
    con_gancho: bool = True,
    con_titulo: bool = True,
    con_cta: bool = True,
    con_flecha: bool = True,
    semilla: str = "",
    on_log: OnLog = _noop,
    on_progress: OnProgress = _noop_progress,
) -> Path:
    """Monta el vídeo final a partir de los DOS clips."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    on_progress(0.05, "Pegando los clips…")
    pegado = concatenar([Path(c) for c in clips], work_dir / "00_concat.mp4", on_log)

    on_progress(0.15, "Cuadrando con la voz…")
    voz_s = probe_duration(Path(audio_path))
    ajustado, _factor = ajustar_velocidad(
        pegado, voz_s, work_dir / "00_speed.mp4", on_log,
    )

    return build_video(
        raw_video=ajustado,
        audio_path=Path(audio_path),
        textos=textos,
        output_path=Path(output_path),
        work_dir=work_dir,
        layout=layout,
        con_gancho=con_gancho,
        con_titulo=con_titulo,
        con_cta=con_cta,
        con_flecha=con_flecha,
        semilla=semilla or Path(output_path).stem,
        on_log=on_log,
        on_progress=on_progress,
    )
