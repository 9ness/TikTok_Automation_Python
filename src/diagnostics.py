"""Recoge información de diagnóstico del VPS para mostrarla en la UI.

Permite al usuario ver desde el propio Streamlit (sin SSH):
- Estado de los 3 servicios (tiktok-factory / tiktok-webhook / gdrive-mount)
- Logs recientes de la app (journalctl)
- Logs del último deploy (logs/deploy.log)
- Logs del webhook listener
- Estado git (HEAD local vs origin/main, commits pendientes)

Asume que el usuario `nebulabsai` tiene sudo NOPASSWD (configurado en
deploy/setup.sh línea ~95: echo "${APP_USER} ALL=(ALL) NOPASSWD:ALL").
Si no, las llamadas a journalctl pedirán password y fallarán con timeout.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _run(cmd: list[str], timeout: int = 6) -> str:
    """Ejecuta un comando y devuelve stdout+stderr (truncado a 50KB)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_repo_root()),
        )
        out = (result.stdout or "") + (result.stderr or "")
        if len(out) > 50_000:
            out = out[-50_000:] + "\n[...truncado, mostrando últimas 50KB]"
        return out.strip() or "(sin output)"
    except subprocess.TimeoutExpired:
        return f"❌ timeout ({timeout}s) ejecutando: {' '.join(cmd)}"
    except FileNotFoundError:
        return f"❌ comando no existe: {cmd[0]}"
    except Exception as e:
        return f"❌ error: {e}"


def get_services_status() -> dict[str, str]:
    """Estado de los servicios systemd críticos. Devuelve {nombre: 'active'|'inactive'|'failed'|...}."""
    services = ["tiktok-factory", "tiktok-webhook", "gdrive-mount"]
    out = {}
    for svc in services:
        result = _run(["systemctl", "is-active", svc], timeout=3)
        # is-active devuelve 'active' / 'inactive' / 'failed' / 'activating'
        out[svc] = result.strip() or "unknown"
    return out


def get_app_logs(n: int = 50) -> str:
    """Últimas N líneas del log de la app Streamlit."""
    return _run(
        ["sudo", "-n", "journalctl", "-u", "tiktok-factory",
         "-n", str(n), "--no-pager", "--output=short-iso"],
        timeout=8,
    )


def get_webhook_logs(n: int = 30) -> str:
    """Últimas N líneas del webhook listener (recibos de pushes de GitHub)."""
    return _run(
        ["sudo", "-n", "journalctl", "-u", "tiktok-webhook",
         "-n", str(n), "--no-pager", "--output=short-iso"],
        timeout=8,
    )


def get_mount_logs(n: int = 30) -> str:
    """Últimas N líneas del mount de Drive."""
    return _run(
        ["sudo", "-n", "journalctl", "-u", "gdrive-mount",
         "-n", str(n), "--no-pager", "--output=short-iso"],
        timeout=8,
    )


def get_deploy_log(n: int = 60) -> str:
    """Últimas N líneas del log del script de deploy (git pull + restart).
    Lee directamente el archivo (no requiere sudo)."""
    log_path = _repo_root() / "logs" / "deploy.log"
    if not log_path.exists():
        return "(sin log de deploy todavía — no se ha lanzado ningún auto-deploy)"
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:]).strip() or "(log vacío)"
    except Exception as e:
        return f"❌ error leyendo deploy.log: {e}"


def get_git_status() -> dict[str, Optional[str]]:
    """Estado git: HEAD local, último de origin/main, commits pendientes."""
    out: dict[str, Optional[str]] = {
        "head_local": None,
        "head_local_msg": None,
        "head_remote": None,
        "head_remote_msg": None,
        "pending_commits": None,
        "is_dirty": None,
    }
    head_full = _run(["git", "log", "-1", "--format=%h %ci %s", "HEAD"], timeout=3)
    if head_full and not head_full.startswith("❌"):
        out["head_local_msg"] = head_full
        out["head_local"] = head_full.split()[0]

    # fetch silencioso para tener origin/main al día (puede tardar 2-3s)
    _run(["git", "fetch", "--quiet", "origin", "main"], timeout=8)

    head_remote = _run(
        ["git", "log", "-1", "--format=%h %ci %s", "origin/main"], timeout=3,
    )
    if head_remote and not head_remote.startswith("❌"):
        out["head_remote_msg"] = head_remote
        out["head_remote"] = head_remote.split()[0]

    # Commits pendientes (en origin pero no en local)
    pending = _run(
        ["git", "log", "HEAD..origin/main", "--oneline"], timeout=3,
    )
    if pending and not pending.startswith("❌"):
        if pending == "(sin output)":
            out["pending_commits"] = ""
        else:
            out["pending_commits"] = pending

    # Working tree limpio?
    dirty = _run(["git", "status", "--porcelain"], timeout=3)
    out["is_dirty"] = bool(dirty and dirty != "(sin output)" and not dirty.startswith("❌"))

    return out


def get_disk_space() -> str:
    """Espacio libre en disco (útil para detectar VPS lleno)."""
    return _run(["df", "-h", "--output=avail,pcent,target", "/"], timeout=3)


def get_queue_summary() -> dict:
    """Resumen del estado de la cola de jobs (sin necesidad de subprocess)."""
    import json
    state_path = _repo_root() / "temp_work" / "queue_state.json"
    if not state_path.exists():
        return {"total": 0, "pending": 0, "running": 0, "failed": 0, "completed": 0}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        jobs = data.get("jobs", [])
        counts = {"total": len(jobs), "pending": 0, "running": 0,
                  "failed": 0, "completed": 0, "cancelled": 0}
        for j in jobs:
            s = j.get("status", "")
            if s in counts:
                counts[s] += 1
        return counts
    except Exception:
        return {"error": "no se pudo leer queue_state.json"}
