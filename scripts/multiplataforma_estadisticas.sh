#!/usr/bin/env bash
# Guarda las estadísticas de Meta de la semana en ~/multiplataforma/estadisticas/<fecha>.json
# y el informe semanal_<fecha>.md (scripts/multiplataforma_informe.py).
# Se copia al contenedor como el tick, para no depender de un despliegue.
set -euo pipefail

aqui="$(cd "$(dirname "$0")" && pwd)"
destino="$HOME/multiplataforma/estadisticas"
mkdir -p "$destino"
salida="$destino/$(date +%F).json"

docker cp "$aqui/multiplataforma_estadisticas.py" tiktok-api:/tmp/multiplataforma_estadisticas.py >/dev/null
docker exec -w /app -e PYTHONPATH=/app tiktok-api python /tmp/multiplataforma_estadisticas.py "$@" > "$salida.tmp"
mv "$salida.tmp" "$salida"
chmod 600 "$salida"
echo "$salida"
# Informe en Markdown (host, sin API): semanal_<fecha>.md junto al JSON.
python3 "$aqui/multiplataforma_informe.py" --carpeta "$destino"
