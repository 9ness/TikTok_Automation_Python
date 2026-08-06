"""Deja la música de fondo a un nivel PREDECIBLE respecto a la voz.

`MUSIC_VOLUME` era un multiplicador fijo sobre lo que trajera el fichero, así
que el resultado dependía de cómo estuviera masterizado el mp3 que hubiera en
la carpeta. Con `Musica Reels.MP3` (-18,6 LUFS) y ganancia 0,75, la música
acababa **20 dB por debajo de la voz**: se oye si la buscas, pero no se siente.

Normalizando primero, `MUSIC_VOLUME` pasa a significar lo que uno espera —
cuánto por debajo de la voz queda— y cambiar de canción no descoloca la mezcla.

Mismo patrón que `cta_audio` y `audio_bank`: la versión procesada se cachea en
`_procesados/`, junto al original, que no se toca.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# La voz de los vídeos acaba en torno a -12,5 LUFS. Con la música a -24 queda
# ~11 dB por debajo: se siente y no tapa. A 20 dB (lo de antes) no se notaba.
MUSICA_LUFS = -24.0
MUSICA_TP = -2.0

_PROCESADOS = "_procesados"


def preparar(musica: Path, *, on_log: OnLog = _noop) -> Path:
    """Devuelve la música normalizada, cacheada. El original no se toca.

    Si falla se devuelve el original: mejor la música floja que una tanda
    entera caída por esto.
    """
    musica = Path(musica)
    destino = musica.parent / _PROCESADOS / musica.name
    try:
        if destino.is_file() and destino.stat().st_mtime >= musica.stat().st_mtime:
            return destino
        destino.parent.mkdir(parents=True, exist_ok=True)
        med = _medir(musica)
        norm = f"loudnorm=I={MUSICA_LUFS}:TP={MUSICA_TP}:LRA=11"
        if len(med) == 4:
            norm += (
                f":measured_I={med['input_i']}:measured_TP={med['input_tp']}"
                f":measured_LRA={med['input_lra']}:measured_thresh={med['input_thresh']}"
            )
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(musica), "-af", norm, str(destino)],
            check=True, capture_output=True,
        )
        on_log(f"[musica] {musica.name}: {med.get('input_i', '?')} → {MUSICA_LUFS} LUFS")
        return destino
    except Exception as e:
        on_log(f"[musica] ⚠️ no pude normalizar {musica.name} ({e}) — se usa el original")
        return musica


def _medir(audio: Path) -> dict[str, str]:
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(audio), "-af",
         f"loudnorm=I={MUSICA_LUFS}:TP={MUSICA_TP}:LRA=11:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    salida: dict[str, str] = {}
    for clave in ("input_i", "input_tp", "input_lra", "input_thresh"):
        m = re.search(rf'"{clave}"\s*:\s*"?(-?[\d.]+)"?', r.stderr)
        if m:
            salida[clave] = m.group(1)
    return salida
