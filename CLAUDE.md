# CLAUDE.md — Contexto del proyecto

> Este archivo se carga automáticamente al abrir el proyecto. Mantenlo conciso —
> cada línea consume contexto en cada sesión.

## 🦴 Modo CAVEMAN (ACTIVO)
Regla estricta: Respuestas de 1-2 líneas máximo. Cero explicaciones, cortesías o resúmenes. Solo tool calls y confirmación de archivos modificados.

## Resumen del proyecto

`TikTok_Automation_Python` — fábrica Streamlit que genera vídeos virales 9:16
para TikTok Creator Reward Program. **3 nichos** seleccionables en la sidebar:

| Nicho | Modo | Propósito |
|---|---|---|
| 🏛️ Presidentes Top 5 | `PRESIDENTS_TOP5` | Rankings de presidentes USA con guion IA + assets locales |
| 📊 Pronósticos Diarios | `PRONOSTICOS_DIARIOS` | Vídeos de pronósticos deportivos desde Redis (bet-ai-master) |
| 🛡️ Quitar Copy | `COPYRIGHT_CLEANER` | Re-subtitula vídeos para evadir copyright |

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

## Variables de entorno (`.env`)

```env
# Path raíz de assets (carpeta sincronizada con Drive). Opcional:
# si no se define, src/utils.py:resolve_tiktok_root() escanea las unidades
# del sistema buscando "Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_CR/TIKTOK_ASSETS".
# Solo fíjala para forzar una ubicación concreta.
# TIKTOK_ROOT_PATH="H:/Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_CR/TIKTOK_ASSETS"

# OpenAI (Presidentes — guion JSON)
OPENAI_API_KEY=...

# MiniMax (TTS)
MINIMAX_API_KEY=...
MINIMAX_GROUP_ID=...
MINIMAX_VOICE_ID=...                # voz por defecto (inglesa, Presidents)
PRONOSTICOS_VOICE_ID=Spanish_*       # opcional — override del nicho Pronósticos

# Gemini (legado de antes — Pronósticos NO lo usa)
GOOGLE_GEMINI_KEY=...

# Redis Upstash (Pronósticos lee de aquí)
UPSTASH_REDIS_REST_URL=https://xxxxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=AX...
REDIS_PREFIX=betai:                  # default

# APIs de stock (opcionales — sin ellas Pronósticos cae a fondo sólido)
PEXELS_API_KEY=...
PIXABAY_API_KEY=...
```

---

## Configuración de la sidebar

La sidebar muestra solo los bloques relevantes al nicho activo:

| Bloque | Presidentes | Pronósticos | Quitar Copy |
|---|---|---|---|
| 🎯 Estrategia & Nicho | ✅ | ✅ | ✅ |
| 🎥 Resolución | ✅ | ✅ | ✅ |
| 🎥 Motor Animación (v1/v2) | ✅ | — | — |
| 📝 Subtítulos karaoke | ✅ | — | — |
| 🎣 Hook box | ✅ | — | — |

Pronósticos tiene sus propios controles dedicados en el área principal:
voz, SFX (4: dinero/clink/cámara/BGM), overlay de ligas, saturación,
duración objetivo, carrusel pick, carpeta intro, edición efímera del guion,
selector de versión + cola.

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

---

## Mantenimiento de este archivo

Actualiza CLAUDE.md cuando:
- Se añada/elimine un módulo en `src/`
- Cambien las variables de entorno requeridas
- Cambie el schema de Redis o los nombres de assets esperados
- Se añada un nicho nuevo

NO actualizes CLAUDE.md por:
- Cambios menores de UI / refactors internos / bugfixes
- Ajustes de parámetros (volúmenes, sliders, etc.)
- Lo que se pueda derivar leyendo el código directamente

Mantén el archivo bajo 250 líneas. Si crece más, mueve detalles a un
markdown específico (ej: `docs/pronosticos.md`) y deja aquí solo el resumen
+ un link.

### Memoria y Tareas
- **Lectura**: Lee `tasks.md` para pendientes y `learnings.md` para historial técnico.
- **Escritura Autónoma**: Al resolver un bug o implementar un patrón técnico nuevo, añade obligatoriamente un registro de 1 línea en `learnings.md`. Al finalizar una tarea, muévela a la sección `## ✅ Done` en `tasks.md`.

