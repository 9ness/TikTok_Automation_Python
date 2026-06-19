# EDITOR_DEBUGGING.md — Playbook de depuración del cortador de vídeo

> **Para quién es esto:** cualquier sesión de Claude (PC o VPS remoto) que tenga
> que diagnosticar o arreglar un fallo de EDICIÓN del Editor Auto
> (`src/editor_auto/tools/silence_cutter.py`). Aquí está la inteligencia
> acumulada depurando casos reales: cómo funciona el motor, qué señales fiarse,
> los bugs que ya pasaron y cómo se diagnostican nuevos. **Léelo entero antes de
> tocar el cortador.** Detalle cronológico → `learnings.md`. Lecciones que se
> inyectan a los prompts de IA → `src/editor_auto/prompts/editor_lessons.md`.

---

## 0. La regla de oro: jerarquía de señales

El 90% de los bugs de edición salen de **fiarse de la señal equivocada**. Orden
de fiabilidad para "¿hay voz aquí y dónde?":

1. **silero VAD** (`speech_intervals`, fase `silero_vad`) — **la más fiable**.
   Detector neuronal de voz, independiente de Whisper. Si silero dice que [a,b]
   es voz, casi seguro hay habla ahí (aunque sea floja). Segmenta con silencios
   ≥0.5s, así que une palabras contiguas en un intervalo.
2. **Energía/RMS del audio** — fiable para "¿esto es silencio?" pero **frágil
   para colas de palabra** (fricativas, voz floja caen bajo el umbral de ruido).
3. **Timings de palabra de Whisper** — **NO TE FÍES de los timestamps**. Whisper
   (a) **infla spans** absorbiendo la pausa siguiente (vio "proteína" como
   `[8.28-11.12]`=2.8s cuando la palabra dura 0.4s), (b) **coloca mal** palabras
   (la misma "proteína" la puso en 8.28, en 11.6 sobre silencio, y en 10.74 según
   el modelo/run), (c) **re-transcribe distinto** el mismo audio entre runs
   ("cartón"→"carito", "asegúrate"→"trata de"). Úsalo para el TEXTO, no para
   localizar contenido en el tiempo.

**Corolario:** para decidir si un trozo cortado tenía voz real, mira **silero +
energía**, no dónde Whisper puso la palabra.

---

## 1. El motor NO es determinista

El mismo vídeo puede dar **100 en un run y 88 en otro**. Causa: Whisper
re-transcribe ligeramente distinto cada vez → la IA toma decisiones de corte
distintas → a veces sobre-corta. Implicaciones al depurar:

- **Una sola corrida no prueba nada.** Un fallo que no se reproduce un run puede
  volver al siguiente. Un fix "verificado" en 1 run puede ser suerte.
- El objetivo de los fixes NO es eliminar la varianza (imposible con Whisper)
  sino **subir el SUELO**: que cuando la IA se equivoque, una red la corrija
  (self-heal, rescate de islas).
- El progreso de la cola es de **grano grueso** (0.01 → salta al final). No
  confundir "0.33 parado 8 min" con cuelgue: con `large-v3` en CPU sobre un
  vídeo de 4 min, transcribir es genuinamente lento.

---

## 2. El pipeline en orden (qué hace cada fase)

Fases tal cual salen en `diagnostic["phases"]` (orden real de ejecución):

| Fase | Qué hace | ¿Corta CONTENIDO o solo SILENCIO? |
|---|---|---|
| `audio_leveling` | normaliza loudness si viene bajo | — |
| `whisper` | transcribe input (faster-whisper LOCAL, $0) | — |
| `span_realign` / `phantom_words` | limpia spans Whisper, quita fantasmas | — |
| `stretched_fillers` | detecta rellenos con span inflado | silencio |
| `silero_vad` | **intervalos de VOZ** (señal de oro) + silencios | silencio |
| `auto_trim` | recorta cabecera/cola muerta | silencio |
| `inter_word_gap` | corta huecos entre palabras ≥ umbral (conv 0.8s) | silencio |
| `amplitude` | corta por debajo del umbral de ruido | silencio |
| `acoustic_combined` | fusiona silero+amplitude+gap | silencio |
| `ai_holistic` | limpieza holística (gpt-5.4, 2 pasadas) | **contenido** |
| `ai` | analista de cortes (gpt-5.4) — incluye `noise_gap` | contenido / pausa |
| `ngram_repetition` | quita frases repetidas | **contenido** |
| `ai_pass2_false_starts` | falsos inicios (gpt-5.4) | **contenido** |
| `word_protection_from_acoustic` | re-anexa palabras que un corte acústico se comió | (protección) |
| `voiced_edge_rescue` | extiende bordes de keep a la voz contigua (energía) | (protección) |
| `silero_island_rescue` | **rescata islas de voz claras dentro de un `noise_gap`** | (protección) |
| `loose_filler_cleanup` | tira clips sueltos de relleno ('os','la') | limpieza |
| (render ffmpeg) | aplica los keeps | — |
| `post_render_audit` | re-analiza el MP4 (silencios/sueltas/residuo) → score | — |
| deep audit | **re-transcribe el OUTPUT** y compara con lo esperado | — |
| coherence judge | gpt-5.4 juzga si el render tiene SENTIDO | — |
| `self_heal` | corrige los fallos del audit y re-renderiza | — |
| `false_start_output_sweep` | barre falsos inicios sobre el output | contenido |

**Clave del diseño** (`_CONTENT_CUT_SOURCES` = `stretched_filler, ai_holistic,
ai, ngram_repetition, ai_pass2`): las fuentes ACÚSTICAS solo deben cortar
SILENCIO; las de CONTENIDO son borrados deliberados de la IA. Las protecciones
distinguen ambas. **`ai_noise_gap`** es especial: la IA marcó una PAUSA (no un
borrado deliberado) → se trata como pausa, y si tragó una palabra hay que
rescatarla.

---

## 3. Casuística real (los bugs que ya pasaron — "jurisprudencia")

Cada uno con: SÍNTOMA → ROOT CAUSE → FIX. Si un fallo nuevo se parece, empieza
por aquí.

### 3.1 "Falta una palabra y hay un silencio donde iba" (caso proteína, buga_3)
- **Síntoma:** "los dos ingredientes [silencio ~0.5s] y crema de arroz" — falta
  "proteína", el cliente oye un hueco.
- **Root cause:** la clienta dice "Proteína." CLARA y FUERTE (-22dB) en una ISLA
  de voz aislada (silero `[10.4-11.6]`), rodeada de pausas. La IA marcó TODO el
  tramo `[8.3-12.16]` como UNA pausa (`ai_noise_gap`) y se tragó la palabra. El
  rescate de islas normal (`_preserve_speech_islands_in_cuts`) SE SALTA los
  noise_gap (para no resucitar tos/falsos-inicios) → la isla de voz buena se
  perdía. NO era timing mal calculado: era una palabra entera cortada.
- **Fix:** `_rescue_silero_islands_in_noise_gaps` — devuelve al keep las islas de
  voz silero que (1) silero marca voz, (2) NO están ya en keep, (3) caen dentro
  de un `ai_noise_gap`, (4) NO tocan content cut, (5) ≥0.30s, (6) energía ≥16dB
  sobre el suelo de silencio (descarta tos/ruido flojo). Verificado: salida pasó
  de "ingredientes [hueco] y crema" → "ingredientes proteína y crema de arroz".
- **Trampa que me costó:** perseguí DOS sitios equivocados antes (un mumble flojo
  en otro segundo que NO era la proteína buena). El cliente lo clavó: "coge los
  segundos equivocados". **Siempre localiza la palabra por silero+energía, no por
  Whisper.**

### 3.2 "El mismo vídeo a veces sale 100 y a veces 88" (over-cut no restaurado)
- **Síntoma:** coherencia baja a 88 con `coherence_fallos=1`; el render cortó una
  frase ("...la cesta amarilla y date prisa"→"la cesta prisa"; "20 euros"→"20").
- **Root cause:** el juez de coherencia DETECTABA el over-cut (con `restore_span`)
  pero `_derive_self_heal_actions` solo generaba la restauración para
  `type=="promised_item_cut"` e IGNORABA `dangling_ref`/`number_altered` → el
  self-heal no tenía acción → entregaba el over-cut.
- **Fix:** restaurar CUALQUIER defecto `fixable` con `restore_span` (el defecto ya
  pasó el filtro estricto del juez). La puerta MONÓTONA del self-heal descarta
  una restauración que no mejore. PRUEBA EN VIVO: buga_2 se cortó (88) → self-heal
  restauró 88→100. Sube el SUELO aunque la IA varíe.

### 3.3 "Falso inicio no cortado" (caso "y esto empezó", buga_1)
- **Síntoma:** "...android y esto empezó esto costaba 12 euros" — arranque
  abandonado + reinicio sobre palabra pivote ("esto"), no se cortaba.
- **Root cause:** no es n-grama (repite 1 palabra). Es trabajo de la pasada IA de
  falsos arranques, que se lo saltaba por borderline.
- **Fix:** Pattern 2b en `silence_cutter_false_starts.md` + lección + el
  **barrido final** (`false_start_output_sweep`) que corre sobre el transcript del
  OUTPUT renderizado (donde el detector SÍ los caza) y re-corta.

### 3.4 "Cierre seco / falta frase puente" (caso clienta_2 — FALSA ALARMA)
- **Síntoma percibido:** "...hasta el día 7 y píllate la tuya" suena cortado.
- **Realidad:** transcribí el audio input — la clienta dijo LITERAL eso, **no hay
  frase puente**. El editor fue fiel. **Lección meta: antes de "arreglar" un
  final raro, transcribe el INPUT y confirma que la frase existe.** No persigas
  fantasmas.

### 3.5 Palabra muy floja confundida con silencio
- **Síntoma:** una palabra dicha bajísima (-40dB, bajo el umbral de ruido -24dB)
  la cortan los detectores acústicos como si fuera silencio.
- **Pista:** silero (neuronal) SÍ la ve como voz aunque la amplitud no. Si
  silero dice voz y amplitude dice silencio → es voz floja, protégela.

---

## 4. PLAYBOOK: cómo diagnosticar una queja de edición

Cuando el cliente dice "en el segundo X falla Y", sigue ESTO (no adivines):

1. **Identifica el job** y lee su diagnóstico (ver §5 comandos). El campo
   `audit.deep.out_words` es **la re-transcripción del OUTPUT = lo que el
   espectador OYE**. Busca ahí la zona del problema.
2. **¿El output dura lo que crees?** (`audit.output_duration_s`). Si el cliente
   dice "segundo 67" pero el output dura 28s, probablemente quiso decir "6-7s".
   No depures el sitio equivocado (me pasó).
3. **Localiza la palabra/frase en el INPUT** transcribiendo solo esa ventana con
   `large-v3` (no te fíes del transcript guardado, que puede tener spans
   inflados). Confirma QUÉ se dijo y CUÁNDO de verdad.
4. **Mira la ENERGÍA** de esa ventana del input (RMS por 20ms) → distingue voz
   (alta) de silencio (baja ~-55dB) de voz floja (-40dB). Te dice el alcance
   acústico real de la palabra.
5. **Cruza con silero** (`phases.silero_vad.preview_speech`): ¿silero ve voz ahí?
   ¿En qué intervalo? Esa es la verdad de "hay voz".
6. **¿En qué keep cae?** (`final.preview_keep_intervals`). Si la palabra está
   FUERA de los keeps → la cortaron. Mira `final.cuts_by_source` y
   `phases.ai.raw_cuts` (con `reason`) para ver QUÉ fuente la cortó:
   - cortada por `noise_gap` (pausa IA) o acústico → candidata a rescate de isla.
   - cortada por `ai`/`ai_holistic`/`ngram`/`ai_pass2` → borrado deliberado;
     ¿correcto? Si no, es la pasada IA la que se equivocó (prompt/lección).
7. **Solo entonces** decide el fix: rescate de isla, protección de palabra,
   ajuste de prompt/lección, etc. Y recuerda §1: **verifica en varios runs**.

---

## 5. Cheatsheet de operaciones (servidor)

> Acceso: `ssh root@62.238.19.31`. App en contenedor `tiktok-api`. Diagnósticos
> en `/app/temp_work/editor_diagnostic_<job_id>.json` (dentro del contenedor).
> Repo de deploy: `/home/nebulabsai/TikTok_Automation_Python` (Docker). Repo del
> claude-remote: `/home/nebulabsai/proyectos/TikTok-Automation-Python` (¡son DOS
> copias distintas!).

**Leer el diagnóstico de un job:**
```bash
ssh root@62.238.19.31 'docker exec tiktok-api python3 -c "
import json; d=json.load(open(\"/app/temp_work/editor_diagnostic_<JOBID>.json\"))
a=d[\"audit\"]; print(\"score\",a.get(\"quality_score\"),\"coh\",a.get(\"coherence_score\"),\"requeue\",a.get(\"needs_requeue\"))
print(\"out_text:\", (a.get(\"deep\") or {}).get(\"out_text\",\"\")[:400])
print(\"phases:\", list(d[\"phases\"].keys()))
"'
```

**Transcribir una ventana del input (la verdad, no el transcript guardado):**
```bash
ssh root@62.238.19.31 'docker exec tiktok-api python3 -c "
import subprocess; from faster_whisper import WhisperModel
src=\"<RUTA_INPUT>\"  # diagnostic[\"input_path\"]
subprocess.run([\"ffmpeg\",\"-y\",\"-ss\",\"<INI>\",\"-i\",src,\"-t\",\"<DUR>\",\"-ar\",\"16000\",\"-ac\",\"1\",\"/tmp/x.wav\"],capture_output=True)
m=WhisperModel(\"large-v3\",device=\"cpu\",compute_type=\"int8\")
for s in m.transcribe(\"/tmp/x.wav\",language=\"es\",word_timestamps=True)[0]:
    for w in s.words: print(w.word, round(w.start+<INI>,2), round(w.end+<INI>,2))
"'
```

**Coste de un vídeo (cost_tracking en Redis Upstash, prefijo `tiktok_shop:`):**
clave `cost:job:<jobid>` → JSON con `total_usd` y `lines`. Índice mensual
`cost:index:editor_auto:YYYY-MM`. Coste normal ≈ **$0.05/vídeo** (máx ~$0.11).

**GOTCHAS de prueba/deploy (todos reales, todos muerden):**
- **Cola in-memory:** encolar por `docker exec` (proceso aparte) NO lo ve el
  worker vivo. Hay que reiniciar para que cargue del disco. Pero `docker restart`
  tras un exec-enqueue **PIERDE** los jobs (el shutdown dumpea la cola en memoria
  sobre el disco). Patrón fiable: exec-enqueue → `docker kill` (SIGKILL, sin
  dump) → `docker start` (carga del disco).
- **Contenedor fantasma:** `docker compose up --build` a veces da "name already
  in use" → `docker rm -f tiktok-api` y reintentar.
- **El diagnóstico se escribe PRONTO** (antes del render). No uses
  `test -f diagnostic` como "terminado": mira `status=completed` en la cola.
- **Hot-patch sin git** (si el commit/clasificador falla): `scp` el fichero →
  `docker cp` al contenedor → `docker restart`. OJO: un `compose up --build`
  posterior lo pisa (rebuild desde imagen). El deploy durable es git+rebuild.

---

## 6. Arquitectura de auto-corrección (el editor se revisa solo)

Esto es lo que hace que el editor "actúe como un humano que revisa su corte":

- **deep audit** (`_deep_audit_compare`): re-transcribe el OUTPUT y lo compara con
  lo esperado → detecta palabras perdidas (`missing_blocks`) y residuos
  (`inserted_blocks`). Muchos filtros anti-falso-positivo (varianza de Whisper).
- **coherence judge** (`_ai_coherence_judge`): gpt-5.4 juzga si el render TIENE
  SENTIDO comparado con el original. Da `restore_span` para lo que falta. Tiene
  pre-screen ($0 si el render sale limpio).
- **self-heal** (`_derive_self_heal_actions` + el loop): convierte los hallazgos
  en cortes/restauraciones, re-renderiza con ffmpeg (sin coste IA) y re-audita.
  **Monótono**: nunca entrega algo peor que el render base (`_qkey`).
- **rescate de islas** y **word_protection**: §2/§3.1.
- **`editor_lessons.md`**: lecciones que se INYECTAN a los prompts de IA por
  pasada (`clean_script`/`analyst`/`false_starts`/`completeness`). Aquí es donde
  el editor "APRENDE": cuando un caso nuevo falla, añade una lección corta y
  general (no detalle técnico — eso va a `learnings.md`).

---

## 7. Estado conocido / banderas (jun 2026)

- **`silero_edge_snap` DESACTIVADO** (`silero_edge_snap_enabled`=False): extendía
  bordes de keep a la voz silero, pero sin word-guard se disparaba en EXCESO en
  vídeos conversacionales (clienta_2: 24 bordes → micro-artefactos). El que SÍ
  está ON y es el fix bueno es el **rescate de ISLAS** (§3.1). Si lo reactivas,
  ponle un word-guard primero.
- **GAP de robustez: 429 / sin crédito OpenAI.** Si OpenAI se queda sin saldo a
  mitad de job, las pasadas IA fallan con 429 y el editor **degrada EN SILENCIO**
  a corte solo-acústico (vídeo roto, score 0, lleno de residuo) en vez de
  abortar/reencolar. Si ves un vídeo con score 0 + muchos `n_residue_islands` +
  `completeness_review.error: 429` → es ESTO, no un bug de corte. Fix pendiente:
  detectar 429 → abortar y reencolar + alerta de saldo.
- **Tarifa gpt-5.4 cableada a ojo** en `cost_tracking.py` ($1.25/$10 por 1M) con
  comentario "calibrar con /costs". Las cifras de coste tienen esa incertidumbre.
- **Producción en Whisper** (Deepgram evaluado, NO adoptado; flag
  `EDITOR_ASR_PROVIDER`).

---

## 8. Reglas al tocar el cortador

1. **Verifica en VARIOS runs** (es no-determinista). Un run no prueba nada.
2. **No regreses los vídeos que funcionan.** Diseña los fixes para ser **no-op**
   cuando no aplican (gates estrechos, solo-añade-keep, puerta monótona).
3. **Localiza contenido por silero+energía, nunca por timings de Whisper.**
4. **Antes de "arreglar" algo raro, transcribe el INPUT** y confirma qué se dijo
   de verdad (puede ser fiel y no haber bug).
5. Añade una línea a `learnings.md` (detalle) y, si es una regla de edición
   general, a `editor_lessons.md` (para que la IA aprenda).
6. La calidad del corte es el producto. No ahorres coste a costa de calidad.
