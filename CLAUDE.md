# CLAUDE.md — Contexto del proyecto

> Este archivo se carga automáticamente al abrir el proyecto. Mantenlo conciso —
> cada línea consume contexto en cada sesión.

## 🦴 Modo CAVEMAN (ACTIVO)
Regla estricta: Respuestas de 1-2 líneas máximo. Cero explicaciones, cortesías o resúmenes. Solo tool calls y confirmación de archivos modificados.

## Resumen del proyecto

`TikTok_Automation_Python` — fábrica Streamlit que genera vídeos virales 9:16
para TikTok. **4 programas principales** seleccionables en la sidebar (Creator
Reward / TikTok Shop / Editor Auto / Tiktok Shop AI Pro), cada uno con sus
nichos.

### Programa 1 — Creator Reward (existente)

| Nicho | Modo | Propósito |
|---|---|---|
| 🏛️ Presidentes Top 5 | `PRESIDENTS_TOP5` | Rankings de presidentes USA con guion IA + assets locales |
| 📊 Pronósticos Diarios | `PRONOSTICOS_DIARIOS` | Vídeos de pronósticos deportivos desde Redis (bet-ai-master) |
| 🛡️ Quitar Copy | `COPYRIGHT_CLEANER` | Re-subtitula vídeos para evadir copyright |
| 🏗️ Construcción POV | `CONSTRUCCION_POV` | Vídeo input → guion Gemini 1ª persona → voz MiniMax EN + anti-copy + subs |
| 🔧 Herramientas · Voces | (sin modo) | Hub global voces MiniMax: presets ES/EN + clonado reutilizable entre modos |

### Programa 2 — TikTok Shop (en construcción)

| Función | Modo | Propósito |
|---|---|---|
| 🛒 Generador Shop | `TIKTOK_SHOP` | Vídeos affiliate AI con Seedance/Veo3, multi-cuenta, multi-producto |

### Programa 3 — Editor Auto

| Función | Modo | Propósito |
|---|---|---|
| ✂️ Editor Auto | `EDITOR_AUTO` | Edita vídeo input con flujo configurable de herramientas componibles por usuario (subs, cortador silencios + IA, ...) |

### Programa 4 — Tiktok Shop AI Pro

| Función | Modo | Propósito |
|---|---|---|
| 🚀 Viralización 1K | `VIRALIZACION_BATCH` | Vídeos POV/reacción en lote (gancho + paisajes) por ponente, sin repetir recursos, para llegar a 1000 seguidores |
| 🎙️ POV BOF Largo | `NICHO_POV_BOF_LARGO_VIDEO` | Como POV BOF pero la voz es un guion escrito por IA para ESE producto y locutado con Fish; dura ~20s, así que van DOS clips de 10s |
| 🧪 Cuenta Piloto | `CUENTA_PILOTO_VIDEO` | Productos que crea el operador SUBIENDO las dos fotos (no de Drive), por usuario y con VARIOS vídeos por producto; vídeo orgánico + edición del POV BOF |
| 🎯 Nicho POV BOF | (sin modo — fase 1) | Navega el Drive COMPARTIDO "Productos España" y lleva el progreso de qué carpeta de producto ya está hecha |
| 🎨 Creativos Pro | (sin modo — no edita vídeo) | Módulo 13: un creativo publicitario por producto. Mismo catálogo que POV BOF (fuentes, fotos, textos, hashtags, escaparate, vendidos); solo cambia el prompt y el formato 3:4 |
| 🖼️ Carruseles | (sin modo — no edita vídeo) | Módulo 14: carrusel de DOS fotos (chica sorprendida + producto) con el texto quemado. Solo productos donde la chica pueda estar EN el sitio |
| 🧢 Nicho Gorras | (sin modo — no edita vídeo) | Módulo 11: solo listar gorras + textos + prompts; el vídeo se publica tal cual |
| 🎬 Nicho BOF Cinematográfico | `NICHO_BOF_CINE_VIDEO` | Módulo 10: como POV BOF pero sin mano — DOS clips de 5s con paneo, pegados y cuadrados por velocidad |
| 👗 Nicho Ropa Con Personas | `NICHO_ROPA_PERSONAS_VIDEO` | Módulo 7: SOLO ropa de mujer, puesta por una modelo creada con IA (ficha JSON por usuario) |
| 👕 Nicho Ropa Sin Personas | `NICHO_ROPA_VIDEO` | Módulo 8 del curso: prendas de una carpeta de Drive compartida POR ENLACE → textos/caption → prompts (vídeo con y sin manos) → montaje 9:16 SIN texto quemado y MUDO |

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
`pipeline/{analyzer,strategist,seedance_director,seedance_renderer,veo3_director,nano_banana_prompt_generator,carousel_director,editor,drive_uploader}.py`,
`prompts/*.md`, `repos/*_repo.py`, `services/{cost_calculator,pilot_tracker,tier_selector,discovery_service,ads_signal,creation_pack}.py`,
`utils/{duration_splitter,image_url_provider,photo_quality}.py`,
`ui/{shop_router,tab_*}.py`.

**Redis** (prefijo `tiktok_shop:`): `user:`, `product:`, `generation:`, `voice:`, `discovery:`, `plan:`.

**🔍 Radar de Productos** (tab `ui/tab_radar.py`): descubre productos ganadores
con inyección de ADS + pocos creadores (estrategia GMV Max) vía EchoTik
(`ECHOTIK_API_USER`/`ECHOTIK_API_PASSWORD`). `services/discovery_service.py`
escanea ranklist/keywords → `services/ads_signal.py` puntúa (demanda, pocos
creadores, ADS, momentum, comisión) → importa a `Product`. Genera también
carruseles (`pipeline/carousel_director.py` + `prompts/carousel_director.md`).
Kalodata NO tiene API barata (solo Enterprise) — el proxy de ADS se infiere de
los vídeos: proxy EchoTik (views altas + engagement bajo + ventas) Y/O la
ETIQUETA AD real de TikTok leída vía Apify (`apify_cloud.extract_ad_flag` +
`search_product_ad_videos`) — `ads_signal.ads_injection_signal` combina ambas en
`gmv_max_likelihood` (0-100) + `probable_boosted`. Selector de fuente en el scan.
`services/creation_pack.py:build_pack/plan_week` deja el producto LISTO PARA
CREAR: descarga fotos (image_search), análisis, research de vídeos ganadores,
genera estilos de vídeo (preset_generator) + carruseles + prompt Nano Banana,
y escribe `_products/<slug>/PLAN.md` + `prompt_templates/` (+ `_plans/week_*.md`
repartiendo productos por día). Persiste un `WeekPlan` (`models/week_plan.py`,
`repos/plan_repo.py`, key `plan:`) → sub-tab "📅 Calendario" muestra qué producto
probar cada día con checkbox "probado". `Product.origin` ("manual"|"radar")
distingue los importados por el Radar de los creados a mano (filtro + badge en
pestaña Productos). UI Radar: sub-tabs "🔎 Descubrir / 🗓️ Plan 7 días /
📅 Calendario / 🎠 Carruseles".
Cola unificada con Creator Reward via `JobMode.TIKTOK_SHOP`.

**Tiers** (5, ver [`config.py`](src/tiktok_shop/config.py)):
🟢 `standard` ($0.018/s i2v) · 🟡 `advanced` ($0.047/s i2v) · 🔴 `pro`
($0.072/s ref2v multi-shot) · 🟣 `veo3_prompt_only` · 🍌 `nano_banana_prompt_only`.
Imágenes a Atlas como **base64 inline** (los 3 tiers). Pro acepta hasta 9 refs.

**Críticas:** `ai_disclosure: true` siempre · presencia humana parcial · Pilot
Program máx 5 shoppable/semana (tracker en `services/pilot_tracker.py`).

---

## Programa 4 — Tiktok Shop AI Pro

**Briefing completo en [`VIRALIZACION_MODULE.md`](VIRALIZACION_MODULE.md)** —
fuente de verdad del módulo (arquitectura, banco de candidatos, estilos,
jitter, numeración, schema Redis).

**Propósito:** vídeos POV/reacción en lote (ponente + b-roll de paisajes)
para llegar a 1000 seguidores en TikTok Shop — técnica anti-copyright
"voice-over + b-roll". Sin Redis de negocio como TikTok Shop, solo tracking
de uso; sin APIs de pago (todo ffmpeg + Whisper local + rclone) → **sin cost
tracking, a propósito** (ver VIRALIZACION_MODULE.md).

**Módulos** (todos en [`src/viralizacion/`](src/viralizacion/)):
`config.py` (paths locales + parámetros de render/jitter),
`repos/{redis_base,usage_repo}.py` (tracking de candidatos ya usados, prefijo
`viralizacion:`), `services/{allocator,drive_uploader}.py`,
`pipeline/{resource_scanner,transcriber,styles,renderer,batch}.py`.

**Ponentes:** Pablo Motos y Víctor Küppers (banco de gancho + audios propios,
paisajes compartidos). Assets en carpeta LOCAL persistente
(`VIRALIZACION_ASSETS_PATH`, NO Drive montado, NO `/tmp`) — vídeo de gancho
por ponente + audios + vídeo de paisajes (~61min) + música de fondo.

**3 estilos de subtítulo/filtro** rotando por ronda (A Clásico / B Reveal
letra-a-letra con glow / C Cinemático karaoke por palabra + letterbox) +
jitter anti-fingerprint (zoom, duración de paisaje, transición, EQ) por
clip/vídeo para que la plantilla no deje huella reconocible.

**Nunca repite** gancho ni tramo de paisaje por ponente (Redis SET de
índices usados, asignación con `PoolExhaustedError` claro si se agota).

Cola unificada con Creator Reward vía `JobMode.VIRALIZACION_BATCH`.

### Nicho POV BOF (mismo programa, fase 1)

Navegador del Drive **compartido conmigo** `Productos España` (2 fuentes:
`1 Prod Aleatorios` / `2 Prod Aleatorios 2`) con progreso por carpeta de
producto. **Todavía no genera vídeos.**

Módulos en [`src/nicho_pov_bof/`](src/nicho_pov_bof/): `config.py`,
`repos/{redis_base,progress_repo,product_repo}.py` (prefijo `nicho_pov_bof:`),
`services/{drive_client,photo_pairing,text_extractor,audio_bank,backup_sync,product_url}.py`,
`pipeline/{duration_match,video_editor}.py`, `prompts/*.md`.
API: `/api/v1/nicho-pov-bof/*`.

`services/product_url.py` averigua la ficha de TikTok Shop
(`https://www.tiktok.com/view/product/<id>`) desde el título + la tienda. La
ÚNICA fuente que da el ID es EchoTik (se descartaron URL canónica, Gemini con
búsqueda web, Apify, DuckDuckGo, fastmoss, kalodata y la web/API de TikTok) y
cada búsqueda GASTA UNA LLAMADA del plan — por eso va con botón manual por
producto, cachea en Redis y descarta resultados con poco parecido. El plan
gratis son 100 llamadas/MES, así que una cuenta seca vuelve a servir al mes:
`tiktok_shop/repos/echotik_cuentas_repo.py` guarda el banco de cuentas con la
fecha de su primera llamada (`echotik:cuentas`) y la UI deja volver a la que ya
haya renovado.

Dos cosas no obvias:
- El Drive es *shared-with-me* → **no aparece en el mount FUSE**; se lee por
  CLI con `--drive-shared-with-me`.
- Dentro de una carpeta hay **nombres de fichero duplicados** (`2.PNG` dos
  veces). El identificador canónico de una foto es su **file ID**, y se
  descarga con `rclone backend copyid`.

Tiene dos fuentes propias más, que NO son del Drive del curso y viven en el
Drive montado: **«🌐 Productos Web»** (`productos_web`), que se llena
importando los ZIP que publica la web del curso —carpetas de diez, y el ZIP
trae la convención AL REVÉS: `N` es la ficha y `N.1` la limpia—, y «Mis
productos», que NO es del curso: la sube el
operador (foto limpia + ficha) y vive en su Drive
(`TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF/mis_productos/`), en carpetas de 10. Las
fotos se guardan con el MISMO convenio de nombres del Drive compartido
(`3.png` / `3(1).png`) para que emparejado, textos, ficha y montaje funcionen
sin código especial (`services/mis_productos.py`).

**TODOS los vídeos son de DOS clips**, montados con el editor del POV BOF Largo
(`montar`: cuadra cada clip con su parte de la voz y salta del uno al otro en
una pausa del habla). Sale de medir el banco: los audios duran 9,7-13,9s
(mediana 12) y un clip da 8s, o 9,6 estirado un 20%; con uno solo faltaba trozo
en todos y el hueco lo rellenaba el rebobinado (`_build_pingpong`) — en un vídeo
de 12s, un tercio era ese rebote.

TODOS los vídeos los locuta el guion escrito para ESE producto
(`prompts/guion_producto.md`, ~190 car → ~10s, Fish) — `JobMode.NICHO_POV_BOF_VIDEO`.
Lo único que cambia es la CTA, que nombra el pago a plazos y/o el envío gratis
según lo que el producto CUMPLA (`config.hay_plazos` y
`nicho_pov_bof_largo.config.hay_envio_gratis`: los leen de la ficha y caen al
precio —40 € y 10 €— si la captura no lo enseña). Los flags
`guion_producto_plazos` / `guion_producto_envio` guardan con cuál se escribió;
con las dos promesas el guion se va a ~259 car (~14s) porque en 10s no caben. Los cinco textos de Klarna (`prompts/guiones_plazos.md`,
`JobMode.NICHO_POV_BOF_PLAZOS_VIDEO`) ya no se usan: son genéricos —no nombran
el producto— y de 253-274 car, o sea vídeos de 13-20s donde se piden 10.

`Productos España` es SOLO LECTURA. El progreso vive en Redis, no en Drive.
Las salidas futuras irán a `TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF/`.

### Nicho Ropa Sin Personas (mismo programa, módulo 8)

Módulos en [`src/nicho_ropa/`](src/nicho_ropa/) (prefijo Redis `nicho_ropa:`).
API: `/api/v1/nicho-ropa/*`. Diferencias con POV BOF:
- La carpeta de fotos se comparte **por enlace**, no está en "Compartido
  conmigo" → se lee con `--drive-root-folder-id`, no con `--drive-shared-with-me`.
- Es UNA sola carpeta con todas las prendas dentro (`NICHO_ROPA_FOLDER_ID`).
- El vídeo **no lleva ningún texto quemado** y sale **mudo** (la música la pone
  el operador al publicar); se le puede añadir voz hombre/mujer si se pide.
- El prompt de vídeo tiene versión CON y SIN manos: se guarda un solo texto y
  la variante sin manos se deriva quitando `config.LINEA_MANOS`.
- Además de las 4 carpetas del curso (planas), acepta las de la web por ZIP:
  cada una es una carpeta MÁS del selector con slug `mujer_web__Carpeta 23`
  (`services/prendas_web.py`), así el resto del nicho no se entera del nivel
  nuevo. Reusa el importador del POV BOF para no duplicar la inversión de
  nombres. Pero **son dos pantallas**, no una: en la web la prenda va PUESTA
  frente al espejo, así que las carpetas del ZIP viven en "Ropa Mujer/Hombre"
  (`/tiktok-shop-ai-pro/nicho-ropa-web`) con su prompt y conservando la voz
  del clip, y "Sin humanos" se queda con las 4 del Drive. Mismo backend y
  mismo Redis: las separa el flag `web` de `/carpetas`, y la pantalla es el
  mismo componente con `variante`.

Reutiliza del POV BOF `photo_pairing`, la descarga de fotos por file ID y el
motor de extracción (`text_extractor.extract_from_pairs`) — cambia el prompt.

### Nicho Ropa Con Personas (mismo programa, módulo 7)

Módulos en [`src/nicho_ropa_personas/`](src/nicho_ropa_personas/) (prefijo
Redis `nicho_ropa_personas:`). API: `/api/v1/nicho-ropa-personas/*`. La prenda
va PUESTA por una modelo generada con IA. Usa las MISMAS carpetas de prendas
que el módulo 8 (se importan de `nicho_ropa.config`): la foto vale para los dos
nichos, cambia el prompt.

Paso propio que no tiene ningún otro nicho: **crear la chica**. El operador
sube una foto de internet, Gemini la mete en la plantilla del curso
(`prompts/plantilla_chica.json`) y sale una ficha JSON que se guarda con nombre
y se copia en cada vídeo. Es **por usuario** — la cara es la identidad de la
cuenta. La plantilla ya trae el bloque `clothing`, así que crear a la chica y
vestirla con el producto es UN prompt, no dos.

Audios locutados (5 voces de mujer, se sortea una):
`TIKTOK_SHOP_AI_PRO/Nicho_Ropa_Personas/audios/mujer/`.

### Nicho POV BOF Largo (mismo programa)

Módulos en [`src/nicho_pov_bof_largo/`](src/nicho_pov_bof_largo/) (prefijo
Redis `nicho_pov_bof_largo:`). API: `/api/v1/nicho-pov-bof-largo/*`. Es el POV
BOF con la voz cambiada: en vez de una frase genérica del banco, un **guion
escrito para ESE producto** (prompt del curso, literal en `prompts/guion.md`)
y locutado con **Fish Audio** (`FISH_API_KEY`, modelo gratuito
`s2.1-pro-free`). Como el guion dura ~20s y no ~11, el vídeo son **DOS clips
de 10s** pegados; la duración la manda la voz y el vídeo se recorta a ella.

Si el producto pasa de `PRECIO_MIN_PLAZOS`, al guion se le añade el bloque de
`prompts/guion_plazos.md` (una frase de financiación, sin nombrar la pasarela):
misma estructura del curso, un párrafo más en el prompt. `guion_plazos` guarda
en qué modo se escribió y se reescribe si el precio lo cambia.

Su pantalla es un CALCO de la del POV BOF (misma UI y flujo) — solo cambia que
se sube el guion + DOS clips. Comparte catálogo/carpetas/textos/fotos con el POV
BOF (reusa sus endpoints), pero el **progreso es individual**: carpeta hecha
(`progress_repo` propio + `/complete`), subido y guion/clips/vídeo viven en
`nicho_pov_bof_largo:` (`/producto/estado`). Dos progresos son GLOBALES a
propósito (ver "Escaparate y vendidos" abajo).

### Escaparate y vendidos — transversales a TODOS los nichos

Dos cosas NO son de ningún nicho: se hacen una sola vez por producto porque la
cuenta de TikTok es la misma. Las dos viven en
[`src/nicho_pov_bof/repos/product_repo.py`](src/nicho_pov_bof/repos/product_repo.py)
y los demás nichos las reusan (no dupliques índices por nicho):

- **Escaparate** — `escaparate:index[:usuario]`, clave `norm(tienda)|norm(titulo)`
  (`clave_escaparate` / `escaparate_index` / `set_escaparate`). El mismo producto
  sale repetido en varias carpetas del Drive y se graba con varios nichos:
  marcado en uno, aparece marcado en todos. Sin textos extraídos la clave es
  vacía y no deduplica.
- **Vendidos** — `vendidos:index[:usuario]` + `vendido:[u:<usuario>:]<ref>`,
  un ranking por persona; **no** se clasifica por nicho (`NICHOS_VENTA` queda
  solo por compatibilidad del dato antiguo). La carpeta "Top vendidos" del
  Drive sí es común: es un catálogo, no un progreso.

Ambos son **por usuario**: Ana y Mauro son otras personas con su propia cuenta,
y una venta o un escaparate es el resultado de SU cuenta. El histórico va en la
clave sin sufijo, que es la de `ness` (mismo criterio que el progreso de
carpetas).

Cosas que ya costaron una vez:
- El documento del curso pide 260 caracteres "para 15 segundos", pero su propio
  ejemplo tiene 357 y a 18,2 car/s eso son 20s. **No se recorta**: forzarlo con
  reintentos deja el guion telegráfico. Solo se avisa.
- Los textos del producto (título, tienda, caption) se **leen** del Nicho POV
  BOF, no se re-extraen: costarían las llamadas de Gemini dos veces.
- La cadena de nivelado del POV BOF (`TP=-1.5`) NO vale para Fish: daba +0,20
  dBTP. Aquí es `TP=-2.0` con limitador 0.89.

### Nicho Carruseles (mismo programa, módulo 14)

Módulos en [`src/nicho_carruseles/`](src/nicho_carruseles/) (prefijo Redis
`nicho_carruseles:`). API: `/api/v1/nicho-carruseles/*`. **No edita vídeo**:
publica un carrusel de DOS fotos con el texto quemado encima (PIL, sin cola —
es un PNG sobre un JPEG).

Lo que no tiene ningún otro nicho:
- **Filtro de categoría.** No todo producto funciona en este formato: hay un
  paso de clasificación con Gemini (texto suelto sobre los títulos YA
  extraídos, sin imágenes) + interruptor manual por producto. Al filtrar, una
  carpeta de diez se queda en dos o tres: el listado de carpetas enseña cuántos
  aptos tiene cada una para no abrirlas en balde.
- **La chica de la casa**: se sube la foto de una chica y Gemini saca su ficha
  JSON (`services/chica_ficha.py`, idea del Nicho Ropa Con Personas). Con ella,
  el prompt para crear la referencia de cada escenario lleva a ESA chica dentro
  — un párrafo no clava a una persona y la referencia es lo que manda en
  imagen-a-imagen.
- **La foto 1 NO depende del producto, solo del SITIO.** Es una chica
  sorprendida generada en Google Flow, y lo único que tiene que encajar es
  dónde está: `generico`, `cama`, `sofa`, `exterior`, `cocina`, `bano`,
  `coche` y `escritorio` — un prompt por escenario
  (`prompts/foto_chica_<escenario>.md`), y la categoría decide cuál le toca.
  Las tandas se suben POR ESCENARIO y para TODOS los catálogos a la vez, y se
  reparten por orden entre los productos que no tienen. La foto 2 —el
  producto— sí es de cada uno y se sube en su tarjeta.
- Las fotos viven en el Drive montado
  (`TIKTOK_SHOP_AI_PRO/Nicho_Carruseles/<usuario>/`), y el original y la
  versión con texto van en carpetas distintas: quemar sobre lo quemado deja el
  texto doble. El vínculo foto↔producto es el NOMBRE del fichero
  (`<fuente>__<carpeta>__<producto>.jpg`), no un índice en Redis.

Comparte con el POV BOF catálogo, textos, hashtags, escaparate y vendidos
(igual que Creativos Pro). Progreso y "subido" son propios.

### Cuenta Piloto (mismo programa, no es un módulo del curso)

Módulos en [`src/cuenta_piloto/`](src/cuenta_piloto/) (prefijo Redis
`cuenta_piloto:`). API: `/api/v1/cuenta-piloto/*`. Vídeo ORGÁNICO (la imagen no
la genera IA; la voz sí) con la MISMA edición del POV BOF — se reutiliza
`build_video` tal cual.

Tres cosas que no hace ningún otro nicho:
- **El producto nace de una SUBIDA.** Las dos fotos (limpia + ficha) las sube el
  operador; no hay Drive que recorrer ni emparejado que adivinar. Las fotos NO
  pueden ir a `api_uploads/` (se purga a las 24h): van al Drive montado en
  `TIKTOK_SHOP_AI_PRO/Cuenta_Piloto/<usuario>/`.
- **Es por usuario**: un documento Redis por operador, sin doc compartido.
- **VARIOS vídeos por producto** — `videos` es una LISTA y se añade con
  `product_repo.add_video()` bajo cerrojo. En el resto de nichos hay un solo
  `video_path` y el segundo montaje pisa al primero.

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
# ATLAS_POLL_TIMEOUT_S=7200                              # default 2h. Sube si Standard
                                                         #            tier suele tardar más.

# fal.ai — fallback automático de Atlas Cloud. Mismo modelo Seedance pero
# en otro hosting con queue independiente. Se activa solo si Atlas falla.
# Si no está configurado, jobs fallidos en Atlas propagan el error.
# FAL_API_KEY=...
# FAL_POLL_TIMEOUT_S=1800                                # default 30 min

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

# === Programa 4 — Tiktok Shop AI Pro (Viralización) ===
# Path raíz LOCAL (no Drive) de assets: gancho/audios/paisajes/música.
# Auto-detect si no se define (prueba "~/viralizacion_assets").
# VIRALIZACION_ASSETS_PATH="/home/nebulabsai/viralizacion_assets"
# VIRALIZACION_REDIS_PREFIX=viralizacion:   # default
# CUENTA_PILOTO_REDIS_PREFIX=cuenta_piloto:  # default
# FISH_API_KEY=sk-fish-...                   # TTS del POV BOF Largo
# NICHO_POV_BOF_LARGO_REDIS_PREFIX=nicho_pov_bof_largo:  # default
# ZOOM_MARCA_AGUA=1.05                       # ampliación que se come la marca
# ESQUINA_MARCA_AGUA=abajo-derecha           #   de agua del generador de vídeo
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

### Programa 4 — Tiktok Shop AI Pro

Grupo de sidebar propio (frontend Next.js) separado de "TikTok Shop" —
`basePath: /tiktok-shop-ai-pro`. Un único item hoy: "Viralización 1K"
(`/tiktok-shop-ai-pro/viralizacion`), formulario simple (ponentes + cantidad
+ nombre de cuenta + rondas con música). Pensado para acumular más
herramientas del mismo grupo en el futuro.

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
  Excepción explícita: Programa 4 (Viralización) no usa ninguna API de pago
  (ffmpeg/Whisper local/rclone) → sin `record_*`, a propósito (ver
  VIRALIZACION_MODULE.md).

---

## Índice de documentación

| Archivo | Contenido |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Este archivo — contexto general, programas, env vars, convenciones |
| [`ADDING_PROGRAM.md`](ADDING_PROGRAM.md) | **Checklist para añadir un programa nuevo** (touchpoints API + runner + Redis + frontend + cost + deploy + tests + docs) |
| [`TIKTOK_SHOP_MODULE.md`](TIKTOK_SHOP_MODULE.md) | Programa 2 — arquitectura completa, esquemas Redis, prompts, Pilot Program |
| [`EDITOR_AUTO_MODULE.md`](EDITOR_AUTO_MODULE.md) | Programa 3 — flujo modular, tools registry, Silero VAD + OpenAI GPT-4o |
| [`VIRALIZACION_MODULE.md`](VIRALIZACION_MODULE.md) | Programa 4 — banco de candidatos sin repetir, 3 estilos de subtítulo, jitter anti-fingerprint, numeración de rondas |
| [`EDITOR_DEBUGGING.md`](EDITOR_DEBUGGING.md) | **Playbook de depuración del cortador de vídeo** — LEER antes de tocar `silence_cutter.py`: jerarquía de señales (silero>energía>Whisper), pipeline, casuística de bugs reales (proteína…), cómo diagnosticar una queja, gotchas de cola/deploy, auto-corrección |
| [`PronosticosAuto.md`](PronosticosAuto.md) | Nicho Pronósticos — schema Redis bet-ai-master, segmentos, overlays |
| [`APK.md`](APK.md) | **APK Android (TWA)** — por qué TWA y no Capacitor (descargas), cómo se genera, cuándo hay que rehacerla, gotchas de Bubblewrap |
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
