"""Muestras de voz del POV BOF Largo con un guion REAL de un producto.

Para elegir voces nuevas hace falta oírlas diciendo lo que van a decir de
verdad: la muestra que trae el catálogo de Fish sirve para el timbre, pero no
para saber cómo le sienta a la voz nuestra CTA ni cuánto dura el vídeo.

Coge un guion ya escrito de Redis (uno del modo precio y otro del de dolor),
lo locuta con cada `reference_id` que se le pase y deja los mp3 en una carpeta,
listos para subir al Drive. Usa el MISMO camino que la cola —`voz.sintetizar`—
así que el audio sale con su nivelado, su recorte de silencios y su acelerón:
lo que se oye es exactamente lo que iría en el vídeo.

    python3 scripts/muestras_voces_largo.py --ids ids.txt --salida /tmp/muestras

`ids.txt`: una línea por voz, `CODIGO reference_id` (lo que sobra se ignora).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()


def _guion_de_ejemplo(
    estilo: str, source: str, carpetas: list[str], usuario: str,
) -> tuple[str, str]:
    """El guion más largo ya escrito en ese modo. `(de dónde sale, guion)`.

    Se leen carpetas concretas y no se busca por patrón: el cliente de Upstash
    de este nicho no tiene `SCAN` (ver `repos/redis_base.py`), y añadirlo solo
    para un script de andar por casa no compensa.
    """
    from src.nicho_pov_bof_largo.repos import product_repo

    mejor = ("", "")
    for carpeta in carpetas:
        doc = product_repo.load_folder(source, carpeta, usuario, estilo)
        for pid, prod in (doc.get("productos") or {}).items():
            guion = str(prod.get("guion") or "").strip()
            # El más largo es el que peor lo va a pasar de duración, así que es
            # con el que hay que juzgar la voz.
            if len(guion) > len(mejor[1]):
                mejor = (f"{carpeta}·producto {pid}", guion)
    if len(mejor[1]) < 150:
        raise SystemExit(
            f"No encontré guion en modo {estilo} en {source} "
            f"({', '.join(carpetas)}). Prueba otras carpetas con --carpetas."
        )
    return mejor


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="fichero con 'CODIGO reference_id' por línea")
    ap.add_argument("--salida", default="/tmp/muestras_voces")
    ap.add_argument("--guion", default="", help="texto a locutar; por defecto, uno real de Redis")
    ap.add_argument("--source", default="productos_web", help="catálogo del que sacar el guion")
    ap.add_argument("--carpetas", default="", help="carpetas separadas por coma")
    ap.add_argument("--usuario", default="ness")
    args = ap.parse_args()

    if not os.getenv("FISH_API_KEY"):
        raise SystemExit("Falta FISH_API_KEY en el .env")

    from src.nicho_pov_bof_largo import config
    from src.nicho_pov_bof_largo.services import voz

    if args.guion:
        guiones = [("amano", args.guion)]
    else:
        carpetas = [c.strip() for c in args.carpetas.split(",") if c.strip()]
        if not carpetas:
            from src.nicho_pov_bof.services import drive_client

            carpetas = [f["name"] for f in drive_client.list_product_folders(args.source)]
            print(f"{len(carpetas)} carpeta(s) en {args.source}")
        guiones = []
        for estilo in ("precio", "dolor"):
            try:
                de, g = _guion_de_ejemplo(estilo, args.source, carpetas, args.usuario)
                guiones.append((estilo, g))
                print(f"[{estilo}] guion de {de} · {len(g)} caracteres")
            except SystemExit as e:
                print(f"[{estilo}] {e}")
        if not guiones:
            raise SystemExit("Ningún guion que locutar")

    voces = []
    for linea in Path(args.ids).read_text(encoding="utf-8").splitlines():
        partes = linea.split()
        if len(partes) >= 2 and len(partes[1]) == 32:
            voces.append((partes[0], partes[1]))
    print(f"{len(voces)} voces × {len(guiones)} guion(es)")

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    # El mismo sitio que tendrían en el vídeo: dos clips de 8s.
    metraje = 16.0
    for codigo, ref in voces:
        for estilo, guion in guiones:
            destino = salida / f"{codigo}_{estilo}.mp3"
            try:
                info = voz.sintetizar(
                    guion, destino,
                    voz={"id": ref, "label": codigo},
                    segundos_ideal=metraje,
                    segundos_max=round(metraje * config.ESTIRADO_CLIP, 1),
                    segundos_min=config.DURACION_MINIMA_S,
                    on_log=lambda m: None,
                )
                print(f"  {destino.name}: {info['duracion']:.1f}s · x{info['tempo']:.2f} "
                      f"· {info['lufs']:.1f} LUFS")
            except Exception as e:  # noqa: BLE001 — una voz mala no para el resto
                print(f"  {codigo} ({estilo}) falló: {e}")
    print(f"\nListo en {salida}")


if __name__ == "__main__":
    main()
