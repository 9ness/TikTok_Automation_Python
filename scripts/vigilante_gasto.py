"""Recolector del vigilante de gasto y salud (#293). Corre DENTRO de tiktok-api.

Lo lanza `scripts/vigilante_gasto.sh` con `docker exec`. Imprime un JSON con:
  · `jobs`: los JobCost del mes actual y del anterior, ya adelgazados (sin
    títulos ni usuarios);
  · `salud`: la respuesta de `/api/health/completo` (None si no contesta).
No escribe nada ni llama a ninguna API de pago.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from src import cost_tracking
try:
    from src.vigilante_gasto import adelgazar
except ImportError:  # imagen anterior al deploy: el .sh copia el módulo junto a este script
    from vigilante_analisis import adelgazar  # type: ignore[no-redef]


def _meses(ahora: datetime) -> list[str]:
    anterior = ahora.replace(day=1) - timedelta(days=1)
    return [ahora.strftime("%Y-%m"), anterior.strftime("%Y-%m")]


def _salud() -> dict | None:
    puerto = os.getenv("API_PORT", "8000")
    req = urllib.request.Request(f"http://127.0.0.1:{puerto}/api/health/completo")
    if os.getenv("API_KEY"):
        req.add_header("X-API-Key", os.environ["API_KEY"])
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:  # 503 trae el cuerpo con los fallos
        try:
            return json.loads(e.read())
        except Exception:  # noqa: BLE001
            return None
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    ahora = datetime.now(timezone.utc)
    jobs: list[dict] = []
    for mes in _meses(ahora):
        jobs.extend(cost_tracking.list_jobs(month=mes, limit=5000))
    json.dump({"ahora": time.time(), "jobs": adelgazar(jobs), "salud": _salud()}, sys.stdout)


if __name__ == "__main__":
    main()
