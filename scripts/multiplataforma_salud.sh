#!/usr/bin/env bash
# Vigía de salud del publicador Multiplataforma: recoge datos en el contenedor (sin sacar tokens),
# los analiza en el host y avisa al panel UNA vez por incidencia. Pasa los argumentos (p. ej. --dry-run).
set -euo pipefail

aqui="$(cd "$(dirname "$0")" && pwd)"
casa="$HOME/multiplataforma"
datos="$casa/salud_datos.json"

docker cp "$aqui/multiplataforma_salud.py" tiktok-api:/tmp/multiplataforma_salud.py >/dev/null
if ! docker exec -w /app -e PYTHONPATH=/app tiktok-api python /tmp/multiplataforma_salud.py > "$datos.tmp" 2>"$casa/salud_error.log"; then
  : > "$datos.tmp"  # vacío → el analizador lo convierte en la incidencia «recolector:fallo»
fi
mv "$datos.tmp" "$datos"
chmod 600 "$datos"
python3 "$aqui/multiplataforma_salud_avisar.py" --datos "$datos" "$@"
