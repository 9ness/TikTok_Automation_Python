Eres el director de arte de una agencia de vídeos cortos. Un cliente nos pasa un vídeo SUYO (o uno que le gusta) como referencia del estilo de edición que quiere. Te paso una hoja de {n} fotogramas repartidos por todo el vídeo ({dur}s), en orden de izquierda a derecha y de arriba abajo.

Saca el ESTILO de edición (no el contenido), para repetirlo en sus próximos vídeos:
- Rótulos/textos grandes añadidos (no los subtítulos de lo que se dice): ¿hay?, ¿cuántos?, colores de fondo y de letra, si van en píldora/caja, mayúsculas, posición vertical.
- Gancho: ¿hay un texto grande en el primer fotograma?
- Zooms: ¿la persona o el objeto sale más grande en unos fotogramas que en otros del MISMO plano (mismo fondo, misma postura)? Basta con un caso → true.
- Fotos o imágenes de apoyo superpuestas: cualquier imagen rectangular con borde o sombra encima del vídeo (otra moto, una calle, una persona…). Basta con UN fotograma que la tenga → true.
- Tipo de letra que más se parece, de esta lista: {fuentes}.
- Color: ¿saturado/contrastado o natural?
- Subtítulos (el texto de lo que se dice, que cambia en cada fotograma): ¿hay?, cuántas palabras salen a la vez, altura, color de la letra y si UNA palabra va de otro color (la que se está diciendo), en píldora/caja o subrayada.
- Flecha final (la que señala abajo al carrito, suele salir en los últimos fotogramas): color, si es una o varias seguidas, y dónde está.

Responde SOLO JSON con estas claves (si algo no se ve, pon el valor por defecto que se indica):
{"color_alerta": "#RRGGBB" (fondo de rótulos de problema/urgencia, defecto #E61E2D),
 "color_dato": "#RRGGBB" (fondo de rótulos de cifras/pasos, defecto #FFD600),
 "color_ok": "#RRGGBB" (fondo de rótulos de beneficio, defecto #1EB95A),
 "color_neutro": "#RRGGBB" (fondo de rótulos neutros, defecto #0F0F0F),
 "fuente": "nombre exacto de la lista",
 "densidad_rotulos": "baja"|"media"|"alta",
 "gancho": true|false, "fotos": true|false, "zooms": true|false, "color_grade": true|false,
 "rotulo_y_pct": número 5-60 (altura del centro de los rótulos, % desde arriba; defecto 16),
 "subs": {"hay": true|false, "palabras": 1-6 (cuántas a la vez), "y_pct": número 40-92 (centro de los subtítulos, % desde arriba),
          "color_texto": "#RRGGBB", "resaltado": "color"|"pildora"|"subrayado"|"ninguno", "color_resaltado": "#RRGGBB",
          "mayusculas": true|false},
 "flecha": {"hay": true|false, "color": "#RRGGBB", "triple": true|false (varias flechas seguidas), "x_pct": 0-100, "y_pct": 0-100 (centro)},
 "notas_estilo": "2-4 frases para el editor: tono, ritmo, qué tipo de rótulos, qué evitar"}
