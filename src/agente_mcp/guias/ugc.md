# Nicho General · UGC — `/tiktok-shop-ai-pro/nicho-general`

Lee antes [`README.md`](README.md) y las tres guías de [`comun/`](comun/).

## Qué sale

Un **anuncio UGC de 3 clips** (más si la tienda pide una duración mínima,
hasta 8): **1) dolor o gancho → 2) producto y beneficios → 3) urgencia y
CTA**. La misma persona (un **personaje**) sale en las tres escenas y **habla
dentro del clip** → **todo en Google Flow** (imagen Nano Banana 2 y vídeo
Omni). La app ordena los clips por lo que dicen, recorta el silencio del
principio, quema un texto los primeros 4 s (sin tapar la cara), pone la flecha
y limpia metadatos.

Coste de referencia: 3 imágenes + 3 clips por producto (3 × 12 créditos a
8 s, 3 × 15 a 10 s) + la imagen del personaje.

## Qué preguntar además de lo común

- **Gancho**: «Punto de dolor» o «General».
- **Duración de cada clip**: «10 s · Omni» u «8 s · GenAI Pro (Veo)». ⚠️ Aunque
  la etiqueta diga GenAI Pro, el clip habla: **se hace en Flow** a 8 s. El
  guion se escribe para esa duración, así que se elige ANTES de escribir las
  escenas.
- **Personaje**: el del nicho del producto que propone la tarjeta (lo normal),
  o el personaje fijo de la cuenta si el operador lo tiene (Paso 0).

Gancho y duración son la clave del anuncio: cada combinación es un anuncio
distinto con sus propias escenas y clips.

## Paso a paso

### 0. Situarte
1. Abre `/tiktok-shop-ai-pro/nicho-general`.
2. «📁 Dónde trabajas» → **Catálogo** (por defecto «📦 Inventario General»)
   → **Gancho** → **Duración de cada clip** → chip de la **carpeta**.

### Paso 0 · «Crear tu personaje» (plegado; una vez por cuenta)
Solo si el operador quiere un personaje fijo para la cuenta y aún no existe:
foto de cuerpo entero de Pinterest (pelo suelto, manos a la vista, sin marca de
agua) → «Copiar prompt de personaje» → pégalo en **Gemini** con esa foto → la
descripción que devuelve se genera en **Flow** → guarda la imagen como
`personaje.png`. **Pregunta antes**: es la cara de la cuenta.

### 1. Paso 1 (violeta) · «Escribir las escenas»
1. **«Obtener textos (x/y)»** si falta.
2. **«Escribir las escenas que falten (N)»** → la app escribe, por producto,
   las 3 escenas: prompt de imagen, prompt de vídeo y lo que se dice. (Cola,
   ~1 min.) «Rehacer todas las de esta carpeta»: **no** sin permiso.

### 2. Paso 2 (fucsia) · «Generar los clips fuera»
1. **«Todas las fotos (N)»** → fotos limpias de los productos.
2. Por cada producto, en su **tarjeta**:
   1. **Personaje**: la tarjeta tiene un selector de nicho (Belleza, Hogar,
      Exterior…) y los botones **«👩 Mujer» / «👨 Hombre»**. Copia el
      **marcado** (el que casa con la voz de los guiones ya escritos) → Flow,
      imagen, 9:16 → `personaje.png`. Si tocas el otro (sale con ✨), la app
      reescribe los guiones de ese producto para ese sexo: solo si te lo piden.
      Si el operador usa personaje fijo de cuenta, sáltate esto y usa el suyo
      — pero comprueba que el sexo coincide con el marcado.
   2. **Fotos** — bloque «Fotos · en Flow (Nano Banana 2 · 9:16), con el
      personaje y el producto»: para cada **«📸 Foto 1/2/3»**, adjunta
      `personaje.png` + la foto limpia del producto y pega → `imagen_1.png`,
      `imagen_2.png`, `imagen_3.png`. El «?» explica qué se ve en cada una.
      Revisa: **la misma persona en las tres**, el mismo escenario, el
      producto idéntico.
   3. **Vídeos** — bloque «Vídeos · sobre la foto de cada escena»: para cada
      **«🎬 Vídeo n»**, Flow, vídeo Omni, **FRAME INICIAL = imagen_n.png**, la
      duración acordada, pega → `clip_n.mp4`. Revisa que dice su texto entero,
      en español de España, con la voz del sexo correcto.
   4. El recuento de caracteres de cada escena sale en ámbar si se pasa: esa
      escena puede cortarse. Si pasa, **«↻ rehacer»** esa escena (avisa).

### 3. Subir y montar (en la tarjeta)
1. Sube los clips en los huecos **«Clip 1» … «Clip N»** (el orden lo arregla
   la app, pero súbelos en orden).
2. Deja marcado **«Recortar el silencio del principio de cada clip»**.
3. **«Texto de los primeros 4 s»**: déjalo como lo propone la app salvo que el
   operador diga otra cosa.
4. «Hashtags y menciones que pide la tienda» (Muestras/Tareas): si la tienda
   los pide y el operador te los dio, pégalos ahí.
5. **«Montar (N)»** → cola. Espera a «Ver vídeo» / «Montado el …» y revísalo.

### 4. Paso 3 (azul) · «Descargar lo ya montado»
**«Vídeos (N)»** → `<Carpeta>/videos/`. En el VPS:
`~/gdrive/TIKTOK_SHOP_AI_PRO/Nicho_General/<usuario>/<carpeta>/ugc_<producto>_<gancho>_<dur>_<ts>.mp4`
(búscalo también bajo `NEBULABS_AUTOMATED_TIKTOK/` si no aparece).

## Trampas

- Esta pantalla **no** muestra el aviso de caption arriesgado: revisa tú que
  los textos no prometan resultados que la ficha no dice.
- «✕ Quitar los N clip(s)» borra los subidos: solo si hay que rehacerlos.
- Los usuarios `ana` y `mauro` pueden no tener acceso a este menú.

## API útil (solo lectura)

- `GET /api/v1/nicho-general/config` → ganchos, duraciones, nichos.
- `GET /api/v1/nicho-general/productos?source=<catálogo>&folder=<carpeta>&gancho=<dolor|general>&duracion=<8|10>`
  → cada producto con sus escenas (`prompt_imagen`, `prompt_video`).

## Con el MCP

Con el MCP: `menu="ugc"`, `gancho="dolor"|"general"`, `duracion="10"|"8"`. `plan_producto` trae la ficha del personaje, las fotos y los vídeos de cada escena. Tras subir los clips, `montar(...)` (o `subir_clips_de_bandeja`, que ya monta).
