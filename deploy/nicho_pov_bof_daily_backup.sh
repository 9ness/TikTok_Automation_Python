#!/usr/bin/env bash
# Backup diario de "Productos España" (Drive de un tercero que el admin borra
# sin aviso). Encola un job en la cola de la app: detecta qué cambió desde la
# última copia y guarda solo la diferencia, o una copia completa nueva si
# cambió demasiado.
#
# Instalado en el crontab de `nebulabsai`:
#   0 6 * * * /home/nebulabsai/TikTok_Automation_Python/deploy/nicho_pov_bof_daily_backup.sh
#
# No hace la copia aquí: solo encola. El runner la ejecuta con progreso
# visible en el panel de cola.
set -euo pipefail

REPO="/home/nebulabsai/TikTok_Automation_Python"
LOG="${REPO}/logs/nicho_pov_bof_backup.log"
mkdir -p "$(dirname "$LOG")"

# API_KEY del .env (si no está definida, la API acepta sin auth).
API_KEY="$(grep -E '^API_KEY=' "${REPO}/.env" 2>/dev/null | cut -d= -f2- || true)"

ts() { date -u '+%Y-%m-%d %H:%M:%SZ'; }

# La API escucha detrás de Caddy en el puerto 80 del propio host.
resp="$(curl -sS --max-time 60 -w '\n%{http_code}' \
    -X POST 'http://127.0.0.1/api/v1/nicho-pov-bof/backup/sync' \
    -H "X-API-Key: ${API_KEY}" \
    -H 'Content-Type: application/json' \
    -d '{"force_full": false}' 2>&1)" || {
  echo "$(ts) ERROR: no se pudo contactar con la API" >> "$LOG"
  exit 1
}

code="$(printf '%s' "$resp" | tail -1)"
body="$(printf '%s' "$resp" | sed '$d')"

if [ "$code" = "201" ] || [ "$code" = "200" ]; then
  echo "$(ts) OK encolado: ${body}" >> "$LOG"
else
  echo "$(ts) ERROR HTTP ${code}: ${body}" >> "$LOG"
  exit 1
fi
