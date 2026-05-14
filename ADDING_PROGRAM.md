# Añadir un programa nuevo — checklist exhaustiva

Patrón consolidado a partir de los 2 programas existentes (Creator Reward,
TikTok Shop). Sigue todos los puntos en orden para que el nuevo programa
quede integrado en sidebar + API + cola + cost tracking + tests + deploy
sin tocar nada de los programas existentes.

> **Aislamiento entre programas**: nunca mezcles lógica entre carpetas
> `src/<programa>/`. Solo se comparten módulos transversales (MiniMax,
> FFmpeg, Whisper, Redis base, cost_tracking, queue, fonts_registry).

---

## 0) Decisiones previas

- **Nombre slug**: minúsculas con `_` (ej. `editor_auto`). Se usará en
  carpetas, env vars, JobMode, prefijo Redis, URLs.
- **Tools/Modos internos**: si el programa tiene varias herramientas
  (como TikTok Shop con tiers, o Creator Reward con sus 4 nichos), define
  el set inicial. Cada tool puede o no ser un `JobMode` distinto.
- **Esquema de usuario**: si gestionas usuarios con configuración por tool
  (caso "Editor Auto"), reusa el patrón de [`src/tiktok_shop/models/tiktok_user.py`](src/tiktok_shop/models/tiktok_user.py)
  + [`src/tiktok_shop/repos/user_repo.py`](src/tiktok_shop/repos/user_repo.py).
- **Assets**: si necesita una raíz en Drive distinta, define
  `<PROGRAMA>_ROOT_PATH` en `.env`. Sigue el patrón hermano `TIKTOK_*`.

---

## 1) Backend — capa de modelos y persistencia

Crea `src/<programa>/` con esta estructura mínima:

```
src/<programa>/
├── __init__.py
├── config.py              # paths, env vars, prefijo Redis, helpers
├── models/                # Pydantic — User, Tool, JobConfig, Cost, etc.
│   └── __init__.py
├── repos/                 # CRUD Redis (uno por entidad)
│   ├── __init__.py
│   ├── redis_base.py      # wrapper Upstash con prefijo propio
│   └── user_repo.py
├── services/              # lógica de negocio (validación, cálculos)
├── pipeline/              # módulos del render por etapas
│   └── __init__.py
└── prompts/*.md           # si usa LLMs, prompts SIEMPRE en .md (nunca hardcoded)
```

**Prefijo Redis**: añade en `config.py`:
```python
def redis_prefix() -> str:
    return os.getenv("<PROGRAMA>_REDIS_PREFIX") or "<programa>:"
```
**`redis_base.py`** copia el patrón de [`src/tiktok_shop/repos/redis_base.py`](src/tiktok_shop/repos/redis_base.py)
cambiando el prefijo. NO reutilices `ShopRedis` directamente — créate
`<Programa>Redis` propio para tener namespace aislado.

---

## 2) Queue / Runner

1. **JobMode**: añade en [`src/queue/models.py`](src/queue/models.py):
   ```python
   class JobMode(str, Enum):
       ...
       EDITOR_AUTO_SUBS = "editor_auto_subs"  # un mode por herramienta
   ```

2. **Runner**: crea `run_<tool>(job, on_log, on_progress) -> str` en
   [`src/queue/runners.py`](src/queue/runners.py). Recibe `Job`, escribe progreso, devuelve
   `result_path` (ruta del MP4 final).

3. **Dispatch**: añade entrada en `_RUNNERS` y en `_MODE_TO_PROGRAM`:
   ```python
   _RUNNERS[JobMode.EDITOR_AUTO_SUBS] = run_editor_auto_subs
   _MODE_TO_PROGRAM[JobMode.EDITOR_AUTO_SUBS] = "editor_auto"
   ```
   El wrapper `dispatch_job` ya envuelve automáticamente en
   `cost_tracking.start_job` / `finalize_and_persist`.

---

## 3) Cost tracking

**Obligatorio** para cualquier API externa con coste. Patrón:

- En cada call externa, justo tras el response real, llama al helper
  apropiado de [`src/cost_tracking.py`](src/cost_tracking.py):
  - `record_openai_chat(input_tokens=, output_tokens=, model=, detail=)`
  - `record_openai_whisper(audio_seconds=, detail=)`
  - `record_minimax_tts(chars=, voice=)`
  - `record_atlas_cloud(seconds=, tier=, resolution=, detail=)`
  - `record_custom(kind=, units=, unit_label=, cost_usd=, detail=)` para APIs nuevas
- Si la API es **nueva** (no existe helper): añade tarifa + función
  `record_<api>` en el módulo. Mantén tarifas como constantes top-of-file.
- El panel `/costs` mostrará el desglose automáticamente — no hay que
  tocar UI para que aparezca un programa nuevo.

---

## 4) API FastAPI

```
src/api/
├── routers/<programa>/
│   ├── __init__.py
│   ├── users.py          # CRUD usuarios del programa (si aplica)
│   ├── tools.py          # listado/config de herramientas
│   └── enqueue.py        # POST /enqueue → JobQueue
├── schemas/<programa>/   # Pydantic request/response
└── dependencies.py       # get_<programa>_repo via Depends
```

1. Registra routers en [`src/api/routers/__init__.py`](src/api/routers/__init__.py) y luego en
   [`src/api/main.py`](src/api/main.py) (`app.include_router(...)`).
2. Reusa `get_current_user`, `get_queue` de [`src/api/dependencies.py`](src/api/dependencies.py).
3. **Convención de paths**: `/api/v1/<programa>/<recurso>`.
4. Si el programa expone archivos sin auth header (img/video direct loads),
   crea un `file_router` aparte (patrón `subs_auto_frame_router` o
   `fonts_file_router`) con auth por query `?api_key=`.

---

## 5) Frontend Next.js

```
frontend/
├── app/<programa>/
│   ├── page.tsx          # landing/dashboard del programa
│   ├── users/page.tsx    # gestión de usuarios
│   ├── generate/page.tsx # encolar jobs
│   └── history/page.tsx  # histórico (lee /api/v1/stats/jobs filtrado)
├── components/<programa>/ # componentes propios
├── lib/queries/<programa>.ts  # TanStack Query hooks (1 archivo por programa)
└── lib/types/<programa>.ts    # tipos TS espejo de los Pydantic
```

**Sidebar**: añade un grupo nuevo en [`frontend/components/layout/Sidebar.tsx`](frontend/components/layout/Sidebar.tsx)
con su icono Lucide y sub-items por tool.

**Cost panel**: añade el programa al dropdown `PROGRAMS` y a
`MODES_BY_PROGRAM` en [`frontend/app/costs/page.tsx`](frontend/app/costs/page.tsx).

**Queue card metadata**: añade entrada en
[`frontend/lib/queue-meta.ts`](frontend/lib/queue-meta.ts) (`MODE_TO_PROGRAM`, `MODE_ICON`,
`SUBMODULE_LABEL`, `PROGRAM_BORDER`, etc.) para que el JobCard se vea
correcto en la cola.

---

## 6) Variables de entorno

Añade a `.env.example` (commit) y al `.env` del server (manual):

```env
# === Programa <NOMBRE> ===
# <PROGRAMA>_ROOT_PATH=...     # opcional — raíz de assets en Drive
# <PROGRAMA>_REDIS_PREFIX=...  # opcional — default "<programa>:"
```

Si añades una API externa nueva, define su `*_API_KEY` aquí y documenta
brevemente en `CLAUDE.md` la sección Variables de entorno.

---

## 7) Docker

Si el programa requiere **paths nuevos en el container** (raíz de assets
Drive distinta a `/mnt/drive`), añade override en
[`docker-compose.yml`](docker-compose.yml) en `services.api.environment`:

```yaml
<PROGRAMA>_ROOT_PATH: "/mnt/drive/.../<PROGRAMA>"
```

Si añade **dependencias de sistema** (binarios, librerías), añade
`apt-get install` al `Dockerfile.api`.

---

## 8) Auto-deploy

El [`deploy/deploy_safe.sh`](deploy/deploy_safe.sh) ya detecta cambios en `src/**` y
`frontend/**` para rebuildar containers automáticamente. Si añades
módulos críticos en rutas nuevas, asegúrate de que matchean el regex
de detección (cualquier cosa bajo `src/` cuenta).

---

## 9) Tests

Mínimo: `tests/api/<programa>/test_<recurso>.py` con happy path + error
de validación para cada endpoint. Reusa `app_client`, `fake_job_queue` y
demás fixtures de [`tests/api/conftest.py`](tests/api/conftest.py).

Si el programa toca Redis, mock con `FakeRedis` (ya en conftest).

---

## 10) Documentación

1. Crea `<PROGRAMA>_MODULE.md` en la raíz con: propósito, arquitectura
   (capas: API/runner/pipeline/repos), schema Redis, env vars, flujos por
   tool, prompts (referencia a los `.md` en `prompts/`).
2. Añade fila en CLAUDE.md → tabla de programas (Programa 1/2/3).
3. Enlaza el nuevo `<PROGRAMA>_MODULE.md` desde el índice de CLAUDE.md.
4. Si introduces un patrón técnico nuevo o resuelves un bug raro, registra
   1 línea en `learnings.md`.

---

## Checklist resumen (copiar al issue/PR)

- [ ] `src/<programa>/` con `config.py`, `models/`, `repos/`, `services/`, `pipeline/`, `prompts/`
- [ ] `<programa>:` Redis namespace con su `redis_base.py`
- [ ] `JobMode.<NUEVO>` + runner en `runners.py` + dispatch entry
- [ ] Cost tracking en cada call externa (helpers de `cost_tracking.py`)
- [ ] Routers FastAPI bajo `src/api/routers/<programa>/`
- [ ] Schemas Pydantic en `src/api/schemas/<programa>/`
- [ ] Pages Next.js bajo `frontend/app/<programa>/`
- [ ] Hooks TS en `frontend/lib/queries/<programa>.ts`
- [ ] Sidebar entry + queue-meta entry
- [ ] Entrada en `/costs` (PROGRAMS + MODES_BY_PROGRAM)
- [ ] Env vars en `.env.example`
- [ ] Tests API en `tests/api/<programa>/`
- [ ] `<PROGRAMA>_MODULE.md` + fila en CLAUDE.md
