# Cuenta árabe (Mi 8) y usuario web `nes_bugallo`

> Decidido con Néstor el 29/10/2026. Socio: **Bugallo** (usuario web `nes_bugallo`, nombre visible «Ness/Bugallo»).
> Informe del nicho con los datos (ventas, ritmo, cara/sin cara):
> Drive `TIKTOK_SHOP_AI_PRO/_agente/nestor2/NICHO_ARABE_ES_2026-10-28.md`.
> Lista de productos: Drive `TIKTOK_SHOP_AI_PRO/_agente/nestor2/arabe/PRODUCTOS_ARABE.md`.

## 1. Qué es

Una cuenta antigua de TikTok Shop España (como la de Viva Shop): Néstor le cambia
el nombre y la foto. Va dirigida al **público árabe/magrebí** de España y Europa.
TikTok reparte cada publicación por su idioma: un carrusel con texto en francés
fue en más de un 85 % a Francia.

| | |
|---|---|
| Móvil | **Xiaomi Mi 8** (ADB por Tailscale `100.115.12.26:5555`, 1080x2248, MIUI, Android 10) |
| Formatos | Carruseles de fotos con **precio** + vídeos **POV sin cara** (mano enseñando el producto) |
| Ritmo | **Desde el 29/10: 10 vídeos/día y 0 carruseles** (el modo foto no deja enlazar producto en esta cuenta, ver §5). Cuando lo active: 45 carruseles + 10 vídeos/día. Más adelante, 20 vídeos |
| Horario | Subida automática desde las **00:00**: primero los carruseles, luego los vídeos |
| Presupuesto noviembre | 22-25 € (300 cr de GenAI Pro = 8 €; Omni con marca de agua = 1 cr por clip de 10 s) |
| Objetivo | ~10.000 € de ventas en noviembre (Black Friday). Si deja ~1.000 € de comisión, en diciembre se reinvierte (Genjutsu, más cuentas, avatar para vídeos largos) |

El Mi 8 **también lo usa el agente de stock** (`scripts/stock_tiktok_movil.py`)
y la cuenta servirá para buscar vídeos y stock. Las subidas van de noche y el
resto de trabajos fuera de esa franja. Nunca a la vez: comprueba antes que no hay
otro proceso con el móvil:
`ps -eo pid,etime,args | grep -E "stock_tiktok|subir_" | grep -v grep`.

## 2. Regla de oro: el estilo es el de ELLOS

**No se ponen nuestros textos de venta ni nuestro estilo** (rótulos con brillo,
«CUPÓN DESCUENTO», «APROVECHA AHORA»…). Se miran los textos y el estilo visual
que les funcionan a las tiendas árabes que venden (oujdia, chef.nadia,
saritasara, beldi…) y **se replican tal cual**. Como mucho se añade un plus
visual encima.

**Y encima, más calidad que ellos (Néstor, 29/10):** misma estructura, mismos
textos y mismo tono, pero mejor acabado: texto bien maquetado y legible (precio
grande, jerarquía clara), animaciones suaves de entrada del texto en los POV,
fotos más limpias. El público son árabes/magrebíes que viven en España (el envío
es a España). Nunca se copian cupones, «-60 %» ni precios tachados falsos. Lo calibrado para España no vale para este público (Néstor,
29/10).

Lo que llevan ellos (visto en el Mi 8):
- **Texto**: el nombre del producto en español, una frase en darija o árabe
  («بثمن همزة» = a precio de ganga, «لطلب من هنا 👇» = pídelo aquí) y el
  **precio**. Mezclan los dos alfabetos en la misma línea.
- **Hashtags árabes**: `#إسبانيا🇪🇸_ايطاليا🇮🇹_البرتغال #فرنسا🇨🇵_بلجيكا🇧🇪_المانيا🇩🇪 #المغرب🇲🇦تونس🇹🇳الجزائر🇩🇿`
  más `#tiktokshop #oferta`.
- **Vídeos**: mano o percha con el producto, sin cara ni voz, con música o
  sonido ambiente. Duran 23-74 s. Los que venden suben 12-16 vídeos al día.

**Texto mixto (español + árabe + números): ya se pinta bien** (`src/texto_arabe.py`):
- Con árabe se usa la fuente **Tajawal**, que también trae letras latinas.
- La línea se lee en el sentido de su primera letra.
- Los números, los precios y los trozos latinos van aislados: «39,90 €» y
  «24-48h» no se desordenan, y el 👇 sale en el lado bueno.

Lo usan el bloque de texto del POV y las fotos de los carruseles.
**Revisa siempre la imagen**: que se lea el precio y que todo quede dentro de la
zona segura (`x 0.05-0.78`, `y 0.15-0.75`).

## 3. Carruseles

1. Busca un carrusel viral de una tienda árabe (las de arriba, más las que
   encuentre el agente de carruseles en otros países).
2. `replicar_carrusel(..., url=<viral>, pais="AR")`. El país `AR` es la cuenta
   árabe:
   - Copia el idioma y la mezcla del original: si mezcla español y darija,
     igual; si solo usa español, solo español.
   - Pone el **precio de nuestra ficha** donde el original lleva el suyo.
   - Los hashtags de TikTok son los árabes fijos (`HASHTAGS_ARABE` en
     `src/replicar_viral/carrusel.py`) más 3 de la IA.
3. Imágenes en Flow, `subir_imagen_carrusel`, semáforo, como siempre (guía
   `replicar-carrusel.md`).
4. Producto del carrusel **en el escaparate** de la cuenta árabe antes de
   subirlo.

## 4. Vídeos POV (sin cara)

### Receta desde la ronda 10: POV BOF Largo con rótulos y voz árabes (1/11/2026)

Lo que se coge del viral árabe son sus **rótulos, su gancho, su caption con hashtags y su guion**; los **planos** son los del POV BOF Largo:
- **Imagen** (Flow NB2, una por clip): el prompt del curso literal, `src/nicho_pov_bof/prompts/prompt_imagen.md`: producto en un sitio real distinto del de la ficha, a su tamaño, con su etiqueta, y una mano POV que lo SEÑALA. La imagen 2 lleva la 1 como ingrediente (producto idéntico) y cambia el plano: más cerca, otro ángulo o un detalle.
- **Clip** (Omni 1 cr, igual que ahora): `prompt_video.md` literal, en inglés: «The camera moves realistically with subtle vibrations. The person gestures with the visible hand as if explaining the product, without touching or interacting with any object.». Nada se coge, gira, abre ni enciende; lo electrónico, apagado.
- **Voz** (Fish, darija): si el viral habla, su guion condensado; si es música, uno nuestro con la estructura de `nicho_pov_bof_largo/prompts/guion.md` (nombre → dolor → situación → beneficio → CTA de carrito), unos 11-16 s para 2 clips. Sin promesas totales y sin afirmar cupones.
- **Montaje**: `montar8.py` igual (cabecera con el nombre y el gancho del viral, subtítulos alineados, cierre «راجعي القسائم المتاحة / لطلب من هنا» con la flecha y metadatos limpios).
- **Revisión** a 2 fps del clip entero: la mano no toca nada y el producto sigue igual a la ficha de principio a fin.

> **Regla desde el 1/11/2026 (Néstor), por encima de copiar los planos del viral:** los clips se hacen como en el POV BOF Largo. El producto se queda quieto, la mano no lo coge, ni lo gira ni lo abre si se puede evitar, y no se enciende nada electrónico (pantallas, luces, chorros). Motivo: la cafetera AIRMSEN (ronda 8) salió con un panel distinto al de la ficha y con el vaso llenándose sin chorro, y el molde (ronda 8, 04) se transformaba al girar. Resultado: −8 puntos de CRH, la cuenta en 192/1000 «Necesita atención» y el carrito quitado. El molde y el 08 duplicado de la ronda 9 están borrados.

Se hacen con **«Replicar virales» en modo `con_ia`** (guía
`replicar-virales.md`; MCP `registrar_replica_video`). Así el agente rehace el
vídeo de referencia **con sus textos, su estilo y su sonido**, sin pasar por el
rótulo del POV BOF.

- **Clips**: Omni 1.1 en GenAI Pro, 1080p y 10 s, **con marca de agua** (1 cr cada uno; desde la ronda 9, 1/11). La marca la quita `montar8.py`.
  - Prueba A/B: 1 clip (8 s) contra 2-3 clips (16-24 s).
  - Mano o percha con el producto, como en el original.
- **Texto**: el del vídeo de referencia, con nuestro producto y precio. Para
  quemarlo, `texto_foto.quemar` o `video_editor._render_text_line`, que ya
  pintan árabe.
- **Sonido**: ambiente realista de Veo o un sonido árabe de la biblioteca de
  TikTok al subir. Con producto enlazado, TikTok solo deja «Sonidos
  comerciales». **Nada de música con copyright**; ojo con Omni, que mete
  sirenas y pitidos que TikTok silencia (`learnings.md`).
- **Anti-sanción** (obligatorio):
  - el nombre del producto, en pantalla;
  - `limpiar_metadatos`;
  - subtítulos solo si hay voz.
- **Semáforo** antes de darlo por hecho; nada de niños; nunca afirmar cupones.
- Se registra con `para="nes_bugallo"` para que no se mezcle con las tandas de
  Néstor. Ya funciona vía `carrusel.destino()`.

### Banco de productos (1/11)

`/mnt/HC_Volume_106974679/navegador/trabajo/hmizat_ronda9/BANCO.json` (+ `BANCO.md`): 49 productos
de virales de las tiendas árabes con el **enlace ya comprobado en el Mi 8**, ordenados por GMV del
viral. `tipo: camara_a_pov` = el viral es una chica hablando a cámara y lo hacemos en nuestro POV
en 1ª persona (Néstor, 1/11). Se coge de arriba abajo y se marca `hecho: true`. Antes de producir un
producto nuevo, comprobar que se puede enlazar (buscarlo por ID en «Añadir enlace → Producto»).

### Receta probada: 10 POV replicados en un día (ronda 8, 31/10)

Scripts en [`scripts/cuenta_arabe_pov/`](../scripts/cuenta_arabe_pov/README.md): se copian
a la carpeta de la ronda (`/mnt/HC_Volume_106974679/navegador/trabajo/hmizat_rondaN/`) y se
ejecutan desde ahí con `~/nav-venv/bin/python`. Coste de la ronda 8: 21 créditos de GenAI
(unos 0,6 €) para 10 vídeos; imágenes y voz gratis.

1. **Virales**: los perfiles de las tiendas árabes de §2, mirados en Social1 (Chrome 9222).
   Solo POV de producto (mano y sin cara) de productos que tengamos en stock y se puedan enlazar.
   `tikwm_hojas.py` baja de cada viral el caption, el audio y una hoja de fotogramas.
2. **Idioma, al pie de la letra.**
   - El texto en pantalla va en el idioma del ORIGINAL, que se mira en sus fotogramas:
     español si es español, árabe si es árabe (las marcas en latino: `WISECEE F206`).
   - No se mezcla en un mismo bloque ni se añade darija porque la cuenta sea árabe.
   - **El caption es el del original, literal, con sus hashtags** (incluso erratas como
     `#blakfriday`). Solo se colapsan los espacios.
   - Los precios o «-X %» del original se cambian por «Mira la oferta en el carrito».
3. **¿Habla o es música?** Se transcribe el audio del original con Whisper `small`
   (`language="ar"`, con `nice` y 1-2 hilos, nunca `large`; al modelo se le pasa un array de
   numpy, porque con la ruta del fichero falla av).
   - **Si habla** (en la ronda 8, 9 de 10 en darija): guion darija condensado del suyo,
     de 2-3 frases cortas (`audio/guiones.json`). Locución con Fish (`voz8.py`, modelo
     `s2.1-pro-free`, voz automática; lee bien la darija). Los subtítulos van alineados por
     palabra con Whisper (`alinear8.py`), y el montaje parte en dos las frases de más de
     6 palabras. Con `silencedetect` salían descuadrados: las comas también hacen pausa.
   - **Si es música**: el montaje sale sin voz y en `SUBIDA.json` se pone un sonido
     comercial parecido, que se añade al subir (ver §5).
4. **Imágenes** (gratis): Google Flow, Nano Banana 2, en un proyecto PROPIO.
   - Dos escenas por vídeo. La ficha va como ingrediente y, en la escena 2, también la
     imagen 1, para que el producto sea idéntico.
   - Sufijo común: casa española real, una sola mano adulta, el producto idéntico a las
     referencias y sin texto.
   - `gen_todas_cdp.sh` las hace en bucle por **CDP directo** (`cdp.py`, sin Playwright: su
     `connect_over_cdp` se cuelga en cuanto hay una pestaña ajena que no responde). Las
     imágenes salen de `flow-content.google/image/<uuid>` y las referencias subidas TAMBIÉN,
     así que el «antes» se toma justo al pulsar «Iniciar generación» y solo vale una 9:16.
     Hasta la ronda 8, `gen_todas.sh` con Playwright.
   - Cada imagen se revisa contra la ficha antes del clip
     (la cafetera salió sin el portafiltro y se rehízo).
5. **Clips** (desde la ronda 9, 1/11: **Omni**, no Veo): GenAI Pro →
   `?ws=video&mode=frames&model=omni` → Frames, solo el fotograma inicial, **Watermark · 10s ·
   1080p · Portrait 9:16** y «Cost: 1 credit». `generar_omni.py` no envía si algo de eso no
   está marcado (`aria-pressed`) o el coste no es 1; `recoger_omni.py` los baja. Al montar,
   `omni: true` en `CONTROL_CALIDAD.json` aplica el zoom que se come la estrella de la marca.
   Revisión densa a 2 fps del clip ENTERO antes de montar (no 7 fotogramas: el molde de la ronda 8 cambiaba de forma al girar entre dos muestras y costó una sanción). Producto que se transforma al girar o se abre estando cerrado = reintento, nunca verde; si un tramo falla (pieza suelta, mano que sale), se salta con `inicios` (segundo de entrada por clip) y se acorta con `duraciones`.
   Hasta la ronda 8 era Veo (`generar_veo8.py`, `model=veo`), también a 1 cr.
   - Si se abre el modal de modelos, Escape ×2.
   - `generar_veo8.py` lleva `GENERACIONES.json` con un tope de créditos y como mucho un
     reintento por clip.
   - **Prompts cortos (~25 palabras) con una sola acción física**, terminando en «Calm,
     realistic handheld phone shot. Soft ambient room sound.». Los largos o los que llevan
     «no music» o listas de prohibiciones disparan el **«audio safety filter»** de Veo: falla
     y devuelve el crédito.
   - Nada que se despliegue o se transforme (la mesa plegable se deformó). Mejor el producto
     quieto y una mano que lo toca o lo usa.
   - **Plan B**: si un clip falla dos veces, la imagen de Flow con zoom suave (Ken Burns,
     2-3 s).
6. **Revisión**: hoja de fotogramas de cada clip.
   - El producto tiene que ser igual a la ficha en TODO el clip, nada debe atravesar nada y
     solo puede haber una mano.
   - Veo suele estropear el final (a la aspiradora le sale una manguera, aparecen manos de
     más, la fregona desaparece): se recorta a la parte buena en `CONTROL_CALIDAD.json`.
7. **Montaje** (`montar8.py N`): los 2 clips a 1080×1920 y 30 fps, con un acabado más
   cuidado que el suyo.
   - Cabecera de 2 líneas (nombre del producto + gancho del original) en Tajawal ExtraBold
     con caja, que entra con fundido y deslizamiento.
   - Cierre en los últimos 2,8 s: «راجعي القسائم المتاحة» + «لطلب من هنا» en árabe, o
     «Revisa si tienes cupones» + «PINCHA AQUÍ PARA COMPRAR» en español, con una flecha
     naranja que rebota hacia el carrito.
   - Whoosh y pops suaves sintetizados con ffmpeg.
   - Si hay voz: subtítulos encima del cierre, voz con `loudnorm=I=-14:TP=-2.0` y efectos
     al 40 %.
   - `clean_metadata` y una hoja de 15 fotogramas en `revision/`.
8. **Registro y semáforo**: `registrar_app.py N [replica_id_a_reemplazar]` (MCP
   `registrar_replica_video`, `para="nes_bugallo"`).
   - ⚠️ El semáforo por MCP se guarda en el usuario del TOKEN (ness). Hay que ponerlo dentro
     del contenedor: `docker exec tiktok-api python -c "from src.mis_tandas import servicio
     as s; s.poner_semaforo('nes_bugallo','rv|<id>','verde','<motivo>','agente')"`.
   - Lo electrónico que se enciende o tiene pantalla va en ámbar.
9. **Subida**: `SUBIDA.json` de la ronda (`voz.si=true` en los hablados, `sonido` propio en
   los de música) + `scripts/subir_video_movil.py` (§5) y `registrar_subidas`.

Navegador: Flow y GenAI Pro en pestañas propias, con ENTRA/SALE en `~/navegador_turnos.log`
y nunca los dos a la vez si queda poca RAM.

## 5. Subida automática desde el Mi 8

| Pieza | Estado |
|---|---|
| Vídeos: `scripts/subir_video_movil.py` | **Calibrado el 29/10 en el Mi 8** (ronda 6). Uso: `todo <ronda> <n> ["AAAA-MM-DD HH:MM"]` (con hora = programado en TikTok, hora de Madrid) y `programar <ronda> 05=2026-10-29T23:49 06=…` (cola, uno tras otro; si una hora queda a <35 min la corre). Lanzar con `flock /tmp/subir_video.lock`. Lee `SUBIDA.json` de la ronda y apunta en `SUBIDAS.log` |
| Carruseles: `scripts/subir_carrusel_movil.py` | Calibrado para el OPPO; falta pasarlo al Mi 8 |

Cómo lo hace el script de vídeos (por si TikTok cambia la UI):
- Busca por `uiautomator dump`; lo que no sale en el dump (menús flotantes, listas) por OCR (tesseract spa, psm 11).
- Galería: `adb push` + `touch` (si no, conserva el mtime viejo y no sale el primero) + scan; al limpiar, `content delete` en MediaStore.
- Árabe: compartir el texto a Keep → pulsación larga en una palabra → «Seleccionar todo» → «Cortar» → pegar con el chip del portapapeles de Gboard.
- Orden: sonido «Suns» (lupa → « Suns» con espacio delante, el 1.er carácter se pierde) → caption → producto por ID (nombre del enlace ≤30) → sin etiqueta IA.
- **Sonido por vídeo** (31/10): si el viral lleva música, `sonido` en `SUBIDA.json` trae
  `{busqueda, sugerencia ("" = pulsar «Buscar», Intro no busca), fila (regex OCR de su línea
  «N publicaciones»), comprobar}`; si falla dos veces, vuelve a «Suns». La búsqueda de
  sonidos no tiene filtro de «comerciales». Ejemplo para la música jbala/árabe:
  «Arab Romantic Lover» (Zahidan Beats, 1,2M). Los vídeos con voz (`voz.si`) no llevan sonido: el script QUITA el que TikTok
  sugiere solo (X «Cerrar» de la píldora); si se queda y no es comercial, «Producto» sale
  desactivado («Usa un sonido comercial para añadir un producto») y además tapa la voz.
- **Programar**: «Más opciones» → «Programar publicación» → rueda día/hora/minuto (columnas x=254/592/877, fila central y=1424, 106 px = 1 unidad, swipes lentos de 900 ms; se lee por OCR y se corrige) → «Listo». El botón sigue diciendo «Publicar»; tras pulsarlo sale «Consulta tus publicaciones programadas en tu perfil» = subida terminada (solo entonces se cierra TikTok y se borra el vídeo). Mínimo ~30 min por delante, máximo 10 días.
- Comprobar antes que el producto se puede enlazar: «en stock» en la ficha no basta (29/10: prensa, kimono, jellaba mostaza y mkhzani no salen en la búsqueda de «Añadir enlace»).

Reglas del Mi 8:
- **Despertar**: WAKEUP (y POWER si sigue en reposo) + `wm dismiss-keyguard`. Si sale la guía del sensor de proximidad,
  VOLUME_UP y en seguida VOLUME_DOWN (autorizado por Néstor), y deslizar
  `540 1900 → 540 500`. Nunca VOLUME_UP suelto.
- **Perfiles**: `snssdk1233://user/profile/<uid>` (el https abre una web con
  banner de cookies).
- **En bucles de bash**: `adb ... </dev/null`, si no adb se come la entrada.
- **Prohibido**: «Crear ahora» y «Retirar».
- **Al acabar**: `rm /sdcard/u.xml`, HOME y bloquear.

## 6. Usuario web `nes_bugallo`

Entra con su PIN (lo elige la primera vez) y **solo ve dos pantallas**:

- **Subidas** (`/subidas`): vídeos y carruseles publicados cada día, con el total
  del mes y la media frente al objetivo (45 + 10). La rellenan los agentes con
  el MCP. Guía `subidas.md`:
  - `registrar_subidas(fecha, videos, carruseles, nota, modo="sumar"|"fijar")`;
  - `ver_subidas(mes)`.
- **Estadísticas** (`/estadisticas`): las ventas de SU cuenta, con el mismo
  formato que las de Néstor (`estadisticas:ventas:nes_bugallo`). Se leen del Mi 8
  **cada semana** y se guardan con `guardar_estadisticas` (guía
  `estadisticas.md`).
  - PENDIENTE: los scripts de `scripts/estadisticas_movil/` están calibrados
    para el OPPO; adaptarlos al Mi 8.

Sin «Mis tandas»: el contenido lo preparan los agentes.

## 7. Pendientes (orden)

1. Néstor pone la cuenta en el Mi 8 y dice su @ y el nombre nuevo.
2. Calibrar la subida de carruseles en el Mi 8 y subir los primeros 15 a mano
   asistida (sin la tarea nocturna).
3. Script de vídeos con «Comprobar contenido» y primeros 5-10 vídeos (A/B de
   1 contra 2 clips).
4. Tarea nocturna 00:00 y apunte automático en Subidas.
5. Estadísticas del Mi 8 cada lunes.
6. Medir a la semana: ventas por formato (carrusel / POV) y por número de clips;
   decidir si se sube a 20 vídeos.

### Precio y cupones (Néstor, 29/10)
- **Sí se puede** (no se penaliza, lo usamos en las otras cuentas): una invitación genérica a mirar el cupón, tipo
  «Revisa si tiene cupón» / «mira si te sale cupón» (en darija si encaja con el estilo del original).
- **No:** prometer un cupón concreto, un precio «con cupón», «-X %» o precios tachados.
- El precio que se pone es el de la ficha SIN cupón, comprobado en el Mi 8 (`snssdk1233://ec/pdp?product_id=<id>`)
  antes de subir. Si la ficha va con «[Black Friday]», «Flash» o precio tachado, ese precio es temporal: o se vuelve a
  comprobar justo antes de publicar o la pieza va sin cifra (+ «revisa si tiene cupón»).
  Ejemplo 29/10: molinillo LAICHY 1729773675957492189, 15,47 € con «[Black Friday]» en el título.

### Subida desde el Mi 8 (primera prueba, 29/10)
- Molinillo publicado en público el 29/10 a las 13:34 con el sonido «Suns» (Official Sound Studio), el producto 1729773675957492189 (enlace «Molinillo de cafe electrico») y el caption de darija con 4 hashtags.
- **Sin etiqueta «Contenido generado por IA»** (Néstor, 29/10: «no hace falta»). Este primero salió con ella; en los siguientes, no se activa.
- Gboard del Mi 8: autocorrección, revisión ortográfica y sugerencias de palabras **desactivadas** (metían palabras al perder el foco). La barra de sugerencias sigue activa, porque su chip del portapapeles es la forma de pegar el árabe.
- El Mi 8 no admite `input keycombination` (Ctrl+A/C/V): para vaciar se usa `keyevent 123` + DEL; para copiar, una pulsación larga → «Seleccionar todo» → «Copiar» en Keep, y para pegar, el chip del portapapeles de Gboard.
- Voz: los referentes del nicho (C01–C08, V01–V04, E01–E06 en ESTILO_IDIOMAS.md) **no llevan locución de venta**: solo música o el sonido, con texto en pantalla y caption en darija.

### Consistencia del producto y cupones (Néstor, 29/10 tarde)
- **El producto no puede cambiar entre planos.** En el molinillo, el botón de pulsar aparece de la nada en un clip de IA. Antes de dar un vídeo por bueno, comparar fotograma a fotograma con la foto de la ficha (botones, asa, tapa, logos, número de piezas) y descartar el clip que añada o quite piezas.
- **No poner el precio exacto** (cambia siempre). Usar los textos de cupón de las otras cuentas: «CUPÓN DESCUENTO» como gancho visual, «Revisa si tienes cupones», «Precio ajustado / a precio de chollo», «Mira la oferta en el carrito», «Lo tienes en el carrito naranja 🧡». Nunca afirmar «tu cupón» ni una cifra con cupón.
- **Voz:** si el POV de referencia lleva voz, el nuestro lleva voz en árabe/darija de Fish Audio; si no la lleva, solo música o sonido.
- **Receta del viral, tal cual (Néstor, 29/10):** idioma en pantalla y caption, los MISMOS que lleve el viral que se replica. No se añade darija «porque la cuenta es árabe». Ejemplo, el tocador (C01 @halaluxe, 800k): fotos en español y caption solo con hashtags, con el árabe del original (`#اسبانيا🇪🇸_ايطاليا🇮🇹_البرتغال🇵🇹`). Solo cambia lo obligatorio: el precio exacto pasa a ser el gancho del cupón.

- **29/10 14:40 · Sin carruseles por ahora.** En @hmizat.spain el modo foto NO deja enlazar producto («De momento, los enlaces a productos no están disponibles en el modo de foto»; en la cuenta del OPPO sí deja). Néstor: nada de «vídeos de fotos»; la cuenta sube **solo vídeos, 10 al día**, hechos por Codex, y con continuidad TikTok suele activarlo (le pasó con otras cuentas). Revisar de vez en cuando si «Producto» deja de salir en gris en un carrusel; entonces se vuelve al plan 45 + 10.
