"""Los cortes de color del formato "Tienda Colores".

En los virales de referencia el vídeo arranca con la chica quieta nombrando
tres o cuatro colores —"rosa, beige, negro y verde"— y en cada palabra el
pantalón cambia de color de golpe. No son cuatro tomas: es la MISMA toma
recoloreada y cortada al ritmo de la voz. Lo último que nombra es lo que lleva
puesto, y ahí sigue el vídeo.

Aquí se hace exactamente eso sobre el clip 1 que sale del generador:

1. Se transcribe la voz (Whisper) y se busca en qué instante dice cada color.
2. Por cada color que NO lleva puesto, se saca el fotograma del instante en
   que lo nombra (otra pose cada vez: en el viral cada color es otra toma) y
   Gemini devuelve ese fotograma con el pantalón de ese color.
3. Se superponen esas fotos sobre el vídeo, cada una desde su palabra hasta
   la siguiente, con punch-in y vibración de mano para que no parezcan
   congeladas; al nombrar el puesto sigue el vídeo real. Audio intacto.

Si algo falla (Whisper, Gemini, un color que no encuentra), quien llama
sigue con el clip original: es un adorno y no tira el montaje.
"""

from __future__ import annotations

import os
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


# Si un color no tiene foto subida, ¿se recolorea con Gemini (~4 cts por
# color)? Apagado por defecto: el operador pidió que el formato saliera
# gratis — las fotos de cada color las hace Flow. Con la variable a "1" se
# recupera el recolor como red de seguridad.
RECOLOR_IA = os.getenv("TIENDA_COLORES_RECOLOR_IA", "0").strip().lower() in ("1", "true", "si", "sí")


def aplicar(
    clip: Path, colores: list[str], work_dir: Path, on_log: OnLog = _noop,
    tonos: dict[str, str] | None = None,
    fotos_colores: dict[str, Path] | None = None,
) -> Path:
    """El clip con los cortes de color metidos (mismo audio, misma duración).

    `colores` en el orden en que se dicen, el puesto el último. Con menos de
    dos no hay nada que cortar y se devuelve el clip tal cual.
    `fotos_colores` son las fotos subidas por el operador (la imagen 1 en
    cada color, hechas en Flow): son las que se cortan. Un color sin foto se
    recolorea con Gemini solo si `RECOLOR_IA`; si no, ese corte se salta
    (se queda el vídeo real) y se avisa. `tonos` (`{color: "#rrggbb"}`) es
    para el recolor.
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

    tonos = {str(k).lower(): str(v) for k, v in (tonos or {}).items()}
    subidas = {str(k).lower(): Path(v) for k, v in (fotos_colores or {}).items()}
    fotos: list[Path] = []
    sin_foto: list[str] = []
    for i, color in enumerate(colores[:-1], start=1):
        if color.lower() in subidas:
            on_log(f"[colores] «{color}»: foto subida por el operador")
            fotos.append(subidas[color.lower()])
            continue
        if not RECOLOR_IA:
            sin_foto.append(color)
            fotos.append(None)  # type: ignore[arg-type]
            continue
        from src.nicho_ropa.services import recolor

        # Cada color con SU fotograma: el del instante en que lo nombra. En
        # el viral cada color es otra toma (se lo acaba de subir, se coloca
        # la cintura), así que entre un corte y otro la pose CAMBIA; con el
        # mismo fotograma para todos parecía una foto que cambia de color.
        # El prompt del clip 1 le pide que se vaya colocando mientras los
        # nombra, para que haya pose distinta que coger.
        fotograma = work_dir / f"fotograma_{i}.jpg"
        _run([
            "ffmpeg", "-y", "-v", "error", "-ss", f"{tiempos[i - 1]:.3f}", "-i", str(clip),
            "-frames:v", "1", "-q:v", "2", str(fotograma),
        ], on_log)
        # Se nombra por el color y no por el índice: si se vuelve a montar el
        # mismo producto, las que ya salieron no se vuelven a pagar.
        salida = work_dir / f"color_{_norm(color).replace(' ', '_') or i}.png"
        if salida.is_file() and salida.stat().st_size > 0:
            on_log(f"[colores] «{color}»: ya estaba recoloreado, se reutiliza")
        else:
            on_log(f"[colores] recoloreando a «{color}» el fotograma de {tiempos[i - 1]:.2f}s…")
            salida.write_bytes(recolor.recolorear(
                fotograma.read_bytes(), color, on_log=on_log,
                tono=tonos.get(color.lower(), ""),
            ))
        fotos.append(salida)

    if sin_foto:
        on_log(
            "[colores] ⚠️ sin foto para: " + ", ".join(sin_foto)
            + " — en esos colores se queda el vídeo real (sube la imagen 1 en "
            "ese color, o TIENDA_COLORES_RECOLOR_IA=1 para recolorear con Gemini)"
        )
    if not any(fotos):
        on_log("[colores] ninguna foto de color: el clip sale sin cortes")
        return Path(clip)
    destino = Path(clip).with_name(f"{Path(clip).stem}_colores.mp4")
    _superponer(Path(clip), fotos, tiempos, destino, on_log)
    on_log(f"[colores] {sum(1 for f in fotos if f)} cortes de color metidos en el clip 1")
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


# Los cortes de color del viral son TOMAS distintas con corte seco: en cada
# una la chica se acaba de poner el pantalón y se mueve un poco. Aquí son
# fotos, así que se les da vida como en un edit de influencer: cada corte
# entra con un punch-in distinto (zoom que va creciendo despacio) y una
# vibración de mano continua. Congelada, la foto canta; con esto lee como
# otra toma. Escalas por corte, cíclicas.
PUNCH_ESCALAS = (1.04, 1.08, 1.05, 1.09)
# Cuánto crece el zoom a lo largo del corte (por segundo) y la amplitud de
# la vibración, en fracción del ancho/alto.
PUNCH_CRECIMIENTO_S = 0.025
VIBRACION_X = 0.006
VIBRACION_Y = 0.004


def _superponer(
    clip: Path, fotos: list[Path], tiempos: list[float], destino: Path, on_log: OnLog,
) -> None:
    """Cada foto tapa el vídeo desde su instante hasta el siguiente; la
    primera desde el fotograma 0 (en los virales el primer color ya está
    puesto al arrancar). El audio se copia sin tocar."""
    w, h = _tamano(clip)
    partes = ["[0:v]null[v0]"]
    entradas: list[str] = []
    n = 0
    for i, foto in enumerate(fotos, start=1):
        if not foto:
            continue
        n += 1
        entradas += ["-loop", "1", "-i", str(foto)]
        desde = 0.0 if i == 1 else tiempos[i - 1]
        hasta = tiempos[i]
        escala = PUNCH_ESCALAS[(i - 1) % len(PUNCH_ESCALAS)]
        # La foto de Gemini puede volver con otra proporción: se rellena y se
        # recorta al tamaño del clip, y algo más grande para el punch-in.
        sw, sh = int(w * escala) // 2 * 2, int(h * escala) // 2 * 2
        partes.append(
            f"[{n}:v]scale={sw}:{sh}:force_original_aspect_ratio=increase,"
            f"crop={sw}:{sh},setsar=1,fps={_fps(clip)}[f{n}]"
        )
        # El zoom crece desde el instante en que entra el corte y la mano
        # vibra con dos senos de frecuencias que no son múltiplos.
        t0 = f"(t-{desde:.3f})"
        zoom = f"(1+{PUNCH_CRECIMIENTO_S}*{t0})"
        # Centrada: la esquina se desplaza la mitad de lo que sobra.
        x = (
            f"(({w}-{sw}*{zoom})/2 + {VIBRACION_X * w:.1f}*sin(6.3*t) "
            f"+ {VIBRACION_X * w / 2:.1f}*sin(11.7*t))"
        )
        y = (
            f"(({h}-{sh}*{zoom})/2 + {VIBRACION_Y * h:.1f}*cos(4.9*t) "
            f"+ {VIBRACION_Y * h / 2:.1f}*cos(9.1*t))"
        )
        partes.append(
            f"[f{n}]scale=w='{sw}*{zoom}':h='{sh}*{zoom}':eval=frame[z{n}]"
        )
        partes.append(
            f"[v{n - 1}][z{n}]overlay=x='{x}':y='{y}':eval=frame"
            f":enable='between(t,{desde:.3f},{hasta:.3f})'[v{n}]"
        )
    ultimo = f"[v{n}]"
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(clip), *entradas,
        "-filter_complex", ";".join(partes),
        "-map", ultimo, "-map", "0:a?", "-shortest",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "copy", "-movflags", "+faststart", str(destino),
    ], on_log)


def _fps(clip: Path) -> int:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True,
    )
    try:
        num, den = proc.stdout.strip().split("\n")[0].split("/")[:2]
        return max(1, round(int(num) / int(den)))
    except (ValueError, IndexError, ZeroDivisionError):
        return 30


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
