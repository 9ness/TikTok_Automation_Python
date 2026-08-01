"""Lee/expone el estado del deploy actual para que la UI lo muestre.

`deploy/deploy_safe.sh` escribe `temp_work/deploy_status.json` al iniciar
(state=running) y al terminar (state=success/failed). Si ese archivo no
existe (deploy nunca ha corrido), se cae a `git rev-parse HEAD` para que
la UI siempre muestre algo.

Estructura del JSON:
{
    "state": "running|success|failed|deferred",   # deferred = había
                                                   # jobs renderizando y NO se desplegó
    "current_sha": "5ea1505",
    "current_sha_full": "5ea15054...",
    "previous_sha": "f5875e7",
    "started_at": 1746123456.789,
    "finished_at": 1746123480.123,
    "target_sha": "5ea1505"          # solo en state=running
}
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Optional


def _repo_root() -> Path:
    """Raíz del repo (carpeta padre de src/)."""
    return Path(__file__).resolve().parent.parent


def _status_path() -> Path:
    return _repo_root() / "temp_work" / "deploy_status.json"


def _git_head_sha(short: bool = True) -> Optional[str]:
    """SHA de HEAD vía git. Devuelve None si falla (no es repo, sin git)."""
    try:
        args = ["git", "rev-parse", "--short", "HEAD"] if short else \
               ["git", "rev-parse", "HEAD"]
        out = subprocess.check_output(
            args, cwd=str(_repo_root()), stderr=subprocess.DEVNULL,
            text=True, timeout=2,
        )
        return out.strip() or None
    except Exception:
        return None


def _git_head_time() -> Optional[float]:
    """Timestamp del último commit (no del último deploy real). Fallback
    para cuando no hay deploy_status.json."""
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%ct", "HEAD"],
            cwd=str(_repo_root()), stderr=subprocess.DEVNULL,
            text=True, timeout=2,
        )
        return float(out.strip())
    except Exception:
        return None


def get_status() -> dict:
    """Devuelve el estado actual. Siempre devuelve un dict (nunca None).

    Campos garantizados:
        - state: "running" | "success" | "failed" | "deferred" | "unknown"
        - current_sha: str ("?" si no se puede determinar)
        - age_seconds: int (segundos desde el último cambio relevante)

    Si el JSON registra un estado "failed"/"running" pero el HEAD real
    de git es DISTINTO al registrado, asumimos que hubo una recuperación
    manual (alguien hizo git pull + restart por SSH) y reseteamos el
    estado a success en el SHA real. Sin esta detección el badge se
    quedaría rojo para siempre tras un fallo aunque la app ya esté OK.
    """
    info = {
        "state": "unknown",
        "current_sha": "?",
        "current_sha_full": "?",
        "previous_sha": None,
        "started_at": None,
        "finished_at": None,
        "target_sha": None,
        "age_seconds": None,
    }

    # 1. Intentar leer deploy_status.json (lo escribe deploy_safe.sh)
    p = _status_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            info.update(data)
        except Exception:
            pass

    # 2. Leer SIEMPRE el HEAD real de git (independiente del JSON)
    actual_sha = _git_head_sha(short=True)
    actual_sha_full = _git_head_sha(short=False)

    # 3. Detección de recuperación manual: estado registrado dice failed
    #    o running, pero HEAD ya está en otro SHA → manual recovery hecha,
    #    el estado JSON está obsoleto.
    recorded = info.get("current_sha")
    state = info.get("state")
    is_stale = (
        state in ("failed", "running")
        and actual_sha
        and recorded
        and recorded not in ("?", None)
        and recorded != actual_sha
    )
    if is_stale:
        info["state"] = "success"
        info["current_sha"] = actual_sha
        info["current_sha_full"] = actual_sha_full or "?"
        info["error"] = None
        info["finished_at"] = _git_head_time()  # fecha del commit
        info["recovered_manually"] = True

    # 4. Si current_sha sigue desconocido (no había JSON), fallback a git
    if info["current_sha"] == "?":
        if actual_sha:
            info["current_sha"] = actual_sha
        if actual_sha_full:
            info["current_sha_full"] = actual_sha_full

    # 5. Calcular edad
    now = time.time()
    ref_time = info.get("finished_at") or info.get("started_at")
    if ref_time is None:
        ref_time = _git_head_time()
    if ref_time is not None:
        info["age_seconds"] = int(max(0, now - ref_time))

    # 6. Si no hay state pero tenemos sha, asumimos success (ya está corriendo)
    if info["state"] == "unknown" and info["current_sha"] != "?":
        info["state"] = "success"

    return info


def format_age(seconds: Optional[int]) -> str:
    """Formato humano: '12s', '3m', '1h 15m', '2d', etc."""
    if seconds is None:
        return "?"
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h {m}m"
    d, h = divmod(h, 24)
    return f"{d}d {h}h"


def write_status(payload: dict) -> None:
    """Helper para escribir el estado (lo usa deploy_safe.sh indirectamente
    o cualquier script Python que quiera marcar estado)."""
    p = _status_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(p)


# CLI usage: `python -m src.deploy_status` imprime el estado actual en JSON
if __name__ == "__main__":
    print(json.dumps(get_status(), ensure_ascii=False, indent=2))
