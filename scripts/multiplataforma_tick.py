"""Un tick del publicador Multiplataforma (lo llamará un timer/cron).

    python scripts/multiplataforma_tick.py --dry-run          # ver el plan, sin guardar
    python scripts/multiplataforma_tick.py --limite 5         # publicar (lo que tenga token)

Antes de publicar, ingesta los vídeos nuevos de las carpetas del Drive de
todas las cuentas activas (`<Multiplataforma>/<slug>/{viralizacion,producto}/`).
Sin token, cada plataforma se simula igualmente (estado `simulado`); con
`--dry-run` no se guarda nada en Redis.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env")

from src.multiplataforma import publicador  # noqa: E402
from src.multiplataforma.services import ingesta  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Publica las publicaciones vencidas de la cola multiplataforma")
    ap.add_argument("--dry-run", action="store_true", help="simula todo y no guarda nada")
    ap.add_argument("--limite", type=int, default=10, help="máximo de publicaciones en este tick")
    ap.add_argument("--sin-ingesta", action="store_true", help="no mirar las carpetas del Drive")
    args = ap.parse_args()
    dry = args.dry_run or None
    informe: dict = {}
    if not args.sin_ingesta and not args.dry_run:
        # la ingesta escribe en la cola: con --dry-run no se hace
        informe["ingesta"] = ingesta.ingestar_todas(log=print)
    informe["publicacion"] = publicador.publicar_pendientes(limite=args.limite, dry_run=dry, log=print)
    print(json.dumps(informe, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
