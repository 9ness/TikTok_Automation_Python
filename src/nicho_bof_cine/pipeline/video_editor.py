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

El factor sale de la voz de CADA vídeo, no de una constante. Si lo que pide la
voz se pasa del rango razonable (`VELOCIDAD_MIN/MAX` — más allá el movimiento
se arrastra y se nota), se aplica el tope y el resto lo cuadra el ajuste de
duración de siempre. Así el vídeo acaba clavado con la voz en todos los casos,
y en el rebobinado solo cae lo que la velocidad no ha podido absorber:

    voz 10,2s → velocidad 0,98 → listo
    voz 11,5s → velocidad 0,87 → listo
    voz 14,0s → velocidad 0,85 (tope) + 1,7s de ajuste
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


def _medidas(video: Path) -> tuple[int, int]:
    """`(ancho, alto)` del vídeo. `(1080, 1920)` si no se puede leer."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=s=x:p=0", str(video)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        w, h = (int(x) for x in out.split("x")[:2])
        return (w, h) if w > 0 and h > 0 else (1080, 1920)
    except Exception:  # noqa: BLE001
        return 1080, 1920


def concatenar(clips: list[Path], destino: Path, on_log: OnLog = _noop) -> Path:
    """Pega los clips uno detrás de otro, re-codificando.

    Se re-codifica en vez de copiar el flujo porque los dos clips vienen de
    generaciones distintas y pueden traer fps o codificación distintos; con
    `-c copy` eso da saltos en el audio/vídeo o directamente un fichero roto.
    """
    # Se igualan tamaño y relación de píxel antes de pegar: `concat` exige que
    # todas las entradas midan lo mismo y si no falla con "Invalid argument
    # (-22)". Pasó de verdad en el POV BOF Largo con un clip venido de otra
    # generación (720x1280 contra 1080x1920).
    ancho, alto = _medidas(clips[0])
    entradas: list[str] = []
    for c in clips:
        entradas += ["-i", str(c)]
    cadenas = "".join(
        f"[{i}:v:0]scale={ancho}:{alto}:force_original_aspect_ratio=decrease,"
        f"pad={ancho}:{alto}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}];"
        for i in range(len(clips))
    )
    filtro = (
        cadenas
        + "".join(f"[v{i}]" for i in range(len(clips)))
        + f"concat=n={len(clips)}:v=1:a=0[v]"
    )
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

    El factor sale de la duración de la voz de ESTE vídeo, no de una constante:
    cada frase locutada dura lo suyo. Si lo que pide la voz se sale del rango
    razonable, se aplica el tope y el resto lo cuadra después el ajuste de
    duración de siempre — así el hueco nunca cae entero en el rebobinado, que
    es lo que se ve en un paneo.

    Devuelve `(ruta, factor)`; 1.0 = no se ha tocado nada.
    """
    dur = probe_duration(video)
    if dur <= 0 or objetivo_s <= 0:
        return video, 1.0

    # factor < 1 = más lento (el vídeo dura más). Sale de la voz de ESTE
    # vídeo, no de una constante: cada frase locutada dura lo suyo.
    pedido = dur / objetivo_s
    # Se aplica lo que quepa dentro del rango razonable y NO se renuncia al
    # resto: lo que la velocidad no cubra lo remata después el ajuste de
    # siempre (recortar o alargar), igual que en el POV BOF. Antes, con una
    # voz muy larga, se descartaba el ajuste entero y todo el hueco caía en el
    # rebobinado — que es justo lo que canta en un paneo.
    factor = min(max(pedido, config.VELOCIDAD_MIN), config.VELOCIDAD_MAX)
    if abs(factor - 1.0) < 0.01:
        return video, 1.0
    if abs(pedido - factor) > 0.01:
        on_log(
            f"[cine] la voz pedía velocidad {pedido:.2f}; se aplica {factor:.2f} "
            "(el tope) y el resto lo cuadra el ajuste de duración"
        )

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
