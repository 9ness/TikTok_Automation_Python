#!/usr/bin/env bash
# Flechas de colores nuevos, sacadas de la BLANCA.
#
# Las flechas son ProRes 4444 con transparencia: relleno + borde negro. Se tiñe
# la blanca multiplicando cada canal por el color que se quiere, así que el
# relleno pasa a ese color, el borde sigue negro y la animación y la
# transparencia quedan intactas. Sale igual que las originales, sin rehacerlas
# a mano en un editor.
#
# Se usan en el Nicho Ropa (la flecha casa con el color del vídeo, ver
# `_FLECHA_POR_COLOR` en `src/nicho_ropa/pipeline/video_editor.py`): con seis
# colores se quedaba corto para las calles de otoño, los tonos tierra y la
# ropa en rosas o lilas.
#
# Además de colores, ESTILOS: todos los que tienen versión blanca (la fina, la
# de bloque, los chevrones y las tres flechitas) se tiñen en toda la paleta.
#
# Uso (dentro del contenedor de la API, que tiene ffmpeg y el Drive montado):
#   docker cp scripts/flechas_colores.sh tiktok-api:/tmp/ && \
#   docker exec tiktok-api bash /tmp/flechas_colores.sh
# Repetible: sobrescribe las que ya existan.
set -euo pipefail

DIR="${FLECHAS_DIR:-/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_EDITOR/Assets/flechas}"
BASE="$DIR/flecha_blanca.mov"
[[ -f "$BASE" ]] || { echo "No está $BASE" >&2; exit 1; }

# nombre  R     G     B      (0-1, lo que se multiplica al blanco)
COLORES="
naranja  1.00  0.54  0.12
marron   0.60  0.38  0.20
beige    0.90  0.81  0.64
rosa     1.00  0.49  0.70
morada   0.63  0.42  1.00
azul     0.24  0.48  1.00
burdeos  0.56  0.11  0.23
amarilla 1.00  0.84  0.20
roja     0.90  0.16  0.16
verde    0.30  0.78  0.36
cyan     0.20  0.82  0.90
negra    0.16  0.16  0.16
"

# Los ESTILOS que tienen versión blanca y se pueden teñir. Del de siempre
# (`flecha_blanca`) ya había amarilla, roja, verde, cyan y negra originales:
# esas no se tocan (`-n`), solo se añaden los colores que faltaban.
ESTILOS="
flecha_
flecha_avanza_
flecha_triple_
flecha_abajo_triple_
"

for estilo in $ESTILOS; do
    base="$DIR/${estilo}blanca.mov"
    [[ -f "$base" ]] || { echo "sin base: $base" >&2; continue; }
    echo "$COLORES" | while read -r nombre r g b; do
        [[ -z "$nombre" ]] && continue
        destino="$DIR/${estilo}${nombre}.mov"
        # Las que ya existen se quedan: las originales están mejor hechas que
        # un tinte, y así el script se puede repetir sin pisar nada.
        if [[ -f "$destino" ]]; then
            continue
        fi
        tmp="$(mktemp -d)/${estilo}${nombre}.mov"
        # `-nostdin`: sin él, ffmpeg se come la lista de colores que le llega
        # al bucle por la tubería y los nombres salen cortados ("flecha_rron").
        ffmpeg -nostdin -y -v error -i "$base" \
            -vf "format=rgba,colorchannelmixer=rr=${r}:rg=0:rb=0:gr=0:gg=${g}:gb=0:br=0:bg=0:bb=${b}" \
            -c:v prores_ks -profile:v 4444 -pix_fmt yuva444p10le -alpha_bits 16 \
            -an "$tmp"
        # Se escribe fuera y se copia: en el Drive montado, un ffmpeg a medias
        # dejaría una flecha rota a la vista de todos los montajes.
        cp "$tmp" "$destino"
        rm -rf "$(dirname "$tmp")"
        echo "✓ ${estilo}${nombre}.mov"
    done
done
