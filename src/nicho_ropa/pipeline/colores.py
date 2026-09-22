"""Los cortes de color del formato "Tienda Colores".

En los virales de referencia el vídeo arranca con la chica quieta nombrando
tres o cuatro colores —"rosa, beige, negro y verde"— y en cada palabra el
pantalón cambia de color de golpe. No son cuatro tomas: es la MISMA toma
recoloreada y cortada al ritmo de la voz. Lo último que nombra es lo que lleva
puesto, y ahí sigue el vídeo.

Aquí se hace exactamente eso sobre el clip 1 que sale del generador:

1. Se transcribe la voz (Whisper) y se busca en qué instante dice cada color.
2. Se saca el fotograma del instante en que nombra el ÚLTIMO (el puesto): es
   el que se recolorea, así el corte al vídeo real es invisible —misma pose.
3. Gemini devuelve una copia por cada color que NO lleva puesto.
4. Se superponen esas fotos sobre el vídeo, cada una desde su palabra hasta
   la siguiente, y el audio se deja intacto.

Si algo falla (Whisper, Gemini, un color que no encuentra), quien llama
sigue con el clip original: es un adorno y no tira el montaje.
"""

from __future__ import annotations

import subprocess
import unicodedata
from pathlib import Path
from typing import Callable

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# Los colores se nombran al principio: pasados estos segundos ya no se buscan
# (evita casar "verde" con un "verde" de más adelante en el guion).
VENTANA_S = 6.0
# Cuando Whisper no encuentra las palabras: un corte cada tanto, empezando
# donde arranca la voz. Medido en los virales: 0,7-0,9 s por color.
PASO_DEFECTO_S = 0.8


def aplicar(
    clip: Path, colores: list[str], work_dir: Path, on_log: OnLog = _noop,
) -> Path:
    """El clip con los cortes de color metidos (mismo audio, misma duración).

    `colores` en el orden en que se dicen, el puesto el último. Con menos de
    dos no hay nada que cortar y se devuelve el clip tal cual.
    """
    colores = [c.strip() for c in colores if c and c.strip()]
    if len(colores) < 2:
        return Path(clip)
    from src.nicho_pov_bof.pipeline.video_editor import _transcribir_voz

    work_dir.mkdir(parents=True, exist_ok=True)
    palabras = _transcribir_voz(Path(clip), work_dir, on_log) or []
    tiempos = tiempos_de_colores(palabras, colores)
    if tiempos:
        on_log(
            "[colores] cortes por voz: "
            + ", ".join(f"{c}@{t:.2f}s" for c, t in zip(colores, tiempos))
        )
    else:
        tiempos = _tiempos_por_defecto(palabras, len(colores))
        on_log(
            "[colores] Whisper no encontró los colores: cortes cada "
            f"{PASO_DEFECTO_S}s desde {tiempos[0]:.2f}s"
        )

    # El fotograma del instante en que dice el color puesto: desde ahí sigue
    # el vídeo real, así que recolorear ESE es lo que hace el corte invisible.
    t_puesto = tiempos[-1]
    fotograma = work_dir / "fotograma.jpg"
    _run([
        "ffmpeg", "-y", "-v", "error", "-ss", f"{t_puesto:.3f}", "-i", str(clip),
        "-frames:v", "1", "-q:v", "2", str(fotograma),
    ], on_log)
    base = fotograma.read_bytes()

    from src.nicho_ropa.services import recolor

    fotos: list[Path] = []
    for i, color in enumerate(colores[:-1], start=1):
        # Se nombra por el color y no por el índice: si se vuelve a montar el
        # mismo producto, las que ya salieron no se vuelven a pagar.
        salida = work_dir / f"color_{_norm(color).replace(' ', '_') or i}.png"
        if salida.is_file() and salida.stat().st_size > 0:
            on_log(f"[colores] «{color}»: ya estaba recoloreado, se reutiliza")
        else:
            on_log(f"[colores] recoloreando a «{color}»…")
            salida.write_bytes(recolor.recolorear(base, color, on_log=on_log))
        fotos.append(salida)

    destino = Path(clip).with_name(f"{Path(clip).stem}_colores.mp4")
    _superponer(Path(clip), fotos, tiempos, destino, on_log)
    on_log(f"[colores] {len(fotos)} cortes de color metidos en el clip 1")
    return destino


def _norm(txt: str) -> str:
    """Sin acentos, en minúsculas y sin la puntuación pegada ("Rosa," → "rosa")."""
    plano = unicodedata.normalize("NFKD", txt or "")
    return "".join(
        c for c in plano if not unicodedata.combining(c)
    ).lower().strip(" .,;:!?¡¿«»\"'")


def tiempos_de_colores(palabras: list[dict], colores: list[str]) -> list[float]:
    """Cuándo empieza a decir cada color, en orden. `[]` si no los encuentra.

    Se busca cada color a partir de donde acabó el anterior (así "azul claro,
    azul" no casa dos veces con el mismo "azul"), por la PRIMERA palabra del
    color y solo dentro de la ventana inicial. Con los que no encuentra se
    interpola entre vecinos; si falla más de la mitad, se rinde.
    """
    if not palabras or not colores:
        return []
    ventana = [
        (i, _norm(w.get("word", "")), float(w.get("start") or 0.0))
        for i, w in enumerate(palabras)
        if float(w.get("start") or 0.0) <= VENTANA_S
    ]
    encontrados: list[float | None] = []
    desde = 0
    for color in colores:
        trozos = [_norm(t) for t in color.split() if _norm(t)]
        if not trozos:
            encontrados.append(None)
            continue
        primera = trozos[0]
        hallado = None
        for pos, (_i, palabra, inicio) in enumerate(ventana):
            if pos < desde:
                continue
            # "beige" ↔ "beis"/"beche": basta con que empiece igual (3 letras)
            # o que una contenga a la otra; Whisper se inventa el final.
            if _parecidas(palabra, primera):
                hallado = inicio
                desde = pos + len(trozos)
                break
        encontrados.append(hallado)
    hallados = [t for t in encontrados if t is not None]
    if len(hallados) * 2 < len(colores) or not hallados:
        return []
    salida: list[float] = []
    for i, t in enumerate(encontrados):
        if t is not None:
            salida.append(t)
            continue
        # Interpolar entre el anterior y el siguiente encontrados.
        prev = next((salida[j] for j in range(i - 1, -1, -1)), None)
        sig = next((x for x in encontrados[i + 1:] if x is not None), None)
        if prev is not None and sig is not None:
            salida.append(prev + (sig - prev) / 2)
        elif prev is not None:
            salida.append(prev + PASO_DEFECTO_S)
        else:
            salida.append(max(0.0, sig - PASO_DEFECTO_S))
    # Tienen que ir en orden y sin dos en el mismo instante.
    for i in range(1, len(salida)):
        if salida[i] <= salida[i - 1]:
            salida[i] = salida[i - 1] + 0.3
    return salida


def _parecidas(oida: str, pedida: str) -> bool:
    """Si lo que oyó Whisper es ese color. Oye "beche" por beige y "kawki"
    por caqui, así que además del prefijo vale un parecido de letras alto."""
    from difflib import SequenceMatcher

    if not oida or not pedida:
        return False
    if oida == pedida or oida in pedida or pedida in oida:
        return True
    if len(oida) >= 3 and len(pedida) >= 3 and oida[:3] == pedida[:3]:
        return True
    return len(oida) >= 4 and SequenceMatcher(None, oida, pedida).ratio() >= 0.6


def _tiempos_por_defecto(palabras: list[dict], n: int) -> list[float]:
    inicio = float(palabras[0].get("start") or 0.0) if palabras else 0.3
    return [inicio + i * PASO_DEFECTO_S for i in range(n)]


def _superponer(
    clip: Path, fotos: list[Path], tiempos: list[float], destino: Path, on_log: OnLog,
) -> None:
    """Cada foto tapa el vídeo desde su instante hasta el siguiente; la
    primera desde el fotograma 0 (en los virales el primer color ya está
    puesto al arrancar). El audio se copia sin tocar."""
    w, h = _tamano(clip)
    partes = ["[0:v]null[v0]"]
    entradas: list[str] = []
    for i, foto in enumerate(fotos, start=1):
        entradas += ["-i", str(foto)]
        desde = 0.0 if i == 1 else tiempos[i - 1]
        hasta = tiempos[i]
        # La foto de Gemini puede volver con otra proporción: se rellena y se
        # recorta al tamaño del clip para que el corte no salte.
        partes.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1[f{i}]"
        )
        partes.append(
            f"[v{i - 1}][f{i}]overlay=0:0:enable='between(t,{desde:.3f},{hasta:.3f})'[v{i}]"
        )
    ultimo = f"[v{len(fotos)}]"
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(clip), *entradas,
        "-filter_complex", ";".join(partes),
        "-map", ultimo, "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "copy", "-movflags", "+faststart", str(destino),
    ], on_log)


def _tamano(clip: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True,
    )
    try:
        w, h = proc.stdout.strip().split("\n")[0].split(",")[:2]
        return int(w), int(h)
    except (ValueError, IndexError):
        return 1080, 1920


def _run(cmd: list[str], on_log: OnLog) -> None:
    on_log("+ " + " ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {proc.stderr[-400:]}")
