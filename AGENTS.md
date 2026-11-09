# AGENTS.md — TikTok_Automation_Python

> Manual de trabajo para agentes de IA (OpenCode / Claude Code / Codex) en este repo.
> Resumen operativo; el contexto por programa/nicho, las convenciones, la tabla de documentación y
> el modo CAVEMAN están en [`CLAUDE.md`](CLAUDE.md) (fuente de verdad) y el detalle en `docs/contexto/`.
> Idioma de comunicación con el usuario: **ESPAÑOL**.

---

## Selección de modelo (auto-routing — hazlo ANTES de empezar la tarea)
Este proyecto trabaja con dos PERFILES, no con nombres fijos:
- Perfil PESADO (rol tipo "Opus": el potente) — mejor en ficheros enormes y tareas largas/multi-fichero.
- Perfil DIARIO (rol tipo "Sonnet": rápido y barato) — el de por defecto para tareas normales.

| Perfil | Modelo |
|---|---|
| PESADO | el modelo potente del usuario (él sabe cuál cargar) |
| DIARIO | el modelo rápido/barato del usuario (él sabe cuál cargar) |

Al recibir una tarea, clasifícala y avisa en UNA línea. Es PESADA si cumple CUALQUIERA:
- Localizar/modificar detalles en un fichero muy grande (> ~2000 líneas) o varios grandes.
- El cambio toca MÁS de ~3-4 ficheros o muchos call-sites.
- Tarea multi-paso larga (migración, barrido) de muchos turnos.
- Perder el hilo entre pasos tendría coste alto.
Si no, es LIGERA. Si es PESADA: di "Esta tarea es PESADA (motivo: …), usa el perfil PESADO
(ver tabla); si no lo tienes cargado, cámbialo antes de seguir." Si es LIGERA: procede sin avisar.
En ficheros de miles de líneas, si concluyes que algo "no existe", haz grep del nombre exacto antes de afirmarlo.

**Ficheros que casi siempre disparan PESADO aquí** (verificado con `wc -l`, nov 2026):
`src/editor_auto/tools/silence_cutter.py` (~8.250) ·
`src/queue/runners.py` (~5.590) ·
`main.py` (~2.465, Streamlit legacy) ·
`frontend/components/products/PresetsManager.tsx` (~2.320) ·
`src/api/routers/products.py` (~2.210) ·
`src/api/routers/tiktok_shop/radar.py` (~1.620) ·
`frontend/components/generate/shop/Veo3Card.tsx` (~1.540) ·
`src/pronosticos/pipeline.py` (~1.450) ·
`frontend/app/editor-auto/users/_components/UserFoldersPanel.tsx` (~1.430) ·
`frontend/app/tiktok-shop/calendar/page.tsx` (~1.360) ·
`src/tiktok_shop/pipeline/preset_generator.py` (~1.250) ·
`src/api/routers/editor_auto/web_upload.py` (~1.230) ·
`src/tiktok_shop/pipeline/seedance_renderer.py` (~1.140) ·
`frontend/components/generate/GeneratorWizard.tsx` (~1.115) ·
`src/subtitles_only.py` (~1.030) ·
`src/tiktok_shop/ui/tab_products.py` (~1.020).

---

## 1. Resumen del proyecto

Fábrica de vídeos verticales 9:16 para TikTok. Backend Python (FastAPI + cola de jobs propia con
WebSocket de progreso) que orquesta pipelines de IA generativa y edición de vídeo (guiones
OpenAI/Gemini/Claude, voz MiniMax/Fish, faster-whisper, MoviePy/FFmpeg, subtítulos karaoke).
**4 programas aislados** entre sí (Creator Reward, TikTok Shop, Editor Auto, Tiktok Shop AI Pro; ver
`CLAUDE.md`). Frontend Next.js (App Router). `main.py` es la UI Streamlit **legacy**: ya NO se sirve
(retirada del deploy en sep 2026, `Dockerfile.api` no la copia). Estado y assets: Redis (Upstash REST
y Redis local de la fábrica, ver `docs/contexto/env-vars.md`) + Google Drive montado por rclone.

**Stack:** Python 3.10+ · FastAPI + uvicorn · MoviePy <2 + FFmpeg · faster-whisper · Silero VAD +
torchaudio 2.5.1 · OpenAI · Gemini (dual-key FREE/PAID) · Claude (Haiku/Sonnet, ver env-vars) · MiniMax
TTS/voice-clone · Fish Audio · Atlas Cloud (Seedance) + fal.ai (fallback) · EchoTik / Apify (Radar) ·
easyocr + opencv-headless · Redis · Next.js 14 + TypeScript + Tailwind + Radix + React Query + Zustand ·
Docker Compose (api + web + Caddy) en el VPS Contabo `vps-trabajo` con Tailscale Funnel.

**Documentación profunda:** la tabla completa («Índice de documentación») y el detalle por nicho están
en [`CLAUDE.md`](CLAUDE.md). Lee la que toque antes de tocar código; en especial `EDITOR_DEBUGGING.md`
antes de `silence_cutter.py`, `UI_NICHOS.md` antes de una pantalla de nicho y
`src/agente_mcp/guias/README.md` si te piden HACER el trabajo de un menú de AI Pro.

---

## 2. Comandos reales

### Backend (raíz del repo, pip + `requirements.txt`, venv NO versionado)
```bash
python -m venv venv && source venv/bin/activate   # Windows: .\venv\Scripts\activate
pip install -r requirements.txt

uvicorn src.api.main:app --reload --port 8000     # API FastAPI (hot-reload)
streamlit run main.py                             # UI Streamlit legacy (:8501), solo en local
```

### Frontend (`/frontend`, npm)
```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
npm run build
npm run start
npm run lint       # next lint
npm run typecheck  # tsc --noEmit
npm run test       # vitest run  (npm run test:watch para watch)
```

### Tests Python (pytest, sin config propia — se ejecuta desde la raíz)
```bash
python -m pytest tests -q
python -m pytest tests/tiktok_shop tests/editor_auto tests/api -q   # por módulo
```
Suites en `tests/` (api, tiktok_shop, editor_auto, mis_tandas, multiplataforma, replicar_viral, cuotas y tests sueltos).
Usan `FakeRedis` / `FakeJobQueue` (`tests/*/conftest.py`) — no tocan red ni Upstash.
**PENDIENTE: confirmar** — `pytest` NO está en `requirements.txt` (hay que instalarlo
aparte) y no hay `pytest.ini`/`pyproject.toml`/`setup.cfg`.

### Comprobaciones rápidas (del README / DEV_SETUP)
```bash
python -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('src').rglob('*.py')]"
python -c "from src.api.main import app; print('OK', len(app.routes))"
curl http://localhost:8000/api/health
```

### Producción (solo al desplegar — nunca en dev)
```bash
docker compose --env-file .env up -d --build   # servicios: api, web, caddy
docker compose logs -f api web caddy
```
En el VPS el despliegue real se dispara con `deploy/deploy_safe.sh` (ver
[`deploy/README.md`](deploy/README.md), histórico, y [`deploy/SERVER_ACCESS.md`](deploy/SERVER_ACCESS.md), vigente).

---

## 3. Arquitectura y directorios clave

```
main.py                     # UI Streamlit LEGACY (~2.5k líneas), no se sirve. No es el entry point
src/
  api/main.py               # entry point FastAPI (uvicorn src.api.main:app)
  api/routers/<programa>/   # routers por programa; api/schemas/; api/websockets/queue_ws.py (/ws/queue)
  queue/                    # models.py (JobMode), runners.py (dispatch_job), widget Streamlit
  cost_tracking.py          # OBLIGATORIO para toda API de pago (record_*)
  locutor.py, subtitles*.py, text_hook.py, logic.py, guionista.py, video_remover.py   # transversales
  pronosticos/ construccion_pov/ tiktok_shop/ editor_auto/ viralizacion/ nicho_*/ agente_mcp/ …  # un dir por programa/nicho
whatsapp_bot/               # bot de WhatsApp del Editor: servicio AUTÓNOMO para vps-webs (no importa src/; ver su README)
frontend/                   # Next.js App Router
tests/                      # pytest + FakeRedis
deploy/                     # setup.sh, install_app.sh, deploy_safe.sh, webhook_listener.py, systemd/
docker-compose.yml, Dockerfile.api, Caddyfile
config/, assets/, scripts/, tools/, eval/, docs/
```

**Fuente de verdad de datos:** Redis (REST/HTTP) con prefijo por programa (`betai:` Pronósticos,
`tiktok_shop:`, `editor_auto:`, `nicho_pov_bof:`…). Assets pesados en Google Drive (`Nebulabs/TikTok/…`,
ver `docs/DRIVE.md`). **Cola unificada:** todo trabajo pasa por `JobMode` (`src/queue/models.py`) y
`dispatch_job` (`src/queue/runners.py`), que envuelve el job con `start_job`/`finalize_and_persist`.

---

## 4. Convenciones propias de este fichero

Las convenciones de código, UI, anti-sanción, vídeo no terminado, cost tracking y MCP están en `CLAUDE.md › Convenciones`.
Resumen de las OBLIGATORIAS (texto completo en `CLAUDE.md › Convenciones`; si tu agente no lee CLAUDE.md, léelo antes de tocar código):
- **Cost tracking:** toda llamada a API de pago pasa por un `record_*` de `src/cost_tracking.py` con datos reales del response.
- **System prompts** en `src/<programa>/prompts/*.md`, NUNCA hardcodeados. **Aislamiento:** NUNCA mezclar lógica entre programas; solo módulos transversales.
- **Errores defensivos:** el pipeline NUNCA aborta por un asset opcional que falte; loguea y continúa. Variables en ASCII.
- **Frontend mobile-first.** Pantallas de nicho: leer `UI_NICHOS.md` ANTES de crear o retocar una.
- **Un vídeo NO está terminado hasta que se comprueba:** semáforo en Mis tandas antes de darlo por hecho.
- **Anti-sanción en TODO vídeo que se monte (OBLIGATORIO):** subtítulos de la voz, nombre del producto quemado y metadatos limpios (`limpiar_metadatos`).
- **MCP y guías al día:** toda función nueva de un menú de AI Pro entra también en el MCP y en su guía en el mismo cambio.
- **Commits:** Conventional Commits **en español, con scope**, detectados del historial. Ej.:
  `feat(radar): descubrimiento invertido — de la inyección de ADS al producto`,
  `fix(calendario): dejar vaciar los campos numéricos`, `docs(tasks): plan EchoTik en ness4b`.
  Scopes vistos: `radar`, `shop`, `calendario`, `tasks`, `pronosticos`.
- **Rama por defecto:** `main`. Remote: `origin` → `github.com/9ness/TikTok_Automation_Python`.
- **Formato:** sin black/ruff/prettier configurados; solo `next lint` y `tsc --noEmit` en el frontend.
  **PENDIENTE: confirmar** si se quiere añadir formateador Python.

---

## 5. Gotchas / cosas no obvias

1. **`silence_cutter.py` es el fichero más delicado del repo.** LEE [`EDITOR_DEBUGGING.md`](EDITOR_DEBUGGING.md)
   ANTES de tocarlo: jerarquía de señales (silero > energía > Whisper), casuística de bugs reales y cómo
   diagnosticar una queja. No parchees a ciegas.
2. **`main.py` es Streamlit legacy** (no se sirve). La app real es FastAPI (`src/api/main.py`) + Next.js.
   No rompas Streamlit al refactorizar módulos compartidos.
3. **La API NO debe depender de Streamlit.** `src/queue/__init__.py` importa el widget de forma lazy
   justo por eso — no lo subas a top-level.
4. **Redis en modo REST**, no TCP (`UPSTASH_REDIS_REST_URL` + `_TOKEN`, o `FABRICA_REDIS_REST_*` para el local).
5. **Dependencia cruzada con `bet-ai-master`:** Pronósticos lee `betai:daily_bets_tiktok_video:YYYY-MM`,
   escrito por el otro repo. Si el schema cambia allí, aquí se rompe (y viceversa). Ver `PronosticosAuto.md`.
6. **Pins frágiles en `requirements.txt`** — hay comentarios explicando por qué: `packaging` va primero
   (silero-vad), `moviepy<2.0`, `numpy<2.0.0`, `torchaudio==2.5.1` (>=2.10 rompe con `OSError WinError 127`).
   No los "actualices" sin motivo.
7. **Rutas de assets en Google Drive:** usa los helpers de resolución (`src/rutas_drive.py`,
   `src/tiktok_shop/config.py:resolve_shop_root()`), nunca rutas hardcodeadas. En el VPS es un mount
   rclone, no un Drive Desktop de Windows.
8. **Gemini dual-key:** `GOOGLE_GEMINI_KEY_FREE` → fallback a `GOOGLE_GEMINI_KEY_PAID` si 429.
   `GOOGLE_GEMINI_KEY` es legacy (Creator Reward) y solo se reusa si no hay FREE/PAID.
9. **Atlas Cloud → fal.ai** es un fallback automático; si `FAL_API_KEY` no está configurada, un fallo
   de Atlas propaga el error.
10. **TikTok Shop tiene reglas de negocio no negociables:** `ai_disclosure: true` siempre, presencia
    humana parcial, y máx. 5 shoppable/semana del Pilot Program (`services/pilot_tracker.py`).
11. **El Radar depende de cuota externa:** la clave EchoTik del VPS es de una cuenta de PRUEBAS casi
    agotada (ver `tasks.md`). Si el Radar falla, mira eso antes de depurar código.
12. **CI mínimo:** `.github/workflows/` solo compila la APK (`android-apk*.yml`). Nada valida tests/lint
    salvo que los ejecutes a mano.
13. **`.gitignore` ignora `*.mp4/*.mp3/*.jpg/*.png`** con excepciones puntuales
    (`frontend/public/brand/*`, `frontend/app/icon.png`…). Si añades un asset de marca y no aparece en
    producción, es esto.
14. **Raíz algo sucia:** `inputs_generados/`, `tmp/` (scripts sueltos de análisis) y un fichero llamado
    `-` (contiene `fake_output_mp4`, residuo de un test). No son parte del pipeline.
    **PENDIENTE: confirmar** si el fichero `-` se puede borrar.
15. **Ediciones en ficheros largos:** nada de parches parciales ambiguos. Usa reemplazos con contexto
    amplio y único, o reescribe la función completa.
16. **Al añadir un MODO o programa nuevo**, sigue [`ADDING_PROGRAM.md`](ADDING_PROGRAM.md) entero
    (JobMode + runner + cost tracking + API + frontend + Docker + tests + docs). Saltarse un touchpoint
    deja el programa a medias.

---

## 6. Reglas de trabajo

- **Git:** el agente NO commitea ni pushea salvo petición explícita del usuario.
  Cuando se autorice: `git add <fichero concreto>`, nunca `git add .`.
  Prohibido: force-push, reescribir historial, crear/borrar ramas o tags.
  Push a `main` puede disparar el auto-deploy del VPS (webhook) — piénsalo antes.
- **NO tocar sin permiso:** los prompts `src/*/prompts/*.md` (calibrados en
  producción), los schemas de Redis (rompen `bet-ai-master` y/o el frontend),
  `deploy/**` y `docker-compose.yml`/`Caddyfile`, y los ficheros temporales de la
  raíz (`tmp/`, `-`).
- **Secretos:** nunca los imprimas, comitees ni los saques de `.env` /
  `secrets/`. `.gitignore` ya bloquea `.env` y `secrets/` — no lo debilites.
  Claves en juego: `OPENAI_API_KEY`, `MINIMAX_API_KEY`/`GROUP_ID`/`VOICE_ID`,
  `GOOGLE_GEMINI_KEY*`, `ATLASCLOUD_API_KEY`, `FAL_API_KEY`,
  `UPSTASH_REDIS_REST_URL`/`TOKEN`, `ECHOTIK_API_USER`/`PASSWORD`,
  `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `API_KEY` (auth de la API).
- **Si cambias un schema de Redis o de la API**, actualiza en el MISMO cambio
  los tipos TypeScript del frontend y la doc del `*_MODULE.md` correspondiente.
- **Antes de un comando o escritura crítica**, párate y razona: *"¿esto rompe el
  build, la Streamlit legacy, el otro programa o el deploy del VPS?"*.
- **Memoria y tareas:** `learnings.md` (1 línea por bug/aprendizaje; NO crees otro fichero) y
  `tasks.md` (al cerrar, a `## ✅ Done`). Cuándo actualizar `CLAUDE.md`: ver «Mantenimiento» allí.
- **Ante cualquier duda, pregunta.** No inventes rutas, keys ni comandos.

## 7. Skills en reserva

Doce skills de vídeo y análisis están fuera de `~/.claude/skills` para no gastar contexto: `hyperframes` (y `-animation`, `-audio`, `-cli`, `-core`, `-creative`, `-studio`), `general-video`, `media-use`, `motion-graphics`, `music-to-video` y `reverse-engineer-anything`. Están en `~/.claude/skills-reserva/`. Úsalas solo si la tarea es de animación o vídeo por código con HyperFrames, vídeo desde música o ingeniería inversa: lee su `SKILL.md` ahí, o muévela de vuelta a `~/.claude/skills/` y abre un chat nuevo.
