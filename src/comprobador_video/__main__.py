"""`python3 -m src.comprobador_video v1.mp4 [v2.mp4 …] [--clips 2] [--con-voz] [--json]`

Una línea por vídeo con el veredicto y lo que no pasa. Sale con 1 si alguno
falla y con 2 si alguno no se pudo leer. Solo necesita ffmpeg y ffprobe.
"""

from __future__ import annotations

import argparse
import json
import sys

from src.comprobador_video.tecnico import DUDAS, FALLA, PASA, ErrorComprobador, comprobar

MARCA = {PASA: "✅", DUDAS: "🟡", FALLA: "🔴"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m src.comprobador_video", description=__doc__.split("\n\n")[1])
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--clips", type=int, default=2, help="de cuántos clips está montado (movimiento por clip)")
    ap.add_argument("--con-voz", action="store_true", help="el formato lleva voz: sin audio es fallo")
    ap.add_argument("--json", action="store_true", help="salida en JSON (una lista)")
    a = ap.parse_args(argv)

    salida, codigo = [], 0
    for ruta in a.videos:
        try:
            inf = comprobar(ruta, clips=a.clips, con_voz=a.con_voz)
        except ErrorComprobador as e:
            codigo = 2
            salida.append({"ruta": ruta, "veredicto": "error", "error": str(e)})
            if not a.json:
                print(f"⚠️  error   {ruta}\n     {e}")
            continue
        if inf.veredicto == FALLA and codigo == 0:
            codigo = 1
        salida.append(inf.como_dict())
        if not a.json:
            print(f"{MARCA[inf.veredicto]} {inf.veredicto:<6} {ruta}")
            for c in inf.comprobaciones:
                if c.veredicto != PASA:
                    print(f"     {MARCA[c.veredicto]} {c.clave}: {c.detalle}")
    if a.json:
        print(json.dumps(salida, ensure_ascii=False, indent=1))
    elif any(s.get("veredicto") == PASA for s in salida):
        print("\nPasar lo técnico no es un verde: falta revisar el producto contra la ficha.")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
