# Moda Mujer · Marca Personal — `/tiktok-shop-ai-pro/moda-mujer-marca`

Lee antes [`README.md`](README.md) y las tres guías de [`comun/`](comun/).
Es la misma pantalla que [Moda Mujer · Aleatorios](moda-mujer-aleatorios.md)
(catálogo, pasos y tarjetas iguales); aquí solo cambian los modos y que sale
**siempre el mismo personaje**, que es la identidad de esta cuenta.

## Qué sale

Un clip **mudo** de ~10 s por prenda (la música la pone el operador en TikTok
al publicar). La app recorta a 1080×1920, aplica un grado de color «de
película», quema un **texto de temporada** («AUTUMN / cozy season»; en
zapatos «AUTUMN BOOTS / step into style») y limpia metadatos. No lleva
subtítulos ni nombre del producto (nadie habla).

## Los tres modos

| Botón | Qué es | Imagen: qué adjuntas | Clip: cómo entra la imagen | Productos |
|---|---|---|---|---|
| 🪞 **Espejo Multi Escena 10s** | tu personaje frente al espejo, varias escenas en un clip | **tu personaje + la foto de la prenda** | FRAME INICIAL | cualquier prenda |
| 👢 **Zapatos Multi Escena 10s** | tu personaje con los zapatos, varias escenas | **tu personaje + la foto del zapato** | **INGREDIENTE** (¡no frame inicial!) | **solo calzado** |
| 👟 **Zapatos Vista POV 10s** | los zapatos desde arriba, en primera persona | **solo la foto del zapato** (chica aleatoria) | FRAME INICIAL | **solo calzado** |

⚠️ La pantalla **no filtra** el calzado: en los dos modos de zapatos salen
todas las prendas de la carpeta. Salta tú las que no sean zapatos, botas o
zapatillas.

## Qué preguntar además de lo común

- **Modo** (y recuerda: dos de tres son solo calzado).
- **Dónde el clip** (es mudo): Flow a 10 s (lo normal), GenAI Pro (8 s) o
  Magnific. **Zapatos Multi Escena solo en Flow**, que es el que acepta
  ingredientes.

## El personaje

En el **Paso 3 · «Copiar el prompt»**, debajo de los enlaces a Flow/GenAI Pro,
está el bloque **«👤 Tu personaje»** con su miniatura:

- **«Bajar personaje»** → descárgalo a la carpeta de trabajo como
  `personaje.jpg`. Es el que adjuntas en Flow en Espejo y Zapatos Multi Escena.
- Si pone «Aún no lo has subido», **para y pide al operador** la foto (o que
  la suba con «Subir personaje»). Sin él, cada vídeo sale con una persona
  distinta y la cuenta pierde la marca.
- No uses «Cambiar personaje» sin permiso.

## Paso a paso

1. Abre `/tiktok-shop-ai-pro/moda-mujer-marca` → **«Modo de grabación»** → el
   modo → **«Catálogo»** → chip de la carpeta.
2. **Paso 1 · «Textos de la ficha»** → «✨ Obtener textos (x/N)» si falta.
3. **Paso 2 · «Bajar las fotos»** → «Todas (N)».
4. **Paso 3 · «Copiar el prompt»**:
   - **«1 · Imagen (Flow)»** → Flow, imagen, Nano Banana 2, 9:16, 1 resultado.
     Adjunta lo que diga la tabla (personaje + prenda, o solo el zapato).
     Revisa: **es tu personaje** (misma cara, pelo, cuerpo), la prenda o el
     zapato idénticos → `imagen_1.png`.
   - **«2 · Vídeo (movimiento)»** → el prompt de movimiento, igual para todas
     las prendas. En Flow: vídeo, 9:16, 10 s, la imagen como **FRAME INICIAL**
     o como **INGREDIENTE** según la tabla. En GenAI Pro: start + end =
     `imagen_1.png`. Revisa (en zapatos: no se le ve la cara, no manipula el
     zapato, el zapato no cambia) → `clip_1.mp4`.
5. **Tarjeta** → **«Subir»** el clip. Se monta solo.
6. **Paso 4 · «Descargar lo ya montado»** → «Vídeos x/N» → `<Carpeta>/videos/`.
   En el VPS:
   `~/gdrive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_Ropa_Sin_Personas/videos/[<usuario>/]<carpeta>/<nombre>__<modo>.mp4`.

## API útil (solo lectura)

- `GET /api/v1/nicho-ropa/prompts?carpeta=<slug>&modo=<modo>&modalidad=marca`
- `GET /api/v1/nicho-ropa/prendas?carpeta=<slug>&modo=<modo>`
- `GET /api/v1/nicho-ropa/personaje-marca?descargar=1` → la foto del personaje.

Claves de modo: `marca_espejo`, `marca_zapatos`, `marca_pov`.

## Con el MCP

Con el MCP: `menu="moda_mujer_marca"`, `modo="marca_espejo"|"marca_zapatos"|"marca_pov"`. El personaje: herramienta `personaje_marca` (lo deja en `moda_mujer_marca/personaje_marca.jpg` de la bandeja).
