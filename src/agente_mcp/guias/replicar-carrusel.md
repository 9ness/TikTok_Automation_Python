# Replicar carrusel — guía para agentes

> Viene de la clase del 7 oct 2026 (`docs/clases/2026-10-07_clase_miercoles.md`,
> § C): el «replicador de carruseles virales» de la web del curso, pero gratis
> (las fotos se generan en Flow, que no gasta créditos).
> Código: `src/replicar_viral/carrusel.py`, API `/api/v1/replicar-viral/carrusel/*`,
> pantalla `/tiktok-shop-ai-pro/replicar-carrusel`, MCP `replicar_carrusel`,
> `producto_carrusel`, `subir_imagen_carrusel`, `descargar_carrusel`.
> Catálogo propio: `src/replicar_viral/catalogo.py`. Para VÍDEOS: [`replicar-viral.md`](replicar-viral.md).

## La idea

Mismo carrusel, diapositiva a diapositiva: **mismo papel y misma forma de texto
en cada foto, otro ambiente y NUESTRO producto**. La app no genera imágenes:
escribe el texto y el prompt de cada foto; tú las generas en Google Flow y la
app les quema el texto (el mismo estilo que el nicho Carruseles) y las da
todas en orden (en la web, una a una; por el MCP, también en ZIP).

## 1. De dónde salen

El operador busca en **Social1** (*Content Type › Slideshows only*, *Last 7
days*, *Trending*) y te pasa el enlace de TikTok. Comprueba con él qué
producto NUESTRO va con ese carrusel (del mismo estilo; búscalo con
`productos` en el catálogo del POV BOF). Solo para cuentas fuera de estado
crítico de CRH y pocos al día.

### Si el producto no está en ningún catálogo: «🖼️ Carruseles virales»

Se da de alta en la misma pantalla (caja «Carruseles virales» › «Dar de alta
un producto») o con
`producto_carrusel(product_url, foto_limpia, foto_ficha, carrusel_url)`:
foto limpia + captura de la ficha (título, tienda, precio) + URL del producto
en TikTok Shop; el enlace del carrusel viral es opcional. Cada foto puede ser
`archivo_id`, ruta de tu bandeja o URL. La app la guarda en el catálogo
`carruseles_virales` (carpetas de diez, como «Muestras productos»), lee los
textos de la ficha (una llamada de Gemini, solo de ese producto, con su coste)
y apunta `product_url`. Si devuelve `aviso` es que no pudo leer la ficha: el
producto queda y se reintenta con `producto_carrusel(releer_carpeta=…,
releer_producto=…)` (en la web, «Leer textos»).

El catálogo es **COMPARTIDO**: lo ven Néstor, Ana y Mauro, y cada uno puede
replicar el mismo producto en su cuenta. `producto_carrusel()` sin argumentos
lo lista (con `carrusel_url`, el último viral con el que se replicó).

## 2. Analizar y adaptar

`replicar_carrusel(catalogo, carpeta, producto, url=<enlace>)` (con el
catálogo nuevo: `catalogo="carruseles_virales"`). ~1 min, una
llamada de Gemini Flash (céntimos). Hasta 12 diapositivas. Devuelve `id`,
`formato` (3:4 o 9:16, el del original), `apto`, `caption`, `hashtags` y por
diapositiva: `rol`, `texto_original`, `texto` (el nuestro), `usa_foto_producto`,
`prompt_imagen` y `original` (enlace a la foto del viral, ábrela con `ver`).

Si `apto` es `false`, díselo al operador y no sigas sin su «sí».
Revisa los textos: sin promesas de salud ni resultados, nada que no diga la
ficha, y **cupones nunca afirmados** («revisa si tienes cupones», jamás «tu
cupón»). Si hay que corregir uno: `descargar_carrusel(id, texto_n=N, texto=…)`.

## 3. Generar (en la WEB, nunca por API)

En **Google Flow (Nano Banana)**, una imagen por diapositiva, en su `formato`:
- con `usa_foto_producto: true`, adjunta la **foto limpia del producto** como
  referencia (la bajas con `preparar_bandeja` o `ver` del POV BOF);
- pega el `prompt_imagen` tal cual (ya pide imagen sin texto).

Antes de subir, revisa (`comun/revision-calidad.md`): producto idéntico a la
ficha y a tamaño real, nada flotando, **ningún texto ni letras en la imagen**
(lo pone la app), sin niños, sin pantallas con números, y que se parezca a la
original en encuadre y emoción pero en otro sitio.

## 4. Subir y descargar

1. `subir_imagen_carrusel(id, n, archivo_id|ruta_bandeja|url)` por diapositiva
   (n = 1, 2…). La app guarda la foto y le quema su `texto`. Subir otra vez la
   misma `n` la sustituye.
2. `descargar_carrusel(id)` → `hechas`/`total` y `zip` (todas con su texto, en
   orden, + `caption.txt`). En la web: botón «Descargar todas» en la pantalla
   Replicar carrusel y «Fotos» en **Mis tandas › Fotos**, que bajan las fotos
   UNA A UNA y en orden (`carrusel_<producto>_<id>_01.jpg`, 02…), sin ZIP, para
   tenerlas listas en la galería (la tanda entera sí va en ZIP,
   ver `mis-tandas.md`).
3. Lo publica el operador (TikTok y, si toca, Instagram) con el caption y los
   hashtags, y lo marca **Subido** en Mis tandas › Fotos
   (`marcar_tanda(id, subido=True, fotos=True)`, solo si te lo pide).

## Replicar otra vez / para otro usuario

`replicar_carrusel(replica_id=<id>)` vuelve a replicar el MISMO viral con el
MISMO producto (textos nuevos: otra llamada de IA). Con `para="ana"` lo crea
en la cuenta de otro usuario — **solo el administrador** (Néstor); a los
demás les da 403. También vale `para` en una réplica nueva. En la web: caja
«Replicar otra vez» del carrusel abierto, y «Para:» junto al enlace. La copia
guarda `replica_de` (el id original) y aparece en el «Replicar carrusel» y en
Mis tandas › Fotos de ese usuario.

## Reglas

- Nunca la cara, el texto literal ni la foto del creador original.
- **Nunca niños ni bebés**; personas solo si el original las tiene, y otras.
- Lo que se vea tiene que ser NUESTRO producto (sanción por «producto
  incoherente»). Al menos una diapositiva lo enseña.
- Una réplica por carrusel y producto: no lances varias «por si acaso».
