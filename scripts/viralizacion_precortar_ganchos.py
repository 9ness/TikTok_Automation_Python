#!/usr/bin/env python3
"""Pre-corta los ganchos de un ponente a clips de 3s y libera el vídeo fuente.

El vídeo de gancho pesa entre 300 MB y 1,1 GB por ponente. Con varios
ponentes el disco del VPS se llena, y encima el original NO hace falta para
renderizar: solo se usa para sacar 3 segundos. Aquí se recortan todos los
candidatos a ficheros de ~0,8 MB y se guarda la ruta en el JSON de
candidatos; después se puede borrar el vídeo grande (sigue en Drive).

Se recorta SIN tocar el encuadre: el `cx_frac` y el zoom los sigue aplicando
el renderer en cada vídeo, que es lo que da el jitter anti-fingerprint.

Uso:
    python scripts/viralizacion_precortar_ganchos.py mario [segarra …]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.viralizacion import config  # noqa: E402


def precortar(slug: str) -> int:
    fuente = config.ponente_gancho_video(slug)
    cache = config.hook_candidates_cache_path(slug)
    if fuente is None or not cache.is_file():
        print(f"  ✗ {slug}: falta el vídeo fuente o el JSON de candidatos")
        return 0

    data = json.loads(cache.read_text())
    destino = config.ponente_ganchos_dir(slug)
    destino.mkdir(parents=True, exist_ok=True)

    hechos = 0
    for c in data.get("candidates", []):
        out = destino / f"hook_{c['index']:04d}.mp4"
        if not out.is_file():
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y",
                 "-ss", f"{float(c['start']):.3f}", "-t", f"{config.HOOK_DUR:.3f}",
                 "-i", str(fuente),
                 # Re-encode corto: con `-c copy` el corte salta al keyframe
                 # anterior y el gancho empezaría en otro sitio.
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                 "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart",
                 str(out)],
                check=True,
            )
            hechos += 1
        # Ruta relativa a la carpeta del ponente: así el JSON no depende de
        # dónde esté montado el disco (host vs container).
        c["clip"] = out.name
        # `start` pasa a ser 0: el clip YA es el tramo recortado.
        c["start_original"] = c["start"]
        c["start"] = 0.0

    data["ganchos_precortados"] = True
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(f.stat().st_size for f in destino.glob("hook_*.mp4"))
    print(f"  ✓ {slug}: {len(data['candidates'])} ganchos ({hechos} nuevos) · "
          f"{total/1e6:.0f} MB · fuente {fuente.stat().st_size/1e6:.0f} MB se puede borrar")
    return hechos


if __name__ == "__main__":
    for slug in sys.argv[1:] or sorted(config.PONENTES):
        precortar(slug)
