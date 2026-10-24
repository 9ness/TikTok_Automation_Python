# Curso Skool «Crea con Seedance» (Jonny, 18:26) — 24/10/2026

Lección única del módulo «Crea con Seedance» de Skool ([enlace](https://www.skool.com/tiktokshopaipro/classroom/633e4d15?md=9d81158dd4304baaa6b8dfc7994cc15e)), subida el 22/10/2026. Para escribir esto se usaron:

- la transcripción (subtítulos CC de Mux, `transcripcion_cc.txt`; confunde nombres: «Sidance» es Seedance, «CACU/casco» es CapCut y «fix» es Fish);
- fotogramas a 1080p del vídeo;
- los dos prompts literales de la web del curso (`prompts_revelacion_15s.txt`).

La transcripción y los prompts, como los del resto de cursos, solo están en el VPS y no se suben a git.

Los cursos hermanos son [Genjutsu](../2026-10-13_tutorial_genjutsu_higgsfield.md) e [Instagram Shop](../2026-10-23_instagram_shop/README.md).

## Qué es, en una línea

**Formato «Revelación 15 s»** para ropa con varios colores. Un personaje eufórico destapa maniquíes enfundados en plástico y grita solo el color de cada uno. Luego enseña las características y cierra con la CTA del carrito naranja.

Se genera en **una sola toma de 15 s con Seedance 2.0 Fast**, dentro de **CapCut** (Video Studio), sin clips que pegar. **No replica virales**: es un formato plantilla del curso, igual que los de Moda. Para replicar virales, Jonny sigue enseñando Genjutsu.

## Flujo (lo que hace Jonny)

1. **Personaje.**
   - Busca en Pinterest una persona REAL; si la foto es de IA, el resultado sale peor.
   - Le pasa la foto a ChatGPT con el *prompt de imagen*.
   - Con el prompt que devuelve, crea el personaje en Flow: de cuerpo entero, sobre fondo blanco.
2. **Producto.**
   - Elige una prenda de **varios colores** del catálogo (Comunidad › Productos › Ropa Hombre; el equipo mete tiendas con muchos colores: chándal, pantalón de trabajo, chaquetas).
   - Descarga todas las fotos: una por color + la ficha.
3. **Vestirlo.** En Flow, «viste al personaje con la chaqueta y un outfit a juego». Esa imagen es la referencia del vídeo.
4. **Proyecto.**
   - En ChatGPT, *prompt de guion y vídeo* + fotos de colores + ficha.
   - Devuelve el prompt completo, con las escenas «0-6 s revelación» y «6-15 s características y CTA» y la narración exacta.
5. **CapCut.**
   - Entra en capcut.com/ai-creator (Video Studio) › Video › **Seedance 2.0 Fast · 720p · 9:16 · 15 s**.
   - Pega el prompt y sube las imágenes: el personaje vestido + un color por foto, 5 en su ejemplo. El tope es **9 imágenes + 3 vídeos** de referencia.
   - El agente «Director» de CapCut lo convierte en tarjeta y pide confirmar («Sí, crear el vídeo»).
   - Quita la marca de agua y descarga.
6. **Arreglar la voz.** La voz de Seedance falla en la pronunciación («cider»):
   - extrae el audio del vídeo y lo clona en **Fish Audio** (plan de **14 €/mes, 250.000 créditos**; modelo «Fish Audio Drama 3»);
   - le pide a ChatGPT el guion entero en un solo párrafo;
   - lo locuta con esa voz clonada, porque así sale con el MISMO ritmo y cuadra casi sola;
   - en CapCut, en un clip compuesto, **aísla y elimina la voz original para conservar los efectos** (el ruido de los plásticos) y encima pone la de Fish;
   - cuadra las ondas y corta los silencios y la transición antes de cada revelación.
   - El labio descuadra «un pelín» y lo da por bueno.
7. **Acabado.** En CapCut, **filtro 4K a 30 y filtro HD a 30**, exportado a 30 fps.
8. **Voz fija entre vídeos:** el audio bueno se añade como **referencia de audio** en cada proyecto nuevo, y así Seedance mantiene ese tono.
   - A ChatGPT se le pide que devuelva siempre el proyecto + el guion entero aparte, por si hay que rehacer la voz.

## Variantes que propone (el prompt es una plantilla)

- Cambiar el escenario: mercadillo en vez de tienda, o alguien que llega y le pregunta.
- En vez de los colores, contar «1, 2, 3» o «no 1, no 2, no 3…» para packs (p. ej. «3 pantalones por el precio de 1»).
- **Nunca decir el precio.**
- Funciona mucho mejor con prendas **de un solo color entero**. Con colores mezclados en la misma prenda (su chaqueta con contrastes) duda: lee «azul, blanco y rojo» de una sola prenda.
- Por qué Seedance y no Omni: **en Omni el vídeo es de 10 s y no sigue bien este prompt**. Además, 15 s «es contenido de valor» para TikTok.

## Cuánto cuesta (verificado en pantalla y en capcut.com/pricing, 24/10/2026)

| Concepto | Dato |
|---|---|
| Plan de Jonny | CapCut **Ultra**: 7.483 créditos IA/mes; él tiene 7.473. En la web cuesta **68 €/mes**, con «hasta 40 % de descuento» en el mensual (≈ 41 €, lo que él llama «el plan de 40 €»; parece precio de primer mes) |
| Plan Pro | 29,99 €/mes, **650 créditos** (≈ 8 vídeos así): no da para producir |
| 1 vídeo de 15 s, Seedance 2.0 Fast, 720p | CapCut estima **45 créditos**; el contador bajó de **7.473 a 7.398 = 75 créditos** |
| Vídeos/mes con Ultra | Jonny dice «unos 100, 3 al día». A 75 cr salen ≈ 100; a 45 cr, ≈ 165 |
| Coste por vídeo | ≈ **0,40-0,70 €** con el plan Ultra a 41-68 € |
| Voz Fish | Plan de 14 €/mes, que **ya tenemos** (`FISH_API_KEY`, voz clonada de Néstor) |
| Modelos en CapCut | Automático, Seedance 2.5, 2.0 Mini (el barato, «hasta 58 % menos créditos»), 2.0 Fast, 2.0 y Omni |
| Duraciones | 5/10/15 s en el móvil; en la web el Director llega a 30 s, 1 min y 2 min |

**Riesgo visto en el propio tutorial:** la primera generación falló con «la generación se bloqueó por una restricción de derechos vinculada a las referencias de persona/prendas». Tuvo que repetirla, y el personaje cambió. Hay que contar con reintentos.

### ¿Nos sirve? Alternativa sin pagar CapCut

**Higgsfield, que ya pagamos (Ultra, 2.884 créditos el 24/10), trae Seedance:**

- `seedance_2_0` con modo `fast`, 4-15 s, 480p/720p, referencias de imagen, vídeo y **audio**, y audio nativo;
- `seedance_2_0_mini`;
- `seedance_2_5`, hasta 30 s.

Se puede hacer el mismo formato desde su web o el MCP **sin otra suscripción**. El MCP no da el precio en créditos sin lanzar el trabajo: hay que mirarlo en la web de Higgsfield antes de generar el primero. Genjutsu a 480p sale a 3 cr/s, así que un Seedance Fast de 15 s debería salir bastante más barato.

Además, Néstor no usa CapCut, así que el arreglo de la voz lo haría el agente:

- separar la voz de los efectos con un separador de pistas;
- locutar con Fish usando la voz clonada del clip;
- cuadrar con el editor del POV BOF Largo;
- aplicar `ACABADO_4K`.

## Encaje con nuestras cuentas (análisis propio, no del curso)

- **Replicar virales sencillos:** sí sirve, aunque Jonny no lo enseña así. Seedance 2.0 hace 15 s seguidos con hasta 9 imágenes de referencia, mantiene la identidad y da voz con labios. Un viral sencillo (una persona, un sitio, una acción, ≤ 15 s) se replica en UNA toma, sin cortes entre clips de 8-10 s y más barato que Genjutsu.
  - Genjutsu sigue siendo lo mejor cuando lo que importa es copiar la actuación y la cámara exactas de un vídeo real, porque transfiere el movimiento.
  - Seedance sirve cuando basta con recrear la idea y el guion.
- **Ana (ropa):** es justo su caso, prendas con varios colores. Se puede usar con su chica de siempre (la ficha del Nicho Ropa Con Personas), con un maniquí por color y la CTA del carrito.
  - Ojo: Ana está en recuperación tras la sanción por baja calidad. Las fotos de los colores tienen que ser de la MISMA prenda del enlace, y cada color, uno de verdad (regla de «producto consistente»).
  - Encaja con su `tienda_colores` (pantalones), que hoy se hace con Omni en 2 clips.
- **Casca Chollos (nestor2):** el gancho de «destapar» vale para productos con variantes de color (fundas, termos, mochilas). El cascanueces enmascarado no tiene labios, así que la voz va en off con Fish «Chico» y no hay que sincronizar nada, lo que encaja mejor que con un personaje que habla.
  - Para productos sin colores vale la variante «1, 2, 3» con packs.
- **ness:** no, su formato es el POV de siempre.

## Pendiente (decide Néstor)

1. ¿Probamos el formato con Seedance de **Higgsfield** (lo que ya pagamos) en 1 vídeo de Ana, antes de plantear CapCut Ultra?
2. Si funciona: crear el estilo «Revelación» en Moda Mujer · Multimodo, con su MCP y su guía, igual que se hizo con los otros formatos.
