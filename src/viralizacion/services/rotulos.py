"""Detectar texto sobreimpreso en un clip de paisaje.

Vive aquí, y no dentro del script que trocea el vídeo fuente, porque hace
falta en DOS momentos: al construir la biblioteca y al repasar una biblioteca
ya construida cuando se cuela algo (que es como se descubrió el fallo que
motiva este módulo).

**El fallo:** la primera versión miraba UN fotograma a 0,5s, dando por hecho
que "las cartelas de título duran todo el plano". No es cierto. En los vídeos
de recopilación las cartelas entran ANIMADAS: el plano abre limpio y a los dos
segundos aparece `GRAND CANYON` ocupando el bajo del encuadre, o un mapa de
Estados Unidos con `UNITED STATES` escrito encima. A 0,5s no hay nada que leer,
así que el clip pasaba el filtro y salía publicado con el rótulo dentro.

Por eso se muestrea a lo largo de TODO el clip. Los fotogramas se pegan en una
sola tira y se hace UNA llamada al OCR: easyocr cuesta sobre todo por área de
imagen, pero cada llamada suelta arrastra su propio arranque, y cinco llamadas
por clip multiplicaban por tres el tiempo de la biblioteca entera.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

# Cinco cortes repartidos por el clip. Con menos se escapa una cartela que
# entra y sale; con más, el barrido de 300 clips se va de tiempo sin encontrar
# nada nuevo (comprobado: el sexto y el séptimo no cambiaron ningún veredicto).
FRACCIONES = (0.04, 0.26, 0.48, 0.70, 0.92)

# Ancho de cada fotograma en la tira. Lo que se busca son cartelas con letras
# enormes; a 288px se leen igual y el OCR cuesta la mitad que a 480.
ANCHO_MUESTRA = 288

# Un rótulo es una PALABRA legible, no una letra suelta en un cartel de
# carretera ni el ruido que el OCR se inventa en una textura de roca.
CONF_MIN = 0.55
LARGO_MIN = 4


def _duracion(path: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return float(out)
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def _tira_de_muestras(video: Path, destino: Path) -> Path | None:
    """Pega varios fotogramas del clip en una sola imagen horizontal."""
    from PIL import Image

    dur = _duracion(video)
    if dur <= 0:
        return None

    trozos = []
    for i, frac in enumerate(FRACCIONES):
        # Se acota para no pedir un fotograma más allá del final: en los clips
        # de 3s el 0.92 cae a 2,76s y el último GOP puede no estar completo.
        t = min(max(dur * frac, 0.0), max(dur - 0.15, 0.0))
        frame = destino.parent / f"m{i}.jpg"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
             "-frames:v", "1", "-vf", f"scale={ANCHO_MUESTRA}:-2", str(frame), "-y"],
            capture_output=True,
        )
        if frame.is_file():
            trozos.append(frame)

    if not trozos:
        return None

    imgs = [Image.open(p).convert("RGB") for p in trozos]
    alto = max(im.height for im in imgs)
    tira = Image.new("RGB", (sum(im.width for im in imgs), alto), (0, 0, 0))
    x = 0
    for im in imgs:
        tira.paste(im, (x, 0))
        x += im.width
    tira.save(destino, quality=88)
    return destino


def texto_en_clip(video: Path, lector) -> list[str]:
    """Palabras sobreimpresas que se leen en el clip. Vacío = limpio.

    Devuelve las palabras, no un booleano, para poder revisar POR QUÉ se
    descarta un clip: cuando el filtro se pasa de listo hay que poder verlo.
    """
    with tempfile.TemporaryDirectory(prefix="rotulos_") as tmp:
        tira = _tira_de_muestras(video, Path(tmp) / "tira.jpg")
        if tira is None:
            return []
        try:
            hallado = lector.readtext(str(tira), detail=1)
        except Exception:
            return []
    return [
        str(txt).strip()
        for _caja, txt, conf in hallado
        if conf > CONF_MIN and len(str(txt).strip()) >= LARGO_MIN
    ]


def tiene_texto(video: Path, lector) -> bool:
    return bool(texto_en_clip(video, lector))
