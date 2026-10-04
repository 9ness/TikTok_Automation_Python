# POV BOF Largo — `/tiktok-shop-ai-pro/pov-bof-largo`

Lee antes [`README.md`](README.md) y las tres guías de [`comun/`](comun/).
**Recetas exactas de punta a punta (Flow, GenAI Pro, Kling, revisión, subida, errores):
[`pov-bof-largo-recetas.md`](pov-bof-largo-recetas.md)** — imprescindible si continúas
el trabajo desde el VPS.

## Qué sale

Un vídeo de **16-40 s** por producto: una **mano en primera persona señalando
el producto** (imagen generada), animada en **2 a 5 clips** pegados, con una
**voz Fish** que lee un guion escrito por IA para ESE producto. La app pone
la voz, los subtítulos, el nombre del producto, la flecha al carrito y limpia
los metadatos. **El clip va mudo**: el audio que traiga se descarta.

Tu trabajo: **1 imagen por producto** y **tantos clips como huecos tenga su
tarjeta**.

## Qué preguntar además de lo común

- **Modo del guion**: «Precio» (urgencia de precio) o «Punto de dolor». Es un
  interruptor de TODA la pantalla y cada modo lleva su propio progreso,
  guiones y vídeos.
- **Clips de 8 s o 10 s** para la carpeta (por defecto, 8 s).
- **Plataforma del clip**: Flow, GenAI Pro o Magnific (las tres valen porque
  el clip va mudo).

## Paso a paso

### 0. Situarte
1. Abre `/tiktok-shop-ai-pro/pov-bof-largo`.
2. **«📁 Dónde trabajas»** → **Catálogo** (ej. «📦 Inventario General»,
   «🌐 Productos Web», «Muestras productos», «Tareas Productos»,
   «Top vendidos») → chip de la **carpeta**.
3. Arriba de los pasos, **«Modo del guion · todo el catálogo»**: pulsa
   «Precio» o «Punto de dolor» según lo acordado. (Si ya está en ese, no
   toques.)

### 1. Paso 1 (violeta) · «Preparar textos y guion»
1. Si el botón dice **«Obtener textos (x/y)»** con x < y, púlsalo: lee título,
   tienda y precio de las fichas (~1 min) y **encola solo los guiones que
   falten**. Si dice «Textos al día», no hace falta.
2. Si queda algún producto sin guion, **«Escribir todos los guiones (n)»**.
   ⚠️ Si el botón dice **«Rehacer los N guiones»**, NO lo pulses sin permiso
   (reescribe lo que ya está).
3. **«Clips de toda la carpeta: 8s | 10s»** → el acordado. Esto cambia cuántos
   huecos de clip pide cada tarjeta.
4. Espera a que la cola termine y recarga los productos si hace falta. Cada
   tarjeta enseña un chip **«🎬 15-16s»** (la duración del guion) y los huecos
   **«Clip 1»…«Clip n»**. Si un chip sale con «⚠️», el guion está desfasado:
   la app lo reescribe sola al montar, no hace falta tocarlo.

### 2. Paso 2 (fucsia) · «Generar los clips fuera»
1. **«Fotos x/y»** (o **«🔗 Con URL (n)»** si solo trabajas los que tienen
   ficha) → baja las fotos limpias. Muévelas a
   `<Carpeta>/<nº>_<título>/foto_limpia.jpg`.
2. **«Prompt imagen (NB2 · 9:16)»** → cópialo. Es el MISMO para todos los
   productos.
3. **«Prompt vídeo»** → cópialo. También es el mismo para todos.
4. Por cada producto, en **Google Flow** (imagen, Nano Banana 2, 9:16, 1
   resultado): adjunta su **foto limpia** + pega el prompt de imagen. Revisa
   con [`revision-calidad.md`](comun/revision-calidad.md): el producto
   idéntico, la mano señalándolo sin tocarlo, sin precios ni texto.
   → `imagen_1.png`.
5. **Clips**: mira en la tarjeta cuántos huecos pide (**«Clip 1»…«Clip n»**;
   la franja de color y los botones «2 clips / 3 clips / 4 clips» del paso lo
   agrupan). Genera ese número de clips **desde la misma imagen**:
   - **GenAI Pro**: Frames · start + end = `imagen_1.png` las dos · 9:16 ·
     8 s · 1 vídeo · Original · pega el «Prompt vídeo».
   - **Magnific**: space «Foto con IA → vídeo» (o el «(2)»), sube
     `imagen_1.png`.
   - **Flow**: vídeo, FRAME INICIAL = `imagen_1.png`, 8 o 10 s, pega el
     «Prompt vídeo».

   Revisa cada clip (el producto no se deforma, la mano no lo toca) →
   `clip_1.mp4`, `clip_2.mp4`…

### 3. Subir a editar (en la tarjeta de cada producto)
0. **Ordena los clips con criterio antes de subirlos** (petición del operador,
   1/10/2026). Mira los fotogramas de todos los clips del producto y no los subas
   en el orden en que salieron:
   - **Clip 1 = el que mejor enseña el producto** (entero, reconocible, como en la
     ficha): engancha y deja claro qué se vende.
   - Luego una progresión que el espectador note: cerca → lejos (detalle →
     contexto), uno → varios (una silla con funda → el comedor con cuatro), de
     día → de noche / encendido al final si el producto da luz.
   - Si el guion nombra algo en un momento (una pieza, el uso), que ese tramo lo
     enseñe.
1. Antes de subir, en la tarjeta:
   - **Voz**: deja «🖐️ Auto» (la IA decide por la mano: mujer salvo reloj o
     vello) salvo que el operador diga otra cosa.
   - **Herramientas** (chip «✨ n/5»): déjalas como están. Por defecto van
     gancho, texto del producto, CTA, flecha y subtítulos (obligatorios
     contra la sanción). «💬 Subliminal» va apagado.
2. Sube **«Clip 1»**, **«Clip 2»**… uno en cada hueco, en orden. Al llenar el
   último, la app **encola el montaje** y **borra los clips del hueco** (si el
   montaje falla, habrá que volver a subirlos: guárdalos siempre).
3. Espera a **«▶ Ver vídeo · <voz>»**. Míralo entero (checklist final de
   [`revision-calidad.md`](comun/revision-calidad.md)).

### 4. Paso 3 (azul) · «Descargar lo ya montado»
- **«Vídeos x/y»** o **«🔗 Con URL (n)»** → a `<Carpeta>/videos/`.
- En el VPS ya están en
  `~/gdrive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF_Largo/videos/<catálogo>/<carpeta>/<nº título HHMM>.mp4`.

### 5. Marcas (solo si te lo piden)
«🏪 Escaparate», «📤 Subido», «💰 Vendió» en la última fila de la tarjeta.
Aquí «Vendió» **no** marca «Subido» solo. La carpeta: «Completada».

## Límites y trampas

- Con clips de 8 s y guion de 40 s la tarjeta pediría **5 clips**, pero la
  pantalla solo enseña 4 huecos: el montaje no arrancaría. Si ves un producto
  así, **no lo hagas y avisa**.
- Las fuentes «1 Prod Aleatorios» / «2 Prod Aleatorios 2» (Drive antiguo)
  todavía salen aquí; no trabajes en ellas salvo que te lo pidan.
- No hay botón de «volver a montar con los clips que ya están»: si un montaje
  falla, vuelve a subir los clips.
- «🚫 Sin stock» → sáltalo.
- «🔁 Rehacer» (lo marca el operador al revisar un vídeo; el chip de la
  carpeta cuenta cuántos hay; el MCP los lista todos con `para_rehacer(menu)` y los da en `avisos` y en `rehacer` con su
  nota): rehaz ese producto —fotos nuevas en Flow si hace falta, otro
  escenario para cada clip, y la nota dice qué falló— y vuelve a subir los
  clips. La marca se quita sola al montarse el vídeo nuevo, y el producto pasa a la carpeta virtual **«🔁 Rehechos»** (arriba del todo en la lista de carpetas, con la nota de qué se arregló) hasta que el operador lo marca «📤 Subido». Sin ficha («URL» en gris) → se puede hacer, pero
  no se podrá publicar con carrito: pregunta.

## ⚡ Modo «Épico» (oct 2026)

Tercer modo del guion, junto a «Precio» y «Punto de dolor». Es el de dolor del
curso, pero con un gancho de menos de 3 s y frases cortas. El guion marca de 2 a 4 (según cuántas frases potentes tenga)
**golpes**: en cada uno la voz se calla, entra un **inserto** de 1 s (el
producto con fondo épico, el texto grande arriba y un golpe de sonido) y sigue
la voz. Las pausas de antes y de después se recortan solas. Patrón y pruebas:
`_agente/ness/referencias_epico/analisis/`.

Por producto, además de sus clips normales:
1. `plan_producto` lista los golpes (`epico_N.png` / `epico_N.mp4`): texto en
   pantalla, frase y escena.
2. **Imagen (Flow, Nano Banana 2, modo imagen)**: adjunta un **fotograma de TUS
   clips** del producto y pide «edita esta imagen manteniendo producto y mano
   EXACTAMENTE iguales; cambia SOLO el fondo». Fondo según el producto:
   escenario negro con foco cenital y neblina (tecnología, herramientas,
   muebles) o blanco a contraluz (cosmética, hogar claro). Revísala contra la
   foto limpia: color y logo exactos. La luz cálida tira el color, así que pide
   luz neutra.
3. **Clip (Magnific, Kling 2.5 · 9:16 · 5 s · 720p ∞)** en el **«Video
   Generator #4»** del Space (lo alimenta la «List #5»; los clips POV de 10 s
   van en el #3 con la «List #3»). **No toques el «Video Generator #1»** (10 s,
   prompt de otros flujos). Prompt: acercamiento lento de cámara, el producto y
   la mano quietos, sin texto. Kling 2.5 no admite imagen final; Kling 2.6 sí,
   pero solo en 1080p y con créditos, así que no se usa. Del clip solo se usa
   el segundo 1-2: lo que pase después no se ve.
4. `subir_clip(..., inserto=N)` por cada golpe. El montaje arranca cuando están
   los clips normales y todos los insertos.

### Variedad: que no salgan todos iguales (análisis del 2 oct 2026)

Sale de un vídeo de ejemplo que pasó el operador (una creadora que copia al
viralizador original; `diferentes_efectos_apico.mp4` en su Drive): 7 cortes
épicos en 21 s. Lo que hace y lo que ya hace la app:

| En el ejemplo | En la app |
|---|---|
| Los cortes **oscuros** llevan TODOS el mismo «sting» de 1 s (nota sostenida en La y golpe a 0,55 s), a −25 dB, más bajo que la voz | Cada vídeo sortea UN sonido para sus insertos oscuros entre `golpe_clasico` (el que eligió el operador), `sting_trailer` (el del ejemplo) y `ritmo_tambores`. Dentro de un vídeo no cambia; entre vídeos, sí |
| El corte de **fondo blanco** suena distinto: un **boom grave sostenido**, mucho más fuerte (−13,5 dB, 95 % de la energía por debajo de 150 Hz) | Si el inserto es de fondo blanco (se mide solo, por el brillo del tercio de arriba), lleva `boom_grave` |
| Fondo blanco + **titular ROJO con serifa** («VESTIDO PISTACHO»), sin oscurecer la imagen | Fondo blanco → texto rojo `#D7261E` en Playfair Display Black, ajustado al ancho, sin viñeta ni oscurecido. Fondo oscuro → letra blanca con borde negro (como antes) |
| Fondos: humo **dorado/ámbar** con foco cálido, humo **azul-gris frío**, foco cenital sobre negro y blanco | Varía tú el fondo en la imagen de Flow (abajo) |
| Los cortes oscuros **no llevan texto**; el remate final es un montaje de 3 cortes seguidos con un ritmo de tambores | No se hace (el operador pidió texto en cada golpe). Si algún día se quiere, es aquí |

Los sonidos están en `assets/sfx/epico/` (se sacaron del ejemplo: los cuatro
cortes oscuros promediados, para limpiar la voz). Para añadir uno, deja el
`.wav` (1 s, normalizado a −1 dBFS) en esa carpeta y súmalo a
`config.SONIDOS_OSCURO`.

**Cómo variar al generar las imágenes épicas** (el fondo lo decides tú):
- Mezcla en un mismo vídeo un inserto **oscuro** y uno **blanco a contraluz**:
  el blanco es el que se lleva las letras rojas y el boom, y es el que más
  impacta. Guárdalo para la característica más fuerte, no para el gancho.
- En los oscuros alterna entre vídeos: «foco cenital blanco + neblina sobre
  negro», «humo dorado/ámbar con luz cálida desde arriba» (cuida el color del
  producto: pide que conserve sus colores reales) y «humo azul-gris frío».
- Productos claros (blancos, rosas, cosmética) quedan mejor en oscuro; productos
  negros (muebles, herramientas) se pierden sobre negro: blanco a contraluz o
  humo dorado.

**Ojo con la foto del producto**: muchas fichas son un montaje de catálogo con
los accesorios sueltos al lado (gomas, cables, mandos). Si la imagen copia
eso, los accesorios salen **flotando en el aire** y el vídeo no se puede
publicar (pasó con el banco de pesas, oct 2026). En la escena di DÓNDE están:
«las gomas, recogidas en el suelo junto a la pata del banco», nunca «colgadas».

## 🔄 Modo «Venta inversa» (oct 2026)

Cuarto modo del guion (`estilo_guion="inversa"`), el que el curso sacó en su web
(«Venta inversa · Irónica») sin publicar el prompt. El nuestro está en
`prompts/guion_inversa.md`, hecho por ingeniería inversa de dos generaciones de
la web (`docs/venta_inversa/`).

- Forma: gancho irónico («El gran problema de… es que…», «No lo compres si no
  quieres…», «Ni se te ocurra…») → negaciones con DATOS reales de la ficha →
  (en 30 s) cómo se usa → «El único problema es que… / Lo peor es que…» →
  cierre de disponibilidad: «Te lo voy a intentar dejar en el carrito naranja,
  pero no puedo asegurarte que siga disponible cuando veas el vídeo».
- **Una sola duración: 3 clips** (~24 s; con clips de 10 s se recortan). El
  guion «de 15 s» de la web son ~400 caracteres (~22 s de voz) y en 2 clips no
  cabe sin mutilar el cierre. Lo fija `config.SEGUNDOS_INVERSA`, pida lo que
  pida el producto.
- Ningún dato ni frase se repite (la web repetía «120 kilos» dos veces).
- Sin urgencia de precio ni frase de plazos. La escalera de cierres al locutar
  es la suya (`config.CTAS_INVERSA`); el recorte por precio no la toca.
- Revisa la ironía: que se entienda que lo recomiendas, sin efectos sobre el
  cuerpo («te pone en forma») ni datos inventados (programas, niveles).

## 🎄 Productos Q4 (Black Friday y Navidad)

Carpeta de temporada dentro de **📦 Inventario General**, la primera de la lista
(solo la ve `ness`). Son COPIAS de productos del inventario (fotos + textos):
el original no se toca y en la copia el guion, los clips, el vídeo y las marcas
son nuevos, así que se puede repetir un producto ya publicado.

- Añadir: MCP `anadir_a_q4(productos=["inventario_general|Carpeta_22|3", …], clips=3)`
  (API: `POST /api/v1/nicho-pov-bof-largo/q4/anadir`). Idempotente.
- `clips=3` deja el guion en 24 s (tres clips de 8 s): una imagen por clip, tres
  sitios distintos.
- Después, como cualquier carpeta: `preparar_carpeta(catalogo="inventario_general",
  carpeta="Productos Q4", clip_s=8, estilo_guion=…)`. El modo es del catálogo
  entero: si se hace media carpeta en «precio» y media en «dolor», cada mitad se
  ve con su modo activo.
- Ángulo de campaña: `campanas` y [`comun/campanas.md`](comun/campanas.md). Nada
  de prometer ofertas que la ficha no tenga.

## Lo que aprendimos haciendo carpetas enteras (sep 2026)

Sale de ~55 productos (5 carpetas de Inventario en «dolor» + 5 de Tareas en
«precio»). Seguirlo ahorra la mitad de las repeticiones:

- **Una imagen por clip, cada una en un sitio distinto** (cocina / salón,
  taller / suelo junto a un enchufe…), no dos clips de la misma imagen: el
  vídeo parece otro plano en vez de repetirse.
- **El producto IDÉNTICO en todos los clips** (oct 2026, cinco vídeos a rehacer
  de golpe). Si cada imagen sale solo de la foto limpia, el generador inventa
  detalles distintos en cada una: un tapón transparente donde era negro, un
  botón que desaparece, tiradores negros en un clip y dorados en otro, un
  cepillo con otra cabeza. Haz la **imagen del clip 1**, revísala contra la ficha
  y, para los demás clips, adjunta en Flow la foto limpia **y esa imagen** con la
  frase «la segunda imagen es el MISMO producto: idéntico (forma, piezas,
  botones, colores, detalles); solo cambian el sitio, el encuadre y la luz».
  Antes de subir, pon las 3 imágenes una al lado de otra y compáralas pieza a
  pieza.
- **Cada imagen, según lo que dice la voz en ESE clip** (oct 2026). El plan
  trae `dice_la_voz_en_este_clip` en cada imagen: con 3 clips o más la voz se
  reparte a partes iguales, así que el tramo es casi exacto. Si nombra una
  característica, que se vea («aguanta 120 kg» → el banco con discos al lado;
  «plegable» → plegado junto a la pared; «con mando» → el mando bien visible);
  si nombra un uso o un sitio, ese sitio. La persona NUNCA usa el producto:
  solo la mano que señala. Si el tramo es genérico (cierre, CTA), elige el
  plano que mejor enseñe el producto entero. Sube los clips en el orden del
  guion, no al azar.
- **Lee título y ficha antes de escribir la escena**: tamaño real (un mini
  móvil de 8,9 cm junto a una taza para que se vea diminuto; una carpa 3×3 o
  una bici enteras en el plano, señaladas desde lejos), para quién es
  (infantil ≠ adulto) y si es un pack (salen TODAS las piezas). Quita de la
  foto medidas, flechas y sellos tipo «TOP PICKS».
- **NUNCA niños ni bebés** en imágenes ni clips, tampoco en productos
  infantiles (juguetes, organizadores de LEGO, cosas de bebé): TikTok lo
  sanciona fuerte. La escena infantil va SIN personas (un cuarto de niño,
  una sala de juegos) y la única persona es la mano adulta del POV. Escríbelo
  en la pista («sin ningún niño ni persona aparte de la mano») y revisa que
  no se cuele ninguno, ni al fondo, ni en fotos o dibujos realistas.
- **Para dar escala, nunca un objeto de la MISMA categoría** que el producto:
  nada de otro móvil junto al mini móvil, otra botella junto al termo, otra
  crema junto a la crema. Usa objetos neutros (taza, llaves, un libro). El
  vídeo del mini móvil con un móvil normal al lado se sancionó (-24) y la
  apelación se rechazó (ver `APELACIONES.md`).
- **Espejos**: el reflejo confunde al generador (dobles marcos, manos
  duplicadas). Ponlo de frente o ligeramente girado, nunca muy de lado (de
  lado el marco parece más grueso), y revisa que el marco no cambie de forma.
  Que las luces de un espejo LED se enciendan o apaguen NO es un fallo: es una
  función del producto. El espejo MIKOMIKA sancionado (-24) salía muy de lado
  y la mano le agarraba el borde.
- **Productos con pantalla** (móviles, relojes, multímetros): pide la
  pantalla apagada o con la MISMA imagen que la foto limpia, y rechaza el
  clip si el generador la enciende con iconos o menús inventados.
- **Que el dedo roce el producto en la imagen NO es motivo de repetirla** (lo dijo el operador): lo que se rechaza es el CLIP en que el producto se mueve, se deforma o la mano lo coge/gira.
- **La mano**: «la mano lo señala con el dedo índice desde unos 15 cm, SIN
  tocarlo». Con productos pequeños (multímetro, powerbank) Nano Banana pone
  el dedo encima aunque se pida lo contrario → repite la imagen; un dedo
  apoyado acaba en el clip agarrando o girando el producto. Pide el dedo
  índice explícitamente (una vez salió un gesto ofensivo).
- **Postura estable**: los aparatos pequeños mejor **tumbados** sobre la mesa
  que de pie; de pie, Kling tiende a moverlos o girarlos.
- **Aparatos con luz**: pídelos ENCENDIDOS (lámparas, LED, luces de
  crecimiento). Que en el clip se enciendan pantallas no es un fallo.
- **Revisa sobre todo el último segundo del clip**: es donde Kling gira la
  bici, hace aparecer un teclado o la mano coge el bote. Ver los rechazos
  típicos en [`revision-calidad.md`](comun/revision-calidad.md).
- Productos con 3 clips (guion largo): súbelos con `subir_clip(clip=3)`; con
  el último hueco se monta solo.
- Al terminar la carpeta (todos «▶ Ver vídeo»), márcala «Pendiente» si el
  operador lo pide (`marcar_carpeta(pendiente=true)`); no marques Subido ni
  Escaparate.

## API útil (solo lectura, con la sesión del navegador)

- `GET /api/v1/nicho-pov-bof-largo/productos?source=<catálogo>&folder=<carpeta>`
  → productos con guion, duración, clips necesarios y estado del vídeo.
- `GET /api/v1/nicho-pov-bof/prompts` → `imagen` y `video` (los dos prompts).
- `GET /api/v1/nicho-pov-bof-largo/folders?source=<catálogo>` → carpetas y
  progreso.

Slugs de catálogo: `inventario_general`, `productos_web`, `mis_productos`
(«Muestras productos»), `tareas_productos`, `top_vendidos`.

## Con el MCP

Con el MCP: `menu="pov_bof_largo"` · `preparar_carpeta(..., clip_s=8|10, estilo_guion="precio"|"dolor")`. `subir_clip(clip=N, voz="auto")` por cada hueco; con el último se monta solo. Con el MCP **sí** se pueden hacer los productos de 5 clips (la pantalla solo enseña 4 huecos).
