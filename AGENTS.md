# AGENTS.md — TikTok_Automation_Python

> Manual de trabajo para agentes de IA (OpenCode / Claude Code) en este repo.
> Resumen operativo + puntero a la documentación profunda ya existente
> (`CLAUDE.md` y los `*_MODULE.md`). Idioma de comunicación con el usuario: **ESPAÑOL**.

---

## Selección de modelo (auto-routing — hazlo ANTES de empezar la tarea)
Este proyecto trabaja con dos PERFILES, no con nombres fijos:
- Perfil PESADO (rol tipo "Opus": el potente) — mejor en ficheros enormes y tareas largas/multi-fichero.
- Perfil DIARIO (rol tipo "Sonnet": rápido y barato) — el de por defecto para tareas normales.

| Perfil | Modelo |
|---|---|
| PESADO | el modelo potente del usuario (él sabe cuál cargar) |
| DIARIO | el modelo rápido/barato del usuario (él sabe cuál cargar) |

Al recibir una tarea, clasifícala y avisa en UNA línea. Es PESADA si cumple CUALQUIERA:
- Localizar/modificar detalles en un fichero muy grande (> ~2000 líneas) o varios grandes.
- El cambio toca MÁS de ~3-4 ficheros o muchos call-sites.
- Tarea multi-paso larga (migración, barrido) de muchos turnos.
- Perder el hilo entre pasos tendría coste alto.
Si no, es LIGERA. Si es PESADA: di "Esta tarea es PESADA (motivo: …), usa el perfil PESADO
(ver tabla); si no lo tienes cargado, cámbialo antes de seguir." Si es LIGERA: procede sin avisar.
En ficheros de miles de líneas, si concluyes que algo "no existe", haz grep del nombre exacto antes de afirmarlo.

**Ficheros que casi siempre disparan PESADO aquí** (verificado con `wc -l`):
`src/editor_auto/tools/silence_cutter.py` (~7.430) ·
`main.py` (~2.465, Streamlit legacy) ·
`frontend/components/products/PresetsManager.tsx` (~2.320) ·
`src/api/routers/products.py` (~2.210) ·
`src/queue/runners.py` (~2.105) ·
`frontend/components/generate/shop/Veo3Card.tsx` (~1.540) ·
`src/pronosticos/pipeline.py` (~1.450) ·
`frontend/app/editor-auto/users/_components/UserFoldersPanel.tsx` (~1.430) ·
`src/tiktok_shop/pipeline/preset_generator.py` (~1.250) ·
`src/tiktok_shop/pipeline/seedance_renderer.py` (~1.140) ·
`frontend/components/generate/GeneratorWizard.tsx` (~1.115) ·
`src/api/routers/tiktok_shop/radar.py` (~1.100) ·
`src/api/routers/editor_auto/web_upload.py` (~1.055) ·
`frontend/app/tiktok-shop/calendar/page.tsx` (~1.050) ·
`src/subtitles_only.py` (~1.030) ·
`src/tiktok_shop/ui/tab_products.py` (~1.020).

---

## 1. Resumen del proyecto

Fábrica de vídeos verticales 9:16 para TikTok. Un backend Python (FastAPI +
cola de jobs propia con WebSocket de progreso) orquesta pipelines que combinan
IA generativa y edición de vídeo: guiones con OpenAI/Gemini, voz con MiniMax
TTS, alineado de palabras con faster-whisper, montaje con MoviePy/FFmpeg y
subtítulos karaoke. Hay **3 programas aislados** entre sí: **Creator Reward**
(Presidentes Top 5, Pronósticos Diarios desde el Redis del proyecto hermano
`bet-ai-master`, Quitar Copy, Construcción POV), **TikTok Shop** (vídeos de
afiliado con Seedance/Veo3/Nano Banana, Radar de productos vía EchoTik/Apify,
planes semanales) y **Editor Auto** (cadena configurable de herramientas:
subtítulos, cortador de silencios con Silero VAD + GPT-4o…). El frontend es
Next.js (App Router); `main.py` es la UI Streamlit **legacy** que sigue
funcionando en paralelo. Estado y assets viven en Upstash Redis + Google Drive
(montado por rclone en el VPS).

**Stack:** Python 3.10+ · FastAPI + uvicorn · Streamlit (legacy) · MoviePy <2 +
FFmpeg · faster-whisper · Silero VAD + torchaudio 2.5.1 · OpenAI ·
google-generativeai (Gemini, dual-key FREE/PAID) · MiniMax TTS/voice-clone ·
Atlas Cloud (Seedance) + fal.ai (fallback) · EchoTik / Apify (Radar) ·
easyocr + opencv-headless · Upstash Redis (REST) · Next.js 14 + TypeScript +
Tailwind + Radix + React Query + Zustand · Docker Compose (api + web + Caddy)
en VPS Hetzner con Tailscale Funnel.

**Documentación profunda — LEE la que toque antes de tocar código:**

| Fichero | Cuándo leerlo |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Contexto general por programa/nicho, env vars, assets, convenciones. **Fuente de verdad**; AGENTS.md solo lo resume |
| [`ADDING_PROGRAM.md`](ADDING_PROGRAM.md) | Añadir un programa nuevo (checklist de touchpoints) |
| [`TIKTOK_SHOP_MODULE.md`](TIKTOK_SHOP_MODULE.md) | Programa 2 — arquitectura, Redis, tiers, prompts, Pilot Program |
| [`EDITOR_AUTO_MODULE.md`](EDITOR_AUTO_MODULE.md) | Programa 3 — flujo modular, registry de tools |
| [`EDITOR_DEBUGGING.md`](EDITOR_DEBUGGING.md) | **Obligatorio antes de tocar `silence_cutter.py`** |
| [`PronosticosAuto.md`](PronosticosAuto.md) | Schema Redis de `bet-ai-master`, segmentos, overlays |
| [`DEV_SETUP.md`](DEV_SETUP.md) | Arranque local y troubleshooting WS/cache |
| [`deploy/README.md`](deploy/README.md), [`deploy/SERVER_ACCESS.md`](deploy/SERVER_ACCESS.md) | Despliegue VPS y acceso SSH |
| [`learnings.md`](learnings.md) | Historial técnico (1 línea por fix/aprendizaje) |
| [`tasks.md`](tasks.md) | TODO pendientes (incluye tareas humanas: claves, planes de pago) |
| [`SESSION_STATE.md`](SESSION_STATE.md) | Handoff del refactor TikTok Shop (mayo 2026) |

---

## 2. Comandos reales

### Backend (raíz del repo, pip + `requirements.txt`, venv NO versionado)
```bash
python -m venv venv && source venv/bin/activate   # Windows: .\venv\Scripts\activate
pip install -r requirements.txt

uvicorn src.api.main:app --reload --port 8000     # API FastAPI (hot-reload)
streamlit run main.py                             # UI Streamlit legacy (:8501)
```

### Frontend (`/frontend`, npm)
```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
npm run build
npm run start
npm run lint       # next lint
npm run typecheck  # tsc --noEmit
npm run test       # vitest run  (npm run test:watch para watch)
```

### Tests Python (pytest, sin config propia — se ejecuta desde la raíz)
```bash
python -m pytest tests -q
python -m pytest tests/tiktok_shop tests/editor_auto tests/api -q   # por módulo
```
Suites en `tests/api`, `tests/tiktok_shop`, `tests/editor_auto`, `tests/test_config.py`.
Usan `FakeRedis` / `FakeJobQueue` (`tests/*/conftest.py`) — no tocan red ni Upstash.
**PENDIENTE: confirmar** — `pytest` NO está en `requirements.txt` (hay que instalarlo
aparte) y no hay `pytest.ini`/`pyproject.toml`/`setup.cfg`.

### Comprobaciones rápidas (del README / DEV_SETUP)
```bash
python -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('src').rglob('*.py')]"
python -c "from src.api.main import app; print('OK', len(app.routes))"
curl http://localhost:8000/api/health
```

### Producción (solo al desplegar — nunca en dev)
```bash
docker compose --env-file .env up -d --build   # servicios: api, web, caddy
docker compose logs -f api web caddy
```
En el VPS el despliegue real se dispara con `deploy/deploy_safe.sh` (ver
[`deploy/README.md`](deploy/README.md)).

**No hay CI:** el repo no tiene `.github/workflows/`. Lint/tests son manuales.

---

## 3. Arquitectura y directorios clave

```
main.py                     # UI Streamlit LEGACY (~2.5k líneas). No es el entry point moderno
src/
  api/main.py               # entry point FastAPI (uvicorn src.api.main:app)
  api/routers/              # dashboard, queue, products, users, voices, stats, costs, deploy…
    creator_reward/         #   presidents, pronosticos, copyright, construccion_pov, subs_auto
    tiktok_shop/            #   radar.py (~1.1k) y demás
    editor_auto/            #   enqueue, web_upload (~1k), users, plans, sharing, subscriptions
  api/schemas/, api/websockets/queue_ws.py   # /ws/queue: progreso en vivo
  queue/                    # models.py (JobMode), runners.py (~2.1k, dispatch_job), widget Streamlit
  cost_tracking.py          # OBLIGATORIO para toda API de pago (record_*)
  locutor.py, subtitles*.py, text_hook.py, logic.py, guionista.py, video_remover.py   # transversales
  pronosticos/              # data_loader (Redis betai:), segment_locator, stock_search, pipeline
  construccion_pov/         # gemini_video, script_generator, pipeline
  tiktok_shop/              # api/, models/, repos/, services/, pipeline/, prompts/*.md, ui/, utils/
  editor_auto/             # config, models, repos, services, tools/ (silence_cutter ~7.4k), pipeline, prompts
frontend/                   # Next.js App Router: app/creator-reward, app/tiktok-shop, app/editor-auto
tests/                      # api/ · tiktok_shop/ · editor_auto/ (pytest + FakeRedis)
deploy/                     # setup.sh, install_app.sh, deploy_safe.sh, webhook_listener.py, systemd/
docker-compose.yml, Dockerfile.api, Caddyfile
config/, assets/, scripts/, tools/, eval/, docs/
```

**Fuente de verdad de datos:** Upstash Redis (modo REST/HTTP). Prefijos por
programa: `betai:` (Pronósticos, escrito por `bet-ai-master`), `tiktok_shop:`,
`editor_auto:`. Los assets pesados viven en Google Drive
(`TIKTOK_CR/` · `TIKTOK_SHOP/` · `TIKTOK_EDITOR/`, carpetas HERMANAS).

**Cola unificada:** todo trabajo pasa por `JobMode` (`src/queue/models.py`) y
`dispatch_job` (`src/queue/runners.py`), que envuelve el job con
`start_job`/`finalize_and_persist` de `cost_tracking`.

---

## 4. Convenciones

- **Imports:** stdlib → terceros → `src.` → relativo. Excepción: `import
  streamlit as st` y `from dotenv import load_dotenv` cerca del entry point.
- **Nombres de variable en ASCII** (`competition_focus`, no `competición_focus`).
  Strings y comentarios en español sí llevan acentos.
- **System prompts en ficheros `.md`** (`src/<programa>/prompts/*.md`), NUNCA
  hardcodeados en el código.
- **Aislamiento entre programas:** jamás mezcles lógica de Creator Reward,
  TikTok Shop y Editor Auto. Solo se comparten módulos transversales
  (`locutor.py`, `cost_tracking.py`, `fonts_registry.py`, `src/queue/*`,
  `subtitles*`).
- **Cost tracking obligatorio:** toda llamada a una API de pago (OpenAI,
  MiniMax, Gemini, Atlas Cloud, EchoTik…) pasa por un `record_*` de
  [`src/cost_tracking.py`](src/cost_tracking.py), con tokens/chars/segundos
  REALES del response. El panel `/costs` se rellena solo.
- **Errores defensivos:** el pipeline NUNCA aborta por un asset opcional que
  falte (perfil.png, sfx, logos) — loguea aviso y continúa.
- **Logging UI:** los pipelines aceptan `log_callback`; default `_noop = lambda _: None`.
- **Frontend mobile-first:** grids `grid-cols-2 sm:grid-cols-N`, diálogos
  `w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto`, texto `text-xs sm:text-sm`,
  `truncate`/`break-words`. La app se usa desde el móvil.
- **Slugs de carpetas de stock:** minúsculas, no-alfanumérico → `_`, sin
  acentos (helper `src/pronosticos/stock_search.py:_slug()`).
- **Commits:** Conventional Commits **en español, con scope**, detectados del
  historial. Ej.: `feat(radar): descubrimiento invertido — de la inyección de
  ADS al producto`, `fix(calendario): dejar vaciar los campos numéricos`,
  `docs(tasks): plan EchoTik en ness4b`. Scopes vistos: `radar`, `shop`,
  `calendario`, `tasks`, `pronosticos`.
- **Rama por defecto:** `main`. Remote: `origin` → `github.com/9ness/TikTok_Automation_Python`.
- **Formato:** sin black/ruff/prettier configurados; solo `next lint` y
  `tsc --noEmit` en el frontend. **PENDIENTE: confirmar** si se quiere añadir
  formateador Python.
- **Modo CAVEMAN (activo, ver CLAUDE.md):** respuestas de 1-2 líneas, sin
  explicaciones ni resúmenes largos. Solo tool calls + confirmación de ficheros
  modificados.

---

## 5. Gotchas / cosas no obvias

1. **`silence_cutter.py` (~7.4k líneas) es el fichero más delicado del repo.**
   LEE [`EDITOR_DEBUGGING.md`](EDITOR_DEBUGGING.md) ANTES de tocarlo: jerarquía
   de señales (silero > energía > Whisper), casuística de bugs reales y cómo
   diagnosticar una queja. No parchees a ciegas.
2. **`main.py` es Streamlit legacy**, no el entry point actual. La app real es
   FastAPI (`src/api/main.py`) + Next.js. Ambos conviven; no rompas Streamlit
   al refactorizar módulos compartidos.
3. **La API NO debe depender de Streamlit.** `src/queue/__init__.py` importa el
   widget de forma lazy justo por eso — no lo subas a top-level.
4. **Upstash en modo REST**, no TCP (`UPSTASH_REDIS_REST_URL` + `_TOKEN`).
5. **Dependencia cruzada con `bet-ai-master`:** Pronósticos lee
   `betai:daily_bets_tiktok_video:YYYY-MM`, escrito por el otro repo. Si el
   schema cambia allí, aquí se rompe (y viceversa). Ver `PronosticosAuto.md`.
6. **Pins frágiles en `requirements.txt`** — hay comentarios explicando por qué:
   `packaging` va primero (silero-vad), `moviepy<2.0`, `numpy<2.0.0`,
   `torchaudio==2.5.1` (>=2.10 rompe con `OSError WinError 127`). No los
   "actualices" sin motivo.
7. **Rutas de assets en Google Drive:** `TIKTOK_CR/`, `TIKTOK_SHOP/` y
   `TIKTOK_EDITOR/` son HERMANAS, no anidadas. Usa los helpers de resolución
   (`src/tiktok_shop/config.py:resolve_shop_root()`), nunca rutas hardcodeadas.
   En el VPS es un mount rclone, no un Drive Desktop de Windows.
8. **Gemini dual-key:** `GOOGLE_GEMINI_KEY_FREE` → fallback a
   `GOOGLE_GEMINI_KEY_PAID` si 429. `GOOGLE_GEMINI_KEY` es legacy (Creator
   Reward) y solo se reusa si no hay FREE/PAID.
9. **Atlas Cloud → fal.ai** es un fallback automático; si `FAL_API_KEY` no está
   configurada, un fallo de Atlas propaga el error.
10. **TikTok Shop tiene reglas de negocio no negociables:** `ai_disclosure: true`
    siempre, presencia humana parcial, y máx. 5 shoppable/semana del Pilot
    Program (`services/pilot_tracker.py`).
11. **El Radar depende de cuota externa:** la clave EchoTik del VPS es de una
    cuenta de PRUEBAS casi agotada (ver `tasks.md`). Si el Radar falla, mira eso
    antes de depurar código.
12. **Sin CI:** no hay `.github/workflows/`. Nada valida tu cambio salvo que
    ejecutes tests/lint a mano.
13. **`.gitignore` ignora `*.mp4/*.mp3/*.jpg/*.png`** con excepciones puntuales
    (`frontend/public/brand/*`, `frontend/app/icon.png`…). Si añades un asset de
    marca y no aparece en producción, es esto.
14. **Raíz algo sucia:** `temp_work/`, `logs/`, `inputs_generados/`, `tmp/` y un
    fichero llamado `-` (contiene `fake_output_mp4`, residuo de un test). No son
    parte del pipeline. **PENDIENTE: confirmar** si el fichero `-` se puede borrar.
15. **Ediciones en ficheros largos:** nada de parches parciales ambiguos. Usa
    reemplazos con contexto amplio y único, o reescribe la función completa.
16. **Al añadir un MODO o programa nuevo**, sigue [`ADDING_PROGRAM.md`](ADDING_PROGRAM.md)
    entero (JobMode + runner + cost tracking + API + frontend + Docker + tests +
    docs). Saltarse un touchpoint deja el programa a medias.

---

## 6. Reglas de trabajo

- **Git:** el agente NO commitea ni pushea salvo petición explícita del usuario.
  Cuando se autorice: `git add <fichero concreto>`, nunca `git add .`.
  Prohibido: force-push, reescribir historial, crear/borrar ramas o tags.
  Push a `main` puede disparar el auto-deploy del VPS (webhook) — piénsalo antes.
- **NO tocar sin permiso:** los prompts `src/*/prompts/*.md` (calibrados en
  producción), los schemas de Redis (rompen `bet-ai-master` y/o el frontend),
  `deploy/**` y `docker-compose.yml`/`Caddyfile`, y los ficheros temporales de la
  raíz (`temp_work/`, `tmp/`, `-`).
- **Secretos:** nunca los imprimas, comitees ni los saques de `.env` /
  `secrets/`. `.gitignore` ya bloquea `.env` y `secrets/` — no lo debilites.
  Claves en juego: `OPENAI_API_KEY`, `MINIMAX_API_KEY`/`GROUP_ID`/`VOICE_ID`,
  `GOOGLE_GEMINI_KEY*`, `ATLASCLOUD_API_KEY`, `FAL_API_KEY`,
  `UPSTASH_REDIS_REST_URL`/`TOKEN`, `ECHOTIK_API_USER`/`PASSWORD`,
  `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `API_KEY` (auth de la API).
- **Si cambias un schema de Redis o de la API**, actualiza en el MISMO cambio
  los tipos TypeScript del frontend y la doc del `*_MODULE.md` correspondiente.
- **Antes de un comando o escritura crítica**, párate y razona: *"¿esto rompe el
  build, la Streamlit legacy, el otro programa o el deploy del VPS?"*.
- **Mantén `learnings.md` con 1 línea por bug/aprendizaje resuelto** (el fichero
  existe en la raíz, en minúsculas — NO crees otro). Al cerrar una tarea,
  muévela a `## ✅ Done` en `tasks.md`.
- **Actualiza `CLAUDE.md`** solo si: módulo nuevo/eliminado en `src/`, env vars,
  schema Redis, assets esperados, nicho o programa nuevo. NO por bugfixes ni
  refactors. Cap de 250 líneas.
- **Ante cualquier duda, pregunta.** No inventes rutas, keys ni comandos.
