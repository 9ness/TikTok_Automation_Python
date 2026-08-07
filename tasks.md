## 👤 Tareas Humanas

- [ ] **EchoTik plan de pago (Radar v2)** — el motor está construido y VERIFICADO contra ES (`services/fresh_ads_discovery.py`, 14 tests); solo falta cuota.
  1. Correo a `massif@echotik.live` **desde `ness4b@gmail.com`** pidiendo presupuesto de **25.000 / 50.000 requests/año** (uso real ~8.800/año) + opción mensual. Incluir el `username` de la API key de `ness4b` (echotik.live/platform/api-keys). Preguntar por qué su web anuncia ¥0.001/request (~14$/100k) si el presupuesto que dieron fue ~100$/100k — son 7x.
  2. ⚠️ **Al activar el plan: cambiar `ECHOTIK_API_USER`/`ECHOTIK_API_PASSWORD` del `.env` del VPS** (`/home/nebulabsai/TikTok_Automation_Python/.env`) por las de `ness4b`. Ahora mismo tiene las de una cuenta de PRUEBAS (le quedan ~42 llamadas) → si no se cambia, el Radar tirará de una cuenta agotada. Recrear contenedor `api` después.
- [ ] **PENDIENTE · Editor Auto email avisos**: generar *contraseña de aplicación* en `nebulabsaimedia@gmail.com` (Google Account → Seguridad → Verificación en 2 pasos → Contraseñas de aplicación → "Correo") y añadir al `.env` del server: `EDITOR_SMTP_USER=nebulabsaimedia@gmail.com` + `EDITOR_SMTP_APP_PASSWORD=<16 chars>` → recrear contenedor `api`. Hasta entonces, el botón "Marcar día listo" solo comparte la carpeta de salida (sin email). El código ya está listo (`src/editor_auto/services/email_notify.py`).
- [ ] **Editor Auto planes baratos** (cuando se asignen): meter al seeder Esencial 5 (249€/+fotos 289€) y Plus 10 (349€/+fotos 399€). Por ahora la config (delay + máx/día) se hace por usuario a mano.
- [ ] Probar generación async de presets en local (`/tiktok-shop/products/<id>` → tab Presets → "Regenerar todos") y verificar: barra progreso, cambio de tab sin perder estado, hard refresh recupera, toast final.
- [ ] Si OK → commit + push los cambios pendientes de la sesión (ver `SESSION_STATE.md` "Próximos pasos")
- [ ] Tras push → SSH al VPS y disparar `deploy_safe.sh` para aplicar
- [ ] Probar el flujo end-to-end del refactor TikTok Shop: crear producto desde URL → fotos → análisis → presets → /generate con bulk + smart variants

## 🗂️ Drive "Productos España" — mapa de carpetas por nicho (2026-08-03)

Explorado entero. Tenía 16 subcarpetas, no las 2 que conocíamos. La carpeta que
el operador pasó por enlace (`10jSRauIlUVFXo3Dr6RCi8iO1gIY2TDIL`) resultó ser
`Camisetas／Conjuntos/Jonny/1`.

### Ropa — hay MÁS producto y un prompt más

| Carpeta | ID | Fotos | Nota |
|---|---|---|---|
| `Camisetas／Conjuntos/Jonny/1` | `10jSRau…` | 16 → **8 prendas** | Ya conectada |
| `Ropa/Ropa Mujer/1 Mono` | `1MXBSXZRwqbo1F25OAM-MhO-qTf4SmxyK` | 14 → ~7 | **Sin conectar** |
| `Ropa/Ropa Mujer/2 Pantalon corto` | `11enOhq4DL_lmdttQWqgowmA1MRqrR3_0` | 10 → ~5 | **Sin conectar** |
| `Ropa/Ropa Mujer/Bikinis` | `1T-nqij3xl4Dp-h2JvGJofCq6Wzoia25a` | 14 → ~7 | **Sin conectar** |

✅ **RESUELTO (2026-08-03).** Las tres carpetas de `Ropa Mujer` son la materia
prima del MÓDULO 7 (ropa CON personas, que va con producto de mujer). Pero
**una misma prenda vale para los dos nichos**: puesta por una modelo (módulo 7)
o colgada en percha (módulo 8). Lo que cambia es el prompt, no la foto.

Por eso las cuatro carpetas están conectadas al módulo 8 con un selector, y
cuando se monte el 7 se conectarán también allí. La relación carpeta→nicho NO
es 1 a 1.

**Prompts de `Camisetas／Conjuntos/Ropa/Pronts/`** — 6, y solo DOS son sin personas:

| Prompt | ¿Sin personas? | Nicho |
|---|---|---|
| `Pronts/Pronts.docx` | ✅ | Es EXACTAMENTE el que ya está implementado (alfombra + luces LED) |
| `Ropa Percha.docx` | ✅ | ✅ **AÑADIDO** — prenda colgada en percha, sin modelos, mano que acaricia + zoom in/out. Sale como "Vídeo · percha" en la pantalla del nicho |
| `Pront Generico.docx` | ❌ modelo | Módulo 7 (con personas) |
| `Pront Movil Generico.docx` | ❌ chica con móvil | Módulo 7 |
| `Pront Pantalones.docx` | ❌ modelo | Módulo 7 |
| `Pront Pijamas.docx` | ❌ modelo | Módulo 7 — **esto es lo de los pijamas que preguntó el operador: NO es de este nicho** |
| `Pront Vestidos.docx` | ❌ modelo | Módulo 7 |

### El nombre de la carpeta ES el prompt a usar

Descubrimiento útil para automatizar: las carpetas de producto se llaman igual
que los prompts de escenario. `Zapatillas/13 Terraza Mesa` + `Suplementos/1
Terraza Mesa` ↔ `Pronts/BOF Videos 8 Segundos/Terraza Mesa BOF.docx`. Es decir,
el nombre de la carpeta dice con qué prompt se monta. Eso permite elegir el
prompt SOLO, sin que el operador lo diga.

Escenarios que hay (`Pronts (1)`, dos versiones de cada uno):
- **BOF 8 segundos**: Almacén Suelo · Almacén Mesa · Maquinaria · Mujer Terraza
  Mesa · Deck Muebles · Terraza Césped · Terraza Mesa
- **MOF 15 segundos**: Almacén Suelo · Almacén Mesa · Terraza Césped · Terraza Mesa
- General: `Pront General Kling.docx`

### Resto de carpetas → a qué nicho van

| Carpeta | Contenido | Nicho |
|---|---|---|
| `Zapatillas/` | 6 carpetas `13-18 Terraza Mesa` | Módulo 12 — Zapatos |
| `Zapatos Mujer/` | 20 fotos sueltas | Módulo 12 — Zapatos |
| `Gorras/` | Por persona (Bilal, Claudia, Claudio, Jonny, Víctor) + `1Pronts` + `Tiendas Asignadas.docx` | Módulo 11 — Gorras |
| `Carruseles/` | `Productos Carruseles` + `Pronts Carruseles` | Módulo 14 — Carruseles |
| `Creativos/` | 8 fotos | Módulo 13 — Creativos Profesionales |
| `Suplementos/` | 4 carpetas `Terraza Mesa` | POV BOF / General |
| `Top Ventas/` | Abril 2026 · Mayo 2026 · Productos Alumnos | Referencia, no producción |
| `BILAL PRODUCTOS ESPAÑA/` | 19+ carpetas numeradas | Sin asignar — preguntar |
| `No Tocar/` | Bilal · Mikomika · Varios + 20 fotos | **No tocar** (lo dice el nombre) |
| `Sin Existencias ZHIMING_SPAIN/` | `3 Pront Flow`, `4 Pront Flow` | Descartado (sin stock) |

## 🌍 Viralización — ampliar a más ponentes (España) y a Estados Unidos

**Tarea grande y tediosa, NO empezar hasta que el operador lo pida.** Él avisa
cuando se vaya a dormir; son ~2h. Trabajo repetitivo → repartir entre varios
subagentes y **verificar SIEMPRE con capturas** (que el recorte no corte la
cabeza, que no haya texto quemado en los paisajes, etc.).

### Reparto del trabajo
- **El operador** revisa los AUDIOS: algunos duran 2 min y pico y hay que
  trocearlos en trozos de ~40s (como se hizo con Pablo y Víctor). Lo hace él
  por la mañana; no tocar los audios.
- **Yo** hago los ganchos y los clips de paisaje.

### España
1. Sacar los **ganchos** (trozos de 3s con la cara en primer plano) de las
   personas que faltan, además de Pablo Motos y Víctor Küppers.
2. Ojo al ENCUADRE, que no es igual en todos: Víctor se mueve por el
   escenario y hubo que centrarlo (`cx_frac` del escaneo de cara); Pablo sale
   bien de serie. Hay que mirarlo persona a persona.

### Estados Unidos — Billy Graham (4 ago, mañana)

**Hecho y desplegado:**
- Imagen de la API de 12 GB a **4,6 GB** (torch CPU-only; el VPS no tiene GPU).
  Con eso el disco pasó de 11 a 23 GB libres y los deploys vuelven a caber.
- País por ponente, idioma de Whisper por ponente, pool de paisajes por país.
- **161 ganchos** precortados y verificados con capturas: sin logo, sin
  teléfono y con la cara bien encuadrada. Sermones fuente borrados.
- Voces: 30 MP3 ya en `billy/audios/`.

**Lo aprendido con los sermones (por si se añade otro ponente de EEUU):**
el logo llega hasta x=900 y el teléfono empieza en x=1300, así que entre los
dos NO cabe un recorte 9:16 — mover el encuadre no sirve. Se declara
`recorte_util` en `PONENTES` (aquí, quitar de y=770 abajo) y se aplica al
precortar, así el renderer vuelve a encuadrar libre.

**En marcha:** trocear el vídeo de paisajes de EEUU (151 min, 80 lugares) a
`paisajes_clips_us/`. El recorte 9:16 centrado ya deja fuera la marca "EPIC" y
el nombre del sitio, así que el OCR de descarte se pasa SOBRE EL RECORTE, no
sobre el fotograma entero.

**Falta después:** borrar el vídeo fuente (6,2 GB) y probar un lote de Billy
Graham de punta a punta.

### Estados Unidos — SOLO BILLY GRAHAM (decidido 2026-08-03)

**No empezar hasta que el operador lo diga; lo pedirá POR LA NOCHE** para que
corra mientras duerme (descargar y trocear un vídeo de paisajes son horas).

Material localizado en Drive (compartido, `--drive-shared-with-me`):
`Skool/Estrategia viralización/Estados Unidos/`

| Carpeta | Contenido |
|---|---|
| `Billy Graham/Videos Gancho/` | 2 sermones completos: *Jesus Calls You by Name* (309 MB) y *The Holy Spirit and You* (291 MB) |
| `Billy Graham/Voces Billy/` | **31 MP3** ya troceados, casi todos ~2.3 MB (≈1 min) → no hace falta el cortador de clips |
| `Videos Paisajes/` | 4 vídeos, **22 GB en total** (5.9 + 3.1 + 2.9 + 10.0 GB) |
| `Warren Buffet/`, `Dante Gabel/`, `Hombre podcast/` | **APLAZADOS** |

**Por qué solo Billy Graham:** los de Warren Buffett son vídeos YA MONTADOS, así
que habría que cogerlos tal cual y quitarles el copyright cambiando paisajes o
similar — mucho más difícil. Billy Graham es el caso limpio: sermón en bruto +
voces sueltas.

Qué hay que hacer:
1. **Ganchos.** Sacarlos de los 2 sermones. Ojo: hay que **mirar dónde se le ve
   a él bien encuadrado y que no haya texto quemado** (estos sermones llevan
   rótulos y subtítulos incrustados que estropean el gancho). Mismo escaneo de
   cara que en España, pero revisando a mano con capturas.
2. **Paisajes.** Con **UN solo vídeo basta**, dice el operador: 4 son demasiado
   contenido. Elegir uno y trocearlo como se hizo con España
   (ver `VIRALIZACION_MODULE.md`), descartando los planos con texto o logos.
   ⚠️ **Disco:** quedan ~11 GB libres y el más pequeño pesa 2.9 GB. Descargar
   UNO, trocearlo, y BORRAR el fuente al terminar — es lo que ya se hizo con
   España (ver `paisajes/_fuente_en_drive/LEEME.txt`).
3. **Voces:** las 31 ya sirven tal cual. No tocarlas de entrada.

Tres cosas del código que HOY asumen España y hay que tocar:
- `config.WHISPER_LANGUAGE = "es"` es **global** → Billy Graham habla inglés.
  Tiene que pasar a ser por ponente.
- `config.paisajes_folder()` es **una sola carpeta compartida** por todos los
  ponentes → hacen falta dos pools (paisajes ES / paisajes US), o los vídeos de
  Billy Graham saldrían con paisajes de España.
- `PONENTES` no tiene país; hace falta para el selector España/EEUU del punto 5.

Más adelante: probar a subir con esa persona y ver si funciona antes de meter
al resto.

### Recortes de audio que indicó el operador (Mario, España)
Solo hay que recortar los de Mario; el resto de España valen tal cual.

| Audio | Dura | Corte indicado | Queda |
|---|---|---|---|
| `audio mario 1.MP3` | 1:31 | 1:22 | 82s |
| `audio mario 2.MP3` | 1:33 | 1:25 | 85s |
| `audio mario 5.MP3` | 2:02 | 1:25 | 85s |

⚠️ **Siguen por encima del tope de 75s** (ver bloqueo abajo): tal cual, el
pipeline recortaría por su cuenta los últimos 7-10s. Confirmar con el
operador si recorta más (~70s) o si se monta por tandas.

### Producto final
5. En el menú de **Viralización 1K**, selector **España / Estados Unidos**;
   al elegir uno salen solo los ponentes de ese sitio.

### Bloqueo conocido: duración máxima de vídeo (~75s)
La biblioteca de paisajes son planos MUY cortos (el más largo 6,8s útiles,
mediana 2,6s), así que los `MAX_PAISAJE_CLIPS` (12) de un vídeo suman ~72s de
b-roll → tope real ~75s de vídeo. `MAX_VIDEO_DURATION_S` está puesto en 75
como guardarraíl: por encima, el allocator mete 20-40 clips y el `xfade` mata
a ffmpeg por OOM (un decodificador 1080x1920 por clip, VPS de 8 GB; pasó con
19 clips).

Para vídeos más largos NO basta con subir el tope: hay que montar los
paisajes **por tandas** (grupos de ~8 y luego concatenar) en vez de un solo
`xfade` con N entradas. Decisión del operador (2026-07-29): de momento él
recorta los audios largos en vez de tocar el render.

### Pendiente de aclarar antes de empezar
- ~~Dónde está el material~~ → localizado (ver tabla de EEUU arriba).
- **Cuál de los 4 vídeos de paisajes de EEUU** se trocea. Por tamaño, el de
  2.9 GB (*MOST STUNNING 8K HDR*) es el que menos disco pide; el de 5.9 GB
  (*Maravillas de Estados Unidos, 80 lugares*) es el que más variedad de sitios
  tendría. Preguntar antes de descargar.

## 🤖 Cola del Agente

### [ ] Unificar la pantalla del POV BOF Largo con la del POV BOF ⬅️ SIGUIENTE

Lo pidió el operador el 2026-08-06: *"el POV BOF Largo es visualmente diferente
al POV BOF, quiero que se parezca lo máximo posible"*. Son el MISMO catálogo de
productos; lo único que cambia de verdad es que la voz es un guion escrito por
IA y locutado con Fish, y que van dos clips de 10s en vez de uno.

**Los dos ficheros:**
- `frontend/app/tiktok-shop-ai-pro/nicho-pov-bof/page.tsx` — 2.173 líneas (el bueno)
- `frontend/app/tiktok-shop-ai-pro/pov-bof-largo/page.tsx` — 401 líneas (el pobre)

**Lo que le falta al Largo** (comprobado por grep, no de memoria): barra de
Escaparate + Vendidos con contador, botón "Textos" (extraer con Gemini), botón
de descargar todas las fotos, chips de hashtags, la caja de "Mis productos"
(`AltaMiProducto`) y el selector de fuente con las tres carpetas. Ya comparte
`CopyChip` y `FotoModal` en `frontend/components/tiktok-shop-ai-pro/`.

**Ya está hecho y NO hay que rehacerlo:** las ventas se apuntan por nicho —
`NICHOS_VENTA` en `src/nicho_pov_bof/repos/product_repo.py:526` ya incluye
`pov_bof_largo`, y `marcar_vendido(..., nicho=)` / `ranking_vendidos(nicho=)`
aceptan el filtro.

**Cómo abordarlo:** el camino sano es extraer de `nicho-pov-bof/page.tsx` los
bloques comunes a `components/tiktok-shop-ai-pro/` y que las dos páginas los
consuman, NO copiar y pegar (ya somos 8 nichos con pantalla casi igual: cine,
ropa, ropa-personas, gorras, cuenta-piloto, creativos… cada copia nueva es otro
sitio donde arreglar el mismo bug). Es un refactor grande: **abrirlo en sesión
nueva y limpia**, no de cola de otra tarea.

**Cuidado con dos cosas que ya mordieron:**
- Nada de `export const` en un `page.tsx` de Next: rompe el type-check de rutas.
  Lo compartido va a `components/` o `lib/`.
- Todo mobile-first (el operador trabaja desde el móvil): `grid-cols-2
  sm:grid-cols-N`, diálogos `w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto`.

- [ ] `deploy_safe.sh`: purgar caché de Docker ANTES de construir. El disco
      llega al 100% cada pocos deploys (hacen falta ~14 GB transitorios) y ya
      truncó `page.tsx` a 0 bytes una vez.
- [ ] `list_carpetas` se traga los errores: devuelve [] cuando Drive falla,
      indistinguible de "no hay carpetas".

- [Viralización] `MAX_VIDEO_DURATION_S = 130` contradice el diseño (20-60s) y
  los docstrings ("~55s", "163s → 3 trozos"; con 130 sale 1 trozo + resto). Ya
  NO es inerte: Billy Graham tiene 6 audios de más de 90s y uno de 180s que se
  parte en 130s + 50s. Decidir: bajar el tope o corregir los docs.
- [Viralización] `is_valid_mp4(min_duration=MIN_VIDEO_DURATION_S*0.8)` = 16s
  fijo: un audio corto genera un MP4 correcto que se declara inválido y se
  borra. Debería medir contra `win_dur` esperado, no contra una constante.
- [Viralización] `VIRALIZACION_MODULE.md:85` y `:248` siguen documentando
  `gdrive:VIRALIZACION/...` (la ruta real ya es
  `NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/VIRALIZACION`).
- [Viralización] El "reanudar batch" (skip de MP4 ya válidos) es código muerto:
  `batch_id` lleva un uuid aleatorio, así que el staging nunca preexiste.
## ✅ Done

- [2026-08-05] [Programa 4] **Cuenta Piloto** completa: `src/cuenta_piloto/`
  (config + `repos/{redis_base,product_repo}` + `services/{photo_store,text_extractor}`
  + `pipeline/video_editor`), `JobMode.CUENTA_PILOTO_VIDEO` + `run_cuenta_piloto_video`,
  router `/api/v1/cuenta-piloto/*` (8 endpoints), página
  `/tiktok-shop-ai-pro/cuenta-piloto` + item de sidebar, 12 tests.
  Lo nuevo respecto al resto de nichos: producto creado SUBIENDO las dos fotos
  (primer nicho sin Drive), aislamiento por usuario y **lista de vídeos** por
  producto (`add_video`, bajo cerrojo) en vez del `video_path` único.
  De paso, `queue-meta.ts` y la union `JobMode` del frontend, a las que les
  faltaban `nicho_ropa_personas_video` y `nicho_bof_cine_video` desde que se
  crearon esos nichos.

- [2026-08-04] [Viralización] Rótulos que se colaban en los paisajes: el filtro
  miraba UN fotograma a 0,5s y las cartelas entran animadas. `services/rotulos.py`
  muestrea 5. Retirados 22 clips de 300 en EE.UU. (mapas `UNITED STATES`,
  cartelas de sitio y 5 con el botón `SUSCRIBIRSE`). España comprobada por
  muestreo y NO tocada: sus 2 positivos eran letreros filmados.
- [2026-08-04] [Viralización] `renderer.py`: el `work/` de clips se borra ya en
  `try/finally`, no solo en el camino feliz.
- [2026-08-04] [Nicho POV BOF] Modo escaparate: pendientes agrupados por tienda
  (una búsqueda en el Marketplace por tienda en vez de una por producto) con
  estado `en_escaparate` privado por usuario.
- [2026-08-04] [Nicho POV BOF] Buscador de productos en las 35 carpetas (dos
  `mget`, 0,5s) para dar con el que vendió y marcarlo desde el resultado.

- **Voz del Nicho POV BOF más alta sin saturar** — normalización por sonoridad
  en dos pasadas + compresor. De -17/-23 LUFS a -12,5/-14 con picos bajo
  -0,9 dBTP. (`alimiter` necesita `level=disabled` o re-nivela hacia arriba.)
- **Caption sin promesas** — el prompt describe en vez de prometer y
  `caption_arriesgado()` avisa en la ficha si se cuela una.
- **Botones Ver/Descargar + refresco en caliente** del vídeo montado.

- [2026-07-28] [Nicho POV BOF] Fase 2 backend: `services/audio_bank.py` (banco
  de audios locutados en Drive + recorte de silencios con ffmpeg
  `silenceremove`, versión procesada cacheada en `_procesados/` sin tocar el
  original), `JobMode.NICHO_POV_BOF_VIDEO` + `run_nicho_pov_bof_video`
  (textos guardados → audio preparado → `video_editor.build_video` → copia a
  Drive `.../videos/<folder>/<producto> <folder>.mp4` → marca `uploaded`) +
  router `productos.py` (`/prompts`, `/productos`, `/extraer-textos`,
  `/foto-limpia`, `/video/upload`, `/producto/estado`, `/vendidos`).
  Frontend pendiente (otro agente en paralelo).
- [2026-05-18] Nicho 4 Construcción POV completo: JobMode + runner + pipeline (Gemini video → MiniMax → anti-copy + subs karaoke) + endpoints `/construccion-pov/enqueue` y `/voices/clone|sample|delete` + sidebar nav + página `/creator-reward/construccion-pov` + hub `/creator-reward/tools/voices` + 40 presets EN MiniMax.

## 🔜 Reintento IA con feedback (<90) — DISEÑO APROBADO, pendiente implementar+validar
- Cuando un vídeo web sale <90 (audit `needs_requeue`), re-encolar máx **2** veces (3 totales).
- En cada reintento, inyectar en el prompt de GPT-4o (pass2 de `silence_cutter`) los fallos
  concretos del audit anterior (loose_words_preview, surviving_stretched_preview,
  internal_silences con contexto) → "estos rellenos/palabras quedaron sin cortar, córtalos".
- Quedarse con el MEJOR intento (mayor quality_score).
- Tocar: runners.run_editor_auto (re-enqueue guardado a jobs web), run.py (param retry_feedback
  → inyectar en config del step silence_cutter), silence_cutter (consumir retry_feedback en prompt),
  web_upload.web_output (best-of por source via retry_group), setting flag auto_retry (default OFF).
- VALIDAR con un clip real que dé <90 antes de activar el flag.

## ⏸️ Reintentos <90 — APARCADO (decisión)
- NO tocar el motor de silencios con reintentos por ahora.
- Mientras: <90 se gestiona MANUALMENTE (revisar/aprobar o avisar y mejorar a mano).
- Retomar solo con el "cambio grande" del motor, validándolo con un clip real <90.
