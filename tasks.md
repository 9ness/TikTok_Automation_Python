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

### Estados Unidos — APLAZADO (2026-07-29)
Los vídeos de gancho de EEUU **traen audio propio**, así que la metodología no
es la misma que en España: primero hay que extraer y separar ese audio. El
operador decide dejarlo para más adelante. Cuando se retome:
3. Mismos ganchos que en España, para cada persona (+ separar el audio).
4. **Además**, los clips de PAISAJE de EEUU: mismo proceso que se hizo con los
   de España (ver `VIRALIZACION_MODULE.md`) — trocear por cada plano/lugar
   distinto y descartar los que llevan texto o logos encima.

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
- **Dónde está el material.** Ni `~/viralizacion_assets/` ni
  `TIKTOK_SHOP_AI_PRO/` en Drive tienen nada de las personas nuevas ni de los
  paisajes de EEUU (solo `pablo`, `victor` y `paisajes` de España). Preguntar
  la ruta exacta.
- Cuántas personas hay en cada país y cómo se llaman.

## 🤖 Cola del Agente

- [Viralización] `renderer.py`: el dir `work/` de clips solo se borra en el
  camino feliz. Si ffmpeg falla, quedan ~220 MB (vídeo 39s) o ~500 MB (90s)
  huérfanos por vídeo fallido. Envolver en `try/finally`. Relevante: el disco
  del VPS va al 92%.
- [Viralización] `MAX_VIDEO_DURATION_S = 90` contradice el diseño (20-60s) y
  los docstrings ("~55s", "163s → 3 trozos"; con 90 salen 2). Hoy es inerte
  (todos los audios < 90s). Decidir: bajar a ~55-60 o corregir los docs.
- [Viralización] `is_valid_mp4(min_duration=MIN_VIDEO_DURATION_S*0.8)` = 16s
  fijo: un audio corto genera un MP4 correcto que se declara inválido y se
  borra. Debería medir contra `win_dur` esperado, no contra una constante.
- [Viralización] `VIRALIZACION_MODULE.md:85` y `:248` siguen documentando
  `gdrive:VIRALIZACION/...` (la ruta real ya es
  `NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/VIRALIZACION`).
- [Viralización] El "reanudar batch" (skip de MP4 ya válidos) es código muerto:
  `batch_id` lleva un uuid aleatorio, así que el staging nunca preexiste.
## ✅ Done

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
