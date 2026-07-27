"""Construcción del filter_complex y render final con ffmpeg: gancho (3s,
cara en primer plano) + tramos de paisaje, xfade, filtro "película"
(+ extras por estilo), subtítulos quemados (estilo A/B/C) y mezcla de
audio (voz [+ música opcional]).

Adaptado de `~/viralizacion_work/build_test_v2.py` (prototipo validado por
el operador) con estas diferencias:
- Ponente / candidatos de gancho y paisaje son dinámicos (vienen del
  allocator, nunca se repiten — ver `services/allocator.py`).
- 3 estilos de subtítulo/filtro rotables (`pipeline/styles.py`).
- Jitter aleatorio por clip/vídeo (zoom, duración de paisaje, duración de
  transición, eq) para evitar una "huella" de plantilla reconocible — ver
  `config.py` sección "Anti-fingerprint"."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.viralizacion import config
from src.viralizacion.pipeline.ffmpeg_utils import ffprobe_duration, run
from src.viralizacion.pipeline.styles import StylePreset
from src.viralizacion.pipeline.transcriber import group_into_phrases

OnLog = Callable[[str], None]


@dataclass
class ClipSpec:
    src: Path
    start: float          # inicio nominal en la fuente
    nominal_dur: float    # duración "lógica" en el timeline final
    extract_start: float  # inicio real a extraer (compensado para el xfade)
    extract_dur: float    # duración real a extraer
    zoom: float            # zoom extra sobre el mínimo necesario para cubrir 1080x1920
    cx_frac: float | None = None  # None = crop centrado


def _jittered_paisaje_durations(fill_duration: float, n: int) -> list[float]:
    """`n` duraciones cuya SUMA es exactamente `fill_duration`, cada una
    variando dentro de `PAISAJE_CLIP_DUR_JITTER_RANGE` (media ~4.5s) para
    que no todos los tramos midan lo mismo (huella de plantilla)."""
    if n <= 1:
        return [fill_duration]
    lo, hi = config.PAISAJE_CLIP_DUR_JITTER_RANGE
    weights = [random.uniform(lo, hi) for _ in range(n)]
    scale = fill_duration / sum(weights)
    durations = [w * scale for w in weights]
    # Clamp + redistribuye el exceso/déficit un par de pasadas para converger
    # dentro del rango sin perder la suma exacta.
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
    # Corrección final: absorbe cualquier resto de precisión flotante en el
    # último elemento para que la suma cuadre EXACTA (milisegundo) con
    # `fill_duration` — el vídeo tiene que durar lo mismo que el audio.
    diff = fill_duration - sum(durations)
    durations[-1] += diff
    return durations


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
    """Nº de tramos de paisaje necesarios para cubrir `fill_duration`
    (~PAISAJE_CLIP_TARGET_S cada uno, en MEDIA — la duración real de cada
    uno se jitteriza luego en `_jittered_paisaje_durations`)."""
    return max(1, round(fill_duration / config.PAISAJE_CLIP_TARGET_S))


def build_transitions(n_clips: int) -> list[tuple[str, float]]:
    """Una entrada por transición (len == n_clips - 1): la 1ª es el hblur
    gancho→paisaje (fija, validada), el resto fadeblack paisaje→paisaje
    con duración jitterizada por transición (anti-fingerprint)."""
    if n_clips < 2:
        return []
    lo, hi = config.TRANSITION_LANDSCAPE_JITTER_RANGE
    landscape = [("fadeblack", round(random.uniform(lo, hi), 3)) for _ in range(n_clips - 2)]
    return [config.TRANSITION_HOOK] + landscape


def build_clip_specs(
    hook_video: Path,
    hook_start: float,
    hook_cx_frac: float,
    paisajes_video: Path,
    paisaje_segments: list[tuple[float, float]],
    transitions: list[tuple[str, float]],
    target_duration: float,
) -> list[ClipSpec]:
    nominal = [(hook_video, hook_start, config.HOOK_DUR, hook_cx_frac,
                random.uniform(*config.HOOK_ZOOM_JITTER_RANGE))]
    nominal += [
        (paisajes_video, s, d, None, random.uniform(*config.PAISAJE_ZOOM_JITTER_RANGE))
        for s, d in paisaje_segments
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


def build_filter_complex(
    specs: list[ClipSpec],
    transitions: list[tuple[str, float]],
    ass_path: Path,
    target_duration: float,
    style: StylePreset,
    voice_path: Path,
    music_path: Path | None,
) -> tuple[str, list[str]]:
    input_args: list[str] = []
    per_clip_labels = []

    for s in specs:
        input_args += ["-ss", f"{s.extract_start:.3f}", "-t", f"{s.extract_dur:.3f}", "-i", str(s.src)]

    filters = []
    for i, s in enumerate(specs):
        scale_w = max(config.TARGET_W, round(config.TARGET_W * s.zoom))
        scale_h = max(config.TARGET_H, round(config.TARGET_H * s.zoom))
        if s.cx_frac is not None:
            x_expr = f"min(max((in_w-{config.TARGET_W})*{s.cx_frac},0),in_w-{config.TARGET_W})"
        else:
            x_expr = f"(in_w-{config.TARGET_W})/2"
        y_expr = f"(in_h-{config.TARGET_H})/2"
        label = f"v{i}"
        filters.append(
            f"[{i}:v]scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
            f"crop={config.TARGET_W}:{config.TARGET_H}:x='{x_expr}':y='{y_expr}',"
            f"hflip,fps={config.TARGET_FPS},format=yuv420p,setsar=1[{label}]"
        )
        per_clip_labels.append(label)

    offsets = xfade_offsets(specs, transitions)
    prev_label = per_clip_labels[0]
    for i in range(1, len(specs)):
        out_label = f"x{i}"
        ttype, tdur = transitions[i - 1]
        filters.append(
            f"[{prev_label}][{per_clip_labels[i]}]xfade=transition={ttype}:"
            f"duration={tdur}:offset={offsets[i-1]:.3f}[{out_label}]"
        )
        prev_label = out_label

    eq_filter = _jittered_eq_filter(style.eq_extra)
    vignette_filter = f"vignette=angle={style.vignette_angle}:mode=forward"
    noise_filter = style.noise_filter_override or config.NOISE_FILTER_BASE

    ass_escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    fontsdir_escaped = config.SUB_FONTSDIR.replace("\\", "\\\\").replace(":", "\\:")

    post_label = "vsubs" if style.post_subtitle_filters else "vfinal"
    filters.append(
        f"[{prev_label}]{eq_filter},{vignette_filter},{noise_filter},"
        f"subtitles=filename='{ass_escaped}':fontsdir='{fontsdir_escaped}'[{post_label}]"
    )
    if style.post_subtitle_filters:
        filters.append(
            f"[vsubs]{','.join(style.post_subtitle_filters)}[vfinal]"
        )

    n = len(specs)
    voice_idx = n
    input_args += ["-t", f"{target_duration:.3f}", "-i", str(voice_path)]
    filters.append(f"[{voice_idx}:a]volume={config.VOICE_VOLUME}[voice]")

    if music_path is not None:
        music_idx = n + 1
        input_args += ["-ss", "0", "-t", f"{target_duration:.3f}", "-i", str(music_path)]
        fade_start = max(0.0, target_duration - config.MUSIC_FADEOUT_DUR)
        filters.append(
            f"[{music_idx}:a]volume={config.MUSIC_VOLUME},"
            f"afade=t=out:st={fade_start:.3f}:d={config.MUSIC_FADEOUT_DUR}[music]"
        )
        filters.append(
            "[voice][music]amix=inputs=2:duration=first:normalize=0,"
            "alimiter=limit=0.95[aout]"
        )
    else:
        filters.append("[voice]alimiter=limit=0.95[aout]")

    return ";\n".join(filters), input_args


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
) -> Path:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    target_duration = ffprobe_duration(audio_path)
    if on_log:
        on_log(f"[renderer] audio completo: {target_duration:.2f}s (se usa entero, sin recortar)")

    lines = group_into_phrases(words)
    if on_log:
        on_log(f"[renderer] {len(lines)} líneas de subtítulo · estilo {style.label}")

    ass_path = tmp_dir / f"{output_path.stem}_subs.ass"
    ass_path.write_text(style.build_ass(lines, style), encoding="utf-8")

    fill_duration = target_duration - config.HOOK_DUR
    durations = _jittered_paisaje_durations(fill_duration, len(paisaje_candidates))
    paisaje_segments = [(c["start"], d) for c, d in zip(paisaje_candidates, durations)]

    transitions = build_transitions(1 + len(paisaje_segments))
    specs = build_clip_specs(
        hook_video, hook_candidate["start"], hook_candidate["cx_frac"],
        paisajes_video, paisaje_segments, transitions, target_duration,
    )

    use_music = include_music and music_path is not None
    filter_script, input_args = build_filter_complex(
        specs, transitions, ass_path, target_duration, style,
        voice_path=audio_path, music_path=music_path if use_music else None,
    )

    filter_script_path = tmp_dir / f"{output_path.stem}_filter_complex.txt"
    filter_script_path.write_text(filter_script, encoding="utf-8")

    cmd = ["ffmpeg", "-y"] + input_args + [
        "-filter_complex_script", str(filter_script_path),
        "-map", "[vfinal]", "-map", "[aout]",
        "-t", f"{target_duration:.3f}",
        "-r", str(config.TARGET_FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    run(cmd, on_log=on_log)
    return output_path
