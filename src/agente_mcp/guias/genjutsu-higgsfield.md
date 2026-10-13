# Genjutsu de Higgsfield — receta completa para agentes

> **Encargo de Néstor, 13/10/2026:** preparar una cuenta NUEVA de TikTok, en unos días, para publicar menos vídeos y con mayor calidad, usando referencias virales. Esta guía deja el procedimiento listo para quien haga el trabajo después. No se ha creado esa cuenta, personaje ni vídeo, ni se ha comprado Higgsfield. Nombre de cuenta, personaje, productos, frecuencia y presupuesto siguen sin fijarse.
>
> **Fuente del curso:** «Genjutsu de Higgsfield: contenido viral para UGC», Jonny, Skool, 28:35. Análisis y **nueve bloques de prompts literales**: `docs/clases/2026-10-13_tutorial_genjutsu_higgsfield.md` en el repo. [Tutorial](https://www.skool.com/tiktokshopaipro/classroom/bd12442c?md=ba632bb17e334c61ac67734a21aa0b9b).
>
> **Leyenda de origen:** **TUTORIAL** = observado/explicado por Jonny; **PROYECTO** = procedimiento de nuestras guías existentes; **RECETA** = instrucciones operativas que completan lo anterior, no un prompt literal de Jonny; **PENDIENTE** = acceso o implementación sin verificar. No presentar una receta nuestra como una cita del curso.

> **Repaso 13/10 (decisión de Néstor, manda sobre lo de abajo):**
> - La cuenta nueva es **Casca Chollos**: réplicas virales de máxima calidad, aunque sea sin el personaje del cascanueces. Sale del modo piloto hacia el 19/10; conviene publicar a los 30 días, pero se van preparando vídeos.
> - **Primero se prueba con Omni 1.1 de GenAI Pro** (1 crédito el clip). Higgsfield solo se usa cuando un viral dé dinero.
> - Máximo 20-30 s por réplica. Nada de vídeos con dos voces.
> - Fish Voice Changer solo para quien habla a cámara; con voz en off, guion nuevo con TTS.
> - Jonny sacará otro tutorial (Omni) para replicar vídeos hechos CON IA.
> - Detalle con minutos en el doc de clases, sección «Repaso del agente jefe».

## 0. Leer y situarse

Lee `comun/navegador-vps.md`, `comun/plataformas.md` y `comun/revision-calidad.md`. Para Social1 desde el VPS, también `comun/navegador-proxy-es.md`. Usa una pestaña propia, registra entrada/salida y no cierres pestañas ajenas.

Esta ruta **no es la réplica POV de dos clips de 8 s**. En ella, un vídeo REAL entra en **Higgsfield Genjutsu / Transferencia de movimiento** y sale otra actuación que conserva el movimiento. No usar `replicar_viral` esperando que renderice el vídeo o que conserve esa actuación: esa herramienta devuelve textos/prompts para nuestro formato anterior.

Plataformas de este flujo: **Flow = imágenes del personaje y variantes; Higgsfield = transferencia desde vídeo; Fish = voz; CapCut o montaje local = edición**. GenAI Pro/Magnific siguen sirviendo para otros formatos; no sustituyen automáticamente esta operación de Genjutsu.

El permiso actual cubre documentación y preparar la conexión MCP. **No autoriza generar, comprar planes o publicar.** En un encargo futuro reutiliza las autorizaciones que dé el operador y registra cantidad, plataforma, calidad y máximo de intentos. No volver a pedirlas si ya están claras.

## 1. La ficha del producto: antes de buscar el render

**TUTORIAL (8–9 min):** el viral de mantas enseña colores que no aparecen en la ficha del producto. Jonny captura los colores reales de TikTok Shop y los adjunta; no copia sin más las mantas del original.

**RECETA:** crear `PLAN.md` con estos datos:

- Cuenta destino y usuario/catálogo/producto de la app, si ya está dado de alta. La cuenta nueva no se llama automáticamente `ness`, `ana` ni `mauro`.
- Título EXACTO, URL de ficha de TikTok Shop cuando exista, marca/modelo y vendedor; estado de enlace/stock revisado y fecha de comprobación.
- Fotos limpias: frente, lados/detalles funcionales y variantes que realmente se venden. Captura de la ficha para validar las afirmaciones.
- Qué cambia respecto al vídeo viral: producto completo, solo color, atuendo, persona y escenario. Lo que se conserva: acción, función demostrada, cortes y tiempos.
- Guion/transcripción del original y qué frases encajan con nuestra ficha. No afirmar precio, descuento, envío, medidas o resultados que la ficha no justifique.

Si ya está en la app, consultar `productos`/`ver_producto` y usar sus fotos/ficha. No llamar a servicios de pago para descubrir o extraer fichas sin autorización de ese gasto.

**Ejemplos del curso:** mantas rosa/gris/beige; fregona y sus piezas; escaladora; alfombra gris; cojín cervical; botín con cremallera. Estos ejemplos no son productos aprobados para la cuenta nueva: hay que casar la referencia con el producto elegido.

## 2. Elegir el viral que se puede trasladar

**TUTORIAL (5–8 y 14–18 min):** Social1 → país España; también Alemania y EE. UU.; **contenido NO IA → solo vídeos**. Se ven filtros `Today` / `Trending`. Busca actuaciones reales con potencial ya observado y productos disponibles en España. Un ejemplo alemán de ejercicio tiene unos 10 M de vistas; la cifra sola no prueba ventas de nuestra versión.

**RECETA de selección:**

1. Abrir el vídeo y mirarlo entero: gancho, acción, producto, voz, boca, textos y cambios de plano. Guardar URL, autor, fecha, duración y métricas disponibles, distinguiendo vistas de conversiones.
2. Preferir **20–30 s**, demostración clara y un producto que podamos representar con nuestras fotos. Los clips del curso duran 11, 16, 17, 19, 29 o 30 s.
3. Para alguien hablando, preferir **una sola voz**. Dos personas mudas no son el problema; dos interlocutores hablando complican la conversión de audio.
4. Elegir desde el principio una ruta: `mudo/música`, `voz_en_off` o `hablado_a_camara`. Se edita de forma distinta en el paso 7.
5. Comprobar que el producto y su uso son compatibles. Si un aparato/tejido necesita deformarse para copiar la acción de otro, buscar otra referencia.
6. Si el guion hablado contiene datos incompatibles, elegir otro original. Con la boca visible no basta con reemplazar las palabras y poner otra voz.

Para Social1 en VPS, usar el navegador/proxy de su guía; no imprimir credenciales del proxy ni crear otra cuenta/prueba. Si el acceso actual ha caducado, preparar los candidatos ya disponibles o trabajar con los enlaces que dé el operador.

**Destino nuevo:** no asumir que TikTok Shop o carrito están habilitados. Para contenido orgánico, no quemar una CTA al carrito que el vídeo no tiene; la CTA depende de la publicación autorizada.

## 3. Descargar y preparar la referencia

**TUTORIAL:** copiar enlace → SSSTik → descarga sin marca → CapCut. Si dura más de lo deseado, subir un poco la velocidad antes de mandarlo a Genjutsu, para consumir menos segundos.

**PROYECTO:** desde el VPS ya existe `src/replicar_viral/servicio.py:descargar_tiktok`, que usa tikwm. Puede reutilizarse para bajar la referencia sin ejecutar `replicar` ni llamar a Gemini. También se puede subir el MP4 autorizado. Rechazar un enlace de carrusel: no es entrada de vídeo.

**RECETA:** guardar `referencia_original.mp4` y medir antes de editar:

```bash
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of json referencia_original.mp4
```

Elegir tramo que conserve la demostración completa. Guardar inicio, fin y velocidad en `PLAN.md`. La duración máxima se comprueba en el generador actual; el tutorial trabaja hasta 30 s.

**Cuenta exacta:** duración nueva = duración del tramo / velocidad. Para 35 s → 30 s, velocidad ≥1,167×. El 1,1× que Jonny dice como ejemplo dejaría 31,8 s. No cortar el final ni acelerar una acción que ya va demasiado rápida.

Ejemplo local: 35 s de referencia → aproximadamente 30 s, con vídeo y audio acelerados juntos. Es una receta nuestra; comprobar la duración real del resultado antes de subirlo.

```bash
ffmpeg -nostdin -i referencia_original.mp4 -vf 'setpts=PTS/1.167' -af 'atempo=1.167' -c:v libx264 -crf 18 -c:a aac referencia_preparada.mp4
```

Si no tiene pista de audio, omitir `-af` y usar `-an`. Si solo hace falta recortar, hacerlo sin el acelerón. No mandar al render dos minutos esperando el mismo coste que 20 s.

## 4. Crear el personaje en Flow y mantenerlo

### 4a. Qué sabemos del tutorial

**TUTORIAL (15:30–17):** en Flow Jonny adjunta una miniatura de SU chica de cuerpo entero con ropa clara; el cuadro muestra el prompt **«vistela con ropa negra de gym y gorra»**, modelo **Nano Banana Pro**, **×1** y modo/interfaz **Agente**. En su biblioteca se ven las variantes con ropa negra/gorra sobre fondo blanco. Le cambia el atuendo a ropa deportiva/gorra para la escaladora y crea variantes de pijama hasta escoger una llamativa para la alfombra. Mantiene el personaje como referencia y lo menciona en el prompt de Genjutsu.

**Límite del registro:** se ve el prompt completo de CAMBIO DE ROPA, pero no toda la conversación ni el prompt inicial de creación de identidad desde cero. No confundir ambos pasos. No inventar uno «literal de Jonny». La receta siguiente completa ese paso con el procedimiento de personaje ya documentado en nuestro proyecto.

### 4b. Crear la referencia base una vez

**PROYECTO:** `ugc.md`, «Paso 0 · Crear tu personaje»; prompt existente `src/nicho_general/prompts/personaje.md`; descripciones ya preparadas en `src/nicho_general/prompts/personajes/`. No modificar esos prompts de producción para hacer este trabajo.

1. Si la cuenta ya tiene personaje aprobado, descargarlo y reutilizarlo. No sustituirlo por Lucía, por una cara de ness ni por otro personaje de la app.
2. Si todavía no existe, preparar para el operador la propuesta de personaje y su voz: adulto, apariencia, pelo/rasgos y estilo que encajen con el producto. La imagen que se acepte será la identidad de la cuenta.
3. La receta existente toma una referencia de persona y usa **«Copiar prompt de personaje»** en UGC; la pasa a Gemini con esa imagen para obtener una descripción independiente. Gemini solo redacta; **la imagen se hace en Flow**. No asumir que tenemos permiso para esa llamada de pago.
4. Alternativa sin otra llamada: reutilizar una descripción de personaje existente elegida/aprobada, o redactar una descripción propia. Etiquetarla como **RECETA**, nunca como prompt literal del tutorial. No usar la cara del creador del vídeo viral como nueva identidad de la cuenta.
5. En Flow, abrir un proyecto nuevo para esa cuenta, **Crear imagen → Nano Banana 2 → 9:16 → un resultado**. Revisar esos ajustes después de una recarga: puede volver a horizontal o modo vídeo.
6. Pegar la descripción: cuerpo entero de cabeza a pies, postura frontal natural, fondo blanco, luz uniforme, fotografía realista; manos visibles y vacías, sin texto/marca. Si ya existe imagen base, adjuntarla como referencia de identidad.
7. Generar solo dentro del presupuesto autorizado. Revisar cara, manos, cuerpo, ropa y encuadre; descargar `personaje_base.png`. La miniatura o el prompt no bastan: guardar la imagen aprobada y el texto exacto usado.
8. Guardar en `PERSONAJE.md`: imagen aprobada, descripción estable, fecha, cuenta destino, voz/lengua y qué variantes pertenecen a la misma identidad.

### 4c. Vestir al MISMO personaje para la actuación

**TUTORIAL, variante literal de vestuario:** adjuntar la chica base y usar el prompt corto de Flow que se copia en el paso 5. Nano Banana Pro/×1 es lo que aparece en su pantalla; Nano Banana 2 es la opción actual que establecen nuestras guías. Comprobar el modelo disponible/coste del encargo, sin atribuirle a Jonny la selección de NB2.

**RECETA operativa inspirada en los ejemplos, no cita del curso:** adjuntar `personaje_base.png` en Flow, modo imagen; mantener la conversación y pedir la variante de ropa. Ejemplo:

```text
Mantén exactamente la identidad del personaje de la imagen adjunta: mismo rostro, cabello, edad aparente y proporciones. Cambia solo el atuendo a ropa deportiva y una gorra, adecuado para una demostración de ejercicio. Fotografía fotorrealista de cuerpo entero, de cabeza a pies, postura natural, manos visibles y vacías, fondo blanco, luz uniforme, formato vertical 9:16. Sin texto ni marcas de agua.
```

Para el caso de alfombra, cambiar únicamente el atuendo a **pijama** acorde con el concepto. Jonny prueba varias opciones; eso son imágenes nuevas y hay que contarlas en el presupuesto. No copiar automáticamente Batman u otro estampado concreto solo porque aparece en su ejemplo.

Revisar **misma persona** frente a la base antes de aceptarla. Guardar `personaje_gym.png` o `personaje_pijama.png` y su prompt. Adjuntar en Higgsfield la variante final, no todas las pruebas rechazadas ni una imagen donde aparezca otro producto.

En este flujo **no hace falta generar en Flow una imagen inicial de cada plano del vídeo**: Genjutsu recibe el vídeo y las referencias. Crear fotos de escenario/producto adicionales solo cuando el plan las necesita.

## 5. Leyenda de imágenes: imprescindible en cada producto

Los números dependen del **orden real de adjuntos de esa generación**. No existe una regla global «Imagen 1 siempre personaje». Teclear `@` y elegir la referencia en el desplegable de Higgsfield; volver a comprobar las menciones si se quita o reordena una foto.

| Caso del tutorial | `@Imagen 1` | `@Imagen 2` | Otras | Prompt que se usa |
|---|---|---|---|---|
| Mantas | Personaje | Manta rosa | `3` gris, `4` beige/marrón claro | Mantas/colores |
| Fregona | Personaje | Producto | Más fotos de piezas/ángulos si ayudan; no afirmar que el prompt las menciona todas | Personaje + producto + escenario |
| Escaladora | Personaje deportivo | Máquina | Se ve una referencia de pose; registrar su papel si se adjunta | Añadir máquina, ver TV, eliminar textos |
| Alfombra | Alfombra gris | Personaje en pijama | Se ve también referencia original | Alfombra + personaje + salón |
| Cojín | Personaje | Cojín nuevo | Vídeo original de uso en coche | Cojín; concretar otro coche para evitar el error observado |
| Botas | Producto | Otra vista del producto | `3`, `4`, `5`: otras referencias del mismo botín | Cambiar producto; no necesita una cara nueva si no sale |

Estas son las **menciones legibles** del curso. Que haya varias miniaturas no demuestra que todas sean imágenes subidas: el panel puede enseñar también la referencia de vídeo. En la escaladora/botas no inventar el contenido de una miniatura que no se identifica claramente.

Ejemplo de leyenda propia en `PLAN.md`:

```text
@Imagen 1 → personaje_gym.png → identidad y atuendo, NO producto
@Imagen 2 → producto_frente.jpg → modelo y color exactos del catálogo
@Imagen 3 → producto_detalle.jpg → pieza/función que aparece en el vídeo
referencia_preparada.mp4 → actuación, cámara y cortes; 22,0 s
Escenario nuevo → otro salón doméstico, conserva el uso frente a una TV
Audio → música / voz en off / persona hablando (elegir UNO)
```

Seleccionar el prompt que corresponde y copiarlo **entero**, adaptar las menciones a esta leyenda y concretar el escenario. No usar la frase «cambia el tono de voz» esperando que funcione: Jonny prueba eso y termina resolviéndolo en Fish.

### Prompts del curso: copia completa

#### Los tres publicados debajo del tutorial

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

#### Otros prompts completos visibles en pantalla

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

## 6. Higgsfield: MCP primero si está autorizado; web como alternativa

### Estado de conexión (13 oct 2026)

**MCP oficial:** `https://mcp.higgsfield.ai/mcp`, publicado en [Higgsfield MCP](https://higgsfield.ai/mcp).

En **Claude Code del VPS** ya se registró con:

```bash
claude mcp add --transport http --scope user higgsfield https://mcp.higgsfield.ai/mcp
```

Se guarda fuera del repo, en la configuración de usuario de Claude; no lleva una API key. **Estado comprobado: `Needs authentication`**, no conectado a una cuenta. Cuando exista la cuenta del operador, este abre Claude Code, usa `/mcp`, selecciona Higgsfield y completa la autenticación en su navegador. Después verificar `claude mcp get higgsfield`. Nunca pegar contraseñas/códigos/tokens en el chat ni fingir que registrar la URL ya autenticó el servicio.

En **Claude web/Desktop**, el operador añade un conector llamado Higgsfield con esa misma URL y autoriza su cuenta. La configuración del VPS no modifica automáticamente su aplicación de escritorio. En ChatGPT existe el plugin oficial Higgsfield; se localizó y se ofreció su conexión, pero **no quedó autenticado**. [Instrucciones oficiales](https://higgsfield.ai/blog/generate-ai-videos-ai-agents-2026).

### Usarlo después de autenticarse

**RECETA:**

1. Descubrir las herramientas y sus schemas reales. Esta documentación no fija nombres internos sin haber leído el `tools/list` autenticado. `/genjutsu` es el comando/flujo anunciado por Higgsfield, no un nombre de función MCP que se deba inventar.
2. Subir vídeo e imágenes a los Assets por las herramientas que ofrezca; guardar sus IDs y la leyenda. Una ruta del VPS no es una URL que el servidor remoto pueda leer.
3. Pedir **Genjutsu → Motion Transfer**, referencia preparada, fotos correctas, prompt completo, calidad acordada y presupuesto. Desactivar la elección automática de otro modelo: no queremos un generador de vídeo desde foto.
4. Pedir cotización/ajustes ANTES de ejecutar. Consultar duración, resolución, créditos e intentos autorizados. Si no existe cotización separada, usar la confirmación del cliente o la web; no lanzar una generación para «ver cuánto cuesta».
5. Ejecutar una generación autorizada, esperar estado final, descargar el MP4 y revisar. Registrar job/asset ID y consumo real. El ejemplo original/los Assets de referencia no son el resultado: comprobar cuál se descarga.
6. Si falla o necesita otro intento, explicar el fallo y respetar el máximo ya autorizado. No repetir indefinidamente ni usar otra plataforma/modelo en silencio.

Texto de encargo para un agente **ya autenticado** (plantilla nuestra):

```text
Prepara una transferencia con Higgsfield Genjutsu / Motion Transfer usando referencia_preparada.mp4 y la leyenda de PLAN.md. Mantén la acción, la cámara y los cortes; sustituye personaje, producto y escenario exactamente como indica el prompt del plan. Muéstrame duración, calidad y coste en créditos antes de generar. No cambies a otro modelo. Genera únicamente cuando exista autorización para ese coste e intentos. Devuelve el identificador del trabajo y el MP4 final para revisar; no lo publiques.
```

**Coste del MCP:** utiliza créditos de Higgsfield; no es gratis por ir desde Claude. La documentación oficial indica que las promociones Unlimited y generaciones gratuitas de la web **no se aplican a MCP/CLI/Plugin**. Separar este acceso del producto API con sus claves/tarifas. [Coste y flujo oficial](https://higgsfield.ai/blog/automate-ai-video-no-code).

### Misma operación en la web

**TUTORIAL:** abrir `https://higgsfield.ai/es/ai/video?model=genjutsu`; **Crear vídeo → Higgsfield Genjutsu → Transferencia de movimiento**. Subir referencia preparada y fotos; activar Prompt, insertar las menciones reales `@`, calidad, comprobar el gasto de **Generar**. Abrir el resultado, revisar, **Descargar**. **Recrear** gasta otra generación.

Hay **Intercambio de objetos / Object Swap**, pero los ejemplos revisados de Jonny usan Transferencia de movimiento. Si el encargo pide reproducir actuación/escenario, no cambiar a Object Swap porque el nombre parezca parecido.

**Calidad para esta cuenta nueva:** Néstor prioriza calidad y menos volumen. Elegir una resolución real adecuada, normalmente probar 720p/1080p según el coste autorizado, y revisar el archivo. **480p + filtro** es el ahorro que enseña Jonny, no el objetivo por defecto de esta nueva cuenta. Si la cotización no permite la calidad prevista, preparar la alternativa para el operador.

Consumos del tutorial: 30 s a 480p = 90 cr; 30 s a 720p = 210 cr. Son orientación histórica; manda la cotización actual. No confundir una suscripción mensual con cobrar solo la parte proporcional por vídeo ni asumir que un upscale esté incluido.

## 7. Audio: tres rutas, sin mezclar

| Qué muestra el vídeo | Qué hace Jonny | Qué hace el agente |
|---|---|---|
| Mudo / música | Transferencia y montaje; puede acelerar | Preservar la acción; música/sonido permitido para el destino, sin inventar diálogo |
| Voz en off, boca no visible | Transcribir → corregir → Fish TTS → ajustar | Puede adaptar texto a NUESTRA ficha/lengua y grabar nueva voz; conservar la correspondencia frase/acción |
| Persona hablando con boca visible | Exportar audio original → Fish Voice Changer | Cambiar timbre manteniendo palabras, pausas y tiempos; revisar labios después |

### Voz en off

**TUTORIAL (10–14):** Submagic, transcripción de TikTok en español; si falla la primera vez, reintenta. DeepSeek: «corrige este guion» con el texto. Fish Audio → **Text to Speech**, elegir voz, generar y descargar.

**PROYECTO:** Gemini de la réplica ya puede analizar imagen/audio, o se transcribe localmente con Whisper. No volver a transcribir con otra API de pago solo por reproducir las herramientas del vídeo. En el VPS, Whisper pesado va en contenedor separado con CPU limitada, **nunca dentro de `tiktok-api`**.

Guardar `guion_final.txt` y `voz_final.mp3`; contrastar datos con la ficha antes de locutar. En CapCut, silenciar/quitar audio original, importar Fish, cuadrar duración: quitar aire del inicio/final y ajustar ligeramente velocidad si hace falta. Jonny compara los segundos del audio y del vídeo y ajusta; no hay un valor universal 0,99× para todos.

### Habla a cámara

**TUTORIAL (20:40–24):** evitar dos voces; CapCut → **Exportar → desmarcar vídeo, dejar audio**; Fish Audio → **Voice Changer → Convert**, cargar audio, elegir voz y convertir; **History → descargar**. Enseña «Arnold» para inglés, no como voz obligatoria de nuestra cuenta.

**RECETA local para extraer el audio de la referencia preparada**, manteniendo sus tiempos:

```bash
ffmpeg -nostdin -i referencia_preparada.mp4 -vn -c:a pcm_s16le -ar 48000 audio_referencia.wav
```

Comparar `voz_convertida.mp3` con el vídeo: misma frase en el mismo gesto/boca. Si se acortó/aceleró la referencia, convertir **ese audio preparado**, no otro de duración distinta. Evitar mezclar música/varias voces en la conversión; si hay que separar audio, presupuestar el paso antes.

**Lengua:** Voice Changer cambia timbre, **no traduce una actuación inglesa a español**. Para habla en español escoger referencia española, o preparar otra ruta de localización/lipsync y validarla aparte; no decir que el tutorial resuelve esa traducción. Para voz en off sí se puede adaptar el guion a español porque no depende de los labios.

Coste web Fish orientativo verificado: Voice Changer 3.000 créditos/minuto, por segundo; 30 s = 1.500. La cuota gratis de 8.000 cr no es ilimitada ni el saldo de nuestra cuenta. El TTS del Largo es otra operación: no conserva por sí mismo la actuación vocal original.

## 8. Montar y dar acabado sin perder la actuación

**TUTORIAL (19–20:40):** CapCut → **Filtros → buscar «4K»**; ajusta intensidad y compara. Prueba «8K», pero suaviza demasiado al personaje; prefiere «4K». No fija una intensidad obligatoria. Higgsfield también ofrece upscale a 1080p; no suponerlo gratis.

**RECETA:**

1. Mantener 9:16; no añadir bandas ni cortar partes del producto/manos necesarias para la demostración.
2. Sustituir el audio solo con la ruta del paso 7. Revisar el resultado completo, no solo el primer segundo.
3. Decidir filtro/upscale por comparación a tamaño real: no borrar textura de tejido, etiquetas o piel, ni convertir el «4K» del filtro en una afirmación de resolución real.
4. Subtítulos de **las palabras realmente locutadas**, con tiempos alineados. Guardar texto y tiempos; revisar nombres/modelos y que no tapen boca ni producto.
5. Añadir **nombre del producto** legible, sin inventar beneficios. CTA según destino real y solo si procede; respetar que la cuenta nueva quizá aún no tiene carrito.
6. Limpiar metadatos con los helpers existentes cuando se use el montaje de la app. Marcar IA en publicación cuando proceda; limpiar metadatos no sustituye esa declaración.
7. Exportar 1080×1920 cuando sea el objetivo acordado, y medir resolución/duración/audio. Si se reescala un 480p, registrarlo como reescalado, no como nativo 1080p.

**No meter sin más el hablado en POV BOF Largo:** su editor elimina el sonido del clip y crea una voz nueva. UGC/Multimodo conservan audio, pero esperan sus formatos/huecos; una transferencia continua de 19–30 s no queda integrada por el mero hecho de subirla allí. Hasta tener una entrada específica validada, preparar montaje manual/local y guardar la salida, sin forzar IDs o schemas de otro nicho.

## 9. Revisión de calidad y cuándo repetir

Comprobar referencia, foto de ficha y resultado lado a lado. Revisar el vídeo entero y fotogramas de inicio, cambios de plano, acción funcional y cierre:

- **Producto exacto:** forma, tamaño, color, piezas, tejido/etiqueta/cremallera. No desaparece, se transforma, flota o se duplica durante el movimiento.
- **Acción:** gesto original reconocible; mano y producto interactúan de forma posible. Las botas muestran subir/bajar cremallera: no sirve una cremallera que atraviesa el material o cambia de lado.
- **Personaje:** misma cara/cuerpo/atuendo aprobado entre planos, manos correctas, sin cambio de identidad.
- **Escenario:** nuevo pero conserva el uso. El cojín del coche debe seguir en un coche cuando ese sea el concepto; «otro escenario» a secas le falló a Jonny.
- **Texto:** sin restos del original, frases de otro idioma/precios/claims incorrectos; subtítulos y nombre claros.
- **Audio:** una voz coherente, no mezcla con el original, sin frases cortadas; si se ve la boca, coinciden palabras y labios. Conversión de voz no garantiza esto por sí sola.
- **Archivo:** duración real, vertical, sin barras, imagen suficiente para este encargo de calidad, sin confundir resolución del panel con la del MP4.

Si falla, señalar segundo y defecto, proponer el cambio mínimo (referencia/ángulo/prompt/escenario/audio) y usar solo el reintento autorizado. Si agotó el máximo, apartar y dejar motivo. No «arreglar» deformaciones del producto con un filtro ni aprobarlo porque el gancho sea viral.

## 10. Dossier, entrega y relevo

**RECETA de organización**, dentro de una bandeja del usuario real ya conocido. Si todavía no existe, preparar el plan en el repo/local y confirmar dónde se guardará antes de subir assets a otra cuenta. No crear por su cuenta un usuario Redis para la nueva cuenta.

```text
<cuenta>/<producto>/<version>/
  PLAN.md                     # ficha, referencia, objetivo, créditos, orden de fotos
  referencia_original.mp4
  referencia_preparada.mp4
  personaje_base.png          # o vínculo al personaje estable de la cuenta
  personaje_variante.png
  producto_frente.jpg, producto_detalle.jpg, variantes_*.jpg
  guion_final.txt
  voz_final.mp3               # TTS, o voz_convertida.mp3 para hablado
  genjutsu_bruto.mp4
  video_final.mp4
  REVISION.md                 # segundos revisados, defectos, aprobado/repetir
  RELEVO.md                   # permisos, IDs, hecho/falta, gastos y bloqueos
```

Los nombres son una **convención propuesta** para este flujo; no una carpeta ya creada ni un menú nuevo de la app. Solo subir al Drive los assets finales/intermedios necesarios para reanudar y revisar, según la bandeja del encargo. Borrar las descargas/cachés del VPS cuando la entrega esté confirmada; no borrar los assets de otra sesión ni el personaje aprobado.

Plantilla mínima de `PLAN.md`:

```text
Cuenta destino / usuario app:
Objetivo: menos vídeos, mayor calidad; frecuencia aprobada:
Producto / marca / modelo / variante / URL / ficha comprobada el:
Referencia viral / autor / duración / vistas y otras métricas / origen autorizado:
Qué acción se copia y por qué encaja con EL producto:
Ruta de audio: mudo | voz_en_off | hablado_a_camara; idioma:
Personaje aprobado / variante / voz:
Tramo original / velocidad / duración preparada:
LEYENDA @Imagen 1, 2, 3...: archivo → función de cada referencia
Prompt final COMPLETO:
Genjutsu / Transferencia de movimiento / calidad y coste cotizados:
Autorización: nº generaciones + tope créditos + nº reintentos:
IDs del trabajo/Assets y gasto REAL:
Edición / subtítulos / nombre / CTA según destino:
Revisión por segundos y estado:
Entrega / ubicación / qué falta:
```

**Entregar:** vídeo final + ficha/enlace + guion/caption revisados + dossier y estado. No publicar ni marcar «Subido/Vendió/Escaparate» salvo encargo explícito. Si solo se pidió preparar, entregar el plan sin gastar créditos y dejar claro qué accesos faltan.

## 11. Qué queda listo y qué no

- **Listo en el repo:** tutorial analizado, prompts, esta receta y `guia("genjutsu")`; los cambios del MCP de nuestra app se sirven en producción después del despliegue habitual, que no se ha realizado en este encargo.
- **Registrado en VPS:** MCP HTTP `higgsfield` en Claude Code, configuración de usuario.
- **PENDIENTE de operador:** cuenta Higgsfield, autenticación OAuth y presupuesto; cuenta nueva de TikTok y personaje/destino exactos. No se ha comprado ninguna suscripción.
- **PENDIENTE de verificación tras autenticar:** herramientas reales de Genjutsu, uploads, cotización y resultados desde el MCP. No afirmar que se ha probado una generación.
- **PENDIENTE solo si se quiere integrar en la app:** entrada de transferencia continua/voz convertida en el montaje y Mis tandas. Esta guía no cambia schemas ni crea un programa.
