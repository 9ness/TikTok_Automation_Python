#!/usr/bin/env python3
"""webhook_listener.py — Servidor HTTP minimal que:

1) **Recibe webhooks de GitHub** (HMAC-SHA256) y dispara `deploy_safe.sh`.
2) **Expone endpoints autenticados de admin** para el panel "Deploy" del
   frontend: deploy manual, rebuild docker, restart containers, tail de
   logs, lista de containers, estado del sistema.

Diseño:
- stdlib only (sin Flask) → cero dependencias, vive fuera del venv principal
- Validación HMAC-SHA256 con secret compartido (header X-Hub-Signature-256)
  para webhook GitHub
- Auth `X-API-Key` (mismo valor que `API_KEY` de la app) para endpoints admin
- Lanza `deploy_safe.sh` como subprocess detached y responde 202 inmediato
  (GitHub no espera; el deploy puede tardar lo que tarde la cola en vaciarse)
- Logs a stdout → systemd journald

Variables de entorno requeridas (vienen del .env de la app vía systemd):
- WEBHOOK_SECRET: secret compartido con GitHub (mismo que en Settings → Webhooks)
- WEBHOOK_PORT: puerto del listener (default 9000)
- APP_DIR: raíz del repo (default /home/nebulabsai/TikTok_Automation_Python)
- API_KEY: token compartido con la app — autentica el panel admin del frontend

Endpoints:
  GitHub:
    POST /deploy                  — webhook GitHub (HMAC)
    GET  /health                  — healthcheck simple
    GET  /version                 — estado del último deploy
  Admin (requieren `X-API-Key`):
    POST /admin/deploy            — git pull + rebuild
    POST /admin/docker/rebuild    — docker compose up -d --build api web
    POST /admin/docker/restart    — docker compose restart {service}
    GET  /admin/docker/ps         — docker compose ps (parseado)
    GET  /admin/deploy/log?n=200  — tail de logs/deploy.log
    GET  /admin/system            — uptime + disk + mem
"""

import hashlib
import hmac
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


LOG = logging.getLogger("webhook")
LOG.setLevel(logging.INFO)
_h = logging.StreamHandler(sys.stdout)
_h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
LOG.addHandler(_h)


APP_DIR = os.environ.get("APP_DIR", "/home/nebulabsai/TikTok_Automation_Python")
DEPLOY_SCRIPT = os.path.join(APP_DIR, "deploy", "deploy_safe.sh")
# Script de rescate del backend "Remote Control" del chat web de Claude
# (Agent SDK en :8765). Lo lanza el panel Settings → Deploy. El listener
# corre como `nebulabsai` (mismo user dueño del uvicorn del SDK) → puede
# reiniciarlo sin sudo (kill + relaunch) o liberar el slot colgado.
FIX_REMOTE_SCRIPT = os.path.join(APP_DIR, "deploy", "fix_remote.sh")
DEPLOY_LOG = os.path.join(APP_DIR, "logs", "deploy.log")
SECRET = os.environ.get("WEBHOOK_SECRET", "").encode()
ADMIN_API_KEY = os.environ.get("API_KEY", "")  # mismo de la app
PORT = int(os.environ.get("WEBHOOK_PORT", "9000"))
ALLOWED_BRANCHES = ("main",)
MAX_BODY_BYTES = 5_000_000

# Whitelist de servicios que se pueden reiniciar vía /admin/docker/restart.
# Cualquier otro nombre se rechaza con 400 — evita que un atacante con la
# API key reinicie servicios arbitrarios del docker-compose del host.
ALLOWED_SERVICES = {"api", "web", "caddy"}


def _run(cmd: list[str], timeout: int = 30, cwd: str | None = None) -> tuple[int, str, str]:
    """Ejecuta un comando capturando salida. Devuelve (rc, stdout, stderr)."""
    try:
        p = subprocess.run(
            cmd, cwd=cwd or APP_DIR, capture_output=True, timeout=timeout, text=True,
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout tras {timeout}s"
    except Exception as e:
        return -2, "", str(e)


def _spawn_background(cmd: list[str], logfile: str | None = None) -> None:
    """Lanza un proceso detached. Si `logfile` se provee, redirige stdout+
    stderr ahí; si no, a /dev/null."""
    if logfile:
        f = open(logfile, "ab", buffering=0)
        subprocess.Popen(
            cmd, stdout=f, stderr=f, start_new_session=True, cwd=APP_DIR,
        )
    else:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            cwd=APP_DIR,
        )


def _tail_file(path: str, n: int = 200) -> str:
    if not os.path.isfile(path):
        return ""
    try:
        # Leer las últimas ~64KB es suficiente para 200 líneas razonables.
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > 65536:
                f.seek(-65536, 2)
                f.readline()  # descartar línea parcial
            data = f.read()
        return "\n".join(data.decode("utf-8", errors="replace").splitlines()[-n:])
    except OSError as e:
        return f"<error leyendo {path}: {e}>"


class WebhookHandler(BaseHTTPRequestHandler):
    # Override para que el log salga a nuestro logger (journald-friendly)
    def log_message(self, fmt, *args):
        LOG.info("%s - %s", self.client_address[0], fmt % args)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _json_response(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # Mismo CORS que la API principal — Caddy reescribe Origin pero por
        # si alguna ruta del frontend llama directo en dev.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.end_headers()
        self.wfile.write(body)

    def _check_admin_auth(self) -> bool:
        """Auth para endpoints `/admin/*`. Compara `X-API-Key` (o `?api_key=`
        en query) con `API_KEY` del entorno. Si `API_KEY` está vacía,
        rechaza TODO (no modo dev permisivo en admin)."""
        if not ADMIN_API_KEY:
            LOG.warning("API_KEY no configurada — admin desactivado")
            self._json_response(503, {"error": "admin disabled (no API_KEY)"})
            return False
        header = self.headers.get("X-API-Key", "")
        if not header:
            # Fallback: query param para clientes que no pueden setear headers.
            qs = parse_qs(urlparse(self.path).query)
            header = (qs.get("api_key") or [""])[0]
        if header != ADMIN_API_KEY:
            self._json_response(401, {"error": "invalid api key"})
            return False
        return True

    def _parse_json_body(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            return None
        if n <= 0:
            return {}
        if n > MAX_BODY_BYTES:
            return None
        raw = self.rfile.read(n)
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return None

    # ------------------------------------------------------------------
    # CORS preflight
    # ------------------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.end_headers()

    # ------------------------------------------------------------------
    # GET routes
    # ------------------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/health":
            self._json_response(200, {"status": "ok"})
            return

        if path == "/version":
            try:
                sys.path.insert(0, APP_DIR)
                from src.deploy_status import get_status
                self._json_response(200, get_status())
            except Exception as e:
                self._json_response(500, {"error": str(e)})
            return

        # -------- Admin --------
        if path == "/admin/docker/ps":
            if not self._check_admin_auth():
                return
            rc, out, err = _run(["docker", "compose", "ps", "--format", "json"], timeout=15)
            # `docker compose ps --format json` puede devolver un JSON array
            # o NDJSON según versión. Normalizamos a list[dict].
            containers: list[dict] = []
            if rc == 0 and out.strip():
                stripped = out.strip()
                if stripped.startswith("["):
                    try:
                        containers = json.loads(stripped)
                    except json.JSONDecodeError:
                        containers = []
                else:
                    for line in stripped.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            containers.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            self._json_response(200 if rc == 0 else 500, {
                "ok": rc == 0,
                "containers": containers,
                "raw_error": err if rc != 0 else None,
            })
            return

        if path == "/admin/deploy/log":
            if not self._check_admin_auth():
                return
            qs = parse_qs(urlparse(self.path).query)
            try:
                n = max(1, min(2000, int((qs.get("n") or ["200"])[0])))
            except ValueError:
                n = 200
            self._json_response(200, {"log": _tail_file(DEPLOY_LOG, n=n)})
            return

        if path == "/admin/system":
            if not self._check_admin_auth():
                return
            self._json_response(200, _system_status())
            return

        if path == "/admin/status":
            if not self._check_admin_auth():
                return
            self._json_response(200, _smart_status())
            return

        if path == "/admin/claude-sdk/status":
            self._handle_claude_sdk("status")
            return

        self.send_error(404)

    # ------------------------------------------------------------------
    # POST routes
    # ------------------------------------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path

        # GitHub webhook
        if path == "/deploy":
            self._handle_github_webhook()
            return

        # Admin
        if path == "/admin/deploy":
            self._handle_manual_deploy()
            return

        if path == "/admin/docker/rebuild":
            self._handle_docker_rebuild()
            return

        if path == "/admin/docker/restart":
            self._handle_docker_restart()
            return

        if path == "/admin/claude-sdk/restart":
            self._handle_claude_sdk("restart")
            return

        if path == "/admin/claude-sdk/free":
            self._handle_claude_sdk("free")
            return

        self.send_error(404)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _handle_github_webhook(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return
        if content_length > MAX_BODY_BYTES:
            self.send_error(413, "Payload too large")
            return

        body = self.rfile.read(content_length)

        if not SECRET:
            LOG.error("WEBHOOK_SECRET no configurado — rechazando")
            self.send_error(500, "Server misconfigured")
            return

        sig_header = self.headers.get("X-Hub-Signature-256", "")
        if not sig_header.startswith("sha256="):
            LOG.warning("Firma ausente o mal formada — rechazado")
            self.send_error(401, "Missing signature")
            return
        expected = sig_header[len("sha256="):]
        actual = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, actual):
            LOG.warning("HMAC inválido — push rechazado")
            self.send_error(401, "Invalid signature")
            return

        event = self.headers.get("X-GitHub-Event", "")
        if event == "ping":
            LOG.info("ping de GitHub OK (config webhook validada)")
            self._json_response(200, {"status": "pong"})
            return
        if event != "push":
            LOG.info(f"Evento '{event}' ignorado")
            self._json_response(200, {"status": "ignored", "reason": "not push"})
            return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ""
        if branch not in ALLOWED_BRANCHES:
            LOG.info(f"Push a rama '{branch}' ignorado (solo {ALLOWED_BRANCHES})")
            self._json_response(200, {"status": "ignored", "reason": "branch"})
            return

        head_sha = (payload.get("head_commit") or {}).get("id", "?")[:8]
        pusher = (payload.get("pusher") or {}).get("name", "?")
        LOG.info(f"✅ Push validado: {branch} @ {head_sha} por {pusher} — lanzando deploy_safe.sh")
        try:
            _spawn_background(["/bin/bash", DEPLOY_SCRIPT])
        except Exception as e:
            LOG.error(f"No pude lanzar deploy: {e}")
            self.send_error(500, "Deploy launch failed")
            return

        self._json_response(202, {
            "status": "deploy_started",
            "head": head_sha,
            "pusher": pusher,
        })

    def _handle_manual_deploy(self) -> None:
        """Botón "Deploy ahora" del panel admin — equivalente a un push.
        Llama a `deploy_safe.sh` en background y responde 202 inmediato."""
        if not self._check_admin_auth():
            return
        if not os.path.exists(DEPLOY_SCRIPT):
            self._json_response(500, {"error": f"script no existe: {DEPLOY_SCRIPT}"})
            return
        try:
            _spawn_background(["/bin/bash", DEPLOY_SCRIPT])
        except Exception as e:
            self._json_response(500, {"error": f"no pude lanzar deploy: {e}"})
            return
        LOG.info("🚀 Deploy manual lanzado desde panel admin")
        self._json_response(202, {"status": "deploy_started", "kind": "manual"})

    def _handle_docker_rebuild(self) -> None:
        """Rebuild explícito de containers (sin tocar git). Útil cuando
        cambias el `.env` o quieres forzar un build limpio sin esperar a
        `deploy_safe.sh`. Escribe stdout/err a `logs/deploy.log` para que
        el panel pueda mostrar el progreso."""
        if not self._check_admin_auth():
            return
        body = self._parse_json_body()
        if body is None:
            self._json_response(400, {"error": "invalid body"})
            return
        services = body.get("services") or ["api", "web"]
        services = [s for s in services if s in ALLOWED_SERVICES]
        if not services:
            self._json_response(400, {"error": "no valid services",
                                       "allowed": sorted(ALLOWED_SERVICES)})
            return
        # `--no-cache` por defecto: el botón "Rebuild forzado" del panel
        # se invoca normalmente cuando una imagen se quedó atascada con
        # layers viejas (typical: requirements.txt cambió pero el cache
        # de pip sirvió el wheel viejo). Si el caller quiere usar cache,
        # pasa `no_cache: false` en el body.
        no_cache = bool(body.get("no_cache", True))
        no_cache_flag = " --no-cache" if no_cache else ""
        services_str = " ".join(services)
        # Encadenamos build + up --force-recreate en una shell para
        # ejecutar como un solo subprocess detached. El `&&` asegura que
        # el up solo corre si el build pasa (sin imagen rota corriendo).
        shell_cmd = (
            f"docker compose build{no_cache_flag} {services_str} "
            f"&& docker compose up -d --force-recreate {services_str}"
        )
        try:
            with open(DEPLOY_LOG, "a", encoding="utf-8") as f:
                f.write(
                    f"\n===== {time.strftime('%Y-%m-%dT%H:%M:%S')} "
                    f"rebuild manual: {services_str} "
                    f"(no_cache={no_cache}) =====\n"
                )
            _spawn_background(["/bin/bash", "-c", shell_cmd], logfile=DEPLOY_LOG)
        except Exception as e:
            self._json_response(500, {"error": str(e)})
            return
        LOG.info(f"🐳 Rebuild manual lanzado: {services} (no_cache={no_cache})")
        self._json_response(
            202,
            {"status": "rebuild_started", "services": services, "no_cache": no_cache},
        )

    def _handle_docker_restart(self) -> None:
        """Restart de un container concreto SIN rebuild. Más rápido (~5s)
        que rebuild, útil para aplicar cambios de .env o desbloquear un
        container que se cuelga."""
        if not self._check_admin_auth():
            return
        body = self._parse_json_body()
        if body is None:
            self._json_response(400, {"error": "invalid body"})
            return
        service = (body.get("service") or "").strip()
        if service not in ALLOWED_SERVICES:
            self._json_response(400, {
                "error": f"service '{service}' no permitido",
                "allowed": sorted(ALLOWED_SERVICES),
            })
            return
        # Síncrono — el restart es rápido y queremos devolver el rc.
        rc, out, err = _run(
            ["docker", "compose", "restart", service], timeout=60,
        )
        LOG.info(f"🔄 restart {service} → rc={rc}")
        self._json_response(200 if rc == 0 else 500, {
            "ok": rc == 0,
            "service": service,
            "stdout": out[-500:],
            "stderr": err[-500:],
        })

    def _handle_claude_sdk(self, action: str) -> None:
        """Rescate del backend Remote Control del chat web de Claude (Agent
        SDK en :8765), fuera de Docker. Corre `deploy/fix_remote.sh`:
          - status  → estado del proceso + sesiones remotas activas
          - free    → libera (stop) los slots remotos colgados (graceful)
          - restart → reinicio duro del backend SDK
        Síncrono — devolvemos rc + salida para que el panel la muestre."""
        if not self._check_admin_auth():
            return
        if not os.path.exists(FIX_REMOTE_SCRIPT):
            self._json_response(500, {"error": f"script no existe: {FIX_REMOTE_SCRIPT}"})
            return
        arg = {"restart": "--restart", "status": "--status", "free": ""}.get(action)
        if arg is None:
            self._json_response(400, {"error": f"acción inválida: {action}"})
            return
        cmd = ["/bin/bash", FIX_REMOTE_SCRIPT]
        if arg:
            cmd.append(arg)
        rc, out, err = _run(cmd, timeout=120)
        LOG.info(f"🤖 claude-sdk {action} → rc={rc}")
        self._json_response(200 if rc == 0 else 500, {
            "ok": rc == 0,
            "action": action,
            "stdout": out[-2000:],
            "stderr": err[-1000:],
        })


def _smart_status() -> dict:
    """Snapshot inteligente para que el panel UI decida si ofrecer Deploy
    activo o "ya estás al día".

    Devuelve:
      - `current_sha`, `current_sha_short`
      - `remote_sha`, `remote_sha_short`
      - `commits_behind`: cuántos commits hay en origin/main respecto a HEAD
      - `commits_preview`: hasta 10 oneline de esos commits
      - `deploy_in_progress`: True si el lock file existe Y hay proceso vivo
      - `would_rebuild`: lista de servicios que se rebuildearían si se
        deployase AHORA (api / web / caddy / webhook). Calcula en base a
        los ficheros que cambiarían (no triggerea el deploy).
      - `last_deploy`: contenido de deploy_status.json (estado + SHA + when)
    """
    out: dict = {"timestamp": int(time.time())}

    # Fetch silencioso para tener la referencia más reciente del remoto.
    # Si falla (sin conectividad, repo sin remote), seguimos con info local.
    _run(["git", "fetch", "--quiet", "origin", "main"], timeout=15)

    rc, sha_local, _ = _run(["git", "rev-parse", "HEAD"], timeout=5)
    rc2, sha_remote, _ = _run(["git", "rev-parse", "origin/main"], timeout=5)
    sha_local = sha_local.strip() if rc == 0 else ""
    sha_remote = sha_remote.strip() if rc2 == 0 else ""
    out["current_sha"] = sha_local
    out["current_sha_short"] = sha_local[:8]
    out["remote_sha"] = sha_remote
    out["remote_sha_short"] = sha_remote[:8]

    # Commits que llegarían con un git pull
    commits_preview: list[dict] = []
    commits_behind = 0
    changed_files: list[str] = []
    if sha_local and sha_remote and sha_local != sha_remote:
        rc, count, _ = _run(
            ["git", "rev-list", "--count", f"{sha_local}..{sha_remote}"],
            timeout=5,
        )
        if rc == 0 and count.strip().isdigit():
            commits_behind = int(count.strip())
        rc, log_out, _ = _run(
            ["git", "log", "--pretty=%h\t%s\t%an",
             f"{sha_local}..{sha_remote}", "--max-count=10"],
            timeout=5,
        )
        if rc == 0:
            for line in log_out.splitlines():
                parts = line.split("\t", 2)
                if len(parts) >= 2:
                    commits_preview.append({
                        "sha": parts[0],
                        "subject": parts[1],
                        "author": parts[2] if len(parts) > 2 else "",
                    })
        rc, diff_out, _ = _run(
            ["git", "diff", "--name-only", f"{sha_local}..{sha_remote}"],
            timeout=5,
        )
        if rc == 0:
            changed_files = [f for f in diff_out.splitlines() if f]
    out["commits_behind"] = commits_behind
    out["commits_preview"] = commits_preview

    # ¿Qué se rebuildearía si se deploya ahora? — mismos patterns que el
    # `deploy_safe.sh`. Mantener sincronizado con esa lógica.
    would_rebuild: list[str] = []
    api_re = (
        "^Dockerfile\\.api$|^docker-compose\\.yml$|^requirements\\.txt$|"
        "^src/(api|editor_auto|fonts_registry\\.py|queue/(metrics|manager|models|runners|__init__)\\.py|"
        "subtitles|pronosticos|tiktok_shop|video_remover|locutor|guionista|logic|"
        "word_calibrator|text_hook|font_resolver|diagnostics|cost_tracking)"
    )
    import re as _re
    api_pat = _re.compile(api_re)
    for f in changed_files:
        if api_pat.search(f) and "api" not in would_rebuild:
            would_rebuild.append("api")
        if f.startswith("frontend/") and "web" not in would_rebuild:
            would_rebuild.append("web")
        if f in ("Caddyfile", "docker-compose.yml") and "caddy" not in would_rebuild:
            would_rebuild.append("caddy")
        if f == "deploy/webhook_listener.py" and "webhook" not in would_rebuild:
            would_rebuild.append("webhook")
    out["would_rebuild"] = would_rebuild
    out["changed_files_count"] = len(changed_files)
    out["changed_files_preview"] = changed_files[:30]

    # ¿Hay un deploy corriendo ahora mismo? El lock file existe pero
    # podría ser zombie — verificamos PID si está disponible.
    lock = "/tmp/tiktok-deploy.lock"
    in_progress = False
    if os.path.exists(lock):
        # `flock` no escribe PID por defecto, pero podemos buscar procesos
        # bash ejecutando deploy_safe.sh.
        rc, ps_out, _ = _run(
            ["pgrep", "-f", "deploy_safe.sh"], timeout=3,
        )
        in_progress = rc == 0 and bool(ps_out.strip())
    out["deploy_in_progress"] = in_progress

    # Último deploy persistido
    last_path = os.path.join(APP_DIR, "temp_work", "deploy_status.json")
    if os.path.isfile(last_path):
        try:
            with open(last_path, "r", encoding="utf-8") as f:
                out["last_deploy"] = json.load(f)
        except Exception:
            out["last_deploy"] = None
    else:
        out["last_deploy"] = None

    return out


def _system_status() -> dict:
    """Snapshot rápido del host: uptime, disco, memoria, carga."""
    out: dict = {"timestamp": int(time.time())}

    # Uptime
    try:
        with open("/proc/uptime", "r") as f:
            up = float(f.read().split()[0])
        out["uptime_seconds"] = int(up)
    except Exception:
        out["uptime_seconds"] = None

    # Disco — punto raíz "/"
    try:
        total, used, free = shutil.disk_usage("/")
        out["disk"] = {
            "total_gb": round(total / 1e9, 1),
            "used_gb": round(used / 1e9, 1),
            "free_gb": round(free / 1e9, 1),
            "used_pct": round(used / total * 100, 1) if total else None,
        }
    except Exception:
        out["disk"] = None

    # Memoria — parsea /proc/meminfo
    try:
        mem: dict[str, int] = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                k, v = line.split(":", 1)
                # valores en kB
                mem[k.strip()] = int(v.strip().split()[0]) * 1024
        total = mem.get("MemTotal", 0)
        avail = mem.get("MemAvailable", mem.get("MemFree", 0))
        out["memory"] = {
            "total_gb": round(total / 1e9, 2),
            "available_gb": round(avail / 1e9, 2),
            "used_pct": round((total - avail) / total * 100, 1) if total else None,
        }
    except Exception:
        out["memory"] = None

    # Load average
    try:
        out["load_avg"] = list(os.getloadavg())
    except Exception:
        out["load_avg"] = None

    return out


def main():
    if not SECRET:
        LOG.error("WEBHOOK_SECRET no definido en environment. Sal y configura.")
        sys.exit(1)
    if not os.path.exists(DEPLOY_SCRIPT):
        LOG.error(f"Script de deploy no existe: {DEPLOY_SCRIPT}")
        sys.exit(1)
    if not ADMIN_API_KEY:
        LOG.warning("⚠️  API_KEY no definida — endpoints /admin/* responderán 503")

    # ThreadingHTTPServer (no HTTPServer) — el single-threaded se colgaba
    # con cualquier conexión lenta/abandonada que dejaba el socket abierto,
    # bloqueando todas las requests siguientes. ThreadingHTTPServer spawnea
    # un hilo por request → las conexiones lentas no afectan al resto.
    server = ThreadingHTTPServer(("0.0.0.0", PORT), WebhookHandler)
    # Marcar los threads como daemon → se cierran limpios al shutdown.
    server.daemon_threads = True
    LOG.info(f"Webhook listener arrancado en 0.0.0.0:{PORT} (threaded)")
    LOG.info("Endpoints:")
    LOG.info("  POST /deploy                    (GitHub push events, HMAC)")
    LOG.info("  GET  /health, /version")
    LOG.info("  POST /admin/deploy              (X-API-Key)")
    LOG.info("  POST /admin/docker/rebuild      (X-API-Key)")
    LOG.info("  POST /admin/docker/restart      (X-API-Key)")
    LOG.info("  POST /admin/claude-sdk/restart  (X-API-Key)")
    LOG.info("  POST /admin/claude-sdk/free     (X-API-Key)")
    LOG.info("  GET  /admin/claude-sdk/status   (X-API-Key)")
    LOG.info("  GET  /admin/docker/ps           (X-API-Key)")
    LOG.info("  GET  /admin/deploy/log?n=200    (X-API-Key)")
    LOG.info("  GET  /admin/system              (X-API-Key)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Parando listener…")
        server.shutdown()


if __name__ == "__main__":
    main()
