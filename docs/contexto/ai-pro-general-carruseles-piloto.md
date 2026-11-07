# Programa 4 AI Pro — Nicho General UGC, Carruseles y Cuenta Piloto

> Movido literal desde CLAUDE.md (nov 2026) para no cargarlo en cada chat. Se lee solo al tocar este tema.

### Nicho General · UGC (mismo programa, módulo 9)

Módulos en [`src/nicho_general/`](src/nicho_general/) (prefijo Redis
`nicho_general:`). API: `/api/v1/nicho-general/*`. El formato que publicó el
curso para el Q4, y el primero que NO es un vídeo de una sola pieza: el anuncio
son **tres clips** (dolor o gancho → producto y beneficios → urgencia y CTA)
que se generan uno a uno en Flow/Omni y se pegan aquí.

Lo que no tiene ningún otro nicho:

- **Dos ejes, no uno.** El gancho (`GANCHOS`: dolor / general) es como los
  estilos del POV BOF Largo, pero además está la **duración**: 10s en Omni u 8s
  en GenAI Pro (Veo). No es un ajuste de vídeo — en 8 segundos no cabe lo mismo,
  así que el guion se escribe entero para esa duración y el vídeo es otro. Las
  dos cosas van en la clave del documento.
- **Un personaje fijo**, creado aparte desde una foto de Pinterest
  (`prompts/personaje.md`) y reutilizado en todas las escenas: es lo que da la
  continuidad, junto con el escenario y con que la identidad vocal vaya copiada
  palabra por palabra en los tres prompts. El curso PROHÍBE decir "continúa" o
  "misma persona" entre clips.
- **Los clips se suben sin orden.** El operador los adjunta todos de golpe y
  `pipeline/video_editor.py` los ordena transcribiéndolos y casándolos con el
  guion de cada escena; solo se recorta el silencio de ENTRADA de cada uno.

Comparte con el POV BOF catálogo, carpetas, fotos, textos, escaparate y
vendidos. Lo suyo (escenas, clips, vídeo, subido) es por usuario.

### Nicho Carruseles (mismo programa, módulo 14)

Módulos en [`src/nicho_carruseles/`](src/nicho_carruseles/) (prefijo Redis
`nicho_carruseles:`). API: `/api/v1/nicho-carruseles/*`. **No edita vídeo**:
publica un carrusel de DOS fotos con el texto quemado encima (PIL, sin cola —
es un PNG sobre un JPEG).

Lo que no tiene ningún otro nicho:
- **Filtro de categoría.** No todo producto funciona en este formato: hay un
  paso de clasificación con Gemini (texto suelto sobre los títulos YA
  extraídos, sin imágenes) + interruptor manual por producto. Al filtrar, una
  carpeta de diez se queda en dos o tres: el listado de carpetas enseña cuántos
  aptos tiene cada una para no abrirlas en balde.
- **La chica de la casa**: se sube la foto de una chica y Gemini saca su ficha
  JSON (`services/chica_ficha.py`, idea del Nicho Ropa Con Personas). Con ella,
  el prompt para crear la referencia de cada escenario lleva a ESA chica dentro
  — un párrafo no clava a una persona y la referencia es lo que manda en
  imagen-a-imagen.
- **La foto 1 NO depende del producto, solo del SITIO.** Es una chica
  sorprendida generada en Google Flow, y lo único que tiene que encajar es
  dónde está: `generico`, `cama`, `sofa`, `exterior`, `cocina`, `bano`,
  `coche` y `escritorio` — un prompt por escenario
  (`prompts/foto_chica_<escenario>.md`), y la categoría decide cuál le toca.
  Las tandas se suben POR ESCENARIO y para TODOS los catálogos a la vez, y se
  reparten por orden entre los productos que no tienen. La foto 2 —el
  producto— sí es de cada uno y se sube en su tarjeta.
- Las fotos viven en el Drive montado
  (`Nebulabs/TikTok/TikTok Shop/Nicho_Carruseles/<usuario>/`), y el original y la
  versión con texto van en carpetas distintas: quemar sobre lo quemado deja el
  texto doble. El vínculo foto↔producto es el NOMBRE del fichero
  (`<fuente>__<carpeta>__<producto>.jpg`), no un índice en Redis.

Comparte con el POV BOF catálogo, textos, hashtags, escaparate y vendidos
(igual que Creativos Pro). Progreso y "subido" son propios.

### Cuenta Piloto (mismo programa, no es un módulo del curso)

Módulos en [`src/cuenta_piloto/`](src/cuenta_piloto/) (prefijo Redis
`cuenta_piloto:`). API: `/api/v1/cuenta-piloto/*`. Vídeo ORGÁNICO (la imagen no
la genera IA; la voz sí) con la MISMA edición del POV BOF — se reutiliza
`build_video` tal cual.

Tres cosas que no hace ningún otro nicho:
- **El producto nace de una SUBIDA.** Las dos fotos (limpia + ficha) las sube el
  operador; no hay Drive que recorrer ni emparejado que adivinar. Las fotos NO
  pueden ir a `api_uploads/` (se purga a las 24h): van al Drive montado en
  `Nebulabs/TikTok/TikTok Shop/Cuenta_Piloto/<usuario>/`.
- **Es por usuario**: un documento Redis por operador, sin doc compartido.
- **VARIOS vídeos por producto** — `videos` es una LISTA y se añade con
  `product_repo.add_video()` bajo cerrojo. En el resto de nichos hay un solo
  `video_path` y el segundo montaje pisa al primero.

