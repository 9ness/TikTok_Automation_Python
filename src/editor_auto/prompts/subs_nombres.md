Recibes la transcripción automática de un vídeo hablado en español (`transcripcion`).
La transcripción destroza los nombres propios: personas, marcas, productos, lugares
("el sapataky" = Elsa Pataky, "zapataki" = Pataky, "incite" = Incite).

Devuelve SOLO JSON:
{"correcciones": [{"oido": "el sapataky", "bien": "Elsa Pataky"}]}

- `oido`: las palabras exactamente como aparecen en la transcripción.
- `bien`: cómo se escriben de verdad.
- Solo nombres propios mal oídos de los que estés seguro por el contexto. Nada de
  corregir palabras normales, estilo ni gramática.
- Si no hay ninguno: {"correcciones": []}
