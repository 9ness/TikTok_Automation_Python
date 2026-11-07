# Programa 2 — TikTok Shop (Seedance/Veo3, Radar de productos)

> Movido literal desde CLAUDE.md (nov 2026) para no cargarlo en cada chat. Se lee solo al tocar este tema.

## Programa 2 — TikTok Shop (en construcción)

**Briefing completo en [`TIKTOK_SHOP_MODULE.md`](TIKTOK_SHOP_MODULE.md)** —
fuente de verdad del módulo (arquitectura, esquemas Redis, fases, prompts,
flujos por tier, Pilot Program, Drive layout).

**Propósito:** afiliado TikTok Shop España. Vídeos AI multi-cuenta × producto
con Seedance (3 tiers Atlas) o Veo3 / Nano Banana (prompt-only manual).
Independiente del Programa 1 — selector en sidebar separa ambos.

**Raíz Drive:** `TIKTOK_SHOP/` — HERMANA de `TIKTOK_CR/`, no anidada. Helper
canónico: `src/tiktok_shop/config.py:resolve_shop_root()` (autodetect con
override `TIKTOK_SHOP_ROOT_PATH` en .env). Estructura interna:
`_users/@user/products/{slug}/videos/` + `_products/{slug}/photos_source/`
+ `_products/{slug}/photos_generated/`.

**Módulos** (todos en [`src/tiktok_shop/`](src/tiktok_shop/)):
`api/{atlas_cloud,gemini,minimax_clone}.py`,
`pipeline/{analyzer,strategist,seedance_director,seedance_renderer,veo3_director,nano_banana_prompt_generator,carousel_director,editor,drive_uploader}.py`,
`prompts/*.md`, `repos/*_repo.py`, `services/{cost_calculator,pilot_tracker,tier_selector,discovery_service,ads_signal,creation_pack}.py`,
`utils/{duration_splitter,image_url_provider,photo_quality}.py`,
`ui/{shop_router,tab_*}.py`.

**Redis** (prefijo `tiktok_shop:`): `user:`, `product:`, `generation:`, `voice:`, `discovery:`, `plan:`.

**🔍 Radar de Productos** (tab `ui/tab_radar.py`): descubre productos ganadores
con inyección de ADS + pocos creadores (estrategia GMV Max) vía EchoTik
(`ECHOTIK_API_USER`/`ECHOTIK_API_PASSWORD`). `services/discovery_service.py`
escanea ranklist/keywords → `services/ads_signal.py` puntúa (demanda, pocos
creadores, ADS, momentum, comisión) → importa a `Product`. Genera también
carruseles (`pipeline/carousel_director.py` + `prompts/carousel_director.md`).
Kalodata NO tiene API barata (solo Enterprise) — el proxy de ADS se infiere de
los vídeos: proxy EchoTik (views altas + engagement bajo + ventas) Y/O la
ETIQUETA AD real de TikTok leída vía Apify (`apify_cloud.extract_ad_flag` +
`search_product_ad_videos`) — `ads_signal.ads_injection_signal` combina ambas en
`gmv_max_likelihood` (0-100) + `probable_boosted`. Selector de fuente en el scan.
`services/creation_pack.py:build_pack/plan_week` deja el producto LISTO PARA
CREAR: descarga fotos (image_search), análisis, research de vídeos ganadores,
genera estilos de vídeo (preset_generator) + carruseles + prompt Nano Banana,
y escribe `_products/<slug>/PLAN.md` + `prompt_templates/` (+ `_plans/week_*.md`
repartiendo productos por día). Persiste un `WeekPlan` (`models/week_plan.py`,
`repos/plan_repo.py`, key `plan:`) → sub-tab "📅 Calendario" muestra qué producto
probar cada día con checkbox "probado". `Product.origin` ("manual"|"radar")
distingue los importados por el Radar de los creados a mano (filtro + badge en
pestaña Productos). UI Radar: sub-tabs "🔎 Descubrir / 🗓️ Plan 7 días /
📅 Calendario / 🎠 Carruseles".
Cola unificada con Creator Reward via `JobMode.TIKTOK_SHOP`.

**Tiers** (5, ver [`config.py`](src/tiktok_shop/config.py)):
🟢 `standard` ($0.018/s i2v) · 🟡 `advanced` ($0.047/s i2v) · 🔴 `pro`
($0.072/s ref2v multi-shot) · 🟣 `veo3_prompt_only` · 🍌 `nano_banana_prompt_only`.
Imágenes a Atlas como **base64 inline** (los 3 tiers). Pro acepta hasta 9 refs.

**Críticas:** `ai_disclosure: true` siempre · presencia humana parcial · Pilot
Program máx 5 shoppable/semana (tracker en `services/pilot_tracker.py`).

---

### Programa 2 — TikTok Shop

Sin sidebar — todo en tabs del área principal: Productos / Usuarios /
Generar Vídeo / Voces / Histórico (ver [`src/tiktok_shop/ui/`](src/tiktok_shop/ui/)).

