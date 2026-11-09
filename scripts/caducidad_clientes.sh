#!/bin/bash
# Ejecuta scripts/caducidad_clientes.py dentro de tiktok-api (la imagen no copia scripts/).
exec docker exec -i -w /app tiktok-api python - "$@" < "$(dirname "$(readlink -f "$0")")/caducidad_clientes.py"
