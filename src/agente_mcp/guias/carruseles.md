# Carruseles — `/tiktok-shop-ai-pro/carruseles`

Lee antes [`README.md`](README.md) y las tres guías de [`comun/`](comun/).

## Qué sale

**No hay vídeo.** Un carrusel de **DOS fotos 9:16** por producto, con un
mensaje quemado encima de cada una (lo hace la app con PIL, sin cola larga):

- **Foto 1 — la chica sorprendida.** NO depende del producto, solo del
  **sitio** (escenario): cama, sofá, cocina, baño, coche, escritorio,
  exterior, calle de noche, playa… Se generan en **tandas por escenario** para
  todos los catálogos a la vez y la app las reparte entre los productos que no
  tienen.
- **Foto 2 — el producto** en el sitio donde se usa, a partir de su foto
  limpia. Esta sí es de cada producto.

Solo valen los productos que tienen sentido con una chica EN el sitio: la app
los filtra («Apto / No apto»).

## Qué preguntar además de lo común

- ¿Trabajo **una carpeta** o **una tanda de escenario / categoría** para todo
  el catálogo? (Lo eficiente es por tandas.)
- Cuántas chicas por escenario (el Paso 2 dice cuántas **faltan** en cada uno).
- ¿Llego a **quemar los textos** y bajar las fotos en orden, o solo genero?

## Paso a paso

### 0. Situarte
«📁 Dónde trabajas» → catálogo → chip de carpeta (el chip dice cuántos
**aptos** tiene).

### 1. Paso 1 (violeta, plegado) · «Preparar la carpeta» — en este orden
1. **«1º Obtener textos»**.
2. **«🔎 2º Filtrar los que valen para carrusel»** (Gemini sobre los títulos).
3. **«✍️ 3º Escribir los dos mensajes (x/y)»**.
Los productos «No apto» se ignoran. No cambies «Apto/No apto» a mano sin
permiso.

### 2. Paso 2 (fucsia, plegado) · «La tanda de chicas (foto 1)»
1. Bloque **«Foto de referencia (chica)»**: descárgala (`referencia_chica.jpg`).
   Se adjunta **SIEMPRE** en Flow con el prompt. Algunos escenarios tienen su
   propia referencia en su tarjeta: si la hay, usa esa.
2. Por cada **escenario** con «faltan N»: copia su **«Prompt»** → Flow,
   imagen, Nano Banana 2, **9:16**, adjunta la referencia + pega. Genera N
   imágenes (una por generación, o varias si Flow lo deja sin gastar de más).
   Revisa: chica adulta, cara de sorpresa natural, el sitio correcto, sin
   texto ni marcas, manos bien.
3. **«Subir tanda (N)»** de ese escenario con todas las buenas a la vez. La
   app las reparte. («Subir de repuesto» = sobrantes para más adelante.)

### 3. Paso 3 (esmeralda, plegado) · «La foto del producto (foto 2)»
1. Descarga las fotos limpias: **«Esta carpeta (N)»** o por **categoría**
   (las de categoría son de TODOS los catálogos, solo las que aún no tienen
   foto 2).
2. Copia el prompt de la categoría → Flow, imagen, 9:16, adjunta **la foto
   limpia de ESE producto** + pega. Una imagen por producto. Revisa con
   [`revision-calidad.md`](comun/revision-calidad.md) (producto idéntico,
   texto del envase sin inventar). Nombra el fichero con el número y título del
   producto.
3. Súbelas: **«Traer las fotos generadas»** (todas de golpe; la IA de la app
   empareja cada foto con su producto — las que no reconoce van a «Sin
   asignar») o, producto a producto, **«Subir foto 2»** en su tarjeta (más
   seguro).
4. «Forzar la mano también en los productos grandes»: déjalo como esté.

### 4. Paso 4 (azul) · «Editar y publicar la carpeta»
1. **«Mandar a editar las fotos de la carpeta»** → quema los mensajes.
   («Poner los textos a TODO el catálogo» hace lo mismo con todo: solo si te
   lo piden.)
2. **«Bajar las N fotos de esta carpeta, en orden»** (salen numeradas 01, 02…:
   la 1 y la 2 de cada producto seguidas) o **«Con URL (N)»** →
   `<Carpeta>/carruseles/`.
3. Revisa que el texto se lee, no tapa la cara ni el producto y no promete
   nada de salud o resultados que la ficha no diga.

Los pasos 5 («Publicar por nicho») y 6 («La frase de la que salen los
mensajes») son del operador: no los toques.

## Dónde queda

En el Drive: `TIKTOK_SHOP_AI_PRO/Nicho_Carruseles/<usuario>/` (original y con
texto en carpetas distintas; el vínculo foto↔producto es el nombre del
fichero `<fuente>__<carpeta>__<producto>.jpg`).

## API útil (solo lectura)

- `GET /api/v1/nicho-carruseles/prompts` → escenarios con su prompt y formato.
- `GET /api/v1/nicho-carruseles/referencia?tipo=chica&descargar=1[&escenario=<clave>]`

## Con el MCP

Con el MCP: el MCP todavía **no** cubre Carruseles (`guia("carruseles")` sí). Hazlo por la web.
