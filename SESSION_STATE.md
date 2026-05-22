# Estado de sesión — Refactor TikTok Shop (mayo 2026)

> Documento de handoff post-compact. Contiene el estado exacto del refactor
> mayor del módulo TikTok Shop que añade producto-flow completo, sistema de
> presets generados por IA, A/B testing inteligente, async generation con
> progress, y fix del webhook listener.

## 🎯 Big picture — qué se construyó

Refactor del módulo `src/tiktok_shop/` para pasar de "configurar cada
vídeo a mano" a un flujo end-to-end:

1. **Crear producto desde URL TikTok Shop** → scraper + Gemini autorrellena
2. **Fotos por URL/búsqueda DDG + Gemini Vision** las puntúa 0-10 y compara
   con referencia para descartar productos distintos / duplicados
3. **Análisis Gemini Vision** → audiencia, key features, selling points,
   warnings explicativos
4. **Presets de vídeo precocinados** (música 8-10 + scripted 10-15 por ángulo)
   con prompts seedance+veo3 listos para los 4 tiers
5. **Variantes A/B inteligentes** — Gemini crea N variantes con hipótesis
   distintas (color, hook, CTA, ángulo, etc.)
6. **Generación masiva** desde /generate — selecciona presets + N variantes
   por preset → encola todo

## 📂 Archivos clave creados/modificados

### Backend nuevos
- `src/tiktok_shop/models/video_preset.py` — modelo VideoPreset con
  TextOverlayStyle, SubtitleStyle, CtaArrowStyle anidados
- `src/tiktok_shop/pipeline/preset_generator.py` — Gemini call por kind +
  sanitizers (shot_style, tiers, overlay, subtitle, arrow)
- `src/tiktok_shop/pipeline/variants_generator.py` — Gemini call para
  micro-variantes A/B desde un preset base
- `src/tiktok_shop/pipeline/photo_grader.py` — Gemini Vision scoring 0-10
- `src/tiktok_shop/utils/url_scraper.py` — sigue redirects `vm.tiktok.com`,
  parsea `og_info` JSON-encoded de los share-URLs
- `src/tiktok_shop/utils/photo_downloader.py` — descarga og:image y la
  guarda como packshot del producto
- `src/tiktok_shop/utils/image_search.py` — DDG (sin API key) + Google CSE
  opcional con env vars
- `src/tiktok_shop/services/preset_gen_tracker.py` — Redis-backed progress
  tracker (`preset_gen:{gen_id}` con stage/percent)
- `src/tiktok_shop/prompts/music_bof_director.md` — JSON output prompt
- `src/tiktok_shop/prompts/scripted_bof_director.md` — JSON output prompt
- `src/tiktok_shop/prompts/photo_grader.md`
- `src/tiktok_shop/prompts/ab_variants_director.md`
- `deploy/tiktok-webhook-healthcheck.service` + `.timer` — watchdog

### Backend modificados
- `src/api/routers/products.py` — endpoints async para generate-presets
  (BackgroundTasks), variants, photo import, url preview. **DELETE
  producto borra carpeta Drive recursivamente (best-effort).**
- `src/api/schemas/product.py` — Pydantic schemas para todo lo anterior
- `src/tiktok_shop/api/gemini.py` — cost tracking automático en
  `_call_with_key` extrayendo `usage_metadata`
- `src/tiktok_shop/models/product.py` — añadidos `video_presets`,
  `photos_quality_assessment`, `last_analysis_warnings`
- `src/tiktok_shop/utils/validators.py` — `TIKTOK_SHOP_URL_PATTERN`
  acepta cualquier subdominio (`vm.`, `vt.`, `shop-xx.`)
- `deploy/webhook_listener.py` — `HTTPServer` → `ThreadingHTTPServer`
  (fix raíz del hang crónico)

### Frontend nuevos
- `frontend/components/products/PresetsManager.tsx` — tab Presets con
  filtros, generación async con progress bar persistente, editor inline
- `frontend/components/products/PhotoImportFromUrls.tsx` — DDG search +
  pega URLs + grid scored
- `frontend/components/products/TabHint.tsx` — banner colores por modo
- `frontend/components/generate/shop/VideoPresetsPicker.tsx` — picker en
  AutoVideoCard filtrado por tier
- `frontend/components/generate/shop/BulkGenerateDialog.tsx` — generación
  masiva con toggle "Smart variants" + chips de dimensiones

### Frontend modificados
- `frontend/lib/types/product.ts` — VideoPreset, SubtitleStyle,
  CtaArrowStyle, TextOverlayStyle, PresetGenStatus, etc.
- `frontend/lib/queries/products.ts` — useGeneratePresets (async),
  usePresetGenStatus (polling 2s), useGenerateVariants, etc.
- `frontend/lib/api.ts` — añadido `api.patch`
- `frontend/components/products/ProductCard.tsx` — botón borrar con
  AlertDialog estilizado
- `frontend/components/products/ProductCreateDialog.tsx` — flujo completo
  URL → Analizar → autorrelleno + auto-download foto
- `frontend/components/products/ProductEditorTabs.tsx` — tabs reemplazados
  por **tarjetas coloreadas** (5 tabs: Identidad/Fotos/Análisis/Audiencia/
  Presets), Config técnica + Voz + Hooks **ocultos** (movidos a preset)
- `frontend/components/generate/shop/AutoVideoCard.tsx` — selector tier
  arriba siempre visible + VideoPresetsPicker + botón generación masiva
- `frontend/app/settings/page.tsx` — Deploy arriba, API colapsada

## 🏗️ Arquitectura — decisiones clave

### Preset generation flow (async)
```
POST /products/{id}/video-presets/generate
  ↓ devuelve { gen_id, stage: "started" } INMEDIATO
  ↓ BackgroundTask corre _generate_presets_background
  ↓ Actualiza Redis: preset_gen:{gen_id} con stage/percent
Frontend persiste gen_id en localStorage `preset-gen:{product_id}`
Frontend poll cada 2s: GET /products/{id}/preset-gen-status/{gen_id}
Cuando stage=done → invalida product detail + limpia localStorage
```
Refresh navegador en medio → al recargar lee gen_id de localStorage y
retoma polling. La generación sigue corriendo en el server.

### Shot style rules (single vs multi-shot)
```
Reglas DURAS (failsafes — limitaciones del modelo):
  duration_s < 8     → single_shot forzado (Seedance mín clip = 4s)
  style=creator_pov  → single_shot forzado (lip-sync requiere continuidad)
  only veo3 compat   → single_shot forzado (Veo 3 nativo 10s)

A partir de 8s, Gemini decide libre.
"auto" sugiere single+cinematic ≤10s, multi+dynamic >10s.
8-10s permite multi si Gemini propone strategy=dynamic.
```

### Tier compatibility
```
voiceover style    → standard, advanced, pro, veo3_prompt_only
creator_pov style  → pro, veo3_prompt_only (Standard/Advanced no lip-sync)
duration > 10s     → quita veo3_prompt_only (Veo 3 cap nativo)
```

### Precio en hooks (anti-spam comercial)
Backend calcula `_hook_price_suggestion(product)` = `real_price * 0.70`
redondeado a barrera psicológica (5/10/50). 29.95€ → 20€. Se pasa a
Gemini en el user prompt como `Precio para hooks: 20€`. Las hooks de
ahorro/comparativa lo usan en lugar del real (justificado por cupones).

### Watchdog webhook
- `tiktok-webhook-healthcheck.timer` → cada 2 min `curl /health` con
  timeout 5s. Si falla → `systemctl restart tiktok-webhook`.
- Causa raíz arreglada: `ThreadingHTTPServer` en vez de `HTTPServer`
  single-threaded (cualquier conexión lenta colgaba todo).

### Tab cards en producto
```
🔵 azul = auto + editable (Identidad, Fotos)
🟢 verde = auto-generado (Análisis, Audiencia, Presets)
⚫ gris = manual (no quedan tabs manuales tras el refactor)
```
Mobile: grid 2-col. Desktop: 5-col.

## 🚦 Estado actual de despliegue

**Local (D:\Proyectos_Personales\TikTok_Automation_Python):**
- Backend uvicorn en :8000 ✅
- Frontend Next.js en :3000 ✅
- Todo el código del refactor presente
- Último commit local: el del fix webhook (`857e7db`)

**Producción VPS (62.238.19.31):**
- Commit desplegado: `857e7db fix(webhook): ThreadingHTTPServer + watchdog`
- Containers: tiktok-api + tiktok-web rebuildados con `f7a5e6f`
- ⚠️ **Pendiente desplegar:** los últimos commits del session (timestamps en
  preset cards + async progress generation). Hay que pushear el commit
  pendiente (la generación async + UI progress no está commiteada todavía).

## 🔧 Permisos añadidos en `.claude/settings.local.json`
- `Bash(git push:*)` — push autorizado
- `Bash(ssh*root@62.238.19.31*)` — SSH deploy autorizado
- `Bash(ssh*nebulabsai@62.238.19.31*)` — SSH user app
- `Bash(scp*62.238.19.31*)` — copia archivos VPS

## ⏳ Estado verificable AHORA (al recoger la sesión)

1. ✅ Permisos VPS funcionando — puedo SSH y deploy automático
2. ✅ Webhook watchdog activo en VPS — `systemctl status
   tiktok-webhook-healthcheck.timer` debe decir active(waiting)
3. ⚠️ **Commits LOCALES sin pushear** que añaden:
   - Timestamp en cada PresetCard ("hoy 14:23")
   - Generación async con progress bar persistente
   - Tracker Redis `preset_gen:{id}`
   - Endpoint `GET /products/{id}/preset-gen-status/{gen_id}`
4. ⚠️ **Usuario quería probar en local** la generación async antes de
   pushear. El comando para verificar local:
   ```powershell
   .\venv\Scripts\python.exe -c "from src.api.main import app; print('OK')"
   ```

## 🔜 Próximos pasos (orden sugerido al retomar)

1. **Probar en local**: el usuario quería ver la barra de progreso
   funcionando antes de commitear:
   - `/tiktok-shop/products/<id>` → tab Presets
   - Click "Regenerar todos"
   - Debería ver:
     - Toast "Generación iniciada · puedes cambiar de tab sin perder progreso"
     - Barra de progreso con stage actual + percent + N/M presets
     - Cambiar a otra tab y volver → barra sigue visible
     - Hard refresh navegador → barra recupera estado
     - Al final: toast "X presets generados" + lista refrescada

2. **Si todo OK en local**: commit + push:
   ```
   feat(tiktok-shop): preset generation async con progress persistente
   ```
   Incluye:
   - `src/tiktok_shop/services/preset_gen_tracker.py` (nuevo)
   - `src/api/routers/products.py` (refactor endpoint a BackgroundTasks)
   - `src/api/schemas/product.py` (PresetGenStatusResponse)
   - `frontend/lib/types/product.ts` (PresetGenStatus type)
   - `frontend/lib/queries/products.ts` (usePresetGenStatus polling)
   - `frontend/components/products/PresetsManager.tsx` (UI progress + LS)

3. **Tras push**: SSH al VPS, lanzar `sudo -u nebulabsai bash
   /home/nebulabsai/TikTok_Automation_Python/deploy/deploy_safe.sh`.
   Verificar que las imágenes docker rebuildean OK con disk space.

4. **Cosas que el usuario aún no probó del refactor**:
   - Generar variantes A/B (toggle Smart variants en bulk dialog)
   - Aplicar un preset desde `/generate` → encolar vídeo real → ver si
     el cta_arrow renderiza la flecha correctamente con el sticker.mov
   - Comprobar que los presets `creator_pov` SOLO aparecen en tier Pro/Veo3

## 📋 Convenciones del proyecto a respetar

- **No push automático** sin pedirlo el user (memoria de usuario)
- **Caveman mode** activo en CLAUDE.md → 1-2 líneas máx, cero cortesías
- **Cost tracking obligatorio** para toda API externa → ya wraped en
  preset_generator + variants_generator con start_job/finalize
- **Mobile-first siempre** → toda UI nueva debe verse bien en móvil
- **Aislamiento entre programas** — no mezclar lógica Creator Reward
  y TikTok Shop. Solo módulos transversales (locutor, cost_tracking,
  queue, fonts, subtitles).
- **System prompts en archivos `.md`** — todos los prompts de TikTok
  Shop viven en `src/tiktok_shop/prompts/*.md`, nunca hardcoded
