"""Montaje del vídeo de una prenda.

Es deliberadamente MÍNIMO comparado con el del Nicho POV BOF, porque este
nicho no lleva nada encima: ni gancho, ni título, ni CTA, ni flecha. La prenda
se enseña y ya. Lo único que se hace es:

1. Encuadrar a 1080x1920 (cover-fit), que es lo que pide TikTok, con la
   ampliación que se come la marca de agua del generador.
2. Quitar el audio. **Va mudo por defecto**: el operador le pone la música al
   publicar, y el audio que trae el vídeo generado no sirve para nada.
3. Opcionalmente, ponerle una voz del banco (hombre/mujer) si el operador la
   pide. Es la misma biblioteca de audios que usa el otro nicho.

La excepción es el catálogo de la web (Ropa Mujer/Hombre): ahí el clip sale de
VEO con el prompt del espejo, o sea que ya trae la voz de la creadora hablando
y sincronizada con los labios. Ese audio SÍ vale, y silenciarlo se carga el
vídeo entero — por eso existe `conservar_audio`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof import config as pov_config

OnLog = Callable[[str], None]


def _noop(_: str) -> None:
    return None


def _run(cmd: list[str], on_log: OnLog) -> None:
    on_log("+ " + " ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {proc.stderr[-500:]}")


def montar(
    video_in: Path,
    out_path: Path,
    *,
    voz: Path | None = None,
    conservar_audio: bool = False,
    on_log: OnLog = _noop,
) -> Path:
    """Encuadra a 9:16 y deja el vídeo mudo (o con la voz que se le pase).

    `-an` no es un descuido: el vídeo que sale del generador trae un audio
    ambiente que no aporta nada, y el operador quiere ponerle la música él al
    publicar.

    `conservar_audio` es justo lo contrario, y es para el catálogo de la web:
    el clip ya viene hablado por la creadora, sincronizado con los labios. Una
    voz del banco manda sobre esto — no tiene sentido pisar una voz con otra.
    """
    # Mismo encuadre que el resto de nichos, con la ampliación que se come la
    # marca de agua del generador.
    vf = pov_config.filtro_encuadre()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if voz is None and conservar_audio:
        # `-c:a aac` y no `copy`: el contenedor de salida cambia y algunos
        # clips llegan con audio en un códec que el MP4 de TikTok no traga.
        _run([
            "ffmpeg", "-y", "-v", "error", "-i", str(video_in),
            "-vf", vf, "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(out_path),
        ], on_log)
        on_log("[nicho_ropa] vídeo con SU audio (la voz que trae el clip)")
        return out_path

    if voz is None:
        _run([
            "ffmpeg", "-y", "-v", "error", "-i", str(video_in),
            "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-movflags", "+faststart", str(out_path),
        ], on_log)
        on_log("[nicho_ropa] vídeo mudo (sin voz ni música, a propósito)")
        return out_path

    # Con voz: el vídeo dura lo que dure la voz. `-shortest` corta por el más
    # corto de los dos, que es lo que evita quedarse con imagen congelada al
    # final si la voz acaba antes.
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video_in), "-i", str(voz),
        "-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-shortest",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(out_path),
    ], on_log)
    on_log(f"[nicho_ropa] vídeo con voz: {voz.name}")
    return out_path
