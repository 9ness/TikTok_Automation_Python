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

## Sacar la fábrica del VPS (o cambiar de proveedor)

Todo habla la API REST de Upstash, así que mover los datos es copiar y cambiar
dos variables:
1. Destino nuevo: un Upstash (o cualquier Redis gestionado con `redis-rest`
   delante, en Railway/Fly/otro VPS).
2. Copiar: `migrar.py <url_nuevo> <token_nuevo> --desde http://redis-rest:8080 <FABRICA_REDIS_REST_TOKEN>`
   (con la cola vacía). Alternativa sin red: el `.rdb` diario de
   `Drive › _backups › redis` se importa en cualquier Redis.
3. `.env`: `FABRICA_REDIS_REST_URL/_TOKEN` = el destino nuevo (o quitarlas para
   volver al Upstash compartido) y recrear la api.
