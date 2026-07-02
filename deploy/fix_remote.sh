#!/usr/bin/env bash
#
# fix_remote.sh — libera / reinicia el backend de "Remote Control" del chat
# web de Claude (menú Claude → botón "A la app").
#
# CONTEXTO
#   El chat web usa un Agent SDK (FastAPI) atado al host en 172.18.0.1:8765
#   (creds de la suscripción Max del host, sin API key ni coste). El control
#   remoto tiene UN SOLO slot: al pulsar "A la app" se inyecta Remote Control
#   a esa sesión. Si una sesión queda colgada ocupando el slot, el SDK entra
#   en crash-loop resumiéndola y "A la app" ya no activa remoto en otro chat
#   (síntoma: "le doy a remoto y no veo nada").
#
# QUÉ HACE
#   Sin args     → libera (stop) TODAS las sesiones marcadas remote=true (graceful).
#   <session_id> → libera solo esa sesión.
#   --restart    → reinicio duro del backend SDK (systemd si lo gestiona, si no
#                  kill + relaunch con nohup). Úsalo si el graceful no basta.
#   --status     → muestra estado del proceso y sesiones remotas activas.
#
# VARIABLES (opcionales)
#   CLAUDE_SDK_DIR       dir del venv del SDK (default: ~/.claude-sdk-test)
#   CLAUDE_CHAT_API_KEY  si el backend exige X-API-Key, ponla aquí
#   SDK_HOST / SDK_PORT  override del bind (default 172.18.0.1 / 8765)
#
# EJEMPLOS
#   bash deploy/fix_remote.sh
#   bash deploy/fix_remote.sh 85b9bed3-833d-4f4c-9b7e-0f21ef9da4f3
#   bash deploy/fix_remote.sh --restart
#
set -uo pipefail

SDK_HOST="${SDK_HOST:-172.18.0.1}"
SDK_PORT="${SDK_PORT:-8765}"
BASE="http://${SDK_HOST}:${SDK_PORT}"
SDK_DIR="${CLAUDE_SDK_DIR:-$HOME/.claude-sdk-test}"
KEY="${CLAUDE_CHAT_API_KEY:-}"

log() { echo "[fix_remote] $*"; }

# curl con header X-API-Key opcional
_curl() {
  if [[ -n "$KEY" ]]; then
    curl -s --max-time 10 -H "X-API-Key: ${KEY}" "$@"
  else
    curl -s --max-time 10 "$@"
  fi
}

_proc_pid() { pgrep -f "uvicorn app:app.*${SDK_PORT}" | head -1; }

list_remote_sessions() {
  _curl "${BASE}/claude-chat/sessions" 2>/dev/null | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    for s in d.get("sessions", []):
        if s.get("remote"):
            print(s["id"])
except Exception:
    pass
' 2>/dev/null
}

stop_session() {
  local sid="$1"
  log "liberando remoto: ${sid}"
  local out
  out=$(_curl -X POST "${BASE}/claude-chat/remote/stop" -F "session_id=${sid}" || true)
  [[ -n "$out" ]] && echo "        ↳ ${out}"
}

show_status() {
  local pid; pid=$(_proc_pid || true)
  if [[ -n "$pid" ]]; then
    log "SDK vivo (PID ${pid}) en ${BASE}"
  else
    log "SDK NO está corriendo en ${BASE}"
  fi
  log "subprocesos claude remotos:"
  pgrep -af "_bundled/claude.*--resume" | grep -v "shell-snapshots" || echo "        (ninguno)"
  local sids; sids=$(list_remote_sessions)
  if [[ -n "$sids" ]]; then
    log "sesiones remote=true según el SDK:"; echo "$sids" | sed 's/^/        /'
  else
    log "sin sesiones remote=true (o el SDK no responde)."
  fi
}

restart_sdk() {
  log "reinicio duro del backend SDK…"
  local pid unit
  pid=$(_proc_pid || true)

  # 1) ¿lo gestiona systemd? → restart limpio por la unidad.
  if [[ -n "$pid" ]]; then
    unit=$(systemctl status "$pid" 2>/dev/null | awk 'NR==1{print $2}')
  fi
  if [[ -n "${unit:-}" && "$unit" == *.service ]]; then
    log "gestionado por systemd (${unit}) → systemctl restart"
    if sudo systemctl restart "$unit"; then
      sleep 3; log "OK — $(_proc_pid && echo vivo || echo 'no arrancó, revisa journalctl')"; return 0
    fi
  fi

  # 2) fallback: kill + relaunch con nohup.
  if [[ -n "$pid" ]]; then
    log "kill ${pid}"; kill "$pid" 2>/dev/null || true; sleep 3
  fi
  if _proc_pid >/dev/null; then
    log "se relanzó solo (supervisor/systemd) — OK"; return 0
  fi
  if [[ ! -x "${SDK_DIR}/bin/uvicorn" ]]; then
    log "no encuentro ${SDK_DIR}/bin/uvicorn — exporta CLAUDE_SDK_DIR y reintenta."; return 1
  fi
  log "relanzo uvicorn desde ${SDK_DIR}"
  ( cd "$SDK_DIR" && nohup ./bin/uvicorn app:app --host "$SDK_HOST" --port "$SDK_PORT" \
      >/tmp/claude-sdk.log 2>&1 & )
  sleep 3
  if _proc_pid >/dev/null; then
    log "relanzado OK (log en /tmp/claude-sdk.log)"; return 0
  fi
  log "no arrancó — revisa /tmp/claude-sdk.log"; return 1
}

main() {
  case "${1:-}" in
    --restart) restart_sdk ;;
    --status)  show_status ;;
    -h|--help) sed -n '2,40p' "$0" | sed 's/^#\{1,\} \{0,1\}//' ;;
    "")
      local sids; sids=$(list_remote_sessions)
      if [[ -z "$sids" ]]; then
        log "no hay sesiones remotas activas según el SDK (o no responde)."
        log "si 'A la app' sigue fallando, reinicia el backend: bash $0 --restart"
        exit 0
      fi
      while IFS= read -r sid; do [[ -n "$sid" ]] && stop_session "$sid"; done <<< "$sids"
      log "hecho. Reintenta 'A la app' en el chat que quieras."
      log "si aún falla: bash $0 --restart"
      ;;
    *) stop_session "$1" ;;
  esac
}

main "$@"
