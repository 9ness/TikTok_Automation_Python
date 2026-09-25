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
# Recolorear el pantalón sobre el propio vídeo (fotograma a fotograma) en
# vez de tapar con fotos: gratis, con movimiento, y con el tono del hex de
# cada variante. Solo cuando el color puesto se deja aislar (ver
# `recolor_video.aislable`); si no, se cae a las fotos como antes.
# APAGADO desde el 24/9/2026: los cambios de color los hace el propio
# generador (clip 1 con las imágenes de cada color como ingredientes), así
# que el montaje no tiene que tocar el vídeo. El código se queda por si
# alguna vez el generador deja de hacerlos: `TIENDA_COLORES_RECOLOR_VIDEO=1`.
RECOLOR_VIDEO = os.getenv("TIENDA_COLORES_RECOLOR_VIDEO", "0").strip().lower() in ("1", "true", "si", "sí")


# Cuánto tiene que cambiar el tono de la prenda entre una palabra de color y
# otra para dar por hecho que el vídeo YA trae los cortes. Medido: entre dos
# colores de verdad la distancia pasa de 25; el mismo color en dos instantes
# se mueve menos de 6 por la luz.
DE_YA_HECHO = 15.0


def _ya_trae_colores(clip: Path, tiempos: list[float], on_log: OnLog) -> bool:
    """¿El clip cambia el color de la prenda al nombrar cada color?"""
    try:
        import cv2
        import numpy as np

        from src.nicho_ropa.pipeline import recolor_video as rv

        cap = cv2.VideoCapture(str(clip))
        medidos = []
        for t in tiempos:
            cap.set(cv2.CAP_PROP_POS_MSEC, (t + 0.25) * 1000)
            ok, frame = cap.read()
            if ok:
                medidos.append(rv.color_prenda(frame))
        cap.release()
        if len(medidos) < 2:
            return False
        distancias = [
            float(np.hypot(a[1] - b[1], a[2] - b[2]))
            for a, b in zip(medidos, medidos[1:])
        ]
    except Exception as e:  # noqa: BLE001 — ante la duda, se monta como siempre
        on_log(f"[colores] no se pudo comprobar si el clip ya trae colores ({str(e)[:80]})")
        return False
    if sum(1 for d in distancias if d >= DE_YA_HECHO) >= max(1, len(distancias) - 1):
        on_log(
            "[colores] el clip YA cambia de color al nombrarlos "
            f"(distancias {', '.join(f'{d:.0f}' for d in distancias)}): se deja tal cual"
        )
        return True
    return False


def _recolorear_en_video(
    clip: Path, colores: list[str], tiempos: list[float], tonos: dict[str, str],
    fotos: dict[str, Path], work_dir: Path, on_log: OnLog,
) -> Path | None:
    """El clip con cada tramo de color recoloreado sobre el vídeo, o None si
    no se puede (sin tono para algún color, o color puesto no aislable).

    El tono de cada color sale, por este orden, de la FOTO de ese color que
    subió el operador (misma chica y encuadre: se mide el pantalón ahí) y, si
    no la hay, del hex leído de la miniatura de la ficha.
    """
    from src.nicho_ropa.pipeline import recolor_video as rv

    tramos = []
    faltan = []
    for i, color in enumerate(colores[:-1]):
        destino = None
        foto = fotos.get(color.lower())
        if foto:
            destino = rv.color_de_foto(foto)
            if destino is not None:
                on_log(f"[colores] «{color}»: tono medido en la foto subida")
        if destino is None and tonos.get(color.lower()):
            destino = tonos[color.lower()]
            on_log(f"[colores] «{color}»: tono del hex de la ficha ({destino})")
        if destino is None:
            faltan.append(color)
            continue
        desde = 0.0 if i == 0 else tiempos[i]
        tramos.append((desde, tiempos[i + 1], destino))
    if faltan:
        on_log(f"[colores] sin tono para {', '.join(faltan)} (ni foto ni hex): no se recolorea el vídeo")
        return None
    destino = clip.with_name(f"{clip.stem}_colores.mp4")
    try:
        import cv2

        cap = cv2.VideoCapture(str(clip))
        cap.set(cv2.CAP_PROP_POS_MSEC, tiempos[-1] * 1000)
        ok, ref = cap.read()
        cap.release()
        if not ok:
            return None
        origen = rv.color_prenda(ref)
        if not rv.aislable(origen):
            on_log(
                "[colores] el color puesto no se deja aislar (croma "
                f"{float(((origen[1]-128)**2 + (origen[2]-128)**2) ** 0.5):.0f}): se usan fotos"
            )
            return None
        rv.recolorear_tramos(clip, tramos, destino, on_log=on_log, t_medida=tiempos[-1])
    except Exception as e:  # noqa: BLE001 — a las fotos, sin tirar el montaje
        on_log(f"[colores] no se pudo recolorear el vídeo ({str(e)[:120]}): se usan fotos")
        return None
    on_log(f"[colores] {len(tramos)} cortes de color recoloreados sobre el vídeo")
    return destino


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
    # Con las dos vías apagadas no hay nada que hacer: los cambios de color
    # los trae el propio clip. Se sale ANTES de mirar las fotos subidas —
    # dejarlas actuar era lo que seguía tapando el vídeo con fotos fijas de
    # montajes anteriores.
    # Con fotos de cada color subidas (hechas en Flow) se cortan ellas aunque
    # las dos vías de recolor estén apagadas: Omni NO hace de fiar los tres
    # cortes en 2,5 s (sep 2026: se comía el azul marino, o dos colores, y si
    # se le rotulaban los planos escribía los rótulos). El clip 1 se genera
    # entonces solo con el color puesto y los cortes los pone el montaje, a la
    # palabra. Si el clip ya cambia de color, no se toca (ver abajo).
    hay_fotos = any(Path(v).is_file() for v in (fotos_colores or {}).values())
    if not RECOLOR_VIDEO and not RECOLOR_IA and not hay_fotos:
        on_log("[colores] los colores los trae el vídeo: la edición no los toca")
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

    # Primero, recolorear el VÍDEO (con movimiento) si el color puesto se
    # deja aislar y hay tono para cada color: es lo más parecido al viral, y
    # sin contenido estático. Si no se puede, fotos.
    if RECOLOR_VIDEO:
        # Si el clip YA cambia de color (lo hizo el generador), no se toca:
        # repintarlo encima sería recolorear lo ya recoloreado.
        if _ya_trae_colores(Path(clip), tiempos, on_log):
            return Path(clip)
        hecho = _recolorear_en_video(Path(clip), colores, tiempos, tonos, subidas, work_dir, on_log)
        if hecho:
            return hecho

    if hay_fotos and not RECOLOR_VIDEO and _ya_trae_colores(Path(clip), tiempos, on_log):
        return Path(clip)

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
