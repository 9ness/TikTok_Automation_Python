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

## Prototipo del paraguas (3 oct 2026)

Resultado: `Drive › TIKTOK_SHOP_AI_PRO/Formato_Duelo/paraguas_automatico/duelo_paraguas_v13.mp4`
(45 s). Scripts y prompts: `tools/formato_duelo/` — `flowgen.py`/`genaigen.py`
con el navegador del VPS; `voces.py` y `montaje3.py` dentro del contenedor de la
API, en `/app/temp_work/duelo` (NO en `/tmp`: un despliegue lo borra, y nos
pasó a mitad de render).

### Cómo se hace (la receta que ha salido)

1. **Imagen base en Flow, plano compartido** (los dos en el mismo banco, con
   hueco entre ellos): foto del rival + fotos del producto como ingredientes.
2. **Las caras fuera del plano desde la imagen, no recortando el vídeo**: se
   EDITA la base buena con «el fotógrafo inclinó el móvil hacia abajo: el borde
   de arriba pasa justo bajo la barbilla y abajo queda más suelo»
   (`prompts/p_T1.txt`). Sale natural, a pantalla completa, y el suelo de abajo
   es sitio limpio para subtítulos (68 %), datos (83 %) y flecha.
3. **Cada estado del producto, una edición de esa misma base** (nunca
   regenerar): cerrado TUMBADO en el regazo (`p_T2`), abierto de lado como un
   escudo copiando la postura de otra imagen buena (`p_TD2`, 2 referencias),
   viento (`p_TC` + `p_TC2`).
4. **Clips de 8 s en GenAI Pro (Veo, Frames) con inicio = fin** en esa imagen y
   un «FRAMING LOCK» (cámara fija, las cabezas nunca entran) en el prompt.
5. **Montaje** (`montaje3.py`): recorte del 8 % de arriba (al hablar y reír la
   boca baja hasta el 4 % y la barbilla al 6 %), un clip sigue por donde iba
   entre frases, `clip2` + `corte` para cambiar de estado DENTRO de una frase
   («¡con un botón! — se abre solo» = corte de cerrado a abierto; «abierto mide
   más de un metro — y plegado 38 cm» = al revés), `LIMITE` por clip para no
   usar el tramo donde se deforma, limitador de audio y la flecha del POV.

6. **Variedad**: no repetir el mismo clip del banco en todas las frases. Para
   lo que el plano compartido no puede enseñar sin riesgo (la anilla), un
   INSERTO de ~2 s en primer plano (`p_I_anilla`: colgado de la mochila, como
   la foto del producto) y vuelta al banco (`tramos` en el guion); un primer
   plano del rival (`p_I_rival`) y un tercer reposo (`p_I_risa`).
7. **Zonas seguras de TikTok** (medidas en los virales de referencia): títulos
   centrados al ~10 % (más arriba los tapa el buscador), bandera debajo
   (~17 %), dato al 60 % encima de los subtítulos (68 %); nada por debajo del
   ~78 % (descripción) ni pegado a la derecha (botones). En el cierre, solo la
   flecha: ningún texto de «mira el precio abajo».

8. **Voces** (Fish, `voces.py`): rival «Amigo con Humor», el nuestro «Chico»
   (elegida por ness entre las 16 de hombre: la que suena de España). Delante
   `[excited]` (no se lee) y atempo 1,06; «¿Cuál será mejor?» con las dos a la
   vez. Muestras de todas: `Formato_Duelo/pruebas_voz/voces_hombre/`.

9. **Gancho** (`gancho` en el guion): 1,7 s del momento más visual (el rojo
   dado la vuelta) sin voz, con la pregunta en grande («¿Cuál aguanta esto?»).
10. **Sonido** (`sfx.sh <dir>/media/sfx`, hechos con ffmpeg): calle mojada siempre debajo, lluvia
    solo donde llueve, golpe de viento y «pop» en cada rótulo azul.
11. **Planos de charla «recién ha parado de llover»** (suelo mojado, sin lluvia):
    si llueve y los dos tienen el paraguas cerrado, no tiene sentido.

### Los fallos (y la regla que dejan)

| Fallo | Regla |
|---|---|
| **El paraguas compacto CRECE** (cerrado y en vertical, Veo lo convierte en uno largo hasta el suelo con mango en J, aun con inicio = fin). Es sanción por producto incoherente | Lo pequeño, en una postura donde no pueda «crecer»: tumbado en el regazo y que el prompt no le pida tocarlo («the small closed navy object… NEVER moves»). Revisar 16 fotogramas por clip midiendo el producto contra el muslo |
| Levantarlo por la anilla: +35 % de largo y luego vertical | No pedir que se mueva el producto pequeño; la anilla se ENSEÑA en el regazo y lo dice el rótulo |
| El mango de anilla se ve como gancho en J cuando la mano lo suelta | «His hand GRIPS THE HANDLE THE WHOLE TIME» |
| Recortar la cara en el montaje (11 %, 32 %…) dejaba bocas o perdía los brazos; el difuminado arriba no gustó | Encuadre de cámara inclinada desde la imagen (paso 2). Pedir «crop at nose / neck down» saca cuerpos decapitados |
| Encuadre cerrado: los dos muy cerca | El abierto (los dos enteros) es el que gusta |
| El toldo abierto salía cortado o colgando de la mano al revés | Copiar la postura de otra imagen buena como 2.ª referencia |
| El rojo «dado la vuelta» sujeto por la punta | Decir dónde está la mano y hacia dónde va la vara |
| Pico de audio > 0 dBFS con las dos voces a la vez | `alimiter=limit=0.89` (−0,8 dB) |
| Rótulos cortados | Encoger hasta caber (`encajar`), y subtítulos a dos líneas antes que diminutos |
| La bandera tapaba el mango del rival | Con la cámara inclinada arriba hay cuerpos: títulos lo más arriba y la bandera en el hueco entre los dos |
| 5 clips tirados por cambiar de encuadre después | Decidir el encuadre (y enseñarlo) ANTES de generar clips |
| Títulos al 6 %: debajo del buscador de TikTok; datos al 83 %: debajo de la descripción | Posiciones de los virales de referencia (paso 7) |
| El mismo clip del banco en 5-6 frases | Insertos de primer plano y un reposo más (paso 6) |
| El paraguas del rival «flota»: suelta las manos y se queda de pie solo entre las rodillas. Veo IGNORA «never lets go» | Usar solo el tramo en que lo agarra (`VENTANA` por clip en `montaje3.py`) y generar los clips nuevos con un fotograma de INICIO = FIN sacado de un momento en que ya lo agarra con las dos manos «como un bastón» (`g_f_*.txt`): así sale bien los 8 s |
| «Pulsar el botón y que se abra» (inserto): Veo abría el paraguas por el lado del MANGO, que desaparecía, y la mano acababa cogiendo la tela | Era la IMAGEN: el paraguas estaba cogido al revés (mango arriba). Editada con el mango ABAJO en el puño y la tela hacia arriba (`p_S_boton3`), Veo lo abre entero a la primera sin deformar nada (`k_boton.txt`)… pero ness lo DESCARTÓ: con el muelle de la vara a la vista y la tela saliendo de golpe parece que el paraguas se ha roto. Se publica la v13 (solo el arranque de la apertura). Kling 2.5 con la misma imagen: lento y a medias, peor. Si se reintenta: pedir que la vara no se vea (telescópica, tapada por la tela) y una apertura suave |
| Veo pone algo de lluvia aunque el prompt diga «no rain falling» | Se nota poco con el suelo mojado; quitarla del todo exigiría editar la base y aun así no está garantizado |
| Bandera en una comparativa de TIPOS de producto | Sin bandera: solo si el título compara países («Paraguas español vs coreano») |
| Datos con el mismo naranja que los subtítulos: no se distinguen | Rótulo de dato blanco con brillo azul (el color del producto) en caja azul marino, en el centro de la pantalla |
| Planos «quietos» (mesa, perchero) en GenAI inventan manos u objetos; start ≠ end frame saca una segunda mano | Plano compartido con gente moviéndose; inicio = fin |

**GenAI Pro vs Kling 2.5 (Magnific)** en «se abre solo» con la mano: los dos
deforman el mango al abrirse; Kling es más lento (~10 min, uno a la vez) y más
tosco. Por eso la apertura no se genera: es un corte.

**Coste del prototipo entero**: ~28 créditos de GenAI (14 en esta última vuelta:
5 tirados por el encuadre, 3 con el compacto creciendo, 6 buenos) y ~30
imágenes de Flow. Uno nuevo con esta receta: 3-4 imágenes y 6-7 clips.

**Pendiente si se sigue**: dura 45 s y las referencias 75-85 s (más rondas =
más clips); convertirlo en formato de la app (guion por IA desde la ficha +
`montaje3.py` como pipeline).
