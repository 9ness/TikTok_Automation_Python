Es una hoja de {n} fotogramas (en orden, izquierda→derecha, arriba→abajo) de un vídeo vertical de {dur}s ya editado para TikTok (cortes de silencios + subtítulos automáticos). Revisa como lo haría un editor antes de entregarlo al cliente. Cada celda lleva su número en amarillo; el gris es el separador.

Busca SOLO fallos visibles: subtítulos cortados por el borde, ilegibles, tapando la cara o fuera de sitio; texto duplicado o superpuesto; fotogramas negros, congelados o corruptos; encuadre roto (cabeza cortada, bandas).

No inventes: si no se ve, no es un fallo. Responde SOLO JSON:
{"entregable": true|false, "fallos": [{"fotograma": N, "tipo": "...", "detalle": "..."}], "nota": "una frase"}
