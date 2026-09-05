"""Monta el anuncio UGC: ordena los tres clips, les quita el silencio de
entrada y los pega.

Lo que hace distinto a los demás nichos:

**Los clips llegan SIN orden.** El operador los genera de uno en uno en Flow y
los adjunta todos de golpe, en el orden que le salga del selector de ficheros.
Aquí se transcribe cada uno y se casa con el guion de su escena —que ya está
guardado, porque lo escribimos nosotros—, así que el orden lo pone la voz y no
el nombre del fichero. Se prueban los seis emparejamientos posibles y se elige
el que MÁS suma: casar uno a uno se equivoca cuando dos escenas empiezan
parecido, y con tres clips probarlos todos es gratis.

**Solo se recorta el silencio del PRINCIPIO.** Los clips generados suelen
arrancar con medio segundo mudo antes de que la persona hable, y tres medios
segundos son un anuncio que empieza tres veces. En medio no se toca nada: ahí
el silencio es de la propia interpretación.

No hay voz nuestra ni texto quemado: el clip ya viene hablado desde Omni.
"""

from __future__ import annotations

import itertools
import re
import subprocess
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# Vertical de TikTok. 60 fps porque es lo que pide el operador para que se vea
# fluido; los clips vienen a 24-30 y subirlos aquí no inventa suavidad, pero
# tampoco la pierde al concatenar material de distintas fuentes.
ANCHO, ALTO, FPS = 1080, 1920, 60

# Silencio de entrada: por debajo de esto y durante al menos esto, es hueco.
_RUIDO_DB = -35
_MIN_SILENCIO_S = 0.15
# Se deja un respiro antes de la primera palabra: cortar a hueso hace que la
# frase empiece con la boca ya abierta y suena a corte.
_MARGEN_S = 0.08
# Nunca se comen más de esto, por si el clip empieza con la persona respirando
# y el detector se pasa de listo.
_MAX_RECORTE_S = 1.5


def _norm(texto: str) -> str:
    """Para comparar voz con guion: sin tildes, sin signos y en minúsculas."""
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9ñ ]+", " ", t).split())


def _transcribir(clip: Path, work_dir: Path, on_log: OnLog) -> str:
    """Lo que se oye en el clip. Cadena vacía si no se puede transcribir."""
    from src.subtitles import transcribe

    wav = work_dir / f"{clip.stem}_16k.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(clip),
             "-vn", "-ac", "1", "-ar", "16000", str(wav)],
            check=True, capture_output=True,
        )
        palabras = transcribe(str(wav), model_size="small", language="es")
    except Exception as e:  # noqa: BLE001
        on_log(f"[nicho_general] no se pudo transcribir {clip.name}: {e}")
        return ""
    return " ".join(str(p.get("word") or "") for p in palabras)


def ordenar_clips(
    clips: list[Path], escenas: list[dict], work_dir: Path, on_log: OnLog = _noop,
) -> list[Path]:
    """Los clips en el orden de las escenas, por lo que se dice en cada uno.

    Si no se puede transcribir (Whisper caído, clip mudo) se respeta el orden
    en que se subieron y se avisa: es mejor un anuncio con las escenas
    cambiadas —que se ve al reproducirlo— que ninguno.
    """
    if len(clips) < 2:
        return list(clips)

    dichos = [_norm(_transcribir(c, work_dir, on_log)) for c in clips]
    guiones = [_norm(e.get("guion") or "") for e in escenas]
    if not all(dichos) or not all(guiones):
        on_log(
            "[nicho_general] sin transcripción o sin guiones: se dejan los "
            "clips en el orden en que se subieron."
        )
        return list(clips)

    def parecido(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    # Los seis emparejamientos posibles; gana el que más suma en total.
    mejor, mejor_suma = None, -1.0
    for orden in itertools.permutations(range(len(clips))):
        suma = sum(
            parecido(dichos[c], guiones[i])
            for i, c in enumerate(orden)
            if i < len(guiones)
        )
        if suma > mejor_suma:
            mejor, mejor_suma = orden, suma

    medio = mejor_suma / max(1, min(len(clips), len(guiones)))
    # 0,45 y no menos: dos textos en español sin NADA que ver ya se parecen un
    # 0,28 solo por las letras que comparten, así que un umbral bajo daba por
    # bueno cualquier orden. Un clip de verdad, aunque Whisper se coma
    # palabras, pasa de 0,6.
    if medio < 0.45:
        on_log(
            f"[nicho_general] los clips no se parecen a ningún guion "
            f"(parecido medio {medio:.2f}): se dejan como se subieron. "
            "¿Son de este producto?"
        )
        return list(clips)

    on_log(f"[nicho_general] orden por la voz: {[i + 1 for i in mejor]} (parecido {medio:.2f})")
    return [clips[i] for i in mejor]


def _silencio_inicial(clip: Path) -> float:
    """Cuánto dura el hueco del principio, 0 si empieza hablando."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(clip),
         "-af", f"silencedetect=noise={_RUIDO_DB}dB:d={_MIN_SILENCIO_S}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    inicio = fin = None
    for linea in proc.stderr.splitlines():
        if "silence_start:" in linea:
            try:
                inicio = float(linea.split("silence_start:")[1].split()[0])
            except (IndexError, ValueError):
                inicio = None
        elif "silence_end:" in linea and inicio is not None:
            try:
                fin = float(linea.split("silence_end:")[1].split()[0])
            except (IndexError, ValueError):
                fin = None
            break
    # Solo cuenta si el silencio ARRANCA el clip: uno que empiece en el
    # segundo 3 es una pausa de la persona y ahí no se toca.
    if inicio is None or fin is None or inicio > 0.15:
        return 0.0
    return max(0.0, min(fin - _MARGEN_S, _MAX_RECORTE_S))


def montar(
    clips: list[Path],
    escenas: list[dict],
    salida: Path,
    *,
    work_dir: Path | None = None,
    on_log: OnLog = _noop,
) -> Path:
    """Los clips ordenados, sin el silencio de entrada y pegados en un 9:16."""
    if not clips:
        raise ValueError("No hay clips que montar.")
    work = work_dir or salida.parent / "_ugc_tmp"
    work.mkdir(parents=True, exist_ok=True)

    ordenados = ordenar_clips(clips, escenas, work, on_log)

    recortados = []
    for i, clip in enumerate(ordenados, start=1):
        quitar = _silencio_inicial(clip)
        destino = work / f"clip{i}.mp4"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        if quitar > 0.05:
            on_log(f"[nicho_general] clip {i}: se quitan {quitar:.2f}s de silencio inicial")
            cmd += ["-ss", f"{quitar:.3f}"]
        cmd += [
            "-i", str(clip),
            "-vf", (
                f"scale={ANCHO}:{ALTO}:force_original_aspect_ratio=decrease,"
                f"pad={ANCHO}:{ALTO}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"fps={FPS},setsar=1"
            ),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            str(destino),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        recortados.append(destino)

    # Concat por lista: los trozos ya salen con el mismo formato exacto, así
    # que no hace falta volver a codificar.
    lista = work / "clips.txt"
    lista.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in recortados) + "\n",
        encoding="utf-8",
    )
    salida.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(lista),
         "-c", "copy", "-movflags", "+faststart", str(salida)],
        check=True, capture_output=True,
    )
    on_log(f"[nicho_general] montado: {salida.name} ({len(recortados)} clips)")
    return salida
