#!/bin/bash
# Vigilante (cron cada 5 min): si hay vídeos de clientes de Nebulabs Media esperando
# aprobación, lanza UNA rutina de agente que los revisa (~/rutinas/revision-clientes-nebulabs.md).
# Mirar la cuenta no gasta nada; el agente solo arranca cuando hay trabajo.
#   */5 * * * * /home/nebulabsai/proyectos/TikTok_Automation_Python/scripts/vigilar_revision_clientes.sh
set -u
NOMBRE="Revisar vídeos clientes Nebulabs"
SES="rut_$(echo "$NOMBRE" | md5sum | cut -c1-10)"
tmux has-session -t "$SES" 2>/dev/null && exit 0          # ya hay uno revisando
# Solo cuenta lo que el agente AÚN no ha revisado: en la fase de arranque lo
# revisado espera el OK de Néstor y no hay que relanzar al revisor por ello.
REV=/home/nebulabsai/rutinas/estado/revisados_nebulabs.txt
touch "$REV"
n=$(docker exec -e PYTHONPATH=/app tiktok-api python scripts/revision_clientes.py pendientes 2>/dev/null \
    | python3 -c '
import json, sys
hechos = set(open(sys.argv[1]).read().split())
try:
    p = json.load(sys.stdin)
except Exception:
    p = []
print(sum(1 for x in p if "|".join(str(x.get(k)) for k in ("user_id", "day", "filename")) not in hechos))
' "$REV")
[[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -gt 0 ] || exit 0
echo "$(date -Is) $n pendiente(s) → lanzo revisor" >> /home/nebulabsai/rutinas/rutinas.log
exec /usr/local/bin/rutina "$NOMBRE" TikTok_Automation_Python /home/nebulabsai/rutinas/revision-clientes-nebulabs.md "VPS - Editor Video"
