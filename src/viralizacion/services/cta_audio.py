"""Deja la coletilla del CTA al MISMO volumen que la voz del vídeo.

El fichero que grabó el operador (`CTA Final Videos.MP3`) viene a -18,9 LUFS,
y la voz de los vídeos ya montados anda por -10/-13. Metido tal cual se oye
6 dB por debajo del resto: suena, pero "ni lo aprecias" — que es justo lo que
reportó el operador antes incluso de que el fichero estuviera puesto.

El renderer le aplica `volume=VOICE_VOLUME` igual que a la voz, así que la
diferencia de nivel viaja entera al vídeo. Se arregla aquí y no en el
filtergraph porque así se paga UNA vez por fichero, no en cada uno de los 20+
vídeos de una tanda.

Mismo patrón que `nicho_pov_bof/services/audio_bank.py`: la versión procesada
se cachea junto al original, en `_procesados/`, y el original NUNCA se toca.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# En medio de lo que miden sus vídeos (-10,3 a -12,8 LUFS). Subir más no gana
# nada: TikTok normaliza al reproducir y solo se gana riesgo de recorte.
CTA_LUFS = -12.5
CTA_TP = -1.5

# Compresión ANTES de normalizar, la misma cadena del Nicho POV BOF. Sin esto
# no se llega al objetivo: la grabación tiene 17 dB de cresta (media -20,9 dB,
# pico -3,3) y `loudnorm` se frena para no recortar — se quedaba en -14,8 LUFS,
# todavía 2 dB por debajo de la voz. Comprimiendo primero, la ganancia cabe.
_CADENA = (
    "acompressor=threshold=-20dB:ratio=4:attack=5:release=120:makeup=2,"
    "speechnorm=e=8:r=0.0008:l=1"
)

_PROCESADOS = "_procesados"


def preparar(cta: Path, *, on_log: OnLog = _noop) -> Path:
    """Devuelve la coletilla nivelada, cacheada. El original no se toca.

    Si algo falla (ffmpeg ausente, carpeta de solo lectura) se devuelve el
    original: mejor un CTA bajito que una tanda entera caída por esto.
    """
    cta = Path(cta)
    destino = cta.parent / _PROCESADOS / cta.name
    try:
        if destino.is_file() and destino.stat().st_mtime >= cta.stat().st_mtime:
            return destino
        destino.parent.mkdir(parents=True, exist_ok=True)
        medidas = _medir(cta, _CADENA)
        norm = f"loudnorm=I={CTA_LUFS}:TP={CTA_TP}:LRA=9"
        if len(medidas) == 4:
            norm += (
                f":measured_I={medidas['input_i']}:measured_TP={medidas['input_tp']}"
                f":measured_LRA={medidas['input_lra']}:measured_thresh={medidas['input_thresh']}"
            )
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(cta), "-af",
             # `level=disabled` o `alimiter` re-nivela hacia arriba y el pico
             # acaba por encima de 0 dBTP (ya pasó en el POV BOF).
             f"{_CADENA},{norm},alimiter=limit=0.9:level=disabled", str(destino)],
            check=True, capture_output=True,
        )
        on_log(
            f"[cta] {cta.name}: {medidas.get('input_i', '?')} → {CTA_LUFS} LUFS"
        )
        return destino
    except Exception as e:
        on_log(f"[cta] ⚠️ no pude nivelar {cta.name} ({e}) — se usa el original")
        return cta


def _medir(audio: Path, extra: str = "") -> dict[str, str]:
    import re

    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(audio), "-af",
         (f"{extra}," if extra else "")
         + f"loudnorm=I={CTA_LUFS}:TP={CTA_TP}:LRA=9:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    salida: dict[str, str] = {}
    for clave in ("input_i", "input_tp", "input_lra", "input_thresh"):
        m = re.search(rf'"{clave}"\s*:\s*"?(-?[\d.]+)"?', r.stderr)
        if m:
            salida[clave] = m.group(1)
    return salida
