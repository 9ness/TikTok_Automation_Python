#!/bin/bash
# Vigilante (cron cada 5 min): si hay vídeos de clientes de Nebulabs Media esperando
# aprobación, lanza UNA rutina de agente que los revisa (~/rutinas/revision-clientes-nebulabs.md).
# Mirar la cuenta no gasta nada; el agente solo arranca cuando hay trabajo.
#   */5 * * * * /home/nebulabsai/proyectos/TikTok_Automation_Python/scripts/vigilar_revision_clientes.sh
set -u
NOMBRE="Revisar vídeos clientes Nebulabs"
SES="rut_$(echo "$NOMBRE" | md5sum | cut -c1-10)"
tmux has-session -t "$SES" 2>/dev/null && exit 0          # ya hay uno revisando
n=$(docker exec -e PYTHONPATH=/app tiktok-api python scripts/revision_clientes.py cuenta 2>/dev/null | tail -1)
[[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -gt 0 ] || exit 0
echo "$(date -Is) $n pendiente(s) → lanzo revisor" >> /home/nebulabsai/rutinas/rutinas.log
exec /usr/local/bin/rutina "$NOMBRE" TikTok_Automation_Python /home/nebulabsai/rutinas/revision-clientes-nebulabs.md "VPS - Editor Video"
