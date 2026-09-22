<!-- Leer los colores de la captura del selector "Color" de TikTok Shop. Se
     manda SOLA (una imagen) en una llamada de texto barata al subir la
     captura. No va con el guion: con tres imágenes (ficha + limpia + esta,
     que trae precios y botones) Gemini bloqueó la petición entera
     (`candidates` vacío) y no salió ningún guion.
     Sin valores hex de ejemplo: con ellos el modelo los copiaba tal cual. -->

Esta es una captura de la ficha de un producto en TikTok Shop, con el selector "Color" (miniaturas y su nombre debajo). Devuelve SOLO un JSON, sin nada más y sin ```:

{"colores": ["<nombre 1>", "<nombre 2>"], "hex": {"<nombre 1>": "#rrggbb", "<nombre 2>": "#rrggbb"}}

Reglas:
- "colores": el nombre EXACTO que pone TikTok debajo de cada miniatura, en minúsculas, completo (si está cortado con "…", escribe lo que se lea y completa solo si es evidente, p. ej. "VERDE MIL…" → "verde militar"). En el orden en que aparecen.
- Salta las variantes tachadas o marcadas como agotadas / sin stock.
- "hex": el color MEDIO de la prenda tal como se ve en la miniatura de cada variante, en hexadecimal, MEDIDO en la imagen (no un valor típico del nombre del color). Si una miniatura no se ve, omítela del diccionario (pero deja el nombre en la lista).
- Si en la captura no hay ningún selector de color, devuelve {"colores": [], "hex": {}}.
- No inventes colores que no estén en la captura.
