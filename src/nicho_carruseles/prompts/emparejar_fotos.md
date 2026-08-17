Repartes fotos entre los productos de un catálogo de TikTok Shop.

Te paso dos listas:

- `fotos`: cada una con su número y una descripción de QUÉ PRODUCTO sale en ella.
- `catalogo`: los productos que están esperando foto, con su identificador y su título real de la tienda.

Cada foto se generó a partir de la foto de UNO de esos productos. Dime de cuál es cada una.

Reglas:

- Un producto no puede llevarse dos fotos: reparte.
- Puede haber productos MUY parecidos (varias cremas, varios colchones). Fíjate en los detalles concretos —marca, color, formato del envase, número de unidades—, no en el tipo genérico.
- MUY IMPORTANTE: puede que el producto de una foto NO esté en el catálogo. No es una lista donde haya que elegir por fuerza. Si no es NINGUNO de los de arriba —aunque se le parezca en tipo o en estilo—, deja su producto en `""`. Una foto mal asignada acaba publicada en el carrusel de otro producto; decir que no está no cuesta nada.
- El identificador que devuelvas tiene que ser EXACTAMENTE uno de los del catálogo, copiado tal cual.

Responde SOLO con un objeto JSON, sin explicaciones ni ```:

{"fotos": [{"n": 1, "id": "<identificador del catálogo o vacío>", "por_que": "6 palabras"}, ...]}
