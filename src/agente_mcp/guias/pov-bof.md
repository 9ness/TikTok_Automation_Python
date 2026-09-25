# Nicho POV BOF — `/tiktok-shop-ai-pro/nicho-pov-bof`

Lee antes [`README.md`](README.md) y las tres guías de [`comun/`](comun/).
Es el hermano corto del [POV BOF Largo](pov-bof-largo.md): mismo tipo de
imagen y de clip, guion más corto (~10 s).

## Qué sale

Un vídeo de **~10-12 s** por producto: **mano en primera persona señalando el
producto** (imagen generada) animada en **1 o 2 clips**, con voz Fish que lee
un guion de ~190 caracteres escrito para ESE producto. La app pone voz,
subtítulos, gancho «CUPÓN DESCUENTO», nombre del producto, CTA, flecha y
limpia metadatos. **El clip va mudo** (el audio se descarta).

**Cuántos clips: lo que diga la tarjeta** (huecos «Subir clip» = 1, o
«Clip 1» + «Clip 2» = 2). Normalmente: clip de 10 s → 1; clip de 8 s → 2.

## Qué preguntar además de lo común

- **Clips de 8 s o 10 s** (por defecto, 10 s). Con 10 s, **GenAI Pro no
  sirve** (llega a 8 s): usa Flow o Magnific.
- **Plataforma del clip**: Flow, GenAI Pro (solo 8 s) o Magnific.

## Paso a paso

### 0. Situarte
1. Abre `/tiktok-shop-ai-pro/nicho-pov-bof`.
2. **«📁 Dónde trabajas»** → **Catálogo** («Muestras productos», «Tareas
   Productos», «🌐 Productos Web», «📦 Inventario General», «Top vendidos»)
   → chip de la **carpeta**. Se abre la caja de la carpeta con «Anterior /
   Siguiente».

### 1. Paso 1 (violeta) · «Preparar la carpeta»
1. **«Obtener textos (x/y)»** si x < y (Gemini, ~1 min). Si pone «Textos al
   día · volver a extraer», no lo toques.
2. **«Guiones de la carpeta (x/y)»** si x < y → escribe los que falten (cola).
3. **«Clips de toda la carpeta: 8s | 10s»** → el acordado.
4. «🏷️ IDs de producto… opcional · PC»: **no hace falta**, sáltalo.
5. Espera a la cola. En cada tarjeta, el chip del guion pasa a
   **«🎬 10-12s»** y aparecen los huecos de clip.

### 2. Paso 2 (fucsia) · «Generar los clips fuera»
1. «Primero, baja las fotos»: **«Fotos x/y»** o **«🔗 Con URL (n)»**. Si hay
   mezcla, salen también «1 clip (n)» / «2 clips (n)» para bajar por grupos.
2. **«Prompt imagen (NB2 · 9:16)»** y **«Prompt vídeo»**: los mismos para
   todos los productos.
3. Por producto, en **Google Flow** (imagen, Nano Banana 2, 9:16, 1
   resultado): **foto limpia** adjunta + prompt de imagen → revisa
   ([`revision-calidad.md`](comun/revision-calidad.md)) → `imagen_1.png`.
4. Genera los clips que pida la tarjeta, **desde la misma imagen**:
   - **GenAI Pro** (solo 8 s): Frames · start + end = `imagen_1.png` las dos ·
     9:16 · 1 vídeo · Original · «Prompt vídeo».
   - **Magnific**: space «Foto con IA → vídeo» (o «(2)»).
   - **Flow**: vídeo, FRAME INICIAL = `imagen_1.png`, 8 o 10 s, «Prompt vídeo».

   Revisa cada clip → `clip_1.mp4` (`clip_2.mp4`).

### 3. Subir a editar (en la tarjeta)
1. **Voz**: «🖐️ Auto» salvo que digan otra cosa.
2. **Herramientas** (chip «✨ n/5»: 🎣 Gancho, 📝 Texto producto, 👉 CTA,
   ⬇️ Flecha, 🔤 Subtítulos): déjalas todas encendidas — el texto del
   producto y los subtítulos son el refuerzo contra la sanción.
3. Sube **«Subir clip»** o **«Clip 1»** y **«Clip 2»**. Con todos los huecos
   llenos: «Los clips están: montando el vídeo.»
4. Si el montaje falla, sale **«🎬 Montar con los clips que ya están»**: úsalo
   una vez (ojo: vuelve a encender todas las herramientas).
5. Revisa el montado con «▶ Ver vídeo».

### 4. Paso 3 (azul) · «Descargar lo ya montado»
- **«Vídeos x/y»** / **«🔗 Con URL (n)»** → `<Carpeta>/videos/`.
- En el VPS:
  `~/gdrive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF/videos/[<usuario>/]<carpeta>/<nº título HHMM>.mp4`
  (sin subcarpeta de usuario si es `ness`).

### 5. Marcas (solo si te lo piden)
«🏪 Escaparate · 📤 Subido · 💰 Vendió» (aquí «Vendió» marca también
«Subido»). La carpeta: «Completada» / «Pendiente».

## Trampas

- **«⚠️ El caption dice «X»…»** → no publicar sin el operador.
- **«💳 Plazos»** en la tarjeta: el guion promete pago a plazos. Comprueba en
  la ficha (miniatura → foto de la ficha) que de verdad los ofrece.
- «→ Copiar a Moda», «🧹 Limpiar», «🗑️ Quitar», «📦 Recolocar»: **no** los
  toques.
- Algunas pistas de la pantalla dicen «la voz sale del banco de audios»: es
  viejo; hoy la voz lee el guion del producto (el banco solo si no hay guion).

## API útil (solo lectura)

- `GET /api/v1/nicho-pov-bof/productos?source=<catálogo>&folder=<carpeta>`
- `GET /api/v1/nicho-pov-bof/prompts` → `imagen`, `video`.
- `GET /api/v1/nicho-pov-bof/folders?source=<catálogo>`

Slugs de catálogo: `mis_productos`, `tareas_productos`, `productos_web`,
`inventario_general`, `top_vendidos`.

## Con el MCP

Con el MCP: `menu="pov_bof"` · `preparar_carpeta(..., clip_s=8|10)`. Si el montaje falla, `montar(...)` vuelve a montar con los clips que ya están.
