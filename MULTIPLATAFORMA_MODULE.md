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
<mount>/Nebulabs/TikTok/TikTok Shop/Multiplataforma/<slug>/
    viralizacion/            → tipo prueba_viral
    viralizacion/publicados/
    producto/                → tipo producto
    producto/publicados/
    fotos/                   → tipo foto (.jpg/.png, solo Facebook)
    fotos/publicados/
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
- `fotos/` (oct 2026, FrutiDramas): una foto suelta por publicación (fotograma
  del episodio en 4:5 + una pregunta genuina en el `.json`) para dar
  interacción a la página entre reels. Ritmo/horas de `foto` (def. 1 a las
  17:00). Se publica con `publicar_fotos` (una foto → `/feed`); IG no admite
  9:16 en foto y Threads necesita ≥2, así que solo Facebook.

## Historias de Facebook (`CuentaDestino.fb_historias`)

Con el flag, tras cada reel publicado en FB (tipos de vídeo, no carrusel ni
foto) el mismo vídeo sale como historia de la página (`/{page_id}/video_stories`,
start → rupload → finish). Si dura más de `MULTIPLATAFORMA_FB_HISTORIA_MAX_S`
(def. 60) se recortan los primeros segundos con ffmpeg. Si falla, el reel ya
está publicado: queda `historia_error` en `resultados.facebook` y no se
reintenta. Activo en `frutidramas`.

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

## Carruseles de fotos (`tipo="carrusel"`, oct 2026)

Los carruseles de «Replicar carrusel» (`src/replicar_viral/carrusel.py`) se
publican con `services/carruseles.py:encolar(slug, carrusel_id, asin|shein, caption, desde)`
(API `POST /cuentas/{slug}/carrusel`, MCP `encolar_carrusel`):
- Copia las fotos listas (con texto quemado, o la de Flow si no lleva) a
  `Multiplataforma/<cuenta>/carruseles/<id>/NN.jpg` y una versión 4:5
  (`ig/NN.jpg`, lienzo 1080×1350 con el fondo desenfocado): **IG rechaza 3:4
  y 9:16**. `Publicacion.imagenes` / `imagenes_ig` / `carrusel_id`;
  `video_path` = la primera foto (identidad / idempotencia).
- Enlace obligatorio (ASIN o SHEIN, se guarda en `enlaces:<slug>` con la misma
  `producto_key` tienda|título). Sin enlace no se encola.
- Hora: `horas["carrusel"]` de la cuenta (por defecto 17:00 ± desfase), ritmo
  1/día, tras el último carrusel programado y no antes de `desde`.
- Texto: el caption de la réplica sin las frases de carrito/TikTok (o el que
  se pase), hashtags sin los de TikTok + los de la tienda.
- Publicación: IG contenedores IMAGE `is_carousel_item` → CAROUSEL `children`
  → `media_publish`; FB `/{page}/photos published=false` → `/{page}/feed`
  `attached_media[i]` + enlace en el primer comentario; Threads items IMAGE →
  CAROUSEL → `threads_publish`; Pinterest `multiple_image_urls` (máx. 5). Los
  ids intermedios (`children`, `photo_ids`, `container_id`) se guardan para
  no duplicar al reintentar.
- **IG y FB van como REEL de fotos con música** (27/10/2026,
  `services/reel_fotos.py`): la API no deja poner música a un carrusel y sin
  ella tenían 0 de alcance. Fotos en 9:16 (fondo desenfocado),
  `REEL_FOTO_S`=3 s cada una con zoom suave, y la pista `musica.meta.fichero`
  de la réplica (o una del banco rotando) a −14 LUFS. Se monta en el tick a
  `<carpeta del carrusel>/reel.mp4` y se reutiliza. Threads y Pinterest
  siguen como carrusel. `MULTIPLATAFORMA_CARRUSEL_REEL=0` vuelve al carrusel.
- **Solos desde el tick** (`carruseles.auto_encolar_todas`, 1 vez/hora): los
  carruseles TERMINADOS de los dueños de las cuentas que no están en ninguna
  cola entran en la de su nicho (`cuenta_para` por `categoria_link`: moda
  mujer → `ama_shop`, belleza/salud → `viva_salud`, resto → `viva_shop`;
  `config.CARRUSEL_CUENTAS`). Los que no tienen enlace en esa cuenta salen en
  `sin_enlace` del tick.log y entran en cuanto se guarde el enlace. IG no
  deja programar por API: lo «programado» es la hora a la que el tick publica.

## Agente diario de enlaces (23/10/2026)

`~/multiplataforma/clasificar.sh` (cron 07:07 UTC, log `clasificar.log`, informe
`clasificar_informe.md`): `claude -p` en modo `dontAsk` con lista blanca (script
`scripts/multiplataforma_enlaces.py`, Chrome del VPS, su informe). Busca ASIN /
enlace SHEIN de `pendientes` y `carruseles`, `guardar` y `encolar`; el tick
reordena por época. Las tres cuentas tienen `priorizar_epocas` y `auto_tandas=7`;
Viva Shop/Salud con `duenos_extra=[nestor2, mauro]`.

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
- **Plan B (30/10/2026), que no haya día sin vídeo:**
  - *Rescate:* una plataforma que acaba `fallido` vuelve a `pendiente` DE CERO
    (sin los ids del intento roto: un contenedor de IG en ERROR no se recupera)
    y la publicación se aplaza `MULTIPLATAFORMA_RESCATE_S` (7200). Máx.
    `MULTIPLATAFORMA_MAX_RESCATES` (1) por plataforma (`Publicacion.rescates`);
    sin fichero no se rescata.
  - *Garantía diaria* (`tandas.garantia_diaria_todas`, en cada tick): desde
    `MULTIPLATAFORMA_GARANTIA_HORA` (22:00, vacío = apagada), si una cuenta con
    ritmo de producto > 0 no ha sacado hoy ningún `producto` en IG ni le queda
    uno para hoy, adelanta a ahora el ÚLTIMO de su cola (no el de mañana). Una
    vez al día (`garantia:<slug>`). viva_salud (ritmo 0) queda fuera.
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
| `garantia:<slug>` | JSON | `{dia, pub}` último día en que la garantía diaria adelantó un vídeo |
| `corto:<código>` | JSON | enlace corto (#296): `{url, cuenta, pid, plataforma, producto_ref, creado_en}` |
| `clics:<pid>` | HASH | `{red: clics}` del enlace corto de esa publicación |
| `embudo:<slug>:<AAAA-MM>` | HASH | página de la bio: `v:<DD>` visitas del día, `c:<DD>:<producto_key>` clics en ese producto |
| `embudo:tope:<slug>:<minuto>` | INT (EX 2 min) | tope de avisos por cuenta y minuto |
| `comenta_si:hecho:<comment_id>` · `comenta_si:usuario:<media>:<usuario>` | STR (EX 30 d) | «Comenta SÍ» ya atendido |
| `comenta_si:hora:<slug>:<AAAAMMDDHH>` | INT (EX 1 h) | tope por cuenta y hora |
| `comenta_si:seco:<fecha>` | JSON lista | lo que se HABRÍA mandado en seco (máx. 500/día) |

## API (`/api/v1/multiplataforma`, API key)

`GET /cuentas` (sin tokens) · `POST /cuentas` · `PUT /cuentas/{slug}/tokens`
(solo escritura) · `POST /meta/conectar-facebook` y `/meta/conectar-threads`
(pantalla web `/tiktok-shop-ai-pro/conectar-meta`, también en el menú de Ana (`pro` tiene `/meta/*`): se pega el token de usuario FB ampliado → saca el de
cada página por `/me/accounts`, y el de Threads se casa por el id de `/me`; el token
es la prueba de permiso y nunca se devuelve) · Threads por OAuth: `GET|POST /meta/threads/app` (id + clave secreta de la app, en Redis `threads_app`, nunca se devuelve), `GET /meta/threads/autorizar` (URL de permiso con `state` firmado) y **público** `GET /meta/threads/retorno` (canjea el `code` por token de 60 días y vuelve a `/conectar-meta`); el tick renueva cada token de Threads semanalmente (`renovar_tokens_threads`, marca `threads_renovado`). Existe porque el generador de tokens de Meta falla desde el navegador de Messenger · `POST /publicaciones` (encola; `asin` o `enlace`; mismo
vídeo+cuenta+tipo pendiente no se duplica) · `GET /cola?todas=` ·
`POST /tick?dry_run=true` · `POST /cuentas/{slug}/ingestar` · **público**:
`GET /archivo/{token}` (vídeo firmado; solo sirve rutas —resueltas, sin
symlinks ni `..`— bajo la raíz Multiplataforma, la del Programa 4
`Nebulabs/TikTok/TikTok Shop/` (vídeos de Mis tandas), `temp_work/` o `API_TEMP_ROOT`).

### Enlaces por producto y resubida de Mis tandas

Los gestiona SOLO el agente por MCP (guía
[`src/agente_mcp/guias/multiplataforma.md`](src/agente_mcp/guias/multiplataforma.md)):
no hay pantalla en la app. La cuenta necesita `dueno` (usuario cuyas tandas se
resuben: `ama_shop`→ana, `viva_shop`→ness) y puede sumar `duenos_extra`
(`viva_shop`/`viva_salud` → nestor2, mauro): sus filas llevan el usuario
delante del id (`nestor2::pov|…`) para sacar la foto. Entran también las
réplicas virales ya montadas (`fuentes.replicas_video`, ids `rv|…`).
Desde la terminal del VPS: `scripts/multiplataforma_enlaces.py`
(`pendientes` · `carruseles` · `guardar` · `encolar`, dentro del contenedor),
pensado para el agente diario que busca los enlaces.

**Orden por época** (`priorizar_epocas` en la cuenta): el tick, una vez por hora, rehace la cola (`tandas.replanificar`) sin huecos y con el ritmo y las horas de la cuenta. Producto va por prioridad: réplicas virales → Halloween → Black Friday → Navidad → otoño/invierno → neutro (época de Mis tandas), y dentro, semáforo verde antes que sin revisar y ámbar. Fuera de su ventana (`config.VENTANA_EPOCA`) una época no se encola y lo ya encolado pasa al final. Rojo nunca se encola. Los mudos «Solo Meta» de Ana entran revisados aunque no estén en TikTok. No toca lo ya empezado ni lo que sale en menos de 45 min.

**El mismo producto no sale días seguidos** (`tandas.espaciar`, 9/11/2026): una tanda trae varios vídeos del mismo producto y salían uno detrás de otro (viva_salud publicó la misma proteína 7 días seguidos). Al encolar y al replanificar, un `producto_ref` no vuelve a salir hasta pasados `MULTIPLATAFORMA_SEPARACION_PRODUCTO_DIAS` (3, aprobado por Néstor 9/11; 0 = apagado), contando lo publicado esos días. Reordena lo mínimo y solo dentro de la misma prioridad (nunca adelanta lo neutro a lo de temporada) y nunca deja nada sin salir: si solo quedan vídeos de ese producto, salen. Solo cambia el orden, no lo que se publica.

**¿Cabe lo de temporada? (`tandas.capacidad_epocas`, 9/11/2026):** por cada época con la ventana abierta, cuántos vídeos de producto hay en cola, cuántos salen a tiempo y cuántos saldrían cuando ya ha pasado, y el `ritmo_necesario` (vídeos de producto al día para que todo lo de temporada quepa, sacando antes la época que antes acaba). Solo lee. Lo recogen el vigía (`cuentas.<slug>.epocas` → incidencia `cola:<slug>:epocas`, nivel aviso) y las estadísticas (`epocas` por cuenta → sección «Temporada: ¿cabe en la cola?» del informe). La época de una copia con música sale del `.json` de al lado (`original`), y esa ruta se lleva a donde está hoy la carpeta (`rutas_drive.a_absoluta`): tras la mudanza del Drive del 5/11 guardaba la ruta vieja y 137 vídeos de ama_shop (39 de otoño) contaban como «neutro» al ordenar por época.

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
- **Temporada** (`temporada` en el enlace: `verano`/`invierno`/`navidad`,
  meses en `config.TEMPORADAS`): el enlace se guarda todo el año, pero
  `encolar` solo publica en esos meses (`omitidas.fuera_temporada`). Una
  tumbona o una piscina no salen en Q4.
- **Encolado automático** (`CuentaDestino.auto_tandas` = N días, 0 = apagado):
  el tick llama a `tandas.auto_encolar_todas` (máx. 1 vez/hora por cuenta,
  marca `auto_tandas:<slug>`) y rellena hasta N días de vídeos `producto` en
  cola. Así, un vídeo nuevo marcado subido a TikTok de un producto CON enlace
  entra solo. Las dos cuentas de `ness` reparten por dónde está el enlace:
  salud/belleza en `viva_salud`, el resto en `viva_shop`.
- `producto_key` = sha1 de `norm(tienda)|norm(título)`[:16]: vale para todas
  las versiones del producto (modos del Largo, POV BOF, copias Q4). Si se
  reescribe el título cambia → hay que volver a guardar el enlace.

**Página pública** `/links/<cuenta>` (Next, sin login, `noindex`) — la de la
bio de IG/FB. Lee `GET /links/{slug}` (público, sin auth, caché 120 s: solo
id, título corto, foto, enlace, tienda, `categoria`, `publicado_en` +
`aviso_amazon` si hay alguno de Amazon; SOLO productos ya publicados en
alguna red —los enlaces se preparan en lote para la cola y no salen hasta su
vídeo—; orden: lo último publicado primero; categoría por palabras del título,
`config.CATEGORIAS_LINKS`). La página pone el último en grande, chips de
categoría, buscador y la lista de 20 en 20 con miniaturas `?w=192` y `GET /links/{slug}/foto/{producto_key}?w=`
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
`MULTIPLATAFORMA_MUSICA_TRABAJO`, `MULTIPLATAFORMA_MUSICA_LUFS`, `MULTIPLATAFORMA_CARRUSEL_REEL`,
`MULTIPLATAFORMA_ENLACE_CORTO` (0), `MULTIPLATAFORMA_ENLACE_CORTO_AMAZON` (0), `MULTIPLATAFORMA_ENLACE_CORTO_BASE`,
`MULTIPLATAFORMA_SEPARACION_PRODUCTO_DIAS` (3; 0 = sin separar), `MULTIPLATAFORMA_EMBUDO_TOPE_MINUTO` (300),
`MULTIPLATAFORMA_COMENTA_SI_ENVIAR` (0), `MULTIPLATAFORMA_COMENTA_SI_DIAS`, `MULTIPLATAFORMA_COMENTA_SI_TOPE_HORA`,
`MULTIPLATAFORMA_RESCATE_S`, `MULTIPLATAFORMA_MAX_RESCATES`, `MULTIPLATAFORMA_GARANTIA_HORA`, `MULTIPLATAFORMA_IG_GRACIA_ERROR_S` (180: segundos que se sigue sondeando un contenedor de IG en ERROR antes de tirarlo).
Reutiliza `PUBLIC_BASE_URL` y `AUTH_COOKIE_KEY`. Sin cost tracking: las APIs
de publicación son gratuitas.

## Estadísticas semanales (6/11/2026)

`scripts/multiplataforma_estadisticas.sh` copia `scripts/multiplataforma_estadisticas.py` al contenedor y guarda en
`~/multiplataforma/estadisticas/<fecha>.json` los últimos 7 días de viva_shop, viva_salud y ama_shop: seguidores y totales
por plataforma, cada publicación, media por `tipo`, `salud` (estados y comentarios de FB fallidos) y `en_cola`. Solo lectura,
sin tokens en la salida; una métrica sin dato queda en `null`. La analiza la rutina `~/rutinas/meta-semanal.md` (lunes).

Desde el 9/11 cada publicación lleva también `pid`, `hora`, `ts`, `origen` y `producto_ref`, y el `.sh` genera además
`semanal_<fecha>.md` con `scripts/multiplataforma_informe.py` (host, solo stdlib; lógica en `services/informe.py`, tests en
`tests/multiplataforma/test_estadisticas.py`). Junta todas las lecturas (manda la más reciente) y ordena por MEDIANA de vistas
de IG: por cuenta·formato (`viral_pablo_motos` y `remedios` salen del título), plataforma, franja horaria y día, top 10,
«despegaron» (≥10× la mediana de su cuenta), «no despegan» (≥48 h y <¼ de su mediana), FB a cero y seguidores frente a hace
una semana. No se vuelca a `video_stats` del panel: ese esquema es de TikTok (programa, hora de México, recompensas).

Del 9/11 (sprint Fable) también: «Hora dentro de cada formato» (franjas con ≥3 publicaciones del mismo formato: la tabla
general de horas mezcla formatos y ahí gana la hora del formato que más rinde, no la mejor hora), «Mismo producto ≥3 veces»
en la semana por `producto_ref` (viva_salud sacó el mismo whey 7 días seguidos), «Página de la bio» (embudo) y
«Temporada: ¿cabe en la cola?» (`epocas` de cada cuenta).

## Vigía de salud (9/11/2026)

`scripts/multiplataforma_salud.sh [--dry-run]`: el recolector `scripts/multiplataforma_salud.py` corre en el
contenedor (solo lectura, nunca saca tokens: de cada uno, si vale, cuándo caduca y sus permisos; cola de 7 días;
reproducciones de los reels de FB) → `~/multiplataforma/salud_datos.json`; el host lo analiza con
`src/multiplataforma/services/salud.py` (stdlib) junto con la cola de `tick.log` y avisa a `/api/avisos` del panel.
Incidencias: token inválido o que caduca en <3 días (grave, notifica), Threads sin renovar >14/50 días, publicaciones
pendiente/error >1 h tras su hora, fallidas en 48 h (error normalizado), FB a cero (≥3 reels >48 h, todos ≤2), tick
parado >45 min (grave, notifica) o con Traceback en los últimos 4, y recolector caído. Deduplica con
`~/multiplataforma/salud_estado.json`: una vez por incidencia, recordatorio a los 7 días, aviso si sube de nivel y
«✅ Resuelto» al desaparecer; si el POST falla, se reintenta en el siguiente pase. No reintenta, no publica, no borra.
Cron propuesto (pendiente de Néstor): `7 * * * * ~/proyectos/TikTok_Automation_Python/scripts/multiplataforma_salud.sh >> ~/multiplataforma/salud.log 2>&1`.

## Enlace corto con clics (#296) y «Comenta SÍ» (#297) · 9/11/2026

Los dos están **apagados**; encenderlos cambia lo que sale publicado → «sí» de Néstor.
- **Enlace corto** (`services/enlace_corto.py`, `MULTIPLATAFORMA_ENLACE_CORTO=1`): en `publicador._ejecutar` la COPIA
  que se envía lleva `<base>/<código>` en el texto de Threads, el comentario de FB y el `link` de Pinterest (la cola
  guarda el original). Código = `sha1(pid|red)` en 8 letras base32 (reintentos no crean otro). Público
  `GET|HEAD /api/v1/multiplataforma/links/r/{código}` → 302 al enlace guardado (solo https y sin acortadores), suma
  `clics:<pid>` si es GET y no es rastreador (`config.BOTS_USER_AGENT`). Base por defecto la ruta larga, que
  links.nebulabsmedia.com ya sirve; con una regla `/r/*` en el Caddy de vps-webs → `MULTIPLATAFORMA_ENLACE_CORTO_BASE`.
  Amazon NO se acorta salvo `MULTIPLATAFORMA_ENLACE_CORTO_AMAZON=1` (normas de afiliados). Los clics van al JSON de
  estadísticas (`clics`) y al informe semanal («🔗 Clics en el enlace»).
- **Comenta SÍ** (`services/comenta_si.py`, pase con `scripts/multiplataforma_comenta_si.py` dentro del contenedor):
  reels de IG publicados con enlace de los últimos `COMENTA_SI_DIAS` (7) → `GET /{media}/comments` → `es_si` (corto,
  empieza por sí/siii/yes) → mensaje privado `POST /{ig_user_id}/messages` `{recipient:{comment_id}}` con
  `prompts/comenta_si.md` (en IG un enlace en respuesta pública no es clicable). Una vez por comentario y por
  usuario·reel, tope `COMENTA_SI_TOPE_HORA` (30) por cuenta; si el envío falla no se marca y se reintenta. En seco
  (por defecto) solo anota en `comenta_si:seco:<fecha>`; enviar = `MULTIPLATAFORMA_COMENTA_SI_ENVIAR=1`, con la app en
  Live y `instagram_manage_comments` + `instagram_manage_messages`. Sin cron todavía.

## Embudo de la página de la bio (9/11/2026)

En IG el pie de un reel no lleva enlace: quien quiere el producto pasa por `/links/<cuenta>`. `services/embudo.py`
cuenta por día las **visitas** a la página y los **clics por producto**, para saber cuánta gente llega de la bio y
qué abre. El enlace sigue yendo DIRECTO a la tienda (Amazon no admite acortadores): `LinksCuenta.tsx` avisa aparte con
`navigator.sendBeacon` a `POST /api/v1/multiplataforma/links/{slug}/evento` (público, cuerpo
`{"tipo": "visita"|"clic", "producto": key}` como text/plain, siempre 204). Solo contadores: sin cookies, IP ni
identificador (lo dice la página de privacidad). No cuentan los rastreadores (`BOTS_USER_AGENT`), los productos que no
están en la página ni lo que pase de `MULTIPLATAFORMA_EMBUDO_TOPE_MINUTO` (300) avisos por cuenta y minuto; si Redis
falla, la página no se entera. `scripts/multiplataforma_estadisticas.py` vuelca `embudo` por cuenta (`visitas`,
`clics`, `por_dia`, top de `productos` con título) y el informe semanal saca «🧭 Página de la bio» (clics por visita y
lo que más se abre). No cambia nada de lo que se publica. Al desplegar: comprobar que el Caddy de vps-webs deja pasar
el POST a `/api/v1/multiplataforma/links/*`. Tests: `tests/multiplataforma/test_embudo.py`.

## Qué falta

1. **App de Meta** (tipo Business) con `instagram_content_publish`,
   `pages_manage_posts`, `pages_read_engagement`, `threads_content_publish`;
   revisión de app (App Review) para usarla con cuentas que no sean de prueba.
   Cuentas IG profesionales vinculadas a una página de FB.
2. **Tokens** de larga duración por cuenta (página FB → IG; Threads aparte) y
   su renovación (los de Threads/IG caducan a 60 días): se pegan en la pantalla `/tiktok-shop-ai-pro/conectar-meta`
   (o `PUT /cuentas/{slug}/tokens`). Threads: botón «Conectar Threads» (OAuth) y renovación semanal en el tick.
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
