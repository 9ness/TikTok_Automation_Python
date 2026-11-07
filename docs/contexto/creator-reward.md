# Creator Reward — nichos 1 a 4 (Presidentes, Pronósticos, Quitar Copy, Construcción POV)

> Movido literal desde CLAUDE.md (nov 2026) para no cargarlo en cada chat. Se lee solo al tocar este tema.

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

## Nicho 4 — Construcción POV

**Flujo:** vídeo input (sin voz) → Gemini 2.5 Pro analiza el vídeo y devuelve
un guion narrado 1ª persona US English calibrado a la duración real → MiniMax
TTS (voz preset EN o clonada) → ffmpeg mux audio nuevo sobre vídeo → Whisper
alinea palabras → transformaciones visuales anti-copy (zoom, saturación,
metadata strip, opcional 1080p Lanczos) → render karaoke subs sobre el
resultado. Sin Redis, sin assets externos — todo en runtime.

**Módulos clave** (todos en [`src/construccion_pov/`](src/construccion_pov/)):
- `gemini_video.py` — cliente Gemini con upload de vídeo (Files API + polling
  ACTIVE + delete) y fallback dual-key FREE→PAID
- `script_generator.py` — calcula `target_chars` por duración (15.5 ch/s EN,
  cola silenciosa 4s) y construye el prompt desde `prompts/pov_script.md`
- `pipeline.py` — orquestador end-to-end con franjas de progreso

**Voces:** preset MiniMax inglés (`English_*` definidas en
[`tiktok_shop/config.py:DEFAULT_VOICE_PRESETS_EN`](src/tiktok_shop/config.py))
o clones globales gestionados desde `/creator-reward/tools/voices` (UI hub).

**Endpoints API:**
- `POST /api/v1/creator-reward/construccion-pov/enqueue` — multipart con
  vídeo + style subs + voice_id + anti-copy options
- `POST /api/v1/voices/clone` — sube sample → MiniMax voice_clone → guarda
  VoiceClone en Redis (índice `voice:index`)
- `GET  /api/v1/voices/{id}/sample` — MP3 cacheado para audicionar voz (sin
  auth, sirve `<audio src>`)
- `DELETE /api/v1/voices/{id}` — borra clones (presets bloqueados)

**Output:** `<output_folder>/CONSTRUCCION_POV/POV_<stem>_<ts>.mp4`.

---

Sidebar (Streamlit legacy):

### Programa 1 — Creator Reward

Sidebar tiene: 🎯 Estrategia & Nicho, 🎥 Resolución (siempre); + 🎥 Motor
Animación, 📝 Subtítulos karaoke, 🎣 Hook box (solo Presidentes). Pronósticos
tiene controles dedicados en área principal (voz, SFX, overlays, saturación,
carrusel, intro, selector de versión + cola).

