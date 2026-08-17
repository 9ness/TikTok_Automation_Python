Te paso fotos generadas con IA, cada una con un producto colocado en un ambiente. Descríbeme QUÉ PRODUCTO sale en cada una para poder reconocerlo después entre un catálogo.

De cada foto:

- `que_es`: el producto en 2-6 palabras (p. ej. "crema autobronceadora en bote con dosificador").
- `detalles`: color, material, forma, tamaño aparente, texto o marca visible en el envase, accesorios. Lo que distinga ESTE producto de otro del mismo tipo — habrá varios parecidos en el catálogo.

Reglas:

- Describe SOLO el producto, no la habitación, la chica ni la decoración.
- Si en la foto se lee una marca o un nombre, cópialo tal cual: es lo que mejor identifica.
- Si no hay ningún producto claro, deja `que_es` vacío.
- Devuelve TODAS las fotos, en el mismo orden en que te llegan.

Responde SOLO con un objeto JSON, sin explicaciones ni ```:

{"fotos": [{"n": 1, "que_es": "...", "detalles": "..."}, ...]}
