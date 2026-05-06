#!/usr/bin/env bash
#
# setup.sh — Provisión inicial del VPS para TikTok Automation Python.
#
# Instala dependencias del sistema, crea usuario nebulabsai, configura
# firewall, hardeniza SSH e instala FFmpeg, Python, Redis, rclone y
# Tailscale.
#
# Uso (como root, en una sesión SSH fresca a Hetzner):
#   wget https://raw.githubusercontent.com/9ness/TikTok_Automation_Python/main/deploy/setup.sh
#   chmod +x setup.sh
#   ./setup.sh
#
# IMPORTANTE: editar APP_USER abajo si quieres otro nombre. Por defecto
# crea el usuario "nebulabsai" (minúsculas obligatorias en Debian/Ubuntu).

set -euo pipefail

# ============================================================
# Configuración (editar antes de ejecutar si hace falta)
# ============================================================
APP_USER="nebulabsai"  # Linux/Debian no permite mayúsculas por defecto en NAME_REGEX
APP_USER_PASSWORD=""  # Se rellena interactivamente

# ============================================================
# Helpers
# ============================================================
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[setup]${NC} $1"; }
warn() { echo -e "${YELLOW}[setup]${NC} $1"; }
err()  { echo -e "${RED}[setup]${NC} $1" >&2; }

if [[ $EUID -ne 0 ]]; then
   err "Este script debe ejecutarse como root. Usa: sudo ./setup.sh"
   exit 1
fi

# ============================================================
# 1. Sistema base — actualizar paquetes
# ============================================================
log "1/8 Actualizando paquetes del sistema…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq

# ============================================================
# 2. Dependencias base + FFmpeg + Python
# ============================================================
log "2/8 Instalando dependencias del sistema (puede tardar 2-3 min)…"
apt-get install -y -qq \
    ca-certificates curl wget git unzip \
    python3 python3-pip python3-venv python3-dev \
    build-essential pkg-config \
    ffmpeg \
    redis-server \
    fuse3 \
    ufw \
    htop nano vim less \
    fonts-dejavu fonts-liberation fonts-noto-color-emoji \
    libsm6 libxext6 libxrender1 libgl1 \
    imagemagick

# ttf-mscorefonts-installer (Impact, Arial, Verdana, Times, Comic Sans, Trebuchet,
# Georgia, Courier — son las fuentes que el código hardcodea como C:\Windows\Fonts\*).
# Repo "contrib" + auto-aceptar EULA de Microsoft.
add-apt-repository -y contrib 2>/dev/null || true
apt-get update -qq
echo ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true \
    | debconf-set-selections
apt-get install -y -qq ttf-mscorefonts-installer || warn "ttf-mscorefonts-installer falló — el código caerá a fallbacks DejaVu"
fc-cache -fv 2>/dev/null || true

# ImageMagick: MoviePy lo usa para algunos efectos de texto. Por defecto
# tiene una policy que bloquea lectura/escritura de @* (un viejo CVE).
# Permitimos la operación segura para que MoviePy funcione.
if [[ -f /etc/ImageMagick-6/policy.xml ]]; then
    sed -i 's/<policy domain="path" rights="none" pattern="@\*"\/>/<!-- allowed by tiktok-automation -->/' /etc/ImageMagick-6/policy.xml || true
fi

# ============================================================
# 3. Usuario de aplicación
# ============================================================
log "3/8 Creando usuario de aplicación: ${APP_USER}…"
if id "$APP_USER" &>/dev/null; then
    warn "El usuario ${APP_USER} ya existe. Saltando creación."
else
    adduser --disabled-password --gecos "" "$APP_USER"
    usermod -aG sudo "$APP_USER"
    log "Usuario ${APP_USER} creado y añadido al grupo sudo."

    # Copiar llaves SSH del root al nuevo usuario para login directo
    if [[ -f /root/.ssh/authorized_keys ]]; then
        mkdir -p "/home/${APP_USER}/.ssh"
        cp /root/.ssh/authorized_keys "/home/${APP_USER}/.ssh/"
        chown -R "${APP_USER}:${APP_USER}" "/home/${APP_USER}/.ssh"
        chmod 700 "/home/${APP_USER}/.ssh"
        chmod 600 "/home/${APP_USER}/.ssh/authorized_keys"
        log "Llaves SSH del root copiadas a ${APP_USER}."
    else
        warn "No se encontraron llaves SSH en /root/.ssh/authorized_keys."
    fi
fi

# Configurar sudoers para que el usuario pueda hacer sudo sin password
# (cómodo para administrar; si prefieres password, comenta esta línea)
SUDO_FILE="/etc/sudoers.d/${APP_USER}"
echo "${APP_USER} ALL=(ALL) NOPASSWD:ALL" > "$SUDO_FILE"
chmod 440 "$SUDO_FILE"

# ============================================================
# 4. Hardening SSH
# ============================================================
log "4/8 Hardening SSH (deshabilitando login root con password)…"
SSHD_CONFIG="/etc/ssh/sshd_config"
cp "$SSHD_CONFIG" "${SSHD_CONFIG}.bak.$(date +%Y%m%d)"
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' "$SSHD_CONFIG"
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' "$SSHD_CONFIG"
sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' "$SSHD_CONFIG"
systemctl reload ssh

# ============================================================
# 5. Firewall UFW (solo SSH)
# ============================================================
log "5/8 Configurando firewall UFW…"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 9000/tcp comment 'GitHub webhook (auto-deploy)'
# Tailscale añadirá sus reglas más adelante automáticamente
ufw --force enable

# ============================================================
# 6. Rclone (mount de Google Drive)
# ============================================================
log "6/8 Instalando rclone…"
if ! command -v rclone &>/dev/null; then
    curl -fsSL https://rclone.org/install.sh | bash
else
    log "rclone ya instalado: $(rclone version | head -1)"
fi

# Habilitar permitir 'allow_other' en fuse para que el mount sea visible
# desde otros usuarios (útil para que systemd lo vea bajo nebulabsai)
if [[ -f /etc/fuse.conf ]]; then
    sed -i 's/^#*user_allow_other/user_allow_other/' /etc/fuse.conf
    grep -q user_allow_other /etc/fuse.conf || echo "user_allow_other" >> /etc/fuse.conf
fi

# ============================================================
# 7. Tailscale
# ============================================================
log "7/8 Instalando Tailscale…"
if ! command -v tailscale &>/dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
else
    log "Tailscale ya instalado: $(tailscale version | head -1)"
fi

# ============================================================
# 8. Redis activado
# ============================================================
log "8/8 Habilitando Redis…"
systemctl enable redis-server
systemctl start redis-server

# ============================================================
# Resumen
# ============================================================
log ""
log "============================================================"
log "✅ Provisión base completada."
log "============================================================"
log ""
log "Próximos pasos (ejecuta en este orden):"
log ""
log "  1. Cambia al usuario de la app:"
log "     su - ${APP_USER}"
log ""
log "  2. Configura rclone con Google Drive:"
log "     rclone config        # crea remote 'gdrive' (ver deploy/README.md §3)"
log ""
log "  3. Clona el repo y arranca la app:"
log "     git clone https://github.com/9ness/TikTok_Automation_Python.git"
log "     cd TikTok_Automation_Python"
log "     bash deploy/install_app.sh"
log ""
log "  4. Configura Tailscale (ver deploy/README.md §6):"
log "     sudo tailscale up"
log "     sudo tailscale serve --bg --https=443 http://localhost:8501"
log "     sudo tailscale funnel --bg 443"
log ""
log "Versión instalada de FFmpeg: $(ffmpeg -version | head -1)"
log "Versión de Python: $(python3 --version)"
log "Versión de rclone: $(rclone version | head -1)"
log ""
