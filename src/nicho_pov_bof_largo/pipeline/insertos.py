"""Insertos «épicos» del modo Épico del POV BOF Largo.

Copiado del patrón de los vídeos virales de referencia (oct 2026): en la PAUSA
entre dos frases la voz se calla, entra un corte de ~1 s con el producto en un
escenario oscuro con foco (o a contraluz sobre blanco), destello blanco al
entrar, dos o tres palabras grandes arriba y un golpe de sonido; luego sigue la
voz. Nunca habla encima.

Dónde va cada corte lo decide el GUION: la IA escribe marcas
`[[GOLPE: TEXTO | escena]]` detrás de las frases potentes (ver
`prompts/guion_epico.md`). Aquí se:

1. separan las marcas del guion (`separar_golpes`) — la voz nunca las lee;
2. localiza con Whisper dónde ACABA cada frase marcada y dónde empieza la
   siguiente (`localizar`);
3. corta el vídeo ya montado por esas pausas, **quitando el silencio** de antes
   y de después del inserto para que el ritmo sea seco (petición del operador:
   en la primera prueba se notaba un hueco hasta que volvía la voz), y pega los
   insertos (`aplicar`).

Se hace DESPUÉS del montaje normal, sobre el vídeo terminado: rótulo,
subtítulos, flecha y voz ya están quemados con sus tiempos, y cortar por una
pausa no los desincroniza (vídeo y audio se cortan juntos). Durante el inserto
no hay rótulo ni subtítulos, igual que en las referencias.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Callable

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

_MARCA_RE = re.compile(r"\[\[\s*GOLPE\s*:\s*([^|\]]+?)\s*(?:\|\s*([^\]]*?))?\s*\]\]", re.IGNORECASE)
# Margen que se deja tras la última palabra y antes de la siguiente: sin él la
# consonante final se corta en seco y suena a error de edición.
_MARGEN_S = 0.06
_FUENTE = str(Path(__file__).resolve().parents[3] / "assets/fonts/Montserrat-ExtraBold.ttf")
# Fondo blanco: titular rojo con serifa, como los «VESTIDO PISTACHO» de las
# referencias (oct 2026). Sobre blanco el texto blanco con borde negro no pega.
_FUENTE_ROJA = str(Path(__file__).resolve().parents[3] / "assets/fonts/PlayfairDisplay-Black.ttf")
_ROJO = "0xD7261E"
# Luminancia media (0-255) del tercio de arriba a partir de la cual el inserto
# se trata como «fondo blanco».
_CLARO = 170


# ---------------------------------------------------------------------------
# Guion
# ---------------------------------------------------------------------------
def separar_golpes(guion: str, maximo: int = 3) -> tuple[str, list[dict]]:
    """`(guion limpio, golpes)`. Cada golpe: `{tras, texto, escena}`.

    `tras` es la frase que acaba justo antes de la marca: es lo que se busca en
    la voz. Se descartan las marcas sin frase delante (al principio) y las que
    pasen de `maximo`.
    """
    golpes: list[dict] = []
    limpio_partes: list[str] = []
    pos = 0
    for m in _MARCA_RE.finditer(guion or ""):
        antes = (guion[pos:m.start()]).strip()
        limpio_partes.append(antes)
        pos = m.end()
        texto_hasta_aqui = " ".join(p for p in limpio_partes if p)
        frases = re.split(r"(?<=[.!?…])\s+", texto_hasta_aqui.strip())
        tras = frases[-1].strip() if frases and frases[-1].strip() else ""
        # Dos marcas seguidas tras la misma frase serían dos cortes en la
        # misma pausa: el segundo no se encontraría en la voz y pediría un
        # inserto de más. Vale la primera.
        if not tras or len(golpes) >= maximo or (golpes and golpes[-1]["tras"] == tras):
            continue
        golpes.append({
            "tras": tras,
            "texto": " ".join(m.group(1).split()).upper()[:40],
            "escena": " ".join((m.group(2) or "").split()),
        })
    limpio_partes.append(guion[pos:].strip() if guion else "")
    limpio = " ".join(" ".join(p for p in limpio_partes if p).split())
    # El primer golpe es el GANCHO y tiene que entrar antes de los 3 s: va
    # siempre tras la PRIMERA frase aunque la IA lo haya puesto más tarde.
    primera = re.split(r"(?<=[.!?…])\s+", limpio, maxsplit=1)[0].strip() if limpio else ""
    if golpes and primera and golpes[0]["tras"] != primera:
        golpes[0]["tras"] = primera
        if len(golpes) > 1 and golpes[1]["tras"] == primera:
            golpes.pop(1)
    return limpio, golpes


def _norm(palabra: str) -> str:
    s = unicodedata.normalize("NFD", palabra.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ]", "", s)


def localizar(palabras: list[dict], golpes: list[dict]) -> list[tuple[float, float] | None]:
    """Para cada golpe, `(fin de su frase, inicio de la siguiente palabra)`.

    Se busca la cola de la frase (sus 3 últimas palabras) en orden, avanzando:
    así dos frases que acaben igual no se confunden. `None` si no aparece
    (Whisper oyó otra cosa) — ese golpe se salta, no se inventa.
    """
    from difflib import SequenceMatcher

    toks = [_norm(w.get("word", "")) for w in palabras]
    salida: list[tuple[float, float] | None] = []
    desde = 0
    for g in golpes:
        cola = [t for t in (_norm(x) for x in g["tras"].split()) if t][-3:]
        hallado = None
        if cola:
            # Parecido, no igualdad: Whisper se come sílabas al principio de
            # frase («¿Te irrita afeitarte?» → «Si rita feitarte»). Se toma la
            # PRIMERA ventana que se parezca lo bastante, avanzando en orden.
            mejor = (0.0, -1)
            for i in range(desde, len(toks) - len(cola) + 1):
                sc = sum(
                    SequenceMatcher(None, a, b).ratio() for a, b in zip(cola, toks[i:i + len(cola)])
                ) / len(cola)
                if sc >= 0.75:
                    mejor = (sc, i)
                    break
                if sc > mejor[0]:
                    mejor = (sc, i)
            if mejor[1] >= 0 and mejor[0] >= 0.6:
                fin_i = mejor[1] + len(cola) - 1
                if fin_i + 1 < len(palabras):
                    hallado = (float(palabras[fin_i]["end"]), float(palabras[fin_i + 1]["start"]))
                    desde = fin_i + 1
        salida.append(hallado)
    return salida


# ---------------------------------------------------------------------------
# Vídeo
# ---------------------------------------------------------------------------
def _run(cmd: list[str], on_log: OnLog) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        on_log(f"[insertos] ffmpeg falló: {r.stderr[-400:]}")
        raise RuntimeError(r.stderr[-400:])


def _duracion(video: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip() or 0)


def _texto_ffmpeg(t: str) -> str:
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def _lineas(texto: str, max_car: int = 13) -> list[str]:
    """Parte el texto en líneas cortas (letra grande en 1080 de ancho)."""
    lineas: list[str] = []
    for w in texto.split():
        if lineas and len(lineas[-1]) + 1 + len(w) <= max_car:
            lineas[-1] += " " + w
        else:
            lineas.append(w)
    return lineas[:3]


def _talla_que_cabe(lineas: list[str], fuente: Path, *, maximo: int, ancho: int) -> int:
    """La letra más grande (≤ `maximo`) con la que la línea más larga cabe en
    `ancho` px. Se mide con PIL; sin PIL, una estimación por caracteres."""
    if not lineas:
        return maximo
    try:
        from PIL import ImageFont

        f = ImageFont.truetype(str(fuente), 100)
        mas_ancha = max(f.getlength(x) for x in lineas)
        return max(60, min(maximo, int(100 * ancho / mas_ancha)))
    except Exception:  # noqa: BLE001
        return max(60, min(maximo, int(ancho / (0.75 * max(len(x) for x in lineas)))))


def es_fondo_claro(clip: Path, desde: float = 1.0) -> bool:
    """¿El inserto es de fondo blanco? Se mira el tercio de ARRIBA del
    fotograma (donde va el texto): en los de contraluz el producto está
    abajo y oscuro, pero el fondo es blanco."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{desde:.2f}", "-i", str(clip), "-frames:v", "1",
         "-vf", "scale=36:64,crop=36:22:0:0,format=gray", "-f", "rawvideo", "-"],
        capture_output=True,
    )
    datos = r.stdout
    return bool(datos) and sum(datos) / len(datos) > _CLARO


def render_inserto(
    clip: Path, texto: str, salida: Path, sonido: Path, *,
    dur: float, desde: float = 1.0, fuente: Path | None = None,
    claro: bool | None = None, on_log: OnLog = _noop,
) -> Path:
    """Un inserto de `dur` s: trozo del clip, destello blanco al entrar,
    acercamiento lento, texto grande arriba y el golpe de sonido.

    Dos estilos según el fondo (`claro`, que se mide si no se da):
    - oscuro: contraste, viñeta y letra blanca con borde negro;
    - blanco: sin oscurecer ni viñeta, titular ROJO con serifa.
    """
    total = _duracion(clip)
    desde = max(0.0, min(desde, max(0.0, total - dur - 0.05)))
    if claro is None:
        claro = es_fondo_claro(clip, desde)
    frames = max(1, int(dur * 30))
    textos = []
    if claro:
        fuente = fuente or Path(_FUENTE_ROJA)
        lineas = _lineas(texto, max_car=11)
        talla = _talla_que_cabe(lineas, fuente, maximo=150, ancho=960)
        for i, linea in enumerate(lineas):
            textos.append(
                f"drawtext=fontfile={fuente}:text='{_texto_ffmpeg(linea)}':fontsize={talla}:"
                f"fontcolor={_ROJO}:shadowx=0:shadowy=4:shadowcolor=black@0.25:"
                f"x=(w-text_w)/2:y=h*0.11+{i}*{int(talla * 1.1)}:enable='gte(t,0.08)'"
            )
        tono = "eq=contrast=1.06:saturation=1.05"
    else:
        fuente = fuente or Path(_FUENTE)
        lineas = _lineas(texto)
        # Una palabra sola más larga que la línea («ENTRETENIMIENTO») se salía
        # por los lados a 112: la talla se ajusta a la más ancha.
        talla = _talla_que_cabe(lineas, fuente, maximo=112, ancho=960)
        for i, linea in enumerate(lineas):
            textos.append(
                f"drawtext=fontfile={fuente}:text='{_texto_ffmpeg(linea)}':fontsize={talla}:"
                f"fontcolor=white:borderw=6:bordercolor=black@0.85:shadowx=0:shadowy=8:"
                f"shadowcolor=black@0.6:x=(w-text_w)/2:y=h*0.17+{i}*{int(talla * 1.18)}:enable='gte(t,0.08)'"
            )
        tono = "eq=contrast=1.15:brightness=-0.03:saturation=1.05,vignette=PI/4.5"
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        f"{tono},"
        f"zoompan=z='1.0+0.05*on/{frames}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
        "fade=t=in:st=0:d=0.15:color=white"
        + ("," + ",".join(textos) if textos else "")
    )
    _run([
        "ffmpeg", "-y", "-v", "error", "-ss", f"{desde:.3f}", "-t", f"{dur:.3f}", "-i", str(clip),
        "-i", str(sonido),
        "-filter_complex",
        f"[0:v]{vf}[v];[1:a]aresample=48000,apad,atrim=0:{dur:.3f},afade=t=out:st={max(0.0, dur - 0.1):.3f}:d=0.1[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", str(salida),
    ], on_log)
    return salida


def elegir_sonidos(sonido: Path, video: Path, claros: list[bool]) -> list[Path]:
    """El sonido de cada golpe. `sonido` puede ser un fichero (todos igual) o
    la carpeta del banco: entonces cada VÍDEO sortea uno para sus insertos
    oscuros (fijo por nombre de vídeo, así un remontaje suena igual) y los de
    fondo blanco llevan el boom grave."""
    from src.nicho_pov_bof_largo import config

    sonido = Path(sonido)
    if not sonido.is_dir():
        return [sonido] * len(claros)
    oscuros = [sonido / n for n in config.SONIDOS_OSCURO if (sonido / n).is_file()]
    blanco = sonido / config.SONIDO_BLANCO
    import zlib
    # Sin la hora que lleva el nombre del vídeo («1 Banco … 2244»): el mismo
    # producto suena igual aunque se remonte.
    clave = re.sub(r"\s*\d{3,4}$", "", Path(video).stem)
    base = oscuros[zlib.crc32(clave.encode()) % len(oscuros)] if oscuros else blanco
    return [blanco if (c and blanco.is_file()) else base for c in claros]


def aplicar(
    video: Path, palabras: list[dict], golpes: list[dict], clips: list[Path],
    work_dir: Path, *, sonido: Path, dur: float = 1.0, on_log: OnLog = _noop,
) -> Path:
    """Mete los insertos en `video` (EN SITIO). Devuelve el mismo path.

    `clips[i]` es el clip épico del golpe `i`. Los golpes que no se localicen
    en la voz se saltan con aviso; si no queda ninguno, el vídeo no se toca.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    tiempos = localizar(palabras, golpes)
    cortes = []
    claros = [bool(i < len(clips) and Path(clips[i]).is_file() and es_fondo_claro(Path(clips[i])))
              for i in range(len(golpes))]
    sonidos = elegir_sonidos(sonido, video, claros)
    for i, (g, t) in enumerate(zip(golpes, tiempos)):
        if t is None or i >= len(clips) or not Path(clips[i]).is_file():
            on_log(f"[insertos] golpe {i + 1} («{g['texto']}») sin sitio en la voz o sin clip: se salta")
            continue
        fin, sig = t
        corte_a = fin + _MARGEN_S
        corte_b = max(corte_a, sig - _MARGEN_S)
        cortes.append((corte_a, corte_b, Path(clips[i]), g["texto"], claros[i], sonidos[i]))
    if not cortes:
        on_log("[insertos] ningún golpe localizado: vídeo sin insertos")
        return video

    total = _duracion(video)
    partes: list[Path] = []
    t0 = 0.0
    enc = ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
           "-c:a", "aac", "-ar", "48000", "-ac", "2"]
    for n, (a, b, clip, texto, claro, son) in enumerate(cortes):
        seg = work_dir / f"ep_seg{n}.mp4"
        _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t0:.3f}", "-to", f"{a:.3f}", "-i", str(video), *enc, str(seg)], on_log)
        partes.append(seg)
        ins = work_dir / f"ep_ins{n}.mp4"
        render_inserto(clip, texto, ins, son, dur=dur, claro=claro, on_log=on_log)
        partes.append(ins)
        on_log(f"[insertos] golpe «{texto}» en {a:.2f}s (pausa {b - a:.2f}s recortada, "
               f"{'blanco' if claro else 'oscuro'}, {son.stem})")
        t0 = b
    fin = work_dir / "ep_fin.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t0:.3f}", "-to", f"{total:.3f}", "-i", str(video), *enc, str(fin)], on_log)
    partes.append(fin)

    lista = work_dir / "ep_lista.txt"
    lista.write_text("".join(f"file '{p}'\n" for p in partes))
    salida = work_dir / "ep_final.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
          *enc, "-movflags", "+faststart", str(salida)], on_log)
    # `move` y no `Path.replace`: el vídeo vive en el mount de Drive y el
    # trabajo en /tmp — son dos sistemas de ficheros y `rename` da EXDEV.
    shutil.move(str(salida), str(video))
    return video
