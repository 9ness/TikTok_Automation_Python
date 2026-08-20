"""Montaje del Nicho POV BOF Largo.

Capa fina: se cuadran los DOS clips con la voz y se pegan; de ahí en adelante es
el montador del Nicho POV BOF sin tocar nada — mismo bloque de gancho/título/CTA,
misma flecha, mismo mux de audio.

**No se toca la velocidad ni se recorta el guion** (el prompt del curso va tal
cual). La duración la manda SIEMPRE la voz, y como los guiones salen de ~18 a
~25s según la voz, el vídeo se ajusta a esa duración.

Reparto entre clips (lo que pidió el operador): en vez de cuadrar el vídeo
entero contra el audio —que dejaba TODO el alargue al final, sobre el segundo
clip— cada clip se cuadra a SU parte del audio. Así, con una voz de 25s, en vez
de un clip de 10s y otro de 15s salen dos de ~12,5s: el rebobinado se reparte y
se nota menos. La técnica de alargar/recortar es la misma de siempre
(`match_video_to_audio`: rebobina el tramo final si falta, recorta si sobra);
solo cambia que se aplica por clip.

El PUNTO de reparto no es la mitad exacta: se busca una **minipausa** de la voz
cerca del centro (`_punto_de_corte` con `silencedetect`) para que el cambio de
vídeo caiga en un silencio y quede orgánico, no a mitad de palabra. Si no hay
pausa aprovechable, se parte por la mitad.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof.pipeline.duration_match import (
    match_video_to_audio,
    probe_duration,
)
from src.nicho_pov_bof.pipeline.video_editor import (
    _VOZ_CADENA,
    _VOZ_LUFS,
    _VOZ_TP,
    build_video,
    layout_for_producto,
)

OnLog = Callable[[str], None]
OnProgress = Callable[[float, str], None]

_noop: OnLog = lambda _msg: None

# Hasta dónde puede descentrarse el corte. Fuera de [20%, 80%] el reparto
# entre los dos clips se desmadra y uno acaba casi entero a base de rebobinado.
_VENTANA = 0.20
# Dos pausas que se diferencian en menos de esto son igual de buenas al oído,
# así que decide la que reparta mejor el metraje.
_EMPATE_S = 0.06
# La cadena que el mux del POV BOF le aplica a la voz. Se IMPORTA, no se copia:
# si allí se toca el compresor y aquí no, se medirían pausas que en el vídeo no
# existen — que es justo el bug que esto arregla. Un rename revienta al cargar
# el módulo, que es lo que se quiere.
_CADENA_MUX = _VOZ_CADENA
_LOUDNORM_MUX = f"loudnorm=I={_VOZ_LUFS}:TP={_VOZ_TP}:LRA=7"
_noop_progress: OnProgress = lambda _p, _m: None


def _run(cmd: list[str], on_log: OnLog) -> None:
    on_log("+ " + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {proc.stderr[-500:]}")


def _medidas(video: Path) -> tuple[int, int]:
    """`(ancho, alto)` del vídeo. `(1080, 1920)` si no se puede leer."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=s=x:p=0", str(video)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        w, h = (int(x) for x in out.split("x")[:2])
        return (w, h) if w > 0 and h > 0 else (1080, 1920)
    except Exception:  # noqa: BLE001
        return 1080, 1920


def concatenar(clips: list[Path], destino: Path, on_log: OnLog = _noop) -> Path:
    """Pega los clips uno detrás de otro, re-codificando.

    Se re-codifica en vez de copiar el flujo porque los clips vienen de
    generaciones distintas y pueden traer fps o codificación distintos; con
    `-c copy` eso da saltos o directamente un fichero roto.

    Y antes de pegar se IGUALAN tamaño y relación de píxel. El filtro `concat`
    exige que todas las entradas midan lo mismo y falla con
    `Invalid argument (-22)` si no — que es exactamente lo que pasó con un
    vídeo de tres clips donde uno venía de otra generación y traía otro
    tamaño. Se toma el del primero como bueno, y el resto se escala dentro
    (sin recortar) con barras si hiciera falta.
    """
    ancho, alto = _medidas(clips[0])
    entradas: list[str] = []
    for c in clips:
        entradas += ["-i", str(c)]
    cadenas = "".join(
        f"[{i}:v:0]scale={ancho}:{alto}:force_original_aspect_ratio=decrease,"
        f"pad={ancho}:{alto}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}];"
        for i in range(len(clips))
    )
    filtro = (
        cadenas
        + "".join(f"[v{i}]" for i in range(len(clips)))
        + f"concat=n={len(clips)}:v=1:a=0[v]"
    )
    _run([
        "ffmpeg", "-y", "-v", "error", *entradas,
        "-filter_complex", filtro, "-map", "[v]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(destino),
    ], on_log)
    return destino


def _voz_como_se_oye(audio_path: Path, work_dir: Path, on_log: OnLog) -> Path:
    """Rinde la voz con la MISMA cadena que le mete el mux al vídeo.

    Hace falta porque las pausas se miden sobre esto, no sobre el mp3 crudo:
    `speechnorm` levanta los tramos bajos y una pausa de 0,50s en el original
    queda en 0,11s en lo que acaba oyendo el espectador. Eligiendo sobre el
    crudo se cortaba en sitios que suenan a mitad de frase.
    """
    salida = work_dir / "voz_oida.wav"
    try:
        _run([
            "ffmpeg", "-y", "-v", "error", "-i", str(audio_path),
            "-af", f"{_CADENA_MUX},{_LOUDNORM_MUX}", str(salida),
        ], on_log)
        return salida
    except RuntimeError as e:
        # Sin esto no hay corte inteligente, pero tampoco es motivo para tumbar
        # el montaje: se mide sobre el crudo como antes.
        on_log(f"[pov_bof_largo] no pude procesar la voz para medir pausas ({e}); mido en crudo")
        return audio_path


def _detectar_silencios(audio_path: Path) -> list[tuple[float, float]]:
    """Tramos de silencio (inicio, fin) de la voz, vía `silencedetect`.

    Umbral -35 dB y 0,08s: se recogen hasta los huecos entre palabras y luego
    `_punto_de_corte` decide cuáles valen.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(audio_path),
         "-af", "silencedetect=noise=-35dB:d=0.08", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    silencios: list[tuple[float, float]] = []
    inicio: float | None = None
    for linea in proc.stderr.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", linea)
        if m:
            inicio = float(m.group(1))
            continue
        m = re.search(r"silence_end:\s*(-?[\d.]+)", linea)
        if m and inicio is not None:
            silencios.append((inicio, float(m.group(1))))
            inicio = None
    return silencios


def _punto_de_corte(
    audio_path: Path, dur: float, work_dir: Path, on_log: OnLog,
) -> float | None:
    """Instante donde partir los DOS clips, en la pausa MÁS LARGA de la voz.

    Se mide sobre la voz ya procesada (`_voz_como_se_oye`), que es la que suena
    en el vídeo, y gana la pausa más larga dentro de la ventana — no la más
    centrada. Antes mandaba la cercanía al medio y el corte acababa en un hueco
    de 0,3s (0,1s reales al oírlo) mientras la voz seguía hablando; un silencio
    grande algo descentrado se nota mucho menos que uno pequeño en el sitio.

    La ventana existe porque el reparto no puede desmadrarse: cortar al 10%
    deja el 90% de la voz sobre el segundo clip a base de rebobinado, y ahí sí
    se ve el truco. Sin ninguna pausa dentro, se parte por la mitad.
    """
    medible = _voz_como_se_oye(audio_path, work_dir, on_log)
    objetivo = dur / 2
    lo, hi = dur * _VENTANA, dur * (1 - _VENTANA)
    candidatos = [
        (fin - inicio, (inicio + fin) / 2)
        for inicio, fin in _detectar_silencios(medible)
        if lo <= (inicio + fin) / 2 <= hi
    ]
    if not candidatos:
        on_log(
            "[pov_bof_largo] la voz no tiene ninguna pausa aprovechable; "
            "parto por la mitad (el cambio se notará)"
        )
        return None
    # Empates: entre dos pausas parecidas de largas, la más centrada reparte
    # mejor el metraje entre los dos clips.
    mejor = max(candidatos, key=lambda c: c[0])[0]
    larga, centro = min(
        (c for c in candidatos if c[0] >= mejor - _EMPATE_S),
        key=lambda c: abs(c[1] - objetivo),
    )
    on_log(
        f"[pov_bof_largo] corte en la pausa de {larga:.2f}s a {centro:.2f}s "
        f"({100 * centro / dur:.0f}% de la voz; la mitad exacta era {objetivo:.2f}s)"
    )
    return centro


def _concatenar_cuadrado(
    clips: list[Path], audio_path: Path, work_dir: Path, on_log: OnLog = _noop,
) -> Path:
    """Cuadra cada clip con SU parte del audio y luego los pega.

    Reparte la duración de la voz entre los clips y cuadra cada uno a su objetivo
    con `match_video_to_audio` —el mismo rebobinado de tramo final que usa el
    POV BOF—, así que el alargue no cae entero sobre el último clip. La suma da
    la duración del audio; el `match_video_to_audio` de `build_video` ya solo
    recorta al milímetro.

    Con DOS clips, el punto de reparto se busca en una minipausa de la voz
    (`_punto_de_corte`) para que el cambio de vídeo quede orgánico y no a mitad
    de palabra; si no hay pausa, se parte por la mitad. Con otro número de clips
    se reparte a partes iguales.

    Si no se puede medir el audio (raro), se cae al pegado directo de siempre y
    que `build_video` cuadre el conjunto.
    """
    try:
        audio_dur = probe_duration(audio_path)
    except Exception as e:
        on_log(f"[pov_bof_largo] no se pudo medir el audio ({e}); pego sin cuadrar por clip")
        return concatenar(clips, work_dir / "00_pegado.mp4", on_log)

    n = max(1, len(clips))
    if n == 2:
        corte = _punto_de_corte(audio_path, audio_dur, work_dir, on_log)
        primero = corte if corte is not None else audio_dur / 2
        # Ningún clip puede aportar más metraje del que tiene. La pausa puede
        # caer descentrada —la ventana llega al 20/80— y con clips de 8s eso
        # pedía 9,6s a uno de los dos en un audio de 12s: lo que falta lo
        # rellenaba el rebobinado, teniendo material de sobra en el otro clip.
        # Se mueve el corte lo justo para que quepa; sobra metraje, así que lo
        # que se descarta sale del FINAL de cada clip (`match_video_to_audio`
        # recorta por el final), que es justo donde el generador de vídeo suele
        # hacer cosas raras.
        try:
            cabe1 = probe_duration(clips[0])
            cabe2 = probe_duration(clips[1])
        except Exception:  # noqa: BLE001
            cabe1 = cabe2 = 0.0
        if cabe1 > 0 and cabe2 > 0:
            minimo, maximo = max(0.0, audio_dur - cabe2), min(cabe1, audio_dur)
            if minimo <= maximo:
                ajustado = min(max(primero, minimo), maximo)
                if abs(ajustado - primero) > 0.01:
                    on_log(
                        f"[pov_bof_largo] el corte en {primero:.2f}s le pedía a "
                        f"un clip más de lo que dura; se mueve a {ajustado:.2f}s "
                        "para no tener que rebobinar"
                    )
                primero = ajustado
        objetivos = [primero, audio_dur - primero]
    else:
        objetivos = [audio_dur / n] * n
    on_log(
        f"[pov_bof_largo] voz {audio_dur:.2f}s → clips de "
        + ", ".join(f"{o:.2f}s" for o in objetivos)
    )
    cuadrados: list[Path] = []
    for i, (clip, objetivo) in enumerate(zip(clips, objetivos), start=1):
        destino = work_dir / f"clip{i}_cuadrado"
        cuadrados.append(
            match_video_to_audio(clip, objetivo, destino, on_log=on_log)
        )
    return concatenar(cuadrados, work_dir / "00_pegado.mp4", on_log)


def montar(
    *,
    clips: list[Path],
    audio_path: Path,
    textos: dict,
    output_path: Path,
    work_dir: Path,
    producto: str = "",
    semilla: str = "",
    con_gancho: bool = True,
    con_titulo: bool = True,
    con_cta: bool = True,
    con_flecha: bool = True,
    on_log: OnLog = _noop,
    on_progress: OnProgress = _noop_progress,
) -> Path:
    """Monta el vídeo final de un producto a partir de sus clips."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    on_progress(0.02, f"🔗 Cuadrando y uniendo {len(clips)} clips…")
    pegado = _concatenar_cuadrado(
        [Path(c) for c in clips], Path(audio_path), work_dir, on_log,
    )

    def _progreso(pct: float, label: str) -> None:
        on_progress(0.05 + pct * 0.95, label)

    return build_video(
        raw_video=pegado,
        audio_path=Path(audio_path),
        textos=textos or {},
        output_path=Path(output_path),
        work_dir=work_dir,
        layout=layout_for_producto(producto or semilla, (textos or {}).get("cta", "")),
        con_gancho=con_gancho,
        con_titulo=con_titulo,
        con_cta=con_cta,
        con_flecha=con_flecha,
        semilla=semilla or Path(output_path).stem,
        on_log=on_log,
        on_progress=_progreso,
    )
