# POV BOF Largo — `/tiktok-shop-ai-pro/pov-bof-largo`

Lee antes [`README.md`](README.md) y las tres guías de [`comun/`](comun/).

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
  carpeta cuenta cuántos hay y el MCP lo da en `avisos` y en `rehacer` con su
  nota): rehaz ese producto —fotos nuevas en Flow si hace falta, otro
  escenario para cada clip, y la nota dice qué falló— y vuelve a subir los
  clips. La marca se quita sola al montarse el vídeo nuevo. Sin ficha («URL» en gris) → se puede hacer, pero
  no se podrá publicar con carrito: pregunta.

## Lo que aprendimos haciendo carpetas enteras (sep 2026)

Sale de ~55 productos (5 carpetas de Inventario en «dolor» + 5 de Tareas en
«precio»). Seguirlo ahorra la mitad de las repeticiones:

- **Una imagen por clip, cada una en un sitio distinto** (cocina / salón,
  taller / suelo junto a un enchufe…), no dos clips de la misma imagen: el
  vídeo parece otro plano en vez de repetirse.
- **Lee título y ficha antes de escribir la escena**: tamaño real (un mini
  móvil de 8,9 cm junto a una taza para que se vea diminuto; una carpa 3×3 o
  una bici enteras en el plano, señaladas desde lejos), para quién es
  (infantil ≠ adulto) y si es un pack (salen TODAS las piezas). Quita de la
  foto medidas, flechas y sellos tipo «TOP PICKS».
- **Para dar escala, nunca un objeto de la MISMA categoría** que el producto:
  nada de otro móvil junto al mini móvil, otra botella junto al termo, otra
  crema junto a la crema. Usa objetos neutros (taza, llaves, un libro). El
  vídeo del mini móvil con un móvil normal al lado se sancionó (-24) y la
  apelación se rechazó (ver `APELACIONES.md`).
- **Productos con pantalla** (móviles, relojes, multímetros): pide la
  pantalla apagada o con la MISMA imagen que la foto limpia, y rechaza el
  clip si el generador la enciende con iconos o menús inventados.
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
