Te paso varias fotos de UNA MISMA prenda de ropa de una tienda online. La PRIMERA foto es la principal (el color que lleva la modelo o el que se ve primero). Las demás son esa misma prenda en sus otros colores.

Tu tarea: decir en qué colores se vende, mirando SOLO las fotos.

Reglas:
- Un nombre por color, en español, corto y como lo pondría una tienda de ropa española. Usa SIEMPRE el más cercano de esta paleta (la voz los tiene que decir y tienen que sonar a lo que se ve): negro, blanco, crudo, beige, camel, marrón, chocolate, gris, gris claro, azul marino, azul, azul claro, turquesa, verde militar, verde oliva, verde menta, verde, mostaza, amarillo, naranja, teja, rojo, burdeos, rosa, rosa claro, fucsia, lila, morado. Solo si ninguno se parece usa otro nombre corto y corriente.
- Si dos fotos son del MISMO color (por ejemplo, la misma prenda de frente y de espaldas), ese color va UNA sola vez.
- Si la prenda es estampada, de cuadros, de rayas o jaspeada, nombra SOLO el color que domina (el del fondo o el que más se ve): «azul», no «cuadros azules» ni «azul estampado». Nada de tejido ni dibujo en el nombre (ni tweed, ni jaspeado, ni floral).
- No inventes colores que no estén en las fotos, y no copies ningún ejemplo: cada nombre tiene que salir de una foto.
- Si dos colores se parecen mucho pero son distintos (negro y azul marino, blanco y crudo), usa nombres que los distingan.

Devuelve SOLO este JSON:
{"colores": ["<color 1>", "<color 2>", "..."], "puesto": "<el color de la PRIMERA foto, escrito igual que en la lista>", "hex": {"<color 1>": "#rrggbb", "...": "#rrggbb"}}

`hex` es el color medio de la prenda en su foto (no el fondo).
