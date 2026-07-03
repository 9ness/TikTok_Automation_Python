#!/usr/bin/env bash
#
# restore_chat_sessions.sh — re-spawnea las sesiones `claude --resume UUID`
# guardadas por `save_chat_sessions.sh`.
#
# Reproduce el mismo comando tmux que usa el backend Remote Control:
#     tmux new-session -d -s rc_<uuid16> -x 200 -y 50 -c <cwd> \
#         claude --resume <uuid> --permission-mode acceptEdits \
#         'Reconectado tras reinicio del server. Responde solo 'ok'.'
#
# Idempotente: si ya hay una tmux session con ese nombre, la salta.
#
# Uso:
#   bash deploy/restore_chat_sessions.sh          # restaura todo
#   bash deploy/restore_chat_sessions.sh --dry    # solo muestra qué haría
#
# Llamado automáticamente por `claude-restore-sessions.service` al bootear.
#
set -uo pipefail

STATE_FILE="${HOME}/.claude/remote_state/active_chats.jsonl"
CLAUDE_BIN="${CLAUDE_BIN:-${HOME}/.local/bin/claude}"
DRY=0
[[ "${1:-}" == "--dry" ]] && DRY=1

if [[ ! -f "$STATE_FILE" ]]; then
  echo "[restore_chat_sessions] no hay estado guardado (${STATE_FILE}) — nada que restaurar."
  exit 0
fi
if [[ ! -x "$CLAUDE_BIN" ]]; then
  echo "[restore_chat_sessions] ⚠️ Claude CLI no encontrado en ${CLAUDE_BIN}"
  exit 1
fi
if ! command -v tmux >/dev/null 2>&1; then
  echo "[restore_chat_sessions] ⚠️ tmux no está instalado"
  exit 1
fi

INITIAL_PROMPT='Reconectado tras reinicio del server. Responde solo '\''ok'\'' y espera mi siguiente mensaje; no edites ni ejecutes nada.'

restored=0
skipped=0
failed=0

while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  uuid=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('uuid',''))" "$line" 2>/dev/null)
  cwd=$(python3  -c "import json,sys; print(json.loads(sys.argv[1]).get('cwd',''))"  "$line" 2>/dev/null)
  name=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('tmux_name',''))" "$line" 2>/dev/null)
  if [[ -z "$uuid" || -z "$cwd" || -z "$name" ]]; then
    echo "[restore_chat_sessions] skip línea inválida: $line"
    skipped=$((skipped + 1)); continue
  fi
  if [[ ! -d "$cwd" ]]; then
    echo "[restore_chat_sessions] skip ${name}: cwd '${cwd}' no existe"
    skipped=$((skipped + 1)); continue
  fi
  # Ya existe una sesión con ese nombre → probablemente ya la respawnió el
  # backend o la snapshot está obsoleta. No la duplicamos.
  if tmux has-session -t "$name" 2>/dev/null; then
    echo "[restore_chat_sessions] skip ${name}: ya vive"
    skipped=$((skipped + 1)); continue
  fi
  if [[ $DRY -eq 1 ]]; then
    echo "[restore_chat_sessions] (dry) tmux new -d -s ${name} -c ${cwd} ${CLAUDE_BIN} --resume ${uuid}"
    restored=$((restored + 1)); continue
  fi
  # Spawn tmux idéntico al que usa el backend Remote Control (mismo tamaño,
  # mismo permission-mode, mismo initial prompt style).
  if tmux new-session -d -s "$name" -x 200 -y 50 -c "$cwd" \
        "$CLAUDE_BIN" --resume "$uuid" --permission-mode acceptEdits "$INITIAL_PROMPT"; then
    echo "[restore_chat_sessions] ✅ restaurada ${name} (uuid ${uuid:0:8}… en ${cwd})"
    restored=$((restored + 1))
  else
    echo "[restore_chat_sessions] ❌ falló ${name}"
    failed=$((failed + 1))
  fi
done < "$STATE_FILE"

echo "[restore_chat_sessions] resumen: ${restored} restauradas · ${skipped} saltadas · ${failed} fallidas"
