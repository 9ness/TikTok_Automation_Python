# Editor Auto · audio que se oye mal, estilo VIP y ahorro de trabajo (10-11/11/2026)

Encargo de Néstor (rutina «Fable · Editor audio y estilo VIP»). Todo se probó en el VPS y en el PC de casa
con vídeos reales del corpus del Editor; nada se ha activado para clientes. Carpeta de pruebas (fuera de git):
`/mnt/HC_Volume_106974679/agentes/trabajo/fable-audio/` (= `$W`).

Anexos con el detalle:
- [`2026-11-10_anexo_escucha_audio.md`](2026-11-10_anexo_escucha_audio.md) — espectrogramas antes/después y tabla problema → método.
- [`2026-11-10_anexo_estilo_vip.md`](2026-11-10_anexo_estilo_vip.md) — qué hace hoy el estilo VIP, medidor de estilo sin IA, fichas Hormozi/Abdaal/Martell/MrBeast, plan.
- [`2026-11-10_anexo_ideas_ahorro.md`](2026-11-10_anexo_ideas_ahorro.md) — 14 ideas nuevas de ahorro (los minutos son estimaciones).

## Resumen en 6 líneas

1. **Audio: DeepFilterNet3 es el mejor con diferencia** (DNSMOS OVRL +0,53 en vídeos reales y +1,09 en casos con ruido; nunca empeora) y es barato: ~1,6 s de CPU por 30 s de audio. **RNNoise** (filtro `arnndn` de ffmpeg) es el segundo, sin dependencias y casi gratis.
2. **`afftdn` (lo que se usa hoy para transcribir) no vale como limpieza**: apaga la voz y empeora música, clics y voz baja. Demucs, VoiceFixer y Resemble no compensan. **El eco no lo quita nada** de lo probado.
3. Hecha la herramienta **«🔊 Mejorar voz» (`audio_clean`)**: tras el cortador, highpass + rnnoise + nivelado a −16 LUFS en dos pasadas, sin recodificar el vídeo. **Apagada por defecto**; le falta el modelo `.rnnn` en el repo (OK de Néstor).
4. **Estilo VIP**: hoy copia el estilo de UNA referencia con una llamada de visión y rellena solo parte de lo que el Editor sabe hacer. Añadí un **elector de estilo por vídeo** (lee la transcripción y decide qué estilo encaja con el nicho y el tono): funciona y cuesta ~0,004 $.
5. **Muestras** original · básico · VIP en `$W/muestras/` con su gasto real (0,154 $ en total): tabla en `$W/muestras/ESTILOS.md` (ver §3). **Veredicto: el VIP aún no está para clientes**: 6 de 9 meten fotos de stock de otro producto (riesgo de sanción) y los textos se cortan o pisan los subtítulos; el mejor saca un 8/10.
6. Lo que más ahorra ya: una sola transcripción por vídeo, comprobador de audio al entrar, biblioteca de estilos con nombre.

## 1. Audio

### Qué se probó y cómo

- **18 audios de 30 s**: 6 reales del corpus (`bugalleitor__1`, `cintiacbc__quiet` a −35 LUFS, `nebulabs__img`, `nueveness__buga_3`, `nueveness__clienta_2`, `patrizziaconz__img`) + 12 semisintéticos (voz limpia real + ruido: música, viento, lluvia, motor, aspiradora, eco, clics, volumen bajo), que dan además SI-SDR frente a la voz limpia.
- **Calidad**: DNSMOS P.835 (SIG voz, BAK fondo, OVRL global, 1-5) en 346 medidas + WER con Whisper small (no large) + espectrogramas y medidas voz−suelo/agudos ([anexo de escucha](2026-11-10_anexo_escucha_audio.md)).
- **Tiempo**: VPS con `--cpus 4` (cargado, carga 15-30: cifras pesimistas) y GTX 1050 Ti del PC de casa.
- **Escucha humana: NO hecha** (un agente no oye). Néstor debería oír `$W/muestras_audio/<caso>/` (15 casos × 8 versiones, niveladas igual; `LEEME.md` dentro).

### Resultados (OVRL medio; Δ frente a lo de hoy, que es solo loudnorm)

| Método | OVRL reales (Δ) | OVRL sintéticos (Δ) | SI-SDR sint. | s por 30 s | Peor caso |
|---|---|---|---|---|---|
| Hoy (loudnorm) | 2,42 | 2,03 | 2,2 dB | 0,02 (VPS) | — |
| `afftdn` (el de hoy al transcribir) | +0,18 | +0,14 | 2,7 | 0,27 | −0,56 clics |
| RNNoise `sh` | +0,19 | +0,62 | 4,3 | 0,42 | −0,24 eco |
| RNNoise `bd` | +0,22 | +0,56 | 4,5 | 0,39 | −0,13 |
| RNNoise `sh` al 70 % | +0,20 | +0,42 | 4,0 | 0,46 | −0,09 |
| RNNoise + compresor | +0,11 | +0,55 | 3,5 | 0,45 | −0,53 |
| `anlmdn` | +0,04 | +0,01 | 2,5 | 3,39 | −0,64 |
| `speechnorm` / `dynaudnorm` | −0,09 / −0,13 | ≈0 | — | 0,16 | empeoran |
| **DeepFilterNet3** | **+0,53** | **+1,09** | **9,8** | **1,61** | **+0,01 (nunca empeora)** |
| DeepFilterNet3 suave (tope 12 / 20 dB) | +0,39 / +0,41 | +0,70 / +0,89 | 6,9 / 8,1 | 1,4 | +0,01 |
| Demucs htdemucs (CPU VPS) | +0,09 | +0,87 | 8,1 | 37,9 | −0,29 |
| Demucs htdemucs (GPU casa) | +0,08 | +0,88 | 11,6 | 3,1 (GPU) | −0,20 |
| VoiceFixer (GPU casa) | +0,46 | +1,06 | −21,4 (rehace la voz) | 4,6 (GPU) | **−1,60 clics** |
| Resemble Enhance denoise (GPU casa) | +0,43 | +1,03 | **14,5** | 1,4 (GPU) | −0,04 |
| Resemble Enhance completo (GPU casa) | — | — | — | 169-235 | no cabe en 4 GB: inviable |

WER (Whisper small; 0 = transcribe todo bien): reales (cambio frente a la transcripción del original) · sintéticos (frente al texto limpio): hoy 0,00 · 0,10 — afftdn 0,07 · 0,12 — RNNoise sh 0,10 · 0,13 — **DFN3 0,11 · 0,13** — DFN3 lim12 0,09 · 0,11 — Demucs 0,06 · 0,10. Ningún método mejora lo que entiende Whisper (todos tocan algo la voz): todos cambian ~1 palabra de cada 10-15 frente al original. Ojo: los subtítulos (peso 90) se transcriben DESPUÉS de «Mejorar voz» (peso 20), así que heredan ese cambio; idea pendiente: transcribir del audio de antes de limpiar.

Nota GPU (GTX 1050 Ti, 4 GB): Demucs pasa de 38 s a 3 s pero sigue sin compensar en vídeos reales. **Resemble Enhance en modo denoise** es casi tan bueno como DFN (SI-SDR incluso mejor, 14,5 dB) pero necesita GPU (2,8 GB de VRAM) y apaños de instalación; VoiceFixer «regenera» la voz (SI-SDR negativo: ya no es la misma señal) y destroza un caso: descartado. Resemble completo (con mejora) no cabe en 4 GB. DeepFilterNet en GPU no se pudo medir (sin rueda para Python 3.12 en casa); en CPU ya va sobrado. **Orden de Néstor (11/11): el Editor y sus pruebas, solo en el VPS** — las medidas de GPU quedan como dato; la recomendación (DeepFilterNet/RNNoise) vale solo con la CPU del VPS.

Por problema ([detalle](2026-11-10_anexo_escucha_audio.md)):

| Problema | Lo arregla | No sirve |
|---|---|---|
| Volumen bajo (cintia, −35 LUFS) | Limpiar ANTES de nivelar: hoy 1,44 → RNNoise 2,25 → DFN 2,79 | Nivelar solo sube el siseo con la voz |
| Ruido constante (motor, aspiradora, siseo) | DFN (≈2,8-3,2); RNNoise bien (≈2,3-2,5) | `afftdn` (−4 a −12 dB de agudos en la voz), Demucs |
| Viento | DFN (SI-SDR 0,8 → 11,5 dB) | RNNoise a medias (queda retumbe), Demucs |
| Música de fondo | DFN y Demucs; RNNoise solo en las pausas | `afftdn` (empeora) |
| Lluvia | DFN (1,29 → 3,30), quizá pierde brillo en las eses | `afftdn` |
| Eco / reverberación | **Nada de lo probado** | Todos; RNNoise incluso se aleja de la voz |
| Clics | Nada claro | `adeclick` no aporta, `afftdn` empeora |

Avisos para escuchar: DFN deja silencio digital entre frases (puede sonar «recortado»); la versión suave lo evita pero pierde gran parte de la mejora. `R_nebulabs__img` no mejora con nada (el problema es la voz, no el fondo).

### Coste por minuto

| Opción | Coste | Notas |
|---|---|---|
| RNNoise en el VPS | 0 $ · ~0,8 s CPU/min | nativo de ffmpeg; solo hace falta el fichero `.rnnn` (~1 MB) |
| DeepFilterNet3 en el VPS | 0 $ · ~3,2 s CPU/min | dependencia nueva (PyPI solo en Python 3.11, el de la imagen) |
| Demucs en el VPS | 0 $ · ~76 s CPU/min | no compensa |
| Auphonic | ≈0,017-0,020 $/min (2 h/mes gratis) | precios de nov 2026 sin confirmar; no probado |
| Dolby.io Enhance | ≈0,043 $/min | sin probar |
| ElevenLabs Voice Isolator | ≈0,12 $/min | sin probar |
| Adobe Podcast Enhance | sin API (9,99 $/mes, a mano) | no automatizable |

Conclusión: no hace falta pagar un servicio; DFN en local da la calidad de un servicio a coste 0. Lo único que podría justificar uno es el eco (Adobe/Auphonic tienen dereverb; sin medir).

### La herramienta `audio_clean` («🔊 Mejorar voz»)

- Código: `src/editor_auto/tools/audio_clean.py` · tests `tests/editor_auto/test_audio_clean.py` (17; 16 pasan y 1 se salta mientras no esté el modelo) · doc en `EDITOR_AUTO_MODULE.md`.
- Va **después del cortador** (peso 20): el cortador sigue decidiendo con el audio original, así que el banco del cortador no cambia (no hizo falta pasarlo).
- Cadena: highpass 80 Hz → (adeclick opcional) → `arnndn` con modelo `.rnnn` → (compresor opcional) → `loudnorm` −16 LUFS en **dos pasadas con `linear=true`**. Vídeo con `-c:v copy`. Si no hay audio, hay silencio o falla ffmpeg: copia la entrada y sigue.
- **Sin el modelo no cae a `afftdn`** (medido: estropea); solo nivela y lo avisa. `afftdn` queda como motor explícito.
- Comprobado con el caso del motor (lo que hace el nivelado de una pasada: subía 11 dB el ruido del arranque): con `audio_clean` el arranque queda a −14,4 dB de la voz (original −13,0: no infla) y con rnnoise a −35,6 dB.
- Ningún flujo la incluye: se añade a mano al flujo de un usuario (Usuarios › flujo › «🔊 Mejorar voz»).

## 2. Estilo VIP

Detalle completo en el [anexo de estilo](2026-11-10_anexo_estilo_vip.md). En corto:

- **Hoy**: `estilo_vip.estilo_desde_video` hace una hoja de 24 fotogramas de UNA referencia y una llamada de visión (Haiku, ~0,0015-0,0018 $ medido por referencia). Rellena colores, fuente de rótulos, densidad, gancho/fotos/zooms y subtítulos (color, resaltado, palabras, altura, mayúsculas, tamaño en 4 escalones). **No se guarda** como preset y no mapea cosas que `subs_auto` ya sabe hacer (fuente de subtítulos, borde, `entrance_anim: pop`, minúsculas, `box_outline`/`glow`). El prompt no pide `tamano`.
- **Medidor sin IA** (prototipo `$W/scripts/medir_estilo.py`): ritmo (cortes y zooms por minuto) y audio en 10-30 s; OCR de subtítulos acierta 3 de 3 pero tarda 213-306 s por vídeo y da falsos rótulos (lee texto de la escena). Propuesta: ritmo + audio siempre, OCR solo en la banda a 1 fps o saltarlo, y meter esas cifras en el prompt de visión.
- **«¿El estilo se adapta al nicho?»** Hoy no: se copia de la referencia tal cual y solo los rótulos y zooms siguen lo que se dice. Por eso se probó un **elector de estilo por vídeo**: lee la transcripción y devuelve nicho, tipo de vídeo, tono, público, cada estilo puntuado 0-10 con motivo, el elegido, ajustes (densidad, gancho, fotos, zooms, SFX, color) y notas para el plan. Ejemplo real (`patrizziaconz__img`, colágeno): «belleza y bienestar · íntimo y cercano» → Abdaal 7, Martell 6, Hormozi 3, MrBeast 1; densidad baja, sin SFX ni color grade, «evitar promesas médicas». Coste medido 0,0037-0,0045 $ y ~20-30 s por vídeo. Vive hoy en el lanzador de pruebas (`$W/scripts/muestras_estilos.py elegir`), no en la app.
- **Carencias para copiar a los grandes**: píldora de frase entera, subtítulos a media altura, animación por barrido, barra de progreso, emojis, tarjetas de motion graphics, música con ducking, multicámara (no copiable sin segunda cámara).

## 3. Muestras original · básico · VIP

`$W/muestras/<original>/` con `original.*`, `basico.mp4` (automatización actual: cortador + subtítulos) y `vip_<estilo>.mp4` (cortador + edición VIP + subtítulos + flecha con el estilo de cada creador). Tabla con referencia, ficha, nota honesta y gasto en **`$W/muestras/ESTILOS.md`**.

Hechas en el VPS (sin subir al Drive): `/mnt/HC_Volume_106974679/agentes/trabajo/fable-audio/muestras/` con `ESTILOS.md` (tabla original · versión · referencia · nota · gasto) y las fichas de estilo. 3 originales × (básico + 3 VIP: el elegido + 2), 9 VIP revisados fotograma a fotograma. **Gasto total 0,154 $** (VIP 0,006-0,010 $ por vídeo, elector 0,004 $, corte 0,011-0,019 $).

| original | elegido por el elector | mejor en la revisión | notas VIP |
|---|---|---|---|
| patrizziaconz (colágeno) | abdaal 5/10 | hormozi 6/10 | 5 · 6 · 6 |
| nueveness (crema de arroz) | martell 5/10 | **abdaal 8/10** | 5 · 8 · 7 |
| bugalleitor (botella gym) | abdaal 5/10 | abdaal 5/10 | 5 · 4 · 4 |

**Veredicto honesto: el VIP aún NO está para clientes.** 6 de 9 meten una foto de stock de OTRO producto (en TikTok Shop es «producto incoherente» y trae sanción); 2 ponen una famosa (Elsa Pataky); los rótulos se cortan a mitad de frase, pisan los subtítulos (Martell los pone al 60 %, en la misma banda que los subtítulos) o tapan la cara; los subtítulos sin borde se pierden en fondos claros. Cuando no hay foto falsa (nueveness abdaal) el resultado es bueno: precio comparado en rojo/verde y rótulos con sentido. Arreglos (orden): 1) en nichos de producto, `photo_insert` sin fotos de stock del producto ni de famosos; 2) frases completas en gancho y rótulos; 3) banda de rótulos ≠ banda de subtítulos, sin tapar la cara; 4) borde obligatorio en subtítulos; 5) repetir la comparativa. cintiacbc no se hizo (tiempo).


## 4. Ideas para ahorrar trabajo

14 ideas en el [anexo](2026-11-10_anexo_ideas_ahorro.md). Las tres de más valor ya: (1) **una sola transcripción por vídeo** (hoy un flujo VIP transcribe el mismo vídeo ≥4 veces: 0,013-0,017 $/min en vez de 0,0043, y palabras distintas en cada paso); (2) **comprobador de audio al entrar** (semáforo de volumen/ruido y activar `audio_clean` solo en ámbar); (3) **biblioteca de estilos con nombre** en Redis. También: el pass2 de Gemini que da 404 en cada vídeo (`tasks.md`), cortador una vez + N variantes, un solo render final (hoy se recodifica 4-5 veces).

## 5. Plan por fases

**Ya** (días):
1. Meter el modelo RNNoise `sh.rnnn` en `assets/rnnoise/` y probar `audio_clean` con 2-3 clientes que se oyen mal. **OK de Néstor** (licencia del modelo y activarlo a clientes).
2. Comprobador de audio al entrar (solo informa).
3. Elector de estilo por vídeo en la app (prompt en `src/editor_auto/prompts/vip_elector.md`, `record_claude`) junto a una **biblioteca de estilos con nombre** (Hormozi, Abdaal, Martell, MrBeast de serie). **OK de Néstor** (schema nuevo de Redis, sin tocar los existentes).
4. Mapear en `estilo_vip._subs_cfg` lo que `subs_auto` ya soporta (fuente, borde, `pop`, minúsculas, `box_outline`/`glow`).
5. Una sola transcripción por vídeo (apagada por defecto hasta pasar el banco).

**Pronto** (1-2 semanas):
6. Motor `deepfilternet` en `audio_clean` (el mejor medido). **OK de Néstor**: dependencia nueva en la imagen (+ torch ya está). Mantener RNNoise de respaldo.
7. Pedir `tamano`, borde y animación en `prompts/vip_estilo_referencia.md`. **OK de Néstor** (prompt calibrado).
8. Medidor de estilo (ritmo + audio) dentro del análisis; varias referencias por estilo; píldora de frase y subtítulos a media altura.

**Futuro**: barra de progreso, emojis, tarjetas, música con ducking, b-roll de vídeo; dereverb (el eco sigue sin solución: probar Auphonic/Adobe con 2-3 vídeos si aparecen clientes con eco); un solo render final.

## 6. Qué necesita el OK de Néstor

- Subir el modelo RNNoise (`.rnnn`, ~1 MB) al repo — revisar licencia.
- Activar `audio_clean` para clientes (hoy apagada).
- DeepFilterNet como dependencia de la imagen de la API.
- Probar servicios de pago (Auphonic/Dolby/ElevenLabs) — solo si hay casos de eco.
- Subir las muestras al Drive (pendiente: lo pregunta el Admin).
- Elector y biblioteca de estilos en la app (Redis nuevo) y tocar `prompts/vip_plan.md` / `vip_estilo_referencia.md`.
- Escuchar `$W/muestras_audio/` y ver `$W/muestras/`: las notas de calidad son de máquina (DNSMOS, fotogramas), no de oído.
