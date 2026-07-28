"""Banco de audios locutados del Nicho POV BOF (Programa 4 — Tiktok Shop AI Pro).

Los audios viven en Drive: `TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF/audios/{hombre,mujer}/`,
nombrados `hombre1_frase1.mp3` (voz, frase). El operador solo elige sexo; la
frase y la voz concretas se sortean (`pick_random`).

Por qué recortar silencios aquí y no con `editor_auto/tools/silence_cutter.py`:
ese módulo son ~7000 líneas con varias pasadas de IA (Whisper + heurísticas +
correcciones) pensadas para vídeos largos con pausas irregulares — un cañón
para recortar el silencio inicial y un par de huecos de una frase corta de
10-14s. Aquí basta un filtro de ffmpeg (`silenceremove`), mucho más barato y
determinista.
"""

from __future__ import annotations

import os
import random
import subprocess
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof import config
from src.nicho_pov_bof.pipeline.duration_match import probe_duration

OnLog = Callable[[str], None]
_noop: OnLog = lambda _msg: None

_SEXOS = ("hombre", "mujer")
_AUDIO_EXTS = {".mp3", ".wav", ".m4a"}

# Filtro sugerido: recorta el silencio INICIAL (una sola pasada, `start_*`) y
# todos los INTERMEDIOS (`stop_periods=-1` = todas las que encuentre). Los
# umbrales son conservadores (-40dB) para no comerse sílabas flojas de la voz.
_SILENCEREMOVE_FILTER = (
    "silenceremove=start_periods=1:start_duration=0.1:start_threshold=-40dB:"
    "stop_periods=-1:stop_duration=0.35:stop_threshold=-40dB"
)

# Por debajo de esto asumimos que el filtro se comió la frase entera (bug,
# audio corrupto o umbral mal calibrado para esa grabación en concreto) — se
# prefiere devolver el original antes que un mp3 casi mudo.
_MIN_VALID_DURATION_S = 3.0

# Subcarpeta donde se cachea la versión ya recortada, hermana del original.
_PROCESADOS_DIRNAME = "_procesados"


def mount_root() -> Path | None:
    """Raíz local del Drive montado por rclone, si está disponible.

    Mismo criterio que `src/viralizacion/services/drive_uploader.py:_mount_root()`
    (el container de la API no trae el binario `rclone`, así que la única vía
    consistente para leer/escribir es el mount FUSE: `/mnt/drive` en el
    container, `~/gdrive` en el host). Se expone público (no `_mount_root`)
    porque el runner de vídeo (`src/queue/runners.py`) también lo necesita
    para publicar el resultado en Drive.
    """
    candidates = [
        os.getenv("DRIVE_MOUNT_ROOT"),
        "/mnt/drive",
        str(Path.home() / "gdrive"),
    ]
    for c in candidates:
        if c and Path(c).is_dir():
            return Path(c)
    return None


def _audios_dir(sexo: str) -> Path | None:
    sexo = (sexo or "").strip().lower()
    if sexo not in _SEXOS:
        raise ValueError(f"sexo debe ser 'hombre' o 'mujer', recibido: {sexo!r}")
    root = mount_root()
    if root is None:
        return None
    return root / config.DRIVE_UPLOAD_ROOT / "audios" / sexo


def list_audios(sexo: str) -> list[Path]:
    """Audios ORIGINALES disponibles para un sexo (no incluye `_procesados/`)."""
    d = _audios_dir(sexo)
    if d is None or not d.is_dir():
        return []
    return sorted(
        p for p in d.iterdir()
        if p.is_file() and p.suffix.lower() in _AUDIO_EXTS
    )


def pick_random(sexo: str) -> Path:
    """Elige un audio al azar para el sexo dado. El operador solo elige sexo;
    frase y voz (`hombreN_fraseM.mp3`) salen sorteadas de aquí."""
    audios = list_audios(sexo)
    if not audios:
        raise RuntimeError(
            f"No hay audios disponibles para sexo={sexo!r} en "
            f"{_audios_dir(sexo)} (¿mount de Drive no disponible?)."
        )
    return random.choice(audios)


def prepare(audio: Path, *, on_log: OnLog = _noop) -> Path:
    """Recorta silencios (inicial + intermedios) y devuelve la ruta lista
    para el pipeline de vídeo. El original NUNCA se borra.

    La versión recortada se cachea en `_procesados/<mismo nombre>`, junto al
    original: si ya existe y es más nueva que el original (mtime), se
    reutiliza sin volver a invocar ffmpeg.
    """
    audio = Path(audio)
    if not audio.is_file():
        raise FileNotFoundError(str(audio))

    out_dir = audio.parent / _PROCESADOS_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / audio.name

    if out_path.is_file() and out_path.stat().st_mtime >= audio.stat().st_mtime:
        on_log(f"[audio_bank] reutilizando versión ya procesada: {out_path.name}")
        return out_path

    # El sufijo `.part` va ANTES de la extensión (`x.part.mp3`, no
    # `x.mp3.part`): ffmpeg deduce el formato de salida de la extensión y con
    # `.part` al final fallaba SIEMPRE con "Unable to find a suitable output
    # format", así que nunca se recortaba nada y además se reintentaba en cada
    # vídeo porque el fichero cacheado no llegaba a crearse.
    tmp_path = out_path.with_name(f"{out_path.stem}.part{out_path.suffix}")
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(audio),
        "-af", _SILENCEREMOVE_FILTER,
        str(tmp_path),
    ]
    on_log("+ " + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        on_log(
            f"[audio_bank] ffmpeg falló recortando silencios "
            f"({(proc.stderr or '')[-300:]}) — se usa el original"
        )
        tmp_path.unlink(missing_ok=True)
        return audio

    try:
        orig_dur = probe_duration(audio)
        trimmed_dur = probe_duration(tmp_path)
    except Exception as e:  # ffprobe puede fallar con un .part corrupto
        on_log(f"[audio_bank] no se pudo verificar la duración recortada ({e}) — se usa el original")
        tmp_path.unlink(missing_ok=True)
        return audio

    # El recorte debe ser MENOR que el original (si no, algo no se aplicó) y
    # mayor que el mínimo válido (si no, se comió la frase entera).
    if trimmed_dur >= orig_dur or trimmed_dur < _MIN_VALID_DURATION_S:
        on_log(
            f"[audio_bank] recorte sospechoso ({orig_dur:.2f}s → {trimmed_dur:.2f}s) "
            "— se descarta y se usa el original"
        )
        tmp_path.unlink(missing_ok=True)
        return audio

    tmp_path.replace(out_path)
    on_log(f"[audio_bank] silencios recortados: {orig_dur:.2f}s → {trimmed_dur:.2f}s ({out_path.name})")
    return out_path
