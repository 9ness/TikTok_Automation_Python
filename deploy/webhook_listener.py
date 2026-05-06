#!/usr/bin/env python3
"""webhook_listener.py — Servidor HTTP minimal que recibe webhooks de GitHub
y dispara `deploy_safe.sh` en background para auto-deploy.

Diseño:
- stdlib only (sin Flask) → cero dependencias, vive fuera del venv principal
- Validación HMAC-SHA256 con secret compartido (header X-Hub-Signature-256)
- Solo acepta `push` events sobre la rama `main`
- Lanza `deploy_safe.sh` como subprocess detached y responde 202 inmediato
  (GitHub no espera; el deploy puede tardar lo que tarde la cola en vaciarse)
- Logs a stdout → systemd journald

Variables de entorno requeridas (vienen del .env de la app vía systemd):
- WEBHOOK_SECRET: secret compartido con GitHub (mismo que en Settings → Webhooks)
- WEBHOOK_PORT: puerto del listener (default 9000)
- APP_DIR: raíz del repo (default /home/nebulabsai/TikTok_Automation_Python)
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


LOG = logging.getLogger("webhook")
LOG.setLevel(logging.INFO)
_h = logging.StreamHandler(sys.stdout)
_h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
LOG.addHandler(_h)


APP_DIR = os.environ.get("APP_DIR", "/home/nebulabsai/TikTok_Automation_Python")
DEPLOY_SCRIPT = os.path.join(APP_DIR, "deploy", "deploy_safe.sh")
SECRET = os.environ.get("WEBHOOK_SECRET", "").encode()
PORT = int(os.environ.get("WEBHOOK_PORT", "9000"))
ALLOWED_BRANCHES = ("main",)
MAX_BODY_BYTES = 5_000_000  # 5MB — los push payloads son pequeños, pero
                            # GitHub puede mandar hasta ~25MB en push grandes.


class WebhookHandler(BaseHTTPRequestHandler):
    # Override para que el log salga a nuestro logger (journald-friendly)
    def log_message(self, fmt, *args):
        LOG.info("%s - %s", self.client_address[0], fmt % args)

    def _json_response(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # Healthcheck simple
        if self.path == "/health":
            self._json_response(200, {"status": "ok"})
            return
        if self.path == "/version":
            # Lee deploy_status.json (escrito por deploy_safe.sh) o cae a git
            try:
                import sys
                sys.path.insert(0, APP_DIR)
                from src.deploy_status import get_status
                self._json_response(200, get_status())
            except Exception as e:
                self._json_response(500, {"error": str(e)})
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != "/deploy":
            self.send_error(404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return
        if content_length > MAX_BODY_BYTES:
            self.send_error(413, "Payload too large")
            return

        body = self.rfile.read(content_length)

        # 1. HMAC validation
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

        # 2. Tipo de evento
        event = self.headers.get("X-GitHub-Event", "")
        if event == "ping":
            LOG.info("ping de GitHub OK (config webhook validada)")
            self._json_response(200, {"status": "pong"})
            return
        if event != "push":
            LOG.info(f"Evento '{event}' ignorado")
            self._json_response(200, {"status": "ignored", "reason": "not push"})
            return

        # 3. Parse payload + filtro de rama
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

        # 4. Disparar deploy en background y responder 202 inmediato
        head_sha = (payload.get("head_commit") or {}).get("id", "?")[:8]
        pusher = (payload.get("pusher") or {}).get("name", "?")
        LOG.info(f"✅ Push validado: {branch} @ {head_sha} por {pusher} — lanzando deploy_safe.sh")
        try:
            subprocess.Popen(
                ["/bin/bash", DEPLOY_SCRIPT],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                cwd=APP_DIR,
            )
        except Exception as e:
            LOG.error(f"No pude lanzar deploy: {e}")
            self.send_error(500, "Deploy launch failed")
            return

        self._json_response(202, {
            "status": "deploy_started",
            "head": head_sha,
            "pusher": pusher,
        })


def main():
    if not SECRET:
        LOG.error("WEBHOOK_SECRET no definido en environment. Sal y configura.")
        sys.exit(1)
    if not os.path.exists(DEPLOY_SCRIPT):
        LOG.error(f"Script de deploy no existe: {DEPLOY_SCRIPT}")
        sys.exit(1)

    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    LOG.info(f"Webhook listener arrancado en 0.0.0.0:{PORT}")
    LOG.info("Endpoints:")
    LOG.info("  POST /deploy   (GitHub push events, requiere X-Hub-Signature-256)")
    LOG.info("  GET  /health   (healthcheck)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Parando listener…")
        server.shutdown()


if __name__ == "__main__":
    main()
