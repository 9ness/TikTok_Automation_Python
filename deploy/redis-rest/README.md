# Redis local de la fábrica

Upstash cobra por comando y la fábrica hacía ~40 % de ellos. Desde oct 2026 la
fábrica usa un **Redis en el VPS** (`redis`, datos en `REDIS_DATA_PATH`, AOF +
RDB) con **`redis-rest`** delante: la misma API REST de Upstash (rutas
`/get/clave`, `/set/clave` con el valor en el cuerpo, JSON en `/`, `/pipeline`),
así que los ~20 clientes de `src/*/repos/redis_base.py` no cambian.

- **Interruptor**: `FABRICA_REDIS_REST_URL=http://redis-rest:8080` (+ `_TOKEN`) en
  `.env` → la api usa el local. Quitarlo y recrear la api = vuelta a Upstash.
- **Se queda en Upstash** (lo comparten otras apps): `editor_auto:` y `nebulabs:`
  (nebulabs-media en Vercel), `betai*` y `user_push_tokens` (Master Picks),
  `fitlife`, `trip`/`viajes`/`session`… (planificador), `fiesta`. Los clientes de
  Editor Auto y Pronósticos leen `UPSTASH_SHARED_*`.
- `paridad.py`: compara respuesta a respuesta Upstash real vs este redis-rest.
- `migrar.py`: copia las claves de la fábrica (tipo + TTL); `--solo-faltan` para
  una segunda pasada que no pisa lo nuevo.
- `backup_redis.sh`: BGSAVE + copia al Drive (`_backups/redis/`, 14 días), cron 4:00.
