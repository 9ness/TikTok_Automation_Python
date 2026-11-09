"""Vigía de salud de Multiplataforma: analiza y avisa al panel UNA vez por incidencia.

Corre en el host (solo biblioteca estándar):
    python3 scripts/multiplataforma_salud_avisar.py --datos salud.json [--log ~/multiplataforma/tick.log]
        [--estado ~/multiplataforma/salud_estado.json] [--dry-run]
`--datos` es la salida de `scripts/multiplataforma_salud.py` (la saca `multiplataforma_salud.sh`).
En seco imprime los avisos y no guarda estado ni manda nada. No reintenta, no publica, no borra.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.multiplataforma.services import salud  # noqa: E402

COLA_LOG_BYTES = 400_000  # ~25 ticks: basta para ver el último y si revienta
AGENTE = "VPS - Agente Jefe Meta"


def leer_cola(ruta: Path, n: int = COLA_LOG_BYTES) -> str | None:
    try:
        with open(ruta, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - n))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return None


def _cfg() -> dict:
    out = {}
    for linea in open("/etc/panel-mcp.env", encoding="utf-8").read().splitlines():
        if "=" in linea and not linea.strip().startswith("#"):
            k, v = linea.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def mandar(aviso: dict, cfg: dict) -> str:
    url = cfg.get("PANEL_URL", "https://panel.nebulabsmedia.com").rstrip("/") + "/api/avisos"
    cuenta = aviso["clave"].split(":")[1] if aviso["clave"].count(":") >= 2 else ""
    body = {"texto": f"Multiplataforma · {aviso['texto']}", "nivel": aviso["nivel"],
            "notificar": bool(aviso.get("notificar")), "cuenta": cuenta}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {cfg['PANEL_TOKEN']}", "X-Agente": AGENTE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return f"ok {resp.status}"
    except (urllib.error.URLError, OSError) as e:
        return f"error {getattr(e, 'code', type(e).__name__)}"


def main() -> int:
    casa = Path.home() / "multiplataforma"
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", required=True)
    ap.add_argument("--log", default=str(casa / "tick.log"))
    ap.add_argument("--estado", default=str(casa / "salud_estado.json"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ahora = time.time()
    try:
        datos = json.loads(Path(args.datos).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:  # el recolector falló: eso también es una incidencia
        datos = {}
        incidencias = [salud._inc("recolector:fallo", "aviso", f"No se pudieron leer los datos de salud ({type(e).__name__}).")]
    else:
        incidencias = []
    incidencias += salud.analizar(datos, leer_cola(Path(args.log)), ahora)

    ruta_estado = Path(args.estado)
    try:
        estado = json.loads(ruta_estado.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        estado = {}
    avisos, nuevo = salud.filtrar_nuevas(incidencias, estado, ahora)

    print(f"{len(incidencias)} incidencias, {len(avisos)} avisos nuevos")
    if args.dry_run:
        for a in avisos:
            print(f"  [{a['nivel']}{' 🔔' if a.get('notificar') else ''}] {a['texto']}")
        return 0
    cfg = _cfg() if avisos else {}
    for a in avisos:
        res = mandar(a, cfg)
        print(f"  [{a['nivel']}] {a['clave']}: {res}")
        if not res.startswith("ok"):  # no se avisó: que lo reintente el siguiente pase
            if a["clave"] in estado:
                nuevo[a["clave"]] = estado[a["clave"]]
            else:
                nuevo.pop(a["clave"], None)
    tmp = ruta_estado.with_suffix(".tmp")
    tmp.write_text(json.dumps(nuevo, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(ruta_estado)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
