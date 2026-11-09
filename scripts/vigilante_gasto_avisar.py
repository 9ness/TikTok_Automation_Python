"""Vigilante de gasto de IA y salud (#293): analiza y avisa al panel UNA vez por incidencia.

Corre en el host (solo biblioteca estándar):
    python3 scripts/vigilante_gasto_avisar.py --datos ~/vigilante/datos.json
        [--estado ~/vigilante/estado.json] [--dry-run]
`--datos` es la salida de `scripts/vigilante_gasto.py` (la saca `vigilante_gasto.sh`).
En seco imprime el resumen y los avisos; no guarda estado ni manda nada.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.vigilante_gasto import avisos_gasto, avisos_salud, nuevos, resumen  # noqa: E402

AGENTE = "Vigilante Factory"


def _cfg() -> dict:
    out = {}
    for linea in open("/etc/panel-mcp.env", encoding="utf-8").read().splitlines():
        if "=" in linea and not linea.strip().startswith("#"):
            k, v = linea.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def mandar(aviso: dict, cfg: dict) -> str:
    url = cfg.get("PANEL_URL", "https://panel.nebulabsmedia.com").rstrip("/") + "/api/avisos"
    body = {"texto": f"Factory · {aviso['texto']}", "nivel": aviso["nivel"], "notificar": False}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {cfg['PANEL_TOKEN']}", "X-Agente": AGENTE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return f"ok {resp.status}"
    except Exception as e:  # noqa: BLE001 — panel caído o respuesta rara: se reintenta en la próxima pasada
        return f"error {getattr(e, 'code', type(e).__name__)}"


def analizar(datos: dict | None, ahora: float) -> tuple[dict | None, list[dict]]:
    """Datos del recolector → (resumen del gasto, avisos). `datos=None` = el recolector falló."""
    if not datos:
        return None, [{"clave": "salud:recolector", "nivel": "aviso",
                       "texto": "El vigilante no pudo leer tiktok-api (¿contenedor caído?). Detalle en ~/vigilante/error.log."}]
    r = resumen(datos.get("jobs") or [], ahora)
    return r, avisos_gasto(r) + avisos_salud(datos.get("salud"))


def main() -> int:
    casa = Path.home() / "vigilante"
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", required=True)
    ap.add_argument("--estado", default=str(casa / "estado.json"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ahora = time.time()
    try:
        datos = json.loads(Path(args.datos).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        datos = None
    r, avisos = analizar(datos, ahora)

    ruta_estado = Path(args.estado)
    try:
        estado = json.loads(ruta_estado.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        estado = {}
    enviar, estado = nuevos(avisos, estado, ahora)

    if args.dry_run:
        print(json.dumps({"resumen": r, "avisos": avisos, "se_enviarian": enviar}, ensure_ascii=False, indent=1))
        return 0
    try:
        cfg = _cfg() if enviar else {}
        if enviar and not cfg.get("PANEL_TOKEN"):
            raise KeyError("PANEL_TOKEN")
    except (OSError, KeyError) as e:  # sin config del panel: no se pierde el aviso, se reintenta
        print(f"sin config del panel (/etc/panel-mcp.env): {type(e).__name__}", file=sys.stderr)
        return 1
    for a in enviar:
        res = mandar(a, cfg)
        print(f"{a['clave']}: {res}")
        if not res.startswith("ok"):
            estado.pop(a["clave"], None)  # no llegó: se reintenta en la próxima pasada
    ruta_estado.parent.mkdir(parents=True, exist_ok=True)
    ruta_estado.write_text(json.dumps(estado), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
