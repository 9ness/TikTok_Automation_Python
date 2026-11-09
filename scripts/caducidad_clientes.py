"""Caducidad de los vídeos de clientes web (Editor Auto) a mano.

    scripts/caducidad_clientes.sh simular     lista lo que se borraría y cuánto ocupa
    scripts/caducidad_clientes.sh ejecutar    lo borra (irreversible)

Pasa por la API que ya corre (POST /api/v1/editor-auto/web/admin/retention):
ella sabe qué trabajos siguen en cola y no abre otra. La pasada automática
la hace el draft_sweeper cada 6 h (src/editor_auto/services/retention_sweeper.py).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

_URL = os.getenv("REVISION_API_BASE", "http://localhost:8000") + "/api/v1/editor-auto/web/admin/retention"


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("simular", "ejecutar"):
        sys.exit(__doc__)
    dry = sys.argv[1] == "simular"
    req = urllib.request.Request(
        f"{_URL}?dry_run={'true' if dry else 'false'}", method="POST", data=b"",
        headers={"X-API-Key": os.getenv("API_KEY", "")},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        res = json.loads(r.read().decode())
    print(f"{'SIMULACIÓN' if dry else 'BORRADO'} · editados {res['retention_days']} días, "
          f"originales {res['retention_source_days']} días")
    for i in res["items"]:
        err = f"  ⚠️ {i['error']}" if i.get("error") else ""
        print(f"  {i['bytes'] / 1e6:8.0f} MB  {i['tipo']:<10} {i['usuario']}: {i['ruta']}{err}")
    print(f"Total: {len(res['items'])} elementos, {res['total_bytes'] / 1e9:.2f} GB")


if __name__ == "__main__":
    main()
