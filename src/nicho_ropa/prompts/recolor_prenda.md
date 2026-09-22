<!-- Recolorear el primer fotograma del clip 1 del formato "Tienda Colores".
     Se manda a Gemini (modelo de imagen) con el fotograma como imagen de
     entrada, una vez por cada color que NO es el que lleva puesto; los
     resultados se intercalan al montar, al ritmo en que la chica nombra
     cada color.

     `{{COLOR}}` llega YA EN INGLÉS y descrito ("a light sand / cream beige
     colour"): `services/recolor.describir_color` traduce el nombre del guion.
     Medido en la primera prueba real: con el nombre en español y un prompt
     largo de "pixel-identical", «beige» volvía sin imagen (IMAGE_OTHER) dos
     veces seguidas; con esta frase corta y el color en inglés salieron
     todos. Cuanto más parezca una orden de edición y menos un contrato,
     mejor.

     `{{REFERENCIA}}` se rellena cuando el guion leyó el tono de esa variante
     (hex de su miniatura en la captura del selector): el "beige" cambia de
     una prenda a otra. Va como TEXTO: adjuntar la captura como segunda
     imagen hacía que el modelo calcara la barra "Añadir al carrito" dentro
     de la foto, dos veces de dos. Sin tono, queda vacío. -->

Make the trousers (the main garment on her lower body) she is wearing {{COLOR}}. Change nothing else: same pose, same top, same shoes, same face and hair, same background, same lighting and framing, same fabric details (seams, waistband, drawstring, pockets). Photorealistic, no text, no watermark.

{{REFERENCIA}}
