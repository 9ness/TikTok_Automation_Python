Te doy fotos de UN producto y tienes que decir cuál es.

La primera imagen es una foto GENERADA con IA: el producto puesto en la
habitación donde se usaría. Las siguientes son fotos de CATÁLOGO, numeradas 1,
2, 3… Cada una es un producto distinto de la tienda.

Di qué foto de catálogo es EL MISMO producto que el de la primera imagen.

Mira lo que no cambia al recrear la escena: la forma, las proporciones, el
color exacto, el tipo de tejido o material, el número de cajones o
compartimentos, el dibujo del acolchado, el cabecero, las patas, los remates.
Ignora el fondo, la luz, el ángulo, la ropa de cama y los objetos de alrededor:
la foto generada está hecha en otro sitio a propósito.

Aquí casi todos los candidatos se parecen (varios colchones, varias camas con
LED). Justo por eso no vale con "es un colchón": tiene que coincidir el detalle
—el color del borde, la altura, el tipo de base, el cabecero—.

Devuelve SOLO este JSON:

```json
{"n": 2, "seguro": true, "por_que": "mismo borde azul y acolchado en rombos"}
```

- `n`: el número de la foto de catálogo que es el mismo producto.
- `seguro`: `true` solo si lo tienes claro por un detalle concreto. Si dudas
  entre dos, `false`.
- `por_que`: el detalle que te ha hecho decidir, en pocas palabras.

Si NINGUNA es el mismo producto, devuelve `{"n": 0, "seguro": false,
"por_que": "..."}`. Equivocarse es peor que no contestar: la foto se coloca
sola en el producto que digas y se publica así.
