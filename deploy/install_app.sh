#!/usr/bin/env bash
#
# install_app.sh — Configura la aplicación tras clonar el repo.
#
# Crea venv, instala requirements, pre-descarga modelos Whisper, prepara
# carpetas locales y registra los servicios systemd.
#
# Uso:
#   cd ~/TikTok_Automation_Python
#   bash deploy/install_app.sh
#
# Asume que setup.sh ya se ejecutó como root previamente.

set -euo pipefail

APP_USER="${USER}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${APP_DIR}/venv"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[install_app]${NC} $1"; }
warn() { echo -e "${YELLOW}[install_app]${NC} $1"; }
err()  { echo -e "${RED}[install_app]${NC} $1" >&2; }

if [[ "$APP_USER" == "root" ]]; then
    err "No ejecutes este script como root. Cámbiate al usuario de la app primero (su - nebulabsai)."
    exit 1
fi

cd "$APP_DIR"
log "Directorio de la app: $APP_DIR"

# ============================================================
# 1. venv + dependencias Python
# ============================================================
if [[ ! -d "$VENV_DIR" ]]; then
    log "1/5 Creando virtualenv en $VENV_DIR…"
    python3 -m venv "$VENV_DIR"
else
    log "1/5 venv ya existe en $VENV_DIR (reutilizando)."
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

log "Actualizando pip + wheel…"
pip install --quiet --upgrade pip wheel setuptools

log "Instalando requirements.txt (puede tardar 5-10 min, faster-whisper compila wheels)…"
pip install --quiet -r requirements.txt

# ============================================================
# 2. Carpetas locales (temp_work + logs)
# ============================================================
log "2/5 Creando carpetas locales de trabajo…"
mkdir -p "$APP_DIR/temp_work"          # Caché temporal + persistencia de la cola
mkdir -p "$APP_DIR/logs"               # Logs de la app (no rclone, ese va a /var/log)
log "  · temp_work/   (estado de la cola, audios temporales)"
log "  · logs/        (stdout de la app)"
# NOTA: los outputs finales van directos al mount de Drive
# (/home/nebulabsai/gdrive/...) — rclone se encarga de subirlos a Drive
# en background gracias a vfs-cache-mode=full. No necesitamos output_local.

# ============================================================
# 3. Pre-descarga del modelo Whisper 'base' (evita esperar al primer render)
# ============================================================
log "3/5 Pre-descargando modelo Whisper 'base' (~150MB)…"
python3 - <<'PY'
try:
    from faster_whisper import WhisperModel
    print("  · Cargando WhisperModel('base', device='cpu', compute_type='int8')…")
    m = WhisperModel("base", device="cpu", compute_type="int8")
    print("  · OK — modelo cacheado en ~/.cache/huggingface/")
except Exception as e:
    print(f"  · WARN: no se pudo precachear ({e}). Se descargará en el primer render.")
PY

# ============================================================
# 4. .env — comprobar que existe
# ============================================================
if [[ ! -f "$APP_DIR/.env" ]]; then
    warn "4/5 NO HAY .env. Sube el tuyo desde local con:"
    warn "   scp -i ~/.ssh/id_ed25519 .env ${USER}@<IP_DEL_VPS>:${APP_DIR}/.env"
    warn ""
    warn "Recuerda añadir/actualizar en el .env del VPS:"
    warn "   TIKTOK_ROOT_PATH=/home/${USER}/gdrive/Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_CR/TIKTOK_ASSETS"
else
    log "4/5 .env detectado: $APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"  # Asegurar permisos restrictivos
fi

# ============================================================
# 5. Plantillas systemd — copiar y rellenar variables
# ============================================================
log "5/5 Preparando plantillas systemd para registrarlas con sudo…"
SYSTEMD_DIR="/etc/systemd/system"
TEMPLATES_DIR="$APP_DIR/deploy/systemd"

cat <<EOF

============================================================
✅ Aplicación instalada en: $APP_DIR
============================================================

Para registrar los servicios systemd ejecuta como sudo:

    sudo bash $APP_DIR/deploy/register_services.sh

Esto activará:
  · gdrive-mount.service   — mount de Drive en ~/gdrive (read-write)
  · drive-sync.timer        — empuja outputs a Drive cada 60s
  · tiktok-factory.service  — Streamlit en localhost:8501

Después configura Tailscale Funnel (ver deploy/README.md §6).

EOF
