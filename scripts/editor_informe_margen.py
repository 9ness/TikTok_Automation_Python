"""Informe de margen del Editor Auto (lo lanza la rutina de los lunes).

Se ejecuta DENTRO del contenedor, que es donde está la SQLite:
    docker exec tiktok-api python scripts/editor_informe_margen.py [--desde AAAA-MM-DD] [--hasta …] [--json]
Solo lee. Sale con código 2 si hay alertas, para que la rutina avise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.editor_auto.services import estadisticas as est  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--desde")
    ap.add_argument("--hasta")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    datos = est.margen(a.desde, a.hasta)
    print(json.dumps(datos, ensure_ascii=False, indent=1) if a.json else est.informe_margen_texto(datos))
    return 2 if datos["alertas"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
