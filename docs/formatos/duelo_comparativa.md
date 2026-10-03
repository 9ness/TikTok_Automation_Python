# Formato «Duelo» (comparativa «el mío vs el tuyo») — análisis y cómo replicarlo con IA

> 3 vídeos de referencia (grabados, sin IA) en
> `Drive › NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/_clases/referencias/comparativas/`
> (auriculares ×2, paraguas). Analizados el 3 oct 2026 (Whisper + fotogramas).

## La plantilla (los tres la siguen al pie de la letra)

| Tramo | Qué pasa | Ejemplo literal |
|---|---|---|
| Rótulo fijo arriba todo el vídeo | `A VS B` con bandera de cada uno (🇪🇸 lo de siempre / 🇰🇷🇯🇵🇨🇳 lo «asiático moderno») | «Auricular Popular España VS Auricular Popular Asiático» |
| Gancho 0-5 s | Las DOS frases de presentación + la pregunta | «Yo utilizo el auricular que se compran todos los españoles. — Yo los que usan coreanos y japoneses. ¿Cuál será mejor?» |
| 3-5 rondas | El rival saca una ventaja; el nuestro la supera con un DATO y lo ENSEÑA | «Los míos 25 h de batería. — Los míos más de 72 h» · «se te caen — no se caen» · paraguas: abrir manual / botón |
| Demostración estrella | Una prueba en vivo con callout en pantalla | traducción china en directo («Traductor de 150 idiomas» + onda de audio) |
| Giro del precio | El rival da por hecho que el nuestro es carísimo | «Si los míos cuestan 300 €, ¿cuánto los tuyos? — Menos de 15 € y envío gratis» |
| CTA de escasez | Flecha roja ↓ al carrito, (paraguas) rejilla de colores | «Si no te sale el cartelito abajo es que se han agotado» |

- **75-85 s** (largo: TikTok lo premia), plano FIJO de móvil, sin música.
- **El truco del clon**: es la MISMA persona grabada dos veces y puesta en pantalla
  partida (vertical en el de auriculares, dos en un banco en el del paraguas, tres
  en el gancho del primero). Una sola voz para los dos, y por eso es gracioso.
- Callouts mínimos: «+70 horas», «Traductor de 150 idiomas», una foto insertada.
- Lo que vende: la COMPARACIÓN con lo que el espectador ya tiene, demostrada,
  y el contraste de precio al final.

## Cómo replicarlo con IA (de más barato a más fiel)

### A · «Duelo sin caras» (lo recomendado para empezar)
Pantalla partida con **manos y producto** (POV), sin nadie hablando a cámara:
- Lado rival: el producto genérico «de siempre» (sin marca). Puede ser UNA imagen
  animada en el editor (zoom suave) → coste 0. Reutilizable entre vídeos.
- Lado nuestro: 4-5 clips MUDOS de 5-8 s (GenAI Pro / Magnific) enseñando cada
  ventaja (la mano solo señala; el producto en uso sin manipularlo).
- Voz: Fish, un diálogo a dos voces (o la misma, como el clon). Gratis.
- Rótulo VS + banderas, callouts de cada dato, precio y flecha CTA: editor.
- Sin sincronía de labios → nada de «IA cutre» en caras.

### B · «Clon con cara» (lo más parecido al original)
Una persona IA fija (Flow, como la «chica de la casa»), duplicada en pantalla
partida y hablando:
- Imagen de la persona sosteniendo cada producto (Flow con la foto del producto).
- Habla con sincronía de labios: OmniHuman 1.5 (~0,16 $/s → ~8 $ por vídeo de
  50 s), Kling lip-sync (~0,07-0,10 $/s → ~4-5 $) o créditos gratis diarios de
  Dreamina (OmniHuman) para probar. Kling se desincroniza pasados ~8 s: hay que
  trocear por frases.
- Riesgo: el producto en la mano se deforma al animar la cara/cuerpo; HeyGen/
  Arcads (110 $/mes por 10 vídeos) son mejores pero caros.

### C · Híbrido (equilibrio calidad/precio)
Cara con sincronía SOLO en el gancho y en el giro del precio (~10-15 s →
~1,5-2,5 $) y el resto como A (manos + producto + voz). Es como editaría un
creador real: cara cuando habla, recortes al producto cuando demuestra.

## Decisiones de ness (3 oct 2026)
- **Ni precio ni número de ventas** en la voz ni en pantalla. En su lugar, «el
  precio no te lo digo, míralo tú mismo abajo» con un rótulo «MIRA EL PRECIO
  ABAJO».
- **Cierre de Venta Inversa** (`nicho_pov_bof_largo.config.CTAS_INVERSA`): «Te lo
  voy a intentar dejar en el carrito naranja con tus cupones, pero no puedo
  asegurarte que siga disponible cuando veas el vídeo.» + flecha al carrito.
- **Subtítulos «pop-up» de 3 palabras**, como el POV BOF, con los tiempos de
  Whisper.
- Hacen falta **más fotos del producto** (galería, vídeo del vendedor, reseñas)
  para enseñar cada gesto sin que la IA lo invente. Carpeta por producto:
  `Drive › TIKTOK_SHOP_AI_PRO/Formato_Duelo/<producto>/fotos/`. TikTok pone
  captcha a la ficha desde el VPS: las saca el operador del móvil.
- Borrador (animatic) gratis antes de gastar créditos: `_clases/referencias/
  comparativas/borradores/` (v2 = sin precio, CTA inversa, subtítulos pop-up).

## Lo que NO se copia (sanción o mentira)
- **Marcas del rival** («AirPods», «HTC»): «el que usa todo el mundo», «el de
  siempre».
- **Precio del rival inventado** (300 €): o un dato real de la categoría o nada.
- **Escasez falsa** («si no sale el cartelito se han agotado»): CTA honesto al
  carrito naranja.
- **Datos que no estén en la ficha** (72 h, 150 idiomas…): solo los suyos.
- Niños nunca; etiqueta de contenido IA siempre.

## Qué hace falta construir (si se aprueba)
1. Guion con la plantilla (generador nuestro, mismas reglas que el Largo).
2. Montaje «duelo»: pantalla partida + rótulo VS con banderas + callouts por
   ronda + giro de precio + flecha CTA, con la voz de Fish marcando los cortes.
3. (Solo B/C) paso de sincronía de labios.

## Prototipo del paraguas (3 oct 2026) — lo que ha funcionado

Resultado: `Drive › TIKTOK_SHOP_AI_PRO/Formato_Duelo/paraguas_automatico/duelo_paraguas_v6_banco.mp4`.
Scripts y prompts: `tools/formato_duelo/` (se ejecutan dentro del contenedor de
la API: Fish + Whisper + PIL; los de generación, con el navegador del VPS).

- **UN plano compartido** (los dos «clones» en el mismo banco, cámara fija) y
  no pantalla partida: es lo que hace la referencia. Imagen base en Flow con la
  foto del rival y las del producto como ingredientes; corregir detalles
  (color del mango) EDITANDO la imagen buena («cambia solo…»), no regenerando.
- **Sin caras**: se genera cortado a la barbilla y el montaje recorta un 11 %
  por arriba → no hay bocas que sincronizar. Pedir «desde el cuello» en el
  prompt sacó cuerpos decapitados con la calle detrás: NO.
- **Todo vídeo, los dos lados moviéndose siempre** (el operador: fotos con
  zoom = «poco movimiento» para TikTok). 5 clips de GenAI Pro desde la misma
  imagen: reposo charlando, rival abriendo a mano, el nuestro abriéndose solo,
  viento (desde una variante editada con los dos abiertos) y «enseñar lo
  corto». Un clip sigue por donde iba entre frases.
- Textos como la referencia: títulos en cursiva blanca con sombra ENCIMA del
  vídeo («Paraguas Tradicional 🇪🇸 VS Paraguas Automático»; sin bandera
  asiática: el producto no es de allí), datos en cursiva con borde naranja,
  subtítulos pop-up de 3 palabras al 68 % (como el Largo): blanco/negro el
  rival, blanco/naranja el nuestro, amarillo cuando hablan los dos.
- Voces: Fish con `[excited]` delante (no se lee; sube tono y ritmo) + atempo
  1,06; la frase «¿Cuál será mejor?» con las dos voces mezcladas.

**GenAI Pro vs Kling 2.5 (Magnific)** en «se abre solo» desde POV con la mano:
los dos fallan igual (el mango cambia de forma al abrirse; GenAI además sacó
una segunda mano con start+end frame). Kling es más lento (~10 min y uno a
la vez en ilimitado) y más tosco. En el plano compartido del banco GenAI lo
hizo bien a la primera. Planos «quietos» (mesa, perchero) en GenAI inventan
manos u objetos: evitarlos. Coste del prototipo: ~14 créditos GenAI y ~20
imágenes de Flow.
