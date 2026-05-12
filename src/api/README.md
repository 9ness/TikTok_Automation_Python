# API FastAPI — Backend para frontend Next.js

Esta API es el reemplazo eventual de la UI Streamlit para el módulo
TikTok Shop. Coexiste con Streamlit durante toda la migración — ambos
apuntan a la misma persistencia (Redis Upstash + Drive sincronizado).

**No se rompe nada de Streamlit hasta que Next.js esté completo y validado.**

---

## Arrancar en local

```bash
# 1. Instalar dependencias nuevas
pip install -r requirements.txt

# 2. Arrancar con auto-reload
uvicorn src.api.main:app --reload --port 8000
```

URLs:

- API base: `http://localhost:8000/api/v1`
- Health: `http://localhost:8000/api/health`
- Swagger UI: `http://localhost:8000/api/docs`
- Redoc: `http://localhost:8000/api/redoc`
- OpenAPI JSON: `http://localhost:8000/api/openapi.json`

---

## Variables de entorno

```env
# === API ===
API_HOST=0.0.0.0                                    # default
API_PORT=8000                                       # default
API_KEY=                                            # opcional — si está definida, header X-API-Key obligatorio
API_CORS_ORIGINS=http://localhost:3000,http://localhost:8501  # default

# === Compartidas con Streamlit (ya existentes) ===
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...
TIKTOK_SHOP_ROOT_PATH=...                           # opcional, autodetect si no se define
GOOGLE_GEMINI_KEY_FREE=...                          # opcional, para análisis productos
GOOGLE_GEMINI_KEY_PAID=...
```

---

## Endpoints — Fase 1A (productos) + Fase 1B (usuarios + voces) + Fase 1C (generaciones + cola) + Fase 1D (Creator Reward) + Fase 1E (WebSocket + Stats + Dashboard)

Todos bajo `/api/v1/products`. Si `API_KEY` está definida en el `.env`,
añadir header `X-API-Key: <valor>` a cada request.

### `GET /api/v1/products`

Lista productos paginados.

```bash
curl 'http://localhost:8000/api/v1/products?limit=20&offset=0'
curl 'http://localhost:8000/api/v1/products?category=fitness'
curl 'http://localhost:8000/api/v1/products?include_deleted=true'
```

### `POST /api/v1/products`

Crea un producto (auto-crea estructura Drive).

```bash
curl -X POST http://localhost:8000/api/v1/products \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Primal Pump Creatina",
    "brand": "Primal Pump",
    "category": "fitness",
    "tiktok_shop": {
      "product_url": "https://www.tiktok.com/@shop/product/12345",
      "commission_rate": 0.15,
      "price_eur": 29.99
    },
    "default_tier": "standard",
    "analyze_with_gemini": false
  }'
```

Si `analyze_with_gemini=true`, lanza análisis Gemini en background tras
crear (no bloquea la respuesta).

### `GET /api/v1/products/{product_id}`

```bash
curl http://localhost:8000/api/v1/products/abc123
```

### `PUT /api/v1/products/{product_id}`

PATCH-style: solo se actualizan los campos enviados. Si cambia `slug`,
se renombra la carpeta en Drive.

```bash
curl -X PUT http://localhost:8000/api/v1/products/abc123 \
  -H 'Content-Type: application/json' \
  -d '{"brand": "Nueva marca", "default_tier": "advanced"}'
```

### `DELETE /api/v1/products/{product_id}`

Soft-delete (marca `deleted=true`, no borra Drive ni Redis).

```bash
curl -X DELETE http://localhost:8000/api/v1/products/abc123
```

### `POST /api/v1/products/{product_id}/photos`

Sube una foto al producto. `multipart/form-data`.

Campos:
- `file`: archivo (jpg/jpeg/png/webp, máx 5MB)
- `location`: `source` (default) o `generated`
- `type`: opcional en `source`, obligatorio en `generated`. Valores:
  `packshot|lifestyle|detail|in_use|macro`
- `origin`: solo en `source`. Valores: `internet|own|tiktok_shop_url`
- `url_origin`: solo en `source`

```bash
curl -X POST http://localhost:8000/api/v1/products/abc123/photos \
  -F 'file=@/path/to/photo.jpg' \
  -F 'location=source' \
  -F 'origin=internet' \
  -F 'url_origin=https://www.amazon.es/dp/...'
```

### `DELETE /api/v1/products/{product_id}/photos/{photo_id}`

Soft-delete de una foto. `photo_id` es el filename guardado en disco.

```bash
curl -X DELETE http://localhost:8000/api/v1/products/abc123/photos/01_amazon.jpg
```

### `PUT /api/v1/products/{product_id}/photos/{photo_id}`

Actualiza metadata de una foto.

```bash
curl -X PUT http://localhost:8000/api/v1/products/abc123/photos/01_amazon.jpg \
  -H 'Content-Type: application/json' \
  -d '{"type": "packshot", "preferred_for_tiers": ["standard", "advanced"]}'
```

### `POST /api/v1/products/{product_id}/analyze`

Re-analiza el producto con Gemini Vision usando las mejores fotos
disponibles (`photos.generated` si las hay, fallback a `source`).
Actualiza `key_features`, `target_audience`, `selling_points`.

```bash
curl -X POST http://localhost:8000/api/v1/products/abc123/analyze
```

### `POST /api/v1/products/{product_id}/nano-banana-prompt`

Genera prompt optimizado para pegar en Gemini chat con Nano Banana 2.

```bash
curl -X POST http://localhost:8000/api/v1/products/abc123/nano-banana-prompt \
  -H 'Content-Type: application/json' \
  -d '{
    "photo_types_wanted": ["packshot", "lifestyle", "macro"],
    "n_angles": 5
  }'
```

---

## Shape de errores

Todos los errores vuelven JSON con shape consistente:

```json
{
  "error": "Producto 'abc123' no encontrado.",
  "code": "product_not_found",
  "details": {"product_id": "abc123"}
}
```

Códigos posibles:
- `product_not_found` (404)
- `photo_not_found` (404)
- `user_not_found` (404)
- `voice_not_found` (404)
- `product_already_assigned` (409)
- `generation_not_found` (404)
- `video_file_not_found` (404)
- `job_not_found` (404)
- `job_not_cancellable` (409)
- `invalid_enqueue_request` (422)
- `quota_exceeded` (429)
- `preset_not_found` (404)
- `pronosticos_version_not_found` (404)
- `invalid_temp_path` (422)
- `validation_error` (422)
- `drive_error` (500)
- `gemini_error` (502)
- `unauthorized` (401)
- `internal_error` (500)

---

## Endpoints — Usuarios TikTok

### `GET /api/v1/users`
Lista usuarios. Query: `limit`, `offset`, `niche`, `include_deleted`.

```bash
curl 'http://localhost:8000/api/v1/users?niche=fitness'
```

### `POST /api/v1/users`
Crea usuario y carpeta Drive `_users/@username/products/`.

```bash
curl -X POST http://localhost:8000/api/v1/users \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "@cuenta_skincare_es",
    "display_name": "Skincare Tips España",
    "niche": "skincare",
    "default_video_tier": "standard"
  }'
```

### `GET /api/v1/users/{username}`
URL-encode el `@` (`%40`).

```bash
curl 'http://localhost:8000/api/v1/users/%40cuenta_skincare_es'
```

### `PUT /api/v1/users/{username}`
PATCH-style.

```bash
curl -X PUT 'http://localhost:8000/api/v1/users/%40cuenta_skincare_es' \
  -H 'Content-Type: application/json' \
  -d '{"followers_count": 1200, "creator_health_rating": 185}'
```

### `DELETE /api/v1/users/{username}`
Soft-delete.

### `POST /api/v1/users/{username}/products`
Asigna un producto. 409 si ya está asignado.

```bash
curl -X POST 'http://localhost:8000/api/v1/users/%40user/products' \
  -H 'Content-Type: application/json' \
  -d '{"product_id": "abc123"}'
```

### `DELETE /api/v1/users/{username}/products/{product_id}`
Desasigna. Idempotente (204 aunque no estuviera asignado).

### `GET /api/v1/users/{username}/pilot-progress`
Estado del Pilot Program: días, vídeos shoppable publicados, CHR, órdenes,
followers, contador semanal, vías de graduación con qué falta para cada una.

```bash
curl 'http://localhost:8000/api/v1/users/%40user/pilot-progress'
```

---

## Endpoints — Voces

### `GET /api/v1/voices`
Lista todas las voces (presets MiniMax + clones). Query: `language`,
`gender` (male/female/neutral), `include_presets`.

```bash
curl 'http://localhost:8000/api/v1/voices?language=es&gender=male'
```

### `GET /api/v1/voices/{voice_id}`
Acepta tanto IDs de preset (`preset_Spanish_EnergeticBoy`) como IDs de
voces clonadas (UUID).

---

## Endpoints — Generaciones (histórico)

### `GET /api/v1/generations`
Lista paginada. Query: `limit`, `offset`, `username`, `product_id`, `status`,
`include_deleted`. Ordenadas por `created_at` desc.

```bash
curl 'http://localhost:8000/api/v1/generations?status=completed&limit=20'
curl 'http://localhost:8000/api/v1/generations?username=@user&product_id=abc123'
```

### `GET /api/v1/generations/{generation_id}`
Devuelve `GenerationResponse` con todos los campos (cost, video_prompts,
photos_used, hooks, voice_used, status, etc.).

### `POST /api/v1/generations/enqueue`
Encola un nuevo job en la cola. Valida usuario+producto+tier+resolución+voz.

```bash
curl -X POST http://localhost:8000/api/v1/generations/enqueue \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "@user",
    "product_id": "abc123",
    "tier": "standard",
    "duration_seconds": 15,
    "resolution": "720p",
    "strategy": "dynamic",
    "voice_enabled": true,
    "voice_id": "Spanish_EnergeticBoy",
    "hook_category": "curiosity",
    "target_audience": "Gymbros",
    "shoppable": false
  }'
```

Devuelve `{job_id, estimated_cost, estimated_duration_seconds, position_in_queue}`.

### `POST /api/v1/generations/{generation_id}/regenerate`
Regenera idéntico (overrides vacío) o con cambios.

```bash
# Idéntico
curl -X POST 'http://localhost:8000/api/v1/generations/abc123/regenerate' \
  -H 'Content-Type: application/json' -d '{"overrides": {}}'

# Con cambios
curl -X POST 'http://localhost:8000/api/v1/generations/abc123/regenerate' \
  -H 'Content-Type: application/json' \
  -d '{"overrides": {"tier": "advanced", "duration": 10}}'
```

### `DELETE /api/v1/generations/{generation_id}`
Soft-delete (no borra el MP4 ni el registro Redis, solo marca `deleted=true`).

### `GET /api/v1/generations/{generation_id}/video`
Devuelve el archivo MP4 con `Content-Type: video/mp4`. Usa `FileResponse`
de FastAPI (streaming nativo). 404 si `local_path` no apunta a un archivo
existente.

### `GET /api/v1/generations/{generation_id}/metadata`
Info técnica: `duration_seconds`, `resolution`, `file_size_bytes`,
`clip_count`, `photos_used`, `voice_id`, `cost`, `tiktok_shop_metadata`,
`drive_path`, `drive_url`.

---

## Endpoints — Cola de jobs

### `GET /api/v1/queue`
Estado actual de la cola.

```bash
curl http://localhost:8000/api/v1/queue
```

Devuelve `{active_jobs[], pending_count, running_count, recent_completed[]}`.
Cada `ActiveJobResponse` lleva `progress_percent`, `current_step`,
`estimated_remaining_seconds`, `params` (subset relevante).

### `GET /api/v1/queue/{job_id}`
Estado individual de un job. 404 si no existe.

### `DELETE /api/v1/queue/{job_id}`
Cancela un job. 204 si pending o running (best-effort en running). 409 si
ya está en estado final (`completed/failed/cancelled`). 404 si no existe.

---

## Tests

```bash
python -m pytest tests/api/ -v
```

Los tests usan `FakeRedis` in-memory + `httpx.AsyncClient` con
`app.dependency_overrides`. Ningún test toca APIs reales — coste $0.

---

## Endpoints — Creator Reward (Fase 1D)

Los 4 nichos del Programa 1 (`PRESIDENTS`, `PRONOSTICOS`, `COPYRIGHT`,
`SUBS_AUTO`) ahora exponen sus operaciones por API. La cola sigue siendo
unificada — usar `/api/v1/queue?mode=presidents,pronosticos,copyright,subs_auto`
para filtrar el histórico CR.

### Filtros nuevos en `/api/v1/queue`

- `?mode=tiktok_shop,presidents` (CSV) — solo jobs de los modos listados.
- `?finished_limit=20` (default 5) — cuántos `recent_completed` devolver.

### Almacén temporal de uploads

- Los endpoints multipart (`/copyright/enqueue`, `/subs-auto/transcribe`)
  guardan el archivo bajo `<temp_root>/api_uploads/<niche>/`.
- Devuelven el path RELATIVO a `temp_root` (ej. `api_uploads/copyright/clean_in_1234.mp4`).
- En `/subs-auto/enqueue` el cliente reenvía ese path; el servidor valida
  anti path-traversal y rechaza con `422 invalid_temp_path` si escapa del
  directorio.
- Cleanup: archivos de `api_uploads/` con mtime > 24h se borran al startup
  de la API (lifespan handler). Configurable con `API_TEMP_ROOT`.

### `/api/v1/creator-reward/presidents/`

```bash
# Encolar un lote de 1-10 vídeos
curl -X POST http://localhost:8000/api/v1/creator-reward/presidents/enqueue \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {"topic": "worst", "top_count": 5, "include_history": true, "include_hook": true},
      {"topic": "richest", "top_count": 3, "prefix": "Top"}
    ],
    "creative_mode": false,
    "engine_version": "v2_estable",
    "resolution": "1080p (Lento)",
    "subs": {"enabled": true, "highlight_mode": "color_swap", "highlight_color": "#FDE047"},
    "hook": {"enabled": true, "duration": 5.0, "animation": "swipe_left"}
  }'

# Presets de subs/hook (Redis tiktokCR:config:*)
curl http://localhost:8000/api/v1/creator-reward/presidents/presets
curl http://localhost:8000/api/v1/creator-reward/presidents/presets/mi_preset
curl -X PUT http://localhost:8000/api/v1/creator-reward/presidents/presets/mi_preset \
  -H 'Content-Type: application/json' \
  -d '{"subs_enabled": true, "subs_highlight_color": "#22D3EE"}'
curl -X DELETE http://localhost:8000/api/v1/creator-reward/presidents/presets/mi_preset
```

### `/api/v1/creator-reward/pronosticos/`

```bash
# Listar versiones disponibles para una fecha
curl 'http://localhost:8000/api/v1/creator-reward/pronosticos/versions?date=2026-05-10'

# Última fecha con payload (mira 14 días atrás por defecto)
curl 'http://localhost:8000/api/v1/creator-reward/pronosticos/latest-date'

# Encolar 1+ versiones (script_overrides solo para las que se editan)
curl -X POST http://localhost:8000/api/v1/creator-reward/pronosticos/enqueue \
  -H 'Content-Type: application/json' \
  -d '{
    "target_date": "2026-05-10",
    "version_ids": ["v1", "v2"],
    "voice_id_override": "Spanish_EnergeticBoy",
    "script_overrides": {"v2": "Guion editado por el usuario"},
    "publish_to_redis": false,
    "audio": {"add_money_sfx": true, "sfx_volume": 0.55},
    "overlays": {"add_league_overlay": true, "saturation": 1.25}
  }'
```

### `/api/v1/creator-reward/copyright/`

```bash
# Subir + encolar limpieza (multipart)
curl -X POST http://localhost:8000/api/v1/creator-reward/copyright/enqueue \
  -F 'file=@video.mp4' \
  -F 'clean_mode=Subtítulos Virales' \
  -F 'hook_y_pct=0.20' \
  -F 'hook_color=#FDD002'
```

Acepta `.mp4`/`.mov` hasta 500 MB. `clean_mode` es uno de:
- `Subtítulos Virales`
- `Camuflaje Geométrico (Sin Subtítulos)`

`hook_y_pct` debe ser uno de `0.20` / `0.45` / `0.75`.

### `/api/v1/creator-reward/subs-auto/`

Flow en 2 pasos: el frontend transcribe primero, muestra el editor de
palabras, y al confirmar manda el render.

```bash
# Paso 1 — transcribir (síncrono, devuelve palabras + paths relativos)
curl -X POST http://localhost:8000/api/v1/creator-reward/subs-auto/transcribe \
  -F 'file=@song.mp4' \
  -F 'model_size=small' \
  -F 'language=es' \
  -F 'audio_type=music' \
  -F 'quality_label=1080p (Lento)'
# → {input_path_relative, out_path_relative, words[{word,start,end}]}

# Paso 2 — encolar render con texto editado y estilo
curl -X POST http://localhost:8000/api/v1/creator-reward/subs-auto/enqueue \
  -H 'Content-Type: application/json' \
  -d '{
    "input_path": "api_uploads/subs_auto/subs_in_1234.mp4",
    "out_path": "api_uploads/subs_auto/subs_out_1234.mp4",
    "edited_text": "hola mundo editado",
    "model_size": "small",
    "audio_type": "speech",
    "quality_label": "1080p (Lento)",
    "style": {
      "font_path": "C:/Windows/Fonts/impact.ttf",
      "highlight_mode": "pill",
      "highlight_color": "#BB0808",
      "text_color": "#FFFFFF",
      "stroke_color": "#000000",
      "stroke_width": 3,
      "case_mode": "UPPERCASE",
      "font_scale": 0.045,
      "max_words": 3,
      "y_position": 0.78,
      "pill_enabled": true,
      "max_width": 0.85,
      "sync_offset": 0
    }
  }'
```

Si `input_path` apunta fuera de `temp_root` o no existe, devuelve
`422 invalid_temp_path`.

---

## Endpoints — Stats (Fase 1E)

### `GET /api/v1/stats/monthly?month=YYYY-MM`
Coste y nº de vídeos del mes (default: mes actual). Desglose por módulo
(`tiktok_shop`/`creator_reward`), usuario, producto, tier y día.

```bash
curl 'http://localhost:8000/api/v1/stats/monthly'
curl 'http://localhost:8000/api/v1/stats/monthly?month=2026-04'
```

### `GET /api/v1/stats/historical?months=N`
Lista de N meses (default 12, máx 60) con stats de cada uno.

```bash
curl 'http://localhost:8000/api/v1/stats/historical?months=6'
```

### `GET /api/v1/stats/budget`
Estado del presupuesto mensual TT Shop. Lee
`TIKTOK_SHOP_MONTHLY_BUDGET_USD` del `.env`. Devuelve:
- `current_month_cost`
- `monthly_budget_usd` (null si no configurado)
- `percent_used`
- `status` (`ok` / `warning` ≥80% / `exceeded` / `no_budget`)
- `days_remaining_in_month`
- `projected_month_end_cost` (extrapolación lineal)

```bash
curl 'http://localhost:8000/api/v1/stats/budget'
```

---

## Endpoints — Dashboard (Fase 1E)

### `GET /api/v1/dashboard/summary`
KPIs globales para la landing del frontend: counters de
usuarios/productos, vídeos+coste del mes, contadores de cola, últimos 5
vídeos, status Pilot Program de cada cuenta y alertas activas.

```bash
curl 'http://localhost:8000/api/v1/dashboard/summary'
```

Códigos de alerta posibles:
- `budget_warning` (warning) — uso ≥80% del presupuesto
- `budget_exceeded` (error) — coste ≥ presupuesto
- `recent_failures` (error) — ≥3 jobs FAILED en últimas 24h
- `pilot_freeze` (info) — usuarios con weekly_shoppable=0

---

## WebSocket — Cola en tiempo real (Fase 1E)

**URL**: `ws://localhost:8000/ws/queue`

Si `API_KEY` está configurada, añadir `?api_key=<token>` como query param.

### Mensajes que el servidor envía

```json
// Al conectar — estado actual
{"type": "snapshot", "data": {"jobs": [{...}, {...}]}}

// Job nuevo o cambio de status
{"type": "update", "data": {"jobs": [{...}]}}

// Cambio solo de progreso/step (status sigue running)
{"type": "progress", "data": {"jobs": [{...}]}}

// Job desaparecido (clear_finished o remove)
{"type": "removed", "data": {"job_ids": ["abc123", ...]}}

// Respuesta a ping del cliente
{"type": "pong", "data": {}}
```

### Mensajes que el cliente puede enviar

```json
{"type": "ping"}
```

### Comando `wscat` para probar manualmente

```bash
# Instalar wscat si no lo tienes
npm install -g wscat

# Conectar (sin API_KEY)
wscat -c ws://localhost:8000/ws/queue

# Con API_KEY
wscat -c 'ws://localhost:8000/ws/queue?api_key=secret-token'

# Una vez conectado, verás el snapshot inicial y luego updates en vivo.
# Puedes mandar ping con:
> {"type":"ping"}
```

### Diseño

- El WebSocket hace polling interno cada 1s a `JobQueue.get_all()` y
  emite solo los deltas (no se modifica `manager.py` con hooks intrusivos).
- Cada conexión tiene su propio task asyncio y snapshot local — múltiples
  clientes simultáneos sin coordinación cruzada.
- Configurable: `ConnectionManager(poll_interval_s=...)`. En tests se
  reduce a 50ms con `app.dependency_overrides[get_connection_manager]`.
