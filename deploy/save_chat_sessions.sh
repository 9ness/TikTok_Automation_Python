#!/usr/bin/env bash
#
# save_chat_sessions.sh — snapshot de las sesiones `claude --resume UUID`
# vivas en tmux ahora mismo (los chats "Conectado" en la app Claude).
#
# Guarda en `~/.claude/remote_state/active_chats.jsonl` una línea por chat
# con la info necesaria para re-spawnearla al arrancar:
#     {"uuid":"...", "cwd":"...", "tmux_name":"rc_..."}
#
# Uso:
#   bash deploy/save_chat_sessions.sh            # snapshot ahora
#   watch -n 60 bash deploy/save_chat_sessions.sh  # actualizar periódicamente
#
# El servicio `claude-restore-sessions.service` lee este archivo al bootear.
#
set -uo pipefail

STATE_DIR="${HOME}/.claude/remote_state"
STATE_FILE="${STATE_DIR}/active_chats.jsonl"
TMP="${STATE_FILE}.tmp"

mkdir -p "$STATE_DIR"
: > "$TMP"

count=0
# Enumeramos procesos `claude --resume UUID`. Excluimos los tmux que
# envuelven al claude (su argv también contiene "claude --resume UUID"
# pero el binario real es tmux, no claude).
while read -r pid; do
  [[ -z "$pid" ]] && continue
  # Solo aceptamos si el binario real es el CLI de Claude, no tmux ni bash
  # (ambos aparecen en pgrep por tener "claude --resume" en su argv).
  # El CLI de Claude Code vive en ~/.local/share/claude/versions/X.Y.Z.
  exe=$(readlink "/proc/${pid}/exe" 2>/dev/null)
  case "$exe" in
    */claude/versions/*|*/claude|*/node) ;;
    *) continue ;;
  esac
  # Extraer UUID del cmdline.
  uuid=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null \
          | grep -oP -- '--resume \K[a-f0-9-]{36}' | head -1)
  [[ -z "$uuid" ]] && continue
  cwd=$(readlink "/proc/${pid}/cwd" 2>/dev/null || echo "")
  [[ -z "$cwd" ]] && continue
  # Nombre tmux estándar del backend: rc_<uuid-sin-dashes-primeros-16>.
  tmux_name="rc_${uuid//-/}"
  tmux_name="${tmux_name:0:19}"  # rc_ + 16 chars = 19
  # Escapamos strings simples con python para robustez.
  python3 -c "
import json
print(json.dumps({'uuid':'${uuid}', 'cwd':'${cwd}', 'tmux_name':'${tmux_name}'}))
" >> "$TMP"
  count=$((count + 1))
done < <(pgrep -f "claude --resume" 2>/dev/null)

# Mueve atómico (no queremos archivo a medias si otro proceso lee).
mv -f "$TMP" "$STATE_FILE"

echo "[save_chat_sessions] ${count} sesión(es) guardada(s) en ${STATE_FILE}"
[[ $count -gt 0 ]] && cat "$STATE_FILE"
