# Tutorial «Genjutsu de Higgsfield: contenido viral para UGC» — 13 oct 2026 (TikTok Shop AI Pro, Jonny)

Fuente: [tutorial en Skool](https://www.skool.com/tiktokshopaipro/classroom/bd12442c?md=ba632bb17e334c61ac67734a21aa0b9b), **28:35**. Revisado con audio transcrito localmente con faster-whisper `small` y fotogramas de pantalla, ampliando los ajustes y los prompts. Los minutos siguientes son del tutorial, no de los clips de ejemplo. Las recomendaciones para nuestra app son análisis propio, separado de lo que enseña Jonny. La transcripción automática confunde nombres y algunas cifras; se contrastaron con la pantalla. No se conserva como transcripción literal del curso.

## Uso operativo y decisión de Néstor (13 oct 2026)

**Objetivo confirmado después del análisis:** una cuenta NUEVA de TikTok, en unos días, con menos vídeos y mayor calidad, para estos formatos virales. No se decidió arrancar en ness o Ana ni hay cuenta/plan de Higgsfield todavía. Conservar todo el procedimiento para futuros agentes es el encargo actual; generar vídeos no lo es.

**Guía completa:** [Genjutsu para agentes](../../src/agente_mcp/guias/genjutsu-higgsfield.md), también preparada en el MCP de la app con `guia("genjutsu")`. Incluye creación/variantes del personaje en Flow, producto y leyenda `@Imagen N`, prompts completos, preparación de referencia, rutas de voz, acabado, controles de calidad y plantilla de relevo. La ruta MCP de la app queda en este cambio del repo; no se ha desplegado.

**Conexión del proveedor:** MCP oficial `https://mcp.higgsfield.ai/mcp` registrado como `higgsfield` en Claude Code del VPS; verificado **Needs authentication**. El operador completa OAuth con su cuenta cuando exista. El plugin oficial para ChatGPT se encontró y se ofreció su conexión, pero no está autenticado. [MCP oficial](https://higgsfield.ai/mcp).

**Personajes:** Jonny muestra su personaje y variantes de ropa deportiva/gorra y pijama; al revisar ampliado el min 15:45 se ve el prompt de vestuario, Nano Banana Pro y un resultado en Flow; este vídeo no documenta la conversación completa de creación en Flow ni publica un prompt íntegro de ese paso. La guía completa ese hueco con el procedimiento existente del proyecto y lo distingue de los prompts literales del tutorial. No se atribuyen al curso frases inventadas.

## Resumen en una línea

**Social1 → descargar un viral → Higgsfield Genjutsu / Transferencia de movimiento + fotos de nuestro personaje y producto → cambiar escenario → rehacer o convertir la voz en Fish → editar en CapCut.** Lo nuevo es reutilizar la actuación y la cámara del vídeo, además de su idea o guion; no es otro generador desde una foto.

## Lo que se ve, por bloques

### 1. Ejemplos y presupuesto — min 0–5

- Compara original y réplica: misma acción y ritmo, otra persona y escenario. Enseña una fregona y una alfombra donde sustituye al hombre original por un personaje con pijama llamativo.
- Dice que Genjutsu es caro. Para **30 s**, explica **210 créditos a 720p** y **90 a 480p**. El botón «Generar 210» se ve al principio; después aparece «Generar 57» con la referencia de manta y calidad 480p (19 s × 3 créditos/s = 57, cálculo consistente con su explicación).
- Propone empezar con referencias de unos **20–30 s**, reducir la duración antes de subirlas y mejorar la resolución después. Su ejemplo verbal de 35 s a velocidad 1,1× es aproximado: **35 / 1,1 = 31,8 s**; para entrar realmente en 30 s hace falta al menos **1,167×** o cortar.
- Los planes se consultan en «Mejorar plan». Hay facturación mensual/anual y tamaños de paquete distintos; no confundir el precio anual por mes con pagar un mes suelto. Costes verificados hoy más abajo.

### 2. Buscar y preparar el vídeo — min 5–8

- En **Social1**, busca vídeos que ya funcionan; en pantalla aparecen país, fecha, rendimiento y filtros de contenido. Elige **contenido no IA** y **solo vídeos**: quiere replicar actuaciones reales, no volver a generar un vídeo que ya era IA. En pantalla se ve «Today» / «Trending»; usa España y después Alemania/EE. UU. buscando productos que también existan en España.
- Abre el contenido de referencia y descarga el MP4 sin marca en **SSSTik**. Lo importa en **CapCut** para preparar el tramo que irá a Genjutsu.
- La referencia debe encajar con el producto: las fotos adjuntas tienen que representar lo que queremos que salga, incluidas variantes y ángulos.

### 3. Generar y revisar en Genjutsu — min 8–10 y 14–19

La URL del generador que aparece es `https://higgsfield.ai/es/ai/video?model=genjutsu`.

1. **Crear vídeo → modelo Higgsfield Genjutsu → Transferencia de movimiento**. «Intercambio de objetos» aparece como otra opción; los ejemplos revisados indican Transferencia de movimiento en sus detalles.
2. Subir **el vídeo de referencia**, ya preparado.
3. Adjuntar las fotos y comprobar qué número tiene cada una. En las mantas: personaje = `@Imagen 1`; variantes rosa/gris/beige = `@Imagen 2`, `3`, `4`. En la alfombra se invierte: producto = `@Imagen 1`, personaje = `@Imagen 2`.
4. Activar **Prompt**, escribir el cambio de escenario, personaje y producto con las menciones: **teclear `@` y seleccionar la foto** del desplegable, no limitarse a escribir su nombre. Hay «Estilo / Aplicar», pero no se identifica un preset obligatorio para estos ejemplos.
5. **Calidad 480p o 720p**, según presupuesto. Antes de generar, leer el gasto del botón **Generar**. Un envío es una nueva generación; prever reintentos.
6. Abrir el resultado, comparar movimiento y producto, **Descargar**. «Recrear» sirve para otra versión; no implica que sea gratis.

| Ejemplo mostrado | Duración visible del resultado | Referencias / cambio | Detalles visibles |
|---|---:|---|---|
| Mantas de punto grueso | 19 s | Chica fija + tres colores de manta; otra habitación | Transferencia de movimiento; calidad 720p; tamaño indicado 576×1024 |
| Fregona | 29 s | Chica + fotos del producto; otro baño; petición de cambiar el tono de voz | Transferencia de movimiento; calidad 720p; 576×1024 |
| Máquina de ejercicio / escaladora | 11 s | Chica con ropa deportiva, aparato, pose; cambia salón y elimina textos | Transferencia de movimiento; calidad 720p; 576×1024 |
| Alfombra | 30 s | Alfombra gris + personaje en pijama; otro salón | Transferencia de movimiento; calidad 720p; 1080×1920 |
| Cojín cervical / viaje | 17 s | Chica + cojín gris en lugar del de leopardo; el escenario pasó del coche a una casa | Transferencia de movimiento; calidad 480p; 576×1024 |
| Botas | 16 s | Varias fotos del mismo botín para cambiar producto y ambiente | Transferencia de movimiento; calidad 480p; 1080×1920 |

**Resolución:** el panel muestra etiquetas de calidad y tamaños que no coinciden siempre. Estos son los valores de pantalla, no una medición de los MP4 de Jonny. En producción hay que comprobar el archivo con `ffprobe`; reescalar a 1080×1920 no garantiza detalle de 1080p.

### 4. Guion y voz — min 10–14 y 19–24

- Para la manta usa **Submagic**, «Generador online gratuito de transcripciones de TikTok», con el enlace del original.
- Pega la transcripción en **DeepSeek** para corregir el texto. Luego **Fish Audio → Text to Speech**, elige voz y genera/descarga la locución.
- En **CapCut**, importa el vídeo nuevo y el audio Fish; sustituye el sonido original y ajusta el montaje a la duración de la voz.
- Para una persona **hablando a cámara**, evita cambiar el guion: la boca ya sigue las palabras del original (min 22). En **CapCut → Exportar**, desmarca vídeo y deja solo audio; luego **Fish Audio → Voice Changer → Convert**: subir ese audio, elegir voz, convertir y descargar desde **History**. Esta vía busca cambiar el timbre conservando la interpretación/ritmo del original; no es lo mismo que volver a leer el texto con TTS.
- **CapCut → Filtros → buscar «4K»** (min 19–20:40): muestra cómo quitar la apariencia blanquecina del render. Prueba «8K», pero dice que suaviza demasiado la persona y prefiere «4K»; la intensidad se puede bajar. Es un filtro de apariencia, no recuperación comprobada de resolución.
- La alfombra le permite añadir un gancho visual al inicio y usar música/sonido sin una persona explicando a cámara. No todos los formatos necesitan voz hablada.

### 5. Plan de producción y cierre — min 24–28:35

- Jonny calcula un plan de **unas 30 piezas al mes**, redondeando el consumo de 30 s / 480p a 100 créditos por pieza: 3.000 créditos. Enseña también **Ultra 6.000 / 220 €/mes** y compara hacerlo a 720p o 480p. Son sus cifras orientativas, no 30 vídeos válidos garantizados después de reintentos.
- Espera amortizar el plan con un vídeo que consiga muchas ventas. Es su expectativa: ni un millón de vistas ni replicar un viral garantiza recuperar la inversión.
- Propone reutilizar también en **Instagram Shop**, buscando el mismo producto en Amazon afiliados; remite a una clase aparte para la vinculación. En nuestra fábrica ya existe la ruta Meta/Amazon/SHEIN: habría que casar el producto, enlace y CTA de cada cuenta, no subir una pieza con la CTA de carrito de TikTok tal cual.
- En el cierre recomienda mirar **consolas para Q4** y elegir referencias cortas: comprueba un vídeo de **22 s sin voz**, que propone acelerar a ~19 s y casar con el producto del marketplace. Es una idea de selección, no una compra ni muestra solicitada por nosotros.
- Distingue **dos voces** de **dos personajes**: en la referencia muda de la consola plantea cambiar a la niña y al hombre; lo que aconseja evitar es la conversión de dos voces que hablan.
- El cierre vuelve a Social1 para enseñar más ideas; no ejecuta una integración de app/MCP en este tutorial.

## Prompts literales

### Los tres publicados debajo del tutorial

«Promts utilizados en los Videos» es **texto dentro de Skool**, no un Google Doc ni PDF. En los tres publicados se conserva su redacción, faltas y espacios; en los de pantalla se transcribe el texto con espacios normalizados y se deshacen los saltos visuales de las menciones; las menciones se deben recrear en el editor con los adjuntos correctos.

**1. Personaje + producto + escenario + voz (fregona):**

```text
Cambia el escenario del video para que no sea igual al original respetando la idea principal del video. Utiliza el personaje @Imagen 1 y los productos @Imagen 2  cuando corresponda.  Tambien cambia el tono de voz de la chica.
```

**2. Personaje + colores de mantas:**

```text
Cambia el escenario del video para que no sea igual al original respetando la idea principal del video. Cambia al personaje por @Imagen 1  . Cambia los colores de las mantas por @Imagen 2  @Imagen 3  @Imagen 4
```

**3. Alfombra + personaje + salón, respetando movimientos:**

```text
Cambia al personaje del video por el personaje @Imagen 2. Cambia el color del producto por el producto @Imagen 1. Cambia el escenario de la casa por otro salon respetando la idea principal y movimientos del video a la perfección.
```

### Otros prompts completos visibles en pantalla

**Flow, variante del personaje — min 15:45 (foto de la chica adjunta, Nano Banana Pro, un resultado):**

```text
vistela con ropa negra de gym y gorra
```

**Escaladora / ejercicio — min 16:00:**

```text
Cambia el escenario del video para que no sea igual al original respetando la idea principal del video. Cambia al personaje por @Imagen 1 . Añade el producto @Imagen 2 . El personaje esta viendo la television. Elimina los textos del video.
```

**Cojín cervical — min 17:18 y 17:50 (incluye la errata «cogin»):**

```text
Cambia el escenario del video para que no sea igual al original respetando la idea principal del video. Cambia a la chica por @Imagen 1 . Cambia el cogin de leopardo por el cogin @Imagen 2
```

**Botas — min 18:30:**

```text
Cambia el escenario del video para que no sea igual al original respetando la idea principal del video. Cambia el producto por el @Imagen 1  @Imagen 2  @Imagen 3  @Imagen 4  @Imagen 5 .
```

**Borrador parcial en el cuadro del generador — min 18:00 (no confundir con un resultado validado):**

```text
Cambia al personaje del video por el personaje por @Imagen 2
```

**DeepSeek — min 10:38, petición de corrección del guion de la manta:**

```text
corrige este guion : no manches con el superdescuentazo que le acaban de colocar a esta frazada  queenside de medida 180x220  lo mejor de todo es que tienes 1 montón de colores  para elegir y es que tan solo checa su diseño acanalado  se ve superbonito y está muy pachoncita  así que si te interesa aprovecha ahora mismo y pídela en el carrito naranja  con 1 superdescuento y envío totalmente gratis
```

Este último es el **ejemplo de Jonny**, no un guion aprobado para nuestra ficha. No trasladar descuentos, envío gratis, medidas ni expresiones regionales sin comprobar que proceden en el producto y la cuenta. La promesa de cambiar el tono de voz en el prompt de la fregona tampoco demuestra por sí sola control fiable de voz: **confirma que la prueba no le cambió la voz** y acaba creando otra en Fish (min 14:23–14:31).

## Tips de Jonny y límites observados

- **Partir de vídeo real ya validado** (min 5:30), no recrear una pieza que ya era IA. Es su criterio de selección, no una garantía de que nuestra versión venda.
- **Usar los colores que de verdad se venden** (min 8–9): el viral de las mantas enseñaba variantes que no existían en la ficha de TikTok Shop. Comprueba la ficha y adjunta las capturas de los colores disponibles.
- **Vestir el personaje para la actuación** (min 15:30–16): en Flow adjunta su chica, escribe «vistela con ropa negra de gym y gorra», Nano Banana Pro, ×1, para la escaladora; para la alfombra crea variantes con pijama hasta elegir una llamativa. No necesita una identidad distinta en cada producto.
- **Especificar el entorno** (min 17:18–18): al pedir solo cambiar escenario, el cojín que se usaba en un coche acabó en una casa. Si el uso depende del coche, pedir explícitamente otro coche.
- **Ahorrar segundos antes del render** (min 4:30–7:30): empezar con 20–30 s y acelerar un poco cuando la acción lo permita. No convertir una demostración en algo ilegible por ahorrar créditos.
- **480p + retoque posterior** (min 3:30–4:25 y 19–20:40): upscale en Higgsfield o filtro «4K» de CapCut; «8K» le resulta excesivo. No confundir la etiqueta del filtro con resolución nativa.
- **Voz en off y persona hablando no se tratan igual** (min 9:30–14): considera dejar una voz en off genérica, o sustituirla con Fish; si hay persona hablando, prefiere cambiar la voz. Para nosotros, mantener la sincronía labial forma parte de la revisión.
- **Elegir una sola voz** (min 20:40–21:30): se equivocó al escoger una pieza con dos personas hablando. Cambiar timbres por tramos complica mucho la edición; recomienda evitarla.
- **Si se ve la boca, conservar las palabras y tiempos** (min 22): usa conversión de voz en lugar de escribir otro guion; si la ficha obliga a cambiar afirmaciones, esa referencia no sirve sin rehacer también la sincronía labial. Esta última condición es nuestro criterio de revisión.
- **«Cambia el tono de voz» no le funcionó** (min 14:23–14:31): el texto del prompt de la fregona se conserva como ejemplo, pero resuelve el audio fuera de Genjutsu.
- **Cuadrar duración antes de exportar** (min 11–13): silenciar/eliminar el audio original al sustituirlo, comprobar los segundos de la voz Fish, ajustar velocidad, recortar aire/final sobrante y revisar volumen.
- **Buscar también Alemania y EE. UU.** (min 14:40–17): usa una demostración alemana de ejercicio y ejemplos de EE. UU./Instagram, comprobando que el producto exista en España. No equivale a intercambiar cualquier aparato parecido.
- **No comenzar con vídeos de dos minutos** (min 13:30): encarecen los intentos. Primero contenido corto con potencial de ventas; reinvertir después en un plan mayor.


## ¿Nos sirve? Comparación con lo que ya tenemos

| Lo existente | Qué hace hoy | Qué añadiría este flujo |
|---|---|---|
| **🔁 Replicar viral** (`src/replicar_viral/servicio.py`) | tikwm baja el original; Gemini ve imagen y audio, analiza escenas y devuelve guion Fish de ~16 s + prompts de dos clips mudos de 8 s. No renderiza el movimiento del original | Usar el vídeo como entrada del render para conservar acción, cámara y tiempos, con otra persona/producto/escenario |
| **POV BOF Largo** | Clips mudos + guion por producto + Fish; montaje con subtítulos, nombre, CTA y limpieza de metadatos. Ya existe estilo `viral` y `/replica/anadir` | Mejor material visual para voz en off; duraciones reales de 19–30 s necesitan ajustar huecos y guion, no subir el nuevo vídeo esperando que mantenga su audio |
| **Nicho General · UGC** | Tres escenas habladas (o más por mínimo de tienda), con el mismo personaje; imágenes y prompts por escena | Actuación continua y cambios de plano que siguen una referencia en vez de tres actuaciones generadas por separado. Su montaje no es todavía una entrada genérica para cualquier clip de 30 s |
| **Moda Mujer · Multimodo (Ana)** | Seis formatos hablados con personaje de cuenta, Omni y voz dentro del clip; montaje conserva audio y añade subtítulos | Réplicas de demostraciones de ropa/bolsos con gestos conocidos. Es el encaje más directo para preservar personaje y voz hablada |
| **Social1 / carruseles** | Búsqueda ya operativa con proxy residencial y catálogos de candidatos; réplica de diapositivas y distribución Meta | Reutilizar la búsqueda para vídeos y registrar referencias, sin duplicar el replicador de fotos |
| **GenAI Pro / Magnific / Flow** | Acuerdo del encargo: vídeo en GenAI Pro Omni, Magnific de respaldo y Flow para imágenes | Higgsfield sería una herramienta adicional para editar desde vídeo, no un reemplazo general de esas plataformas |

**Hallazgo de código:** el estilo `viral` y `/replica/anadir` ya están implementados en `src/api/routers/nicho_pov_bof_largo/productos.py`; la tarea antigua que los marca pendientes está desactualizada. No se ha cambiado su estado en este análisis. `src/nicho_general/pipeline/video_editor.py` conserva el audio y concatena clips, pero no garantiza por sí solo los subtítulos y el nombre de producto exigidos por el estándar actual: cualquier integración debe verificar esas salidas, no darlo por resuelto por usar UGC.

La guía `comun/plataformas.md` es más reciente que partes de `ugc.md` y `pov-bof-largo.md`: menciona **Omni 1.1 de GenAI Pro**, 10 s, 1080p, 1 crédito con marca. Para este plan manda el acuerdo del relevo: **Flow solo imágenes**. El servicio Fish revisado (`src/nicho_pov_bof_largo/services/voz.py`) es locución de texto; el **Voice Changer** del tutorial necesitaría una integración diferente. Los créditos de GenAI Pro y Higgsfield son unidades de plataformas distintas; «1» y «57» no se pueden comparar como euros sin el precio de cada plan.

### Cuenta y prioridad: intención confirmada del operador

- **Destino principal:** cuenta nueva, todavía sin nombre ni personaje elegido; menos vídeos y mayor calidad. Preparar ficha, referencias, identidad y planes para que futuros agentes los ejecuten cuando haya acceso y presupuesto.
- **Calidad:** el 480p del tutorial es una opción de ahorro. Para esta cuenta no se fija como defecto: revisar 720p/1080p y su coste antes de generar; un filtro «4K» no convierte el detalle en resolución nativa.
- **ness/Ana:** son ejemplos de encaje con lo existente, no destinos autorizados de una prueba. Ana podría reutilizar la ruta hablada con su personaje; el Largo sirve para voz en off. No trasladar las marcas, identidad o ritmo diario de esas cuentas a la nueva.
- **Estado de la nueva cuenta:** no asumir acceso a TikTok Shop/carrito, ni identificarla con la cuenta piloto existente; adaptar la CTA al destino real cuando se publique.

## Coste: tutorial, web actual y presupuesto de prueba

**Visto/explicado en el tutorial:** 30 s a 720p = 210 créditos; 30 s a 480p = 90. En la composición de la manta a 480p aparece 57, consistente con 19 s. Para 480p explica mejorar después: upscale en Higgsfield, que hay que presupuestar aparte, o retoque en CapCut. No se ha generado nada ni gastado créditos en este análisis.

**[Precios oficiales](https://higgsfield.ai/pricing), comprobados en Chrome el 13/10/2026 (EUR, sin IVA):**

| Plan | Créditos/mes | Pago mensual | Precio por mes con pago anual | Promoción Genjutsu incluida mostrada |
|---|---:|---:|---:|---|
| Starter | 270 | 19 € | 19 € | No; acceso limitado, no elegir para esta prueba sin confirmar disponibilidad |
| Plus | 1.200 | 59 € | 47 € | 2 generaciones 720p en mensual; 3 en anual |
| Ultra, paquete base | 3.000 | 129 € | 99 € | 2 generaciones 720p en mensual; 3 en anual |

Las generaciones gratis de los planes son de la web, **no de MCP/CLI, Canvas o Supercomputer**. No equivale a una cuenta gratuita con Genjutsu, ni se verificó que las promociones se renueven cada mes. Los paquetes Ultra mayores cambian precio; Jonny enseña también uno de 6.000 créditos. El checkout decide impuestos, región y oferta final.

**Cálculo propio**, usando los consumos que explica el tutorial y consumiendo íntegro el paquete mensual Plus (59 / 1.200 = 0,0492 €/crédito):

| Una generación | Créditos estimados | Parte proporcional de Plus | Máximo teórico con 1.200 cr |
|---|---:|---:|---:|
| 19 s, 480p | 57 | 2,80 € | 21 |
| 30 s, 480p | 90 | 4,43 € | 13 |
| 30 s, 720p | 210 | 10,33 € | 5 |

No son cargos por vídeo ni garantizan tarifa actual: **hay que leer el botón del generador antes de gastar**, y si se usa poco el plan, el coste por vídeo válido sube. Una prueba de **3 vídeos de 20 s, 480p, hasta 2 intentos cada uno** sería aproximadamente **360 créditos / 17,70 € de capacidad del Plus**, pero obliga a pagar el plan completo si no se tiene. No incluye upscale, Fish, Social1 ni edición. Para un flujo de 20 vídeos diarios, 600 × 60 = **36.000 créditos/mes**, sin reintentos: no encaja en Plus/Ultra base.

**Fish, aparte:** Jonny menciona 8.000 créditos gratis y usa la voz «Arnold» como ejemplo en inglés. La [guía oficial de Voice Changer](https://fish.audio/es/blog/how-to-use-ai-voice-changer/?articleLocale=en) tarifa la conversión a **3.000 créditos/minuto**, cobrada por segundo: 20 s = 1.000; 30 s = 1.500. Los [planes web de Fish](https://fish.audio/plan/) muestran 8.000 créditos mensuales gratuitos y Plus de 250.000 por 15 USD/mes. Con 8.000 sin consumir caben cinco conversiones de 30 s (7.500); no es audio ilimitado. No se ha comprobado el saldo del operador y esto no es la tarifa de TTS/API que usa nuestra app.

Como contraste, la [guía oficial de Genjutsu](https://higgsfield.ai/blog/higgsfield-genjutsu) publica precios de septiembre: 15 s = 40 cr a 480p, 104 a 720p y 144 a 1080p. Difieren de extrapolar exactamente los ejemplos de Jonny. No se deben mezclar ambas tablas como una tarifa garantizada; la cotización del generador manda. La [página oficial de Genjutsu](https://higgsfield.ai/genjutsu) describe dos modos y referencias de personaje/producto, con vídeos de 3 a 30 s y hasta 40 imágenes de referencia; sus límites también pueden cambiar.

## Plan para la app / MCP (propuesta, sin implementar)

1. **Preparación para futuros agentes, sin generar ahora:** usar la guía operativa y registrar referencias/productos/personaje de la cuenta nueva; 20–30 s aprox.; escoger la ruta de audio; presupuesto máximo de créditos e intentos aprobado por Néstor. Registrar tiempo de trabajo y coste por vídeo **válido**, además de resultado visual y audio. Medir producto, movimiento, boca/voz, texto, deformaciones y diferencias entre versiones.
2. **Ampliar «Replicar viral», no crear un programa aparte:** mantener la adaptación actual a dos clips/Fish; añadir un plan alternativo de transferencia con referencia original, tramo, velocidad, fotos numeradas, personaje, prompt literal, voz y gasto previsto. Cualquier cambio de prompts, schema o integración queda pendiente de aprobación y debe acompañarse de tipos/API/doc.
3. **Preparar automáticamente los insumos:** reutilizar tikwm, `ffprobe` y FFmpeg; recortar/acelerar a ≤30 s sin cortar la demostración; reunir fotos correctas y producir un mapa `@Imagen N` revisable. No importar guiones de otro producto sin contrastarlos con nuestra ficha.
4. **Generación futura por MCP oficial o navegador, con autorización de gasto:** adjuntar referencia y fotos, elegir Transferencia/calidad acordada, comprobar el coste antes de enviar; descargar y revisar. Valorar API aparte: la [documentación oficial de Object Swap](https://open.higgsfield.ai/models/workflows/genjutsu/object-swap/playground) expone vídeo, imágenes, prompt y resolución, pero no valida el acceso ni los costes de nuestro plan web. No asumir que los créditos/promos de navegador sirven por API.
5. **Dos rutas claras de montaje:** voz en off nueva → Fish/Largo; persona hablando → preservar audio o conversión de voz que mantenga tiempos y montar como hablado. El montaje debe producir subtítulos del texto realmente locutado, nombre de producto y metadatos limpios, y pasar revisión antes de entrar en Mis tandas. Mantener `ai_disclosure` al publicar.
6. **MCP y guía en el mismo cambio:** exponer preparación, estado, descarga/subida y montaje desde el menú existente, con restricciones de usuario; documentar selección de referencias, orden de fotos y revisión. Si se usa API de pago, `record_*` con consumo real; si se trabaja por navegador, registrar el gasto de plataforma sin inventar tokens/API.
7. **Cuenta nueva: menos piezas y calidad revisada:** priorizar demostraciones que Omni desde foto no resuelve; no trasladar el objetivo de volumen diario de ness a esta cuenta. Higgsfield tiene sentido como recurso selectivo, no como compra automática para toda la fábrica.

## Fuentes y comprobación

- Tutorial de Skool y texto «Promts utilizados en los Videos», revisados con sesión del operador; enlaces debajo: [Higgsfield](https://higgsfield.ai/es?fpr=mk), [Social1](https://www.social1.ai/?ref=esp), [DeepSeek](https://chat.deepseek.com/), [Fish Audio](https://fish.audio/).
- Código y guías locales: `src/replicar_viral/servicio.py`, `src/api/routers/nicho_pov_bof_largo/productos.py`, `src/nicho_general/pipeline/video_editor.py`, `src/agente_mcp/guias/replicar-viral.md`, `ugc.md`, `pov-bof-largo.md`, `moda-mujer-multimodo.md`, `comun/plataformas.md`; relevo `~/relevos/vps-tiktok-carruseles-virales.md`.
- No se han comprado planes, creado cuentas, generado contenido, modificado prompts de producción ni hecho commit/push. El vídeo, audio de trabajo, fotogramas y transcripción temporal se eliminan al terminar; queda este análisis.

## Repaso del agente jefe (13/10, transcripción propia con Whisper)

Lo que faltaba o conviene dejar más claro, con minuto de la transcripción:

- **Próximo tutorial (28:03-28:11):** «también se puede replicar contenido de [IA], estructura de contenido, pero eso lo veremos en otro vídeo» (Whisper lo oye como «con mi flat»: según Néstor es **Omni**). Este tutorial cubre réplicas de vídeos REALES; el de vídeos hechos con IA va a salir aparte → analizarlo cuando salga.
- **Duración máxima (4:35, 13:29-13:54, 27:42-27:54):** el primer mes, réplicas de **20-30 s como máximo**, «muy validadas». Nada de vídeos de 2 min hasta que lo pague una venta. Si el viral dura 35 s, se le sube la velocidad hasta dejarlo en 30.
- **Cuadrar voz y vídeo (10:53-11:26):** al locutar con Fish, mirar los segundos de la voz frente al vídeo (ejemplo: voz de 19 s y vídeo de 17). Hay dos salidas: **bajar la velocidad** del vídeo o **recortar el guion**. Si es al revés, se acelera el vídeo. En nuestra app esto lo hace la escalera de CTA del Largo (`config.ctas_posibles` + acelerón ≤×1.10).
- **Fish Voice Changer (22:13-23:49):** SOLO cuando la persona habla a cámara (con la boca visible no se puede cambiar el guion). Se exporta el audio en CapCut, en Fish se pasa por Voice Changer (él usa «Arnold» para inglés) y se pegan los dos para comparar: «es el mismo audio pero con diferente voz». Fish da **8.000 créditos gratis por cuenta**. Con voz en off es mejor un guion nuevo con TTS. **Evitar vídeos con dos voces.**
- **Filtro «4K» de CapCut (4:00-4:21, 19:03-20:34):** quita la «neblina de vídeo de IA». El 8K es demasiado agresivo (alisa la piel), así que se usa el 4K. Es la alternativa barata a renderizar a 720p o a pagar el upscale. **En nuestro editor** (propuesta en `tasks.md`, sin implementar): paso opcional al normalizar con lanczos + `hqdn3d` suave + `unsharp` + un poco de contraste/saturación, validado lado a lado con CapCut.
- **Planes (2:49-3:35, 24:03-24:44):**
  - En Higgsfield: Plus anual 1.200 cr; mensual ~50 € 2.200 cr; 3.000 cr ~130 €; Ultra 6.000 cr **220 €**.
  - Consumo: 30 s a 480p = 90 cr (redondea a 100) y a 720p = 210.
  - Cuentas de Jonny: 3.000 cr ≈ 30 vídeos a 480p y 6.000 ≈ 60. A 720p, la mitad.
  - Él lo plantea como inversión que se recupera con un viral.

### Decisión de Néstor tras el repaso
- **Destino: Casca Chollos** (la cuenta piloto, sale del modo piloto ~19/10; publicar mejor a los 30 días, pero ir preparando). Réplicas de máxima calidad, de vídeos reales y de vídeos con IA, aunque sea sin el personaje del cascanueces. ness (POV), Ana (moda) y Mauro (POV, menos vídeos) **no cambian de formato**: los cambios de estilo les bajan el alcance.
- **Primero Omni 1.1 de GenAI Pro** (1 crédito el clip). Higgsfield (≈60 vídeos a 480p por 220 €) solo cuando un viral dé dinero.
- **App:** menú + MCP «Replicar virales» con dos modos (sin IA / con IA) que acabe en Mis tandas. Más adelante, un usuario propio para la cuenta (tipo `nestor_viral`). Tareas en `tasks.md`.
