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

### 6. Muestras reembolsables («Muestras productos» y «📦 Productos físicos»)
Una muestra REEMBOLSABLE la paga el operador y la tienda se la devuelve si el
producto llega a X ventas antes de una fecha.

**Dónde va cada producto:** si Néstor lo TIENE en casa (lo pidió como muestra y
le llegó), va a **«📦 Productos físicos»** (`productos_fisicos`; Ana:
`productos_fisicos_ana`), y si además la tienda pide ventas para el reembolso
se marca 💸 ahí. **«Muestras productos»** (`mis_productos`) se queda para lo
que se trabaja solo con IA. Las tres fuentes admiten la marca; ninguna más.

En la tarjeta sale el badge
«💸 Reembolsable · 1/3 ventas · faltan 45 días» (🔔 si toca revisar, ✅ cumplido,
⛔ vencido) y arriba la caja «💸 Muestras reembolsables» con todas las de los
catálogos que ve la cuenta, cada una con su catálogo (tocarla abre su carpeta).
- **Marcar:** en la tarjeta «💸 ¿Reembolsable?» (ventas necesarias + días que
  quedan + **dinero que devuelven**, `importe` en €: es lo que ordena la
  prioridad — una de 45 días que da 30 céntimos importa menos que una de 10 €), o al darla de alta en **«Subir productos»** eligiendo «Productos
  físicos» o «Muestras productos» y el check «Muestra reembolsable» (nace con
  0 ventas). Por MCP no hay alta de productos: el operador la sube y tú la
  marcas con `marcar_reembolsable(..., catalogo="productos_fisicos")` (por
  defecto `mis_productos`).
- **Revisar cada 3 días** (`REVISAR_CADA_DIAS`): mira las ventas del producto en
  TikTok Shop y apúntalas («+1 venta» / `actualizar_reembolsable(ventas=N)`); si
  no hay nuevas, «Revisado, sin ventas» (`actualizar_reembolsable` sin cambios)
  para quitar la 🔔.
- **Si no vende:** más versiones del vídeo (otro estilo en POV BOF Largo) o un
  viral del mismo producto que replicar (`replicar_viral`). Avisa al operador
  cuando falten pocos días.
- Herramientas MCP: `reembolsables(catalogo="")` (lista de todos los
  catálogos que ve la cuenta, primero las que toca revisar; cada item trae
  `source` y `catalogo`), `marcar_reembolsable(carpeta, producto,
  ventas_objetivo, dias, importe=..., catalogo=...)`, `actualizar_reembolsable(...,
  sumar_ventas=1 | importe=..., catalogo=...)` («he vendido una más» = `sumar_ventas=1`), `desmarcar_reembolsable(..., catalogo=...)` — pasa siempre
  como `catalogo` el `source` del item.

### 7. Marcas de producto y prioridades (todos los catálogos del operador)
Un producto de «Muestras productos», «Tareas Productos», «Productos físicos»,
«Temporada Q4»… puede llevar VARIAS marcas a la vez (`services/marcas.py`):
- **🎥 Físico** (`fisico`): lo tiene en casa → se puede grabar real (aunque
  también se le puede hacer IA). Los de «Productos físicos» lo son siempre.
- **📣 Necesita contenido** (`contenido_videos=N`, 1 por defecto, 3 si la tienda
  lo pide): cada vídeo del producto marcado **Subido en Mis tandas** (POV BOF o
  Largo) descuenta uno; al llegar a 0 sale «✅ contenido hecho» y pierde la
  prioridad. Desmarcar el subido lo devuelve.
- **🎄 Q4** (`q4`): funciona ahora en Q4 (desempata el resto).
- **📁 Clips reales** (`clips_reales`): la carpeta del Drive con las tomas
  grabadas de ese producto (ruta del mount o enlace). Antes de montar un vídeo
  real, mira ahí.
Se marcan al darlo de alta en «Subir productos», en la fila «🏷️ Marcas» de la
tarjeta (POV BOF y Largo) o con `marcar_producto(carpeta, producto,
catalogo=..., fisico=, contenido_videos=, q4=, clips_reales=)`.

**Qué hacer primero:** `prioridades(catalogo="", solo_fisicos=False,
incluir_resto=False)` (y la caja «🎯 Prioridades» de «Subir productos»):
1) necesita contenido, el que menos vídeos le faltan antes; 2) reembolsables en
curso, el que más dinero devuelve antes; 3) con `incluir_resto`, el resto, primero
los de Q4. Cada item trae `grupo` y `motivo`. Para grabar en real:
`solo_fisicos=True`.

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
- `GET /api/v1/nicho-pov-bof/reembolsables[?source=…]` (y `POST /reembolsable/{marcar,actualizar,desmarcar}` con `source` en el cuerpo, por defecto `mis_productos`)
- `GET /api/v1/nicho-pov-bof/prioridades[?source=…&solo_fisicos=&incluir_resto=&limite=]` · `POST /api/v1/nicho-pov-bof/marcas`

Slugs de catálogo: `mis_productos`, `tareas_productos`, `productos_fisicos`
(ness/nestor2) y `productos_fisicos_ana` (Ana) — lo que tienen en casa y graban de verdad —, `productos_web`,
`inventario_general`, `top_vendidos`.

## Con el MCP

Con el MCP: `menu="pov_bof"` · `preparar_carpeta(..., clip_s=8|10)`. Si el montaje falla, `montar(...)` vuelve a montar con los clips que ya están.
