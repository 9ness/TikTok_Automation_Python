#!/usr/bin/env bash
# Vigilante de gasto de IA y salud (#293): recoge datos dentro de tiktok-api (sin sacar claves),
# los analiza en el host y avisa al panel UNA vez por incidencia. Solo avisa: nunca reinicia.
# Pasa los argumentos al analizador (p. ej. --dry-run).
set -euo pipefail
umask 077  # datos.json lleva la respuesta de salud

aqui="$(cd "$(dirname "$0")" && pwd)"
casa="$HOME/vigilante"
mkdir -p "$casa"
datos="$casa/datos.json"

docker cp "$aqui/vigilante_gasto.py" tiktok-api:/tmp/vigilante_gasto.py >/dev/null 2>"$casa/error.log" || true
docker cp "$aqui/../src/vigilante_gasto.py" tiktok-api:/tmp/vigilante_analisis.py >/dev/null 2>>"$casa/error.log" || true
if ! docker exec -w /app -e PYTHONPATH=/app tiktok-api python /tmp/vigilante_gasto.py > "$datos.tmp" 2>>"$casa/error.log"; then
  : > "$datos.tmp"  # vacío → el analizador avisa de «salud:sin_respuesta»
fi
mv "$datos.tmp" "$datos"
chmod 600 "$datos"
python3 "$aqui/vigilante_gasto_avisar.py" --datos "$datos" "$@"
