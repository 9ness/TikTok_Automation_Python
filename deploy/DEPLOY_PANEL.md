# Panel Deploy en Settings — guía rápida

Tras tirar este deploy, el `Settings → Deploy` deja al operador (sin SSH)
hacer **deploy, rebuild de containers, restart, ver log en vivo y stats
del host**.

## Cómo funciona

```
Frontend Settings
   │   X-API-Key (la misma de la app)
   ▼
Caddy → tiktok-api (FastAPI)
   │   src/api/routers/deploy.py
   │   http://host.docker.internal:9000
   ▼
tiktok-webhook (host)
   │   deploy/webhook_listener.py
   ▼
docker compose / deploy_safe.sh
```

El `webhook_listener.py` SIEMPRE tuvo permisos `docker` y sudo NOPASSWD
puntual; los nuevos endpoints `/admin/*` solo orquestan **lo que ya hacía
`deploy_safe.sh`**, ningún privilegio nuevo.

## Endpoints añadidos (webhook_listener:9000)

| Método | Path | Auth | Acción |
|---|---|---|---|
| POST | `/admin/deploy` | `X-API-Key` | git pull + deploy_safe.sh |
| POST | `/admin/docker/rebuild` | `X-API-Key` | `docker compose up -d --build {svc}` |
| POST | `/admin/docker/restart` | `X-API-Key` | `docker compose restart {svc}` |
| GET  | `/admin/docker/ps` | `X-API-Key` | parsed `docker compose ps` |
| GET  | `/admin/deploy/log?n=200` | `X-API-Key` | tail `logs/deploy.log` |
| GET  | `/admin/system` | `X-API-Key` | uptime/disk/mem |

Whitelist de servicios: `api`, `web`, `caddy`. Cualquier otro nombre → 400.

## Endpoints FastAPI (proxy)

| Método | Path | Acción |
|---|---|---|
| GET  | `/api/v1/deploy/health` | ¿webhook responde? |
| POST | `/api/v1/deploy/run` | botón "Deploy ahora" |
| POST | `/api/v1/deploy/rebuild` | rebuild api+web |
| POST | `/api/v1/deploy/restart` | restart un container |
| GET  | `/api/v1/deploy/containers` | docker compose ps |
| GET  | `/api/v1/deploy/log?n=200` | tail de deploy.log |
| GET  | `/api/v1/deploy/system` | host stats |

## Requisitos en el server

1. **`API_KEY` definida en `.env`** del host. Sin ella el panel no
   funciona (los endpoints `/admin/*` devuelven 503). Es la misma key
   que ya usas para autenticar el frontend.
2. **`tiktok-webhook` corriendo**:
   ```bash
   sudo systemctl status tiktok-webhook
   ```
3. **`docker compose` accesible para `nebulabsai`** (ya cubierto por
   `SupplementaryGroups=docker` en `tiktok-webhook.service`).

## Primera vez: aplicar tras el push

```bash
ssh nebulabsai@SERVER_IP
cd /home/nebulabsai/TikTok_Automation_Python
git pull --ff-only

# 1) Reiniciar el webhook listener para que cargue el nuevo Python
sudo systemctl restart tiktok-webhook
sudo journalctl -u tiktok-webhook -n 20 --no-pager   # verifica que arrancó

# 2) Rebuild api+web para que el FastAPI y el frontend tengan el código nuevo
docker compose up -d --build api web

# A partir de aquí, todo se hace desde el botón "Deploy ahora" en Settings.
```

## Seguridad

- Endpoints `/admin/*` exigen `X-API-Key` (compare_digest no es
  estrictamente necesario aquí, pero el equiv. está garantizado por la
  comparación de string).
- Whitelist explícita de servicios reiniciables.
- `_spawn_background` redirige stdout/err a `deploy.log` para auditoría.
- Sin endpoint de "shell arbitrario" — solo acciones predefinidas.
