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
- «🚫 Sin stock» → sáltalo. Sin ficha («URL» en gris) → se puede hacer, pero
  no se podrá publicar con carrito: pregunta.

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
