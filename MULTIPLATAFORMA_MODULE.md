# Multiplataforma — publicador de vídeos a IG, Facebook, Threads y Pinterest

Sube los vídeos YA montados por la fábrica (POV BOF, POV BOF Largo, Multimodo,
Viralización 1K…) a **Instagram Reels, Facebook Page Reels, Threads y
Pinterest** por las APIs oficiales, con enlace de afiliado (Amazon / SHEIN).
No edita vídeo. Sin tokens funciona en **modo prueba**: anota qué llamadas
haría y no toca la red.

Código: [`src/multiplataforma/`](src/multiplataforma/) · API:
[`src/api/routers/multiplataforma.py`](src/api/routers/multiplataforma.py) ·
tick: [`scripts/multiplataforma_tick.py`](scripts/multiplataforma_tick.py) ·
tests: `tests/multiplataforma/`.

## Piezas

| Fichero | Qué hace |
|---|---|
| `config.py` | Env vars, versión Graph API (`META_GRAPH_VERSION`, def. `v24.0`), límites 24h (IG 50, FB 30, Threads 250, Pinterest 50), hashtags y longitudes máx., acortadores prohibidos |
| `models.py` | `CuentaDestino` (destinos, tokens, tag Amazon) y `Publicacion` (estado/resultados/errores/intentos POR plataforma) |
| `repos/` | `cuentas_repo`, `publicaciones_repo` (cola + contador de envíos 24h) |
| `clients/` | `instagram` (REELS con `video_url` o resumable, `trial_params`, cuota), `facebook` (`video_reels` start→rupload→finish + comentario con el enlace), `threads` (VIDEO + publish), `pinterest` (v5 media→S3→pins) — httpx, timeouts, `ErrorPublicacion(reintentable, parcial)` y `dry_run` |
| `services/textos.py` | Texto por plataforma desde plantillas `prompts/*.md`; aviso literal de Amazon si el enlace es de Amazon |
| `services/enlaces.py` | `enlace_amazon(asin, tag)` → `https://www.amazon.es/dp/<ASIN>?tag=<tag>`; SHEIN: el enlace del panel TAL CUAL (solo se valida dominio/https). Nunca acortadores (incluido `amzn.to`) |
| `services/video_url.py` | URL pública temporal firmada (HMAC con `AUTH_COOKIE_KEY`, contexto propio, TTL 6h) para que IG/Threads descarguen el vídeo |
| `services/ingesta.py` | `ingestar(cuenta)` / `ingestar_todas()`: encola los vídeos nuevos de las carpetas del Drive; `mover_a_publicados` |
| `publicador.py` | `publicar_pendientes(ahora, limite)` — el tick (rellena el enlace desde `enlaces_repo` si la publicación tiene `producto_ref` y aún no lo tiene) |
| `repos/enlaces_repo.py` | Enlace de afiliado POR PRODUCTO y cuenta (`enlaces:<slug>`), con `sin_equivalente` |
| `services/tandas.py` | Productos del dueño de la cuenta desde Mis tandas, `guardar_enlace`, `encolar` (resubida idempotente) y la página pública `/links` |
| `services/musica.py` | Música de fondo para los vídeos MUDOS de Mis tandas: estilo por la `musica.busqueda` de la fila, pista del banco `_musica/` rotando por cuenta, copia con ffmpeg (`-c:v copy`) en `temp_work/multiplataforma_musica/` |

## Ingesta desde el Drive

Carpetas (se crean solas al `POST /cuentas`, mkdir -p defensivo):

```
<mount>/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Multiplataforma/<slug>/
    viralizacion/            → tipo prueba_viral
    viralizacion/publicados/
    producto/                → tipo producto
    producto/publicados/
```

`<mount>` = `mount_root()` del POV BOF (`/mnt/drive` en el container,
`~/gdrive` en el host). Override `MULTIPLATAFORMA_DRIVE_ROOT` (apunta YA a
`Multiplataforma/`); sin mount, `API_TEMP_ROOT/multiplataforma`.

- Solo `.mp4`/`.mov` del primer nivel, orden natural (`2` antes que `10`).
- Ya ingestados: SET `ingestadas:<slug>` (rutas). Un JSON roto o un enlace no
  válido NO se marca: sale en `errores` y se reintenta en el siguiente tick.
- Texto/enlace: `<mismo nombre>.json` (`titulo`, `caption`, `hashtags`, `asin`,
  `enlace`, `plataformas`, `trial_graduation`, `producto_ref`) o `.txt` (línea
  que es solo una URL → enlace; línea solo de `#tags` → hashtags; resto →
  caption). Sin nada: título = nombre del fichero, sin enlace.
- Programación: `CuentaDestino.ritmo` (vídeos/día por tipo, def. 1 y 1; 0 =
  no ingestar esa carpeta) y `CuentaDestino.horas` («HH:MM» en
  `MULTIPLATAFORMA_TZ`, def. Europe/Madrid: viral 19:00, producto 13:00). Se
  continúa tras la última pendiente de esa cuenta+tipo (o desde ahora). Si el
  ritmo supera las horas dadas, los huecos extra van cada hora tras la última.
  Cada hueco se mueve ±`MULTIPLATAFORMA_DESFASE_MIN` (def. 4) minutos, fijo
  por cuenta y día (14:00 → 13:57 / 14:03…), para no publicar al minuto exacto.
- Al quedar `publicado` en TODAS sus plataformas, el vídeo (y su .json/.txt)
  pasa a `<carpeta>/publicados/` y sale del SET; si mover falla, solo log.
  `simulado` no cuenta: sin tokens no se mueve nada.
- El tick (`scripts/multiplataforma_tick.py`) ingesta todas las cuentas
  activas antes de publicar (no con `--dry-run`; `--sin-ingesta` la salta).

## Música en los vídeos mudos (Mis tandas)

La API de Meta no deja elegir canción de Instagram: a los vídeos MUDOS de
Mis tandas (multimodo de 10 s: espejo, espejo_escenas, botas, bolsos, zapatos,
maniquí…) `tandas.encolar` les mezcla música en el fichero
(`services/musica.py:con_musica`). Los que tienen voz no se tocan.

- **Banco** en el Drive: `Multiplataforma/_musica/<estilo>/*.mp3` + `LICENCIA.md`
  (fuente, autor y URL de cada pista) + `pistas.json`. Solo **Mixkit** (Mixkit
  Stock Music Free License, comprobada el 8/10/2026: uso comercial y en redes
  sin atribución; prohibido publicar la pista sola/remezclada o registrarla en
  Content ID; reclamaciones a team@mixkit.co). Nada de Pixabay/YouTube.
  14 estilos, 66 pistas: `lofi_otono` (neutro/fallback), `jazz_cafe`,
  `bossa_lounge`, `country_western`, `folk_acustico`, `folk_carretera`,
  `blues_vintage`, `retro_vintage`, `soul_funk_70s`, `pop_outfit`,
  `house_fashion`, `dream_pop`, `rnb_suave`, `hiphop_chill`. Para añadir un
  estilo: carpeta nueva + sus claves en `musica.ESTILOS`.
- **Mudo** = sin pista de audio (ffprobe) o con una en silencio (< −60 dB).
- **Estilo** por palabras clave sobre `fila["musica"]` (`busqueda` ×3,
  `estilo` ×2, `alternativas` ×1; el orden de `ESTILOS` desempata). Nada casa
  o el estilo no tiene carpeta → `MUSICA_ESTILO_NEUTRO`.
- **Pista**: la siguiente del estilo tras la última usada en esa cuenta
  (Redis `musica_ultima:<cuenta>` = `{estilo: fichero}`).
- **Mezcla**: `loudnorm` a `MULTIPLATAFORMA_MUSICA_LUFS` (−18), fundido de
  0,8 s / 1,5 s, empieza a los 4 s de la pista, recortada a la duración del
  vídeo, AAC 160k, `-c:v copy`, metadatos fuera.
- **Copia** en `temp_work/multiplataforma_musica/<cuenta>/<stem>__<hash>.mp4`
  (+ `.json` con estilo, pista y original), volumen persistente y protegida en
  `temp_cleanup.PROTECTED_DIRS`; los originales de Ana no se tocan. Si ya
  existe y es más nueva que el original se reutiliza. `pub.video_path` apunta
  a la copia; `tandas_encoladas:<slug>` sigue guardando el ORIGINAL
  (idempotencia). La respuesta de `encolar` trae `musica: "estilo/pista"`.
- Cualquier fallo (sin banco, ffmpeg) → log y se publica el original.
- Overrides: `MULTIPLATAFORMA_MUSICA_DIR` (banco), `MULTIPLATAFORMA_MUSICA_TRABAJO` (copias).

## Reglas del tick

- Coge las publicaciones con `programada_en <= ahora` (orden ascendente), hasta `limite`.
- Por plataforma: `publicado`/`fallido` no se tocan (**idempotente**). Los ids
  intermedios (contenedor IG/Threads, `video_id` FB, `media_id` Pinterest) se
  guardan y el reintento los reutiliza: no se crean duplicados.
- Sin token o sin id de destino → `simulado` (se reintenta de verdad cuando
  haya token). `--dry-run` / `MULTIPLATAFORMA_DRY_RUN=1` simula TODO y no guarda.
- Límite 24h móviles por cuenta y plataforma; IG y Threads además consultan la
  cuota real de Meta antes de crear el contenedor.
- Error 5xx/429/timeout → `error` y reintento (máx. `MULTIPLATAFORMA_MAX_INTENTOS`=3);
  4xx → `fallido`.
- `tipo="prueba_viral"` → **solo Instagram** por defecto
  (`config.PLATAFORMAS_POR_TIPO`; un `.json` con `plataformas` lo cambia): son
  para llegar a los 1000 seguidores de IG Shop, y la clase del 7/10 dice de los
  vídeos de viralización «solo mételos en reel de prueba». En IG sería reel de
  prueba (`trial_params`), pero Meta lo rechaza con nuestra app
  (`IG_TRIAL_REELS=0`) y salen como reel normal.

## Textos

- Amazon → «En calidad de Afiliado de Amazon, obtengo ingresos por las compras
  adscritas que cumplen los requisitos aplicables» en TODAS las plataformas
  (`prompts/aviso_amazon.md`, no cambiar).
- IG: «enlace en mi perfil» (el pie no es clicable). FB: «enlace en el primer
  comentario» + comentario con enlace. Threads: enlace en el texto (≤500).
  Pinterest: enlace en `link`, título ≤100.
- Hashtags máx.: IG 5, FB 3, Threads 1, Pinterest 5.

## Redis (prefijo `multiplataforma:`, override `MULTIPLATAFORMA_REDIS_PREFIX`)

| Clave | Tipo | Contenido |
|---|---|---|
| `cuenta:<slug>` | JSON | `CuentaDestino` (con tokens) |
| `cuentas:index` | SET | slugs |
| `pub:<id>` | JSON | `Publicacion` |
| `pubs:pendientes` | SET | ids sin terminar (se ordenan al leer) |
| `pubs:todas` | SET | histórico de ids |
| `envios:<cuenta>:<plataforma>` | JSON lista | timestamps de publicaciones reales (24h móviles) |
| `ingestadas:<slug>` | SET | rutas de vídeo ya encoladas desde el Drive |
| `enlaces:<slug>` | JSON | `{producto_key: {enlace, shein, asin, sin_equivalente, titulo, tienda, foto_url, precio, nota, fila_id, clave, actualizado}}` |
| `tandas_encoladas:<slug>` | SET | rutas de vídeo de Mis tandas ya encoladas (idempotencia de `encolar-tandas`) |
| `musica_ultima:<slug>` | JSON | `{estilo: fichero}` última pista usada por estilo (rotación de la música) |

## API (`/api/v1/multiplataforma`, API key)

`GET /cuentas` (sin tokens) · `POST /cuentas` · `PUT /cuentas/{slug}/tokens`
(solo escritura) · `POST /publicaciones` (encola; `asin` o `enlace`; mismo
vídeo+cuenta+tipo pendiente no se duplica) · `GET /cola?todas=` ·
`POST /tick?dry_run=true` · `POST /cuentas/{slug}/ingestar` · **público**:
`GET /archivo/{token}` (vídeo firmado; solo sirve rutas —resueltas, sin
symlinks ni `..`— bajo la raíz Multiplataforma, la del Programa 4
`TIKTOK_SHOP_AI_PRO/` (vídeos de Mis tandas), `temp_work/` o `API_TEMP_ROOT`).

### Enlaces por producto y resubida de Mis tandas

Los gestiona SOLO el agente por MCP (guía
[`src/agente_mcp/guias/multiplataforma.md`](src/agente_mcp/guias/multiplataforma.md)):
no hay pantalla en la app. La cuenta necesita `dueno` (usuario cuyas tandas se
resuben: `ama_shop`→ana, `viva_shop`→ness).

- `GET /cuentas/{slug}/productos?sin_enlace=1` — productos agrupados por
  `producto_key` (vídeos, subidos a TikTok, en cola, estado del enlace).
- `GET /cuentas/{slug}/productos/{producto_key}/foto` (con auth).
- `PUT /cuentas/{slug}/enlaces/{producto_key}` `{shein | asin | enlace, nota,
  titulo, foto_url, precio}` (`"sin_equivalente"` en shein/asin) ·
  `DELETE` igual.
- `POST /cuentas/{slug}/encolar-tandas?incluir_no_subidos=&limite=` — por
  defecto solo vídeos ya subidos a TikTok y de productos con enlace; ritmo y
  horas `producto` de la cuenta tras lo ya programado; repetir no duplica.
  Devuelve `omitidas` (`sin_enlace`, `no_subidos`, `ya_encolados`,
  `ruta_no_valida`). `Publicacion.origen="tandas"`, `producto_ref=producto_key`.
- `producto_key` = sha1 de `norm(tienda)|norm(título)`[:16]: vale para todas
  las versiones del producto (modos del Largo, POV BOF, copias Q4). Si se
  reescribe el título cambia → hay que volver a guardar el enlace.

**Página pública** `/links/<cuenta>` (Next, sin login, `noindex`) — la de la
bio de IG/FB. Lee `GET /links/{slug}` (público, sin auth, caché 120 s: solo
id, título corto, foto, enlace, tienda + `aviso_amazon` si hay alguno de
Amazon; orden: lo último publicado primero) y `GET /links/{slug}/foto/{producto_key}?w=`
(solo productos con enlace; `foto_url` del candidato o la foto de Mis tandas).
No hace falta tocar Caddy (no autentica); `/api/v1/multiplataforma/links/`
está en `_PREFIJOS_PRO` para que un `pro` con sesión no reciba 403, y el
frontend salta `LoginGate`/sidebar en rutas de `lib/rutasPublicas.ts`
(`components/layout/MarcoApp.tsx`).

MCP: `cuentas_multiplataforma`, `productos_sin_enlace`, `guardar_enlace`,
`encolar_tandas`, `cola_multiplataforma` (requiere token de admin: la API es
solo admin).

## Env vars

`META_APP_ID`, `META_APP_SECRET`, `META_GRAPH_VERSION`, `THREADS_API_BASE`,
`PINTEREST_APP_ID`, `PINTEREST_APP_SECRET`, `PINTEREST_API_BASE` (sandbox con
acceso Trial), `MULTIPLATAFORMA_DRY_RUN`, `MULTIPLATAFORMA_LIMITE_*`,
`MULTIPLATAFORMA_AMAZON_DOMINIO`, `MULTIPLATAFORMA_VIDEO_URL_TTL_S`,
`MULTIPLATAFORMA_DRIVE_ROOT`, `MULTIPLATAFORMA_TZ`, `MULTIPLATAFORMA_MUSICA_DIR`,
`MULTIPLATAFORMA_MUSICA_TRABAJO`, `MULTIPLATAFORMA_MUSICA_LUFS`.
Reutiliza `PUBLIC_BASE_URL` y `AUTH_COOKIE_KEY`. Sin cost tracking: las APIs
de publicación son gratuitas.

## Qué falta

1. **App de Meta** (tipo Business) con `instagram_content_publish`,
   `pages_manage_posts`, `pages_read_engagement`, `threads_content_publish`;
   revisión de app (App Review) para usarla con cuentas que no sean de prueba.
   Cuentas IG profesionales vinculadas a una página de FB.
2. **Tokens** de larga duración por cuenta (página FB → IG; Threads aparte) y
   su renovación (los de Threads/IG caducan a 60 días): hoy se pegan a mano con
   `PUT /cuentas/{slug}/tokens`. Falta flujo OAuth y refresco.
3. **Pinterest**: app con acceso **Standard** (con Trial solo sandbox), token
   OAuth con `pins:write`, `boards:read`, y el `board_id` de cada cuenta.
4. ✅ **Timer** (9/10/2026): cron del host cada 15 min (`2,17,32,47`) →
   `~/multiplataforma/tick.sh` (log `~/multiplataforma/tick.log`, `flock`).
   Corre DENTRO del container de la API: las rutas guardadas son las del
   proceso que ingesta (`/mnt/drive/...`); ingestar desde el host guardaría
   `~/gdrive/...`. `scripts/` no va en la imagen, así que el wrapper lo copia
   con `docker compose cp` antes de cada tick. IG no deja programar reels por
   API: la programación es nuestra cola (`programada_en`).
5. Que `PUBLIC_BASE_URL/api/v1/multiplataforma/archivo/...` sea accesible
   desde internet (Caddy) — Meta descarga el vídeo de ahí.
6. Frontend de la cola/cuentas (no hecho; enlaces y tandas van por MCP, a propósito).
7. Tag de Amazon España y enlaces SHEIN del panel de afiliados.
