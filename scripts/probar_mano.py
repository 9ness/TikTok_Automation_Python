"""Comprueba la detección de mano (hombre/mujer) sobre vídeos ya montados.

Existe porque "auto" se equivocó eligiendo la voz y afinarlo a ciegas —cambiar
el prompt y remontar vídeos para ver qué sale— cuesta una llamada a Gemini y un
montaje entero por prueba. Esto solo mira los fotogramas y dice qué habría
elegido, así que se puede pasar una carpeta entera y contar aciertos.

Uso, en el servidor (los vídeos viven en el Drive montado):

    docker compose exec api python scripts/probar_mano.py \\
        "/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF/videos/4 Pront Flow"

    # o vídeos sueltos, y con la respuesta correcta para que cuente aciertos:
    docker compose exec api python scripts/probar_mano.py video1.mp4=hombre video2.mp4=mujer

Cada línea sale como `NOMBRE → sexo · señales en N/M · pistas`. Con `=hombre`
o `=mujer` detrás del fichero se compara y al final se resume el acierto.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.nicho_pov_bof.services import mano  # noqa: E402

EXTS = (".mp4", ".mov", ".webm", ".mkv")


def _videos(arg: str) -> list[tuple[Path, str]]:
    """`ruta` o `ruta=hombre`. Una carpeta se expande a todos sus vídeos."""
    ruta, _, esperado = arg.partition("=")
    p = Path(ruta)
    if p.is_dir():
        return [(f, esperado.strip().lower()) for f in sorted(p.iterdir())
                if f.suffix.lower() in EXTS]
    return [(p, esperado.strip().lower())]


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2

    objetivos: list[tuple[Path, str]] = []
    for a in args:
        objetivos.extend(_videos(a))
    if not objetivos:
        print("No encontré ningún vídeo en lo que me has pasado.")
        return 2

    aciertos = fallos = 0
    for video, esperado in objetivos:
        if not video.is_file():
            print(f"{video.name}: NO EXISTE")
            continue
        det = mano.detectar(video, on_log=lambda m: None)
        sexo = det.get("sexo") or "(sin mano → mujer por defecto)"
        linea = (
            f"{video.name} → {sexo} · señales en "
            f"{det.get('votos')}/{det.get('total')}"
        )
        if det.get("pistas"):
            linea += f" · {det['pistas']}"
        if esperado:
            ok = (det.get("sexo") or "mujer") == esperado
            aciertos += int(ok)
            fallos += int(not ok)
            linea += f"   [{'OK' if ok else 'FALLO, era ' + esperado}]"
        print(linea, flush=True)

    if aciertos or fallos:
        total = aciertos + fallos
        print(f"\nAciertos: {aciertos}/{total} ({aciertos * 100 // total}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
