#!/usr/bin/env python3
"""Construye la biblioteca de clips de paisaje de un país desde su vídeo fuente.

Cada clip es UN SOLO plano del original (cortado por cambio de escena), ya en
1080x1920, para que el render no reabra el fuente de varios GB ni un tramo
cambie de sitio a mitad.

Se descarta lo que no sirve, que es la mitad del trabajo:
- Planos con TEXTO dentro del encuadre final. Ojo: el recorte 9:16 centrado ya
  deja fuera los rótulos de las esquinas (la marca del canal arriba a la
  derecha, el nombre del sitio abajo a la izquierda), así que el OCR se pasa
  SOBRE EL RECORTE, no sobre el fotograma entero — si no, se descartaría casi
  todo por texto que el espectador nunca va a ver. Lo que sí cae son las
  cartelas de título ("THE WAVE", "SALARES DE BONNEVILLE"), que ocupan el centro.
  El detector está en `services/rotulos.py` y muestrea VARIOS fotogramas: las
  cartelas entran animadas y con uno solo se colaban (ver ese módulo).
- Planos demasiado oscuros o planos (un fundido a negro, un cielo liso).
- Planos más cortos que `MIN_DUR`: no dan ni para un tramo de b-roll.

Uso:
    python scripts/viralizacion_trocear_paisajes.py us [--max 400]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.viralizacion import config  # noqa: E402
from src.viralizacion.services import clip_library, rotulos  # noqa: E402

# Un plano más corto no da ni para un tramo; más largo se corta al usarlo.
MIN_DUR = 3.0
MAX_DUR = 10.0

# Sensibilidad del detector de cambio de plano. 0.4 es alto a propósito: con
# valores bajos, un movimiento de cámara rápido cuenta como corte y salen
# trozos del mismo sitio partidos en dos.
UMBRAL_ESCENA = 0.4

# Por debajo de esto el plano es un fundido o una noche cerrada.
LUMA_MIN = 28.0


def detectar_cortes(video: Path) -> list[float]:
    """Segundos donde cambia el plano."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video),
         "-filter:v", f"select='gt(scene,{UMBRAL_ESCENA})',showinfo",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    tiempos = [
        float(m.group(1))
        for m in re.finditer(r"pts_time:([0-9.]+)", proc.stderr)
    ]
    return sorted(set(tiempos))


def _luma_media(path: Path) -> float:
    """Brillo medio del clip (0-255). Sirve para tirar fundidos y noches."""
    # `-v info` NO es un descuido: `metadata=print` escribe por stderr con
    # nivel info, y con `-v error` no sale NADA. Con eso la media daba 0 y
    # TODOS los clips se descartaban por oscuros — 38 de cada 39.
    # Un fotograma de cada 15 y a 240px: medir el brillo NO necesita ver los
    # 30 fps a resolución completa, y así pasa de 4,7s a menos de 1 por clip.
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "info", "-i", str(path),
         "-vf", ("select='not(mod(n\\,15))',scale=240:-2,"
                 "signalstats,metadata=print:key=lavfi.signalstats.YAVG"),
         "-vsync", "0", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    vals = [float(m.group(1)) for m in re.finditer(r"YAVG=([0-9.]+)", proc.stderr)]
    return sum(vals) / len(vals) if vals else 0.0


def trocear(pais: str, tope: int) -> int:
    video = config.paisajes_video(pais)
    if video is None:
        raise SystemExit(f"No hay vídeo de paisajes en {config.paisajes_folder(pais)}")

    destino = clip_library.clips_folder(pais)
    destino.mkdir(parents=True, exist_ok=True)

    # La detección de planos sobre 2,5 h de vídeo tarda ~20 min: se cachea
    # para poder ajustar los filtros sin repetirla.
    cache = Path("/app/temp_work") / f"cortes_{pais}.json"
    if cache.is_file():
        cortes = json.loads(cache.read_text())
        print(f"  {len(cortes)} cortes (de caché)", flush=True)
    else:
        print(f"Detectando cambios de plano en {video.name}… (tarda)", flush=True)
        cortes = detectar_cortes(video)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(cortes))
        print(f"  {len(cortes)} cortes", flush=True)

    import easyocr

    lector = easyocr.Reader(["es", "en"], gpu=False, verbose=False)

    w, h = config.TARGET_W, config.TARGET_H
    clips: list[dict] = []
    descartados = {"corto": 0, "oscuro": 0, "texto": 0}
    idx = 0

    for i, inicio in enumerate(cortes[:-1]):
        if len(clips) >= tope:
            break
        dur = min(cortes[i + 1] - inicio, MAX_DUR)
        if dur < MIN_DUR:
            descartados["corto"] += 1
            continue

        idx += 1
        out = destino / f"clip_{idx:04d}.mp4"
        # Recorte 9:16 centrado + escalado al formato final, en un solo paso.
        subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{inicio:.3f}", "-t", f"{dur:.3f}",
             "-i", str(video),
             "-vf", (f"crop=ih*{w}/{h}:ih,scale={w}:{h},fps={config.TARGET_FPS},setsar=1"),
             # `ultrafast`: el cuello de botella es codificar 1080x1920, y estos
             # clips se vuelven a codificar en el render final, así que aquí no
             # compensa apurar el bitrate. Con `veryfast` eran ~20s por clip
             # (dos horas la biblioteca entera); así baja a la mitad.
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
             "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(out), "-y"],
            check=True, capture_output=True,
        )

        if _luma_media(out) < LUMA_MIN:
            out.unlink(missing_ok=True)
            descartados["oscuro"] += 1
            continue
        if rotulos.tiene_texto(out, lector):
            out.unlink(missing_ok=True)
            descartados["texto"] += 1
            continue

        clips.append({
            "index": len(clips) + 1,
            "file": out.name,
            "dur": round(dur, 3),
            # Un plano = un lugar. El allocator lo usa para no mezclar el mismo
            # sitio dos veces en el mismo vídeo.
            "location": len(clips) + 1,
            "src_start": round(inicio, 3),
        })
        if len(clips) % 25 == 0:
            print(f"  {len(clips)} clips buenos…", flush=True)

    (destino / clip_library.MANIFEST_NAME).write_text(
        json.dumps({"clips": clips}, ensure_ascii=False, indent=1)
    )
    print(f"\n{len(clips)} clips en {destino}")
    print(f"descartados: {descartados}")
    return len(clips)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pais")
    ap.add_argument("--max", type=int, default=400)
    a = ap.parse_args()
    trocear(a.pais, a.max)
