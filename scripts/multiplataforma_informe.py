"""Informe semanal de Meta en Markdown a partir de ~/multiplataforma/estadisticas/*.json.

Corre en el host (solo biblioteca estándar, sin API):
    python3 scripts/multiplataforma_informe.py [--carpeta DIR] [--dias 7]
Escribe `semanal_<fecha>.md` en la carpeta y imprime su ruta.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.multiplataforma.services import informe  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--carpeta", default=str(Path.home() / "multiplataforma" / "estadisticas"))
    ap.add_argument("--dias", type=int, default=7)
    args = ap.parse_args()
    carpeta = Path(args.carpeta)
    fotos = informe.cargar(carpeta)
    if not fotos:
        print(f"Sin JSON en {carpeta}", file=sys.stderr)
        return 1
    salida = carpeta / f"semanal_{fotos[-1][0]}.md"
    salida.write_text(informe.generar(fotos, dias=args.dias), encoding="utf-8")
    salida.chmod(0o600)
    print(salida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
