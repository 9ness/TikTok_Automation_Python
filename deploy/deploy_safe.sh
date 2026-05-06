#!/usr/bin/env bash
#
# deploy_safe.sh — Auto-deploy seguro tras push a main.
#
# Disparado por webhook_listener.py. Hace:
#   1. Espera a que la cola de jobs esté vacía (no reinicia mid-render)
#   2. git pull --ff-only
#   3. Si requirements.txt cambió → reinstala deps
#   4. systemctl restart tiktok-factory
#
# Logs en logs/deploy.log para auditoría posterior.

set -uo pipefail   # -e no, queremos continuar incluso con steps que fallen para no
                   # dejar tiktok-factory parado

APP_DIR="/home/nebulabsai/TikTok_Automation_Python"
QUEUE_STATE="${APP_DIR}/temp_work/queue_state.json"
DEPLOY_STATUS="${APP_DIR}/temp_work/deploy_status.json"
LOG="${APP_DIR}/logs/deploy.log"
MAX_WAIT_SEC=3600   # 1h máximo esperando que la cola se vacíe
POLL_INTERVAL=30
LOCK_FILE="/tmp/tiktok-deploy.lock"

# Helper: escribe el estado del deploy en JSON. La UI lo lee para mostrar
# el badge de versión y si hay un deploy en curso.
write_status() {
    local state="$1"
    local extra="$2"   # JSON fragment adicional (sin llaves), p.ej. '"target_sha":"abc"'
    mkdir -p "$(dirname "$DEPLOY_STATUS")"
    local current_sha=$(git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || echo "?")
    local current_full=$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || echo "?")
    local now=$(date +%s)
    local body="\"state\":\"${state}\",\"current_sha\":\"${current_sha}\",\"current_sha_full\":\"${current_full}\",\"updated_at\":${now}"
    if [[ -n "$extra" ]]; then
        body="${body},${extra}"
    fi
    echo "{${body}}" > "${DEPLOY_STATUS}.tmp"
    mv "${DEPLOY_STATUS}.tmp" "$DEPLOY_STATUS"
}

mkdir -p "$(dirname "$LOG")"
exec >> "$LOG" 2>&1

# ============================================================
# Lock para evitar deploys concurrentes (si llegan 2 pushes muy seguidos)
# ============================================================
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "[deploy_safe] $(date -Iseconds) — otro deploy está en marcha, saliendo."
    exit 0
fi

echo ""
echo "============================================================"
echo "[deploy_safe] $(date -Iseconds) — INICIADO"
echo "============================================================"

# Marcar estado RUNNING desde el principio (la UI ya lo verá)
START_TS=$(date +%s)
write_status "running" "\"started_at\":${START_TS}"

# ============================================================
# Función: ¿hay jobs activos en la cola?
# Lee temp_work/queue_state.json y cuenta pending+running
# ============================================================
count_active_jobs() {
    if [[ ! -f "$QUEUE_STATE" ]]; then
        echo "0"
        return
    fi
    python3 -c "
import json, sys
try:
    data = json.load(open('${QUEUE_STATE}'))
    n = sum(1 for j in data.get('jobs', []) if j.get('status') in ('pending','running'))
    print(n)
except Exception:
    print(0)
" 2>/dev/null
}

# ============================================================
# 1. Esperar a que la cola se vacíe
# ============================================================
elapsed=0
while true; do
    n_active=$(count_active_jobs)
    if [[ "$n_active" == "0" ]]; then
        echo "[deploy_safe] cola vacía — procediendo con deploy"
        break
    fi
    if [[ $elapsed -ge $MAX_WAIT_SEC ]]; then
        echo "[deploy_safe] ⚠️ TIMEOUT (${MAX_WAIT_SEC}s) — quedan ${n_active} job(s) activos. Procedo igual."
        break
    fi
    echo "[deploy_safe] ${n_active} job(s) activo(s) — esperando ${POLL_INTERVAL}s (transcurridos ${elapsed}s/${MAX_WAIT_SEC}s)"
    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))
done

# ============================================================
# 2. Git pull
# ============================================================
cd "$APP_DIR" || { echo "[deploy_safe] ❌ no existe $APP_DIR"; exit 1; }

git fetch --quiet origin
LOCAL_SHA=$(git rev-parse HEAD)
REMOTE_SHA=$(git rev-parse origin/main)

if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
    echo "[deploy_safe] HEAD ya está en $LOCAL_SHA — sin cambios. Saliendo."
    write_status "success" "\"finished_at\":$(date +%s),\"started_at\":${START_TS},\"note\":\"no_changes\""
    exit 0
fi

echo "[deploy_safe] pulling: ${LOCAL_SHA:0:8} → ${REMOTE_SHA:0:8}"
if ! git pull --ff-only --quiet origin main; then
    echo "[deploy_safe] ❌ git pull falló (¿conflicto? ¿commits locales?)"
    write_status "failed" "\"finished_at\":$(date +%s),\"started_at\":${START_TS},\"error\":\"git_pull_failed\""
    exit 1
fi
NEW_SHA=$(git rev-parse HEAD)
echo "[deploy_safe] HEAD ahora en ${NEW_SHA:0:8}"
write_status "running" "\"started_at\":${START_TS},\"target_sha\":\"${NEW_SHA:0:7}\",\"previous_sha\":\"${LOCAL_SHA:0:7}\""

# ============================================================
# 3. Si requirements.txt cambió → reinstalar deps
# ============================================================
if git diff --name-only "$LOCAL_SHA" "$NEW_SHA" | grep -qE "^requirements\.txt$"; then
    echo "[deploy_safe] requirements.txt modificado, reinstalando deps…"
    if ! "${APP_DIR}/venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"; then
        echo "[deploy_safe] ⚠️ pip install falló — sigo con el restart, pero revisa logs"
    fi
fi

# ============================================================
# 4. Reiniciar tiktok-factory (sudo NOPASSWD ya configurado en setup.sh)
# ============================================================
echo "[deploy_safe] reiniciando tiktok-factory…"
if sudo systemctl restart tiktok-factory; then
    # Streamlit tarda 6-12s en estar 'active' (carga faster-whisper, moviepy,
    # etc). Esperamos hasta 30s con polling cada 2s — más robusto que un
    # sleep fijo. Si tras 30s sigue activating, lo marcamos failed.
    READY=0
    for _ in $(seq 1 15); do
        if systemctl is-active --quiet tiktok-factory; then
            READY=1
            break
        fi
        sleep 2
    done
    if [[ $READY -eq 1 ]]; then
        echo "[deploy_safe] ✅ tiktok-factory reiniciado y activo"
        write_status "success" "\"finished_at\":$(date +%s),\"started_at\":${START_TS},\"previous_sha\":\"${LOCAL_SHA:0:7}\""
    else
        echo "[deploy_safe] ❌ tiktok-factory NO arrancó en 30s. Logs:"
        journalctl -u tiktok-factory -n 30 --no-pager
        write_status "failed" "\"finished_at\":$(date +%s),\"started_at\":${START_TS},\"error\":\"service_not_active_30s\""
        exit 1
    fi
else
    echo "[deploy_safe] ❌ systemctl restart falló"
    write_status "failed" "\"finished_at\":$(date +%s),\"started_at\":${START_TS},\"error\":\"restart_failed\""
    exit 1
fi

echo "[deploy_safe] $(date -Iseconds) — COMPLETADO"
