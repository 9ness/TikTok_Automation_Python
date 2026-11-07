# Programa 4 AI Pro — Viralización 1K y Nicho POV BOF

> Movido literal desde CLAUDE.md (nov 2026) para no cargarlo en cada chat. Se lee solo al tocar este tema.

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

Tiene fuentes propias más, que NO son del Drive del curso y viven en el Drive
montado: **«🌐 Productos Web»** (`productos_web`), que se llena importando los
ZIP que publica la web del curso —carpetas de diez, y el ZIP trae la
convención AL REVÉS: `N` es la ficha y `N.1` la limpia—, y los **dos catálogos
del operador**: «Muestras productos» (`mis_productos`, solo ness/nestor2 como Tareas, el slug es el viejo para
no migrar lo ya guardado; solo IA; una muestra puede ser REEMBOLSABLE —X ventas antes de una fecha, campo `reembolso` del producto, `services/reembolsables.py` con `FUENTES_REEMBOLSO` = Muestras + los dos Productos físicos, revisar cada `REVISAR_CADA_DIAS`, MCP `reembolsables`/`marcar_reembolsable` con `catalogo`, con `importe` € que ordena la prioridad—; además en cualquier catálogo del operador varias MARCAS por producto —`fisico`, `contenido` N vídeos que se descuentan al marcar subido en Mis tandas, `q4`, `clips_reales`— y la lista `prioridades` (contenido → reembolsables por dinero → resto), `services/marcas.py`, MCP `marcar_producto`/`prioridades`, guía `pov-bof.md` §7) y «Tareas Productos» (`tareas_productos`) — muestra
gratuita o tarea pagada, que no se trabajan igual — más «📦 Productos físicos» (`productos_fisicos`, solo ness/nestor2) y «📦 Productos físicos» de Ana (`productos_fisicos_ana`, solo ella) — oct 2026, productos que tienen en casa para grabar con gancho IA (guía `replicar-virales.md`; `usuarios` en SOURCES filtra el selector; se suben desde el menú «Subir productos», `/tiktok-shop-ai-pro/subir-productos`), «🎄 Temporada Q4» (`temporada_q4`, oct 2026: lo más vendido del Q4 anterior según EchoTik, sin saturar; ficha generada con los datos de EchoTik porque la web de TikTok pide captcha) y «🖼️ Carruseles virales» (`carruseles_virales`, COMPARTIDO: alta desde «Replicar carrusel» con foto + ficha + URL, `src/replicar_viral/catalogo.py`). Los sube él (foto limpia +
ficha), viven en su Drive (`Nebulabs/TikTok/TikTok Shop/Nicho_POV_BOF/<slug>/`) en
carpetas de 10, y un producto se puede mover de uno a otro con sus fotos y sus
datos (`mis_productos.mover_producto`). Las fotos se guardan con el MISMO
convenio de nombres del Drive compartido (`3.png` / `3(1).png`) para que
emparejado, textos, ficha y montaje funcionen sin código especial
(`services/mis_productos.py`, que lleva los dos catálogos con un `source`).

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
con las dos promesas el guion se va a ~269 car (~15s) porque en 10s no caben.
Cambiar de cierre NO cuesta una llamada: la CTA es un literal fijo del curso,
así que `config.ajustar_cta` sustituye el final y deja el cuerpo — a Gemini
solo se va cuando el producto no tiene guion o se pide rehacer. Los cinco textos de Klarna (`prompts/guiones_plazos.md`,
`JobMode.NICHO_POV_BOF_PLAZOS_VIDEO`) ya no se usan: son genéricos —no nombran
el producto— y de 253-274 car, o sea vídeos de 13-20s donde se piden 10.

`Productos España` es SOLO LECTURA. El progreso vive en Redis, no en Drive.
Las salidas futuras irán a `Nebulabs/TikTok/TikTok Shop/Nicho_POV_BOF/`.

