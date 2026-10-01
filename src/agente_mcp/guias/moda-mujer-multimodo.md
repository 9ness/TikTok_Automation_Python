# Moda Mujer · Multimodo — `/tiktok-shop-ai-pro/moda-mujer-multimodo`

Lee antes [`README.md`](README.md) y las tres guías de [`comun/`](comun/).
Es la misma pantalla que [Moda Mujer · Aleatorios](moda-mujer-aleatorios.md)
(pasos y tarjetas iguales). Lo que cambia es que **no hay un modo fijo**: en
**cada producto eliges tú el formato** que mejor le va, y así la cuenta no se
ancla en uno solo. Está pensado para que lo trabaje un agente.

## Qué sale

Un clip **mudo** de 10 s por producto. Nadie habla: la música la pone el
operador en TikTok al publicar (en Camiseta Sarcástica, además, el sonido de
risas). La app encuadra a 1080×1920 y limpia metadatos; los dos formatos
«Multi Escena» llevan además el grado de color y el texto de temporada. Los
Vintage NO llevan texto en la imagen: el rótulo otoñal (con sus emojis) lo
quema el montaje, una frase distinta por producto. Nano Banana lo metía en la
foto y Kling lo deformaba a mitad de clip.

**Excepción: los dos formatos de 20 s con voz** (`mm_zapatillas_pov20` y
`mm_zapatillas_sentado20`, «Zapatillas Vista POV/Sentado 20s» de su web). Son
**DOS clips de 10 s**, cada uno de SU imagen (el curso pide dos imágenes con el
mismo prompt: sale otra chica y otro sitio), y los dos **mudos**. La voz la pone
la app al montar: un guion de **punto de dolor** escrito para ese producto
(el mismo prompt que el POV BOF Largo) y locutado con una voz de mujer de
**Fish**. Lleva los textos del POV BOF Largo (gancho, título, CTA, flecha y
subtítulos). Sin música: habla. Si Omni/Kling mete voz en el clip, da igual:
se descarta.

## Flecha CTA al final (prueba, decides tú)

El multimodo sale SIN flecha al carrito, que es lo normal en este nicho. Se
está probando si con ella hay más visitas. Tú decides en cada vídeo:

- `subir_clip(…, flecha=True)` hace que el montaje ponga la flecha **los 3
  últimos segundos**. El color lo elige solo según el fondo del vídeo en ese
  tramo (amarilla en un otoño, verde en un parque, blanca o negra sin color)
  y el estilo rota por producto, igual que en Calle Dividido o POV BOF. En
  formatos de dos clips, pásalo en los DOS.
- **Cuánto:** en **~1 de cada 3 vídeos** de la tanda, repartidos entre tipos
  (no todos los bolsos con flecha y ninguna ropa). Así se puede comparar.
- **En cuáles:** en los que acaban con el producto bien visible y el fondo
  despejado abajo, donde va la flecha. No la pongas si ahí hay manos,
  piernas o el propio producto, porque lo taparía.
- Los 🎙️ de 20 s ya la llevan siempre (montaje del POV BOF Largo): no hace
  falta pasarla.
- En las tandas, los vídeos con flecha llevan ➡️ delante del formato. Así el
  operador puede comparar visitas; si funciona, se pondrá en todos.
- Desde la web es la casilla «➡️ Flecha CTA al final» de la tarjeta, antes
  de subir el clip.

## Catálogos

| Catálogo (`catalogo`) | Qué hay |
|---|---|
| `web` | Ropa Mujer de su web (las carpetas de siempre) |
| `zapatos` | Zapatos Mujer (zapatillas, botas, tacones…) |
| `accesorios` | Accesorios Mujer (bolsos y gafas) |
| `muestras` / `tareas` | Los del operador |

## Qué formato para cada producto

Cada producto trae `tipo_multimodo` (sale del título): `ropa`, `camiseta`,
`calzado`, `botas`, `bolso` o `gafas`. Elige un formato de SU tipo y **alterna**
dentro de la carpeta (no pongas el mismo a todos).

| Tipo | Formatos (`modo`) | Personaje | Imagen en el clip |
|---|---|---|---|
| ropa (vestidos, pantalones, jerséis, chaquetas…) | `mm_espejo` (Espejo Solo Música) · `mm_espejo_escenas` (Espejo Multi Escena) | **sí** | FRAME INICIAL |
| camiseta | `mm_maniqui` (sin persona) · `mm_sarcastica` (solo si la camiseta lleva FRASE) · o los de ropa | maniquí no / sarcástica sí | FRAME INICIAL |
| calzado (zapatillas, zapatos, tacones) | `mm_zapatillas_espejo` · `mm_zapatos_escenas` · `mm_zapatos_pov` · 🎙️ `mm_zapatillas_pov20` · 🎙️ `mm_zapatillas_sentado20` | espejo y escenas sí; POV y los de 20 s no | escenas = **INGREDIENTE**; resto FRAME INICIAL |
| botas | `mm_botas_1` · `mm_botas_2` · `mm_botas_largas_1` · `mm_botas_largas_2` (las «largas», solo botas altas) · o los de calzado (también los 🎙️ de 20 s) | no | FRAME INICIAL |

Los 🎙️ de 20 s son los únicos con voz: úsalos para **mezclar largos con
cortos** (lo pide el curso para evitar sanciones). Son dos clips, así que
cuestan el doble de generación.

### Cuándo elegir un 🎙️ de 20 s (y cuál)

- **Solo** productos con `tipo_multimodo` = `calzado` o `botas`.
- **Ritmo:** más o menos **1 de cada 3-4 calzados** de la tanda. Nunca dos
  seguidos del mismo modo de 20 s: alterna POV ↔ Sentado.
- **`mm_zapatillas_pov20`** (dos manos sujetando el calzado): zapatillas,
  zapatos planos, mocasines y botines, es decir, lo que se enseña bien en la mano. **No**
  para botas altas: no caben enteras en el plano.
- **`mm_zapatillas_sentado20`** (sentada, de rodillas abajo, puesto):
  cualquier calzado que luzca PUESTO: tacones, sandalias, botas altas,
  zapatillas.
- **Mejor si la ficha da para hablar:** el guion sale de los textos
  extraídos (título, caption, características). Si el producto no tiene textos, o
  el título es pobre («Zapatillas mujer»), elige un formato mudo: el guion saldría
  genérico.
- Los plazos y el envío gratis los decide la app por la ficha y el precio: no
  hace falta hacer nada.
| bolso | `mm_bolso_1` · `mm_bolso_2` · `mm_bolso_3` | no | FRAME INICIAL |
| gafas | — **se saltan** (no hay formato mudo) | | |

Si el `tipo_multimodo` no cuadra con lo que ves en la foto (el título engaña),
manda la foto.

## El personaje

Donde pone «Personaje: sí», adjunta en Flow el personaje de la cuenta (el
mismo en todos los vídeos) junto a la foto del producto. Los formatos que el
curso publica con chica aleatoria llevan delante una línea
«CHARACTER OVERRIDE» que manda sobre el «random woman» del texto: no la
quites. Con el MCP, el personaje sale de `personaje_marca`.

## Dónde generar

- **Imagen**: Google Flow · Nano Banana 2 · 9:16 (gratis: repite hasta que
  salga bien).
- **Clip**: Magnific · Kling 2.5 · 10 s · imagen como fotograma inicial
  (ilimitado, aunque lento). `mm_zapatos_escenas` es la excepción: la imagen
  entra como INGREDIENTE, así que va en Flow.
- Descarga a 720p/1080p vertical, sin fotos fijas.
- **Kling 2.5 solo es ilimitado a 720p** (a 1080p gasta créditos). El Video
  Generator de Magnific deja **una** generación a la vez; para una carpeta
  entera usa un **Space** propio (duplica «Foto con IA a Video»): «Clear list»
  en la lista de entrada, «Add media» (2 por tanda, ver abajo), prompt en el nodo
  generador y Run. Se encola en el servidor (~5 min por clip con la cola
  libre; 10-30 si la cuenta tiene más Spaces corriendo). Agrupa por
  prompt: todos los Vintage comparten movimiento; los de espejo, otro.
- **Un nodo que pasa 60 min sin terminar falla entero** («Node execution
  timed out after 60 minutes») y se pierden los clips que no salieron. La cola
  de Kling es de la CUENTA, no del Space: lanza tandas de **2 clips** y
  no abras varios Spaces a la vez si otra persona u otro agente también
  está generando.

## Revisar antes de subir

- Imagen: el producto idéntico (forma, color, estampado, piezas); es el
  personaje en los que lo llevan; los Vintage SIN ningún texto (si Nano Banana
  mete alguno, repite la imagen: el rótulo lo pone la app).
- Clip: el producto no cambia ni se mueve solo, no aparecen manos o piernas
  de más, la cara no se deforma. Compara con el vídeo de ejemplo del formato
  en su web. Repite SOLO por inconsistencias visuales.

## Paso a paso (MCP)

1. `carpetas(menu="moda_mujer_multimodo", catalogo=…)` — el progreso es del
   multimodo entero (una carpeta está hecha cuando cada producto tiene SU
   vídeo, del formato que sea).
2. `productos(menu, catalogo, carpeta)` → mira `tipo_multimodo` y
   `formato_hecho` (lo que ya tiene vídeo) y decide el formato de cada uno.
3. `plan_producto(…, modo="mm_…")` → prompts de imagen y de movimiento de ESE
   formato.
4. Imagen en Flow → clip en Magnific → revisa.
5. `subir_clip(…, modo="mm_…", clip=1)` → se monta solo. En los 🎙️ de 20 s
   sube `clip=1` y `clip=2` (uno de cada imagen): al llegar el segundo, la app
   escribe el guion si no lo tenía, locuta con Fish y monta. Si quieres ver el
   guion antes, `preparar_carpeta(…, modo="mm_zapatillas_pov20")` lo escribe.
6. Al terminar la carpeta: `marcar_carpeta(…, modo="multimodo", pendiente=True)`.

`modo="multimodo"` es solo la vista de todos los vídeos: sirve para listar y
marcar carpetas, no para subir.

## «Continúa la lista multimodo» — cómo seguir sin perderte

> **Estado y relevo a día de hoy:** `tasks.md` › «Multimodo (Ana) — RELEVO» (qué carpetas
> están hechas, qué sigue, lo aprendido y cómo trabajar desde el VPS).

Es lo que te pedirán casi siempre. Qué significa y en qué orden:

1. **Para quién.** Los vídeos del multimodo son de la cuenta de **Ana**. Se
   hacen y se suben con **SU** MCP (`/api/mcp/ana.<token>`, te lo da el
   operador; no lo guardes en memoria ni en el repo). **No uses el selector de
   cuenta de la web**: cierra la sesión y pide PIN. Si no tienes su URL,
   pídela antes de subir nada.
2. **Qué queda.** `carpetas(menu="moda_mujer_multimodo", catalogo=…)` en los
   TRES catálogos de moda (`web`, `zapatos`, `accesorios`), y dentro de cada
   carpeta `productos(…)`: los que tienen `formato_hecho` vacío están por
   hacer. Las gafas se saltan siempre.
3. **Alterna catálogos Y formatos.** No acabes un catálogo entero antes de
   empezar otro: coge 2-4 productos de ropa, luego 2-4 de zapatos, luego de
   accesorios, y vuelta. Dentro de cada tipo, rota los formatos (si el último
   calzado fue POV, el siguiente espejo o escenas; bolsos 1→2→3). Las tandas
   de la app ya mezclan al publicar, pero si solo hay de un tipo no hay nada
   que mezclar.
4. **Por producto:** `plan_producto(…, modo="mm_…")` → imagen en Flow (con
   Lucía si el formato lleva persona) → clip en Magnific → revisar →
   `POST <url MCP>/subir` (multipart `file`) → `archivo_id` →
   `subir_clip(menu="moda_mujer_multimodo", catalogo, carpeta=<slug>,
   producto, modo, clip=1, archivo_id)` → `estado(id=<job>)` hasta `done`.
   La carpeta es el **slug** que devuelve `carpetas` (p. ej.
   `mujer_zapatos_web__Carpeta_2`), no el nombre bonito.
5. **Informe final:** qué productos quedaron hechos (formato de cada uno),
   cuáles se saltaron y por qué, y cuántos clips se repitieron.

### Magnific en práctica

- **Desde el VPS**: el Space de clips se abre y se maneja con el Chrome remoto
  (sin el PC del operador); cómo, y cómo no saturar CPU/RAM/disco, en
  [`comun/navegador-vps.md`](comun/navegador-vps.md).

- **De 2 en 2.** Lanza tandas de 2 clips por Space y espera a que salgan
  antes de lanzar más: la cola es de la cuenta y con 4-6 a la vez el nodo
  pasa de 60 min y falla entero. Si otra sesión (otro agente, Mauro) también
  genera, túrnate con ella.
- **Un Space por prompt** (el movimiento es el mismo para todo el formato):
  uno para espejo, otro para POV de zapatos, otro para Vintage… Cambia solo
  las imágenes de la lista.
- Carga: menú «More» de la lista → «Clear list» → «Add media» → sube las 2
  imágenes → clic en el título del nodo generador y ▶ (Run).
- Si el menú no abre (a veces no se despliega), no hace falta vaciar: pulsa
  el ◎ junto a «N images» y deja marcadas SOLO las imágenes de esta tanda
  (sale «2/6 images»); el Run genera solo esas. «Replace items» NO sustituye
  al añadir, y la tecla **Supr borra el nodo entero** (Ctrl+Z lo recupera).
  Comprueba en `/app/api/creations` que entraron tantos `queued` como
  imágenes marcaste.
- **Estado real y descarga:** la lista del Space no siempre se refresca.
  Pídelo a la API de la propia web, con la sesión abierta:
  `fetch('/app/api/creations?limit=10')` → cada creación trae su estado y el
  vídeo en `metadata.url` (el campo `url` va vacío). Chrome bloquea varias
  descargas seguidas: baja cada vídeo con `curl` desde esa URL.
- Si la pestaña del Space se queda en blanco o diminuta, ábrelo en otra
  pestaña: el trabajo sigue en el servidor.
- Antes de subir, recomprime a H.264 `crf 21` sin audio (`-an`): el clip es
  mudo y así sube rápido.

### Emparejar clip e imagen

Magnific no nombra los clips por el producto. Cada clip empieza con SU
imagen (fotograma inicial), así que compara el primer fotograma del clip con
las imágenes que subiste y quédate con la más parecida. No lo hagas «por
orden de salida»: se cruzan.

### Textos: nunca en la imagen ni en el clip

- Ningún prompt debe acabar poniendo texto: `plan_producto` ya quita el
  rótulo del prompt de imagen de los Vintage y termina el de movimiento con
  «vídeo limpio, sin texto». Si copias el prompt a mano, cópialo ENTERO.
- El rótulo de temporada y sus emojis los **quema el
  montaje**, una frase distinta por producto. Si la IA pone letras, se
  rechaza, aunque parezcan buenas: salen deformes o inventadas («POEAOP»,
  «2024», «PIAPIODMIRMA»).
- La temporada del rótulo es la del día en que se **publicará** (hoy + 3
  días, `config.temporada_multimodo`): otoño hasta el 31 oct (Halloween solo
  si se publica del 10 al 31), invierno en noviembre y de enero a febrero,
  Navidad del 1 dic al 6 ene. Nunca lleva un mes escrito: un «septiembre»
  publicado en octubre delata un vídeo viejo.
- En Zapatos POV el rótulo va arriba para no tapar el zapato.
- El rótulo respeta las **zonas seguras de TikTok** (`SAFE_X`/`SAFE_Y`: ni bajo
  los botones de la derecha ni sobre la descripción de abajo): el montaje lo
  centra en la franja segura y lo empuja hacia dentro. Un texto que venga
  pegado en la imagen NO pasa por ahí — otra razón para que no haya ninguno.

### Que no salga estático

TikTok penaliza el contenido estático. Por eso:

- En los **bolsos** el prompt de movimiento pide una mano que entra, acaricia
  el bolso y juega con el asa; en **botas 1/2**, que la mano gire el zapato
  que ya sujeta. Si Kling deja el clip quieto igualmente, repítelo.
- Un zoom o vaivén añadido en el montaje NO vale (lo descartó el operador):
  el movimiento tiene que estar en el clip.
- En **Zapatillas Espejo** NO pidas que enseñe la zapatilla a cámara: sale el
  pie delante del espejo o el móvil convertido en zapato. El prompt ya la
  deja agachada tocando los cordones.
- En los 🎙️ de 20 s el movimiento del curso es genérico («gesticula con la
  mano»); `plan_producto` le añade lo que tiene que moverse: en POV las manos
  giran el calzado sin soltarlo, y sentada mueve los pies (gira uno, golpecitos
  con la punta, cruza los tobillos). Si sale quieto, repítelo.

### Rechazos típicos (repite solo esto)

- Texto o letras de cualquier tipo en la imagen o en el clip.
- **Zapatos de más**: en POV aparece un tercer zapato o el pie descalzo
  acaba calzado. El prompt ya lo prohíbe («el pie descalzo sigue
  descalzo…»); si pasa, repite el clip.
- El producto cambia de forma, color o estampado, o se mueve solo.
- Otra chica en vez de Lucía, o la cara se deforma.
- Tropiezos de movimiento sin inconsistencia se aceptan.

## Vídeos listos

Arriba de la pantalla, **«📦 Vídeos listos por tandas»** junta todo lo montado
del multimodo (de cualquier catálogo y carpeta) de diez en diez: primero lo
ya subido, y lo que falta MEZCLADO por tipo y formato para que la cuenta no
se ancle (`config.orden_para_publicar`). «Bajar» baja la tanda entera.

**El orden es FIJO** (`product_repo.fijar_orden_multimodo`, Redis
`multimodo:orden:<usuario>`): se calcula una vez y lo nuevo se añade al
final. Marcar subido NO mueve nada — antes el vídeo saltaba al bloque de
arriba y la tanda ya bajada dejaba de coincidir con lo descargado. Para
reordenar a propósito hay que borrar esa clave. El «subido» de las filas va
por `POST /multimodo/subido` (ligero; `/producto/estado` rehace la carpeta
entera y en frío tardaba ~50 s). Los vídeos de las dos primeras tandas por
subir se leen del Drive en segundo plano al abrir la pantalla.

En cada vídeo:

- **✍️ Caption** copia la descripción lista para TikTok: caption del producto
  + emojis + hashtags de Moda Mujer.
- **🔎 Título** y **🏪 Tienda** copian el título literal del producto en TikTok y su tienda,
  para BUSCARLO a mano cuando el enlace 🛍️ de la web del curso no corresponde al producto
  (pasa). Es lo mismo que en POV BOF Largo.
- **🎵** copia la búsqueda de música para la biblioteca de TikTok.
- **«Marcar subido»** marca el PRODUCTO como subido en su carpeta (el mismo
  «Subido» de su tarjeta, por usuario y con fecha): no hay que ir a la carpeta
  a marcarlo otra vez. Vuelve a pulsarlo para desmarcar.
- **🔁** marca el vídeo para rehacerlo, con la nota de qué falla (móvil
  flotando, piernas de más…). `para_rehacer(menu="moda_mujer_multimodo")`
  lo lista con `modo` y `tanda`. Al subir el clip nuevo por `subir_clip` y
  montarse, el «rehacer» se quita solo, la fila sale «✨ Rehecho» y el vídeo
  CONSERVA su puesto en la tanda. Lo normal es que no haga falta: revisa
  cada clip entero (ver «Revisión» arriba) antes de subirlo — un objeto
  suspendido en el aire, algo que aparece de golpe o una chica de espaldas
  al espejo son sanción.

- **🚫** marca el producto **sin stock** (ya no está en TikTok Shop), como en
  POV BOF. Es del PRODUCTO, no del usuario (`sin_stock` en el documento común,
  `POST /multimodo/sin-stock`). El vídeo se queda en su puesto, tachado. Cuenta
  como cerrado para dar la tanda por terminada y «Bajar» se lo salta,
  conservando el número de puesto de los demás. Si el producto vuelve, se pulsa
  otra vez. **No rehagas ni generes nada de un producto sin stock.**

No marques Subido/Escaparate/Vendió/Sin stock salvo que te lo pidan: eso es de
quien publica.

Cada vídeo trae **🎵 la música que le va** (`musica` en la API): una búsqueda
para la biblioteca de sonidos de TikTok, otras de repuesto y el estilo. Sale
de `config.MUSICA_MULTIMODO`: cada formato tiene 3-4 ESTILOS (jazz, francesa,
bossa nova, country, house…) y a cada producto le toca uno, así una tanda no
suena toda igual. Se suman búsquedas de la temporada del día (otoño, invierno,
Navidad) y, del 10 al 31 de octubre, de Halloween.
