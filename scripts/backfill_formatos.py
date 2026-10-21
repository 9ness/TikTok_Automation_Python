"""Rellena los contadores por formato (`formatos`) de los productos con los
vídeos que YA están marcados como subidos en Mis tandas.

Idempotente: `marcas.registrar_subido` apunta ids (`usuario|id de Mis tandas`)
y no cuenta, así que repetirlo no duplica nada, ni en `formatos` ni en
`contenido.subidos` (que también se rellena si el producto necesita contenido).

Por defecto es un ensayo (`--dry-run`): lee y cuenta, no escribe. Para
escribir: `--aplicar`.

    python scripts/backfill_formatos.py              # solo cuenta
    python scripts/backfill_formatos.py --aplicar    # escribe
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env")

from src.mis_tandas import servicio  # noqa: E402
from src.nicho_pov_bof.services import marcas  # noqa: E402

USUARIOS = ("ness", "nestor2", "ana")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--aplicar", action="store_true", help="escribe (sin esto, solo cuenta)")
    ap.add_argument("--dry-run", action="store_true", help="por defecto; solo cuenta")
    args = ap.parse_args()
    aplicar = args.aplicar and not args.dry_run

    total = Counter()
    for usuario in USUARIOS:
        cuenta = Counter()
        for f in servicio.filas(usuario, fresco=True):
            if not f.get("uploaded"):
                continue
            fuente, carpeta, prod = f.get("source"), f.get("carpeta"), f.get("producto")
            if f.get("nicho") == "rv":
                # Las réplicas cuentan si están atadas a un producto del catálogo.
                ref = servicio._ref_rv(usuario, str(f["id"]).split("|", 1)[-1])
                if not ref:
                    continue
                fuente, carpeta, prod = ref[0], ref[1], ref[2]
            if fuente not in marcas.FUENTES_MARCAS:
                continue
            formato = marcas.formato_de(f.get("nicho"), f.get("modo"))
            if not formato:
                continue
            cuenta[formato] += 1
            if aplicar:
                marcas.registrar_subido(
                    fuente, carpeta, prod, f"{usuario}|{f['id']}", True, formato=formato,
                )
        total.update(cuenta)
        print(f"{usuario}: " + (", ".join(f"{k}={v}" for k, v in sorted(cuenta.items())) or "nada"))
    print("TOTAL: " + (", ".join(f"{k}={v}" for k, v in sorted(total.items())) or "nada"),
          "(escrito)" if aplicar else "(dry-run, no se ha escrito nada)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
