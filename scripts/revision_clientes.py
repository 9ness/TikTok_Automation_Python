"""Revisión por agente de los vídeos de clientes de Nebulabs Media.

Con la aprobación manual activa (`settings:manual_approval` = 1), el editor
deja los vídeos buenos «en revisión» y re-edita solo los malos. Este script es
lo que usa el agente revisor (rutina `revision-clientes-nebulabs.md`), DENTRO
del contenedor de la API:

    docker exec tiktok-api python scripts/revision_clientes.py pendientes
    docker exec tiktok-api python scripts/revision_clientes.py aprobar <user_id> <día> <fichero>
    docker exec tiktok-api python scripts/revision_clientes.py rehacer <user_id> <día> <original> [<fichero>]
    docker exec tiktok-api python scripts/revision_clientes.py cuenta          (solo el nº: para el vigilante)

Aprobar = el cliente ya lo ve y, cuando su día queda completo (p. ej. sus 3
vídeos de prueba), le sale el email de «tus vídeos están listos».
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# Todo pasa por la API que ya corre (la cola vive en SU proceso: abrir otra
# aquí podría ponerse a editar por su cuenta).
_BASE = os.getenv("REVISION_API_BASE", "http://localhost:8000") + "/api/v1/editor-auto/web"


def _api(metodo: str, ruta: str, cuerpo: dict | None = None) -> dict:
    import urllib.request

    req = urllib.request.Request(
        _BASE + ruta, method=metodo,
        data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
        headers={"Content-Type": "application/json", "X-API-Key": os.getenv("API_KEY", "")},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def pendientes() -> list[dict]:
    from src.editor_auto.config import user_input_day_folder, user_output_day_folder

    res = _api("GET", "/admin/pending")
    out = []
    for p in res.get("pending", []):
        nombre, day, fn, src = p.get("user_name"), p.get("day"), p.get("filename"), p.get("source")
        out.append({
            **p,
            "ruta_editado": os.path.join(user_output_day_folder(nombre, day), fn) if nombre and fn else None,
            "ruta_original": os.path.join(user_input_day_folder(nombre, day), src) if nombre and src else None,
        })
    return out


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "cuenta":
        try:
            print(len(pendientes()))
        except Exception as e:  # noqa: BLE001 — el vigilante solo quiere un número
            print(0)
            print(f"error: {e}", file=sys.stderr)
    elif cmd == "pendientes":
        print(json.dumps(pendientes(), ensure_ascii=False, indent=1, default=str))
    elif cmd == "aprobar" and len(sys.argv) == 5:
        print(json.dumps(_api("POST", "/admin/approve", {
            "user_id": sys.argv[2], "day": sys.argv[3], "filename": sys.argv[4], "approve": True})))
    elif cmd == "rehacer" and len(sys.argv) in (5, 6):
        print(json.dumps(_api("POST", "/admin/requeue", {
            "user_id": sys.argv[2], "day": sys.argv[3], "source": sys.argv[4],
            "filename": sys.argv[5] if len(sys.argv) == 6 else None})))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
