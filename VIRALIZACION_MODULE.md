# Programa 4 — Viralización ("Tiktok Shop AI Pro")

> Fábrica de vídeos POV/reacción para llegar a 1000 seguidores en TikTok Shop:
> un ponente motivacional (Pablo Motos, Víctor Küppers, …) habla 20-60s sobre
> un tema, 3s de su cara en primer plano al inicio (el "gancho"), y el resto
> son clips de paisajes de España cambiando cada ~4.5s. Técnica estándar
> anti-copyright "voice-over + b-roll". Automatiza en ffmpeg/Whisper local lo
> que el operador hacía a mano en CapCut (~3h para 4 vídeos).

Slug interno: `viralizacion`. Grupo de sidebar/marca del operador:
**"Tiktok Shop AI Pro"** (nombre literal — no traducir/cambiar), con
"Viralización 1K" como su primer item (más herramientas se añadirán a este
mismo grupo en el futuro).

---

## Arquitectura

```
src/viralizacion/
├── config.py                    # paths locales, Redis prefix, parámetros de render/jitter
├── models/                      # (reservado — hoy no hay modelos Pydantic propios,
│                                 #  los payloads de job/API son dicts simples)
├── repos/
│   ├── redis_base.py            # ViralizacionRedis (prefijo `viralizacion:`)
│   └── usage_repo.py            # SET de índices de gancho/paisaje ya usados, por ponente
├── services/
│   ├── allocator.py             # asigna candidatos SIN repetir (usa resource_scanner + usage_repo)
│   └── drive_uploader.py        # rclone copy del batch a Drive
├── pipeline/
│   ├── ffmpeg_utils.py          # run()/ffprobe_duration() compartidos
│   ├── resource_scanner.py      # detección de cara (gancho) + chopping (paisaje), cacheado en JSON
│   ├── transcriber.py           # Whisper (cacheado) + agrupación en frases con timings de palabra
│   ├── styles.py                # 3 StylePreset (Clásico/Reveal/Cinemático) — build_ass + filtros extra
│   ├── renderer.py              # filter_complex ffmpeg (xfade, jitter, subs, audio) — 1 vídeo
│   └── batch.py                 # orquestador: reparto de rondas por audio + loop + upload
```

Backend Job/API: `JobMode.VIRALIZACION_BATCH` (`src/queue/models.py`) →
`run_viralizacion_batch` (`src/queue/runners.py`) → `pipeline/batch.py:run_batch`.
Router: `src/api/routers/viralizacion/enqueue.py` (`GET /api/v1/viralizacion/ponentes`,
`POST /api/v1/viralizacion/generate`). Schemas: `src/api/schemas/viralizacion/models.py`.
Frontend: `frontend/app/tiktok-shop-ai-pro/viralizacion/page.tsx` +
`frontend/lib/queries/viralizacion.ts` + `frontend/lib/types/viralizacion.ts`.

**Sin cost tracking, a propósito**: este programa no llama a NINGUNA API de
pago — todo es ffmpeg local, Whisper local (`faster-whisper`, ya usado en el
resto del repo) y `rclone` para subir a Drive. El wrapper `dispatch_job` sigue
envolviendo el job en `cost_tracking.start_job/finalize_and_persist`
automáticamente (no se puede desactivar sin tocar el wrapper compartido),
pero el runner nunca llama a `record_*` — el panel `/costs` mostrará el
programa con coste `$0` siempre, que es correcto.

---

## Recursos (assets)

Viven en una carpeta LOCAL persistente del VPS (NO Drive montado, NO
`/tmp`, NO en el repo git) — pesan varios GB y se reutilizan en cientos de
renders. Default `/home/nebulabsai/viralizacion_assets`, override con
`VIRALIZACION_ASSETS_PATH`.

```
<ASSETS_ROOT>/
├── pablo/
│   ├── gancho/gancho.mp4          # vídeo largo, fuente de candidatos de gancho
│   ├── audios/*.MP3               # 5 audios (nombres irregulares, se listan alfabético)
│   └── hook_candidates.json       # caché del escaneo de cara (ver resource_scanner)
├── victor/
│   ├── gancho/gancho.mp4
│   ├── audios/*.MP3               # 4 audios
│   └── hook_candidates.json
├── paisajes/
│   ├── paisajes.mp4               # ~61min, COMPARTIDO entre ponentes
│   └── paisaje_candidates.json    # caché del chopping (compartido)
├── musica/Musica Reels.MP3
├── staging/<batch_id>/<ponente>/*.mp4   # vídeos generados antes de subir a Drive
└── _cache/transcripts/<ponente>/<audio_stem>.json   # caché Whisper por audio
```

Añadir un ponente nuevo: crear `<slug>/gancho/` y `<slug>/audios/` con los
ficheros, y una entrada en `config.PONENTES`. El primer render de ese ponente
dispara el escaneo de candidatos (lento la primera vez, cacheado después).

**Destino final (Drive)**: `gdrive:VIRALIZACION/<cuenta_saneada>_<fecha>/<ponente>/`
— una subida por batch, vía `rclone copy` (mismo remote `gdrive:` ya
configurado en el VPS, `--drive-shared-with-me` usado solo para las
descargas iniciales manuales, no en el pipeline).

---

## Banco de candidatos — nunca se repiten (Redis)

**Gancho** (`pipeline/resource_scanner.py:scan_hook_candidates`): muestrea el
vídeo de gancho a 1fps con OpenCV Haar cascade (`haarcascade_frontalface_default.xml`),
detecta la cara más grande de cada frame, agrupa en tramos continuos donde
`h_frac > 0.22` (cara ocupa >22% de la altura = primer plano), y trocea cada
tramo en candidatos NO SOLAPADOS de exactamente 3s con su `cx_frac` (centro X
de la cara, para centrar el crop). Cacheado en `<ponente>/hook_candidates.json`.

**Paisaje** (`scan_paisaje_candidates`): trocea el vídeo de paisajes en
candidatos NO SOLAPADOS de 4.5s, saltando los primeros/últimos 60s (intro/
outro/CTAs). Cacheado en `paisajes/paisaje_candidates.json`, COMPARTIDO entre
ponentes (misma fuente).

**Tracking de uso** (`repos/usage_repo.py`, Redis Upstash, prefijo
`viralizacion:`):
- `hook_used:<ponente>` → SET de índices de `hook_candidates` ya usados por
  ESE ponente.
- `paisaje_used:<ponente>` → SET de índices de `paisaje_candidates` ya
  usados por ESE ponente. El pool de paisajes es compartido (mismo vídeo
  fuente) pero el USO se rastrea por separado por ponente — cada ponente
  tiene su propio pool efectivo sin coordinar entre ellos.

`services/allocator.py` asigna (y marca usado en Redis) un candidato ANTES
de renderizar; si el render falla, el índice se libera (`release_hook`/
`release_paisajes`) para no perder el hueco. Si el pool se agota, lanza
`PoolExhaustedError` con el déficit exacto (cuántos hacían falta / cuántos
quedaban) — NUNCA reutiliza silenciosamente.

Si Redis no está configurado (`UPSTASH_REDIS_REST_URL`/`TOKEN`), el módulo
lanza `RuntimeError` en vez de degradar — la garantía de "nunca repetir" no
se puede mantener sin persistencia.

---

## 7 estilos de subtítulo/filtro (rotan por ronda)

`pipeline/styles.py:STYLE_PRESETS` — registro extensible (`StylePreset`
dataclass: `build_ass(lines, preset)` + overrides de filtro de vídeo). Añadir
un estilo = una entrada nueva en el dict + su clave en `STYLE_ORDER`, sin
tocar el resto del pipeline. Sin selección explícita, `resolve_style(ronda)`
rota por `STYLE_ORDER`; si el operador elige un subconjunto (`styles_pool`),
`distribute_styles` reparte los vídeos entre ellos a partes iguales.

- **A "Clásico"** (ronda 1, 4, 7…): línea completa blanca, borde negro fino,
  `Alignment=5` (centrado horizontal Y vertical), `MarginL=MarginR=145`
  (13.4% — evita la UI de TikTok), DejaVu Sans Bold 68px. Filtro base:
  `eq=contrast~1.14:saturation~1.25:brightness~0.06:gamma=1.08` (jitter ±5%
  por vídeo) + `vignette=angle=PI/4.2:mode=forward` (SIEMPRE `forward` —
  `backward` invierte la viñeta y sobreexpone) + `noise=alls=8:allf=t+u`.

- **B "Reveal"**: UNA palabra en pantalla cada vez (68×1.35px), cambiando de
  molde tipográfico con `_STACK_MOLDES` (mayúsculas/cursiva/escala/amarillo de
  acento) y borde negro nítido. Dos intentos previos descartados: revelar
  letra a letra acumulando la frase (con frases largas el texto se hacía
  diminuto) y una palabra sola con glow blanco (`\bord5\blur5` con borde
  blanco — fundía las letras en un borrón ilegible, ver captura del operador).
  El `end` de cada evento se recorta al `start` de la palabra siguiente: el
  mínimo de 0,12s que evita el parpadeo invadía la siguiente y ASS apilaba los
  dos eventos ("LO / que" en pantalla a la vez). Firma visual extra: se probó
  un overlay de puntos discretos vía `geq` pero resultaba muy lento en vídeos
  largos (1080x1920x30fps) — **fallback usado**: `noise=alls=35:allf=t+u:c0s=1`
  (mucho más denso que el grano base de Estilo A), documentado aquí como
  decisión de diseño, no como olvido.

- **C "Cinemático"**: karaoke por palabra — cada línea genera un evento ASS
  POR PALABRA activa, mostrando la FRASE COMPLETA con la palabra actual en
  blanco (`{\1c&HFFFFFF&}`) y el resto en negro (`{\1c&H000000&}`).
  `OutlineColour=&H00FFFFFF&` (blanco) para que las palabras negras no se
  fundan con fondos oscuros. Filtro extra: grade frío/cálido
  (`gamma_r=1.06:gamma_b=0.94`), viñeta más fuerte (`angle=PI/3.5`), y 2
  `drawbox` negros (77px ≈ 4% de 1920) arriba/abajo tipo letterbox
  cinematográfico — no invaden el área de subtítulos (centrados en Y).
  Las barras no son fijas: `_retracting_bars()` las abre progresivamente
  durante el gancho (14 `drawbox` escalonados con `enable`, porque `drawbox`
  no evalúa `t` en su geometría — su `t` es el grosor del trazo).

- **D "Teal & Orange"** y **F "Hora dorada"**: reaprovechan el `build_ass`
  de C y de B con grade propio (`eq_extra`), viñeta e intensidad de grano
  distintas. Son variantes de color, no de tipografía.

- **E "Cascada"**: las palabras caen DESORDENADAS por la pantalla — un evento
  ASS por palabra con `\pos` (con `\N` todo el bloque comparte una sola
  posición, así que no hay forma de desperdigarlas). Posición horizontal,
  molde tipográfico (`_CASCADA_MOLDES`: escala 0.58-1.45, blanco/amarillo,
  cursiva, mayúsculas) y holgura vertical se SORTEAN por bloque: un zigzag
  fijo izquierda-derecha se lee como plantilla. El bloque va compacto (salto
  0.92× el cuerpo) y cada palabra usa `layer=j`, así la que acaba de entrar
  tapa a las anteriores. Fondo con motas de polvo NEGRAS a la deriva
  (`film_specks` = nº de láminas; ver abajo). Era el estilo "Noir" en blanco
  y negro — descartado por el operador, el paisaje en B/N no vende.

- **G "Cuadrado"**: réplica del formato viral — el vídeo se recorta a un
  cuadrado de `SQUARE_SIDE` px con esquinas redondeadas (`SQUARE_RADIUS`)
  centrado sobre fondo negro, y las palabras van APILÁNDOSE de una en una
  (`build_ass_stacked`), cada una con un molde tipográfico distinto de
  `_STACK_MOLDES` (mayúsculas/cursiva/escala/amarillo), máximo `_STACK_MAX`
  visibles antes de empezar bloque nuevo. Fuente 1.45× la base: el texto vive
  dentro del cuadrado y tiene que llenarlo.
  El redondeo se hace con una máscara PNG generada con PIL
  (`renderer.py:_rounded_square_mask`) + `alphamerge` — ffmpeg no sabe dibujar
  rectángulos redondeados. La máscara se añade como **último** input para que
  su índice sea predecible (`mask_idx = 3 if music_path else 2`); con música
  activada, un índice fijo leería la pista de audio como si fuera la máscara.

**Motas de polvo (`film_specks`)** — `renderer.py:_dust_plate` genera con PIL
una lámina PNG transparente 1.5× el encuadre con ~130 motas y el filtro la
desplaza con `overlay=x='x0+vx*t'`. Se intentó una mota por `drawbox`+`enable`:
hacían falta cientos de filtros para tener unas pocas en pantalla a la vez y
aun así no se movían (`drawbox` no anima su posición — su `t` es el GROSOR).
Con láminas basta un `overlay` por capa, las motas entran y salen del
encuadre solas, y el coste por fotograma es despreciable.

**Índices de input en `_finalize`** — `[0]` vídeo, `[1]` voz, `[2]` música si
la hay, y a partir de ahí todo input visual extra (máscara del cuadrado,
láminas de polvo) se añade con el helper `add_input`, que devuelve el índice.
Hardcodearlos se rompía en cuanto se activaba la música.

---

## Anti-fingerprint (jitter aleatorio)

Si todos los vídeos de la plantilla comparten exactamente el mismo encuadre/
cadencia/color, es una huella reconocible (riesgo de shadowban en cadena
entre cuentas). Cada clip/vídeo sortea (sin seed fija) dentro de estos
rangos, configurables en `config.py`:

- **Zoom extra** por clip (encima del mínimo para cubrir 1080x1920):
  gancho `[1.0, 1.08]` (conservador, no recorta frente/barbilla), paisaje
  `[1.0, 1.18]`.
- **Duración de cada tramo de paisaje**: media ~4.5s, cada clip individual
  varía en `[3.5, 5.5]`s — la SUMA total siempre cuadra EXACTA con el hueco
  a rellenar (`renderer.py:_jittered_paisaje_durations`, corrección final de
  precisión flotante en el último elemento).
- **Duración de transición paisaje→paisaje**: `[0.7, 1.1]`s por transición
  (antes fija en 0.9s). La transición gancho→paisaje (`hblur`) se mantiene
  fija en 0.35s — validada explícitamente por el operador.
- **EQ del vídeo** (contrast/saturation/brightness): ±5% por vídeo (no por
  clip) sobre los valores base aprobados.

---

## Numeración y reparto de rondas

Nombre de fichero: `<ponente>{ronda}_{indice_audio}.mp4` (ej. `pablo1_1.mp4`).
`ronda` = qué repetición es DENTRO de ese audio (empieza en 1 por audio).
`indice_audio` = qué audio de la lista es (1-based, orden alfabético de
`config.ponente_audio_files`).

**Reparto** (`pipeline/batch.py:_rounds_per_audio`): `R = ceil(total / n_audios)`,
relleno SECUENCIAL audio por audio hasta `R` (el último audio que recibe
rondas se queda con el resto exacto). Ej. total=23, 5 audios → R=5 →
`[5,5,5,5,3]` (23=5+5+5+5+3). Ej. total=25 → `[5,5,5,5,5]`. Nunca genera de
más; si `total <= n_audios`, reparte 1 ronda por audio (usa tantos audios
como `total`) — para ver los 3 estilos en una tanda pequeña del MISMO audio,
pide un total que sea múltiplo de `n_audios` (o dirígete a un ponente con
pocos audios).

**Orden de procesamiento**: outer loop = audio (evita recargar/re-transcribir
cada audio repetidamente — la transcripción Whisper se cachea y se reusa en
todas las rondas de ese audio), inner loop = rondas de ese audio.

**Música de fondo**: parámetro `music_rounds` (default 1) — solo las rondas
`<= music_rounds` de CADA audio llevan `Musica Reels.MP3` mezclada
(volumen 0.75, `afade=out` 0.5s, `amix` + `alimiter=limit=0.95`); el resto
solo voz + limiter (para que el operador añada su propia música de TikTok al
subir sin que choque con una ya puesta).

---

## Schema Redis (prefijo `viralizacion:`)

| Key | Tipo | Contenido |
|---|---|---|
| `hook_used:<ponente>` | SET | índices de `hook_candidates.json` ya usados |
| `paisaje_used:<ponente>` | SET | índices de `paisaje_candidates.json` ya usados (por ponente) |

---

## Variables de entorno

```env
# VIRALIZACION_ASSETS_PATH="/home/nebulabsai/viralizacion_assets"   # override, autodetect por defecto
# VIRALIZACION_REDIS_PREFIX=viralizacion:                            # default
```
Reusa `UPSTASH_REDIS_REST_URL`/`UPSTASH_REDIS_REST_TOKEN` ya definidas para
el resto del repo (namespace propio vía prefijo, no hace falta otra
instancia de Redis).

---

## Validación realizada (sesión de implementación)

- Escaneo de candidatos: Pablo → 55 candidatos de gancho (vídeo de 178s) +
  788 candidatos de paisaje (vídeo de ~61min, compartido). Víctor → escaneo
  de gancho sobre un vídeo de ~55min (más lento, un único hilo de OpenCV).
- Batch de prueba: 3 vídeos de Pablo, mismo audio (`audio pablo 1.MP3`,
  índice 1), estilos A/B/C, música solo en ronda 1 — verificado con ffprobe
  (1080x1920, duración = duración del audio) y frames extraídos para
  inspección visual de cada estilo (glow del Reveal a mitad de palabra,
  karaoke blanco/negro + letterbox del Cinemático sin tapar texto).
- Redis: verificado que una 4ª asignación de gancho para el mismo ponente
  devuelve un índice DISTINTO a los 3 ya usados (liberado tras el chequeo
  para no consumir pool de la validación).
- Subida a Drive: `rclone copy` del staging a
  `gdrive:VIRALIZACION/test_<fecha>/pablo/`, verificado con `rclone lsf`.
