# CLAUDE.md — Contexto del proyecto

> Este archivo se carga automáticamente al abrir el proyecto. Mantenlo conciso —
> cada línea consume contexto en cada sesión.

## 🦴 Modo CAVEMAN (ACTIVO)
Regla estricta: Respuestas de 1-2 líneas máximo. Cero explicaciones, cortesías o resúmenes. Solo tool calls y confirmación de archivos modificados.

## Resumen del proyecto

`TikTok_Automation_Python` — fábrica Streamlit que genera vídeos virales 9:16
para TikTok. **3 programas principales** seleccionables en la sidebar (Creator
Reward / TikTok Shop / Editor Auto), cada uno con sus nichos.

### Programa 1 — Creator Reward (existente)

| Nicho | Modo | Propósito |
|---|---|---|
| 🏛️ Presidentes Top 5 | `PRESIDENTS_TOP5` | Rankings de presidentes USA con guion IA + assets locales |
| 📊 Pronósticos Diarios | `PRONOSTICOS_DIARIOS` | Vídeos de pronósticos deportivos desde Redis (bet-ai-master) |
| 🛡️ Quitar Copy | `COPYRIGHT_CLEANER` | Re-subtitula vídeos para evadir copyright |

### Programa 2 — TikTok Shop (en construcción)

| Función | Modo | Propósito |
|---|---|---|
| 🛒 Generador Shop | `TIKTOK_SHOP` | Vídeos affiliate AI con Seedance/Veo3, multi-cuenta, multi-producto |

### Programa 3 — Editor Auto

| Función | Modo | Propósito |
|---|---|---|
| ✂️ Editor Auto | `EDITOR_AUTO` | Edita vídeo input con flujo configurable de herramientas componibles por usuario (subs, cortador silencios + IA, ...) |

Punto de entrada: [`main.py`](main.py). Lanza con `streamlit run main.py`.

---

## Nicho 1 — Presidentes Top 5

**Flujo:** OpenAI genera guion JSON → MiniMax TTS por segmento → MoviePy monta
con imágenes locales de la biblioteca (un Top N de presidentes con datos histó-
ricos polémicos).

**Assets requeridos** (en `TIKTOK_ROOT_PATH`):
- `BIBLIOTECA_PRESIDENTES/<NombrePresidente>/` con fotos `.jpg/.png` y vídeos `.mp4/.mov`
- `BIBLIOTECA_INTRO/Intro/` para el opening
- `BIBLIOTECA_RECURSOS/` para comodines (siluetas, sonidos)

**Módulos clave:** [`src/guionista.py`](src/guionista.py) (OpenAI),
[`src/locutor.py`](src/locutor.py) (MiniMax TTS), [`src/logic.py`](src/logic.py)
(motor v1/v2 de animación), [`src/subtitles.py`](src/subtitles.py) (karaoke),
[`src/text_hook.py`](src/text_hook.py) (hook box).

---

## Nicho 2 — Pronósticos Diarios (más complejo)

**Datos:** Redis Upstash, key `betai:daily_bets_tiktok_video:YYYY-MM` field
`YYYY-MM-DD`. Schema: payload con array `versions[]` (cron + manuales) y
`selected_version_id`. Cada versión trae `mode` (`single_match` / `multi_match`)
+ `script` ya formateado para TTS + lista de picks.

**Flujo:** Redis → MiniMax TTS único → Whisper (word_timings) → detección
de segmentos (intro / picks / CTA) → MoviePy con stock por equipo + overlays.

**Briefing completo en [`PronosticosAuto.md`](PronosticosAuto.md)** — fuente
de verdad del schema y comportamiento del proyecto bet-ai-master.

**Módulos clave** (todos en [`src/pronosticos/`](src/pronosticos/)):
- `data_loader.py` — Redis + manejo de `versions[]` con compat legacy
- `script_builder_ai.py` (BORRADO en v2 — el guion ya viene de Redis)
- `segment_locator.py` — detecta `Empezamos/Seguimos/Vamos/Por último`,
  anchors de dinero (cifra del bote) y CTA midroll
- `cta_locator.py` — detecta ventana del CTA (incluye fallback `mi perfil`)
- `league_overlay.py` — mapping liga → archivo logo + render PIL
- `carousel_renderer.py` — card del pick (deshabilitado por defecto)
- `stock_search.py` — búsqueda jerárquica (equipo → liga → general) con
  fuzzy match (`Atletico_madrid` ↔ `Atlético de Madrid`)
- `pipeline.py` — orquestador

**Assets en `BIBLIOTECA_PRONOSTICOS_CLIPS/`:**
- Subcarpetas por equipo/liga con `.mp4` (stock)
- `fotos/perfil.png` — captura del perfil para el CTA midroll
- `fotos/liga_*.png` y `fotos/copa_*.png` — escudos de ligas/copas
- `sfx/money.mp3`, `sfx/clink.mp3`, `sfx/camera.mp3` — efectos de sonido
- `sfx/fondo.mp3` — música de fondo (recortada a la duración del vídeo,
  fade-out 0.5s, default 20% volumen)

**Voz MiniMax:** la inglesa (`MINIMAX_VOICE_ID`) sirve para Presidentes; para
Pronósticos hay 3 voces favoritas pre-seleccionables en la UI:
`Spanish_Strong-WilledBoy`, `Spanish_EnergeticBoy`, `Spanish_PassionateWarrior`
(todas Standard Spanish del catálogo MiniMax — tono latino-aceptable).
Override por `PRONOSTICOS_VOICE_ID` o por la UI.

**Capa de audio (de fondo a frente):**
1. Música fondo (20%)
2. TTS voz (100%)
3. SFX dinero (cifra del bote)
4. SFX clink (1 por pick, en `más/ambos/victoria/doble/...`)
5. SFX cámara (cuando aparece perfil.png + cuando aparecen logos de ligas)

**Capa visual:**
- Stock por pick (carpeta del equipo > away > liga > general; reparto dinámico
  de N clips de ~12s cada uno)
- Overlay perfil.png durante CTA
- Overlay logos de ligas durante intro (al pronunciar `ligas/champions/europa`)
- Saturación post-render con ffmpeg `eq=saturation=1.25` por defecto
- Subtítulos karaoke palabra-a-palabra con preset `PRONOSTICOS_SUB_STYLE`
  (Impact bold, lowercase, sin píldora, posición Y 78%)

---

## Nicho 3 — Quitar Copy

Sube un vídeo, detecta los subtítulos originales, los enmascara y añade
nuevos con estilo viral. Usa [`src/video_remover.py`](src/video_remover.py).
No depende de Redis ni de assets externos.

---

## Programa 2 — TikTok Shop (en construcción)

**Briefing completo en [`TIKTOK_SHOP_MODULE.md`](TIKTOK_SHOP_MODULE.md)** —
fuente de verdad del módulo (arquitectura, esquemas Redis, fases, prompts,
flujos por tier, Pilot Program, Drive layout).

**Propósito:** afiliado TikTok Shop España. Vídeos AI multi-cuenta × producto
con Seedance (3 tiers Atlas) o Veo3 / Nano Banana (prompt-only manual).
Independiente del Programa 1 — selector en sidebar separa ambos.

**Raíz Drive:** `TIKTOK_SHOP/` — HERMANA de `TIKTOK_CR/`, no anidada. Helper
canónico: `src/tiktok_shop/config.py:resolve_shop_root()` (autodetect con
override `TIKTOK_SHOP_ROOT_PATH` en .env). Estructura interna:
`_users/@user/products/{slug}/videos/` + `_products/{slug}/photos_source/`
+ `_products/{slug}/photos_generated/`.

**Módulos** (todos en [`src/tiktok_shop/`](src/tiktok_shop/)):
`api/{atlas_cloud,gemini,minimax_clone}.py`,
`pipeline/{analyzer,strategist,seedance_director,seedance_renderer,veo3_director,nano_banana_prompt_generator,editor,drive_uploader}.py`,
`prompts/*.md`, `repos/*_repo.py`, `services/{cost_calculator,pilot_tracker,tier_selector}.py`,
`utils/{duration_splitter,image_url_provider,photo_quality}.py`,
`ui/{shop_router,tab_*}.py`.

**Redis** (prefijo `tiktok_shop:`): `user:`, `product:`, `generation:`, `voice:`.
Cola unificada con Creator Reward via `JobMode.TIKTOK_SHOP`.

**Tiers** (5, ver [`config.py`](src/tiktok_shop/config.py)):
🟢 `standard` ($0.018/s i2v) · 🟡 `advanced` ($0.047/s i2v) · 🔴 `pro`
($0.072/s ref2v multi-shot) · 🟣 `veo3_prompt_only` · 🍌 `nano_banana_prompt_only`.
Imágenes a Atlas como **base64 inline** (los 3 tiers). Pro acepta hasta 9 refs.

**Críticas:** `ai_disclosure: true` siempre · presencia humana parcial · Pilot
Program máx 5 shoppable/semana (tracker en `services/pilot_tracker.py`).

---

## Variables de entorno (`.env`)

```env
# === Programa 1 — Creator Reward ===
# Path raíz de assets CR (Drive sincronizado). Auto-detect si no se define
# (escanea "Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_CR/TIKTOK_ASSETS").
# TIKTOK_ROOT_PATH="H:/Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_CR/TIKTOK_ASSETS"

# === Programa 2 — TikTok Shop ===
# Path raíz TikTok Shop. HERMANO de TIKTOK_CR (no anidado). Auto-detect si
# no se define (escanea "Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP").
# TIKTOK_SHOP_ROOT_PATH="H:/Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP"

# Atlas Cloud (Seedance — los 3 tiers Standard/Advanced/Pro). URL default oficial.
ATLASCLOUD_API_KEY=...
# ATLASCLOUD_BASE_URL=https://api.atlascloud.ai/api/v1   # opcional override

# === Compartido entre programas ===
OPENAI_API_KEY=...                   # Presidentes — guion JSON
MINIMAX_API_KEY=...                  # TTS — los 3 nichos CR + TikTok Shop
MINIMAX_GROUP_ID=...
MINIMAX_VOICE_ID=...                 # voz default (inglesa, Presidents)
PRONOSTICOS_VOICE_ID=Spanish_*       # opcional — override Pronósticos

# Gemini — TikTok Shop dual-key con fallback (FREE → PAID si 429); legacy
# `GOOGLE_GEMINI_KEY` lo usa Creator Reward y solo se reusa si no hay FREE/PAID.
GOOGLE_GEMINI_KEY_FREE=AIza...       # proyecto sin billing (free tier)
GOOGLE_GEMINI_KEY_PAID=AIza...       # proyecto con billing (~5€/mes)
GOOGLE_GEMINI_KEY=...                # legacy compartido con CR

# Upstash Redis (Pronósticos prefijo `betai:`, TikTok Shop prefijo `tiktok_shop:`)
UPSTASH_REDIS_REST_URL=https://xxxxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=AX...
REDIS_PREFIX=betai:                  # default — solo afecta a Pronósticos

# APIs stock Pronósticos (opcionales)
PEXELS_API_KEY=...
PIXABAY_API_KEY=...

# Opcional TikTok Shop
# TIKTOK_SHOP_MONTHLY_BUDGET_USD=50   # alerta dashboard al 80%

# === Programa 3 — Editor Auto ===
# Path raíz TikTok Editor. HERMANO de TIKTOK_CR/TIKTOK_SHOP. Auto-detect si
# no se define (escanea "Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_EDITOR").
# TIKTOK_EDITOR_ROOT_PATH="H:/Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_EDITOR"
# EDITOR_AUTO_REDIS_PREFIX=editor_auto:   # default
# OPENAI_API_KEY ya definida arriba — silence_cutter usa gpt-4o (mejor calidad)
```

---

## Configuración de la sidebar

La sidebar muestra solo los bloques relevantes al programa+nicho activo:

### Programa 1 — Creator Reward

Sidebar tiene: 🎯 Estrategia & Nicho, 🎥 Resolución (siempre); + 🎥 Motor
Animación, 📝 Subtítulos karaoke, 🎣 Hook box (solo Presidentes). Pronósticos
tiene controles dedicados en área principal (voz, SFX, overlays, saturación,
carrusel, intro, selector de versión + cola).

### Programa 2 — TikTok Shop

Sin sidebar — todo en tabs del área principal: Productos / Usuarios /
Generar Vídeo / Voces / Histórico (ver [`src/tiktok_shop/ui/`](src/tiktok_shop/ui/)).

---

## Convenciones

- **Imports en orden**: stdlib → terceros → `src.` → relativo. Excepción:
  `import streamlit as st` y `from dotenv import load_dotenv` siempre cerca
  del entry point.
- **Logging UI**: el pipeline acepta `log_callback`. La función
  `_noop = lambda _: None` es el default si nadie la pasa.
- **Errores defensivos**: el pipeline NUNCA aborta por falta de un asset
  opcional (perfil.png, sfx, logos). Solo loguea aviso y continúa.
- **Variables ASCII en código**: nombres de variable sin acentos (`competition_focus`
  no `competición_focus`). Strings y comentarios en español sí pueden tener acentos.
- **Slugs de carpetas de stock**: minúsculas, no-alfanumérico → `_`, sin acentos.
  Helper: `src/pronosticos/stock_search.py:_slug()`.
- **Versiones de vídeo**: nombres de output incluyen sufijo `_v1`/`_v2`/`_v3`
  cuando hay varias versiones del mismo día.
- **Aislamiento entre programas**: NUNCA mezclar lógica de Creator Reward y
  TikTok Shop. Reusar solo módulos transversales (MiniMax, FFmpeg, Whisper,
  Redis, logging). Cualquier cambio en un programa no debe romper el otro.
- **System prompts en archivos `.md`**: todos los prompts de TikTok Shop viven
  en `src/tiktok_shop/prompts/*.md`, NUNCA hardcoded en el código.
- **Frontend mobile-first**: toda UI nueva/modificada debe diseñarse y
  validarse para móvil además de desktop. Grids `grid-cols-2 sm:grid-cols-N`,
  diálogos con `w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto`, texto
  `text-xs sm:text-sm`, valores largos con `truncate`/`break-words`. La app
  se usa también desde móvil.
- **Cost tracking obligatorio**: TODA llamada a API externa con coste (OpenAI,
  MiniMax, Atlas Cloud, …) debe pasar por un `record_*` de
  [`src/cost_tracking.py`](src/cost_tracking.py). El runner ya envuelve cada
  job con `start_job`/`finalize_and_persist` vía `dispatch_job`. Al añadir
  un MODO o API nueva: (1) si la API no existe aún, añade tarifa + helper
  `record_<api>` con la tarifa vigente; (2) llama al helper justo tras el
  response real (con tokens/chars/segundos reales del provider). El panel
  `/costs` mostrará el desglose automáticamente — no hace falta tocar UI.

---

## Índice de documentación

| Archivo | Contenido |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Este archivo — contexto general, programas, env vars, convenciones |
| [`ADDING_PROGRAM.md`](ADDING_PROGRAM.md) | **Checklist para añadir un programa nuevo** (touchpoints API + runner + Redis + frontend + cost + deploy + tests + docs) |
| [`TIKTOK_SHOP_MODULE.md`](TIKTOK_SHOP_MODULE.md) | Programa 2 — arquitectura completa, esquemas Redis, prompts, Pilot Program |
| [`EDITOR_AUTO_MODULE.md`](EDITOR_AUTO_MODULE.md) | Programa 3 — flujo modular, tools registry, Silero VAD + OpenAI GPT-4o |
| [`PronosticosAuto.md`](PronosticosAuto.md) | Nicho Pronósticos — schema Redis bet-ai-master, segmentos, overlays |
| [`DEV_SETUP.md`](DEV_SETUP.md) | Arranque local (uvicorn + npm run dev), troubleshooting WS/cache |
| [`deploy/README.md`](deploy/README.md) | Despliegue VPS Hetzner + Docker stack + Tailscale Funnel + webhook |
| [`deploy/SERVER_ACCESS.md`](deploy/SERVER_ACCESS.md) | Runbook SSH al server (IP, paths, comandos comunes) |
| [`learnings.md`](learnings.md) | Historial técnico (1 línea por aprendizaje/fix) — **escribir al resolver bug o patrón nuevo** |
| [`tasks.md`](tasks.md) | TODO pendientes — mover a `## ✅ Done` al cerrar |
| [`README.md`](README.md) | Onboarding general del repo |

## Estructura por programa

Cada programa vive aislado en `src/<programa>/` con: `config.py`, `models/`,
`repos/`, `services/`, `pipeline/`, `prompts/*.md`. **Nunca se comparte
lógica entre programas** — solo módulos transversales (`src/locutor.py`,
`src/cost_tracking.py`, `src/fonts_registry.py`, `src/queue/*`,
`src/subtitles*`, etc.).

API: `src/api/routers/<programa>/` + `src/api/schemas/<programa>/`.
Frontend: `frontend/app/<programa>/` + `frontend/lib/queries/<programa>.ts`.

## Mantenimiento de este archivo

Actualiza CLAUDE.md cuando: módulo nuevo/eliminado en `src/`, env vars que
cambian, schema Redis, assets esperados, nicho o programa nuevo.
NO por: bugfixes, refactors, ajustes de parámetros, lo derivable del código.
Cap 250 líneas — mover detalles a `.md` específico si crece (p. ej.
`ADDING_PROGRAM.md` recoge la guía completa de "añadir programa").

### Memoria y Tareas
- **Lectura**: Lee `tasks.md` para pendientes y `learnings.md` para historial técnico.
- **Escritura Autónoma**: Al resolver un bug o implementar un patrón técnico nuevo, añade obligatoriamente un registro de 1 línea en `learnings.md`. Al finalizar una tarea, muévela a la sección `## ✅ Done` en `tasks.md`.
