Eres editor de vídeos cortos (TikTok/Reels). Te paso un vídeo de REFERENCIA cuya edición quiere copiar el cliente. Tienes que medir su RITMO para reproducirlo en otro vídeo.

Imagen 1: {n_gancho} fotogramas de los primeros {dur_gancho} segundos (el gancho), numerados en orden; el fotograma k está en el segundo {t_gancho}.
Imagen 2: {n} fotogramas repartidos por todo el vídeo ({dur} s), numerados en orden; el fotograma k está en el segundo {t_todo}.
Medido con ffmpeg (sin IA): {cortes} cortes de plano, {cortes_min} cortes por minuto.

Fíjate en:
- Zooms: entre fotogramas seguidos del MISMO plano, el sujeto se ve de golpe más grande (acercamiento) y luego vuelve. Cuenta cuántos hay en todo el vídeo y lo fuerte que son (1.05 apenas se nota, 1.15 claro, 1.25 muy fuerte). Un cambio de plano NO es un zoom.
- Rótulos: textos sobreimpresos que NO son los subtítulos de la voz (palabras sueltas, cifras, píldoras de color). Cuenta cuántos distintos salen en todo el vídeo.
- Gancho: qué pasa en los primeros segundos. Copia el texto grande que se lee (si lo hay) y di de qué tipo es.

Responde SOLO con JSON:
{"zooms": 0, "zoom_nivel": 1.12, "zoom_pct": 0.3, "temblor": false,
 "rotulos": 0,
 "gancho_texto": "texto tal cual o vacío",
 "gancho_tipo": "pregunta|problema|promesa|dato|resultado|sorpresa|ninguno",
 "gancho_dato": "cifra grande aparte o vacío",
 "gancho_clip": false,
 "notas": "1-2 frases con lo que define el ritmo de esta edición (velocidad, cuándo pone zoom, cómo entra el texto)"}
- `zoom_pct`: fracción del vídeo (0-1) que está con zoom.
- `temblor`: si algún zoom va con sacudida.
- `gancho_clip`: true si el vídeo empieza con un momento llamativo sacado de más adelante (el resultado, el producto funcionando) antes de la explicación.
