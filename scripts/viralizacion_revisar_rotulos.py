#!/usr/bin/env python3
"""Repasa una biblioteca de clips ya construida y retira los que llevan rótulo.

Existe porque el filtro original miraba un solo fotograma y se colaron cartelas
que entran animadas (`UNITED STATES` sobre un mapa, `GRAND CANYON` al pie).
Salieron publicadas en un vídeo, así que hay que poder limpiar el banco SIN
rehacerlo entero: volver a trocear el fuente son horas, y además el fuente ya
se borró para recuperar disco.

Los clips retirados NO se borran: van a `_con_rotulo/` dentro de la propia
biblioteca. Si algún día el filtro se pasa de listo, están ahí para revisarlos.

Uso:
    python scripts/viralizacion_revisar_rotulos.py us
    python scripts/viralizacion_revisar_rotulos.py es --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from src.viralizacion.services import clip_library, rotulos  # noqa: E402


def revisar(pais: str, dry_run: bool) -> int:
    carpeta = clip_library.clips_folder(pais)
    clips = clip_library.all_clips(pais)
    if not clips:
        raise SystemExit(f"No hay biblioteca en {carpeta}")

    import easyocr

    lector = easyocr.Reader(["es", "en"], gpu=False, verbose=False)
    apartados = carpeta / "_con_rotulo"

    limpios: list[dict] = []
    retirados: list[tuple[str, list[str]]] = []
    t0 = time.time()

    for i, clip in enumerate(clips, 1):
        path = clip_library.clip_path(clip, pais)
        if not path.is_file():
            continue
        palabras = rotulos.texto_en_clip(path, lector)
        if palabras:
            retirados.append((clip["file"], palabras))
            print(f"  ✗ {clip['file']}  {palabras[:5]}", flush=True)
            if not dry_run:
                apartados.mkdir(parents=True, exist_ok=True)
                path.rename(apartados / path.name)
        else:
            limpios.append(clip)
        if i % 25 == 0:
            ritmo = (time.time() - t0) / i
            print(f"  … {i}/{len(clips)} revisados, "
                  f"quedan ~{ritmo * (len(clips) - i) / 60:.0f} min", flush=True)

    # NO se renumera, aunque queden huecos. `index` es la CLAVE con la que
    # `usage_repo` lleva en Redis qué clips ha gastado ya cada ponente
    # (`paisaje_used:<ponente>`). Renumerar reasigna esos números a otros
    # clips: los ya gastados volverían a salir y otros quedarían bloqueados
    # sin haberse usado nunca — justo la garantía de "no repetir" que sostiene
    # todo el módulo. Un hueco en la numeración no molesta a nadie.
    print(f"\n{pais}: {len(limpios)} limpios, {len(retirados)} con rótulo")
    for f, pal in retirados:
        print(f"   {f}: {', '.join(pal[:6])}")

    if dry_run:
        print("\n(dry-run: no se ha tocado nada)")
        return len(retirados)

    manifiesto = carpeta / clip_library.MANIFEST_NAME
    manifiesto.write_text(
        json.dumps({"clips": limpios}, ensure_ascii=False, indent=1)
    )
    print(f"\nmanifiesto reescrito: {manifiesto}")
    return len(retirados)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pais")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    revisar(a.pais, a.dry_run)
