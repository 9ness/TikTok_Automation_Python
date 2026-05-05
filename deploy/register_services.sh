#!/usr/bin/env bash
#
# register_services.sh — Copia las plantillas systemd a /etc/systemd/system,
# las habilita y arranca.
#
# Ejecuta como root:
#   sudo bash deploy/register_services.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
   echo "Este script debe ejecutarse con sudo." >&2
   exit 1
fi

APP_USER="nebulabsai"
APP_DIR="/home/${APP_USER}/TikTok_Automation_Python"
TEMPLATES="${APP_DIR}/deploy/systemd"
SYSTEMD_DIR="/etc/systemd/system"

GREEN='\033[0;32m'
NC='\033[0m'
log() { echo -e "${GREEN}[register]${NC} $1"; }

# Verificaciones previas
if [[ ! -d "$APP_DIR" ]]; then
    echo "ERROR: $APP_DIR no existe. ¿Clonaste el repo?" >&2
    exit 1
fi

if ! id "$APP_USER" &>/dev/null; then
    echo "ERROR: usuario $APP_USER no existe. Ejecuta setup.sh primero." >&2
    exit 1
fi

# Comprobar que rclone está configurado con remote 'gdrive'
if ! sudo -u "$APP_USER" rclone listremotes | grep -q '^gdrive:$'; then
    echo "ERROR: rclone no tiene remote 'gdrive' configurado para el usuario $APP_USER." >&2
    echo "       Ejecuta antes: su - $APP_USER -c 'rclone config'" >&2
    exit 1
fi

# Crear directorio del mount (si no existe)
mkdir -p "/home/${APP_USER}/gdrive"
chown "${APP_USER}:${APP_USER}" "/home/${APP_USER}/gdrive"

# Asegurar permisos del .env
if [[ -f "${APP_DIR}/.env" ]]; then
    chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
fi

# Hacer ejecutables los scripts shell
chmod +x "${APP_DIR}/deploy/sync_outputs.sh"
chmod +x "${APP_DIR}/deploy/setup.sh"
chmod +x "${APP_DIR}/deploy/install_app.sh"

# 1. Copiar plantillas
log "Copiando plantillas systemd…"
for unit in tiktok-factory.service gdrive-mount.service drive-sync.service drive-sync.timer; do
    cp "${TEMPLATES}/${unit}" "${SYSTEMD_DIR}/${unit}"
    log "  · ${unit}"
done

# 2. Recargar systemd y habilitar
log "Recargando daemon systemd…"
systemctl daemon-reload

log "Habilitando + arrancando gdrive-mount…"
systemctl enable --now gdrive-mount.service
sleep 5

# Verificar mount
if ! mountpoint -q "/home/${APP_USER}/gdrive"; then
    echo "ERROR: el mount de Drive no está activo. Revisa: journalctl -u gdrive-mount -n 50" >&2
    exit 1
fi
log "  ✅ Drive montado en /home/${APP_USER}/gdrive"

log "Habilitando + arrancando drive-sync.timer (sync cada 60s)…"
systemctl enable --now drive-sync.timer

log "Habilitando + arrancando tiktok-factory (Streamlit)…"
systemctl enable --now tiktok-factory.service

# Status check
sleep 3
if systemctl is-active --quiet tiktok-factory.service; then
    log "  ✅ Streamlit corriendo en http://127.0.0.1:8501"
else
    echo "WARN: tiktok-factory no está activo. Logs: journalctl -u tiktok-factory -n 50" >&2
fi

cat <<EOF

============================================================
✅ Servicios registrados y arrancados.
============================================================

Comandos útiles:

  Ver estado:
    systemctl status tiktok-factory
    systemctl status gdrive-mount
    systemctl list-timers drive-sync.timer

  Logs en vivo:
    journalctl -u tiktok-factory -f
    journalctl -u gdrive-mount -f
    journalctl -u drive-sync -f

  Reiniciar:
    sudo systemctl restart tiktok-factory

  Parar todo (vacaciones):
    sudo systemctl stop tiktok-factory drive-sync.timer gdrive-mount

  Arrancar todo:
    sudo systemctl start gdrive-mount drive-sync.timer tiktok-factory

Próximo paso: configurar Tailscale Funnel
(ver deploy/README.md §6 — necesita login interactivo).
EOF
