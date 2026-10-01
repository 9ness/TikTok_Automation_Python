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
_FUENTE = "assets/fonts/Montserrat-ExtraBold.ttf"


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
        if not tras or len(golpes) >= maximo:
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


def render_inserto(
    clip: Path, texto: str, salida: Path, sonido: Path, *,
    dur: float, desde: float = 1.0, fuente: Path | None = None, on_log: OnLog = _noop,
) -> Path:
    """Un inserto de `dur` s: trozo del clip, oscurecido y con contraste,
    viñeta, acercamiento lento, destello blanco al entrar, texto grande arriba
    y el golpe de sonido."""
    fuente = fuente or Path(_FUENTE)
    total = _duracion(clip)
    desde = max(0.0, min(desde, max(0.0, total - dur - 0.05)))
    frames = max(1, int(dur * 30))
    textos = []
    for i, linea in enumerate(_lineas(texto)):
        textos.append(
            f"drawtext=fontfile={fuente}:text='{_texto_ffmpeg(linea)}':fontsize=112:"
            f"fontcolor=white:borderw=6:bordercolor=black@0.85:shadowx=0:shadowy=8:"
            f"shadowcolor=black@0.6:x=(w-text_w)/2:y=h*0.17+{i}*132:enable='gte(t,0.08)'"
        )
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "eq=contrast=1.15:brightness=-0.03:saturation=1.05,vignette=PI/4.5,"
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
    for i, (g, t) in enumerate(zip(golpes, tiempos)):
        if t is None or i >= len(clips) or not Path(clips[i]).is_file():
            on_log(f"[insertos] golpe {i + 1} («{g['texto']}») sin sitio en la voz o sin clip: se salta")
            continue
        fin, sig = t
        corte_a = fin + _MARGEN_S
        corte_b = max(corte_a, sig - _MARGEN_S)
        cortes.append((corte_a, corte_b, Path(clips[i]), g["texto"]))
    if not cortes:
        on_log("[insertos] ningún golpe localizado: vídeo sin insertos")
        return video

    total = _duracion(video)
    partes: list[Path] = []
    t0 = 0.0
    enc = ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30",
           "-c:a", "aac", "-ar", "48000", "-ac", "2"]
    for n, (a, b, clip, texto) in enumerate(cortes):
        seg = work_dir / f"ep_seg{n}.mp4"
        _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t0:.3f}", "-to", f"{a:.3f}", "-i", str(video), *enc, str(seg)], on_log)
        partes.append(seg)
        ins = work_dir / f"ep_ins{n}.mp4"
        render_inserto(clip, texto, ins, sonido, dur=dur, on_log=on_log)
        partes.append(ins)
        on_log(f"[insertos] golpe «{texto}» en {a:.2f}s (pausa {b - a:.2f}s recortada)")
        t0 = b
    fin = work_dir / "ep_fin.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t0:.3f}", "-to", f"{total:.3f}", "-i", str(video), *enc, str(fin)], on_log)
    partes.append(fin)

    lista = work_dir / "ep_lista.txt"
    lista.write_text("".join(f"file '{p}'\n" for p in partes))
    salida = work_dir / "ep_final.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
          *enc, "-movflags", "+faststart", str(salida)], on_log)
    salida.replace(video)
    return video
