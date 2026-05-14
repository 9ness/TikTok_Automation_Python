# Editor Auto — Programa 3

Editor de vídeo modular tipo "puzzle": cada usuario configura un flujo
de herramientas componibles que se aplica al vídeo input al generar.

## Propósito

Tomar un vídeo manual subido por el usuario y aplicarle una cadena
configurable de transformaciones (subtítulos, corte de silencios, ...)
sin tocar la lógica de Creator Reward ni TikTok Shop. Cada combinación
usuario × flujo es independiente.

## Arquitectura (capas)

```
src/editor_auto/
├── config.py             paths Drive + redis_prefix + TOOL_POSITION_WEIGHTS
├── models/               EditorUser + ToolStep (Pydantic)
├── repos/                EditorRedis + UserRepo (prefijo `editor_auto:`)
├── tools/                BaseTool + REGISTRY + impls
│   ├── base.py           contrato (Protocol)
│   ├── subs_auto.py      subtítulos karaoke (reusa src/subtitles.py)
│   └── silence_cutter.py Silero VAD + OpenAI GPT-4o (transcript clean-up)
├── services/
│   └── flow_orchestrator.py  reordena por position_weight + ejecuta
├── pipeline/
│   └── run.py            entry point del runner de cola
├── api/
│   └── openai_client.py  wrapper Chat Completions + cost tracking
└── prompts/
    └── silence_cutter_analyst.md
```

API: `src/api/routers/editor_auto/{users,tools,enqueue}.py`.
Schemas: `src/api/schemas/editor_auto/`.
Frontend: `frontend/app/editor-auto/{users,tools,generate}/`.

## Estructura de carpetas en Drive

```
TIKTOK_EDITOR/                            (HERMANO de TIKTOK_CR/ y TIKTOK_SHOP/)
└── Usuarios/
    └── <nombre>/
        ├── entrada/                       (futuro — biblioteca de vídeos)
        └── salida/                        (MP4 finales del flujo)
            └── 2026-05-13_141522_editor_abc12345.mp4
```

Resolución de la raíz: `src/editor_auto/config.py:resolve_editor_root()`
con prioridad env `TIKTOK_EDITOR_ROOT_PATH` → autodetect → fallback
`./TIKTOK_EDITOR_FALLBACK/`. Drive Desktop o rclone sincronizan
automáticamente — la app solo copia local.

## Esquema Redis (prefijo `editor_auto:`)

| Key | Tipo | Contenido |
|---|---|---|
| `user:{uuid}` | JSON | `EditorUser.model_dump()` |
| `user:index` | SET | UUIDs de todos los usuarios |
| `user:by_name:{name}` | STR | UUID del usuario llamado `name` |
| `cost:job:{job_id}` | JSON | Cost tracking (compartido con CR/Shop) |

## Modelo `EditorUser`

```python
{
  "id": "uuid-hex",
  "name": "usuario1",                 # nombre de la carpeta Drive
  "display_name": "Usuario 1",
  "description": "",
  "tool_flow": [
    {"tool_id": "subs_auto",       "enabled": true, "config": {...}},
    {"tool_id": "silence_cutter",  "enabled": true, "config": {...}}
  ],
  "drive_folder": "...",
  "deleted": false,
  "created_at": "...",
  "updated_at": "..."
}
```

La config de cada herramienta vive **embebida en ToolStep.config** —
editable por usuario sin tablas separadas.

## Herramientas (registry)

| Tool ID | Peso | API externas | Coste | Notas |
|---|---|---|---|---|
| `silence_cutter` | 10 | Silero VAD (local) + OpenAI gpt-4o | gpt-4o tokens | Cortes A/V con concat MoviePy |
| `subs_auto`      | 90 | faster-whisper (local) | — | Reusa `src/subtitles*.py` |

**Position weight**: menor peso = se ejecuta antes. `silence_cutter`
DEBE ir antes que cualquier overlay porque modifica timestamps. El
orchestrator reordena automáticamente — el orden visual en la UI es
indicativo, no determinante.

Para añadir una herramienta nueva:
1. Crea `tools/<slug>.py` implementando el Protocol `BaseTool`.
2. Define `tool_id`, `display_name`, `description`, `position_weight`.
3. Implementa `default_config()`, `config_schema()` y `run()`.
4. Añade el peso a `config.TOOL_POSITION_WEIGHTS`.
5. Registra en `tools/__init__.py:REGISTRY`.
6. La UI consume `GET /api/v1/editor-auto/tools` y pinta el formulario
   automáticamente desde `config_schema` — no hay que tocar frontend.

## Flujo de generación

1. Frontend `POST /api/v1/editor-auto/enqueue` (multipart) con
   `file=<mp4>` + `user_id=<uuid>`.
2. El router valida, escribe `temp_work/api_uploads/editor_auto/<...>`,
   carga `EditorUser` y encola `JobMode.EDITOR_AUTO` con
   `params={user_id, input_path, temp_folder}`.
3. `dispatch_job` envuelve en `cost_tracking.start_job(program="editor_auto")`.
4. `run_editor_auto` (en `src/queue/runners.py`) llama a
   `run_editor_auto_pipeline()` que:
   - Carga el usuario.
   - Reordena `tool_flow` por `position_weight`.
   - Ejecuta cada herramienta secuencialmente con archivos temporales
     intermedios `editor_step_<job>_<idx>_<tool>.mp4`.
   - La última escribe en un final temporal, que se copia a
     `TIKTOK_EDITOR/Usuarios/<user>/salida/` con nombre versionado.

## Variables de entorno

```env
# Path raíz Drive (opcional — autodetect por defecto)
# TIKTOK_EDITOR_ROOT_PATH="H:/Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_EDITOR"
# EDITOR_AUTO_REDIS_PREFIX=editor_auto:   # default

# OpenAI (silence_cutter usa gpt-4o por defecto)
OPENAI_API_KEY=sk-...
```

Reusa `UPSTASH_REDIS_REST_URL/_TOKEN` ya compartidas entre programas.

## Cost tracking

- Las llamadas a `OpenAI Chat Completions` desde `silence_cutter`
  pasan por `src/editor_auto/api/openai_client.py:analyze_transcript_json`
  que registra `record_openai_chat()` con tokens reales del provider.
- `cost_tracking.py` añadió rates para `gpt-4o` ($2.50/$10.00 por 1M
  input/output tokens) — match por prefix del nombre del modelo.
- `Whisper local` (`faster-whisper`) y `Silero VAD` corren en local y
  no generan coste de API — no se registran.

## Dependencias añadidas

- `silero-vad>=5.1` (ONNX runtime, ligero — no requiere PyTorch full).

## Limitaciones actuales

- Un solo flujo por usuario. Para múltiples flujos ("corto" / "largo")
  habría que añadir un tier intermedio `flow_profile_id` en el job param.
- El reordenamiento es por regla fija (`TOOL_POSITION_WEIGHTS`). Si dos
  herramientas tienen el mismo peso el orden es indeterminado — añadir
  pesos distintos al registrarlas.
- No hay "preview" del flujo antes de encolar (sería un dry-run); la UI
  muestra el orden de ejecución pero la única manera de ver el resultado
  es generar.
