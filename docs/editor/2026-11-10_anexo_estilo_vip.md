# Parte 2 · Sacar un estilo VIP de uno o varios vídeos de referencia (10/11/2026)

> Anexo de [`2026-11-10_audio_y_estilo_vip.md`](2026-11-10_audio_y_estilo_vip.md). Las rutas relativas (`scripts/`, `log/`, `estilo/`, `muestras_audio/`…) son de la carpeta de pruebas `/mnt/HC_Volume_106974679/agentes/trabajo/fable-audio/` (en el ampliado del VPS, fuera de git).

Resumen: hoy el estilo sale de UNA referencia con una sola llamada de visión (24 fotogramas) y
solo rellena una parte de lo que el Editor sabe hacer. El prototipo sin IA (`scripts/medir_estilo.py`)
acierta en subtítulos y ritmo, falla en rótulos y su OCR es demasiado lento tal cual. La propuesta:
medidor rápido (ritmo + audio, y OCR solo en la banda) → cifras dentro del prompt de visión →
mediana de varias referencias → preset con nombre, guardado y aplicable a cualquier usuario.

## a) Qué hay hoy

| Pieza | Qué hace | Carencia |
|---|---|---|
| `services/estilo_vip.py` · `estilo_desde_video(video)` | Una hoja de 24 fotogramas (`revision_visual._fotogramas/_hoja`) → 1 llamada a Claude visión (`claude_client.modelo()`, env `EDITOR_AUTO_CLAUDE_MODEL`; `record_claude` con tokens reales; `max_tokens=16000`). Devuelve config parcial de `vip_overlays` + `_flujo` para `subs_auto` y `sticker_arrow` | Solo UNA referencia. La hoja es de fotos sueltas: no ve ritmo, animación, música ni SFX. No se guarda (el endpoint dice «NO guarda nada») |
| `estilo_desde_texto(texto)` | El cliente lo cuenta con palabras → misma config, solo lo que diga (~0,0005 $) | Igual: no se guarda como preset |
| Endpoints | `POST /vip-overlays/estilo` y `/vip-overlays/estilo-texto` (`src/api/routers/editor_auto/tools.py:50-90`) | La UI mezcla el resultado en el flujo de ESE usuario; no hay biblioteca |
| `prompts/vip_estilo_referencia.md` | Pide colores, preset, fuente, densidad de rótulos, gancho/fotos/zooms/grade, altura de rótulo, notas, y subtítulos (resaltado, colores, palabras, altura, mayúsculas) | No pide `tamano` de letra (el código sí lo mapea → nunca llega), ni borde, ni animación, ni ritmo |
| `services/style_mapper.py` | `build_tool_flow(style)`: flujo por estilo; `_TOOLS_DE_LA_WEB = {silence_cutter, subs_auto, sticker_arrow}`; `conservar_pasos_del_equipo` | Estilos fijos en código; no lee presets guardados |
| `tools/vip_overlays.py` + `prompts/vip_plan.md` | Plan por vídeo (texto): gancho (texto, dato, foto o clip copiado al inicio), rótulos de 1-3 palabras en MAYÚSCULAS con rol (alerta/dato/ok/neutro), zooms 1,10-1,20 de 1-4 s, tarjeta «QUEDAN», fotos de apoyo (buscador de imágenes + verificación con Haiku; NO es generación de pago), SFX sintetizados, color grade, −14 LUFS | Sin emojis, sin barra de progreso, sin tarjetas de lista, sin pantalla partida, sin música |

### Lo que `_a_config` rellena hoy (y lo que no)

- A `vip_overlays`: `color_alerta/dato/ok/neutro`, `preset` (personalizado, impacto, limpio, neon), `font_path`, `densidad_rotulos`, `gancho`, `fotos`, `zooms`, `color_grade`, `rotulo_y_pct` (5-60), `notas_estilo` (≤1500).
- A `subs_auto` (`_subs_cfg`): `highlight_mode` (color→`color_swap`, pildora→`pill`, subrayado→`underline`, ninguno→`none`), `text_color`, `highlight_color`, `max_words` (1-6), `y_position` (0,40-0,92), `case_mode` (`UPPERCASE` o nada), `font_scale` (pequeño 0,035 · normal 0,045 · grande 0,06 · gigante 0,075). Regla: píldora con letra oscura → 1 palabra.
- A `sticker_arrow`: flecha del banco más parecida por color, o apagada.

**Parámetros que `subs_auto` SÍ tiene y el estilo no toca** (ganancia sin escribir herramienta nueva):
`font_path` (la fuente detectada va solo a los rótulos, no a los subtítulos), `stroke_color`, `stroke_width`,
`pill_enabled`, `max_width`, `entrance_anim` (`pop` = escala + fundido ~160 ms; `none`),
`highlight_mode` también `box_outline` y `glow`, `case_mode` también `lowercase` y `Title Case`,
`preset_name`, `sync_offset`.

## b) El prototipo `scripts/medir_estilo.py` y lo medido

Qué mide, sin IA de pago: cortes de plano y saltos/zooms por minuto (diferencia entre fotogramas a
10 fps en 64×114 + histograma), subtítulos por OCR (easyocr a 2 fps, 540 px: palabras a la vez, líneas,
altura, tamaño, mayúsculas, color y color de la palabra resaltada, cambios por segundo), textos fijos,
marca/usuario, gancho, y audio (LUFS, nivel de voz, fondo entre frases → música probable).

Resultados reales (`estilo/out/*.json`, 5 vídeos; VPS con carga ~17 y 3 CPU):

| Vídeo | Dur. | Cortes plano/min | Saltos/min | Subtítulos (medido) | Fondo sonoro | OCR |
|---|---|---|---|---|---|---|
| ed_cintia | 33,2 s | 3,6 | 5,4 | `hay:false` (cobertura 0,12); marca `cintia_gloww`, `tiktok` | sí (−15,4 dB) | 213,8 s |
| ed_nueveness_buga1 | 41,9 s | 0,0 | 2,9 | 4 palabras, 1 línea, y 73 %, letra 4,3 %, minúsculas, #E6EEF4, resaltado color #20D1EC, 1,15 cambios/s | no (−44) | 306,0 s |
| ed_patri | 42,1 s | 0,0 | 5,7 | 1 palabra, y 73 %, letra 3,75 %, MAYÚSCULAS (0,99), #FBFBFA, `ninguno_o_pildora`, 1,66 cambios/s | no (−30,4) | 293,4 s |
| viral_02d1… | 9,5 s | 0 | 6,3 | `hay:false` (0,21); marca `colgate` | — | 70,1 s |
| viral_0465… | 10,0 s | 0 | 0 | sin texto | sí (−7,4) | 64,7 s |

Cortes y audio cuestan 5-19 s y 5-14 s por vídeo. Todo el tiempo se va en el OCR.

### Validación mirando fotogramas (tiras de ed_cintia, ed_patri y ed_buga)

- **ed_cintia: el detector ACIERTA.** El vídeo no lleva subtítulos: es una descarga de TikTok con la
  marca de agua «TikTok @cintia_gloww» (chica enseñando faldas, 4-5 cambios de plano en 33 s, que
  cuadran con 3,6 cortes + 5,4 saltos por minuto). El problema era la referencia, mal etiquetada como «ed_».
- **ed_patri: subtítulos correctos** (1 palabra, mayúsculas, blanca con borde, ~72 %). **Falso positivo
  en rótulos:** el OCR lee la etiqueta del bote («Marine Collagen», «nutritional information») y el logo
  superpuesto → `rotulos_min 15,7` es falso.
- **ed_buga: subtítulos correctos** (3-4 palabras, minúsculas, blanco con la palabra activa en cian).
  **Falsos positivos:** el «10» de la camiseta sale como texto fijo y las frases de subtítulo que duran
  ≥1,5 s se cuentan como «textos fijos» → `rotulos_min 8,6` es falso. Los 2,9 saltos/min son los cortes
  del cortador (correcto).

Conclusión: **subtítulos 3 de 3 bien** (palabras, mayúsculas, altura, color, resaltado) y ritmo creíble;
**rótulos y gancho no son fiables** (texto de escena: ropa, etiquetas; subtítulos lentos). No distingue
píldora de «sin resaltado», ni fuente, ni animación. Muestra pequeña (3 con subtítulos): hace falta
pasarlo por 15-20 vídeos antes de fiarse.

Arreglos baratos del medidor: (1) no contar como «fijo» lo que cae en la banda de subtítulos;
(2) exigir que un rótulo tenga caja o fondo de color uniforme, o dejar rótulos y gancho a la visión;
(3) píldora = fondo claro uniforme alrededor de la caja con letra oscura; (4) `fps` real con
`avg_frame_rate` (ed_patri sale «120 fps» por `r_frame_rate`).

### Cómo bajar el tiempo de OCR (3,2-7 s por fotograma hoy)

| Medida | Efecto esperado (no medido) |
|---|---|
| 1 fps en vez de 2 | la mitad |
| Dos pasadas: 8-10 fotogramas enteros para localizar la banda → OCR solo del recorte (~25 % del alto) | 3-4× menos por fotograma |
| 360 px de ancho en vez de 540 | ~2× |
| Tope de 30 s por referencia (el estilo no cambia a mitad) | fija el techo |
| GPU del PC de casa (GTX 1050 Ti, `~/worker` con CUDA) | easyocr en GPU va en décimas de segundo por fotograma |
| **Saltarse el OCR**: ritmo + audio (10-30 s) y dar a la visión los fotogramas con esas cifras | 0 s de OCR; se pierde palabras/altura medidas, que la visión estima |

Recomendado: ritmo + audio siempre; OCR solo en banda, 1 fps, tope 30 s, en segundo plano o en el PC de
casa; si no está a tiempo, la visión va sin él.

## c) Parámetro de estilo → cómo se mide → a dónde va hoy → qué falta

| Parámetro | Sin IA | Visión | Campo del Editor HOY | Qué falta |
|---|---|---|---|---|
| Fuente | no | sí (familia aproximada) | `font_path` de `vip_overlays` (rótulos) | pasarla también a `subs_auto.font_path`; ampliar `fonts_registry` |
| Color de letra | OCR + color (medido) | sí | `subs_auto.text_color` | nada |
| Resaltado | segundo tono en la banda (medido); píldora no | sí | `highlight_mode`, `highlight_color` | mapear `box_outline` y `glow`; detectar píldora |
| Posición | altura de la banda (medido) | sí | `y_position` (0,40-0,92) | subtítulos a media altura (<0,40) |
| Palabras por línea | mediana y p90 (medido) | sí | `max_words` (1-6) | líneas (1 o 2) |
| Mayúsculas | ratio (medido) | sí | `case_mode` | mapear `lowercase` y `Title Case` |
| Tamaño | alto de caja en % (medido) | sí | `font_scale` (4 escalones) | pedir `tamano` en el prompt, o pasar el % medido directo |
| Borde/sombra | no | sí | — | mapear `stroke_color`, `stroke_width` (ya existen) |
| Animación de subtítulos | cambios/s (ritmo); el tipo no | solo con ráfaga de 6-8 fotogramas seguidos | — | mapear `entrance_anim: pop` (existe); karaoke por barrido no existe |
| Zooms/min | saltos sin cambio de histograma | no (fotos sueltas) | `zooms` (sí/no) | intensidad: zooms por minuto y escala en `vip_plan` |
| Cortes/min | histograma (medido) | no | — | es del cortador/b-roll, no del estilo; sirve como nota |
| Emojis | no | sí | — | herramienta nueva (banco de emojis sobre el rótulo) |
| Overlays/rótulos | OCR poco fiable (falsos positivos) | sí | `densidad_rotulos`, `rotulo_y_pct`, colores, `preset` | rótulos con caja de varias líneas |
| B-roll | cortes de plano con vuelta al plano base | sí | `fotos` (fotos de apoyo) | b-roll de vídeo (clips) |
| Música | fondo entre frases (medido: sí/no) | no | — | pista de música con ducking (hoy no hay) |
| SFX | picos cortos en el audio (por hacer) | no | SFX fijos de `vip_overlays` | activar/desactivar y elegir banco |
| Gancho | texto arriba en el primer segundo (poco fiable) | sí | `gancho` (sí/no) | tipo de gancho (texto, dato, clip) como preferencia |
| Barra de progreso | franja horizontal que crece (fácil, por hacer) | sí | — | herramienta nueva (un `drawbox` animado) |
| Tarjetas / motion graphics | no | sí | tarjeta «QUEDAN» | tarjetas de lista/título (PIL + overlay) |
| Pantalla partida / multicámara | línea divisoria estable (por hacer) | sí | — | no copiable: necesita segunda cámara o b-roll |

## d) Fichas de cuatro estilos americanos

Lo visto en tiras de fotogramas de un short de cada uno (720×1280). El medidor aún no se ha pasado
por ellos: ritmo y música son observación, no cifra.

| Creador | Referencia | Subtítulos | Ritmo y zooms | Música / SFX | Gancho | Copiable HOY | No copiable hoy |
|---|---|---|---|---|---|---|---|
| Alex Hormozi | https://www.youtube.com/shorts/5z5OA5v9rgk (66,9 s) | blancos, pequeños, minúsculas, 2-3 palabras, centrados a media altura; palabra clave en amarillo y cursiva | multicámara y pantalla partida; cortes secos | sin música apreciable | frase directa a cámara | color + resaltado amarillo, 2-3 palabras, minúsculas, tamaño pequeño | altura media (<0,40), cursiva en la palabra clave, multicámara |
| Ali Abdaal | https://www.youtube.com/shorts/AMZ0uEmXXAk (117,7 s) | píldora blanca redondeada, letra oscura, 2-3 palabras, palabra activa resaltada, zona media-baja | plano fijo, zooms suaves | fondo suave | título fijo arriba con lista que se va llenando | `highlight_mode: pill`, altura, letra oscura | píldora de frase entera (hoy la regla la deja en 1 palabra), título fijo con lista |
| Dan Martell | https://www.youtube.com/shorts/oMvaTK163HA (67,7 s) | blancos, finos, pequeños, centrados; frases enteras en amarillo | cortes rápidos, tarjetas animadas | golpes de SFX con las tarjetas | afirmación fuerte | blanco + amarillo, tamaño pequeño, rótulos de dato | tarjetas de motion graphics, resaltar frases enteras |
| MrBeast | https://www.youtube.com/shorts/rqsRdfdN4uI (46,1 s) | sin subtítulos | cortes muy rápidos, muchos planos | música y SFX continuos | reto en la primera frase; barra de emojis de progreso arriba | subtítulos apagados, rótulos grandes, zooms, SFX | barra de emojis de progreso, b-roll de vídeo, música |

(GaryVee, https://www.youtube.com/shorts/Zct_Hn4Cql0, descartado: es una animación.)

## e) Propuesta por fases

### Ya (1-2 días, sin herramientas nuevas)
1. **Mapear lo que `subs_auto` ya soporta**: fuente a los subtítulos, borde, `entrance_anim: pop`,
   `lowercase`/`Title Case`, `box_outline`/`glow`. Esfuerzo S. Toca `estilo_vip._subs_cfg`.
2. **Pedir `tamano` en `prompts/vip_estilo_referencia.md`** y los campos nuevos (borde, animación).
   Esfuerzo S. **Necesita el OK de Néstor: es un prompt calibrado.**
3. **Medidor rápido en el repo** (`services/estilo_medidor.py`): ritmo + audio (10-30 s) y sus cifras
   escritas dentro del prompt de visión («2,9 saltos/min, sin música, subtítulos cambian 1,2 veces/s»),
   para que la IA deje de adivinar lo que una foto no enseña. Esfuerzo S-M.
4. **Presets con nombre**: guardar el resultado como `editor_auto:estilo:<nombre>` (Redis local, JSON con
   la config de `vip_overlays` + `_flujo`), endpoints listar/guardar/aplicar, y botón «Aplicar a usuario».
   Esfuerzo M. Es schema nuevo de Redis (no cambia ninguno existente) + tipos TypeScript.

### Pronto (1-2 semanas)
5. **Varias referencias**: 1 hoja por vídeo en la misma llamada (máx. 3-4) y mediana de lo medido
   (palabras, altura, tamaño, ritmo); colores y resaltado por mayoría. Esfuerzo M.
6. **OCR en banda** (1 fps, recorte, tope 30 s, PC de casa si responde) con los arreglos del medidor
   y validación sobre 15-20 vídeos etiquetados a mano. Esfuerzo M.
7. **Ráfaga de animación**: 6-8 fotogramas seguidos (a 12 fps) de un cambio de palabra, en una segunda
   hoja, para que la visión diga pop/barrido/ninguna. Esfuerzo S.
8. **Presets de serie** «Hormozi», «Abdaal», «Martell», hechos una vez y revisados a ojo. Esfuerzo S.
9. **Píldora de frase** (quitar el límite de 1 palabra cuando la píldora es de frase entera) y
   subtítulos a media altura (`y_position` < 0,40). Esfuerzo S-M en `subs_auto`.

### Futuro
10. Herramientas nuevas: barra de progreso, emojis en rótulos, tarjetas de lista/título, karaoke por
    barrido, música de fondo con ducking, b-roll de vídeo. Esfuerzo M cada una (L la música: licencias).
11. Medir SFX y barra de progreso sin IA; puntuar «parecido con la referencia» pasando el medidor por
    el resultado y comparando cifras (control de calidad automático del preset).

### Coste por análisis
- Hoy: 1 llamada de visión con una hoja de 24 fotogramas. El código documenta ~0,001 $ (docstring de
  `estilo_vip.py`) y ~0,002 $ (endpoint), con el modelo de `claude_client.modelo()` (por defecto Haiku;
  tarifa `claude-haiku-5-5` en `cost_tracking`: 0,10 / 0,50 $ por millón). El gasto real queda en
  `record_claude`.
- Con 3 referencias y la hoja de animación: ~4 imágenes en una llamada, del orden de 0,004-0,008 $
  (estimación, no medido). El medidor no cuesta dinero, solo CPU.
- El preset se analiza una vez y se reutiliza: aplicar un estilo guardado cuesta 0 $.
