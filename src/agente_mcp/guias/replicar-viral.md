# Replicar viral — guía para agentes

> Viene de la clase del 30 sep 2026 (`docs/clases/2026-09-30_clase_miercoles.md`):
> copiar vídeos que YA venden en TikTok Shop, con un producto nuestro.
> Código: `src/replicar_viral/`, API `/api/v1/replicar-viral/*`, MCP `replicar_viral`.

## La idea

No se copia el vídeo: se copia **su fórmula** (gancho, ritmo, demostración) en
nuestro formato de siempre: **dos clips MUDOS de 8 s** (GenAI Pro o Magnific;
nada de Omni con voz) y **una voz en off de ~16 s** locutada con Fish y montada
con el editor del POV BOF Largo.

## 1. De dónde salen los vídeos

El operador busca en **Social1** (la web bloquea el navegador del VPS, así que
lo hace él desde el móvil) y te pasa los enlaces de TikTok. Filtros que usa:
país ES o US, *Top Converters* / *Biggest Hits*, embudo › *AI Content*. Valen
los vídeos **sin nadie hablando a cámara**: manos con el producto, el producto
en su sitio, antes y después, voz en off o solo música.

Antes de replicar, comprueba con él:
- que el vídeo **sigue teniendo carrito naranja** (si no lo tiene, al creador le
  han sancionado: no se copia);
- **qué producto NUESTRO** va con ese vídeo. No hace falta que sea el mismo, pero
  sí del mismo estilo (un organizador por otro organizador). Lo que salga en los
  clips tiene que ser NUESTRO producto: es lo que mira TikTok para sancionar por
  «producto incoherente». Búscalo con `productos` en el catálogo del POV BOF.

## 2. Analizar y adaptar

`replicar_viral(catalogo, carpeta, producto, url=<enlace TikTok>)`, o con
`archivo_id` si el vídeo lo has subido tú (`/subir`). Tarda ~1 min y gasta
una llamada de Gemini Flash (céntimos). Devuelve:

- `original`: transcripción, escenas con segundos, gancho y por qué funciona.
- `apto`: `false` si no se puede hacer bien en nuestro formato (tutoriales,
  alguien contando algo a cámara, producto sin relación). Si sale `false`,
  díselo al operador y no sigas sin su «sí».
- `adaptacion`: `guion` (voz en off, 250-290 caracteres), `texto_gancho`,
  `caption` y, para `clip1` y `clip2`: la parte del guion que cubre (`voz`),
  `prompt_imagen` (imagen inicial) y `prompt_video` (cómo se anima en 8 s).

Si el guion se queda corto o largo (`guion_caracteres` fuera de 250-290), dilo:
el montaje lo cuadra con el cierre, pero mucho fuera de rango se nota.

## 3. Generar (en la WEB, nunca por API)

Como en el resto de menús (`comun/plataformas.md`):
1. Imagen inicial de cada clip en **Google Flow (Nano Banana)** con la foto
   limpia del producto como referencia y el `prompt_imagen`.
2. Revisa la imagen con `comun/revision-calidad.md`: producto idéntico, tamaño
   real, nada flotando, nada de texto ni pantallas con números.
3. Clip de 8 s en **GenAI Pro** (o **Magnific** de respaldo) con esa imagen y el
   `prompt_video`. Mudo.

## 4. Montar (POV BOF Largo, estilo «Réplica viral»)

El Largo tiene un estilo `viral` y una carpeta especial **«Réplicas virales»**
en el Inventario General (modo fijo `viral`):
1. `anadir_replica(producto="<catálogo>|<carpeta>|<producto>", replica_id=<id>)`
   (o `POST /api/v1/nicho-pov-bof-largo/replica/anadir`): copia el producto a
   «Réplicas virales» con fotos y textos, guarda `replica_id` y escribe el guion
   (el de la réplica, sin llamar a la IA; el cierre del carrito naranja se
   cuadra solo). Devuelve en qué `producto` de esa carpeta ha quedado.
2. Sube los dos clips con `subir_clip(menu="pov_bof_largo",
   catalogo="inventario_general", carpeta="Réplicas virales", producto=…)`,
   como en cualquier vídeo del Largo: Fish locuta y se monta solo.
3. Sale en **Mis tandas** del operador con el color de «Réplica viral».

(Si `anadir_replica` aún no existe en tu MCP, es que el Largo no lo ha
desplegado: deja los clips en la bandeja y avisa.)

## Reglas

- Una réplica por vídeo y producto: no lances varias del mismo par «por si acaso».
- Nunca copies la cara, la voz ni el texto literal del creador original.
- No prometas en el guion nada que no diga la ficha (precio, envío, plazos).
