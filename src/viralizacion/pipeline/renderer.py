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
from src.viralizacion.pipeline.ffmpeg_utils import ffprobe_duration, run
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
    return max(1, round(fill_duration / config.PAISAJE_CLIP_TARGET_S))


def build_transitions(n_clips: int) -> list[tuple[str, float]]:
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


def _clip_vf(spec: ClipSpec) -> str:
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


def _extract_clip(spec: ClipSpec, out_path: Path, on_log: OnLog | None) -> Path:
    """Fase 1: un solo input → clip corto 1080x1920. RAM baja, seek rápido."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{spec.extract_start:.3f}",
        "-t", f"{spec.extract_dur:.3f}",
        "-i", str(spec.src),
        "-vf", _clip_vf(spec),
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


def _xfade_clips(
    clip_paths: list[Path],
    specs: list[ClipSpec],
    transitions: list[tuple[str, float]],
    out_path: Path,
    on_log: OnLog | None,
) -> Path:
    """Fase 2: xfade sobre clips YA recortados (pocos MB c/u, sin reabrir el 2.5GB)."""
    if len(clip_paths) == 1:
        shutil.copy2(clip_paths[0], out_path)
        return out_path

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
    vignette_filter = f"vignette=angle={style.vignette_angle}:mode=forward"
    noise_filter = style.noise_filter_override or config.NOISE_FILTER_BASE

    ass_escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    fontsdir_escaped = config.SUB_FONTSDIR.replace("\\", "\\\\").replace(":", "\\:")

    filters: list[str] = []
    post_label = "vsubs" if style.post_subtitle_filters else "vfinal"
    filters.append(
        f"[0:v]{eq_filter},{vignette_filter},{noise_filter},"
        f"subtitles=filename='{ass_escaped}':fontsdir='{fontsdir_escaped}'[{post_label}]"
    )
    if style.post_subtitle_filters:
        filters.append(f"[vsubs]{','.join(style.post_subtitle_filters)}[vfinal]")

    input_args = ["-i", str(video_path)]
    input_args += [
        "-ss", f"{voice_start:.3f}",
        "-t", f"{target_duration:.3f}",
        "-i", str(voice_path),
    ]
    filters.append(f"[1:a]volume={config.VOICE_VOLUME}[voice]")

    if music_path is not None:
        input_args += ["-ss", "0", "-t", f"{target_duration:.3f}", "-i", str(music_path)]
        fade_start = max(0.0, target_duration - config.MUSIC_FADEOUT_DUR)
        filters.append(
            f"[2:a]volume={config.MUSIC_VOLUME},"
            f"afade=t=out:st={fade_start:.3f}:d={config.MUSIC_FADEOUT_DUR}[music]"
        )
        filters.append(
            "[voice][music]amix=inputs=2:duration=first:normalize=0,"
            "alimiter=limit=0.95[aout]"
        )
    else:
        filters.append("[voice]alimiter=limit=0.95[aout]")

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

    fill_duration = target_duration - config.HOOK_DUR
    n_needed = len(paisaje_candidates)
    durations = _jittered_paisaje_durations(fill_duration, n_needed)
    paisaje_segments = [(c["start"], d) for c, d in zip(paisaje_candidates, durations)]

    transitions = build_transitions(1 + len(paisaje_segments))
    specs = build_clip_specs(
        hook_video, hook_candidate["start"], hook_candidate["cx_frac"],
        paisajes_video, paisaje_segments, transitions, target_duration,
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
        _extract_clip(spec, cp, on_log)
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
