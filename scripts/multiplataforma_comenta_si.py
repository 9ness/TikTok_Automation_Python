"""«Comenta SÍ» (#297): un pase por las cuentas de IG. EN SECO salvo
MULTIPLATAFORMA_COMENTA_SI_ENVIAR=1. Corre dentro del contenedor api:

    docker cp scripts/multiplataforma_comenta_si.py tiktok-api:/tmp/ && \
    docker exec -w /app -e PYTHONPATH=/app tiktok-api python /tmp/multiplataforma_comenta_si.py

Imprime el informe en JSON (sin tokens). Lo anotado en seco queda en Redis
`multiplataforma:comenta_si:seco:<fecha>`.
"""

from __future__ import annotations

import json
import sys

from src.multiplataforma.services import comenta_si


def main() -> int:
    informes = comenta_si.procesar_todas(log=lambda m: print(m, file=sys.stderr))
    json.dump(informes, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
