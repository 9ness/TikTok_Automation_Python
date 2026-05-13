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

# Safety net: si por algún deploy anterior (con el commit+push del bump
# VERSION) quedó un commit local "ahead" de origin que no se pudo pushear,
# `git pull --ff-only` fallará. Detectamos y descartamos los commits
# locales SI Y SOLO SI todos son del auto-deploy (autor=auto-deploy) y
# tocan exclusivamente el archivo VERSION — no toca commits manuales.
LOCAL_AHEAD=$(git rev-list origin/main..HEAD --oneline 2>/dev/null | wc -l)
if [[ "$LOCAL_AHEAD" -gt 0 ]]; then
    echo "[deploy_safe] detectados ${LOCAL_AHEAD} commit(s) locales ahead de origin/main"
    ALL_AUTO=1
    while IFS= read -r sha; do
        author=$(git log -1 --format='%an' "$sha" 2>/dev/null)
        files=$(git show --name-only --format= "$sha" 2>/dev/null | tr '\n' ' ')
        if [[ "$author" != "auto-deploy" ]] || [[ "$(echo "$files" | xargs)" != "VERSION" ]]; then
            ALL_AUTO=0
            break
        fi
    done < <(git rev-list origin/main..HEAD)
    if [[ $ALL_AUTO -eq 1 ]]; then
        echo "[deploy_safe] todos son commits auto-deploy de VERSION → reset a origin/main"
        git reset --hard origin/main --quiet || true
    else
        echo "[deploy_safe] ⚠️ hay commits locales NO auto — abortando para no perderlos"
        write_status "failed" "\"finished_at\":$(date +%s),\"started_at\":${START_TS},\"error\":\"local_commits_ahead\""
        exit 1
    fi
fi

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
# 2.b. Auto-bump del archivo VERSION según commits incluidos
# ============================================================
# Convención usada por nuestros commits:
#   feat:      → bump minor
#   feat!:     → bump major
#   fix:|chore:|deploy:|refactor: → bump patch
#   BREAKING CHANGE en el body → bump major
#
# La versión final se escribe en `VERSION` y se commitea con `[skip ci]`
# para no triggerear otro deploy. Si no hay commits relevantes, mantiene
# la versión actual. La UI lee `/api/v1/diagnostics/summary` y muestra
# este valor (cae al short SHA si VERSION no existe).
bump_version() {
    local current_version="$1"
    local bump_type="$2"   # major|minor|patch
    local IFS=.
    # shellcheck disable=SC2206
    local parts=($current_version)
    local major=${parts[0]:-0}
    local minor=${parts[1]:-0}
    local patch=${parts[2]:-0}
    case "$bump_type" in
        major) major=$((major + 1)); minor=0; patch=0 ;;
        minor) minor=$((minor + 1)); patch=0 ;;
        patch) patch=$((patch + 1)) ;;
    esac
    echo "${major}.${minor}.${patch}"
}

determine_bump() {
    local commits="$1"
    if echo "$commits" | grep -qE '^[a-f0-9]+ (feat!|fix!|refactor!|.*BREAKING CHANGE)'; then
        echo "major"
    elif echo "$commits" | grep -qE '^[a-f0-9]+ feat(\(|:)'; then
        echo "minor"
    elif echo "$commits" | grep -qE '^[a-f0-9]+ (fix|chore|deploy|refactor|perf|docs)(\(|:)'; then
        echo "patch"
    else
        echo "none"
    fi
}

VERSION_FILE="${APP_DIR}/VERSION"
CURRENT_VERSION=$(cat "$VERSION_FILE" 2>/dev/null | tr -d '[:space:]')
CURRENT_VERSION=${CURRENT_VERSION:-0.1.0}
COMMITS_BETWEEN=$(git log --format="%h %s" "${LOCAL_SHA}..${NEW_SHA}")
BUMP_TYPE=$(determine_bump "$COMMITS_BETWEEN")
if [[ "$BUMP_TYPE" != "none" ]]; then
    NEW_VERSION=$(bump_version "$CURRENT_VERSION" "$BUMP_TYPE")
    echo "[deploy_safe] versión: ${CURRENT_VERSION} → ${NEW_VERSION} (bump=${BUMP_TYPE})"
    # Sobrescribe el archivo IN-PLACE (mismo inode → el bind-mount Docker
    # ve el cambio sin restart). NO commiteamos a git: el VERSION es un
    # estado local del servidor que evoluciona con cada deploy; meterlo
    # en git crearía divergencia entre local/origin y rompería el siguiente
    # `git pull --ff-only`.
    printf "%s\n" "$NEW_VERSION" > "$VERSION_FILE"
else
    NEW_VERSION="$CURRENT_VERSION"
    echo "[deploy_safe] commits no triggerean bump (versión sigue ${NEW_VERSION})"
fi

# ============================================================
# 3. Si requirements.txt cambió → reinstalar deps (Streamlit venv)
# ============================================================
CHANGED_FILES=$(git diff --name-only "$LOCAL_SHA" "$NEW_SHA")
if echo "$CHANGED_FILES" | grep -qE "^requirements\.txt$"; then
    echo "[deploy_safe] requirements.txt modificado, reinstalando deps del venv…"
    if ! "${APP_DIR}/venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"; then
        echo "[deploy_safe] ⚠️ pip install falló — sigo con el restart, pero revisa logs"
    fi
fi

# ============================================================
# 3.b. Auto-rebuild de containers Docker según ficheros cambiados
# ============================================================
# El stack Docker (FastAPI + Next.js + Caddy) corre en paralelo a Streamlit.
# Cuando cambian ficheros del nuevo stack, hay que rebuildar/restart los
# containers correspondientes — `git pull` solo no basta porque docker no
# detecta cambios en la imagen al vuelo.
#
# Mapping fichero → acción:
#   Dockerfile.api | docker-compose.yml | src/ (excepto src/streamlit*) | requirements.txt
#       → rebuild api
#   frontend/      | docker-compose.yml
#       → rebuild web
#   Caddyfile      | docker-compose.yml
#       → restart caddy (no rebuild)
#
# Si docker no está instalado o no hay docker-compose.yml en el repo, se
# omite limpiamente (modo Streamlit-only).
NEEDS_API_REBUILD=false
NEEDS_WEB_REBUILD=false
NEEDS_CADDY_RESTART=false

if [[ -f "${APP_DIR}/docker-compose.yml" ]] && command -v docker >/dev/null 2>&1; then
    if echo "$CHANGED_FILES" | grep -qE "^(Dockerfile\.api|docker-compose\.yml|requirements\.txt)$"; then
        NEEDS_API_REBUILD=true
    fi
    if echo "$CHANGED_FILES" | grep -qE "^src/(api|fonts_registry\.py|queue/(metrics|manager|models|runners|__init__)\.py|subtitles|pronosticos|tiktok_shop|video_remover|locutor|guionista|logic|word_calibrator|text_hook|font_resolver|diagnostics)"; then
        NEEDS_API_REBUILD=true
    fi
    if echo "$CHANGED_FILES" | grep -qE "^frontend/"; then
        NEEDS_WEB_REBUILD=true
    fi
    if echo "$CHANGED_FILES" | grep -qE "^(Caddyfile|docker-compose\.yml)$"; then
        NEEDS_CADDY_RESTART=true
    fi
fi

# Función helper: corre docker compose con env-file y captura errores.
dc() {
    (cd "$APP_DIR" && docker compose --env-file .env "$@")
}

if [[ "$NEEDS_API_REBUILD" == "true" ]]; then
    echo "[deploy_safe] 🐳 cambios en API/deps detectados — rebuild api…"
    write_status "running" "\"started_at\":${START_TS},\"target_sha\":\"${NEW_SHA:0:7}\",\"previous_sha\":\"${LOCAL_SHA:0:7}\",\"stage\":\"docker_build_api\""
    if ! dc up -d --build api; then
        echo "[deploy_safe] ❌ rebuild api falló"
        write_status "failed" "\"finished_at\":$(date +%s),\"started_at\":${START_TS},\"error\":\"docker_api_build_failed\""
        exit 1
    fi
    echo "[deploy_safe] ✅ api rebuildado"
fi

if [[ "$NEEDS_WEB_REBUILD" == "true" ]]; then
    echo "[deploy_safe] 🐳 cambios en frontend detectados — rebuild web…"
    write_status "running" "\"started_at\":${START_TS},\"target_sha\":\"${NEW_SHA:0:7}\",\"previous_sha\":\"${LOCAL_SHA:0:7}\",\"stage\":\"docker_build_web\""
    if ! dc up -d --build web; then
        echo "[deploy_safe] ❌ rebuild web falló"
        write_status "failed" "\"finished_at\":$(date +%s),\"started_at\":${START_TS},\"error\":\"docker_web_build_failed\""
        exit 1
    fi
    echo "[deploy_safe] ✅ web rebuildado"
fi

if [[ "$NEEDS_CADDY_RESTART" == "true" ]]; then
    echo "[deploy_safe] 🐳 Caddyfile/compose modificado — restart caddy…"
    if ! dc up -d caddy; then
        echo "[deploy_safe] ⚠️ caddy restart falló — comprueba `docker compose logs caddy`"
    else
        echo "[deploy_safe] ✅ caddy reiniciado"
    fi
fi

if [[ "$NEEDS_API_REBUILD" == "true" || "$NEEDS_WEB_REBUILD" == "true" ]]; then
    # Tras los rebuilds, log un ps para auditoría
    echo "[deploy_safe] estado containers tras rebuild:"
    dc ps || true
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
