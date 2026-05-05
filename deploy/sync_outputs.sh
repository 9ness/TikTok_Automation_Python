#!/usr/bin/env bash
#
# sync_outputs.sh — Empuja MP4s de output_local/ a Google Drive.
#
# Estrategia (decisión arquitectónica):
# - MoviePy escribe los MP4 finales en ./output_local/ (SSD del VPS, escritura
#   rápida y sin riesgo de corrupción).
# - Este script copia (no mueve) los nuevos MP4s a la carpeta correspondiente
#   de Drive (BIBLIOTECA_VIDEOS_TERMINADOS), preservando subcarpetas
#   (PRESIDENTES/, PRONOSTICOS/, SUBS_AUTO/, etc).
# - Si la subida fue exitosa, los archivos LOCALES se mueven a output_local/.archived/
#   para liberar espacio del SSD pero conservar copia local 7 días por seguridad.
# - Lo lanza un systemd timer cada 60s.
#
# Variables que el script espera:
# - APP_DIR: raíz del repo (autodetect por convención)
# - GDRIVE_OUTPUT_PATH: subcarpeta dentro del mount donde van los outputs

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_OUTPUT="${APP_DIR}/output_local"
ARCHIVE="${LOCAL_OUTPUT}/.archived"

# Carga .env si existe (para TIKTOK_ROOT_PATH)
if [[ -f "${APP_DIR}/.env" ]]; then
    set -o allexport
    # shellcheck disable=SC1091
    source "${APP_DIR}/.env"
    set +o allexport
fi

# Destino en Drive: por defecto BIBLIOTECA_VIDEOS_TERMINADOS bajo TIKTOK_ROOT_PATH
GDRIVE_OUTPUT_PATH="${GDRIVE_OUTPUT_PATH:-${TIKTOK_ROOT_PATH:-}/BIBLIOTECA_VIDEOS_TERMINADOS}"

if [[ -z "${TIKTOK_ROOT_PATH:-}" ]]; then
    echo "[sync_outputs] WARN: TIKTOK_ROOT_PATH no definido, abortando."
    exit 0
fi

if [[ ! -d "$LOCAL_OUTPUT" ]]; then
    # Nada que sincronizar todavía
    exit 0
fi

# Sólo sincronizamos archivos que han dejado de modificarse (>30s desde la
# última escritura) — evita subir vídeos a medio renderizar.
mkdir -p "$ARCHIVE"
mkdir -p "$GDRIVE_OUTPUT_PATH"

cd "$LOCAL_OUTPUT"

# Buscar MP4s estables (no modificados en los últimos 30s)
mapfile -t stable_files < <(
    find . -maxdepth 5 -type f -name "*.mp4" \
        -not -path "./.archived/*" \
        -mmin +0.5 \
        2>/dev/null
)

if [[ ${#stable_files[@]} -eq 0 ]]; then
    exit 0
fi

echo "[sync_outputs] $(date -Iseconds) — ${#stable_files[@]} archivo(s) estable(s) a sincronizar"

for relpath in "${stable_files[@]}"; do
    # relpath = ./PRESIDENTES/TikTok_AUTO_3.mp4
    relpath="${relpath#./}"
    local_file="${LOCAL_OUTPUT}/${relpath}"
    drive_file="${GDRIVE_OUTPUT_PATH}/${relpath}"
    archive_file="${ARCHIVE}/${relpath}"

    drive_subdir=$(dirname "$drive_file")
    archive_subdir=$(dirname "$archive_file")
    mkdir -p "$drive_subdir" "$archive_subdir"

    # Si ya existe en Drive con mismo tamaño, no re-subir, solo archivar
    if [[ -f "$drive_file" ]]; then
        local_size=$(stat -c%s "$local_file" 2>/dev/null || echo 0)
        drive_size=$(stat -c%s "$drive_file" 2>/dev/null || echo 0)
        if [[ "$local_size" == "$drive_size" ]] && [[ "$local_size" != "0" ]]; then
            echo "  · YA EXISTE: ${relpath} (mismo tamaño, archivando local)"
            mv -f "$local_file" "$archive_file"
            continue
        fi
    fi

    echo "  · COPIANDO: ${relpath} → Drive…"
    if cp "$local_file" "$drive_file.tmp" && mv "$drive_file.tmp" "$drive_file"; then
        echo "    ✅ OK"
        mv -f "$local_file" "$archive_file"
    else
        echo "    ❌ Falló la copia (se reintentará en el próximo ciclo)"
        rm -f "$drive_file.tmp" || true
    fi
done

# Limpiar archivos archivados >7 días
find "$ARCHIVE" -type f -mtime +7 -delete 2>/dev/null || true
# Limpiar dirs vacíos en archive
find "$ARCHIVE" -type d -empty -delete 2>/dev/null || true
