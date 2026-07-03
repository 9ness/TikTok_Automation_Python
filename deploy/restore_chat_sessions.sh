#!/usr/bin/env bash
#
# restore_chat_sessions.sh — activa Remote Control en todos los chats
# guardados por `save_chat_sessions.sh`, llamando al mismo endpoint que
# usa el botón "A la app" del frontend:
#
#     POST http://172.18.0.1:8765/remote/start
#       Form: session_id=<uuid> project=<nombre_proyecto>
#       Header: X-API-Key: <api_key del .env>
#
# El SDK internamente:
#   - kill-session rc_<uuid16>  (por si había residuo)
#   - tmux new-session -d ... claude --resume <uuid> --permission-mode acceptEdits
#   - send-keys "/remote-control" + Space + Enter → activa Remote Control
#   - captura la URL claude.ai/code/... para retorno
#
# Diferencia vs sólo re-spawnar tmux: los chats aparecen no sólo
# "Conectado" sino con **Remote Control ACTIVO** en la app Claude,
# igual que si los hubieras abierto uno por uno.
#
# Uso:
#   bash deploy/restore_chat_sessions.sh          # restaura todos (paralelo)
#   bash deploy/restore_chat_sessions.sh --dry    # solo muestra qué haría
#
# Llamado automáticamente por `claude-restore-sessions.service` al bootear.
#
set -uo pipefail

STATE_FILE="${HOME}/.claude/remote_state/active_chats.jsonl"
SDK_HOST="${SDK_HOST:-172.18.0.1}"
SDK_PORT="${SDK_PORT:-8765}"
BASE="http://${SDK_HOST}:${SDK_PORT}"
ENV_FILE="${HOME}/TikTok_Automation_Python/.env"
DRY=0
[[ "${1:-}" == "--dry" ]] && DRY=1

# Leer API_KEY del .env que usa el SDK.
API_KEY=""
if [[ -f "$ENV_FILE" ]]; then
  API_KEY=$(grep -E "^API_KEY=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'"'')
fi

if [[ ! -f "$STATE_FILE" ]]; then
  echo "[restore_chat_sessions] no hay estado (${STATE_FILE}) — nada que restaurar"
  exit 0
fi

# Espera al SDK (si estamos en boot, tarda unos segundos en estar listo).
attempts=0
while ! curl -s --max-time 3 "${BASE}/health" >/dev/null 2>&1; do
  attempts=$((attempts + 1))
  if [[ $attempts -gt 60 ]]; then
    echo "[restore_chat_sessions] ❌ SDK no responde en ${BASE} tras 60s — abort"
    exit 1
  fi
  sleep 1
done
echo "[restore_chat_sessions] SDK vivo en ${BASE} · $(cat "$STATE_FILE" | wc -l) chat(s) a restaurar"

_do_one() {
  local uuid="$1" project="$2" name="$3"
  local hdr=()
  [[ -n "$API_KEY" ]] && hdr=(-H "X-API-Key: ${API_KEY}")
  if [[ $DRY -eq 1 ]]; then
    echo "  (dry) POST ${BASE}/remote/start session_id=${uuid} project=${project}"
    return 0
  fi
  # El endpoint tarda ~24s por chat (spawn + /remote-control + captura URL).
  # `--max-time 60` deja margen si tarda más de lo normal.
  local out
  out=$(curl -s --max-time 60 -X POST "${BASE}/remote/start" \
          "${hdr[@]}" \
          -F "session_id=${uuid}" \
          -F "project=${project}" 2>&1) || true
  local ok remote url
  ok=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('ok', False))" "$out" 2>/dev/null || echo "False")
  remote=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('remote', False))" "$out" 2>/dev/null || echo "False")
  url=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('url', '') or '')" "$out" 2>/dev/null || echo "")
  if [[ "$ok" == "True" && "$remote" == "True" ]]; then
    echo "  ✅ ${name} (uuid ${uuid:0:8}… project=${project}) · ${url:-sin URL}"
  else
    echo "  ❌ ${name} · respuesta: ${out:0:200}"
  fi
}

pids=()
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  uuid=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('uuid',''))" "$line" 2>/dev/null)
  cwd=$(python3  -c "import json,sys; print(json.loads(sys.argv[1]).get('cwd',''))"  "$line" 2>/dev/null)
  name=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('tmux_name',''))" "$line" 2>/dev/null)
  # `project` es el basename del cwd si está bajo ~/proyectos/. El SDK lo
  # resuelve a ${HOME}/proyectos/<project>. Si el cwd no está bajo
  # proyectos/, pasamos vacío y el SDK usa ~/proyectos/ como cwd default.
  project=""
  if [[ "$cwd" == "$HOME/proyectos/"* ]]; then
    project=$(basename "$cwd")
  fi
  [[ -z "$uuid" ]] && continue
  # Paralelizamos: cada remote/start tarda ~24s (sleeps internos del
  # send-keys). En serie con 7 chats sería casi 3 min; en paralelo son ~30s.
  _do_one "$uuid" "$project" "$name" &
  pids+=($!)
done < "$STATE_FILE"

# Espera todas las tareas en paralelo.
fail=0
for p in "${pids[@]}"; do
  wait "$p" || fail=$((fail + 1))
done

echo "[restore_chat_sessions] terminado · ${#pids[@]} chats procesados · ${fail} fallidos"
