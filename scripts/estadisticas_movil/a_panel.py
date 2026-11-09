"""Copia las estadísticas de TikTok Shop de la Factory al panel (Cuentas › Shop).

Uso (en vps-trabajo, tras guardar_estadisticas):
    python3 -I scripts/estadisticas_movil/a_panel.py            # todas las cuentas
    python3 -I scripts/estadisticas_movil/a_panel.py nestor2    # solo una

Lee `ventas:<usuario>` con `src.estadisticas.repo.leer` dentro del contenedor
`tiktok-api` y lo manda tal cual a `POST /api/shop/stats` del panel (mismo
formato; el panel fusiona por día/mes). Token del panel: /etc/panel-mcp.env.
No imprime secretos.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request

CUENTAS = {
    "ness": "Viva Shop",
    "ana": "Ama Shop (@aama_22)",
    "nestor2": "Casca Chollos (@vistoyfichado)",
    "nes_bugallo": "Cuenta árabe (hmizat)",
}
CAMPOS = ("dias", "meses", "contenidos", "notas", "rango_pedidos", "actualizado")


def _cfg() -> dict:
    out = {}
    for linea in open("/etc/panel-mcp.env", encoding="utf-8").read().splitlines():
        if "=" in linea and not linea.strip().startswith("#"):
            k, v = linea.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def leer_factory(usuario: str) -> dict:
    code = ("import json;from src.estadisticas import repo;"
            f"print(json.dumps(repo.leer({usuario!r}),ensure_ascii=False))")
    r = subprocess.run(["docker", "exec", "-w", "/app", "-e", "PYTHONPATH=/app", "tiktok-api",
                        "python", "-c", code], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-300:])
    return json.loads(r.stdout.strip().splitlines()[-1] or "{}")


def mandar(cuenta: str, doc: dict) -> str:
    cfg = _cfg()
    url = cfg.get("PANEL_URL", "https://panel.nebulabsmedia.com").rstrip("/") + "/api/shop/stats"
    body = {k: v for k, v in doc.items() if k in CAMPOS and v}
    body["cuenta"] = cuenta
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {cfg['PANEL_TOKEN']}", "X-Agente": "TikTok_Automation_Python",
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode()[:300]
    except urllib.error.HTTPError as e:
        return f"Error {e.code}: {e.read().decode()[:300]}"


def main() -> None:
    usuarios = sys.argv[1:] or list(CUENTAS)
    for u in usuarios:
        try:
            doc = leer_factory(u)
        except Exception as e:  # noqa: BLE001
            print(u, "ERROR leyendo Factory:", e)
            continue
        if not any(doc.get(k) for k in ("dias", "meses")):
            print(u, "sin datos en la Factory")
            continue
        print(u, mandar(CUENTAS.get(u, u), doc))


if __name__ == "__main__":
    main()
