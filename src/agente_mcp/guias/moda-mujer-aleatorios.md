# Moda Mujer · Aleatorios — `/tiktok-shop-ai-pro/nicho-ropa-mujer`

Lee antes [`README.md`](README.md) y las tres guías de [`comun/`](comun/).
La misma pantalla sirve para [Ropa Hombre](ropa-hombre.md) y
[Marca Personal](moda-mujer-marca.md); cambian los modos.

## Qué sale

Un vídeo por prenda y por **modo**: una **chica distinta cada vez** (generada)
con la prenda PUESTA, que **habla dentro del clip** (la voz la hace el
generador de vídeo, no la app). Por eso **el clip se hace en Google Flow**
(modelo Omni), el único que locuta. La app recorta a 1080×1920 (se come la
marca de agua), pega los clips si son dos, pone subtítulos y flecha en los
formatos de 15 s, y limpia metadatos.

Cuenta de TikTok nueva → **máximo 10 vídeos al día**. Y el curso pide
**mezclar modos**: no hagas 10 del mismo.

## Los seis modos

Se eligen en «Dónde trabajas» → **«Modo de grabación»** (🗣️ = hablado,
🔇 = mudo). El progreso de la carpeta va **por modo**.

| Botón | Clips | Imagen(es) | Guion del clip | Duración |
|---|---|---|---|---|
| 🪞 **BOF Frente a Espejo** | 1 | 1 · foto de la prenda | lo escribe la app por prenda | 10 s (Omni) u 8 s — se elige |
| 🤳 **BOF Selfie** | 1 | 1 · foto de la prenda | lo escribe la app · ⚠️ **promete plazos siempre** | 10 s u 8 s |
| 🚶 **Situación Real 1** | 1 | 1 · foto de la prenda | diálogo fijo del curso, igual para todas | 10 s |
| ☕ **Situación Real 2** | 1 | 1 · foto de la prenda | diálogo fijo del curso | 10 s |
| 🚶‍♀️ **Calle Dividido 15s** | 2 | 2 · la misma chica en dos calles | la app escribe Guion 1 y Guion 2 | 2 × 8 s |
| 🏬 **Tienda Colores 15s** | 2 | 1 por color + 1 de espaldas | la app escribe los dos prompts de Omni | 2 × 8 s |

## Qué preguntar además de lo común

- **Modo** (de la tabla). Si piden «hazme la carpeta» sin modo, propón
  repartir entre dos o tres.
- **10 s u 8 s** en Espejo y Selfie (selector de duración del Paso 3).
- **Plazos**: si una prenda ofrece pago a plazos, ¿quieres el guion que lo
  dice? (por defecto **no**: el de la app no lo menciona y siempre es válido).

## Paso a paso (común a los seis)

### 0. Situarte
1. Abre `/tiktok-shop-ai-pro/nicho-ropa-mujer`.
2. «📁 Dónde trabajas» → **«Modo de grabación»** → el modo.
3. **«Catálogo»**: «📦 Inventario» (el de la web del curso), «🎁 Muestras» o
   «💼 Tareas» → chip **«Carpeta_N»**. El chip dice `con ficha/total`
   (en Tienda Colores, también `🎨N` = prendas con 3+ colores).

### 1. Paso 1 · «Textos de la ficha»
**«✨ Obtener textos (x/N)»** si x < N. En Tienda Colores va a la cola.

### 2. Paso 2 · «Bajar las fotos»
**«Todas (N)»** → fotos limpias de las prendas. (Si salen «Sin plazos» /
«💳 Con plazos», es para separarlas por grupo.) Guárdalas en
`<Carpeta>/<nº>_<título>/foto_limpia.jpg`.

### 3. Paso 3 · «Copiar el prompt»
Arriba de todo, los accesos a **🖼️ Google Flow** (foto) y **🎬 Google Flow**
(vídeo). Después, el bloque del modo con su lista de pasos 1️⃣ 2️⃣ 3️⃣ — **léela
en pantalla**: dice si la imagen va como FRAME INICIAL o INGREDIENTE. Lo
concreto de cada modo va abajo.

### 4. Subir el clip (en la tarjeta de cada prenda)
- Chip de voz: **«Su voz»** (lo normal: se queda la voz del clip). No elijas
  «Mudo», «Voz H» ni «Voz M» salvo que lo pidan.
- **«Subir»** (1 clip) o **«Clip 1»** + **«Clip 2»**. Con el primero de dos
  sale «Clip 1 guardado. Falta el 2 para montar.»; al subir el segundo
  empieza el montaje («montando…»). Los dos clips la app los **ordena por lo
  que dicen**, pero súbelos en orden igualmente.
- Revisa con «▶ Ver vídeo».

### 5. Paso 4 · «Descargar lo ya montado»
**«Vídeos x/N»** o **«🔗 Con URL (n)»** → `<Carpeta>/videos/`. En el VPS:
`~/gdrive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_Ropa_Sin_Personas/videos/[<usuario>/]<carpeta>/<nombre>__<modo>.mp4`.

### 6. Marcas (solo si te lo piden)
Tarjeta: «🏪 Escaparate · 📤 Subido · 💰 Vendió». Carpeta (por modo):
«Completada» / «Pendiente».

---

## Detalle por modo

### 🪞 BOF Frente a Espejo · 🤳 BOF Selfie
1. Paso 3: elige **«10 s · Omni»** u **«8 s · GenAI Pro (Veo)»** en el
   selector (ojo: aunque diga GenAI Pro, el clip habla → hazlo en **Flow** a
   8 s). El selector cambia la longitud de los guiones.
2. **«✍️ Escribir guiones (x/N)»** → la app escribe un guion por prenda
   (cola, ~1 min). Aparece en cada tarjeta **«✍️ Copiar guion · N car»**
   (🔁 = rehacer ese, no lo uses sin motivo).
3. **«1 · Imagen (Flow)»** → Flow, imagen, Nano Banana 2, 9:16, adjunta
   **solo la foto de la prenda**, pega. Revisa → `imagen_1.png`.
4. Tarjeta → **«✍️ Copiar guion»** → Flow, vídeo Omni, **FRAME INICIAL** =
   `imagen_1.png`, 9:16, 10 s u 8 s. Revisa (habla español de España, dice el
   guion entero, no se corta) → descarga 1080p → `clip_1.mp4`.
5. **Selfie**: el guion del curso **promete pago a plazos**. Úsalo solo con
   prendas que los tengan (la tarjeta dice «💳 Con pago a plazos»); si no,
   **borra esa frase** del guion antes de pegarlo en Flow.
6. Solo si el operador lo pide, **«2 · Guion con plazos 💳»**: es un encargo
   para ChatGPT (con la foto de la ficha) que devuelve el guion con la frase
   de la financiación. Solo para prendas con plazos.

### 🚶 Situación Real 1 · ☕ Situación Real 2
1. **«1 · Imagen (Flow)»** → imagen con la foto de la prenda → `imagen_1.png`.
2. **«2 · Guion (Flow)»** → es un **diálogo cerrado**, el mismo para todas
   las prendas: se pega tal cual en Flow, vídeo Omni, FRAME INICIAL, 10 s.
3. No hay «Escribir guiones» en estos dos modos.
4. «Situación Real 1» sale con la etiqueta **«derivado»**: el texto lo
   adaptamos nosotros del de hombre; revisa con más cuidado que suene natural.

### 🚶‍♀️ Calle Dividido 15s (dos clips)
1. **«✍️ Escribir guiones (x/N)»** → cada tarjeta enseña **«✍️ Guion 1 · N»**
   y **«✍️ Guion 2 · N»**. Si uno sale en rojo con «⚠️», es demasiado largo:
   pulsa 🔁 en esa prenda antes de seguir.
2. **«1 · Imagen»** → Flow, con la foto de la prenda → `imagen_1.png`.
3. **«1b · Imagen 2»** → en el **MISMO chat** de Flow (sin adjuntar nada
   nuevo): la misma chica en otra calle → `imagen_2.png`. Comprueba que es la
   misma persona y la misma prenda.
4. Clip 1: Flow, vídeo Omni, FRAME INICIAL = `imagen_1.png`, **8 s**, pega
   **Guion 1** → `clip_1.mp4`.
5. Clip 2: FRAME INICIAL = `imagen_2.png`, 8 s, pega **Guion 2** → `clip_2.mp4`.
6. Sube «Clip 1» y «Clip 2». La app los pega, pone subtítulos y flecha.

### 🏬 Tienda Colores 15s (dos clips)
Solo prendas con **3 colores o más**: activa el filtro **«🎨 Solo prendas con
3 colores o más»**. (Si los chips no enseñan 🎨, la carpeta se importó antes
del 22/9 y no tiene los colores: avisa.)

1. **«✍️ Escribir guiones (x/N)»** — sin esto **no aparecen** los botones de
   imagen ni de color en las tarjetas. Esto escribe, por prenda, los dos
   prompts de vídeo para Omni con los nombres reales de sus colores.
2. En la tarjeta, **«🎨 N»** → baja las fotos de la prenda en sus otros
   colores → `color_<nombre>.jpg`.
3. **«🖼️ Imagen 1»** (tarjeta) → Flow, imagen, con la foto principal de la
   prenda → la chica en la tienda con la prenda de ese color →
   `imagen_1.png`.
4. En el **MISMO chat**: un botón **«📋 <color>»** por color, adjuntando la foto
   de ese color → una imagen por color (`imagen_color_<nombre>.png`). Revisa
   que es la misma chica y la misma prenda, solo cambia el color.
5. En el mismo chat, **«🖼️ Imagen 2»** → la chica de espaldas →
   `imagen_2.png`.
6. Clip 1: **«🎬 Guion 1 · colores en Omni (fotos como ingredientes)»** →
   Flow, vídeo Omni, **8 s**, 9:16, con **TODAS las imágenes de color como
   INGREDIENTES**, **la del color que lleva puesto, la ÚLTIMA** → `clip_1.mp4`.
   Revisa que la prenda cambia de color cuando la chica nombra cada uno.
7. Clip 2: **«🎬 Guion 2 · en Omni (de espaldas, sentadilla y cierre)»** →
   FRAME INICIAL = `imagen_2.png`, 8 s → `clip_2.mp4`.
8. Sube «Clip 1» y «Clip 2». La app NO toca los colores: pega, subtitula,
   flecha y metadatos.

Los botones **«✍️ Guion 1 / 2»** de estas tarjetas son solo el texto que dice
la chica (para comprobar); lo que se pega en Flow son los **«🎬 … en Omni»**.

#### Tienda Colores con una modelo FIJA (p. ej. «Lucía»)

Si el operador quiere la MISMA chica en todos los vídeos (la aleatoria cambia
entre el clip 1 y el 2), se trabaja así. Salió de una prueba de 4 h
(Carpeta_11, prenda 1, 25/9/2026): sigue el orden y te ahorras los fallos.

**La chica.** Su ficha JSON está guardada en la app (Moda › crear chica) y en
Flow tiene dos referencias: `lucia_cara` y `lucia_cuerpo`. Cara Y cuerpo
(curvas) tienen que coincidir en todo: imagen y vídeo.

**Fotos (Nano Banana 2, gratis: repite hasta que salgan bien).**
1. **Base, en el color que se queda puesto** (el último del guion): la chica
   con la prenda **puesta sobre los hombros, con las mangas, abierta por
   delante**, cogiendo los delanteros. Tiene que VERSE lo que identifica a la
   prenda (cuello, botones, cinturón…). ⚠️ Si la prenda está a medio caer o las
   manos tapan el cuello, Omni no sabe cómo es y en el vídeo la cambia por otra
   (blazer con solapas, parka). Si el cuello sale mal, parte de una foto de la
   chica con la prenda CERRADA y pide solo «desabróchala y ábrela».
2. **Los otros colores**: base + foto de producto de ese color → «Crea otra
   imagen EXACTAMENTE igual… cambiando ÚNICAMENTE el color…». Misma pose en
   todas. Revisa que cada color **se distinga de sus vecinos**: el azul marino
   tiene que verse AZUL y el negro, negro (si no, Omni los funde en uno).
3. **Foto cerrada** (inicio del clip 2): la chica con la prenda abrochada, de
   frente, cuerpo entero.

**Clip 1 · Omni · INGREDIENTES · 8 s · 9:16.**
- Ingredientes en orden: un color por imagen, **en el orden en que se dicen**
  (el que lleva puesto, el último) + **la foto limpia del producto al final**
  como referencia.
- En el prompt, cada imagen con su color («la imagen adjunta 1 es la NEGRA…»,
  «la 5 NO es un plano: es la FOTO DEL PRODUCTO…»), y que diga los colores
  **despacio, con una pausa clara entre cada uno** (cada color ~0,9 s). Si
  va rápido, se come los del medio.
- ❌ **Nada de puntos suspensivos** en lo que dice («Negro… verde…»): la voz
  salió en un idioma inventado. Comas normales.
- ❌ Nada de rótulos tipo «PARTE 1» en el prompt: los escribe en el vídeo.
- Sin fotograma final: solo ingredientes.

**Clip 2 · Omni · FOTOGRAMAS · solo INICIO = la foto cerrada · 8 s.** Sin
fotograma final. Empieza de frente y se gira (no empieza de espaldas: de
espaldas la cara no se reconoce).

**Coste.** Primero **360p (6 pts)**. El operador lo mira; solo con su «ok» se
genera a **720p (12 pts, es OTRA generación)** y se baja en «1080p Resolución
mejorada». Nunca subas a 720p sin su visto bueno.

**Subir.** «Clip 1» + «Clip 2». La app los pega, corta la palabra que Omni
deja a medias tras el guion, subtitula y pone la flecha. No mete fotos fijas:
los colores tienen que venir en el vídeo.

**Flow.** Un proyecto con cientos de generaciones se cuelga: abre uno limpio y
sube solo lo que vas a usar (la base, los colores, la foto cerrada y las fotos
de producto). Un proyecto cada 2 prendas va bien.

**Receta rápida por prenda (probada en 6 prendas, 25/9/2026):**
1. **Base** en el color que se queda puesto: adjunta `LUCIA_ref` (Lucía en la
   tienda, cuerpo entero) + `LUCIA_cara` + foto de producto de ese color, y
   pide «la chica de la 1.ª, con la cara de la 2.ª, en la MISMA tienda y el
   mismo encuadre, con la prenda de la 3.ª EXACTAMENTE igual: <descripción>».
   Vestidos y pantalones: puestos; chaquetas y abrigos: con las mangas y
   abiertos. Pose tipo «acabo de ponérmelo».
2. **Colores**: base + foto de producto de cada color → «EXACTAMENTE igual…
   cambiando ÚNICAMENTE el color». Revisa en una hoja los N colores juntos;
   si un color sale apagado o del tono que no es (el beige tostado, el negro
   gris pizarra), repite solo ese.
3. **Clip 1 · 360p**: ingredientes en el orden del guion + foto de producto.
   Al final del prompt, una línea «MUY IMPORTANTE: la prenda es TODA ella…
   (lo que la define), en todos los colores y planos; nunca…». Sin esa línea,
   un 720p cambió el vestido de flores por uno liso.
4. **Clip 2 · 360p**: fotogramas, solo inicio = la base.
5. **Revisión** (hoja de fotogramas a 2,5 fps + Whisper): colores todos y a su
   palabra, prenda fiel en todos los planos (también primeros planos), misma
   chica, texto dicho entero y SIN repeticiones («y verás, y verás» = otro
   intento), sin texto ni música. Si Whisper duda, transcribe solo ese tramo
   con el modelo `medium`.
6. **720p** (es otra generación: vuelve a revisarlo igual que el 360p) →
   descarga «1080p» → `/subir` + `subir_clip` 1 y 2.

**Lo que se aprendió en la Carpeta_12 (26/9/2026):**
- **Energía.** Sin pedirla, todos los vídeos salen iguales y monótonos. Añade a
  los dos prompts un bloque «ENERGÍA»: creadora con chispa, entusiasmada, voz
  animada, cara expresiva y el cuerpo nunca quieto. En los colores, un gesto
  distinto en cada uno pero SIN moverse del sitio, para que los cortes cuadren
  con la voz. Y cambia las acciones de cada prenda para que no se repitan:
  sentadilla en shorts y monos, andar hacia la cámara, pasarela, sentarse en
  un taburete, recogerse el pelo, vuelta con la falda…
- **Clip 2: fija el color.** Si no, a mitad del clip la prenda cambia a otro de
  los colores. Añade: «lo que lleva puesto es <prenda> en <COLOR> durante TODO
  el vídeo y nunca cambia; los otros colores solo en la percha; la ropa sin
  chapas ni logos».
- **Clip 1: fija también el último color.** Sin esa línea, en los planos de
  detalle volvía a otro color (un halter NEGRO salió crudo al hablar del escote).
  Añade tras el último color: «a partir de aquí y hasta el final (también en los
  planos de detalle) lleva puesto <prenda> en <COLOR>, el de la imagen N; nunca
  vuelve a los otros colores».
- **Clip 2 empieza donde acaba el clip 1.** Si Omni pinta el último color con
  otro tono (p. ej. «verde militar» sale verde y no marrón), haz la foto de
  inicio del clip 2 con ese tono (base + un fotograma del clip 1, «cambia solo
  el color»). Si no, el vídeo pegado cambia de color entre clips.
- **Qué se repite y qué no.** Solo lo visual (prenda o color que cambian, detalle
  que no coincide con el producto, otra chica): eso es sanción. Un tropiezo al
  hablar («al mover, al moverte») se queda. Y si falla un clip, se repite SOLO
  ese.
- **Antes de dar la foto base por buena**, cuenta botones, bolsillos y detalles
  contra la foto del producto (en C11 una chaqueta salió con 6 botones y tenía
  4, y el vídeo no se pudo subir).
- Tras aprobar dos prendas a 360p, el resto de la carpeta va directo a 720p.
- **Prendas estampadas (C13):** Omni ALISA el estampado aunque las fotos de
  color lo tengan (un mono ikat azul salió liso en los cuatro colores) → eso
  es producto incoherente y se repite. Añade a los dos prompts, antes de
  «ENERGÍA», un bloque «ESTAMPADO (lo más importante del vídeo): la prenda NO
  es lisa; lleva en todo momento, en todos los colores y planos, el mismo
  estampado <descríbelo tal cual se ve: rombos, zigzag, flores…> de las
  imágenes adjuntas; solo cambia el color del fondo». Con eso salió bien a la
  primera. Describe el dibujo que se VE en la foto, no el que diga el título.

**Trucos de automatización** (Claude in Chrome): los prompts largos se cargan
en la página con un `<input type=file>` temporal + `file_upload` y se guardan
en `localStorage` (vale para todos los proyectos de Flow); el `fetch` a
`localhost` lo bloquea Chrome. El botón «360p» lleva un icono y no se encuentra
por su texto: haz clic por coordenadas. Con la pestaña oculta o minimizada
Flow va lento (los temporizadores se frenan): evita esperas largas dentro del
JS y usa esperas del navegador. Si una foto subida no aparece en el buscador
de ingredientes, súbela otra vez con otro nombre. Si la ventana se hace
pequeña, «Descargar» pasa al menú «Más opciones» del vídeo.

## API útil (solo lectura)

- `GET /api/v1/nicho-ropa/carpetas?sexo=mujer&modo=<modo>&catalogo=<web|muestras|tareas>`
- `GET /api/v1/nicho-ropa/prendas?carpeta=<slug carpeta>&modo=<modo>` → guiones por prenda (slug de carpeta: `mujer_web__Carpeta 24`).
- `GET /api/v1/nicho-ropa/prompts?carpeta=<slug>&modo=<modo>&duracion=10|8`

Claves de modo: `espejo`, `camara` (Selfie), `calle_1`, `calle_2`,
`calle_dividido`, `tienda_colores`.

## Con el MCP

Con el MCP: `menu="moda_mujer"`, `catalogo="web"|"muestras"|"tareas"`, `modo=` una de las claves de arriba y `duracion="10"|"8"`. `plan_producto` ya trae cada prompt montado para ESA prenda (en Tienda Colores, los de color y los dos de Omni con sus colores).
