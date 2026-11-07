# Programa 4 AI Pro — Nicho Ropa Sin Personas y Ropa Con Personas

> Movido literal desde CLAUDE.md (nov 2026) para no cargarlo en cada chat. Se lee solo al tocar este tema.

### Nicho Ropa Sin Personas (mismo programa, módulo 8)

Módulos en [`src/nicho_ropa/`](src/nicho_ropa/) (prefijo Redis `nicho_ropa:`).
API: `/api/v1/nicho-ropa/*`. Diferencias con POV BOF:
- La carpeta de fotos se comparte **por enlace**, no está en "Compartido
  conmigo" → se lee con `--drive-root-folder-id`, no con `--drive-shared-with-me`.
- Es UNA sola carpeta con todas las prendas dentro (`NICHO_ROPA_FOLDER_ID`).
- El vídeo **no lleva ningún texto quemado** y sale **mudo** (la música la pone
  el operador al publicar); se le puede añadir voz hombre/mujer si se pide.
- El prompt de vídeo tiene versión CON y SIN manos: se guarda un solo texto y
  la variante sin manos se deriva quitando `config.LINEA_MANOS`.
- Además de las 4 carpetas del curso (planas), acepta las de la web por ZIP:
  cada una es una carpeta MÁS del selector con slug `mujer_web__Carpeta 23`
  (`services/prendas_web.py`), así el resto del nicho no se entera del nivel
  nuevo. Reusa el importador del POV BOF para no duplicar la inversión de
  nombres. Pero **son dos pantallas**, no una: en la web la prenda va PUESTA
  frente al espejo, así que las carpetas del ZIP viven en "Ropa Mujer/Hombre"
  (`/tiktok-shop-ai-pro/nicho-ropa-web`) con su prompt y conservando la voz
  del clip, y "Sin humanos" se queda con las 4 del Drive. Mismo backend y
  mismo Redis: las separa el flag `web` de `/carpetas`, y la pantalla es el
  mismo componente con `variante`.

- **Tienda Colores 15s** (`tienda_colores`, Moda Mujer aleatorios) NO es del
  curso: es la receta de cinco virales de pantalones. Dos clips de 8s (frente
  / espaldas) como calle dividido, y el gancho —la chica nombra 3-4 colores y
  el pantalón cambia en cada uno— lo hace el PROPIO generador: el clip 1 se
  pide en Omni con la imagen 1 en cada color como ingredientes y los cortes
  atados a la voz (`prompts/*_video_omni.md`, medido de cinco virales). El
  montaje solo pega, subtitula, pone la flecha y limpia metadatos. Recolorear
  desde la app (`pipeline/colores.py` + `recolor_video.py`/`recolor.py`) se
  deja apagado (`TIENDA_COLORES_RECOLOR_VIDEO=1` lo recupera). Los nombres de
  las variantes los lee el guion de la **captura del selector de colores**
  subida por prenda (`services/variantes.py`, en `API_TEMP_ROOT/variantes`);
  el guion guarda `colores` (el puesto, el último) y `colores_hex`. La imagen
  1 es la chica con mallas y el pantalón a medio poner, y solo se ofrecen las
  prendas con al menos 3 colores (`minimo_variantes`, de las
  `Producto_N_Color_K` del ZIP).
- Los formatos cuyo guion se escribe FUERA (espejo, selfie, gafas) ya no piden
  pasar por ChatGPT a mano: `services/guionista.py` manda a Gemini el MISMO
  prompt del curso + los textos y fotos de la prenda, y el bloque para el
  generador se **monta aquí** (`_montar_video`) con el movimiento literal —
  pedirle a Gemini que lo copiara lo cortaba por RECITATION. Se guarda por
  prenda **y por modo** (`product_repo.guardar_guion`).

Reutiliza del POV BOF `photo_pairing`, la descarga de fotos por file ID y el
motor de extracción (`text_extractor.extract_from_pairs`) — cambia el prompt.

### Nicho Ropa Con Personas (mismo programa, módulo 7)

Módulos en [`src/nicho_ropa_personas/`](src/nicho_ropa_personas/) (prefijo
Redis `nicho_ropa_personas:`). API: `/api/v1/nicho-ropa-personas/*`. La prenda
va PUESTA por una modelo generada con IA. Usa las MISMAS carpetas de prendas
que el módulo 8 (se importan de `nicho_ropa.config`): la foto vale para los dos
nichos, cambia el prompt.

Paso propio que no tiene ningún otro nicho: **crear la chica**. El operador
sube una foto de internet, Gemini la mete en la plantilla del curso
(`prompts/plantilla_chica.json`) y sale una ficha JSON que se guarda con nombre
y se copia en cada vídeo. Es **por usuario** — la cara es la identidad de la
cuenta. La plantilla ya trae el bloque `clothing`, así que crear a la chica y
vestirla con el producto es UN prompt, no dos.

Audios locutados (5 voces de mujer, se sortea una):
`Nebulabs/TikTok/TikTok Shop/Nicho_Ropa_Personas/audios/mujer/`.

