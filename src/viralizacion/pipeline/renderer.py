"""Construcción del filter_complex y render final con ffmpeg: gancho (3s,
cara en primer plano) + tramos de paisaje, xfade, filtro "película"
(+ extras por estilo), subtítulos quemados (estilo A/B/C) y mezcla de
audio (voz [+ música opcional]).

Optimizaciones (2026-07):
- Tope de duración (~55s) + ventana de audio por ronda (no monstruos de 3min).
- Render en 2 fases: pre-extract clip a clip (1 input, RAM baja) → xfade
  sobre clips cortos ya en 1080x1920 → grade/subs/audio final.
- Encode veryfast/CRF23 para peso TikTok y velocidad.
"""

from __future__ import annotations

import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.viralizacion import config
from src.viralizacion.pipeline.ffmpeg_utils import (
    ffprobe_duration,
    leading_silence,
    run,
)
from src.viralizacion.pipeline.styles import StylePreset
from src.viralizacion.pipeline.transcriber import group_into_phrases

OnLog = Callable[[str], None]


@dataclass
class ClipSpec:
    src: Path
    start: float
    nominal_dur: float
    extract_start: float
    extract_dur: float
    zoom: float
    cx_frac: float | None = None


def slice_words(words: list[dict], window_start: float, window_dur: float) -> list[dict]:
    """Recorta palabras a la ventana de audio y re-basa timings a t=0."""
    end = window_start + window_dur
    out: list[dict] = []
    for w in words:
        ws = float(w["start"])
        we = float(w["end"])
        if we <= window_start or ws >= end:
            continue
        out.append({
            "word": w["word"],
            "start": max(0.0, ws - window_start),
            "end": min(window_dur, we - window_start),
        })
    return out


def snap_to_first_word(
    words: list[dict],
    window_start: float,
    window_dur: float,
    audio_path: Path | None = None,
    lead_in: float = 0.06,
) -> float:
    """Adelanta el arranque de la ventana solo lo que haya de SILENCIO delante.

    Los audios traen entre 0,1 y casi 2 segundos de aire antes de la primera
    palabra, y eso al empezar un TikTok es scroll asegurado.

    Manda `silencedetect`, que mide el fichero. Antes se cruzaba con los
    timings de Whisper y se avanzaba hasta "la primera palabra": en
    `pablo5_full.mp3` ("Pau Donés, unos días antes de morir…") Whisper daba la
    primera palabra en 1,90s porque se salta el nombre propio, y el arranque
    se comía "Pau Donés". Whisper NO decide dónde empieza el audio; solo se
    usa si no hay fichero que medir.

    Solo adelanta, nunca retrasa. La ventana se ACORTA en lo adelantado (el
    contenido hablado es el mismo, solo desaparece el silencio de delante).
    """
    if audio_path is not None:
        silencio = leading_silence(audio_path, start=window_start)
        return max(window_start, window_start + silencio - lead_in)

    # Sin fichero (tests, llamadas sintéticas): lo único que queda es Whisper.
    end = window_start + window_dur
    siguientes = [
        float(w["start"]) for w in words
        if window_start <= float(w["start"]) < end
    ]
    if not siguientes:
        return window_start
    return max(window_start, min(siguientes) - lead_in)


def _jittered_paisaje_durations(fill_duration: float, n: int) -> list[float]:
    if n <= 1:
        return [fill_duration]
    lo, hi = config.PAISAJE_CLIP_DUR_JITTER_RANGE
    weights = [random.uniform(lo, hi) for _ in range(n)]
    scale = fill_duration / sum(weights)
    durations = [w * scale for w in weights]
    for _ in range(5):
        excess = 0.0
        free_idx = []
        for i, d in enumerate(durations):
            if d < lo:
                excess += d - lo
                durations[i] = lo
            elif d > hi:
                excess += d - hi
                durations[i] = hi
            else:
                free_idx.append(i)
        if abs(excess) < 1e-9 or not free_idx:
            break
        share = excess / len(free_idx)
        for i in free_idx:
            durations[i] += share
    diff = fill_duration - sum(durations)
    durations[-1] += diff
    return durations


def distribute_with_caps(total: float, caps: list[float]) -> list[float]:
    """Reparte `total` entre clips SIN pasarse del material que tiene cada uno.

    Los clips de la biblioteca son planos reales y duran lo que duran (3,3s a
    17s). Un reparto ciego pediría más segundos de los que un clip tiene y
    ffmpeg rellenaría con el último fotograma congelado. Aquí lo que sobra de
    un clip corto se reparte entre los que aún tienen margen.
    """
    n = len(caps)
    if n == 0:
        return []
    if total <= 0:
        return [0.0] * n
    share = [total / n] * n
    for _ in range(n):
        excess = 0.0
        free = []
        for i in range(n):
            if share[i] > caps[i]:
                excess += share[i] - caps[i]
                share[i] = caps[i]
            elif share[i] < caps[i] - 1e-6:
                free.append(i)
        if excess <= 1e-6 or not free:
            break
        add = excess / len(free)
        for i in free:
            share[i] += add
    return share



def _rounded_square_mask(work: Path, size: int, radius: int) -> Path:
    """Máscara en escala de grises para redondear las esquinas del cuadrado.

    Se genera una vez por render y se reutiliza: `alphamerge` necesita un
    canal alfa y ffmpeg no sabe dibujar rectángulos redondeados por sí solo.
    """
    from PIL import Image, ImageDraw
    out = work / f"mask_sq_{size}_{radius}.png"
    if out.is_file():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    m.save(out)
    return out


def _vignette_filter(style: StylePreset) -> str:
    """Viñeta fija o "respirando" (vaivén lento) según el estilo."""
    if style.vignette_breathe > 0:
        # Periodo largo y aleatorio: es un latido de fondo, no un parpadeo.
        period = random.uniform(6.0, 10.0)
        phase = random.uniform(0.0, 6.28)
        return (
            f"vignette=angle='{style.vignette_angle}"
            f"+{style.vignette_breathe:.3f}*sin(2*PI*t/{period:.2f}+{phase:.2f})'"
            f":mode=forward:eval=frame"
        )
    return f"vignette=angle={style.vignette_angle}:mode=forward"


def _light_leak_filter(style: StylePreset, duration: float) -> str:
    """Destellos cálidos tipo fuga de luz, repartidos por el vídeo.

    Se modela como una campana de Gauss sobre el brillo: sube y baja suave en
    ~0,5s. Se evita el primer y último segundo para no pisar la entrada ni el
    cierre.
    """
    n = max(0, style.light_leaks)
    if n <= 0 or duration <= 3:
        return ""
    margin = 1.5
    span = max(1.0, duration - 2 * margin)
    # Repartidos con jitter, no equiespaciados (delataría la plantilla).
    times = [
        margin + span * (i + 0.5) / n + random.uniform(-0.8, 0.8)
        for i in range(n)
    ]
    terms = "+".join(
        f"{random.uniform(0.16, 0.26):.3f}*exp(-pow(t-{max(0.5, t):.2f},2)/0.06)"
        for t in times
    )
    return f"eq=brightness='{terms}':eval=frame"


def _scratches_filter(style: StylePreset, duration: float) -> str:
    """Rayaduras verticales tipo proyector viejo.

    Líneas finas que aparecen unas décimas en una posición al azar. Se generan
    en Python (posición e instante fijos por render) en vez de con `random()`
    de ffmpeg: así es reproducible y no cuesta CPU por frame.
    """
    n = max(0, style.film_scratches)
    if n <= 0 or duration <= 2:
        return ""
    parts = []
    for _ in range(n):
        x = random.randint(int(config.TARGET_W * 0.08), int(config.TARGET_W * 0.92))
        t0 = random.uniform(0.5, max(0.6, duration - 1.0))
        dur = random.uniform(0.06, 0.18)
        w = random.choice([1, 2, 2, 3])
        alpha = random.uniform(0.12, 0.28)
        parts.append(
            f"drawbox=x={x}:y=0:w={w}:h=ih:color=white@{alpha:.2f}:t=fill"
            f":enable='between(t,{t0:.2f},{t0 + dur:.2f})'"
        )
    return ",".join(parts)


def _dust_plate(work: Path, idx: int, dots: int) -> Path:
    """Lámina PNG transparente con motas de polvo, para superponer a la deriva.

    Se intentó dibujar cada mota con `drawbox` + `enable`: para que hubiera
    unas cuantas en pantalla a la vez hacían falta cientos de filtros y aun
    así no se movían (`drawbox` no puede animar su posición — su `t` es el
    grosor). Con una lámina que se desplaza basta UN `overlay` (que sí evalúa
    `t` en x/y) para tener decenas de motas moviéndose, y entrando y saliendo
    del encuadre porque la lámina es más grande que el vídeo.
    """
    from PIL import Image, ImageDraw, ImageFilter

    out = work / f"dust_{idx}_{dots}.png"
    if out.is_file():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    w = int(config.TARGET_W * 1.5)
    h = int(config.TARGET_H * 1.5)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dib = ImageDraw.Draw(img)
    # Semilla fija por lámina: las dos capas tienen que ser distintas entre
    # sí, pero no hace falta que cambien en cada render (el anti-fingerprint
    # lo pone la deriva, que sí se sortea).
    rnd = random.Random(4200 + idx)
    for _ in range(dots):
        x, y = rnd.randrange(w), rnd.randrange(h)
        r = rnd.choice([2, 2, 3, 3, 4, 5, 7])
        alpha = rnd.randint(55, 175)
        # Negras: en blanco parecían nieve/estrellas. El polvo de película
        # TAPA luz, y sobre paisajes claros se lee mucho mejor en oscuro.
        tono = (0, 0, 0) if rnd.random() < 0.88 else (255, 255, 255)
        dib.ellipse([x - r, y - r, x + r, y + r], fill=(*tono, alpha))
    img.filter(ImageFilter.GaussianBlur(0.8)).save(out)
    return out


def _jittered_eq_filter(extra: dict) -> str:
    frac = config.EQ_JITTER_FRAC
    contrast = config.EQ_BASE_CONTRAST * random.uniform(1 - frac, 1 + frac)
    saturation = config.EQ_BASE_SATURATION * random.uniform(1 - frac, 1 + frac)
    brightness = config.EQ_BASE_BRIGHTNESS * random.uniform(1 - frac, 1 + frac)
    parts = [
        f"contrast={contrast:.4f}",
        f"saturation={saturation:.4f}",
        f"brightness={brightness:.4f}",
        f"gamma={config.EQ_BASE_GAMMA:.4f}",
    ]
    for k, v in extra.items():
        parts.append(f"{k}={v}")
    return "eq=" + ":".join(parts)


def build_paisaje_segments(fill_duration: float) -> int:
    """Cuántos tramos de paisaje entran en `fill_duration`.

    Con tope: el `xfade` final abre UN input de vídeo por tramo y con 19
    decodificadores de 1080x1920 a la vez ffmpeg murió por OOM (SIGKILL) en
    el VPS de 8 GB. Pasado el tope los tramos simplemente duran más.
    """
    n = max(1, round(fill_duration / config.PAISAJE_CLIP_TARGET_S))
    return min(n, config.MAX_PAISAJE_CLIPS)


def build_transitions(n_clips: int, style: "StylePreset | None" = None) -> list[tuple[str, float]]:
    if n_clips < 2:
        return []
    # Cada estilo puede traer su propia transición entre paisajes (disolución
    # larga, fundido a blanco…). Es una de las señas que diferencian un ciclo
    # de otro. Sin override se usa la de config.
    ttype, tbase = (
        style.transition_landscape
        if style is not None and style.transition_landscape
        else config.TRANSITION_LANDSCAPE
    )
    lo, hi = config.TRANSITION_LANDSCAPE_JITTER_RANGE
    # El jitter escala la duración base del estilo, no una constante global.
    scale = tbase / config.TRANSITION_LANDSCAPE[1] if config.TRANSITION_LANDSCAPE[1] else 1.0
    landscape = [
        (ttype, round(random.uniform(lo, hi) * scale, 3))
        for _ in range(n_clips - 2)
    ]
    return [config.TRANSITION_HOOK] + landscape


def build_clip_specs(
    hook_video: Path,
    hook_start: float,
    hook_cx_frac: float,
    paisaje_segments: list[tuple[Path, float, float]],
    transitions: list[tuple[str, float]],
    target_duration: float,
) -> list[ClipSpec]:
    """`paisaje_segments` es (fichero, inicio, duración) por clip.

    Cada paisaje puede venir de un FICHERO distinto (biblioteca de clips) o
    todos del mismo vídeo largo (modo antiguo); al renderer le da igual.
    El zoom se sortea por clip, así que el mismo material nunca sale con el
    mismo encuadre dos veces.
    """
    nominal = [(hook_video, hook_start, config.HOOK_DUR, hook_cx_frac,
                random.uniform(*config.HOOK_ZOOM_JITTER_RANGE))]
    nominal += [
        (src, s, d, None, random.uniform(*config.PAISAJE_ZOOM_JITTER_RANGE))
        for src, s, d in paisaje_segments
    ]

    n = len(nominal)
    specs = []
    for i, (src, start, dur, cx, zoom) in enumerate(nominal):
        in_dur = transitions[i - 1][1] if i > 0 else 0.0
        out_dur = transitions[i][1] if i < n - 1 else 0.0
        extra_start = in_dur / 2
        extra_end = out_dur / 2
        specs.append(ClipSpec(
            src=src,
            start=start,
            nominal_dur=dur,
            extract_start=max(0.0, start - extra_start),
            extract_dur=dur + extra_start + extra_end,
            zoom=zoom,
            cx_frac=cx,
        ))

    total_nominal = sum(s.nominal_dur for s in specs)
    assert abs(total_nominal - target_duration) < 1e-2, (
        f"Las duraciones nominales ({total_nominal}) no cuadran con target_duration ({target_duration})"
    )
    return specs


def xfade_offsets(specs: list[ClipSpec], transitions: list[tuple[str, float]]) -> list[float]:
    offsets = []
    running = specs[0].extract_dur
    for s, (_ttype, tdur) in zip(specs[1:], transitions):
        offsets.append(running - tdur)
        running = running + s.extract_dur - tdur
    return offsets


def _ken_burns_vf(spec: ClipSpec, delta: float) -> str:
    """Zoom lento sobre el clip (Ken Burns), dirección al azar.

    Se escala por encima del destino y `zoompan` recorta una ventana que se
    va cerrando (o abriendo) frame a frame, así el plano "respira" en vez de
    parecer una foto fija. La dirección se sortea por clip para que dos
    paisajes seguidos no se muevan igual.
    """
    zmax = 1.0 + max(0.0, delta)
    # Margen extra para que el zoom no pierda resolución al recortar.
    w = int(config.TARGET_W * zmax)
    h = int(config.TARGET_H * zmax)
    frames = max(1, int(round(spec.extract_dur * config.TARGET_FPS)))
    rate = delta / frames
    if random.random() < 0.5:
        z = f"min(1+{rate:.6f}*on,{zmax:.4f})"      # acercarse
    else:
        z = f"max({zmax:.4f}-{rate:.6f}*on,1.0)"    # alejarse
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d=1:s={config.TARGET_W}x{config.TARGET_H}:fps={config.TARGET_FPS}"
    )


def _clip_vf(spec: ClipSpec, ken_burns: float = 0.0) -> str:
    # El Ken Burns solo va en los PAISAJES (`cx_frac is None`). En el gancho
    # el encuadre está calculado sobre la cara detectada; moverlo la
    # descentraría o le cortaría la frente.
    if ken_burns > 0 and spec.cx_frac is None:
        return (
            f"{_ken_burns_vf(spec, ken_burns)},"
            f"hflip,format=yuv420p,setsar=1"
        )

    scale_w = max(config.TARGET_W, round(config.TARGET_W * spec.zoom))
    scale_h = max(config.TARGET_H, round(config.TARGET_H * spec.zoom))
    if spec.cx_frac is not None:
        x_expr = f"min(max((in_w-{config.TARGET_W})*{spec.cx_frac},0),in_w-{config.TARGET_W})"
    else:
        x_expr = f"(in_w-{config.TARGET_W})/2"
    y_expr = f"(in_h-{config.TARGET_H})/2"
    return (
        f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
        f"crop={config.TARGET_W}:{config.TARGET_H}:x='{x_expr}':y='{y_expr}',"
        f"hflip,fps={config.TARGET_FPS},format=yuv420p,setsar=1"
    )


def _extract_clip(spec: ClipSpec, out_path: Path, on_log: OnLog | None,
                  ken_burns: float = 0.0) -> Path:
    """Fase 1: un solo input → clip corto 1080x1920. RAM baja, seek rápido."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{spec.extract_start:.3f}",
        "-t", f"{spec.extract_dur:.3f}",
        "-i", str(spec.src),
        "-vf", _clip_vf(spec, ken_burns),
        "-an",
        "-c:v", "libx264",
        "-preset", config.FFMPEG_CLIP_PRESET,
        "-crf", str(config.FFMPEG_CLIP_CRF),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_path),
    ]
    run(cmd, on_log=on_log)
    return out_path


def _xfade_por_tandas(
    clip_paths: list[Path],
    specs: list[ClipSpec],
    transitions: list[tuple[str, float]],
    out_path: Path,
    on_log: OnLog | None,
) -> Path:
    """Monta los tramos en grupos y luego encadena los grupos.

    `transitions[i]` es la transición ENTRE el tramo i y el i+1, así que las
    de dentro de un grupo se usan al montarlo y la que cae en su frontera se
    guarda para unir ese grupo con el siguiente.
    """
    # Reparto PAREJO en `n_grupos` trozos, no "de `tam` en `tam`": cortando a
    # tamaño fijo, 8 tramos daban un grupo de 7 y otro de 1, y pegar el suelto
    # al anterior dejaba un grupo de 8 — otra vez por encima del máximo, que
    # se volvía a trocear igual: recursión infinita.
    n = len(clip_paths)
    tam = config.XFADE_MAX_INPUTS
    n_grupos = -(-n // tam)
    base, resto = divmod(n, n_grupos)
    grupos: list[tuple[int, int]] = []
    ini = 0
    for g in range(n_grupos):
        fin = ini + base + (1 if g < resto else 0)
        grupos.append((ini, fin))
        ini = fin

    if on_log:
        on_log(f"[renderer] xfade por tandas: {len(clip_paths)} tramos en {len(grupos)} grupos")

    parciales: list[Path] = []
    specs_parciales: list[ClipSpec] = []
    trans_entre: list[tuple[str, float]] = []

    for idx, (ini, fin) in enumerate(grupos):
        sub_trans = transitions[ini:fin - 1]
        parcial = out_path.with_name(f"{out_path.stem}_t{idx:02d}.mp4")
        _xfade_clips(clip_paths[ini:fin], specs[ini:fin], sub_trans, parcial, on_log)
        # Duración del grupo: lo que suman sus tramos menos el solape de sus
        # transiciones internas (es lo que `xfade_offsets` necesita luego).
        dur = sum(sp.extract_dur for sp in specs[ini:fin]) - sum(t[1] for t in sub_trans)
        parciales.append(parcial)
        specs_parciales.append(
            ClipSpec(src=parcial, start=0.0, nominal_dur=dur,
                     extract_start=0.0, extract_dur=dur, zoom=1.0)
        )
        if fin < len(clip_paths):
            trans_entre.append(transitions[fin - 1])

    return _xfade_clips(parciales, specs_parciales, trans_entre, out_path, on_log)


def _xfade_clips(
    clip_paths: list[Path],
    specs: list[ClipSpec],
    transitions: list[tuple[str, float]],
    out_path: Path,
    on_log: OnLog | None,
) -> Path:
    """Fase 2: xfade sobre clips YA recortados (pocos MB c/u, sin reabrir el 2.5GB).

    Por TANDAS cuando hay más de `XFADE_MAX_INPUTS` tramos: ffmpeg abre un
    decodificador 1080x1920 por entrada y con 19 se quedó sin memoria en el
    VPS de 8 GB. Se montan grupos pequeños y luego se encadenan los grupos
    entre sí (recursivo), así la memoria no depende del nº de tramos y la
    duración del vídeo deja de estar limitada por el montaje.
    """
    if len(clip_paths) == 1:
        shutil.copy2(clip_paths[0], out_path)
        return out_path

    if len(clip_paths) > config.XFADE_MAX_INPUTS:
        return _xfade_por_tandas(clip_paths, specs, transitions, out_path, on_log)

    input_args: list[str] = []
    for p in clip_paths:
        input_args += ["-i", str(p)]

    offsets = xfade_offsets(specs, transitions)
    filters: list[str] = []
    prev = "0:v"
    for i in range(1, len(clip_paths)):
        out_label = f"x{i}"
        ttype, tdur = transitions[i - 1]
        filters.append(
            f"[{prev}][{i}:v]xfade=transition={ttype}:"
            f"duration={tdur}:offset={offsets[i-1]:.3f}[{out_label}]"
        )
        prev = out_label

    filter_script = ";\n".join(filters)
    script_path = out_path.with_suffix(".xfade.txt")
    script_path.write_text(filter_script, encoding="utf-8")

    cmd = (
        ["ffmpeg", "-y"]
        + input_args
        + [
            "-filter_complex_script", str(script_path),
            "-map", f"[{prev}]",
            "-an",
            "-c:v", "libx264",
            "-preset", config.FFMPEG_CLIP_PRESET,
            "-crf", str(config.FFMPEG_CLIP_CRF),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(out_path),
        ]
    )
    run(cmd, on_log=on_log)
    return out_path


def _finalize(
    video_path: Path,
    *,
    ass_path: Path,
    style: StylePreset,
    voice_path: Path,
    voice_start: float,
    target_duration: float,
    music_path: Path | None,
    output_path: Path,
    on_log: OnLog | None,
) -> Path:
    """Fase 3: grade + subtítulos + audio (1 input de vídeo corto)."""
    eq_filter = _jittered_eq_filter(style.eq_extra)
    vignette_filter = _vignette_filter(style)
    noise_filter = style.noise_filter_override or config.NOISE_FILTER_BASE
    # Efectos de cine del estilo. Van ANTES de los subtítulos para que el
    # destello no lave el texto ni la rayadura lo cruce por encima.
    extra_fx = [
        f for f in (
            _light_leak_filter(style, target_duration),
            _scratches_filter(style, target_duration),
        ) if f
    ]

    ass_escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    # Cada estilo puede traer su propia tipografía (estilo H usa Montserrat
    # de `assets/fonts`); el resto cae en la global del sistema.
    fontsdir = style.fonts_dir or config.SUB_FONTSDIR
    fontsdir_escaped = fontsdir.replace("\\", "\\\\").replace(":", "\\:")

    # Inputs en orden FIJO: [0] vídeo, [1] voz, [2] música si la hay. Todo
    # input visual extra (máscara del cuadrado, láminas de polvo) se añade
    # detrás con `add_input`, que devuelve su índice. Hardcodear los índices
    # se rompía en cuanto se activaba la música.
    input_args = ["-i", str(video_path)]
    input_args += [
        "-ss", f"{voice_start:.3f}",
        "-t", f"{target_duration:.3f}",
        "-i", str(voice_path),
    ]
    audio_filters = [f"[1:a]volume={config.VOICE_VOLUME}[voice]"]

    if music_path is not None:
        input_args += ["-ss", "0", "-t", f"{target_duration:.3f}", "-i", str(music_path)]
        fade_start = max(0.0, target_duration - config.MUSIC_FADEOUT_DUR)
        audio_filters.append(
            f"[2:a]volume={config.MUSIC_VOLUME},"
            f"afade=t=out:st={fade_start:.3f}:d={config.MUSIC_FADEOUT_DUR}[music]"
        )
        audio_filters.append(
            "[voice][music]amix=inputs=2:duration=first:normalize=0,"
            "alimiter=limit=0.95[aout]"
        )
    else:
        audio_filters.append("[voice]alimiter=limit=0.95[aout]")

    siguiente_idx = 3 if music_path is not None else 2

    def add_input(args: list[str]) -> int:
        nonlocal siguiente_idx
        input_args.extend(args)
        siguiente_idx += 1
        return siguiente_idx - 1

    filters: list[str] = []
    post_label = "vsubs" if style.post_subtitle_filters else "vfinal"
    # Grading propio del estilo (colorbalance, colorchannelmixer…) ANTES de
    # quemar los subtítulos, para no teñir el texto.
    pre = "".join(f"{f}," for f in [*style.pre_subtitle_filters, *extra_fx])

    def añadir_polvo(entrada: str) -> str:
        """Encadena las láminas de polvo sobre `entrada` y devuelve la salida."""
        capas = max(0, style.film_specks)
        if capas <= 0:
            return entrada
        etiqueta = entrada
        for i in range(capas):
            plate = _dust_plate(ass_path.parent, i, dots=130)
            idx = add_input(["-loop", "1", "-t", f"{target_duration:.3f}", "-i", str(plate)])
            # La lámina es 1.5× el encuadre, así que puede empezar descolocada
            # y derivar sin dejar ver el borde. Cada capa va a su ritmo: dos
            # capas a la misma velocidad se leerían como una textura pegada.
            x0 = random.randint(-int(config.TARGET_W * 0.45), -10)
            y0 = random.randint(-int(config.TARGET_H * 0.45), -10)
            vx = random.uniform(-11, 11)
            vy = random.uniform(-11, 11)
            salida = f"dust{i}"
            filters.append(
                f"[{etiqueta}][{idx}:v]overlay="
                f"x='{x0}+({vx:.2f})*t':y='{y0}+({vy:.2f})*t'"
                f":eval=frame:format=auto[{salida}]"
            )
            etiqueta = salida
        return etiqueta

    if style.square_frame:
        # El vídeo se mete en un CUADRADO de esquinas redondeadas centrado
        # sobre negro. Las esquinas se redondean con `alphamerge` + una
        # máscara PNG: ffmpeg no sabe dibujar rectángulos redondeados.
        # El texto se quema DESPUÉS de componer, para que quede sobre el
        # recuadro y no se recorte con él.
        side, radius = config.SQUARE_SIDE, config.SQUARE_RADIUS
        mask_path = _rounded_square_mask(ass_path.parent, side, radius)
        mask_idx = add_input(["-i", str(mask_path)])
        filters.append(
            f"[0:v]{eq_filter},{vignette_filter},{noise_filter},{pre}"
            f"scale={side}:{side}:force_original_aspect_ratio=increase,"
            f"crop={side}:{side}:(in_w-{side})/2:"
            f"(in_h-{side})*{config.SQUARE_CROP_Y_FRAC}[sq]"
        )
        filters.append(f"[{mask_idx}:v]format=gray[mk]")
        filters.append("[sq][mk]alphamerge[sqa]")
        filters.append(
            f"color=black:size={config.TARGET_W}x{config.TARGET_H}"
            f":rate={config.TARGET_FPS}:duration={target_duration:.3f}[bg]"
        )
        filters.append("[bg][sqa]overlay=(W-w)/2:(H-h)/2:format=auto[framed]")
        con_polvo = añadir_polvo("framed")
        filters.append(
            f"[{con_polvo}]subtitles=filename='{ass_escaped}':"
            f"fontsdir='{fontsdir_escaped}',format=yuv420p[{post_label}]"
        )
    else:
        filters.append(
            f"[0:v]{eq_filter},{vignette_filter},{noise_filter},{pre}null[graded]"
        )
        con_polvo = añadir_polvo("graded")
        filters.append(
            f"[{con_polvo}]subtitles=filename='{ass_escaped}':"
            f"fontsdir='{fontsdir_escaped}'[{post_label}]"
        )
    if style.post_subtitle_filters:
        filters.append(f"[vsubs]{','.join(style.post_subtitle_filters)}[vfinal]")

    filters.extend(audio_filters)

    # OJO: junto al .ass (tmp_dir), NO junto a output_path — el dir de salida
    # se publica entero en Drive y este scratch acababa subido con los MP4.
    script_path = ass_path.with_suffix(".final.txt")
    script_path.write_text(";\n".join(filters), encoding="utf-8")

    cmd = (
        ["ffmpeg", "-y"]
        + input_args
        + [
            "-filter_complex_script", str(script_path),
            "-map", "[vfinal]", "-map", "[aout]",
            "-t", f"{target_duration:.3f}",
            "-r", str(config.TARGET_FPS),
            "-c:v", "libx264",
            "-preset", config.FFMPEG_PRESET,
            "-crf", str(config.FFMPEG_CRF),
            # Techo de bitrate: ver config.FFMPEG_MAXRATE.
            "-maxrate", config.FFMPEG_MAXRATE,
            "-bufsize", config.FFMPEG_BUFSIZE,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", config.FFMPEG_AUDIO_BITRATE,
            "-movflags", "+faststart",
            str(output_path),
        ]
    )
    try:
        run(cmd, on_log=on_log)
    finally:
        script_path.unlink(missing_ok=True)
    return output_path


def render_video(
    *,
    ponente: str,
    audio_path: Path,
    words: list[dict],
    hook_video: Path,
    hook_candidate: dict,
    paisajes_video: Path,
    paisaje_candidates: list[dict],
    style: StylePreset,
    include_music: bool,
    music_path: Path | None,
    output_path: Path,
    tmp_dir: Path,
    on_log: OnLog | None = None,
    audio_start: float = 0.0,
    target_duration: float | None = None,
) -> Path:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    full_audio_dur = ffprobe_duration(audio_path)
    if target_duration is None:
        _start, target_duration = config.audio_window_for_round(full_audio_dur, 1)
        audio_start = _start
    target_duration = float(target_duration)
    audio_start = float(audio_start)

    snapped = snap_to_first_word(words, audio_start, target_duration, audio_path)
    if snapped > audio_start:
        # La ventana se acorta en lo adelantado: el habla es la misma, solo
        # se va el silencio. Si no se restara, el final se saldría del audio
        # y el vídeo acabaría con un tramo mudo.
        target_duration = max(0.0, target_duration - (snapped - audio_start))
        if on_log:
            on_log(
                f"[renderer] arranque de audio {audio_start:.2f}s → {snapped:.2f}s "
                f"(recortado {snapped - audio_start:.2f}s de silencio inicial)"
            )
        audio_start = snapped

    if on_log:
        on_log(
            f"[renderer] ventana audio {audio_start:.1f}s+{target_duration:.1f}s "
            f"(fuente {full_audio_dur:.1f}s)"
        )

    window_words = slice_words(words, audio_start, target_duration)
    lines = group_into_phrases(window_words)
    if on_log:
        on_log(f"[renderer] {len(lines)} líneas de subtítulo · estilo {style.label}")

    ass_path = tmp_dir / f"{output_path.stem}_subs.ass"
    ass_path.write_text(style.build_ass(lines, style), encoding="utf-8")

    fill_duration = max(0.0, target_duration - config.HOOK_DUR)
    n_needed = len(paisaje_candidates)

    # Dos orígenes posibles: biblioteca de clips (cada candidato trae su
    # propio fichero y su ventana) o el vídeo largo de siempre.
    from_library = bool(paisaje_candidates and paisaje_candidates[0].get("path"))
    if from_library:
        # Cada clip solo tiene el material de SU plano: repartir sin pasarse
        # o ffmpeg congelaría el último fotograma para rellenar.
        # Se reserva `CLIP_TRANSITION_PAD_S` por clip para el solape del
        # fundido; lo que queda es lo que se puede usar de verdad.
        pad = config.CLIP_TRANSITION_PAD_S
        caps = [max(0.0, float(c.get("dur") or 0.0) - pad) for c in paisaje_candidates]
        if sum(caps) + 1e-3 < fill_duration:
            raise RuntimeError(
                f"Los {n_needed} clips asignados dan {sum(caps):.1f}s útiles "
                f"(descontado el margen de transición) pero hacen falta "
                f"{fill_duration:.1f}s de paisaje."
            )
        durations = distribute_with_caps(fill_duration, caps)
        # El desplazamiento se sortea AHORA, sabiendo ya cuánto se usa de cada
        # clip: así el fragmento cabe siempre —con su margen— y el mismo clip
        # nunca sale con el mismo encuadre temporal en dos vídeos distintos.
        paisaje_segments = []
        for c, d in zip(paisaje_candidates, durations):
            total = float(c.get("dur") or 0.0)
            half = pad / 2
            start = half + random.uniform(0.0, max(0.0, total - d - pad))
            paisaje_segments.append((Path(c["path"]), round(start, 3), d))
    else:
        durations = _jittered_paisaje_durations(fill_duration, n_needed)
        paisaje_segments = [
            (paisajes_video, c["start"], d)
            for c, d in zip(paisaje_candidates, durations)
        ]

    # Gancho ya recortado a 3s si existe: el vídeo fuente pesa 300 MB-1,1 GB
    # por ponente y no cabe tenerlos todos en el disco del VPS. El encuadre
    # (`cx_frac`) y el zoom los sigue poniendo el renderer, así que el clip
    # se guarda sin recortar de ancho y el resultado es idéntico.
    hook_src, hook_start = hook_video, hook_candidate["start"]
    clip_gancho = hook_candidate.get("clip")
    if clip_gancho:
        candidato = config.ponente_ganchos_dir(ponente) / clip_gancho
        if candidato.is_file():
            hook_src, hook_start = candidato, 0.0
        elif on_log:
            on_log(f"[renderer] ⚠️ falta el gancho pre-cortado {candidato.name}, uso el vídeo fuente")

    transitions = build_transitions(1 + len(paisaje_segments), style)
    specs = build_clip_specs(
        hook_src, hook_start, hook_candidate["cx_frac"],
        paisaje_segments, transitions, target_duration,
    )

    work = tmp_dir / f"{output_path.stem}_clips"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    clip_paths: list[Path] = []
    for i, spec in enumerate(specs):
        cp = work / f"c{i:02d}.mp4"
        if on_log:
            on_log(f"[renderer] extract clip {i+1}/{len(specs)} ({spec.extract_dur:.1f}s)")
        _extract_clip(spec, cp, on_log, ken_burns=style.ken_burns)
        clip_paths.append(cp)

    xfade_path = work / "xfade.mp4"
    if on_log:
        on_log(f"[renderer] xfade {len(clip_paths)} clips…")
    _xfade_clips(clip_paths, specs, transitions, xfade_path, on_log)

    use_music = include_music and music_path is not None
    if on_log:
        on_log("[renderer] finalize (grade + subs + audio)…")
    _finalize(
        xfade_path,
        ass_path=ass_path,
        style=style,
        voice_path=audio_path,
        voice_start=audio_start,
        target_duration=target_duration,
        music_path=music_path if use_music else None,
        output_path=output_path,
        on_log=on_log,
    )

    # Limpia intermedios del vídeo (libera disco; ASS se queda por si debug).
    shutil.rmtree(work, ignore_errors=True)
    return output_path
