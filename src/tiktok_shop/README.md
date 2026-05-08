# TikTok Shop Module

Programa 2 del proyecto. Genera vídeos AI multi-cuenta × producto para
publicación manual en TikTok Shop Seller Center con producto vinculado.

**Independiente del Programa 1 (Creator Reward).** No mezclar lógica entre
programas — solo se reusan módulos transversales (MiniMax `src/locutor.py`,
Whisper `src/subtitles.py`, JobQueue `src/queue/`).

Brief de producto: [TIKTOK_SHOP_MODULE.md](../../TIKTOK_SHOP_MODULE.md).

---

## Diagrama de flujo

```
                     ┌──────────────────────────────────────┐
                     │  UI Streamlit (src/tiktok_shop/ui/)  │
                     │  Tabs: Productos · Usuarios · Generar│
                     │        · Voces · Histórico           │
                     └────────────┬─────────────────────────┘
                                  │
                       enqueue ▼
                     ┌──────────────────────────────────────┐
                     │  JobQueue unificada (src/queue/)     │
                     │  JobMode.TIKTOK_SHOP → run_tiktok_shop│
                     └────────────┬─────────────────────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │  Branch por tier    │
                       └──┬──────────┬───────┘
            standard/adv  │          │  pro
                          ▼          ▼
                ┌──────────────┐ ┌──────────────┐
                │ analyzer →   │ │ analyzer →   │
                │ strategist → │ │ strategist → │
                │ i2v director │ │ pro director │
                │ (list 3)     │ │ (dict multi) │
                └──────┬───────┘ └──────┬───────┘
                       │                │
                       ▼                ▼
              ┌──────────────────────────────┐
              │ Atlas Cloud (POST gen+poll)  │
              │  base64 inline images        │
              └──────┬───────────────────────┘
                     │
                     ▼
                ┌──────────────────────────────┐
                │ MoviePy compose +            │
                │ Whisper captions karaoke +   │
                │ MP4 9:16 + metadata.json     │
                │ → TIKTOK_SHOP/_users/...     │
                └──────────────────────────────┘

   veo3_prompt_only:   analyzer → strategist → veo3_director → escribe .txt
   nano_banana:        nano_banana_prompt_generator → escribe .txt
                       UI: zip de fotos source + upload zone para fotos generadas
```

---

## Estructura de archivos

```
src/tiktok_shop/
├── config.py                  # VIDEO_MODELS, paths, helpers env
├── api/
│   ├── atlas_cloud.py         # cliente HTTP (i2v + ref2v + poll + download)
│   ├── gemini.py              # multimodal con retry on 429
│   └── minimax_clone.py       # voice_clone wrapper
├── pipeline/
│   ├── analyzer.py            # ficha de producto desde fotos
│   ├── strategist.py          # hook + script + estructura
│   ├── seedance_director.py   # branch i2v list / pro dict
│   ├── seedance_renderer.py   # asyncio.gather + anchoring
│   ├── veo3_director.py       # prompt-only (string)
│   ├── nano_banana_prompt_generator.py
│   ├── editor.py              # MoviePy concat + Whisper captions
│   └── drive_uploader.py      # copia local + metadata.json
├── prompts/                   # 6 .md editables
│   ├── product_analyst.md
│   ├── content_strategist.md
│   ├── seedance_image_to_video_director.md   # standard + advanced (DRY)
│   ├── seedance_pro_director.md
│   ├── veo3_director.md
│   └── nano_banana_director.md
├── models/                    # Pydantic v2
│   ├── tiktok_user.py
│   ├── product.py             # ProductPhotos {source, generated}
│   ├── video_generation.py    # estado, coste, tier_used
│   └── voice.py
├── repos/                     # CRUD Redis (prefix tiktok_shop:)
│   ├── redis_base.py
│   ├── user_repo.py
│   ├── product_repo.py        # auto-migración v1 → v2
│   ├── generation_repo.py     # con agregaciones de coste
│   └── voice_repo.py
├── services/
│   ├── cost_calculator.py     # tiers × resolución × voz
│   ├── pilot_tracker.py       # graduación 3 vías + reset semanal
│   └── tier_selector.py       # stub
├── utils/
│   ├── duration_splitter.py   # 5/10/12/15/20/24/25/30s → clips
│   ├── image_url_provider.py  # base64 inline (los 3 tiers)
│   ├── photo_quality.py       # PIL low-res + Gemini flag
│   ├── validators.py          # slug/username/url/foto
│   └── logging_setup.py       # rotación diaria
└── ui/
    ├── shop_router.py         # entry-point en main.py:1029
    ├── tab_products.py
    ├── tab_users.py
    ├── tab_generator.py
    ├── tab_voices.py
    └── tab_history.py
```

---

## Cómo añadir un tier nuevo

1. **Editar `src/tiktok_shop/config.py:VIDEO_MODELS`** — añadir entrada con
   shape:
   ```python
   "mi_tier": {
       "name": "...",
       "model_id": "vendor/model/endpoint",
       "type": "image_to_video" | "reference_to_video" | "prompt_only",
       "supports_multi_ref": bool,
       "max_input_images": int,
       "cost_per_second": float,
       "max_duration": int,
       "max_resolution": str,
       "strategy": "multi_clip_anchor" | "single_shot_multishot" | "manual_paste_in_gemini_chat",
       "use_case": "...",
       "tier_color": "🟦",  # emoji para UI
   }
   ```
2. Si es Atlas:
   - Si `image_to_video` → ya funciona con `submit_image_to_video()` existente.
   - Si `reference_to_video` → idem con `submit_reference_to_video()`.
   - Si requiere shape distinto → añadir método nuevo en `api/atlas_cloud.py`
     y branch en `pipeline/seedance_renderer.py:render_seedance_clips()`.
3. Si es prompt-only:
   - Crear `pipeline/<tier>_prompt_generator.py` análogo a `veo3_director.py`.
   - Crear `prompts/<tier>_director.md`.
   - Añadir branch en `src/queue/runners.py:run_tiktok_shop` (busca el
     comentario `Branch B: Veo3 prompt-only` y replica el patrón).
4. Actualizar UI:
   - `tab_generator.py:_TIER_TOOLTIPS` — añadir tooltip.
   - El radio de tiers se autoreplica de `VIDEO_MODELS.keys()`.
5. Tests:
   - Añadir caso en `tests/tiktok_shop/test_cost_calculator.py`.
   - Añadir mock fake en `tests/tiktok_shop/mocks/mock_gemini.py`.

---

## Cómo añadir un proveedor de vídeo alternativo (no Atlas)

Si se quiere dual-provider (ej. Atlas + Replicate como fallback):

1. Crear `api/<provider>_client.py` con la **misma interfaz** que
   `AtlasCloudClient`:
   - `is_available()`
   - `submit_image_to_video(...)` con kwargs name-compatible
   - `submit_reference_to_video(...)` (si aplica)
   - `poll(job_id) -> Job(status, output_url, error)`
   - `wait(job_id) -> Job`
   - `download(url, dest_path) -> str`
2. En `pipeline/seedance_renderer.py:render_seedance_clips()` añadir el
   selector de cliente según una env var (`TIKTOK_SHOP_VIDEO_PROVIDER=atlas|replicate`).
3. Verificar firmas con `inspect.signature` (ver
   `tests/tiktok_shop/test_mocks.py:test_drop_in_compatibility` como
   referencia — replica esa validación para el nuevo provider).
4. Mantener el shape `AtlasJob` (job_id, status, output_url, error) como
   contrato común — no exponer internals del proveedor en el pipeline.

---

## Troubleshooting común

### "Modo desconocido: JobMode.TIKTOK_SHOP"
El `JobQueue` está cacheado por `@st.cache_resource` con un dispatcher viejo.
Ya está mitigado en `src/queue/manager.py:get_queue()` (re-set_dispatcher en
cada llamada) — pero si aparece, **reinicia `streamlit run main.py`** para
forzar recreación del singleton.

### Atlas devuelve `400 {"code":400,"msg":"not found"}`
El `model_id` del tier en `VIDEO_MODELS` no coincide con la doc de Atlas.
Verifica que la string sea EXACTA. Casos conocidos:
- ✅ `bytedance/seedance-v1.5-pro/image-to-video-fast` (sufijo `-fast` al final)
- ❌ `bytedance/seedance-v1.5-pro-fast/image-to-video` (sufijo en medio — incorrecto)

### `429 Quota exceeded` en Gemini
Gemini `gemini-2.5-flash` (modelo por defecto del módulo) en free tier tiene
20 req/día. El módulo usa **dual-key fallback**: define `GOOGLE_GEMINI_KEY_FREE`
y `GOOGLE_GEMINI_KEY_PAID` en `.env` y al llegar 429 en FREE saltará
automáticamente a PAID. Si aún se agota tras dos keys:
- Esperar al reset diario.
- O aumentar `max_retries_on_quota` en `api/gemini.py:generate_text()`.

**Si el error 429 menciona `gemini-2.0-flash` tras un cambio reciente**:
Streamlit cachea módulos importados — reinicia `streamlit run main.py` para
recoger el nuevo `DEFAULT_MODEL` del `.py`. El log
`tiktok_shop.gemini | Gemini call | model=...` permite verificar el modelo
real que se está enviando a la API en cada llamada.

### Atlas job timeout pero el job sigue procesándose
`POLL_TIMEOUT_S` en `api/atlas_cloud.py` está en 900s (15 min). En horas
pico Atlas puede tardar más. Si el job acaba completed después del timeout,
el coste SE COBRA pero el cliente no descarga el output. Solución: pollear
el job_id manualmente con `AtlasCloudClient().poll("0ac4...")` y descargar
con `client.download(output_url, dest_path)`.

### Photos source con `TIKTOK_CR/TIKTOK_SHOP/...` en Redis (legacy)
Tras mover la carpeta `TIKTOK_SHOP/` fuera de `TIKTOK_CR/` (mayo 2026), los
paths en Redis pueden tener la ruta vieja. Usar el helper de migración (no
está commiteado — ver historial git de `_migrate_paths.py` si se necesita).

### "FileNotFoundError: photos_source\xxx.jpg" durante test
La sincronización Drive Desktop puede no haber bajado las fotos al PC. El
módulo lee desde el filesystem local (sincronizado), no Drive API. Verifica
que el archivo existe físicamente en disco antes de encolar.

### Vídeo final sin audio
- MiniMax devolvió error → revisa logs `tiktok_shop.runner` (busca línea
  con `MiniMax` y `error_type=`).
- O Whisper falló al transcribir el MP3 → el vídeo se compone sin captions
  pero CON la voz. Si tampoco hay voz: error en MiniMax o `voice_id` inválido.

---

## Tests

```bash
# Suite completa del módulo
python -m pytest tests/tiktok_shop/ -v

# Solo un componente
python -m pytest tests/tiktok_shop/test_cost_calculator.py -v

# E2E mockeado (sin gastar)
python -m pytest tests/tiktok_shop/test_mocks.py -v
```

Los tests usan `FakeRedis` in-memory + mocks de Atlas/Gemini/MiniMax. Ningún
test toca APIs reales — coste de la suite: $0.

Para añadir tests E2E reales (gastan dinero), crea un script ad-hoc en la
raíz del repo (ej. `_e2e_real.py`) que invoque el runner con un Job mock —
ver patrón en historial git de `_e2e_standard.py`.
