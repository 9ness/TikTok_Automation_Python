"""Endpoints de diagnóstico — equivalente al panel "🩺 Diagnóstico" del
viejo Streamlit. Lee del filesystem (`temp_work/`, `logs/`, `.git/`) y
expone:

- GET /api/v1/diagnostics/summary    → estado combinado de servicios,
                                       git, deploy, cola, disco.
- GET /api/v1/diagnostics/deploy     → `temp_work/deploy_status.json`
                                       + últimas líneas de `logs/deploy.log`.
- GET /api/v1/diagnostics/app-logs   → últimas líneas de `logs/app.log`
                                       (si existe) — fallback a journalctl
                                       solo si está disponible en el container.

Diseño: la API corre dentro de un container Docker. Para que estos
endpoints reflejen la realidad del HOST (donde corren systemd, git y el
deploy script), `docker-compose.override.yml` debe bind-montar:

    ./temp_work       → /host_data/temp_work    :ro
    ./logs            → /host_data/logs         :ro
    ./.git            → /host_data/.git         :ro
    ./VERSION         → /host_data/VERSION      :ro

Si la ruta `/host_data/...` no existe, los endpoints caen al fallback
del repo del propio container (`/app/...`) — útil en dev local sin
compose.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_current_user

logger = logging.getLogger("api")


router = APIRouter(
    prefix="/api/v1/diagnostics",
    tags=["diagnostics"],
    dependencies=[Depends(get_current_user)],
)


# ---------------------------------------------------------------------------
# Resolución de paths host vs container
# ---------------------------------------------------------------------------
_HOST_DATA = Path("/host_data")


def _host_or_local(rel: str) -> Path:
    """Devuelve la ruta `/host_data/<rel>` si existe, si no `/app/<rel>`."""
    host_path = _HOST_DATA / rel
    if host_path.exists():
        return host_path
    return Path("/app") / rel


def _git_dir() -> Path:
    """Devuelve la ruta del `.git` (host preferido, si no el del container)."""
    candidates = [_HOST_DATA / ".git", Path("/app/.git"), Path(".git")]
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


def _run(cmd: list[str], timeout: float = 6.0) -> str:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        out = (result.stdout or "") + (result.stderr or "")
        return out.strip()
    except subprocess.TimeoutExpired:
        return f"❌ timeout ({timeout}s)"
    except FileNotFoundError:
        return f"❌ comando no existe: {cmd[0]}"
    except Exception as e:
        return f"❌ error: {e}"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _tail_file(path: Path, n: int = 60) -> str:
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:]).strip()
    except FileNotFoundError:
        return ""
    except Exception as e:
        return f"❌ {e}"


def _git_log_oneline() -> dict:
    """Devuelve info del HEAD local (lee `.git` directamente; sin subprocess
    si es posible para reducir latencia)."""
    git_dir = _git_dir()
    out: dict = {"sha": None, "sha_short": None, "message": None, "date": None}
    if not git_dir.exists():
        return out
    # Vía subprocess (más fiable que parsear .git/HEAD manualmente).
    git = shutil.which("git")
    if git:
        result = _run([git, f"--git-dir={git_dir}", "log", "-1", "--format=%H%n%h%n%ci%n%s"], timeout=3)
        lines = result.splitlines()
        if len(lines) >= 4 and not result.startswith("❌"):
            out["sha"] = lines[0]
            out["sha_short"] = lines[1]
            out["date"] = lines[2]
            out["message"] = lines[3]
    return out


def _services_status() -> dict[str, str]:
    """Estado de los servicios del host. Solo funciona si `systemctl` es
    accesible desde dentro del container — normalmente NO lo es. En ese
    caso devolvemos {svc: "unknown"}."""
    svcs = ["tiktok-factory", "tiktok-webhook", "gdrive-mount"]
    out: dict[str, str] = {svc: "unknown" for svc in svcs}
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return out
    for svc in svcs:
        res = _run([systemctl, "is-active", svc], timeout=3)
        out[svc] = (res or "unknown").strip().splitlines()[0][:32]
    return out


def _disk_summary() -> dict:
    """Espacio libre en disco. Usa `shutil.disk_usage` para no depender de `df`."""
    try:
        usage = shutil.disk_usage("/")
        return {
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb": round(usage.used / (1024**3), 1),
            "free_gb": round(usage.free / (1024**3), 1),
            "used_pct": round(usage.used / usage.total * 100, 1) if usage.total else 0.0,
        }
    except Exception as e:
        return {"error": str(e)}


def _queue_counts() -> dict[str, int]:
    """Conteos de la cola leyendo `temp_work/queue_state.json`."""
    qpath = _host_or_local("temp_work/queue_state.json")
    out = {"total": 0, "pending": 0, "running": 0,
           "completed": 0, "failed": 0, "cancelled": 0}
    data = _read_json(qpath)
    if not data:
        return out
    for j in data.get("jobs", []):
        out["total"] += 1
        s = j.get("status", "")
        if s in out:
            out[s] += 1
    return out


def _version_label() -> str:
    """Lee `VERSION` del repo (escrito por `deploy_safe.sh` al hacer push).
    Fallback al short sha del HEAD. Último recurso: "dev"."""
    for cand in (_HOST_DATA / "VERSION", Path("/app/VERSION"), Path("VERSION")):
        try:
            v = cand.read_text(encoding="utf-8").strip()
            if v:
                return v
        except Exception:
            continue
    git = _git_log_oneline()
    return git.get("sha_short") or "dev"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
# Cache módulo — diagnostics_summary corre subprocess (git log) + systemctl
# + psutil. Cada call ~1-2s en local. La sidebar lo pide cada 30s desde
# cada cliente. 10s TTL = la 2ª navegación dentro de ese windows es
# instantánea sin perder reactividad.
_DIAG_CACHE_TTL = 10.0
_diag_cache: dict[str, tuple[float, dict]] = {}


@router.get("/summary")
def diagnostics_summary() -> dict:
    """Snapshot único para el panel de la UI. Combina:
    servicios + git + deploy + cola + disco + versión."""
    now = time.time()
    cached = _diag_cache.get("summary")
    if cached and now - cached[0] < _DIAG_CACHE_TTL:
        return cached[1]
    deploy_status = _read_json(_host_or_local("temp_work/deploy_status.json")) or {}
    result = {
        "version": _version_label(),
        "services": _services_status(),
        "git": _git_log_oneline(),
        "deploy": deploy_status,
        "queue": _queue_counts(),
        "disk": _disk_summary(),
    }
    _diag_cache["summary"] = (now, result)
    return result


@router.get("/deploy")
def diagnostics_deploy(tail: int = 80) -> dict:
    """Estado del último deploy + tail del `deploy.log`."""
    status = _read_json(_host_or_local("temp_work/deploy_status.json")) or {}
    log_text = _tail_file(_host_or_local("logs/deploy.log"), n=tail)
    return {"status": status, "log_tail": log_text}


# ---------------------------------------------------------------------------
# Chivato de cierres de la app
# ---------------------------------------------------------------------------
# La APK "se cierra sola" y desde el servidor NO se puede saber por qué: cuando
# Chrome muere no manda nada. Lo único que queda es que la app, al arrancar,
# cuente cómo terminó la vez anterior — y para eso hay que apuntarlo aquí.
#
# Lo que de verdad se quiere distinguir son tres cosas que se confunden entre
# sí y piden arreglos opuestos:
#   · murió con la app EN PANTALLA        → algo la revienta (memoria, un error)
#   · murió con la app EN SEGUNDO PLANO   → Android matando el proceso
#   · el operador la cerró él             → no hay nada que arreglar
#
# Se guarda en memoria y en el log. No va a Redis a propósito: son cuatro datos
# de depuración de una sola persona, no un histórico que valga la pena persistir.
_CIERRES: list[dict] = []
_MAX_CIERRES = 200


def _fichero_cierres() -> Path:
    """Dónde se guardan los avisos: al lado del estado de la cola.

    Ese directorio es un VOLUMEN de Docker, así que sobrevive al rebuild del
    contenedor — que es justo lo que hacía falta: los avisos vivían solo en
    memoria y un deploy se llevó por delante el histórico entero de cierres.
    (`logs/` del host no vale: está montado en solo lectura.)
    """
    base = Path("/app/temp_work")
    if not base.is_dir():
        base = Path(__file__).resolve().parents[3] / "temp_work"
    base.mkdir(parents=True, exist_ok=True)
    return base / "chivato_cierres.jsonl"


def _guardar_cierre(evento: dict) -> None:
    try:
        f = _fichero_cierres()
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(evento, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("no se pudo guardar el chivato: %s", e)


def _leer_cierres(tail: int) -> list[dict]:
    try:
        f = _fichero_cierres()
        if not f.is_file():
            return []
        lineas = f.read_text(encoding="utf-8").splitlines()[-max(1, tail):]
    except OSError:
        return []
    salida = []
    for linea in lineas:
        try:
            salida.append(json.loads(linea))
        except json.JSONDecodeError:
            continue
    return salida


@router.post("/cliente")
def diagnostics_cliente(evento: dict) -> dict:
    """Recibe un aviso del navegador (cierre anormal o error suelto).

    Nunca falla: si el chivato se rompiera y devolviera un 500, la app pasaría
    a reintentar en bucle justo cuando ya va mal.
    """
    try:
        evento = {k: v for k, v in list(evento.items())[:20]}
        evento["recibido"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _CIERRES.append(evento)
        del _CIERRES[:-_MAX_CIERRES]
        _guardar_cierre(evento)
        logger.info("chivato cliente | %s", json.dumps(evento, ensure_ascii=False)[:800])
    except Exception as e:  # noqa: BLE001
        logger.warning("chivato cliente ilegible: %s", e)
    return {"ok": True}


@router.get("/cliente")
def diagnostics_cliente_listar(tail: int = 50) -> dict:
    """Lo que ha ido contando la app. Ahora se guarda en fichero, así que
    aguanta reinicios y deploys: sirve para ver el patrón de varios días, no
    solo el problema en caliente."""
    guardados = _leer_cierres(tail)
    if not guardados:
        return {"items": _CIERRES[-tail:], "total": len(_CIERRES)}
    return {"items": guardados, "total": len(guardados)}


@router.get("/app-logs")
def diagnostics_app_logs(tail: int = 100) -> dict:
    """Tail del log de la aplicación. Lee `logs/app.log` si existe; si no,
    intenta `journalctl` solo si está disponible."""
    log_text = _tail_file(_host_or_local("logs/app.log"), n=tail)
    if log_text:
        return {"source": "file", "log_tail": log_text}
    journalctl = shutil.which("journalctl")
    if journalctl:
        out = _run(
            [journalctl, "-u", "tiktok-factory", "-n", str(tail), "--no-pager",
             "--output=short-iso"],
            timeout=8,
        )
        return {"source": "journalctl", "log_tail": out}
    return {"source": "none", "log_tail": ""}
