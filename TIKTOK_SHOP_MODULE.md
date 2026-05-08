# TikTok Shop Module — Brief para implementación (v2)

## Contexto del proyecto

Estoy ampliando una aplicación existente llamada **TikTok_Automation_Python** que ya tiene una sección funcional llamada **Creator Reward** (con sus 3 nichos: Presidentes Top 5, Pronósticos Diarios, Quitar Copy).

Ahora estoy construyendo una **NUEVA sección llamada "TikTok Shop"** completamente independiente. La sección Creator Reward NO debe ser modificada — solo añadimos TikTok Shop al lado.

El selector ya existe en el sidebar:
- ⚙️ Creator Reward (existente, no tocar)
- 🛒 TikTok Shop (nuevo módulo)

## Objetivo de TikTok Shop

Soy **afiliado de TikTok Shop España**. Promociono productos de otros vendedores y gano comisión. Necesito generar videos automatizados con AI para subir a múltiples cuentas de TikTok afiliadas.

**Mi flujo de trabajo objetivo:**
1. Crear "Usuarios TikTok" (cuentas afiliadas que gestiono)
2. Crear "Productos" (catálogo de productos a promocionar)
3. Asignar productos a usuarios TikTok
4. Generar videos para combinaciones usuario+producto
5. Los videos van a Google Drive organizados
6. Subo manualmente a TikTok Shop Seller Center con producto vinculado

## Contexto de mi situación actual

- Ya genero videos con Veo 3 (Gemini chat) → 22€/mes, 8 ventas hechas
- Quiero escalar manteniendo calidad pero bajando coste por video
- Plan: empezar con 2-3 videos/día → escalar a 30/día en 4 cuentas
- Estoy en TikTok Shop Affiliate **Pilot Program** (límite 5 shoppable videos/semana hasta graduación)
- Para graduar: 30 días + 6 vids shoppable + quiz aprobado + CHR≥176

**Importante**: muchos productos NO los tengo físicamente. Las fotos vendrán de:
1. Internet (Amazon, web fabricante, TikTok Shop)
2. **Fotos generadas con Nano Banana 2** (Google Gemini Pro, manual) — flujo principal
3. Fotos propias si tengo el producto

---

## ARQUITECTURA TÉCNICA

### Stack de APIs

```
.env (variables nuevas para añadir):

ATLAS_CLOUD_API_KEY=...                     # Video AI (3 tiers Seedance, ya añadida)
GOOGLE_DRIVE_TIKTOK_SHOP_FOLDER_ID=...      # ID carpeta raíz Drive TIKTOK_SHOP

# Gemini multimodal — DUAL-KEY con fallback automático para TikTok Shop:
GOOGLE_GEMINI_KEY_FREE=...                  # proyecto sin billing (free tier 20 req/día con 2.5-flash). Se intenta primero.
GOOGLE_GEMINI_KEY_PAID=...                  # proyecto con billing (~5€/mes). Solo se usa si FREE → 429.

# Reusar variables ya existentes en el proyecto:
MINIMAX_API_KEY (ya existe)                 # TTS + voice cloning
MINIMAX_GROUP_ID (ya existe)                # Group ID Minimax
GOOGLE_GEMINI_KEY (ya existe)               # Legacy de Creator Reward — TikTok Shop NO la toca
                                            #   (solo cae a ella si no defines FREE/PAID — desaconsejado)
UPSTASH_REDIS_REST_URL (ya existe)          # Redis con prefijo tiktok_shop:
UPSTASH_REDIS_REST_TOKEN (ya existe)
```

**Comportamiento dual-key (`src/tiktok_shop/api/gemini.py`):**
- Llama con FREE primero. Si 429 (RESOURCE_EXHAUSTED), switch inmediato a PAID.
- Si solo una de las dos está definida, usa esa con retry on quota interno.
- Si ambas devuelven 429, propaga el error del último intento (PAID).
- Errores no-quota (auth, mal request) propagan inmediatamente sin probar otras keys.

**Importante**: NO se necesita API key separada para Nano Banana 2 ni para Veo 3. Ambos se usan manualmente desde Gemini chat (que el usuario tiene en plan Pro). La app solo genera el prompt optimizado para copiar/pegar.

### Modelos de generación de video — 3 TIERS + 2 PROMPT-ONLY

Todos los modelos van a través de Atlas Cloud (misma API key). Solo cambia el `model_id` y el comportamiento.

```python
VIDEO_MODELS = {
    "standard": {
        "name": "Seedance v1.5 Pro Fast",
        "model_id": "bytedance/seedance-v1.5-pro-fast/image-to-video",
        "type": "image_to_video",
        "supports_multi_ref": False,
        "max_input_images": 1,
        "cost_per_second": 0.018,
        "max_duration": 15,
        "max_resolution": "1080p",
        "strategy": "multi_clip_anchor",
        "use_case": "Volumen diario, validación, testing hooks",
        "tier_color": "🟢"
    },
    "advanced": {
        "name": "Seedance v1.5 Pro",
        "model_id": "bytedance/seedance-v1.5-pro/image-to-video",
        "type": "image_to_video",
        "supports_multi_ref": False,
        "max_input_images": 1,
        "cost_per_second": 0.047,
        "max_duration": 15,
        "max_resolution": "1080p",
        "strategy": "multi_clip_anchor",
        "use_case": "Productos prometedores, A/B testing",
        "tier_color": "🟡"
    },
    "pro": {
        "name": "Seedance 2.0 Fast Reference",
        "model_id": "bytedance/seedance-2.0-fast/reference-to-video",
        "type": "reference_to_video",
        "supports_multi_ref": True,
        "max_input_images": 9,
        "max_input_videos": 3,
        "max_input_audios": 3,
        "cost_per_second": 0.072,
        "max_duration": 15,
        "max_resolution": "1080p",
        "strategy": "single_shot_multishot",
        "use_case": "Productos ganadores, hero ads, packaging complejo",
        "tier_color": "🔴"
    },
    "veo3_prompt_only": {
        "name": "Veo 3 (solo prompt)",
        "model_id": None,
        "type": "prompt_only",
        "supports_multi_ref": True,
        "max_input_images": 5,
        "cost_per_second": 0,
        "max_duration": 8,
        "strategy": "manual_paste_in_gemini_chat",
        "use_case": "Premium puntual manual",
        "tier_color": "🟣"
    },
    "nano_banana_prompt_only": {
        "name": "Nano Banana 2 (solo prompt para fotos)",
        "model_id": None,
        "type": "prompt_only",
        "purpose": "image_generation",
        "use_case": "Generar fotos premium del producto desde 1-2 fotos pobres",
        "tier_color": "🍌"
    }
}
```

### Estrategias de generación por tier

#### `multi_clip_anchor` (Standard y Advanced)

```
Input: 3-5 fotos del producto + 3 prompts generados por Gemini

Para video de 15s:
- Clip 1 (5s): start_frame = foto_1, end_frame = foto_2
- Clip 2 (5s): start_frame = foto_2, end_frame = foto_3
- Clip 3 (5s): start_frame = foto_3, end_frame = libre

Cada clip se genera en paralelo (asyncio.gather).
First/last frame anchoring asegura continuidad entre clips.
FFmpeg concatena los 3 clips en post (sin crossfade).
```

#### `single_shot_multishot` (Pro)

```
Input: hasta 9 fotos del producto + 1 prompt único multi-shot

Para video de 15s:
- 1 único clip de 15s con multi-shot interno:
  "Shot 1 (0-5s): [push-in producto]
   Shot 2 (5-10s): [orbit close-up]
   Shot 3 (10-15s): [macro detail]
   Smooth transitions between shots."

Reference-to-Video acepta múltiples fotos como referencia.
NO se concatena en FFmpeg, viene un solo clip ya editado.
```

#### `manual_paste_in_gemini_chat` (Veo 3)

```
La app genera el prompt optimizado para Veo 3 (8s fijos).
NO renderiza video.
Output en UI:
- Prompt copiable
- Lista de fotos input descargables (botón "Descargar todas")
- Instrucciones de uso

Usuario pega manualmente en Gemini chat con las fotos.
Cuando tiene el video, lo sube manualmente al campo "URL Drive".
La app actualiza Redis con status="manual_completed".
```

#### Workflow Nano Banana 2 (generación de fotos)

```
La app genera prompt optimizado para Nano Banana 2.
NO genera fotos automáticamente.
Output en UI:
- Prompt copiable
- Fotos source descargables
- Instrucciones: "Pega este prompt en Gemini chat con modelo Nano Banana 2 + las fotos"
- Upload zone: "Sube aquí las 4-8 fotos generadas cuando las tengas"

Cuando user sube fotos: guardar en photos_generated/ del producto.
Esas fotos se usan en pipelines Standard/Advanced/Pro a partir de ese momento.
```

---

## ESTRUCTURA DE GOOGLE DRIVE

```
TIKTOK_SHOP/                          (carpeta raíz, ya existe)
│
├── _users/                            (cuentas TikTok)
│   └── @cuenta_skincare_es/
│       ├── _profile.json
│       └── products/
│           └── primal_pump_creatina/
│               └── videos/
│                   ├── 2026-05-07_curiosity_v1.mp4
│                   └── 2026-05-07_curiosity_v1.json
│
└── _products/                         (catálogo maestro)
    └── primal_pump_creatina/
        ├── _product.json
        ├── photos_source/             (fotos originales: internet/propias)
        │   ├── 01_amazon.jpg
        │   └── 02_web_fabricante.jpg
        ├── photos_generated/          (fotos premium Nano Banana 2)
        │   ├── 01_packshot.jpg
        │   ├── 02_lifestyle.jpg
        │   ├── 03_macro.jpg
        │   ├── 04_in_hand.jpg
        │   └── 05_detail.jpg
        └── prompt_templates/
            ├── nano_banana_prompt.txt (prompt usado para generar fotos)
            └── seedance_hooks.json
```

**Justificación**: separar `photos_source` y `photos_generated` permite que los pipelines Standard/Advanced/Pro consuman siempre las premium. Si no hay generadas, fallback a source.

---

## MODELO DE DATOS

### Persistencia: Redis con prefijo `tiktok_shop:`

#### TikTok User

```python
{
    "id": "uuid-v4",
    "username": "@cuenta_skincare_es",
    "display_name": "Skincare Tips España",
    "niche": "skincare",
    "language": "es",
    "country": "ES",
    "status": "pilot" | "graduated",
    "followers_count": 0,
    "creator_health_rating": 200,
    "pilot_program": {
        "started_at": "2026-05-07",
        "shoppable_videos_published": 0,
        "orders_generated": 0,
        "quiz_passed": false,
        "graduation_eligible": false,
        "weekly_shoppable_remaining": 5,
        "weekly_shoppable_reset_at": "2026-05-13"
    },
    "drive_folder_id": "...",
    "assigned_products": ["product_id_1"],
    "default_voice_id": "minimax_voice_xxx",
    "default_language": "es",
    "default_video_tier": "standard",
    "created_at": "...",
    "updated_at": "..."
}
```

#### Product

```python
{
    "id": "uuid-v4",
    "slug": "primal_pump_creatina",
    "name": "Primal Pump - Gominolas Creatina",
    "brand": "Primal Pump",
    "category": "fitness_supplements",
    "subcategory": "creatine",
    "target_audience": ["..."],
    "key_features": ["..."],
    "selling_points": ["..."],
    "tiktok_shop": {
        "product_url": "...",
        "product_id": "...",
        "commission_rate": 0.15,
        "price_eur": 29.99
    },
    "photos": {
        "source": [
            {
                "drive_file_id": "...",
                "filename": "01_amazon.jpg",
                "origin": "internet" | "own" | "tiktok_shop_url",
                "url_origin": "https://...",
                "added_at": "..."
            }
        ],
        "generated": [
            {
                "drive_file_id": "...",
                "filename": "01_packshot.jpg",
                "type": "packshot" | "lifestyle" | "detail" | "in_use" | "macro",
                "generation_prompt_used": "...",
                "generated_at": "..."
            }
        ]
    },
    "video_config": {
        "default_tier": "standard",
        "default_duration": 15,
        "default_resolution": "720p",
        "preferred_styles": ["asmr", "lifestyle", "ugc"],
        "voice_preference": {...},
        "has_complex_packaging": false,
        "use_first_frame_anchor": true
    },
    "performance_history": {
        "total_videos_generated": 0,
        "total_orders_generated": 0,
        "best_hook_category": null,
        "promoted_to_advanced_at": null,
        "promoted_to_pro_at": null
    },
    "hooks_library": [...],
    "drive_folder_id": "...",
    "created_at": "...",
    "updated_at": "..."
}
```

#### Video Generation

```python
{
    "id": "uuid-v4",
    "user_id": "tiktok_user_uuid",
    "product_id": "product_uuid",
    "tier_used": "standard" | "advanced" | "pro" | "veo3_prompt_only",
    "model_used": "bytedance/seedance-v1.5-pro-fast/image-to-video",
    "duration_seconds": 15,
    "resolution": "720p",
    "num_clips": 3,
    "clip_strategy": "multi_clip_anchor" | "single_shot_multishot",
    "language": "es",
    "voice_used": {...},
    "hook": {...},
    "voiceover_script": "...",
    "captions_srt": "...",
    "video_prompts": [...],
    "photos_used": ["drive_id_1", "drive_id_2"],
    "photos_source": "generated" | "source",
    "generation_status": "pending" | "generating" | "completed" | "failed" | "manual_pending",
    "video_type": "shoppable" | "normal",
    "ai_disclosure": true,
    "cost": {
        "video_generation": 0.27,
        "voice_tts": 0.012,
        "total": 0.282
    },
    "drive_file_id": "...",
    "drive_url": "...",
    "metadata_json_drive_id": "...",
    "tiktok_shop_metadata": {
        "caption_template": "...",
        "hashtags": [...],
        "suggested_post_time": "...",
        "human_presence": true
    },
    "performance": {
        "published_at": null,
        "views": null,
        "likes": null,
        "shares": null,
        "orders_generated": 0
    },
    "created_at": "...",
    "completed_at": "..."
}
```

#### Voice Clone Library

```python
{
    "id": "uuid-v4",
    "name": "Mi voz energética ES",
    "minimax_voice_id": "voice_xxx",
    "language": "es",
    "tags": ["energetic", "male", "young"],
    "sample_drive_id": "...",
    "created_at": "..."
}
```

---

## FUNCIONALIDADES A IMPLEMENTAR

### 1. Página: Gestión de Usuarios TikTok

**Ruta**: `/tiktok-shop/users`

- Crear usuario nuevo (formulario completo con tier default)
- Auto-crear estructura Drive
- Listar usuarios con cards (estado Pilot/Graduado, progreso, productos asignados)
- Vista detalle (info expandida + lista productos + histórico videos)

### 2. Página: Catálogo de Productos

**Ruta**: `/tiktok-shop/products`

Wizard creación multi-paso:

**Paso 1: Origen del producto**
- Subir fotos source (1-5)
- O pegar URL TikTok Shop
- O ambas

**Paso 2: Análisis Gemini**
- Si subió fotos: Gemini Vision analiza
- Si subió URL: scraping básico
- Output editable + flag automático `has_complex_packaging` y `needs_nano_banana_regeneration`

**Paso 3: Configuración del producto**
- Nombre, marca, slug, precio, comisión, URL TikTok Shop, product_id

**Paso 4: Audiencia objetivo**
- Gemini sugiere 5 audiencias, multi-select

**Paso 5: Estilo y tono**
- Estilos visuales preferidos
- Voz preferida

**Paso 6: Hooks/Ganchos**
- Gemini genera 8 hooks, multi-select

**Paso 7: ⭐ Generación de fotos premium con Nano Banana 2 (CRÍTICO)**

Esta es la parte clave del wizard. Si las fotos source son de baja calidad, generamos premium:

- Detectar automáticamente si las fotos source son pobres (resolución <1024 o flag manual)
- Mostrar bloque: "Las fotos del producto pueden mejorarse con Nano Banana 2"
- Botón **"Generar prompt para Nano Banana 2"**:
  - Gemini analiza fotos source con system prompt `nano_banana_director.md`
  - Produce prompt optimizado
- UI muestra:
  - 📋 Prompt copiable (botón "Copiar al portapapeles")
  - 📥 Fotos source descargables (botón "Descargar todas en zip")
  - 📖 Instrucciones paso a paso:
    1. Abre Gemini chat con modelo Nano Banana 2
    2. Sube las fotos descargadas
    3. Pega el prompt
    4. Guarda las 4-8 imágenes generadas
  - 📤 Upload zone: "Sube aquí las fotos generadas cuando las tengas"
- Cuando suba: guardar en `photos_generated/` y mostrar preview
- Opción **"Saltar este paso"** si prefiere hacerlo a mano más tarde o tiene fotos buenas

**Paso 8: Confirmación**
- Resumen completo
- Auto-crear estructura Drive
- Guardar en Redis

Listar productos con cards. Editar producto.

### 3. Página: Generador de Videos

**Ruta**: `/tiktok-shop/users/[user_id]/products/[product_id]/generate`

Wizard:

**Paso 1: Confirmación contexto**
- Usuario y producto pre-seleccionados
- Mostrar fotos disponibles (separadas: source vs generated)
- Por defecto se usan `photos_generated`. Si no hay, fallback a `photos_source`.
- Permitir override manual

**Paso 2: Tipo de generación**
- 🟢 Standard automático ($0.27/15s) — Seedance v1.5 Fast
- 🟡 Advanced automático ($0.71/15s) — Seedance v1.5 Pro
- 🔴 Pro automático ($1.08/15s) — Seedance 2.0 Reference
- 🟣 Solo prompt para Veo 3 (manual, 8s, $0)
- "Generar todos para comparar" (opcional, suma costes)

**Paso 3: Configuración técnica**
- Si tier Standard/Advanced/Pro:
  - Duración: 5/10/15s
  - Resolución: 720p (default) / 1080p
  - Audio AI nativo: ON/OFF (default OFF, Minimax después)
- Si tier Veo 3:
  - Duración fija 8s
  - Estilo objetivo (cinematic / UGC / ASMR / lifestyle)

**Paso 4: Hook + Audiencia**
- Hook (dropdown del producto + custom)
- Audiencia objetivo

**Paso 5: Voz**
- Voz a usar (dropdown Voice Library)
- Idioma
- Tono

**Paso 6: Generación múltiple**
- Cuántas variantes generar (1-5)

**Paso 7: Resumen + Coste**
- Calcula coste estimado
- Botón "Generar"

### 4. Pipeline de generación (backend)

#### Pipeline Standard / Advanced (multi_clip_anchor)

```
1. Cargar fotos producto desde Drive (photos_generated preferred)
2. Gemini con content_strategist + seedance_standard_director (o advanced)
   → JSON con 3 video_prompts
3. asyncio.gather de 3 clips:
   - Atlas Cloud API con model_id del tier
   - First/last frame anchoring
   - Timeout 5min, retry max 3
4. Minimax voz (speech-02-turbo)
5. Whisper local captions
6. FFmpeg compose:
   - Concatenar 3 clips
   - Mix audio
   - Force 1080x1920, 30fps
7. Drive upload + metadata.json
8. Redis registry
```

#### Pipeline Pro (single_shot_multishot)

```
1. Cargar hasta 9 fotos del producto
2. Gemini con seedance_pro_director → 1 prompt multi-shot
3. Atlas Cloud API con seedance-2.0-fast/reference-to-video
   - Pasar todas las fotos como references
   - 1 sola petición de 15s
4. Minimax voz
5. Whisper captions
6. FFmpeg compose (sin concatenar, solo overlay voz/música/captions)
7. Drive upload + metadata.json
8. Redis registry
```

#### Pipeline Veo 3 (prompt-only)

```
1. Cargar fotos del producto desde Drive
2. Gemini con veo3_director → prompt 8s
3. UI muestra:
   - Prompt copiable
   - Fotos descargables (zip)
   - Campo "URL del video Drive cuando lo subas"
4. Redis registry status="manual_pending"
5. Cuando user sube video manual: status="manual_completed"
```

#### Pipeline Nano Banana 2 (prompt-only para fotos)

```
1. Cargar fotos source pobres del producto
2. Gemini con nano_banana_director → prompt
3. UI muestra:
   - Prompt copiable
   - Fotos source descargables
   - Upload zone para fotos generadas
4. Cuando user sube fotos: guardar en photos_generated/
5. Actualizar producto en Redis con nuevas fotos
```

### 5. Sistema de "Gems" (System Prompts)

Crear en `src/tiktok_shop/prompts/`:

```
src/tiktok_shop/prompts/
├── product_analyst.md
├── content_strategist.md
├── seedance_standard_director.md
├── seedance_advanced_director.md
├── seedance_pro_director.md
├── veo3_director.md
└── nano_banana_director.md
```

#### product_analyst.md

```markdown
# Product Analyst System Prompt

You are an expert product analyst for TikTok Shop affiliate marketing.

Task: analyze product photos (and optionally URL/description) and extract structured data.

## Output Format (JSON only, no preamble)

{
  "product_type": "string",
  "category": "string",
  "subcategory": "string",
  "key_features": ["string"],
  "materials_visual": ["string"],
  "has_complex_packaging_text": boolean,
  "best_camera_angles": ["packshot", "in_use", "detail", "lifestyle"],
  "suggested_audiences": ["string (Spanish)"],
  "selling_points": ["string"],
  "photos_quality_assessment": "high" | "medium" | "low",
  "needs_nano_banana_regeneration": boolean,
  "warnings": ["string"]
}

## Rules

- If packaging has prominent text/logo → has_complex_packaging_text: true
- If photos are <1024px or have artifacts/watermarks → needs_nano_banana_regeneration: true
- Spanish-speaking audience suggestions (5 distinct)
- Selling points must be CONSUMER-CENTRIC
- Only valid JSON output
```

#### content_strategist.md

```markdown
# TikTok Shop Content Strategist

You are a TikTok Shop content strategist focused on conversions.

Input: product analysis + audience + hook category + duration + tier

Output (JSON only):

{
  "hook_text": "First 3 seconds of voiceover, must stop the scroll",
  "voiceover_script": "Full script for [duration]s, max 80 words for 15s",
  "captions_emphasis": ["KEY", "WORDS"],
  "cta_text": "Final CTA",
  "video_structure": [
    {
      "clip_number": 1,
      "duration_seconds": 5,
      "purpose": "hook/product reveal/social proof",
      "visual_description": "what to show",
      "voiceover_segment": "specific words"
    }
  ],
  "human_presence_required": true,
  "tiktok_hashtags": ["#fyp", "..."]
}

## Rules

- Spanish only (or specified language)
- Voiceover CONVERSATIONAL not corporate
- Hook MUST stop scroll in 3 seconds
- ALWAYS include hands or partial human presence
- For tier=standard or advanced (multi-clip):
  - 15s = 3 clips × 5s with continuity
  - 10s = 2 clips × 5s
  - 5s = 1 clip
- For tier=pro: 1 video with internal multi-shot description
- For tier=veo3: 1 video of 8s, single coherent shot
- CTA must mention "link en bio" or "toca el cesto"
- 5-8 hashtags total
```

#### seedance_standard_director.md / seedance_advanced_director.md

```markdown
# Seedance Image-to-Video Director (Standard/Advanced)

Expert in Seedance v1.5 Pro (Fast/normal) image-to-video prompts.

Input: video_structure from strategist + product photos + camera style

Output (JSON only):

[
  {
    "clip_idx": 0,
    "duration": 5,
    "ref_photo_index": 0,
    "use_first_frame_anchor": false,
    "anchor_to_previous_clip_end": null,
    "prompt": "..."
  },
  {
    "clip_idx": 1,
    "duration": 5,
    "ref_photo_index": 1,
    "use_first_frame_anchor": true,
    "anchor_to_previous_clip_end": 0,
    "prompt": "..."
  }
]

## Prompt Structure (per clip, max 80 words)

[CAMERA]: explicit slow movement
[SUBJECT]: from reference photo
[ENVIRONMENT]: setting/background
[LIGHTING]: type, direction, mood
[STYLE]: cinematic / commercial / UGC / ASMR
[NEGATIVES]: explicit avoid list

## Rules

- AVOID prompts requiring legible text on packaging
- Camera SLOW: push-in, orbit, pan. NEVER fast/shaky
- Product STATIC, only camera moves
- Anchor between clips: clip N's last frame = clip N+1's first
- Hands ok but no extreme close-ups
- Maximum 1 person, partial body
- JSON only, no preamble
```

#### seedance_pro_director.md

```markdown
# Seedance 2.0 Reference-to-Video Director (Pro)

Expert in Seedance 2.0 Fast Reference-to-Video, multi-shot capable.

Input: video_structure + product photos + camera style

Output (JSON only):

{
  "duration": 15,
  "ref_photos_indices": [0, 1, 2, 3],
  "ref_videos": [],
  "ref_audios": [],
  "prompt": "..."
}

## Prompt Structure (single 15s clip with multi-shot)

"Shot 1 (0-5s): [CAMERA] [SUBJECT] [LIGHTING] [STYLE].
Shot 2 (5-10s): [CAMERA] [SUBJECT] [LIGHTING] [STYLE].
Shot 3 (10-15s): [CAMERA] [SUBJECT] [LIGHTING] [STYLE].
Smooth transitions between shots. Consistent product appearance."

## Rules

- Use ALL provided reference photos (max 9)
- Multi-shot internal transitions auto-generated by model
- Each shot ~5s typically
- Product MUST stay consistent across shots
- Lighting consistent (no random changes)
- JSON only, no preamble
```

#### veo3_director.md

```markdown
# Veo 3 Director System Prompt

Expert in Google Veo 3 (8-second video generation).

Input: video_structure + product photos + style preference

Output: a SINGLE prompt string (max 100 words), ready to paste in Gemini chat.

## What Veo 3 does WELL
- Cinematic shots
- Packaging recreation with text
- Realistic lighting and physics
- Single coherent 8s scene

## What Veo 3 STRUGGLES with
- Multi-shot with hard cuts (use single continuous shot)
- Hand close-ups (fingers can deform)
- Reading text smaller than 30% of frame
- Multiple human faces

## Prompt Structure

[CAMERA]: explicit slow movement
[SUBJECT]: detailed from reference photos
[ENVIRONMENT]: scene setting
[LIGHTING]: type, direction, mood, time of day
[STYLE]: cinematic / UGC / ASMR / lifestyle
[NEGATIVE]: avoid

## Output Format

Just the prompt string. NO preamble. NO markdown.
Maximum 100 words.
End with: "9:16 vertical format, 8 seconds, single continuous shot."
```

#### nano_banana_director.md

```markdown
# Nano Banana 2 Director System Prompt

Expert in Google Nano Banana 2 prompts for product photography generation.

Task: Generate prompt to create premium product photos from low-quality source images.

Input: product description + 1-2 source photos + desired use cases

Output: a SINGLE prompt string (max 150 words), ready to paste in Gemini chat with Nano Banana 2.

## Goal

Generate 4-8 premium photos of the SAME product:
- Multiple angles (front, side, 3/4, top, hand-held)
- Clean consistent backgrounds
- Studio-quality lighting
- 9:16 vertical or square format
- Professional product photography style

## Prompt Structure

"Generate professional product photography of [PRODUCT_DESCRIPTION]:
1. Front view, clean white background, soft studio lighting
2. 3/4 angle view, same lighting, same background
3. Hand holding the product, lifestyle context, warm natural light
4. Macro detail shot showing texture
5. Top-down view on minimalist surface
[continue per use case]

CRITICAL: Maintain EXACT product appearance across all images.
Same colors, same labels, same proportions. Only angle and context vary.
9:16 vertical format. Ultra high quality. Photorealistic."

## Rules

- ALWAYS request 4-8 distinct angles
- ALWAYS include "Maintain EXACT product appearance across all images"
- Match style to product use cases (ASMR macro / lifestyle / packshot)
- Output: just the prompt, no preamble
- Maximum 150 words
```

### 6. Voice Library

**Página**: `/tiktok-shop/voices`

- Listar voces clonadas + presets MiniMax
- Botón "Clonar nueva voz" (sample MP3 → POST Minimax /v1/voice_clone)
- Botón "Probar voz" (genera audio sample con texto custom)

### 7. Histórico y Dashboard

**Página**: `/tiktok-shop/history`

- Tabla generaciones (fecha, usuario, producto, tier, coste, status, link Drive)
- Dashboard:
  - Coste total mes (por tier)
  - Coste por usuario / producto
  - Vídeos/día (gráfico)
  - Estado Pilot Program de cada cuenta
  - Top hooks por uso
  - Alertas cuentas próximas a graduarse

---

## INTEGRACIÓN CON LO EXISTENTE

### NO TOCAR
- Sección Creator Reward
- Schemas Redis existentes
- UI/UX general

### REUSAR
- Cliente MiniMax existente (`src/locutor.py`)
- Helpers FFmpeg si existen
- Whisper local si configurado
- Logging structure
- Error handling patterns

### AÑADIR NUEVO
- Módulo `src/tiktok_shop/` completo
- Cliente Atlas Cloud (image-to-video + reference-to-video)
- System prompts en `src/tiktok_shop/prompts/*.md`
- Schemas Redis con prefijo `tiktok_shop:`
- UI sections nuevas

---

## ESTRUCTURA DE CÓDIGO

```
src/
├── creator_reward/                 # YA EXISTE, no tocar
│
└── tiktok_shop/                    # NUEVO
    ├── __init__.py
    ├── config.py                   # VIDEO_MODELS (3 tiers + 2 prompt-only)
    ├── api/
    │   ├── atlas_cloud.py          # Cliente Atlas (i2v + ref2v)
    │   ├── minimax.py              # REUSA src/locutor.py
    │   └── gemini.py               # Cliente Gemini multimodal
    ├── pipeline/
    │   ├── analyzer.py
    │   ├── strategist.py
    │   ├── seedance_generator.py   # Standard + Advanced
    │   ├── seedance_pro_generator.py
    │   ├── veo3_prompt_generator.py
    │   ├── nano_banana_prompt_generator.py
    │   ├── voice.py
    │   ├── captions.py
    │   ├── editor.py
    │   └── drive_uploader.py
    ├── prompts/
    │   ├── product_analyst.md
    │   ├── content_strategist.md
    │   ├── seedance_standard_director.md
    │   ├── seedance_advanced_director.md
    │   ├── seedance_pro_director.md
    │   ├── veo3_director.md
    │   └── nano_banana_director.md
    ├── models/
    ├── repositories/
    ├── services/
    │   └── tier_selector.py        # Recomendación tier por producto
    ├── ui/pages/
    └── utils/
```

---

## PLAN DE IMPLEMENTACIÓN POR FASES

### Fase 1: Base + CRUD (Día 1-3)
- Estructura módulo
- Redis schemas con prefijo tiktok_shop:
- Modelos Pydantic
- CRUD Users (sin UI)
- CRUD Products (sin UI)
- Estructura inicial Drive

### Fase 2: Análisis y Generación de Prompts (Día 4-5)
- Cliente Gemini
- product_analyst implementado
- content_strategist implementado
- 5 directors implementados (3 seedance + veo3 + nano_banana)
- System Prompts cargados desde .md
- Tests con producto real

### Fase 3: Generación de Video (Día 6-8)
- Cliente Atlas Cloud (i2v + ref2v)
- Pipeline Standard + Advanced (multi_clip_anchor)
- Pipeline Pro (single_shot_multishot)
- Pipeline Veo 3 (prompt-only)
- Pipeline Nano Banana 2 (prompt-only)
- Reuso Minimax via src/locutor.py
- Whisper captions
- FFmpeg composer
- Drive uploader
- Test E2E

### Fase 4: UI (Día 9-12)
- Página Users
- Wizard Products (8 pasos con Nano Banana)
- Wizard generación (3 tiers + Veo 3)
- Voice Library
- Histórico
- Dashboard

### Fase 5: Pulido (Día 13-14)
- Pilot Program tracker
- Generación múltiple variantes
- Tier selector inteligente
- Calculadora coste tiempo real
- Manejo errores robusto

---

## RESTRICCIONES

### NO
- Modificar Creator Reward
- Suscripciones APIs (todo pay-per-use)
- Publicación auto a TikTok
- Selenium/automation browser para TikTok
- Romper schemas Redis existentes

### SÍ
- Patrones código existentes
- Async/await en I/O (asyncio.gather)
- Type hints
- Logging estructurado
- Retry exponencial (max 3) en errores transitorios
- Costes calculados en cada generación
- System prompts en .md (NUNCA hardcoded)

---

## INFORMACIÓN DE CONTEXTO

### Precios Atlas Cloud (con descuentos vigentes)

```
Standard:  Seedance v1.5 Pro Fast    $0.018/seg = $0.27/15s
Advanced:  Seedance v1.5 Pro         $0.047/seg = $0.71/15s
Pro:       Seedance 2.0 Fast Ref     $0.072/seg = $1.08/15s
```

### TikTok Shop Affiliate Pilot Program (España)

- <5000 followers → Pilot Program automático
- Límite: 5 shoppable videos/semana hasta graduación
- Para graduar (UNA): 5000+ followers / 6+ shoppable + 30 días + quiz + CHR≥176 / 10 órdenes + 30 días
- Graduado: shoppable ilimitados, programación 30 días vista
- Videos NO shoppable son ilimitados durante Pilot

### Sobre AI

- AI disclosure obligatorio en TikTok
- Presencia humana parcial (manos, torso) — TikTok penaliza 100% AI sin humanos
- Pipeline genera prompts con esto considerado

---

## NOTAS FINALES

Módulo pensado para crecer iterativamente. Fase 1 entrega valor mínimo. Cada fase añade capacidad. Prefiero algo simple funcionando hoy que algo perfecto en 2 meses.

Si encuentras decisiones técnicas no especificadas, **PREGUNTA antes de asumir**.
