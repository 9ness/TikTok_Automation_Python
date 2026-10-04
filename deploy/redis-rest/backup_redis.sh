#!/bin/bash
# Copia diaria del Redis local de la fábrica al Drive (cron del host).
#   0 4 * * * /home/nebulabsai/TikTok_Automation_Python/deploy/redis-rest/backup_redis.sh
# Guarda las últimas 14. Restaurar: parar `redis`, copiar el .rdb como
# <REDIS_DATA_PATH>/dump.rdb (y quitar appendonlydir) y arrancarlo.
set -euo pipefail
DATOS="${REDIS_DATA_PATH:-/mnt/HC_Volume_106974679/redis-data}"
DESTINO="/home/nebulabsai/gdrive/_backups/redis"
mkdir -p "$DESTINO"
antes=$(docker exec tiktok-redis redis-cli LASTSAVE)
docker exec tiktok-redis redis-cli BGSAVE >/dev/null
for _ in $(seq 1 60); do
  [ "$(docker exec tiktok-redis redis-cli LASTSAVE)" != "$antes" ] && break
  sleep 2
done
sudo -n cat "$DATOS/dump.rdb" > "$DESTINO/redis-$(date +%F).rdb"
ls -1t "$DESTINO"/redis-*.rdb | tail -n +15 | xargs -r rm -f
echo "$(date -Is) backup redis ok: $(du -h "$DESTINO/redis-$(date +%F).rdb" | cut -f1)"
