"""Quitar la música de fondo de un clip, dejando solo la voz.

Los clips que salen de YouTube traen la sintonía del programa por debajo. En
los de Pablo Motos está unos 23 dB bajo la voz — poco, pero se nota, y al
montarlo con la música que le pone el operador al publicar quedan dos músicas
peleándose.

Se usa Demucs (separación de fuentes) y nos quedamos con la pista de voz.
Tarda ~1,2x la duración del audio en CPU, así que va en la cola, nunca en una
petición HTTP.

**No se aplica solo.** Separar voz de música deja a veces un punto metálico en
la voz, y eso solo se juzga escuchando: el operador decide clip a clip.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from src.viralizacion import config

OnLog = Callable[[str], None]


def _noop(_: str) -> None:
    return None


# Mismos valores que la voz del pipeline: si el clip limpio sonara más flojo
# que los demás, el lote saldría descompensado.
LUFS_OBJETIVO = -11.0
TECHO_TP = -1.5


def disponible() -> bool:
    try:
        import demucs  # noqa: F401

        return True
    except ImportError:
        return False


def separar_voz(
    audio: Path, *, tmp_dir: Path | None = None, on_log: OnLog = _noop,
) -> tuple[Path, Path]:
    """Devuelve `(voz, fondo)`. Los dos en MP3, en un temporal.

    El `fondo` se devuelve además de la voz porque es lo que permite comprobar
    QUÉ se ha quitado sin tener que fiarse: se sube 12 dB y se escucha.
    """
    if not disponible():
        raise RuntimeError(
            "Demucs no está instalado. Se instala a mano porque meterlo en "
            "requirements.txt obliga a reconstruir la capa de pip entera y el "
            "disco del VPS no da:\n"
            "    docker exec tiktok-api pip install --no-cache-dir demucs==4.1.0"
        )
    trabajo = Path(tmp_dir or tempfile.mkdtemp(prefix="voz_limpia_"))
    trabajo.mkdir(parents=True, exist_ok=True)

    on_log(f"[voz_limpia] separando voz y música de {audio.name}…")
    proc = subprocess.run(
        [
            "python3", "-m", "demucs", "--two-stems=vocals",
            "-o", str(trabajo), "--mp3", "--mp3-bitrate", "192", str(audio),
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Demucs falló: {proc.stderr[-400:]}")

    # Demucs escribe en <out>/<modelo>/<nombre sin extensión>/.
    carpeta = next((p for p in trabajo.rglob(audio.stem) if p.is_dir()), None)
    if carpeta is None:
        raise RuntimeError(f"Demucs no dejó salida para {audio.name}")
    voz, fondo = carpeta / "vocals.mp3", carpeta / "no_vocals.mp3"
    if not voz.is_file():
        raise RuntimeError("Demucs no generó la pista de voz.")
    return voz, fondo


def limpiar(
    audio: Path, destino: Path, *, tmp_dir: Path | None = None, on_log: OnLog = _noop,
) -> Path:
    """Deja en `destino` el audio con solo la voz, ya nivelado."""
    voz, _fondo = separar_voz(audio, tmp_dir=tmp_dir, on_log=on_log)
    destino.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(voz),
        "-af",
        f"loudnorm=I={LUFS_OBJETIVO}:TP={TECHO_TP}:LRA=11,"
        "alimiter=limit=0.9:level=disabled",
        "-b:a", config.FFMPEG_AUDIO_BITRATE, str(destino),
    ]
    on_log("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)
    on_log(f"[voz_limpia] {destino.name} listo")
    return destino


def limpiar_en_sitio(audio: Path, *, on_log: OnLog = _noop) -> Path:
    """Sustituye el clip por su versión limpia, guardando el original al lado.

    El original se conserva en `_con_musica/` porque la separación no siempre
    queda bien y hay que poder volver atrás sin re-descargar nada.
    """
    respaldo_dir = audio.parent / "_con_musica"
    respaldo_dir.mkdir(parents=True, exist_ok=True)
    respaldo = respaldo_dir / audio.name
    if not respaldo.exists():
        shutil.copy2(audio, respaldo)
        on_log(f"[voz_limpia] original guardado en {respaldo.parent.name}/")

    with tempfile.TemporaryDirectory(prefix="voz_limpia_") as tmp:
        salida = Path(tmp) / audio.name
        limpiar(respaldo, salida, tmp_dir=Path(tmp) / "demucs", on_log=on_log)
        shutil.copy2(salida, audio)
    return audio
