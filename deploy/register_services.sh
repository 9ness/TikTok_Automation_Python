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

# ============================================================
# Verificaciones previas
# ============================================================
if [[ ! -d "$APP_DIR" ]]; then
    echo "ERROR: $APP_DIR no existe. ¿Clonaste el repo?" >&2
    exit 1
fi

if ! id "$APP_USER" &>/dev/null; then
    echo "ERROR: usuario $APP_USER no existe. Ejecuta setup.sh primero." >&2
    exit 1
fi

# Comprobar que rclone está configurado con remote 'gdrive' para nebulabsai
if ! sudo -u "$APP_USER" rclone listremotes | grep -q '^gdrive:$'; then
    echo "ERROR: rclone no tiene remote 'gdrive' configurado para el usuario $APP_USER." >&2
    echo "       Ejecuta antes: su - $APP_USER -c 'rclone config'" >&2
    exit 1
fi

# ============================================================
# Pre-requisitos: directorios y archivos de log
# ============================================================
log "Preparando directorio del mount: /home/${APP_USER}/gdrive"
mkdir -p "/home/${APP_USER}/gdrive"
chown "${APP_USER}:${APP_USER}" "/home/${APP_USER}/gdrive"

log "Preparando log file: /var/log/rclone.log"
touch /var/log/rclone.log
chown "${APP_USER}:${APP_USER}" /var/log/rclone.log
chmod 644 /var/log/rclone.log

# ============================================================
# Sudoers granular para el auto-deploy
# El webhook listener (tiktok-webhook.service) corre como nebulabsai y
# necesita reiniciar tiktok-factory tras cada git pull. Le damos NOPASSWD
# SOLO para ese comando exacto — ni shell ni nada más. Defensa-en-profundidad
# por si alguien rompe el HMAC del webhook (improbable, pero por si acaso).
# ============================================================
SUDOERS_FILE="/etc/sudoers.d/${APP_USER}-deploy"
SUDOERS_TMP=$(mktemp)
cat > "$SUDOERS_TMP" <<EOF
# Auto-generado por register_services.sh — permite al webhook reiniciar
# la app sin password tras un push validado de GitHub.
${APP_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart tiktok-factory, /bin/systemctl restart tiktok-factory.service, /usr/bin/systemctl restart tiktok-factory, /usr/bin/systemctl restart tiktok-factory.service
EOF

# Validar SIEMPRE con visudo antes de mover al sistema. Si visudo falla,
# abortamos sin tocar /etc/sudoers.d/ — un sudoers roto deja al sistema
# inutilizable para sudo.
if visudo -c -f "$SUDOERS_TMP" >/dev/null; then
    install -m 0440 -o root -g root "$SUDOERS_TMP" "$SUDOERS_FILE"
    rm -f "$SUDOERS_TMP"
    log "  ✅ sudoers granular: $SUDOERS_FILE"
else
    rm -f "$SUDOERS_TMP"
    echo "ERROR: el sudoers generado falló visudo -c. Abortando." >&2
    exit 1
fi

# Permisos del .env
if [[ -f "${APP_DIR}/.env" ]]; then
    chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
fi

# Hacer ejecutables los scripts shell del repo
chmod +x "${APP_DIR}/deploy/setup.sh" 2>/dev/null || true
chmod +x "${APP_DIR}/deploy/install_app.sh" 2>/dev/null || true
chmod +x "${APP_DIR}/deploy/deploy_safe.sh" 2>/dev/null || true

# ============================================================
# 1. Copiar plantillas systemd
# ============================================================
log "Copiando plantillas systemd…"
for unit in tiktok-factory.service gdrive-mount.service tiktok-webhook.service; do
    if [[ -f "${TEMPLATES}/${unit}" ]]; then
        cp "${TEMPLATES}/${unit}" "${SYSTEMD_DIR}/${unit}"
        log "  · ${unit}"
    fi
done

# Limpiar plantillas obsoletas si existen de un despliegue anterior
for old in drive-sync.service drive-sync.timer; do
    if [[ -f "${SYSTEMD_DIR}/${old}" ]]; then
        log "  · eliminando plantilla obsoleta: ${old}"
        systemctl disable --now "${old}" 2>/dev/null || true
        rm -f "${SYSTEMD_DIR}/${old}"
    fi
done

# ============================================================
# 2. Recargar systemd y habilitar
# ============================================================
log "Recargando daemon systemd…"
systemctl daemon-reload

log "Habilitando + arrancando gdrive-mount…"
systemctl enable --now gdrive-mount.service
sleep 6

# Verificar mount
if ! mountpoint -q "/home/${APP_USER}/gdrive"; then
    echo "ERROR: el mount de Drive no está activo. Revisa: journalctl -u gdrive-mount -n 50" >&2
    exit 1
fi
log "  ✅ Drive montado en /home/${APP_USER}/gdrive"

log "Habilitando + arrancando tiktok-factory (Streamlit)…"
systemctl enable --now tiktok-factory.service

# Status check
sleep 3
if systemctl is-active --quiet tiktok-factory.service; then
    log "  ✅ Streamlit corriendo en http://127.0.0.1:8501"
else
    echo "WARN: tiktok-factory no está activo. Logs: journalctl -u tiktok-factory -n 50" >&2
fi

# ============================================================
# Webhook listener (auto-deploy desde GitHub)
# Solo se arranca si WEBHOOK_SECRET está definido en el .env. Si no,
# el listener saldría con error inmediato y systemd entraría en loop.
# ============================================================
if [[ -f "${APP_DIR}/.env" ]] && grep -qE '^WEBHOOK_SECRET=.+' "${APP_DIR}/.env"; then
    log "Habilitando + arrancando tiktok-webhook (auto-deploy)…"
    systemctl enable --now tiktok-webhook.service
    sleep 2
    if systemctl is-active --quiet tiktok-webhook.service; then
        log "  ✅ Webhook listener escuchando en :9000"
    else
        echo "WARN: tiktok-webhook no está activo. Logs: journalctl -u tiktok-webhook -n 30" >&2
    fi
else
    log "ℹ️  WEBHOOK_SECRET no encontrado en .env — saltando tiktok-webhook"
    log "    Para activar auto-deploy: añade WEBHOOK_SECRET=<token> al .env y"
    log "    ejecuta: sudo systemctl enable --now tiktok-webhook"
fi

cat <<EOF

============================================================
✅ Servicios registrados y arrancados.
============================================================

Comandos útiles:

  Ver estado:
    systemctl status tiktok-factory tiktok-webhook gdrive-mount

  Logs en vivo:
    journalctl -u tiktok-factory -f      # streamlit
    journalctl -u tiktok-webhook -f      # auto-deploy webhook
    journalctl -u gdrive-mount -f        # rclone mount
    tail -f /var/log/rclone.log
    tail -f /home/${APP_USER}/TikTok_Automation_Python/logs/deploy.log

  Reiniciar la app:
    sudo systemctl restart tiktok-factory

  Parar todo (vacaciones):
    sudo systemctl stop tiktok-factory tiktok-webhook gdrive-mount

  Arrancar todo:
    sudo systemctl start gdrive-mount tiktok-factory tiktok-webhook

Próximo paso: configurar Tailscale Funnel
(ver deploy/README.md — necesita login interactivo).
EOF
