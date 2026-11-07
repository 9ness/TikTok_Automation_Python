# CLAUDE.md — Contexto del proyecto

> Este archivo se carga automáticamente al abrir el proyecto. Mantenlo conciso —
> cada línea consume contexto en cada sesión. El detalle de cada nicho/módulo vive en
> `docs/contexto/*.md` (texto literal): **si tu tarea toca uno de esos temas, léelo ANTES de tocar código.**

## 🦴 Modo CAVEMAN (ACTIVO)
Regla estricta: Respuestas de 1-2 líneas máximo. Cero explicaciones, cortesías o resúmenes. Solo tool calls y confirmación de archivos modificados.

## Resumen del proyecto

`TikTok_Automation_Python` — fábrica que genera vídeos virales 9:16 para TikTok
(API FastAPI + frontend Next.js; `main.py` es la UI Streamlit legacy, ya no se sirve). **4 programas**
aislados, cada uno con sus nichos. Tabla completa con todas las celdas largas:
[`docs/contexto/resumen-nichos-completo.md`](docs/contexto/resumen-nichos-completo.md).

| Programa | Nicho / modo | Propósito |
|---|---|---|
| 1 Creator Reward | 🏛️ Presidentes Top 5 `PRESIDENTS_TOP5` | Rankings de presidentes USA, guion IA + assets locales |
| | 📊 Pronósticos Diarios `PRONOSTICOS_DIARIOS` | Pronósticos deportivos desde Redis (bet-ai-master) |
| | 🛡️ Quitar Copy `COPYRIGHT_CLEANER` | Re-subtitula vídeos para evadir copyright |
| | 🏗️ Construcción POV `CONSTRUCCION_POV` | Vídeo input → guion Gemini 1ª persona → voz MiniMax EN + anti-copy + subs |
| | 🔧 Herramientas · Voces | Hub global de voces MiniMax: presets ES/EN + clonado |
| 2 TikTok Shop | 🛒 Generador Shop `TIKTOK_SHOP` | Vídeos affiliate AI con Seedance/Veo3, multi-cuenta, multi-producto |
| 3 Editor Auto | ✂️ Editor Auto `EDITOR_AUTO` | Edita vídeo input con flujo configurable de herramientas (subs, cortador de silencios + IA...) |
| 4 AI Pro | 📦 Mis tandas | Primero del menú: lo ya montado (POV BOF, Largo, Multimodo) de 10 en 10, con semáforo 🟢🟡🔴 antes de subir. Solo lee |
| | 🔁 Replicar viral · 🎞️ Replicar virales · 🖼️ Replicar carrusel | Copiar la fórmula de un viral (vídeo o carrusel de fotos) con un producto nuestro |
| | 🚀 Viralización 1K `VIRALIZACION_BATCH` | Vídeos POV/reacción en lote por ponente, sin repetir recursos |
| | 🎙️ POV BOF Largo `NICHO_POV_BOF_LARGO_VIDEO` | POV BOF con guion IA para ESE producto + voz Fish; 2 clips |
| | 🧪 Cuenta Piloto `CUENTA_PILOTO_VIDEO` | Productos que sube el operador (2 fotos), varios vídeos por producto |
| | 🎛️ Moda Mujer · Multimodo (`mm_*`) | Formatos mudos de 10 s/20 s y seis hablados de ropa, elegidos por producto por un agente |
| | 🎯 Nicho POV BOF | Navega el Drive COMPARTIDO "Productos España" y lleva el progreso por carpeta |
| | 🎨 Creativos Pro · 🖼️ Carruseles · 💬 Plantillas mensajes · 🧢 Gorras | Módulos 13/14/11 y mensajes a vendedores; sin edición de vídeo |
| | 🌐 Nicho General · UGC `NICHO_GENERAL_ESCENAS/VIDEO` | Módulo 9: anuncio de TRES clips pegados |
| | 🎬 BOF Cinematográfico `NICHO_BOF_CINE_VIDEO` · 👗 Ropa Con Personas `NICHO_ROPA_PERSONAS_VIDEO` · 👕 Ropa Sin Personas `NICHO_ROPA_VIDEO` | Módulos 10, 7 y 8 |

Punto de entrada: API `uvicorn src.api.main:app`; legacy `streamlit run main.py`.

## Detalle por nicho/módulo (leer ANTES de tocarlo)

| Tema | Lee | Gotchas que muerden |
|---|---|---|
| Presidentes, Pronósticos, Quitar Copy, Construcción POV (Programa 1) | [`creator-reward.md`](docs/contexto/creator-reward.md) + [`PronosticosAuto.md`](PronosticosAuto.md) | Pronósticos lee Redis `betai:` escrito por bet-ai-master; capas de audio/visual; voces MiniMax |
| Programa 2 TikTok Shop, Radar de productos, tiers Seedance/Veo3 | [`tiktok-shop-programa2.md`](docs/contexto/tiktok-shop-programa2.md) + [`TIKTOK_SHOP_MODULE.md`](TIKTOK_SHOP_MODULE.md) | `ai_disclosure: true`, Pilot Program máx 5/semana, EchoTik gasta llamadas |
| Viralización 1K y Nicho POV BOF (Drive "Productos España", catálogos del operador, reembolsables, marcas, guion y CTA) | [`ai-pro-viralizacion-pov-bof.md`](docs/contexto/ai-pro-viralizacion-pov-bof.md) + [`VIRALIZACION_MODULE.md`](VIRALIZACION_MODULE.md) | Drive compartido NO está en el mount FUSE (rclone `--drive-shared-with-me`); nombres de fichero duplicados → file ID; `Productos España` es solo lectura; todos los vídeos son de DOS clips |
| Ropa Sin Personas / Con Personas, Tienda Colores, guionista Gemini | [`ai-pro-ropa.md`](docs/contexto/ai-pro-ropa.md) | Carpeta por enlace (`--drive-root-folder-id`); sin texto quemado y mudo; dos pantallas (web vs Drive) |
| POV BOF Largo (estilos de guion épico/inversa/acción/regalo/viral, Fish, CTA, Q4) | [`ai-pro-pov-bof-largo.md`](docs/contexto/ai-pro-pov-bof-largo.md) + [`docs/CALENDARIO_POV_BOF_LARGO.md`](docs/CALENDARIO_POV_BOF_LARGO.md) | El cierre/CTA es la pieza de ajuste; duración en CLIPS; banco de voces medido |
| Nicho General UGC, Carruseles, Cuenta Piloto | [`ai-pro-general-carruseles-piloto.md`](docs/contexto/ai-pro-general-carruseles-piloto.md) | UGC: no recortar guion, prohibido "continúa" entre clips; Carruseles: original y quemado en carpetas distintas; Piloto: fotos al Drive, no a `api_uploads/` |
| MCP de agentes, Multiplataforma, Estadísticas/Subidas, Mi menú, Escaparate y vendidos | [`ai-pro-transversales.md`](docs/contexto/ai-pro-transversales.md) + [`MULTIPLATAFORMA_MODULE.md`](MULTIPLATAFORMA_MODULE.md) | Token MCP = HMAC (`MCP_TOKEN_SALT`); escaparate y vendidos son transversales y por usuario; enlaces de afiliado NUNCA en TikTok; si cambias una pantalla, cambia su guía |
| Variables de entorno `.env`, rutas Drive (`*_DRIVE_DIR`), Redis local vs Upstash, claves de IA por programa | [`env-vars.md`](docs/contexto/env-vars.md) + [`docs/DRIVE.md`](docs/DRIVE.md) | Editor Auto y Pronósticos siguen SIEMPRE en Upstash (`UPSTASH_SHARED_*`) |

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
- **System prompts en archivos `.md`** (`src/<programa>/prompts/*.md`), NUNCA hardcoded en el código.
- **Aislamiento entre programas**: NUNCA mezclar lógica de Creator Reward,
  TikTok Shop y Editor Auto. Reusar solo módulos transversales (MiniMax, FFmpeg, Whisper,
  Redis, logging, `locutor.py`, `fonts_registry.py`, `src/queue/*`, `subtitles*`).
  Cualquier cambio en un programa no debe romper el otro.
- **Frontend mobile-first**: toda UI nueva/modificada debe diseñarse y
  validarse para móvil además de desktop. Grids `grid-cols-2 sm:grid-cols-N`,
  diálogos con `w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto`, texto
  `text-xs sm:text-sm`, valores largos con `truncate`/`break-words`. La app
  se usa también desde móvil.
- **Todas las pantallas de nicho se parecen (OBLIGATORIO).** Son once y las
  usan tres personas: quien aprende una tiene que saber usar las demás. El
  estándar entero —anatomía de pantalla y de tarjeta, colores con significado,
  tamaños y qué componentes reutilizar— está en
  [`UI_NICHOS.md`](UI_NICHOS.md); **léelo antes de tocar una pantalla de
  nicho**. En corto: cabecera de TEXTO (nunca la portada del curso), `Caja`
  "Dónde trabajas" con `Sub` + barra + carpetas como CHIPS con `hechas/total`,
  `Paso` numerados con sus colores fijos (violeta preparar · fucsia generar ·
  esmeralda prompt · azul descargar), tarjetas en `sm:grid-cols-2` y la fila
  Escaparate/Subido/Vendió siempre la última. Lo que no encaje se añade a
  `components/tiktok-shop-ai-pro/` y se usa desde todos — no se inventa un
  diseño por pantalla.
- **MCP y guías al día (OBLIGATORIO).** Los vídeos los hacen sobre todo agentes: toda función
  nueva de un menú de AI Pro entra también en el MCP (`src/agente_mcp/`) y en su guía
  (`src/agente_mcp/guias/*.md`) en el mismo cambio (README › «Mantener el MCP al día»).
- **Un vídeo NO está terminado hasta que se comprueba (OBLIGATORIO, 18/10/2026).**
  Todo vídeo montado (de cualquier nicho, réplicas incluidas) se revisa y lleva
  semáforo en Mis tandas antes de darlo por hecho; una tanda con `sin_revisar` > 0
  no está terminada. La web bloquea la descarga para publicar de lo que no tiene
  semáforo o está en rojo (`servicio.sin_revisar`). Ver `src/agente_mcp/guias/mis-tandas.md`.
- **Refuerzo anti-sanción en TODO vídeo que se monte (OBLIGATORIO).** TikTok
  Shop sanciona por "promoción de productos incoherente" cuando no le queda
  claro que el vídeo enseña el producto enlazado, y lo decide una máquina. Así
  que cualquier formato nuevo, de cualquier nicho, sale con: **subtítulos** de
  lo que dice la voz (el TEXTO del guion locutado, los TIEMPOS de Whisper —
  ver `build_video(con_subtitulos, texto_voz)`), el **nombre del producto**
  quemado en pantalla, y los **metadatos limpios** (`limpiar_metadatos`). Lo
  que NO sirve: meter la foto del producto "con opacidad 0" o fuera del
  encuadre — en un MP4 renderizado no hay capas y el archivo sale idéntico.
- **Cost tracking obligatorio**: TODA llamada a API externa con coste (OpenAI,
  MiniMax, Gemini, Atlas Cloud, EchoTik…) debe pasar por un `record_*` de
  [`src/cost_tracking.py`](src/cost_tracking.py), con tokens/chars/segundos
  REALES del response. El runner ya envuelve cada job con
  `start_job`/`finalize_and_persist` vía `dispatch_job`. Al añadir un MODO o API
  nueva: (1) si la API no existe aún, añade tarifa + helper `record_<api>` con la
  tarifa vigente; (2) llama al helper justo tras el response real. El panel
  `/costs` muestra el desglose solo. Excepción explícita: Programa 4
  (Viralización) no usa ninguna API de pago (ffmpeg/Whisper local/rclone) → sin
  `record_*`, a propósito (ver VIRALIZACION_MODULE.md).

---

## Índice de documentación

| Archivo | Contenido |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Este archivo — contexto general, programas, env vars, convenciones |
| [`ADDING_PROGRAM.md`](ADDING_PROGRAM.md) | **Checklist para añadir un programa nuevo** (touchpoints API + runner + Redis + frontend + cost + deploy + tests + docs) |
| [`TIKTOK_SHOP_MODULE.md`](TIKTOK_SHOP_MODULE.md) | Programa 2 — arquitectura completa, esquemas Redis, prompts, Pilot Program |
| [`EDITOR_AUTO_MODULE.md`](EDITOR_AUTO_MODULE.md) | Programa 3 — flujo modular, tools registry, Silero VAD + Claude Haiku (OpenAI de respaldo) |
| [`TTSHOP_AI_PRO_WEB.md`](TTSHOP_AI_PRO_WEB.md) | **La web del curso** — cómo funciona `ttshopaiproapp.com`, de donde salen prompts, ZIP y fichas. Está tras login del operador: ningún agente puede mirarla, así que lo que se sepa se escribe ahí |
| [`APELACIONES.md`](APELACIONES.md) | Cómo apelar sanciones de TikTok Shop («promoción incoherente»): pruebas, forma del texto, qué no decir, casos aprobados |
| [`UI_NICHOS.md`](UI_NICHOS.md) | **Estándar visual de las pantallas de nicho** (Programa 4) — anatomía de pantalla y de tarjeta, colores con significado, piezas que se reutilizan. Obligatorio antes de crear o retocar una |
| [`VIRALIZACION_MODULE.md`](VIRALIZACION_MODULE.md) | Programa 4 — banco de candidatos sin repetir, 3 estilos de subtítulo, jitter anti-fingerprint, numeración de rondas |
| [`src/agente_mcp/guias/`](src/agente_mcp/guias/README.md) | **Si te piden HACER el trabajo de un menú de Tiktok Shop AI Pro** (bajar fotos, generar en Flow, subir clips…) y **guías para agentes de IA** (una por menú del Programa 4): las lee el MCP con `guia`, se sirven en `/api/v1/agente/guias/…` y cada pantalla las enlaza con «Guía IA». Si cambias el flujo de una pantalla, actualiza su guía. Skill: `.claude/skills/operar-tiktok-ai-pro` |
| [`WEB_CURSO.md`](WEB_CURSO.md) | **Web del curso (`ttshopaiproapp.com`)** — mapa de menús y hashes, inventarios, cómo entran ZIP/enlaces en nuestra app, prompts publicados, precios de Compras, peticiones de mejora pendientes |
| [`EDITOR_DEBUGGING.md`](EDITOR_DEBUGGING.md) | **Playbook de depuración del cortador de vídeo** — LEER antes de tocar `silence_cutter.py`: jerarquía de señales (silero>energía>Whisper), pipeline, casuística de bugs reales (proteína…), cómo diagnosticar una queja, gotchas de cola/deploy, auto-corrección |
| [`PronosticosAuto.md`](PronosticosAuto.md) | Nicho Pronósticos — schema Redis bet-ai-master, segmentos, overlays |
| [`APK.md`](APK.md) | **APK Android (TWA)** — por qué TWA y no Capacitor (descargas), cómo se genera, cuándo hay que rehacerla, gotchas de Bubblewrap |
| [`DEV_SETUP.md`](DEV_SETUP.md) | Arranque local (uvicorn + npm run dev), troubleshooting WS/cache |
| [`deploy/README.md`](deploy/README.md) | Histórico: instalación original en Hetzner (migrado a Contabo el 4-nov-2026) + Docker stack + Tailscale Funnel + webhook |
| [`deploy/SERVER_ACCESS.md`](deploy/SERVER_ACCESS.md) | Runbook SSH al server (IP, paths, comandos comunes) |
| [`deploy/CLAUDE_REMOTE.md`](deploy/CLAUDE_REMOTE.md) | Claude Code en el VPS (Remote Control + chat web): qué ocupa, cómo quitarlo y cómo reinstalarlo |
| [`deploy/CODEX_REMOTE.md`](deploy/CODEX_REMOTE.md) | Codex en el VPS (remote-control con cuenta ChatGPT): qué ocupa, limpiar versiones viejas, quitarlo y reinstalarlo |
| [`deploy/NAVEGADOR_REMOTO.md`](deploy/NAVEGADOR_REMOTO.md) | Chrome con pantalla virtual en el VPS (noVNC + CDP), MONTADO a demanda (Accesos › Navegador remoto) con las sesiones de Magnific/Flow/GenAI Pro; guía para agentes en `src/agente_mcp/guias/comun/navegador-vps.md` |
| [`docs/DRIVE.md`](docs/DRIVE.md) | **Dónde va cada cosa en el Google Drive** (árbol `Nebulabs/`, qué está compartido, rutas viejas → nuevas, reglas para agentes) |
| [`learnings.md`](learnings.md) | Historial técnico (1 línea por aprendizaje/fix) — **escribir al resolver bug o patrón nuevo** |
| [`tasks.md`](tasks.md) | TODO pendientes — mover a `## ✅ Done` al cerrar |
| [`docs/contexto/`](docs/contexto/) | Detalle literal por nicho/módulo y `.env` movido de este archivo (tabla «Detalle por nicho/módulo» arriba) |
| [`src/agente_mcp/guias/genjutsu-higgsfield.md`](src/agente_mcp/guias/genjutsu-higgsfield.md) | **Cuenta nueva de Néstor / vídeos virales de mayor calidad y menor volumen**: receta completa de producto, personaje en Flow, Genjutsu web/MCP, voz y revisión. Tutorial y prompts en `docs/clases/2026-10-13_tutorial_genjutsu_higgsfield.md`; MCP de la app `guia("genjutsu")`. Higgsfield registrado en Claude Code del VPS, pendiente de autenticación |
| [`docs/clases/2026-10-23_instagram_shop/README.md`](docs/clases/2026-10-23_instagram_shop/README.md) | **Cuentas de Meta (viva_shop, viva_salud, ama_shop) y vídeos para Instagram/Facebook**: curso Skool «Instagram Shop · Fase 1». Incluye restricción de países, 10 reels sin enlaces para crecer, calentamiento de 72 h, bandera de España al fondo y la CTA «Comenta SÍ + Sígueme». También el formato avatar «remedios» y la marca Buumi (+20 % sobre Amazon). Los prompts y guiones del curso solo están en el VPS, sin subir a git |
| [`docs/clases/2026-10-24_seedance_capcut/README.md`](docs/clases/2026-10-24_seedance_capcut/README.md) | **Seedance 2.0 / formato «Revelación 15 s»** (curso Skool «Crea con Seedance»): un personaje destapa maniquíes y grita cada color, en una toma de 15 s. Incluye los prompts literales de la web, los costes de CapCut (Ultra, unos 75 créditos por vídeo), la alternativa con el Seedance de Higgsfield y el encaje con Ana y Casca Chollos |
| `MCP_URLS.local.md` (NO está en git) | **URLs del MCP de la app con su token** (p. ej. la de Ana, para subir los vídeos del multimodo). Solo existe en el PC del operador y en el VPS; nunca las copies a memoria, commits ni chats. Si no lo encuentras, pídele la URL al operador |
| [`docs/CUENTA_ARABE.md`](docs/CUENTA_ARABE.md) | **Cuenta árabe del Mi 8 y usuario web `nes_bugallo` («Ness/Bugallo»)** (29/10/2026): público árabe/magrebí, 45 carruseles + 10 vídeos POV/día, **se copia el estilo y los textos de SUS tiendas, no los nuestros**, precio sí. Carruseles con `replicar_carrusel(pais="AR")`; texto mixto español+árabe+números con `src/texto_arabe.py` (Tajawal + bidi); pantallas Subidas y Estadísticas de nes_bugallo; subida automática del Mi 8 pendiente |
| [`SESSION_STATE.md`](SESSION_STATE.md) | Handoff del refactor TikTok Shop (mayo 2026) |
| [`README.md`](README.md) | Onboarding general del repo |


## Estructura por programa

Cada programa vive aislado en `src/<programa>/` con: `config.py`, `models/`,
`repos/`, `services/`, `pipeline/`, `prompts/*.md`. **Nunca se comparte
lógica entre programas** — solo módulos transversales (`src/locutor.py`,
`src/cost_tracking.py`, `src/fonts_registry.py`, `src/queue/*`,
`src/subtitles*`, etc.). Flechas CTA y estilos de subtítulos: catálogo común
[`src/catalogo_edicion/`](src/catalogo_edicion/README.md) (Editor Auto + TikTok Shop + web
Nebulabs Media; lo nuevo se aprueba a mano con `scripts/catalogo_edicion.py`).

API: `src/api/routers/<programa>/` + `src/api/schemas/<programa>/`.
Frontend: `frontend/app/<programa>/` + `frontend/lib/queries/<programa>.ts`.

## Mantenimiento de este archivo

Actualiza CLAUDE.md cuando: módulo nuevo/eliminado en `src/`, env vars que
cambian, schema Redis, assets esperados, nicho o programa nuevo.
NO por: bugfixes, refactors, ajustes de parámetros, lo derivable del código.
Cap 250 líneas — mover detalles a `.md` específico si crece: el de cada nicho va
literal en `docs/contexto/` (y su fila en «Detalle por nicho/módulo»); `ADDING_PROGRAM.md`
recoge la guía completa de "añadir programa". No copies aquí lo que ya está en AGENTS.md.

### Memoria y Tareas
- **Lectura**: Lee `tasks.md` para pendientes y `learnings.md` para historial técnico.
- **Escritura Autónoma**: Al resolver un bug o implementar un patrón técnico nuevo, añade obligatoriamente un registro de 1 línea en `learnings.md`. Al finalizar una tarea, muévela a la sección `## ✅ Done` en `tasks.md`.
