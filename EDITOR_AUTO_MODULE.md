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
│   └── silence_cutter.py Silero VAD + Claude Haiku / OpenAI (transcript clean-up)
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
| `silence_cutter` | 10 | Silero VAD (local) + Claude Haiku (OpenAI de respaldo) | tokens Claude/OpenAI | Cortes A/V con concat MoviePy |
| `audio_clean`    | 20 | — (ffmpeg local) | — | «Mejorar voz»: ruido + volumen tras el corte. **Apagada: no está en el flujo de nadie** (ver abajo) |
| `vip_overlays`   | 60 | faster-whisper (local) + Claude Haiku | ~0,003 $ | Edición VIP: gancho, rótulos, zooms, fotos, SFX |
| `subs_auto`      | 90 | faster-whisper (local) | — | Reusa `src/subtitles*.py` |
| `sticker_arrow`  | — | — | — | Flecha CTA (`.mov` de `Assets/flechas/`) |

**Revisión antes de entregar (clientes web, 5/11/2026):** con
`settings:manual_approval` = 1 el auto-revisor re-edita solo lo malo y deja lo
bueno «en revisión»; un agente lo revisa (cron `scripts/vigilar_revision_clientes.sh`
cada 5 min → rutina `~/rutinas/revision-clientes-nebulabs.md` →
`scripts/revision_clientes.sh pendientes|aprobar|rehacer`, que habla con la API
por HTTP). Aprobar el último del día manda el email «listos» (activado por
defecto: solo no se avisa a quien lo apagó). Los pasos que pone el equipo a
mano (`vip_overlays`) se conservan al re-sincronizar con el estilo de la web.

**Flechas y estilos de subtítulos del cliente** salen del catálogo común
[`src/catalogo_edicion/`](src/catalogo_edicion/README.md): solo lo aprobado
(`editor_auto: true`) se ofrece en la web y en el modo «Inteligente»; las de
Navidad son de «entrada» (se reproducen una vez y se quedan señalando).

**«Mejorar voz» (`audio_clean`, 10/11/2026 — sin activar):** para vídeos que se
oyen poco o con ruido. Tras el cortador (peso 20, así el corte sigue decidiendo
con el audio original) pasa el audio por: highpass 80 Hz → `adeclick` (opcional)
→ reducción de ruido (`motor`: `rnnoise` = filtro `arnndn` con un modelo `.rnnn`;
`afftdn`; `ninguno`) → compresor (opcional) → `loudnorm` a −16 LUFS en dos
pasadas. El vídeo va con `-c:v copy` (solo se recodifica el audio a AAC 192k /
48 kHz) y no usa ninguna API de pago. Si no hay pista de audio, está en silencio
o ffmpeg falla, copia la entrada y sigue. El modelo se busca en
`assets/rnnoise/sh.rnnn` (clave `modelo_rnnoise`); **todavía no está en el repo**
(pendiente de que Néstor decida la licencia): mientras falte, `rnnoise` solo
nivela y lo avisa (no cae a `afftdn`: medido, apaga la voz y empeora música, clics
y voz baja). Medidas y plan: `docs/editor/2026-11-10_audio_y_estilo_vip.md`. `build_tool_flow` (el flujo de la web) NO la añade: se pone a mano en
el flujo de un usuario (Usuarios › flujo › añadir herramienta «🔊 Mejorar voz»,
o `ToolStep(tool_id="audio_clean", enabled=True, config={...})`) y
`conservar_pasos_del_equipo` la mantiene al re-sincronizar con la web. Tests:
`tests/editor_auto/test_audio_clean.py`.

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

### Clientes web (nebulabsmedia.com) — planes, cola y revisión automática (nov 2026)

- **Límites por plan web**: manda el `planId` de la cuenta web (`nebulabs:user:{email}`),
  no la suscripción vieja del backend: `config.WEB_PLAN_DAILY` (Básico 3, Pro 5,
  Studio 10, Escala/`agencia` 15, VIP 5). Sin plan = prueba: `trialVideos` gratis
  y luego 402. Los admins no tienen límite.
- **Prioridad**: `params.queue_priority` (`config.WEB_PLAN_PRIORITY`, VIP el
  primero). El worker coge el de mayor prioridad entre ediciones de cliente y
  FIFO a igualdad; `posiciones_pendientes()` usa el mismo orden.
- **Revisor automático** (`web_upload.auto_review_hook`, hook de
  `JobQueue.add_finish_hook`): entregable → se aprueba solo; si no, se re-edita
  hasta `EDITOR_AUTO_REVIEW_RETRIES` (2) veces sin gastar cuota; si sigue mal,
  queda en `webday_attention:{user}:{day}` y se avisa al operador por email
  (`EDITOR_OPERATOR_EMAIL`, o la cuenta SMTP). Se apaga con Redis
  `settings:auto_review` = 0 (vuelve la aprobación manual).
  Antes de aprobar, **revisión final** (`services/revision_visual.py`, prompt
  `prompts/revision_visual.md`): ffmpeg (negros, congelados, silencio total ≥5 s,
  sin audio, A/V desfasado) + geometría sin IA frente al original (desplazado,
  aplastado, girado: los modelos no lo ven) + hoja de 16 fotogramas → Haiku
  (subtítulos cortados/superpuestos/atascados, texto en la cara, corrupción).
  ~0,0007 $; banco 3/11: 23/25 sin falsos positivos, Sonnet no mejora. Si falla
  se retiene y avisa (no re-edita); si no puede revisar, aprueba. Se apaga con
  `EDITOR_AUTO_REVISION_VISUAL=0`.

### Edición VIP automática con el estilo del cliente (nov 2026)

`tools/vip_overlays.py` repite sola la edición VIP hecha a mano del candado
(`agentes/trabajo/candado_demo/vip/vip.py`):
- **Estilo = config de la herramienta en el flujo del usuario**: colores de las
  píldoras por rol (alerta/dato/ok/neutro, o un preset), fuente, densidad de
  rótulos, gancho, fotos, zooms, SFX, color y `notas_estilo` (texto libre que
  lee la IA). Al ser por usuario, su estilo se repite en todos sus vídeos.
- **Estilo desde un vídeo de referencia**: en el flujo del usuario, la tarjeta
  «Edición VIP» tiene «Copiar estilo de un vídeo de referencia» →
  `POST /api/v1/editor-auto/tools/vip-overlays/estilo` → `services/estilo_vip.py`
  (24 fotogramas → Claude visión, ~0,002 $) rellena el formulario; se guarda
  con «Guardar flujo». CLI: `python -m src.editor_auto.services.estilo_vip <video>`.
- **Plan**: Haiku (`prompts/vip_plan.md`) con las palabras y sus tiempos + los
  sonidos fuertes sin voz (candidatos a gancho: alarma, pitido) → gancho
  (rótulo, dato y tramo que se COPIA al principio con temblor), rótulos,
  zooms y fotos. `_sanitize` impone límites: sin solapes, ≤50 % con zoom.
- **Render**: una pasada de ffmpeg (zoom por fotograma con `scale eval=frame`
  + `crop`, píldoras/tarjetas PIL con "pop", SFX sintetizados + boom, loudnorm).
  Peso 60: los tiempos ya son los cortados y fotos/flecha/subtítulos van encima
  (transcriben su salida, así que el gancho copiado no los descuadra).
  Si algo falla, copia la entrada y el flujo sigue.

## Caducidad de vídeos de clientes web (9/11/2026)

`src/editor_auto/services/retention_sweeper.py`, desde el loop del `draft_sweeper` (cada 6 h):
- Editados `salida/<día>/`: se borran a los `retention_days` (30) del día; el cliente ve
  «Descárgalos antes del …» en el panel y en el email de listos. Al caducar, claves `webday_*`
  fuera y el día pasa a `webdays_expired:{uid}` (la web lo pinta «vídeos borrados»; `/download` → 410).
- Originales `entrada/<día>/` y `recuperacion/`: a los `retention_source_days` (10). Nunca con trabajos abiertos.
- Por cliente `retention_days_override` (Usuarios › «Guardar editados»): vacío = general, 0 = nunca, N días.
- Solo cuentas web (`account_email`). Redis: `settings:retention_days`, `settings:retention_source_days`,
  `settings:retention_enabled` (0 = apagado). Env: `EDITOR_RETENTION_DAYS`, `EDITOR_RETENTION_SOURCE_DAYS`.
- A mano: `scripts/caducidad_clientes.sh simular|ejecutar` (POST `/web/admin/retention?dry_run=`).

## Variables de entorno

```env
# Path raíz Drive (opcional — autodetect por defecto)
# TIKTOK_EDITOR_ROOT_PATH="H:/Mi unidad/Nebulabs/TikTok/TIKTOK_EDITOR"
# EDITOR_AUTO_REDIS_PREFIX=editor_auto:   # default

# IA del cortador: Claude Haiku primero, OpenAI de respaldo (oct 2026)
ANTHROPIC_API_KEY_EDITOR_AUTO=sk-ant-...
# EDITOR_AUTO_LLM=openai               # vuelve a OpenAI sin tocar código
# EDITOR_AUTO_CLAUDE_MODEL=claude-sonnet-5-5   # otro modelo, para comparar
OPENAI_API_KEY=sk-...
```

Reusa `UPSTASH_REDIS_REST_URL/_TOKEN` ya compartidas entre programas.

## WhatsApp (bot)

Bot externo (otro servidor, `whatsapp_bot/`) que atiende a clientes del Editor Auto. El box solo expone
lo que necesita; todo con `X-API-Key` (`get_current_user`), prefijo `/api/v1/editor-auto/whatsapp`:

| Endpoint | Para qué |
|---|---|
| `GET /cliente?telefono=` | `resumen_cliente`: cuenta, plan, cuota de hoy y últimos 3 días con vídeos (enlaces de descarga con ticket de 6 h) |
| `POST /vincular/pedir` `{telefono,email}` | manda un código de 6 dígitos al email de la cuenta (máx 3/hora; siempre `ok:true`, no revela cuentas) |
| `POST /vincular/confirmar` `{telefono,codigo}` | confirma (máx 5 intentos, caduca a 15 min) y guarda el vínculo |
| `POST /desvincular` `{telefono}` | borra el vínculo |
| `POST /coste` `{modelo,input_tokens,output_tokens,cache_*}` | apunta gasto de Claude (`record_claude`, detail `editor_auto.whatsapp_bot`; fuera de un job queda como coste suelto) |
| `GET/POST /bot/{diagnostico,conversaciones,conversacion,plantillas,suscribir,prueba,pausa,reanudar}` | proxy con lista blanca a `{BOT_URL}/admin/<nombre>` (sin env → `configurado:false`; bot caído → `alcanzable:false`) |

Avisos del box al bot: `services/whatsapp_notify.py` → `POST {BOT_URL}/interno/aviso` (evento `videos_listos`),
enganchado en `_maybe_notify_ready` (una vez por usuario/día, flag `webday_wa_notified:`). Apagado salvo `EDITOR_WHATSAPP_AVISOS=1`.

Claves Redis nuevas (prefijo `editor_auto:`): `wa:by_phone:{tel}` → email, `wa:by_email:{email}` → tel,
`wa:codigo:{tel}` (JSON, TTL 15 min), `wa:pedidos:{tel}` (contador, TTL 1 h). Teléfono = solo dígitos con prefijo país (`34…`).
Envs: `EDITOR_BOX_PUBLIC_URL`, `EDITOR_WHATSAPP_BOT_URL`, `EDITOR_WHATSAPP_BOT_TOKEN`, `EDITOR_WHATSAPP_AVISOS` (ver `docs/contexto/env-vars.md`).

## Cost tracking

- Todas las llamadas de IA de `silence_cutter` pasan por
  `src/editor_auto/api/openai_client.py:analyze_transcript_json`, que va
  primero a `claude_client.py` (Haiku 5.5, `record_claude()`) y, si Claude
  falla, a OpenAI (`record_openai_chat()`), con tokens reales del provider.
  A/B del corpus de regresión (23/10/2026): Haiku 92/87/92/100 frente a
  OpenAI 100/87/100/100 (lo que resta es quitar ruido de fondo repetido),
  a ~0,006 $ el vídeo frente a ~0,12. Con Claude cada render pasa TRES
  comprobaciones (deep audit, coherencia siempre y revisor de sobrantes) y el
  self-heal corrige con lo que encuentran; ver `EDITOR_DEBUGGING.md` §2.
- `cost_tracking.py` añadió rates para `gpt-4o` ($2.50/$10.00 por 1M
  input/output tokens) — match por prefix del nombre del modelo.
- Transcripción: con `EDITOR_ASR_PROVIDER=deepgram` (producción desde el
  4/11/2026) TODAS las herramientas (cortador, VIP, flecha, subtítulos, fotos)
  transcriben con Deepgram nova-3 (`EDITOR_DEEPGRAM_MODEL`) vía `src/editor_auto/asr.py`
  (`record_deepgram`, ~0,0043 $/min). Si Deepgram falla, Whisper local de
  respaldo. Motivo: Whisper large-v3 en CPU tardaba 450 s y llenaba los 10 GB
  del contenedor; con Deepgram ~200 s y ~2,7 GB. Los tramos que Deepgram no
  alinea (palabras a partes iguales) y los huecos >3 s se re-piden recortados
  (`_deepgram_uniform_runs`). `Silero VAD` sigue en local, sin coste.

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

## Memoria de lecciones del motor (auto-aprendizaje)

`src/editor_auto/prompts/editor_lessons.md` es la **memoria viva del motor de
edición**: errores reales observados en vídeos de clientes, escritos como
reglas para la IA. `silence_cutter._with_lessons()` la inyecta en TODOS los
prompts de decisión de corte (holístico, pass1 analyst, pass2 false-starts,
revisión de completitud), con cache por mtime — editar el .md surte efecto en
el siguiente job sin redeploy.

**Workflow al descubrir un fallo de edición nuevo:**
1. Si el patrón es codificable → regla determinista en `silence_cutter.py`
   (snap/trim/valley/guardarraíles) — lo que no depende del LLM no falla.
2. SIEMPRE → añadir la lección a `editor_lessons.md` (para que la IA tenga el
   contexto del fallo) y el detalle técnico a `learnings.md` (para el dev).
