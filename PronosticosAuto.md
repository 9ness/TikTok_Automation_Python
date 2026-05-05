# PronosticosAuto — Generador de Videos TikTok Virales

> Briefing para agente de IA en proyecto **separado**. El proyecto principal `bet-ai-master` ya genera las predicciones, las imágenes de carrusel y el caption viral. Este nuevo proyecto convierte esos datos en un **vídeo MP4 vertical 9:16** narrado por IA, listo para subir a TikTok.

---

## 0. Por qué un proyecto separado

El proyecto principal corre en Next.js + Vercel y no puede ejecutar FFmpeg ni jobs largos. Aquí necesitamos:
- Python 3.10+
- FFmpeg local
- TTS local (motor IA de voz que el usuario ya tiene en otro proyecto — reutilizar la firma)
- Espacio en disco para clips de stock cacheados

Se ejecuta en local (o servidor con Cron) y deja el vídeo final como MP4 más una URL pública opcional en Redis para que la app/web lo muestre.

---

## 1. Objetivo

Generar **1 vídeo MP4 al día** (target: día siguiente) con estas características:

| Campo | Valor |
|---|---|
| Resolución | 1080×1920 (vertical 9:16) |
| Duración | 30–60 seg (target ~50 seg) |
| FPS | 30 |
| Vídeo codec | H.264 `yuv420p` |
| Audio codec | AAC 128 kbps |
| Contenedor | MP4 |
| Subtítulos | Quemados en vídeo (estilo TikTok bold) |

El vídeo presenta las **6 combinadas virales TikTok** del día siguiente (formato carrusel), con voz IA narrando + clips de stock + imágenes del carrusel intercaladas.

---

## 2. Fuente de datos: Redis (Upstash)

### Acceso

Solo necesitas dos variables de entorno:

```env
UPSTASH_REDIS_REST_URL=https://xxxxx.upstash.io
UPSTASH_REDIS_REST_TOKEN=AX...
```

Acceso por **HTTP REST**, no TCP. Cualquier wrapper sirve, ej:

```python
import os, requests
URL = os.environ["UPSTASH_REDIS_REST_URL"]
TOKEN = os.environ["UPSTASH_REDIS_REST_TOKEN"]

def redis_hget(key: str, field: str) -> str | None:
    r = requests.get(f"{URL}/hget/{key}/{field}",
                     headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10)
    r.raise_for_status()
    return r.json().get("result")
```

### Claves relevantes

| Key | Estructura | Contenido |
|---|---|---|
| `betai:daily_bets_tiktok_video:YYYY-MM` | Hash, field `YYYY-MM-DD` | **🎬 Guion de video (LO QUE TÚ LEES)** — payload con `mode` que dispara una shape u otra |
| `betai:daily_bets_tiktok:YYYY-MM` | Hash, field `YYYY-MM-DD` | 6 combinadas virales del CARRUSEL (no para video, contiene prosa larga) |
| `betai:tiktokfactory_tomorrow` | String JSON | Caption/title generado para descripción TikTok (≤4000 chars) |
| `betai:daily_bets:YYYY-MM` | Hash, field `YYYY-MM-DD` | Pronósticos SAFE/VALUE/FUNBET (extra opcional, no usado por el video) |

**IMPORTANTE:** lee de `daily_bets_tiktok_video`, NO de `daily_bets_tiktok`. La key `_video` la pobla un workflow separado (`tiktok_video_script.yml`) que dispara automáticamente tras el carrusel y reescribe el `reason` en formato adecuado para TTS.

**Cómo se genera el guion (referencia para el agente):**
- El proyecto principal usa OpenAI `gpt-5.4` con un prompt específico (`backend/system_prompt_tiktok_video_single.txt` para deep-dive de Champions, `backend/system_prompt_tiktok_video.txt` para el modo multi).
- Para el modo `single_match` se hacen ~6 llamadas a API-Sports antes de invocar el modelo, para meter datos verificables (clasificación, top scorer del torneo, stats de temporada, lesionados) directamente en el input del prompt. El modelo no inventa cifras.
- El script ya viene listo para TTS: cifras escritas en letras (`"doce goles"`, `"dos a uno"`), una sola línea, sin markdown.

> **Importante:** todas las keys llevan prefijo `betai:`. El proyecto principal usa `REDIS_PREFIX=betai:`. Cuando llames REST con HGET, usa el path completo `betai:daily_bets_tiktok:2026-04`.

### Schema del valor en `daily_bets_tiktok_video`

**ESTRUCTURA NUEVA — lista de versiones:** el payload del día no es UNA sola versión sino un **array `versions[]`** con todas las generadas (cron + manuales) y un campo `selected_version_id` que indica cuál usar.

```jsonc
{
  "date": "2026-04-30",
  "is_real": true,
  "updated_at": "2026-04-29T19:42:13",
  "selected_version_id": "2",     // ← TÚ LEES ESTA VERSIÓN para el video del día
  "versions": [
    {
      "id": "1",
      "trigger": "cron",          // generada por el cron de las 18:00
      "generated_at": "2026-04-29T18:05:12",
      "mode": "multi_match",
      "title": "...",
      "script": "...",
      "word_count": 268,
      "estimated_duration_s": 84,
      // ...resto de campos según mode (ver abajo)
    },
    {
      "id": "2",
      "trigger": "manual",        // el admin pulsó "Generar nueva versión"
      "generated_at": "2026-04-29T19:38:42",
      "mode": "multi_match",
      "title": "...",
      "script": "...",
      "word_count": 295,
      "estimated_duration_s": 92,
      // ...
    }
  ]
}
```

**Cómo lo consumes (el agente del video):**

```python
import json, requests, os

def load_video_payload(target_date):
    URL   = os.environ["UPSTASH_REDIS_REST_URL"]
    TOKEN = os.environ["UPSTASH_REDIS_REST_TOKEN"]
    month = target_date[:7]
    r = requests.get(
        f"{URL}/hget/betai:daily_bets_tiktok_video:{month}/{target_date}",
        headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10,
    )
    raw = r.json().get("result")
    if not raw: return None
    data = json.loads(raw) if isinstance(raw, str) else raw
    versions = data.get("versions") or []
    selected_id = data.get("selected_version_id")
    # Encuentra la versión seleccionada (la que el admin marcó con ⭐)
    chosen = next((v for v in versions if v["id"] == selected_id), None)
    if not chosen and versions:
        chosen = versions[-1]  # fallback: la última generada
    return chosen
```

**Reglas para el agente:**
1. Lee `selected_version_id` y busca esa entry en `versions[]`. Si no existe, usa la última de `versions[]`.
2. Una vez tengas `chosen`, sus campos siguen el schema clásico (mode, script, title, word_count, etc.) — el resto de la documentación aplica igual a `chosen`.
3. NUNCA uses `versions[0]` ciegamente — el admin puede haber marcado v2 o v3 como definitiva tras revisar.
4. **Compatibilidad hacia atrás**: si por algún motivo el payload no trae `versions` (formato antiguo), lee los campos del nivel raíz directamente. La API de admin ya migra al vuelo, pero el agente robusto debe tolerar ambos formatos.

```python
# Versión robusta que tolera ambos formatos
def load_chosen_version(target_date):
    data = load_redis(...)
    if data and isinstance(data.get("versions"), list) and data["versions"]:
        sel_id = data.get("selected_version_id")
        return next((v for v in data["versions"] if v["id"] == sel_id), data["versions"][-1])
    # Formato antiguo (legacy): el propio payload ES la versión
    return data
```

#### Detalle de cada `version` según `mode`

(El resto de la documentación describe los campos de UNA `version`. La estructura interna no cambia: solo está envuelta en `versions[]`.)

#### Modo `single_match` (Champions League o liga prioritaria)

Cuando alguno de los 3 partidos top del carrusel es de Champions League, el flujo entra en **deep dive** sobre ese partido único, generando un guion completo de 250-290 palabras (~65-80 seg de narración) con la estructura viral comprobada (hook con dinero → 4 picks intercalados con CTA midroll → killer pick final).

Cada entry en `versions[]` con `mode: "single_match"` tiene esta forma:

```jsonc
{
  "id": "1",
  "trigger": "cron",
  "generated_at": "2026-04-27T18:05:00",
  "mode": "single_match",
  "focus_match": "EL RADAR DE ALTA PRECISIÓN",   // título gancho del carrusel
  "focus_selections": [
    {
      "fixture_id": 1234567,
      "sport": "football",
      "league": "UEFA Champions League",
      "country": "Europe",
      "match": "PSG vs Bayern Múnich",
      "home_id": 85, "home_logo": "https://…/85.png",
      "away_id": 157, "away_logo": "https://…/157.png",
      "time": "21:00",
      "pick": "Ambos marcan",
      "odd": 1.45
    }
    // 3 selecciones del partido prioritario
  ],
  "total_odd": 1.95,
  "title": "Diez mil con la semifinal de Champions PSG vs Bayern",  // título corto para TTS o overlay
  "script": "Diez mil es lo que nos vamos a llevar este martes en la semifinal de Champions… [guion completo, una sola línea, números en letras para TTS]",
  "word_count": 268,
  "estimated_duration_s": 70.9
}
```

### 🎯 Picks entre paréntesis — extracción del texto exacto

**Garantizado por el sistema (no por el modelo):** el `script` lleva cada pick envuelto en `(...)` mediante post-proceso DETERMINISTA en el backend de bet-ai-master. Cada paréntesis cubre el texto LITERAL del pick, mismo case y misma puntuación que aparece narrado. Esto te permite:

1. Extraer el texto exacto de cada pick para resaltarlo en pantalla
2. Sincronizarlo con `word_timings` del TTS para saber CUÁNDO se narra
3. Renderizar overlay con color/efecto distinto durante esa ventana temporal

**Receta completa:**

```python
import re
PICK_RE = re.compile(r"\(([^()]+)\)")

# 1. Extrae picks (texto literal tal cual aparece en el script)
picks = PICK_RE.findall(script)
# Ejemplo: ["más de seis disparos a puerta", "ambos anotan", "Atlético no pierde", ...]

# 2. Limpia paréntesis del script para pasarlo al TTS
clean_script = PICK_RE.sub(lambda m: m.group(1), script)

# 3. TTS → audio + word_timings sobre clean_script
audio, word_timings = tts.synthesize(clean_script, return_timings=True)
# word_timings = [{word: "Empezamos", start: 0.1, end: 0.5}, ...]

# 4. Para cada pick, busca su ventana temporal exacta
def find_pick_window(pick_text, words, start_from=0):
    """Devuelve (start_s, end_s, next_cursor) del pick en el array de words."""
    pt = [w.lower().strip(".,;:") for w in pick_text.split()]
    for i in range(start_from, len(words) - len(pt) + 1):
        seq = [words[i+j]["word"].lower().strip(".,;:") for j in range(len(pt))]
        if seq == pt:
            return words[i]["start"], words[i+len(pt)-1]["end"], i + len(pt)
    return None, None, start_from

# 5. Calcula ventanas para todos los picks (cursor avanza para no matchear repes)
cursor = 0
pick_windows = []  # [(pick_text, start_s, end_s)]
for pick in picks:
    start, end, cursor = find_pick_window(pick, word_timings, cursor)
    if start is not None:
        pick_windows.append((pick, start, end))

# 6. Renderiza overlay/subtítulo con color destacado durante cada ventana
for pick_text, start_s, end_s in pick_windows:
    add_overlay_to_video(text=pick_text, start=start_s, end=end_s,
                         style={"color": "#FFD700", "bold": True, "font_size": 80})
```

**Garantías del sistema:**
- El texto dentro de `()` es **substring literal** del script (mismo case, misma puntuación, sin transformaciones).
- El número de paréntesis `==` número de picks en `selected_picks` (multi) o `focus_selections` (single). Si hay menos, el log del backend ya lo marcó como warning.
- El `i`-ésimo pick en `PICK_RE.findall(script)` corresponde 1-a-1 con `selected_picks[i]` (multi) o `focus_selections[i]` (single). Útil para asociar la cuota individual o el icono al overlay.

**Cómo usar este modo:**
1. **Audio**: pasa `clean_script` al TTS. Cifras en letras (`"doce goles"`, `"dos a uno"`) para pronunciación correcta.
2. **Subtítulos**: si usas Whisper sobre el audio del TTS, ya te da word-level timing. El guion al ser una sola línea no rompe nada.
3. **CTA midroll**: el guion incluye textualmente la frase `"el linkcito de mi perfil"`. Si quieres mantenerlo o sustituirlo, busca esa frase y reemplaza con tu CTA real.
4. **Visual frames**: usa `focus_selections` para construir la imagen del carrusel del partido (logos en `home_logo`/`away_logo`). Mantén la imagen a 1080×1920 con los 3 picks como ya hace el bet-ai-master.
5. **Validaciones del lado del proyecto principal** (estos avisos llegan a logs si el modelo se desvía, pero el payload se guarda igual):
   - `script` debe tener entre 250 y 310 palabras
   - Debe contener las 4 transiciones literales: "Arrancamos con", "Seguimos con", "Vamos con", "Por último"
   - Debe contener la frase del CTA "linkcito de mi perfil"
   - No debe contener vocabulario prohibido (lista en `analyze_tiktok.py:REASON_BANNED_WORDS`)

**Datos extra disponibles si quieres mostrar overlays con stats (overlay de banderas, posición en tabla, top scorer, etc.):** el proyecto principal pre-calcula estos datos vía API-Sports y se podrían exponer en una key adicional si los necesitas. Ahora mismo NO se exponen (solo el `script` y `focus_selections`). Si los necesitas, abre issue en bet-ai-master para añadir `focus_match_data` con el bloque `api_stats` del enricher.

#### Modo `multi_match` (día normal — sin partido único de Champions)

Cuando ningún partido del top 3 del carrusel es Champions, el flujo elige **3, 4 o 5 picks SUELTOS** de partidos distintos (no son combinadas, son apuestas individuales) y prioriza ligas top europeas, pero adapta el formato según lo que ofrezca el día:

- **3 picks** (~220-260 palabras, ~70-80s) — días con pocos partidos top, jornadas Liga MX, ligas Tier 3.
- **4 picks** (~260-300 palabras, ~80-90s) — días intermedios.
- **5 picks** (~290-320 palabras, ~90-100s) — miércoles europeos cargados, fines de semana grandes.

El modelo decide el count según la calidad del pool — mejor 3 picks fuertes que 5 mediocres.

Cada entry en `versions[]` con `mode: "multi_match"` tiene esta forma:

```jsonc
{
  "id": "1",
  "trigger": "cron",
  "generated_at": "2026-04-27T18:05:00",
  "mode": "multi_match",
  "title": "Cuatro mil quinientos con las ligas europeas del miércoles",
  "stake_amount": "cuatro mil quinientos",  // cantidad en letras para el hook (TTS-friendly)
  "selected_picks": [
    {
      "match": "Manchester City vs Burnley",
      "league": "Premier League",
      "pick": "+5.5 disparos a puerta City",
      "fixture_id": 1234567
    },
    {
      "match": "Barcelona vs Celta",
      "league": "La Liga",
      "pick": "+5.5 disparos a puerta Barcelona",
      "fixture_id": 1234568
    }
    // … 4 o 5 picks de partidos distintos
  ],
  "script": "Cuatro mil quinientos es lo que nos vamos a llevar este miércoles con las ligas europeas. Empezamos con City más de seis disparos a puerta. […] Si quieres ganar viendo ligas europeas, asegúrate de unirte al grupo en el linkcito de mi perfil […] Por último, ambos anotan en Leverkusen-Bayern. Bayern lleva siete victorias consecutivas […]",
  "word_count": 290,
  "estimated_duration_s": 90.6
}
```

**Cómo usar este modo:** mismo flujo que `single_match`:
1. Pasa `script` al TTS.
2. Para visuales, usa `selected_picks` (3-5 entries) para construir las imágenes carrusel (una por pick) con logos del bet-ai-master + texto del pick.
3. **Estructura del script según pick count** — divide por las transiciones obligatorias para timeline preciso:

   **3 picks (formato Liga MX):**
   - `"Empezamos con"` → entrada Pick 1
   - `"Seguimos con"` → entrada Pick 2
   - `"linkcito de mi perfil"` → fin del bloque CTA
   - `"Vamos con"` → entrada Pick 3 (cierre, sin "Por último")

   **4 picks:**
   - `"Empezamos con"` → entrada Pick 1
   - `"Seguimos con"` → entrada Pick 2
   - `"Vamos con"` → entrada Pick 3 (anclaje)
   - `"linkcito de mi perfil"` → fin del bloque CTA
   - `"Por último"` → entrada Pick 4

   **5 picks (formato máximo, día europeo cargado):**
   - `"Empezamos con"` → entrada Pick 1
   - `"Seguimos con"` (1ª aparición) → entrada Pick 2
   - `"Vamos con"` → entrada Pick 3 (anclaje)
   - `"linkcito de mi perfil"` → fin del bloque CTA
   - `"Seguimos con"` (2ª aparición) → entrada Pick 4
   - `"Por último"` → entrada Pick 5

**Validaciones que debe pasar el script** (avisos a logs si fallan, payload se guarda igual):
- Word count en rango (220-260 / 260-300 / 290-320 según count)
- Frase `"linkcito de mi perfil"` literal en el midroll
- Transiciones literales según count (con/sin "Por último")
- `selected_picks` con 3-5 entries, todas de partidos distintos **excepto** cuando el payload trae `competition_focus` — en ese caso se permite hasta 3 picks por mismo match (ver sub-caso abajo).

##### Sub-caso: `competition_focus` (días de Europa/Conference League con pocos partidos)

Cuando el día tiene 2+ partidos de competición premium europea (Champions/Europa/Conference) pero **no hay 1 deep-dive obvio**, el flujo restringe el guion a **EXCLUSIVAMENTE esos partidos** y permite repetir match para llegar al mínimo de palabras. El payload trae 2 campos extra:

- `competition_focus: "UEFA Europa League"` (o "Conference League", etc.) — el tema del hook y CTA viene fijado.
- En el hook se ve `"con la Europa League"` en vez de `"con las ligas europeas"` genérico.

Ejemplo concreto (jueves de Europa League con sólo 2 partidos disponibles):

```jsonc
{
  "date": "2026-04-30",
  "mode": "multi_match",
  "competition_focus": "UEFA Europa League",
  "is_real": true,
  "generated_at": "2026-04-29T18:05:00",
  "title": "Cuatro mil con la Europa League del jueves",
  "stake_amount": "cuatro mil",
  "selected_picks": [
    { "match": "PSG vs Tottenham", "league": "UEFA Europa League", "pick": "+1.5 goles", "fixture_id": 1234567 },
    { "match": "PSG vs Tottenham", "league": "UEFA Europa League", "pick": "Ambos Marcan", "fixture_id": 1234567 },
    { "match": "Roma vs Leverkusen", "league": "UEFA Europa League", "pick": "Victoria Roma", "fixture_id": 1234568 },
    { "match": "Roma vs Leverkusen", "league": "UEFA Europa League", "pick": "+3.5 goles totales", "fixture_id": 1234568 }
  ],
  "script": "Cuatro mil nos llevaremos este jueves con la Europa League. Empezamos con […] Si quieres ganar viendo la Europa League, asegúrate de unirte al grupo en el linkcito de mi perfil […] Por último, más de tres goles totales en Roma-Leverkusen.",
  "word_count": 245,
  "estimated_duration_s": 76.6
}
```

**Cómo lo distingues**: presencia del campo `competition_focus`. Si está, el agente del video sabe que TODAS las imágenes carrusel deben ser de la misma competición, los logos/banderas pueden incluir el escudo de la competición (UEFA Europa League logo), y el flujo narrativo está cerrado al pool premium.

#### Detalle del modo: cómo elegimos `single` vs `multi`

Detección sobre **TODAS las combinadas del carrusel** (no sólo top 3) para no perder partidos premium en posiciones bajas.

```
PREMIUM_LEAGUES = Champions League / Europa League / Conference League
                  (más adelante: finales de copa nacional)

• 1 match premium  → mode = single_match  (deep-dive de ese match, ~270 palabras)
• 2+ matches premium  → mode = multi_match
                        candidates = SOLO los matches premium
                        competition_focus = nombre de la competición
                        allow_match_repetition = true
                        (el guion se centra exclusivamente en esos matches)
• 0 matches premium  → mode = multi_match clásico
                       candidates = top 3 carrusel
                       prioriza ligas top europeas, fallback Liga MX
```

Cuando el payload Redis tiene el campo `competition_focus`, significa que el día tenía competición europea premium y el guion está restringido a ella. Ejemplos:

- Día con **2 partidos de Europa League** → `mode: multi_match`, `competition_focus: "Europa League"`, 4 picks (2 por match), tema del hook = "Europa League"
- Día con **1 partido de Champions** → `mode: single_match`, `competition: "UEFA Champions League"`, 4 picks del mismo match
- Día con **3 partidos de Conference + 0 champions** → `mode: multi_match`, `competition_focus: "Conference League"`, 3-4 picks (1-2 por match)
- Día normal (Premier + LaLiga + Bundesliga, sin Europa) → `mode: multi_match` clásico, sin `competition_focus`

**Prioridad de ligas en modo multi_match:**

| Tier | Ligas | Trato |
|---|---|---|
| 1 (preferente) | Premier, La Liga, Bundesliga, Serie A, Ligue 1, Champions, Europa League | Siempre se eligen primero |
| 2 (válido) | Eredivisie, Liga Portugal, Scottish Premiership, MLS finales, Conference League | Solo si no hay suficiente Tier 1 |
| 3 (último) | Liga MX, Brasileirão, Argentina Primera, Saudi Pro League | Fallback. Si hay derbi famoso, sube a Tier 1 |

Si quieres añadir más ligas a la prioridad de single_match (ej: Copa del Rey final, derbis), edita la lista `PRIORITY_LEAGUES_FOR_SINGLE` en `backend/src/services/analyze_tiktok_video.py`. La prioridad de multi_match está en el prompt `system_prompt_tiktok_video.txt` (sección "PRIORIDAD POR PRESTIGIO DE LIGA").

#### Datos enriquecidos de API-Sports (ambos modos)

Antes de invocar al modelo, el flujo hace ~6 llamadas por partido a API-Sports para tener datos verificables (cacheado por liga para deduplicar):

| Endpoint | Saca | Uso típico en script |
|---|---|---|
| `/standings` | `rank`, `points`, `form` "WWDLW" | "París es segundo de su grupo con 12 puntos" |
| `/players/topscorers` | `name`, `goals`, `appearances` | "Kane lleva doce goles en once partidos" |
| `/teams/statistics` | `goals_for_avg`, `clean_sheets` | "marca tres goles por partido en promedio" |
| `/injuries` | lista de lesionados con `reason` | "llega con cuatro bajas: Davies, Kim..." |

Esto evita que el modelo invente cifras. Si una llamada API falla, simplemente omite ese dato y el modelo cuenta solo con lo que sí está disponible.

---

## 3. Pipeline de generación

```
[Redis: daily_bets_tiktok_video] → [TTS] → [Stock Search] → [Carousel Renderer] → [FFmpeg Composer] → MP4
```

### 3.1. Script — YA VIENE HECHO en Redis

**No construyes el guion**. El proyecto principal `bet-ai-master` ejecuta cada día tras el carrusel un workflow (`tiktok_video_script.yml`) que:

1. Lee las 6 combinadas del carrusel desde `daily_bets_tiktok:YYYY-MM`.
2. Detecta el modo (`single_match` / `multi_match` con o sin `competition_focus`).
3. Llama a OpenAI `gpt-5.4` con un prompt entrenado al formato viral de TikTok (>4M views como referencia).
4. Aplica enriquecimiento previo con API-Sports (standings, top scorers, lesionados — ver sección 2).
5. Persiste el guion completo en `daily_bets_tiktok_video:YYYY-MM` campo `YYYY-MM-DD`.

**Tu trabajo aquí**: leer el campo `script` del payload y pasarlo directo al TTS. Las cifras vienen ya en letras (`"doce goles"`, `"dos a uno"`) para que el TTS las pronuncie bien, las transiciones obligatorias (`"Empezamos con"`, `"Vamos con"`, `"Por último"`) están en su sitio, y el CTA midroll con el `"linkcito de mi perfil"` ya viene insertado.

```python
import requests, os
URL   = os.environ["UPSTASH_REDIS_REST_URL"]
TOKEN = os.environ["UPSTASH_REDIS_REST_TOKEN"]
target_date = "2026-04-30"
month = target_date[:7]

r = requests.get(
    f"{URL}/hget/betai:daily_bets_tiktok_video:{month}/{target_date}",
    headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10,
)
payload = r.json().get("result")
import json
data = json.loads(payload) if isinstance(payload, str) else payload

script   = data["script"]            # texto listo para TTS
mode     = data["mode"]              # "single_match" | "multi_match"
picks    = data.get("selected_picks") or data.get("focus_selections") or []
duration = data.get("estimated_duration_s")
```

Si el guion no está aún (ejecutaste antes de las 18:05 hora Madrid), el HGET devolverá `null`. Reintenta más tarde o muestra "guion no listo".

### 3.2. TTS — generación de voz

Usa el motor que ya tienes en el otro proyecto. Idealmente con **word-level timestamps** para los subtítulos. Si tu TTS lo soporta:

```python
audio_path, word_timings = tts.synthesize(
    text=script,                     # el script viene de Redis (sec 3.1)
    voice="es-ES-MasterPicksVoice",
    return_timings=True,
)
# word_timings = [{"word": "Empezamos", "start": 5.2, "end": 5.6}, ...]
```

Si no soporta timings, usa `whisper` (local, modelo `small` es suficiente) sobre el audio generado para obtenerlos.

### 3.3. Carousel Renderer — replicar las imágenes del TikTok Factory

El proyecto principal renderiza imágenes con `html2canvas` en cliente. **Aquí no podemos usar eso** (no hay navegador). Replícalo con **Pillow**:

Layout por imagen (1080×1920):

```
┌─────────────────────────┐
│   [imagen fondo de equipo │ ← background con jugador/estadio
│    a pantalla completa]  │
│                          │
│   ┌─────────────────┐    │
│   │ EQUIPO A vs B   │    │ ← caja blanca con título partido
│   └─────────────────┘    │
│                          │
│   ┌─────────────────┐    │
│   │ ⚽ +2.5 goles    │    │ ← caja oscura con 3 picks
│   │ 🟨 +3.5 tarjetas │    │   con icono según tipo de pick
│   │ ⛳ +8.5 córners  │    │
│   └─────────────────┘    │
│       ┌──────────┐       │
│       │ +1.95    │       │ ← cuota total
│       └──────────┘       │
└─────────────────────────┘
```

**Mapeo de iconos por tipo de pick** (replicar del componente principal):

| Substring en `pick.lower()` | Emoji |
|---|---|
| `goles`, `gol`, `marcan` | ⚽ |
| `córners`, `corners` | ⛳ |
| `tarjetas` | 🟨 |
| `remates`, `tiros` (totales) | 🥅 |
| `remates`, `tiros` (a puerta) | 🎯 |
| `puntos` (basket) | 🏀 |
| `victoria`, equipo mencionado | ✅ |
| `hándicap`, `o empate` | 📌 |

**Bandera del país de la liga**: usa el helper que ya está en el proyecto principal en [`frontend/utils/flags.ts`](bet-ai-master/frontend/utils/flags.ts) (port a Python). Te da código ISO; descarga la imagen de `https://flagcdn.com/w160/{code}.png` y la pegas a la izquierda del título.

### 3.4. Stock Search — clips de fondo libres de derechos

**Honestidad importante**: highlights reales de equipos NO existen sin copyright. Usa stock genérico.

APIs gratis con licencia comercial:

```python
PEXELS_API_KEY  = os.environ["PEXELS_API_KEY"]   # https://www.pexels.com/api/
PIXABAY_API_KEY = os.environ["PIXABAY_API_KEY"]  # https://pixabay.com/api/docs/

def search_stock_clip(league: str, sport: str, country: str) -> str:
    """
    Busca un clip vertical (orientation=portrait) de fútbol genérico.
    NUNCA busques por nombre de equipo o jugador — desperdicia cuota.
    Estrategia: queries de más específica a más genérica + cache por league.
    """
    queries = [
        f"{league} stadium",
        f"{country} football crowd",
        "soccer goal celebration slow motion",
        "stadium lights night",
        "football fans cheering",
        "soccer ball field",
    ]
    cache_dir = Path(f"cache/clips/{slugify(league)}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = list(cache_dir.glob("*.mp4"))
    if len(cached) >= 3:
        return str(random.choice(cached))

    for q in queries:
        clip_url = pexels_search(q, orientation="portrait", per_page=15)
        if clip_url:
            local = cache_dir / f"{hashlib.md5(clip_url.encode()).hexdigest()[:10]}.mp4"
            download(clip_url, local)
            return str(local)

    return pexels_search("football", orientation="portrait")[0]
```

**Plan de caché:** ~5 clips por liga × 50 ligas activas ≈ 250 clips. ~1.5 GB en disco. Refresca cada 30 días.

### 3.5. FFmpeg Composer — montaje final

#### Asset clave: `perfil.png` (overlay del CTA midroll)

Cuando la narración pronuncia la frase **"el linkcito de mi perfil"**, en pantalla se muestra una **captura del perfil de TikTok** del canal (la pantalla que el espectador tiene que abrir para suscribirse). Este momento es crítico para conversión.

- **Archivo**: `BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/perfil.png`
  - El usuario lo mantiene en su biblioteca local de assets junto a las carpetas de clips por equipo (`Atletico_madrid/`, `fc_barcelona/`, `intro/`, etc.).
  - Si vas a clonar la estructura, replica `assets/fotos/perfil.png` en tu proyecto.
- **Cuándo mostrarlo**: localiza el inicio del CTA en `word_timings` (busca el primer match de la palabra `"Si"` o `"asegúrate"` cercana a `"linkcito"`, o más fácil — busca `"linkcito"` directo en los timings y ancla 1-2 segundos antes).
- **Duración**: dura todo el bloque CTA — desde justo antes de "Si quieres ganar viendo…" hasta justo después de "…todos los días", aproximadamente 5-7 segundos.
- **Encuadre**: la imagen está en formato vertical (capture del móvil) o cuadrado. Renderízala a 1080×1920 con `scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black` para mantener la captura completa con padding.

```python
# Detecta el inicio y final del CTA en los word_timings
def find_cta_window(word_timings):
    """Devuelve (start_s, end_s) del bloque CTA midroll, o None si no se halla."""
    cta_start = None
    cta_end = None
    for i, w in enumerate(word_timings):
        if w["word"].lower().startswith("linkcito"):
            # backtrack hasta encontrar "Si" (~6-8 palabras antes)
            cta_start = max(0, i - 8)
            # forward hasta el final de la frase (≈ 12 palabras después)
            cta_end = min(len(word_timings) - 1, i + 12)
            break
    if cta_start is None:
        return None
    return word_timings[cta_start]["start"], word_timings[cta_end]["end"]
```

```bash
# Genera el segmento de perfil para inyectar en la concat list
ffmpeg -y -loop 1 -i assets/fotos/perfil.png \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,fps=30" \
  -t 6 -c:v libx264 -preset fast -pix_fmt yuv420p -an \
  norm/seg_cta_perfil.mp4
```

Si por lo que sea no tienes el archivo `perfil.png` (primer arranque, archivo movido…), cae al stock de "stadium lights" del último pick para que el video se monte igual y avisa por log. NUNCA falla por falta de este asset.

#### Concat protocol estándar

Por simplicidad y robustez, usa el **concat protocol** con clips ya normalizados al mismo formato:

**Paso 1 — Normalizar cada segmento a 1080×1920, 30fps, H.264:**

```bash
ffmpeg -y -i input.mp4 \
  -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" \
  -t 5 \
  -c:v libx264 -preset fast -pix_fmt yuv420p \
  -an \
  norm/seg_001.mp4
```

Para imágenes (carrusel renderizado), conviértelas a clip de 2-3 seg con Ken Burns:

```bash
ffmpeg -y -loop 1 -i carousel_001.png \
  -vf "scale=1200:2200,zoompan=z='min(zoom+0.0008,1.15)':d=90:s=1080x1920,fps=30" \
  -t 3 -c:v libx264 -preset fast -pix_fmt yuv420p -an \
  norm/seg_001_kb.mp4
```

**Paso 2 — Concatenar todos los segmentos:**

Crea `concat_list.txt` insertando el clip del perfil en el momento del CTA:
```
file 'norm/seg_intro.mp4'
file 'norm/seg_001_kb.mp4'        # carrusel pick 1
file 'norm/seg_001_stock.mp4'     # stock equipo pick 1
file 'norm/seg_002_kb.mp4'        # carrusel pick 2
file 'norm/seg_002_stock.mp4'
file 'norm/seg_003_kb.mp4'        # carrusel pick 3 (anclaje pre-CTA)
file 'norm/seg_cta_perfil.mp4'    # ← captura perfil mientras se narra "linkcito de mi perfil"
file 'norm/seg_004_kb.mp4'        # carrusel pick 4 post-CTA
file 'norm/seg_004_stock.mp4'
file 'norm/seg_005_kb.mp4'        # último pick (si hay 5)
file 'norm/seg_outro.mp4'
```

```bash
ffmpeg -y -f concat -safe 0 -i concat_list.txt -c copy concat.mp4
```

**Paso 3 — Mezclar con voz TTS:**

```bash
ffmpeg -y -i concat.mp4 -i voice.mp3 \
  -map 0:v -map 1:a \
  -c:v copy -c:a aac -b:a 128k \
  -shortest \
  with_voice.mp4
```

**Paso 4 — Quemar subtítulos (genera `.srt` desde word_timings):**

```bash
ffmpeg -y -i with_voice.mp4 \
  -vf "subtitles=script.srt:force_style='FontName=Inter,FontSize=20,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=2,BackColour=&H80000000,Alignment=2,MarginV=180'" \
  -c:a copy \
  out/YYYY-MM-DD_viral.mp4
```

**Generación del SRT** desde word_timings:

```python
def words_to_srt(words: list[dict], words_per_line: int = 3) -> str:
    lines = []
    for i in range(0, len(words), words_per_line):
        chunk = words[i:i+words_per_line]
        start = chunk[0]["start"]
        end = chunk[-1]["end"]
        text = " ".join(w["word"] for w in chunk)
        lines.append(f"{i//words_per_line + 1}\n{ts(start)} --> {ts(end)}\n{text}\n")
    return "\n".join(lines)
```

---

## 4. Estructura del proyecto

```
PronosticosAuto/
├── main.py                       # entry: lee args (--date YYYY-MM-DD) y orquesta
├── requirements.txt              # requests, Pillow, ffmpeg-python, openai (o tu TTS), python-dotenv
├── .env.local                    # secrets (no commitear)
├── .gitignore                    # cache/, out/, .env*
│
├── src/
│   ├── __init__.py
│   ├── redis_client.py           # Upstash REST GET/HGET wrapper
│   ├── data_loader.py            # lee daily_bets_tiktok_video y valida schema
│   ├── tts.py                    # síntesis voz + word_timings (reusa motor existente)
│   ├── cta_locator.py            # detecta ventana del CTA con "linkcito" en word_timings
│   ├── carousel_renderer.py      # Pillow: selected_picks → PNGs (uno por pick)
│   ├── stock_search.py           # Pexels + Pixabay con cache local
│   ├── ffmpeg_runner.py          # wrapper subprocess + logging
│   ├── video_composer.py         # orquesta normalize → concat → mux → subs
│   ├── subtitle_burner.py        # word_timings → .srt
│   └── flags.py                  # port del helper getLeagueFlagCode (ver bet-ai-master)
│
├── assets/
│   ├── fonts/Inter-Bold.ttf
│   ├── fonts/Inter-Regular.ttf
│   ├── fotos/
│   │   └── perfil.png            # ← captura del perfil TikTok que se muestra
│   │                             #   durante la narración del CTA "linkcito de mi perfil"
│   │                             #   (origen: TIKTOK_ASSETS/BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/)
│   └── intro_outro/              # bumpers fijos (logo, CTA)
│
├── cache/
│   ├── clips/                    # stock Pexels/Pixabay cacheado por league
│   ├── flags/                    # PNG de banderas
│   └── carousels/                # imágenes generadas (re-utilizables si re-run)
│
└── out/
    └── YYYY-MM-DD_viral.mp4      # output final
```

---

## 5. Variables de entorno (.env.local)

```env
# Redis (compartido con bet-ai-master)
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...

# Stock APIs
PEXELS_API_KEY=...
PIXABAY_API_KEY=...

# TTS (lo que uses)
TTS_API_KEY=...
TTS_VOICE_ID=es-ES-MasterPicksVoice

# Output
OUTPUT_DIR=out
CACHE_DIR=cache

# Opcional: subir vídeo final a Vercel Blob y dejar URL en Redis
VERCEL_BLOB_TOKEN=...
PUBLISH_TO_REDIS=true   # si true, escribe betai:tiktokfactory_video_tomorrow
```

---

## 6. Schedule (cron)

**Cadena del proyecto principal `bet-ai-master`:**

```
18:00 Madrid  →  3º TikTok Viral Automated (carrusel, escribe daily_bets_tiktok)
              →  4º TikTok Video Script Generator (workflow_run trigger)
                 escribe daily_bets_tiktok_video_VIDEO entre las 18:01 y 18:05
```

A partir de las 18:10 hora Madrid, la key `daily_bets_tiktok_video:YYYY-MM` ya tiene el guion del día siguiente listo. Para más seguridad, lee a partir de las 19:00.

**Recomendación cron del agente PronosticosAuto:**

```cron
# Generar vídeo cada día a las 19:00 hora Madrid (tras el chain del proyecto principal)
0 19 * * * cd /path/PronosticosAuto && python main.py --date $(date -d 'tomorrow' +%Y-%m-%d) >> logs/run.log 2>&1
```

O con GitHub Actions:

```yaml
on:
  schedule:
    - cron: '0 18 * * *'  # 19:00 Europe/Madrid en invierno (CET = UTC+1)
                          # 20:00 Europe/Madrid en verano (CEST = UTC+2)
```

---

## 7. Reglas operativas

### NO hacer

- ❌ Buscar clips de YouTube/Twitch/sitios de partidos. Strikes garantizados.
- ❌ Usar nombres de jugadores/equipos en queries de stock.
- ❌ Caché ilimitada — limita a 30 días de retención (purge de `cache/`).
- ❌ Llamar a la API Pexels/Pixabay sin cache check previo.
- ❌ Re-renderizar el carrusel si ya está en `cache/carousels/{date}/` (ahorra ~10s por bet).
- ❌ Generar audio TTS sin cache — el TTS es el paso más caro.

### SÍ hacer

- ✅ Validar el JSON de Redis antes de proceder (status no PENDING ⇒ skip; bets vacío ⇒ skip).
- ✅ Loggear cada paso con timing (`time.perf_counter()`).
- ✅ Subir log de éxito/fracaso a Redis: `betai:status:scripts` con field `Video TikTok Factory`.
- ✅ Subir `.mp4` final a Vercel Blob y guardar URL en `betai:tiktokfactory_video_tomorrow` (string JSON `{date, url, duration_s, generated_at}`).
- ✅ Manejar fallos del TTS / Pexels con retry exponential backoff (3 intentos máx).
- ✅ Validar que el output existe y tiene > 1MB antes de marcar SUCCESS.

---

## 8. Test del primer run

1. Crea `PronosticosAuto/`, copia este `PronosticosAuto.md` como `README.md`.
2. `pip install -r requirements.txt`
3. Configura `.env.local` con las keys (la URL/token de Redis los tienes ya en el proyecto principal).
4. **Smoke test paso a paso (un script por etapa):**
   ```bash
   python -m src.data_loader --date 2026-04-28           # debe imprimir 6 combinadas
   python -m src.script_builder --date 2026-04-28        # debe imprimir guion + segments
   python -m src.tts --text "test" --out /tmp/test.mp3   # debe generar audio
   python -m src.stock_search --league "La Liga"         # debe descargar 1 clip
   python -m src.carousel_renderer --date 2026-04-28     # 6 PNGs en cache/carousels/
   python main.py --date 2026-04-28 --debug              # MP4 final
   ```
5. Verifica el MP4 en VLC. Sube manualmente a TikTok desde móvil.

Una vez validado, automatiza con cron.

---

## 9. Roadmap próximos pasos (después de v1)

| Idea | Prioridad |
|---|---|
| Variantes de voz (probar voces distintas para A/B test de retención) | media |
| Detección automática de "hook" — alargar la primera combinada con más drama | alta |
| Música de fondo libre de derechos (Pixabay Music) — mezclada bajo voz | alta |
| Branding consistente: bumper inicial 3s con logo Master Picks AI animado | media |
| Multi-idioma (generar versión EN para mercado angloparlante) | baja |
| Integración con TikTok Upload API (auto-publicación) | baja, requiere cuenta business |

---

## 10. Acceso al proyecto principal (referencia)

Si necesitas ver cómo está implementado algo en el proyecto original `bet-ai-master`:

| Archivo | Contiene |
|---|---|
| `frontend/components/TikTokFactory.tsx` | Layout exacto del carrusel, mapeo de iconos, banderas, fuentes, colores |
| `frontend/utils/flags.ts` | Mapeo league_id → ISO country code (port a Python) |
| `frontend/lib/tiktok-versions.ts` | Schema de versiones custom (V1, V2, V3, etc.) |
| `backend/system_prompt_tiktok.txt` | Prompt del CARRUSEL (referencia para entender combinadas) |
| `backend/system_prompt_tiktok_video_single.txt` | **Prompt del guion video deep-dive 1 partido (Champions)** |
| `backend/system_prompt_tiktok_video.txt` | **Prompt del guion video multi-match (fallback no-Champions)** |
| `backend/src/services/analyze_tiktok.py` | Generador del carrusel (Gemini/OpenAI gpt-5.4) |
| `backend/src/services/analyze_tiktok_video.py` | **Generador del guion video — mode detection + enricher + OpenAI** |
| `backend/src/services/tiktok_video_enricher.py` | **Llamadas API-Sports para datos verificables (standings, top scorers, injuries)** |
| `backend/src/services/api_client.py` | Cliente HTTP con proxy residencial + rate limit tracking |
| `backend/src/services/social_generator_tiktok.py` | Genera el caption viral 4000 chars (descripción TikTok) |
| `.github/workflows/tiktok_viral_automated.yml` | Workflow del carrusel (18:00 cron) |
| `.github/workflows/tiktok_video_script.yml` | **Workflow del guion video (workflow_run tras carrusel)** |

No copies código, replícalo en Python tomando estos como referencia visual y de schema.

---

**Autor briefing:** Claude (sesión `bet-ai-master`)
**Fecha:** 2026-04-27
