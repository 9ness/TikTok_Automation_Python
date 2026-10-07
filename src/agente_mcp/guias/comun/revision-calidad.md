# Revisión de fotos y clips antes de subirlos

TikTok Shop revisa los vídeos con una máquina. Si no le queda claro que el
vídeo enseña **exactamente** el producto enlazado, sanciona por «promoción de
productos incoherente» (8 puntos de la cuenta, visibilidad reducida y el
producto retirado del vídeo). Ya ha pasado: un clip de un **inflador** de
ruedas publicado con el enlace de un **ventilador** de mano de la misma
carcasa blanca.

(Si aun así llega una sanción y el vídeo está bien, se apela: método y
casos aprobados en `APELACIONES.md`, en la raíz del repo.)

Por eso **cada imagen y cada clip se revisan contra la foto limpia y la ficha
del producto** (las dos se ven en la app al pulsar la miniatura de la
tarjeta). Si algo falla: **rechazar**, moverlo a `RECHAZADAS/` con el motivo y
repetir (hasta el máximo que acordaste con el operador).

> **Lo que más importa son las IMÁGENES** (Néstor, 7/10/2026): si las 2-3
> imágenes de un vídeo enseñan el producto IGUAL que la foto real y entre sí,
> los clips salen bien casi solos. Antes de lanzar un solo clip, ponlas lado a
> lado con la foto limpia y no sigas hasta que no haya ninguna diferencia en
> el producto. En electrónica, pantallas apagadas y nada encendido.

## Imagen generada — rechazar si…

**El producto**
- [ ] No es el MISMO producto: otra forma, otro color, otra variante, otro
      tamaño relativo, piezas o accesorios de menos o de más (manguera,
      boquilla, tapa, cable, estuche…).
- [ ] El logo, la marca o la etiqueta cambian, desaparecen o salen
      deformados.
- [ ] Falta un **detalle pequeño de la ficha** que en otra escena sí sale
      (los botones táctiles de un espejo LED, un logo, un piloto): las dos
      imágenes de un mismo vídeo tienen que enseñar el producto igual. Suele
      pasar cuando se ve muy de lado; pídelo de frente.
- [ ] La **letra pequeña del envase está inventada** o mal escrita (pasa
      mucho: «FOIL'N CHEESY» en vez de «FOUR CHEESY»). Para TikTok eso es
      «alterar el aspecto del producto».
- [ ] Sale **más de un producto distinto**, o el producto aparece partido,
      tapado o fuera de plano.
- [ ] En ropa: la prenda no conserva **diseño, color, estampado, corte y
      largo** de la foto; o sale otra prenda (falda en vez de pantalón corto).

**La escena**
- [ ] Manos o dedos raros (seis dedos, fundidos con el producto), caras
      deformadas, cuerpos imposibles.
- [ ] Texto, precios, pegatinas de oferta, marcas de agua o logos que no
      están en el producto.
- [ ] No es vertical 9:16 (3:4 en Creativos Pro).
- [ ] **Sale un niño o un bebé** (aunque sea al fondo, de espaldas o en una
      foto realista de la pared): rechazar SIEMPRE, también en productos
      infantiles. TikTok lo sanciona fuerte; la escena infantil va sin
      personas.
- [ ] Persona que parece **menor de edad**, desnudez o poses sexualizadas
      (bikinis y lencería: solo si el prompt del curso lo contempla, y sin
      poses provocativas).
- [ ] En los formatos de dos imágenes: **no es la misma persona** o el
      producto cambia entre la imagen 1 y la 2.

## Clip generado — rechazar si…

- [ ] El producto **se transforma** durante el clip (cambia de forma, de
      color, le salen o desaparecen piezas, el texto del envase baila).
- [ ] El producto hace algo que **no hace de verdad** o que la ficha no dice
      (un ventilador que echa vapor, una crema que borra una cicatriz).
- [ ] Manos o cuerpos que se deforman, objetos que atraviesan otros.
- [ ] **El producto se mueve solo** (gira, se desplaza, se cae, flota) o la
      mano lo **coge, lo empuja o lo gira**. Motivo de rechazo más frecuente
      en los clips mudos de Kling; casi siempre en el último segundo.
- [ ] **Aparecen o desaparecen objetos** de la escena (un teclado y una
      alfombrilla que no estaban, herramientas nuevas). Un monitor del
      fondo que cambia de imagen vale; pero si el PRODUCTO tiene pantalla y
      el generador se la enciende con iconos o menús inventados, rechazar
      (vídeo del mini móvil sancionado, apelación rechazada).
- [ ] En la escena hay **otro objeto de la misma categoría** que el producto
      (otro móvil, otra botella, otra crema): rechazar la imagen.
- [ ] **Al producto le salen detalles que no tenía**: puertos USB, luces
      LED, botones, costuras, tapas. Pasó con un powerbank: en la imagen
      no se veía el canto y a mitad de clip Kling le «dibujó» el puerto y
      los LEDs. El operador lo vio en el móvil; en miniaturas de 120 px no
      se veía.
- [ ] Cómo revisarlo: una tira de ~10 fotogramas para el movimiento Y,
      además, el **primer, el del medio y el último fotograma GRANDES**
      (≥330 px de ancho, o recortados sobre el producto) para comparar el
      producto pieza a pieza. Si el canto o la base no se ven en la imagen
      de partida, mira ahí con más cuidado: es donde el generador inventa.
- [ ] **Clips hablados** (Moda, UGC):
      - la voz no es español de España (o el idioma que pedía el prompt),
      - se come palabras o se corta a media frase al final,
      - no dice el texto del guion (cambia el precio, promete otra cosa),
      - labios que no casan con la voz,
      - se oyen dos voces o música que no se pidió.
- [ ] El generador ha quemado **subtítulos o texto** en el vídeo (la app pone
      los suyos).
- [ ] No es vertical, dura menos de lo pedido o tiene cortes/saltos raros.

## Antes de dar un vídeo por bueno (montado por la app)

- [ ] Míralo entero con «▶ Ver vídeo». Los subtítulos dicen lo que dice la voz.
- [ ] El **enlace de la ficha** (chip «URL» de la tarjeta) es de ESE producto
      y de ESA variante: el color o la talla del vídeo tienen que ser los de la
      ficha enlazada.
- [ ] No hay en pantalla ni en la voz ofertas que la ficha no tenga
      («cupón», «envío gratis», «a plazos»). Si la tarjeta dice «Sin plazos»,
      el vídeo no puede prometerlos.
- [ ] Si la tarjeta muestra **«⚠️ El caption dice…»**, no se publica sin que
      lo vea el operador.

## Qué anotar

Por cada rechazo, una línea en `informe.md`: producto · qué (imagen 1 /
clip 2) · motivo corto · intento n. Si un mismo producto falla dos veces por
lo mismo (siempre inventa el texto del envase, siempre cambia la pieza),
**no insistas**: apártalo y díselo al operador — puede ser que la foto limpia
no sirva.

- **Realismo de la imagen**: rechaza la que parezca un **recorte pegado** o una
  foto de catálogo (producto plano, sin sombra propia, sin relieve ni
  profundidad, con la misma disposición que la foto de referencia). Pasa sobre
  todo con kits de muchas piezas colocadas en fila (lo advirtió el operador con
  el kit de uñas, sep 2026): pide en la pista «fotografía real con relieve,
  cada pieza con su sombra, ángulo de 45°, colocadas de forma natural, no vista
  cenital ni collage».
- **Imágenes con dos vistas del mismo producto** (dos chalecos, dos estuches…):
  el generador copia las dos vistas de la foto limpia. Pide «UN SOLO …, ningún
  otro» y rechaza si sale duplicado; y rechaza **texto inventado** sobre el
  producto (rótulos en la mochila o en la bolsa) que no esté en la foto.

- **Vídeo demasiado estático** (hipótesis, no confirmada; el detector es
  inconsistente): TikTok sancionó (-4) «contenido estático / slideshow» un
  vídeo con el clip casi como una foto (cámara fija, producto quieto, solo
  un dedo que se mueve). Rechaza el clip sin movimiento de cámara ni de mano
  y pide en la pista «la cámara se mueve suavemente / se acerca despacio, la
  mano se mueve con naturalidad». Ver `APELACIONES.md`.
