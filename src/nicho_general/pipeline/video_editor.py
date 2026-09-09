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

Lo elige el operador en la tarjeta y viene marcado. Se desmarca cuando el
vídeo va JUSTO de segundos para lo que pide la tienda: los clips se cuentan
para llegar a esa duración (`config.escenas_para`), así que medio segundo por
clip puede dejarlo por debajo del mínimo — que es el motivo por el que se está
grabando ese producto. Lo normal es que sobre margen (se pide un mínimo de 30s
y se graban 40) y entonces el recorte solo hace bien.

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

    Se prueban TODOS los órdenes posibles porque casar uno a uno se equivoca
    cuando dos escenas empiezan parecido. Con el tope de ocho escenas
    (`config.ESCENAS_MAX`) son 40.320 combinaciones de sumar tres números, que
    es trabajo de milisegundos.
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

    # El parecido de CADA clip con CADA guion, calculado una sola vez. Antes se
    # comparaba dentro del bucle de permutaciones y daba igual con tres clips
    # (seis órdenes), pero un anuncio de ocho son 40.320 órdenes y comparar
    # cadenas ahí dentro es lo que lo volvía lento: con la tabla, el bucle solo
    # suma números.
    tabla = [
        [SequenceMatcher(None, d, g).ratio() for g in guiones] for d in dichos
    ]

    # Todos los emparejamientos posibles; gana el que más suma en total.
    mejor, mejor_suma = None, -1.0
    for orden in itertools.permutations(range(len(clips))):
        suma = sum(
            tabla[c][i] for i, c in enumerate(orden) if i < len(guiones)
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
    recortar_silencios: bool = True,
    bloque_texto: str = "",
    on_log: OnLog = _noop,
) -> Path:
    """Los clips ordenados, sin el silencio de entrada y pegados en un 9:16.

    Con `recortar_silencios=False` se pegan enteros: es lo que toca cuando la
    tienda pide una duración mínima (ver la cabecera del módulo).
    """
    if not clips:
        raise ValueError("No hay clips que montar.")
    work = work_dir or salida.parent / "_ugc_tmp"
    work.mkdir(parents=True, exist_ok=True)

    ordenados = ordenar_clips(clips, escenas, work, on_log)
    if not recortar_silencios:
        on_log(
            "[nicho_general] duración pedida: los clips se pegan enteros, sin "
            "quitarles el silencio de entrada."
        )

    recortados = []
    for i, clip in enumerate(ordenados, start=1):
        quitar = _silencio_inicial(clip) if recortar_silencios else 0.0
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
    pegado = work / "pegado.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(lista),
         "-c", "copy", "-movflags", "+faststart", str(pegado)],
        check=True, capture_output=True,
    )

    # El bloque va ANTES de la flecha: así la flecha se pinta sobre el vídeo
    # definitivo y no hay que volver a codificar por encima de ella.
    if bloque_texto.strip():
        pegado = _quemar_bloque(pegado, bloque_texto, work / "bloque.mp4", work, on_log)

    _flecha(pegado, salida, work, on_log)
    on_log(f"[nicho_general] montado: {salida.name} ({len(recortados)} clips)")
    return salida


def _flecha(video: Path, salida: Path, work: Path, on_log: OnLog) -> None:
    """La flecha que apunta al carrito, la misma que el POV BOF.

    Es lo único que este montaje quema encima: el anuncio no lleva texto (lo
    dice la persona), pero la CTA sin nada a lo que apuntar se queda coja.

    Dos diferencias con el POV BOF y las dos importan: la voz va DENTRO del
    vídeo —así que de ahí se saca cuándo entra la flecha y hay que conservar
    la pista de audio— y si algo falla se publica el vídeo tal cual, que un
    adorno no puede tirar un montaje que ya está hecho.
    """
    import shutil

    from src.nicho_pov_bof.pipeline import video_editor as pov

    try:
        con_flecha = pov._overlay_arrow(
            video, video, work, work / "flecha.mp4", on_log, con_audio=True,
        )
    except Exception as e:  # noqa: BLE001
        on_log(f"[nicho_general] sin flecha ({str(e)[:120]})")
        con_flecha = video
    shutil.move(str(con_flecha), str(salida))


# ---------------------------------------------------------------------------
# Bloque de texto del principio ("mensaje subliminal" del curso)
# ---------------------------------------------------------------------------
# Cuatro líneas en columna sobre los primeros segundos. El curso lo quema
# durante todo el vídeo en el POV BOF, pero aquí hay una persona hablando 40
# segundos: dejarlo puesto tapa la escena y el propio diagnóstico de la agencia
# marca como defecto "la imagen tapa el vídeo". Así que entra y se va.
BLOQUE_S = 4.0
# Fuera de estas bandas no se pinta: arriba está el nombre de la cuenta y
# abajo el caption y los botones de TikTok, que se comerían el texto.
_BANDA_MIN, _BANDA_MAX = 0.10, 0.66


def _frames_del_principio(video: Path, work: Path, segundos: float) -> list[Path]:
    """Unos pocos fotogramas de esos primeros segundos, para mirarlos."""
    destino = work / "frames"
    destino.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-t", f"{segundos:.2f}", "-i", str(video),
         "-vf", "fps=2,scale=270:-1", str(destino / "f%02d.png")],
        check=True, capture_output=True,
    )
    return sorted(destino.glob("f*.png"))


def _sitio_libre(video: Path, work: Path, alto_bloque: int, on_log: OnLog) -> float:
    """Dónde cae el bloque para no tapar ni la cara ni el producto.

    Devuelve la Y (0-1) de la esquina superior del bloque. Mira los primeros
    segundos —que es cuando se ve— y busca la franja más VACÍA: cuenta bordes
    (el producto, los muebles, las manos) y descarta las que pisen una cara.

    Se hace por frames y no a ojo porque el sitio bueno cambia con el plano:
    en un plano medio el hueco está arriba, y en uno donde la persona está de
    pie con el producto en la encimera, el hueco está justo en el medio.
    """
    try:
        import cv2
        import numpy as np
    except Exception as e:  # noqa: BLE001 — sin OpenCV se pinta donde siempre
        on_log(f"[nicho_general] sin OpenCV, bloque al 18% ({str(e)[:60]})")
        return 0.18

    frames = _frames_del_principio(video, work, BLOQUE_S)
    if not frames:
        return 0.18

    cascada = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    coste: dict[int, float] = {}
    caras: set[int] = set()
    paso = 2  # en porcentaje de altura
    for ruta in frames:
        img = cv2.imread(str(ruta))
        if img is None:
            continue
        h, w = img.shape[:2]
        bordes = cv2.Canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 80, 200)
        gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # OJO: `detectMultiScale` devuelve un array de numpy, así que no se
        # puede hacer `or []` — el `if` sobre un array de varios elementos
        # revienta ("truth value is ambiguous").
        detectadas = cascada.detectMultiScale(gris, 1.15, 5)
        for x, y, cw, ch in (detectadas if len(detectadas) else []):
            # La cara con margen: el texto pegado a la barbilla también molesta.
            for p in range(_int_pct(y - ch * 0.25, h), _int_pct(y + ch * 1.25, h) + 1):
                caras.add(p - p % paso)
        alto_rel = alto_bloque / float(ALTO)
        for pct in range(int(_BANDA_MIN * 100), int(_BANDA_MAX * 100) + 1, paso):
            y0 = int(h * pct / 100)
            y1 = min(h, y0 + int(h * alto_rel))
            if y1 <= y0:
                continue
            franja = bordes[y0:y1, :]
            coste[pct] = coste.get(pct, 0.0) + float(np.mean(franja))

    if not coste:
        return 0.18
    # Un bloque de cuatro líneas ocupa un 15% de la altura, así que no basta
    # con que su BORDE SUPERIOR esté libre de cara: hay que mirar todo lo que
    # tapa. Sin esto, el texto empezaba sobre la ventana y terminaba sobre los
    # ojos de la persona.
    alto_pct = max(paso, int(round(alto_bloque / float(ALTO) * 100)))

    def pisa_cara(p: int) -> bool:
        return any(p <= c <= p + alto_pct for c in caras)

    libres = {p: c for p, c in coste.items() if not pisa_cara(p)}
    if not libres:
        on_log("[nicho_general] la cara ocupa todas las franjas; bloque abajo")
        libres = coste
    mejor = min(libres, key=lambda p: libres[p])
    on_log(
        f"[nicho_general] bloque de texto al {mejor}% de altura "
        f"(bordes {libres[mejor]:.1f}, {len(caras)} franja(s) con cara)"
    )
    return mejor / 100.0


def _int_pct(valor: float, total: int) -> int:
    return max(0, min(100, int(round(valor / max(1, total) * 100))))


def _png_bloque(texto: str, work: Path) -> tuple[Path, int]:
    """El bloque de cuatro líneas como PNG transparente. Devuelve (ruta, alto).

    Montserrat cursiva y blanco con borde negro, como el resto de los nichos:
    quien monta uno a mano en CapCut usa esa misma tipografía, y así los vídeos
    de la cuenta se parecen entre sí.
    """
    from PIL import Image, ImageDraw, ImageFont

    from src.nicho_pov_bof.pipeline.video_editor import _font_path

    lineas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    if not lineas:
        raise ValueError("bloque vacío")

    # El cuerpo se ajusta hasta que la línea más larga QUEPA: con un tamaño
    # fijo, "Revisa también tus cupones de descuento" se salía del 9:16 por los
    # dos lados y se leía a medias. Se busca a la baja desde el tamaño bonito.
    ruta_fuente = _font_path("Montserrat-BlackItalic.ttf")
    medidor = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    max_ancho = int(ANCHO * 0.92)
    cuerpo = 52
    while cuerpo > 22:
        fuente = ImageFont.truetype(ruta_fuente, cuerpo)
        anchos = [medidor.textbbox((0, 0), l, font=fuente)[2] for l in lineas]
        if max(anchos) + 40 <= max_ancho:
            break
        cuerpo -= 2
    interlineado = int(cuerpo * 1.28)
    ancho = max(anchos) + 40
    alto = interlineado * len(lineas) + 30

    im = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    dib = ImageDraw.Draw(im)
    for i, linea in enumerate(lineas):
        dib.text(
            (ancho // 2, 15 + i * interlineado), linea, font=fuente,
            fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 235),
            anchor="ma",
        )
    ruta = work / "bloque.png"
    im.save(ruta)
    return ruta, alto


def _quemar_bloque(
    video: Path, texto: str, salida: Path, work: Path, on_log: OnLog,
) -> Path:
    """Pinta el bloque sobre los primeros segundos, donde no tape nada.

    Si algo falla se devuelve el vídeo tal cual: un texto es un adorno y no
    puede tirar un montaje que ya está hecho (mismo criterio que la flecha).
    """
    try:
        png, alto = _png_bloque(texto, work)
        y = _sitio_libre(video, work, alto, on_log)
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-i", str(video), "-i", str(png),
             "-filter_complex",
             f"[0:v][1:v]overlay=(main_w-overlay_w)/2:main_h*{y:.4f}:"
             f"enable='between(t,0,{BLOQUE_S})'[v]",
             "-map", "[v]", "-map", "0:a?",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-c:a", "copy", "-movflags", "+faststart", str(salida)],
            check=True, capture_output=True,
        )
        return salida
    except Exception as e:  # noqa: BLE001
        on_log(f"[nicho_general] sin bloque de texto ({str(e)[:140]})")
        return video
