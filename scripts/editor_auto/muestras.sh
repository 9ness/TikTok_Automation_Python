#!/usr/bin/env bash
# Lanzador de MUESTRAS de edición para captación (Nebulabs Media).
#
# Qué hace, en una línea: coge los vídeos que dejes en ~/muestras_in, los pasa
# por el motor de edición real (dentro del contenedor tiktok-api) con el estilo
# "Nebulabs Prueba", y te deja las muestras editadas en ~/muestras_out listas
# para mandar por DM.
#
# NO toca la imagen de producción, ni el repo, ni ningún servicio: solo copia
# ficheros temporales al contenedor y los borra al terminar.
#
# Uso:
#   1) mete los vídeos de los creadores en ~/muestras_in
#   2) ./scripts/editor_auto/muestras.sh
#   3) recoge las muestras en ~/muestras_out
set -euo pipefail

CONTAINER="tiktok-api"
STYLE_ID="70102ea273c549319b83bec17998a05e"   # "Nebulabs Prueba": cortes + subs karaoke + flechas
IN_DIR="${1:-$HOME/muestras_in}"
OUT_DIR="${2:-$HOME/muestras_out}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$IN_DIR" "$OUT_DIR"

shopt -s nullglob
vids=("$IN_DIR"/*.{mp4,mov,MP4,MOV,mkv,webm,m4v})
if [ ${#vids[@]} -eq 0 ]; then
  echo "No hay vídeos en $IN_DIR — mete ahí los vídeos de los creadores y vuelve a lanzar."
  exit 1
fi
echo "Vídeos a procesar: ${#vids[@]}  (de $IN_DIR)"

# --- montar temporalmente en el contenedor (writable layer, se borra al final) ---
cleanup() { docker exec "$CONTAINER" rm -rf /app/scripts /app/_muestras_in /app/_muestras_out >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker exec "$CONTAINER" mkdir -p /app/scripts/editor_auto /app/_muestras_in /app/_muestras_out
docker cp "$SCRIPT_DIR/batch_samples.py" "$CONTAINER:/app/scripts/editor_auto/batch_samples.py"
for v in "${vids[@]}"; do docker cp "$v" "$CONTAINER:/app/_muestras_in/$(basename "$v")"; done

echo "Procesando dentro del contenedor…"
docker exec -w /app "$CONTAINER" python /app/scripts/editor_auto/batch_samples.py \
  --user-id "$STYLE_ID" --in /app/_muestras_in --out /app/_muestras_out

# --- recoger resultados al host ---
docker cp "$CONTAINER:/app/_muestras_out/." "$OUT_DIR/"
echo ""
echo "✅ Muestras listas en: $OUT_DIR"
ls -1 "$OUT_DIR"/*_muestra.mp4 2>/dev/null || echo "(revisa el log de arriba: ninguna muestra salió)"
