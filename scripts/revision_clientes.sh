#!/bin/bash
# Ejecuta scripts/revision_clientes.py dentro de tiktok-api (la imagen no copia scripts/).
exec docker exec -i -e PYTHONPATH=/app -w /app tiktok-api python - "$@" < "$(dirname "$(readlink -f "$0")")/revision_clientes.py"
