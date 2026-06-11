# LECCIONES APRENDIDAS DEL MOTOR DE EDICIÓN

> **Cómo funciona este archivo (para humanos — este preámbulo NO se envía a la IA):**
> Cada sección `##` lleva etiquetas `[pasada1|pasada2]` que indican a qué
> pasadas de IA se inyecta: `clean_script` (holístico), `analyst` (pass1),
> `false_starts` (pass2), `completeness` (revisión de finales). Una sección
> sin etiquetas se envía a TODAS. Solo se envían las secciones relevantes a
> cada pasada, con un CAP duro (~6000 chars/pasada) — si se supera, el motor
> avisa por log: toca CONSOLIDAR (fusionar lecciones parecidas en una regla
> general), no seguir añadiendo. Las lecciones deben ser cortas, generales y
> accionables. Detalle técnico del fallo → `learnings.md`, no aquí.

## Tartamudeos y repeticiones [clean_script|false_starts]

- Al eliminar una repetición ("muy muy muy" → "muy"), el corte debe cubrir
  SOLO las copias repetidas. NUNCA te lleves la palabra funcional anterior:
  en "la cintura es muy muy muy elástica", elimina "muy muy" y conserva el
  "es" — si cortas "es muy muy" queda "la cintura muy elástica" (frase rota).
- De cada frase repetida conserva UNA instancia COMPLETA (normalmente la
  última, que suele ser la versión buena del hablante), nunca trozos de las
  dos mezclados.

## Finales de segmento [clean_script|completeness]

- Un segmento NUNCA puede terminar a mitad de idea. Ejemplo real: terminar en
  "...y están solo por ocho" (precio sin completar) y saltar a otra cosa suena
  roto. Si la continuación de la frase no se conserva, elimina la frase
  incompleta ENTERA — mejor fuera que a medias.
- Un segmento no puede terminar en conjunción, preposición o muletilla
  colgada: "...que", "...y", "...con", "...bueno". Debe terminar en frase
  completa y natural.
- El FINAL del vídeo es el punto más crítico: tiene que cerrar una frase
  completa. Jamás acabar en muletilla ni dejar una idea anunciada sin
  terminar.

## Frases enteras y coherencia [clean_script|false_starts|completeness]

- Conserva frases COMPLETAS. No dejes una palabra de contenido suelta separada
  de su frase, ni conserves un anuncio ("ahora os voy a enseñar...") cuya
  continuación eliminaste.
- En los micro-cortes internos (pausas o tartamudeos de <2 segundos), la frase
  CONTINÚA al otro lado del corte: no trates ese borde como un final de frase
  ni recortes palabras ahí.

## Rectificaciones del hablante [clean_script|false_starts]

- Si el hablante anuncia algo y MÁS TARDE se rectifica con una versión
  corregida de la misma idea — aunque cambie las palabras y no estén
  contiguas — conserva SOLO la versión final y elimina ENTERO el anuncio
  anterior. Ejemplo real: "os los dejo aquí en el cuadrito naranja para que
  lo podáis ver" y después "os voy a dejar por aquí el enlace para que podáis
  ver todos los estampados" → solo la segunda. Dos anuncios de lo mismo
  confunden y alargan el vídeo.

## Contenido de venta [clean_script|completeness]

- No cortes a medias afirmaciones de venta: precios, beneficios, llamadas a la
  acción. O se conserva la afirmación entera o se elimina entera — un precio
  a medias hace perder la venta.
