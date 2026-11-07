# Variables de entorno (.env) y rutas de Drive

> Movido literal desde CLAUDE.md (nov 2026) para no cargarlo en cada chat. Se lee solo al tocar este tema.

## Variables de entorno (`.env`)

```env
# === Programa 1 — Creator Reward ===
# Path raíz de assets CR (Drive sincronizado). Auto-detect si no se define
# (escanea "Mi unidad/Nebulabs/TikTok/Creator Reward/TIKTOK_ASSETS").
# TIKTOK_ROOT_PATH="H:/Mi unidad/Nebulabs/TikTok/Creator Reward/TIKTOK_ASSETS"

# === Programa 2 — TikTok Shop ===
# Path raíz TikTok Shop. HERMANO de TIKTOK_CR (no anidado). Auto-detect si
# no se define (escanea "Mi unidad/Nebulabs/TikTok/TIKTOK_SHOP").
# TIKTOK_SHOP_ROOT_PATH="H:/Mi unidad/Nebulabs/TikTok/TIKTOK_SHOP"

# Atlas Cloud (Seedance — los 3 tiers Standard/Advanced/Pro). URL default oficial.
ATLASCLOUD_API_KEY=...
# ATLASCLOUD_BASE_URL=https://api.atlascloud.ai/api/v1   # opcional override
# ATLAS_POLL_TIMEOUT_S=7200                              # default 2h. Sube si Standard
                                                         #            tier suele tardar más.

# fal.ai — fallback automático de Atlas Cloud. Mismo modelo Seedance pero
# en otro hosting con queue independiente. Se activa solo si Atlas falla.
# Si no está configurado, jobs fallidos en Atlas propagan el error.
# FAL_API_KEY=...
# FAL_POLL_TIMEOUT_S=1800                                # default 30 min

# === Compartido entre programas ===
OPENAI_API_KEY=...                   # Presidentes — guion JSON
MINIMAX_API_KEY=...                  # TTS — los 3 nichos CR + TikTok Shop
MINIMAX_GROUP_ID=...
MINIMAX_VOICE_ID=...                 # voz default (inglesa, Presidents)
PRONOSTICOS_VOICE_ID=Spanish_*       # opcional — override Pronósticos

# Gemini — TikTok Shop dual-key con fallback (FREE → PAID si 429); legacy
# `GOOGLE_GEMINI_KEY` lo usa Creator Reward y solo se reusa si no hay FREE/PAID.
GOOGLE_GEMINI_KEY_FREE=AIza...       # proyecto sin billing (free tier)
GOOGLE_GEMINI_KEY_PAID=AIza...       # proyecto con billing (~5€/mes)
GOOGLE_GEMINI_KEY=...                # legacy compartido con CR

# Upstash Redis (Pronósticos prefijo `betai:`, TikTok Shop prefijo `tiktok_shop:`)
UPSTASH_REDIS_REST_URL=https://xxxxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=AX...
# Redis LOCAL de la fábrica (VPS, oct 2026): servicios `redis` + `redis-rest`
# (API REST de Upstash, deploy/redis-rest/). Interruptor: con FABRICA_REDIS_REST_URL
# la fábrica usa el local; Editor Auto (↔ nebulabs-media) y Pronósticos (← Master
# Picks) siguen SIEMPRE en Upstash vía UPSTASH_SHARED_* (los pone docker-compose).
# FABRICA_REDIS_REST_URL=http://redis-rest:8080
# FABRICA_REDIS_REST_TOKEN=...
# REDIS_DATA_PATH=/mnt/HC_Volume_106974679/redis-data
REDIS_PREFIX=betai:                  # default — solo afecta a Pronósticos

# APIs stock Pronósticos (opcionales)
PEXELS_API_KEY=...
PIXABAY_API_KEY=...

# Opcional TikTok Shop
# TIKTOK_SHOP_MONTHLY_BUDGET_USD=50   # alerta dashboard al 80%

# === Programa 3 — Editor Auto ===
# Path raíz TikTok Editor. HERMANO de TIKTOK_CR/TIKTOK_SHOP. Auto-detect si
# no se define (escanea "Mi unidad/Nebulabs/TikTok/TIKTOK_EDITOR").
# TIKTOK_EDITOR_ROOT_PATH="H:/Mi unidad/Nebulabs/TikTok/TIKTOK_EDITOR"
# EDITOR_AUTO_REDIS_PREFIX=editor_auto:   # default
# ANTHROPIC_API_KEY_EDITOR_AUTO — silence_cutter usa Claude Haiku (OpenAI de respaldo)
# EDITOR_ASR_PROVIDER=deepgram + DEEPGRAM_API_KEY — transcripción de todo el editor (src/editor_auto/asr.py; Whisper de respaldo)

# === Programa 4 — Tiktok Shop AI Pro (Viralización) ===
# Path raíz LOCAL (no Drive) de assets: gancho/audios/paisajes/música.
# Auto-detect si no se define (prueba "~/viralizacion_assets").
# VIRALIZACION_ASSETS_PATH="/home/nebulabsai/viralizacion_assets"
# VIRALIZACION_REDIS_PREFIX=viralizacion:   # default
# CUENTA_PILOTO_REDIS_PREFIX=cuenta_piloto:  # default
# FISH_API_KEY=sk-fish-...                   # TTS del POV BOF Largo
# ANTHROPIC_API_KEY_AI_PRO=sk-ant-...       # textos/guiones de AI Pro (src/tiktok_shop/api/claude.py:
#                                          #   Haiku texto, Sonnet bajo fotos, Haiku bajo guiones POV+carrusel, Sonnet medio UGC/ropa; Gemini de respaldo)
# AI_PRO_LLM=gemini                         # vuelve todo AI Pro a Gemini sin tocar código
# ANTHROPIC_API_KEY_EDITOR_AUTO=sk-ant-...  # IA del cortador (src/editor_auto/api/claude_client.py, Haiku;
#                                          #   OpenAI de respaldo; EDITOR_AUTO_LLM=openai vuelve a OpenAI)
# NICHO_POV_BOF_LARGO_REDIS_PREFIX=nicho_pov_bof_largo:  # default
# ZOOM_MARCA_AGUA=1.05                       # ampliación que se come la marca
# ESQUINA_MARCA_AGUA=abajo-derecha           #   de agua del generador de vídeo
# PUBLIC_BASE_URL=https://factory.nebulabsmedia.com  # URL pública del MCP y sus enlaces
# MCP_TOKEN_SALT=1                           # cambiarlo revoca todos los tokens del MCP
# AGENTE_BANDEJA_DIR=                        # solo dev/tests: bandeja fuera del Drive
# === Drive (docs/DRIVE.md, src/rutas_drive.py) — Redis guarda `drive:<ruta relativa>` ===
# NEBULABS_DRIVE_DIR=Nebulabs/TikTok              # antes NEBULABS_AUTOMATED_TIKTOK
# AI_PRO_DRIVE_DIR=Nebulabs/TikTok/TikTok Shop    # Programa 4 (antes …/TIKTOK_SHOP_AI_PRO)
# CR_DRIVE_DIR=Nebulabs/TikTok/Creator Reward     # antes TIKTOK_CR (TIKTOK_ROOT_PATH sale de aquí)
# CURSO_DRIVE_DIR=Nebulabs/TikTok/TikTok Shop/_curso   # copias/paquetes de Productos España, Skool
# DRIVE_ALIAS_JSON='{"viejo": "nuevo"}'      # alias extra de rutas viejas (al mover carpetas)
```
