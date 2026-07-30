#!/usr/bin/env python3
"""Genera una miniatura de muestra por cada estilo de Viralización.

Sin esto el operador elige estilos a ciegas: la lista solo dice "B · Reveal"
y no hay forma de saber qué hace hasta gastar un render de 25 vídeos.

Cada miniatura son DOS fotogramas del mismo render de muestra puestos uno al
lado del otro: uno del GANCHO (cara hablando) y otro de un PAISAJE — que es
donde se aprecian las diferencias reales entre estilos (grade, viñeta,
barras de cine, marco cuadrado).

Se guardan en `frontend/public/viralizacion/previews/<key>.jpg` a propósito:
Next.js los sirve como estáticos, así que no hace falta ni endpoint ni
permisos de escritura en el volumen de assets (que en el container es de
solo lectura).

Uso:
    python scripts/viralizacion_previews.py            # todos los estilos
    python scripts/viralizacion_previews.py reveal     # solo algunos
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.viralizacion import config  # noqa: E402
from src.viralizacion.pipeline import styles, transcriber  # noqa: E402
from src.viralizacion.pipeline.ffmpeg_utils import ffprobe_duration  # noqa: E402
from src.viralizacion.pipeline.renderer import (  # noqa: E402
    build_paisaje_segments,
    render_video,
)
from src.viralizacion.services import allocator, clip_library  # noqa: E402

# Ponente de las muestras. Se puede cambiar con VIRALIZACION_PREVIEW_PONENTE
# para revisar el encuadre de otro (el recorte cuadrado depende de dónde
# caiga su cara).
PONENTE = os.environ.get("VIRALIZACION_PREVIEW_PONENTE", "pablo")
OUT_DIR = REPO / "frontend" / "public" / "viralizacion" / "previews"
WORK = Path("/var/tmp/viralizacion_previews")

# Muestra corta: con 14s ya entra el gancho, la transición y dos paisajes,
# que es todo lo que hay que enseñar. Un render completo por estilo serían
# ~10 min para nada.
SAMPLE_DUR = 14.0
# Instantes de los que se saca cada fotograma: dentro del gancho y ya en
# pleno b-roll (después de que entren las barras de cine).
T_GANCHO = 2.0
# 8.4 y no 9.0: en 9.0 el bloque de texto solía estar en su PRIMERA palabra y
# los estilos que apilan (D, E, G) parecían no apilar nada.
T_PAISAJE = 8.4


def _muestra(key: str, hook: dict, audio: Path, words: list[dict]) -> Path:
    preset = styles.STYLE_PRESETS[key]
    fill = max(0.0, SAMPLE_DUR - config.HOOK_DUR)
    n = build_paisaje_segments(fill)

    # Los mismos clips para todos los estilos: si cada uno saliera con
    # paisajes distintos, la comparación no valdría de nada.
    rnd = random.Random(7)
    clips = sorted(clip_library.all_clips(), key=lambda c: c["index"])
    rnd.shuffle(clips)
    sel: list[dict] = []
    vistos: set = set()
    for c in clips:
        usable = sum(x["dur"] - config.CLIP_TRANSITION_PAD_S for x in sel)
        if len(sel) >= n and usable >= fill:
            break
        loc = c.get("location", c["index"])
        if loc in vistos:
            continue
        vistos.add(loc)
        sel.append(c)
    paisajes = [
        {"index": c["index"], "path": str(clip_library.clip_path(c)), "dur": float(c["dur"])}
        for c in sel
    ]

    mp4 = WORK / f"{key}.mp4"
    render_video(
        ponente=PONENTE,
        audio_path=audio,
        words=words,
        hook_video=config.ponente_gancho_video(PONENTE),
        hook_candidate=hook,
        paisajes_video=config.paisajes_video(),
        paisaje_candidates=paisajes,
        style=preset,
        include_music=False,
        music_path=config.musica_file(),
        output_path=mp4,
        tmp_dir=WORK / "tmp",
        on_log=lambda _m: None,
        audio_start=0.0,
        target_duration=SAMPLE_DUR,
    )
    return mp4


def _miniatura(mp4: Path, destino: Path) -> None:
    frames = []
    for i, t in enumerate((T_GANCHO, T_PAISAJE)):
        f = WORK / f"{destino.stem}_{i}.jpg"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", str(mp4),
             "-frames:v", "1", "-vf", "scale=360:-1", "-q:v", "4", str(f), "-y"],
            check=True,
        )
        frames.append(f)
    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(frames[0]), "-i", str(frames[1]),
         "-filter_complex", "[0][1]hstack=inputs=2", "-q:v", "4", str(destino), "-y"],
        check=True,
    )
    for f in frames:
        f.unlink(missing_ok=True)


def main() -> None:
    pedidos = sys.argv[1:] or list(styles.STYLE_ORDER)
    WORK.mkdir(parents=True, exist_ok=True)

    # Vía `scan_hook_candidates` y NO leyendo el JSON a pelo: es quien
    # resuelve la ruta del gancho pre-cortado (`clip`). Leyendo el fichero
    # salía sin ella y el render moría con `-i None`, porque los vídeos de
    # gancho originales ya no están en disco (se subieron a Drive).
    # Tampoco se usa `allocator.allocate_hook`: eso marcaría el gancho como
    # gastado, y una muestra no debe consumir del banco.
    hook = allocator.scan_hook_candidates(PONENTE)[0]
    audio = config.ponente_audio_files(PONENTE)[0]
    words = transcriber.transcribe_words(
        PONENTE, audio, tmp_dir=WORK / "tmp", on_log=lambda _m: None
    )
    print(f"audio {audio.name} · {ffprobe_duration(audio):.1f}s · {len(words)} palabras")

    for key in pedidos:
        if key not in styles.STYLE_PRESETS:
            print(f"  ✗ estilo desconocido: {key}")
            continue
        print(f"  · {key} …", flush=True)
        mp4 = _muestra(key, hook, audio, words)
        _miniatura(mp4, OUT_DIR / f"{key}.jpg")
        print(f"  ✓ {OUT_DIR / f'{key}.jpg'}")


if __name__ == "__main__":
    main()
