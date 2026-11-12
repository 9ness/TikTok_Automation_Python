"""Pegar los clips EN CRUDO que manda un agente, en su orden (12/11/2026).

Los agentes mandan al editor los clips tal cual salen (sin subtítulos, texto,
flecha ni nombre); aquí se igualan a 1080x1920 · 30 fps · AAC 48 kHz estéreo y
se pegan. Con `voz` (la locución aparte, p. ej. Fish), su audio sustituye al de
los clips: el vídeo dura lo que los clips y la voz se rellena con silencio.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

MAX_CLIPS = 10
# Holgura: una voz algo más larga que los clips se corta sin que se note.
_HOLGURA_VOZ = 0.3


class ErrorClips(ValueError):
    """Los clips o la voz no valen (se devuelve como 422)."""


def _probe(ruta: Path) -> tuple[float, set[str]]:
    """(duración, tipos de pista: video/audio)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
         "-of", "json", str(ruta)],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise ErrorClips(f"No puedo leer {ruta.name}: {out.stderr.strip()[-200:]}")
    d = json.loads(out.stdout or "{}")
    tipos = {s.get("codec_type") for s in d.get("streams", [])}
    try:
        dur = float((d.get("format") or {}).get("duration") or 0)
    except ValueError:
        dur = 0.0
    if dur <= 0:
        raise ErrorClips(f"{ruta.name} no tiene duración (¿está entero?).")
    return dur, tipos


def unir(rutas: list[Path], destino: Path, voz: Path | None = None) -> Path:
    """Pega `rutas` en orden en `destino` (MP4 1080x1920). Lanza ErrorClips si algo no vale."""
    if not rutas:
        raise ErrorClips("No hay clips.")
    if len(rutas) > MAX_CLIPS:
        raise ErrorClips(f"Como mucho {MAX_CLIPS} clips por vídeo.")
    info = []
    for r in rutas:
        dur, tipos = _probe(r)
        if "video" not in tipos:
            raise ErrorClips(f"{r.name} no es un vídeo.")
        info.append((dur, "audio" in tipos))
    total = sum(d for d, _ in info)
    entradas: list[str] = []
    partes: list[str] = []
    for i, (r, (dur, audio)) in enumerate(zip(rutas, info)):
        entradas += ["-i", str(r)]
        partes.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"setsar=1,fps=30,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v{i}]")
        if voz is not None:
            continue  # el audio de los clips no se usa
        if audio:
            partes.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                          f"asetpts=PTS-STARTPTS,apad,atrim=0:{dur:.3f}[a{i}]")
        else:
            partes.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{dur:.3f}[a{i}]")
    n = len(rutas)
    if voz is None:
        pares = "".join(f"[v{i}][a{i}]" for i in range(n))
        partes.append(f"{pares}concat=n={n}:v=1:a=1[v][ac]")
        salida_audio = "[ac]"
    else:
        partes.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]")
        dur_voz, tipos_voz = _probe(voz)
        if "audio" not in tipos_voz:
            raise ErrorClips(f"{voz.name} no tiene audio.")
        if dur_voz > total + _HOLGURA_VOZ:
            raise ErrorClips(f"La voz dura {dur_voz:.1f} s y los clips {total:.1f} s: "
                             "manda más clips o más largos.")
        entradas += ["-i", str(voz)]
        partes.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                      f"apad,atrim=0:{total:.3f}[voz]")
        salida_audio = "[voz]"
    destino.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", *entradas,
         "-filter_complex", ";".join(partes), "-map", "[v]", "-map", salida_audio,
         "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
         "-t", f"{total:.3f}", str(destino)],
        capture_output=True, text=True, timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg no pudo pegar los clips: {p.stderr.strip()[-400:]}")
    return destino

