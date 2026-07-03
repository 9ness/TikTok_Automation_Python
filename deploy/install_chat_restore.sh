#!/usr/bin/env bash
#
# install_chat_restore.sh — instala systemd units para snapshot + restore
# automático de las sesiones tmux `claude --resume UUID` (los chats
# "Conectado" de la app Claude).
#
# Idempotente: si los units ya están, hace `daemon-reload` y sigue.
# Requiere sudo (los units viven en /etc/systemd/system/).
#
# Uso:
#   sudo bash deploy/install_chat_restore.sh
#
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SYSTEMD_SRC="${REPO_DIR}/deploy/systemd"
TARGET="/etc/systemd/system"

if [[ $EUID -ne 0 ]]; then
  echo "❌ Este script requiere sudo (instala systemd units en /etc/systemd/system/)."
  echo "   Ejecuta:  sudo bash $0"
  exit 1
fi

log() { echo "[install_chat_restore] $*"; }

units=(
  "claude-save-sessions.service"
  "claude-save-sessions.timer"
  "claude-restore-sessions.service"
)

log "copiando units → ${TARGET}"
for u in "${units[@]}"; do
  src="${SYSTEMD_SRC}/${u}"
  if [[ ! -f "$src" ]]; then
    log "❌ no encontré ${src}"
    exit 1
  fi
  install -m 644 "$src" "${TARGET}/${u}"
  log "  · ${u}"
done

log "daemon-reload"
systemctl daemon-reload

log "enabling units (arranco en boot)…"
systemctl enable claude-restore-sessions.service
systemctl enable claude-save-sessions.timer

log "arrancando timer periódico ahora"
systemctl start claude-save-sessions.timer

# Snapshot inmediato para tener estado válido de ya.
log "snapshot inicial del estado actual"
sudo -u nebulabsai bash "${REPO_DIR}/deploy/save_chat_sessions.sh"

log ""
log "✅ Instalado correctamente."
log ""
log "Comprobaciones:"
log "  systemctl status claude-save-sessions.timer"
log "  systemctl list-timers claude-save-sessions.timer"
log "  cat /home/nebulabsai/.claude/remote_state/active_chats.jsonl"
log ""
log "Tras el próximo reboot / rescale:"
log "  journalctl -u claude-restore-sessions -n 30 --no-pager"
