"""Informe de margen del Editor Auto (lo lanza la rutina de los lunes).

Se ejecuta DENTRO del contenedor, que es donde está la SQLite:
    docker exec -w /app tiktok-api python -m src.editor_auto.services.informe_margen [--desde AAAA-MM-DD] [--hasta …] [--json]
Solo lee. Sale con código 2 si hay alertas, para que la rutina avise.
"""
from __future__ import annotations

import argparse
import json

from src.editor_auto.services import estadisticas as est


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
