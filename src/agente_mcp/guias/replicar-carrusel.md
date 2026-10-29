# Replicar carrusel — guía para agentes

> Viene de la clase del 7 oct 2026 (`docs/clases/2026-10-07_clase_miercoles.md`,
> § C): el «replicador de carruseles virales» de la web del curso, pero gratis
> (las fotos se generan en Flow, que no gasta créditos).
> Código: `src/replicar_viral/carrusel.py`, API `/api/v1/replicar-viral/carrusel/*`,
> pantalla `/tiktok-shop-ai-pro/replicar-carrusel`, MCP `replicar_carrusel`,
> `producto_carrusel`, `subir_imagen_carrusel`, `descargar_carrusel`.
> Catálogo propio: `src/replicar_viral/catalogo.py`. Para VÍDEOS: [`replicar-viral.md`](replicar-viral.md).

> **⛔ PROHIBIDO el texto genérico (Néstor, 29/10/2026).** Nunca un mismo estilo
> «por defecto» (`tiktok_medio`/`tiktok_sans` grande y en negrita) para todos los
> carruseles. Cada diapositiva lleva el **estilo de texto TAL CUAL el original**
> (letra, grosor, color, contorno, caja/píldora/barra de Snapchat, mayúsculas,
> tamaño) y en la **MISMA POSICIÓN** (altura, lado, alineación y cortes de línea).
> Si el viral cambia de estilo o de sitio entre diapositivas, el nuestro también
> (`estilo_n`). Un carrusel con texto genérico NO se pone en verde: se rehace.
> Detalle en § «Letra: la que se parezca al viral».

## La idea

Mismo carrusel, diapositiva a diapositiva: **mismo papel y misma forma de texto
en cada foto, las fotos lo más parecidas posible al viral y NUESTRO producto**. La app no genera imágenes:
escribe el texto y el prompt de cada foto; tú las generas en Google Flow y la
app les quema el texto (el mismo estilo que el nicho Carruseles) y las da
todas en orden (en la web, una a una; por el MCP, también en ZIP).

## 1. De dónde salen

El operador busca en **Social1** (*Content Type › Slideshows only*, *Last 7
days*, *Trending*) y te pasa el enlace de TikTok. Comprueba con él qué
producto NUESTRO va con ese carrusel (del mismo estilo; búscalo con
`productos` en el catálogo del POV BOF). Solo para cuentas fuera de estado
crítico de CRH y pocos al día.

**Social1 de PAGO = Chrome principal (CDP 9222)**, pestaña propia en
`https://www.social1.ai/` (logueado «Nestor»; ese Chrome ya sale por la IP
española). **Trampa:** si ves «Unlock Social1», solo los puestos #61-72 o
«Sign In», estás en el Chrome del proxy 9223 (perfil sin la cuenta de pago):
ciérralo y usa el 9222. Datos sin clicar: la server action de la home (`next-action`
que se ve al marcar *Slideshows only*) con `region` es/uk/fr/de/it/us y `tsStart`/`tsEnd`.

### Buscar virales de cada país (tú solo, sin que te pasen enlaces)

Néstor (27/10): se replican virales de los países de TikTok Shop Europa que
pueden comprar con nuestro carrito, **en su idioma y tal cual**, y se suben en
la cuenta de ness (VivaShop). Social1 tiene **es, fr, de, it, ie, uk** (no
AT/BE/NL/PL: para esos, virales de FR/DE en su idioma valen igual). Un día un
país, otro día otro, o mezclados.

1. Enciende el navegador (`navegador on`; sin permisos, `sudo -n navegador on`)
   si hay RAM (≥2,5 GB disponibles, ver `comun/navegador-vps.md`).
2. Recoge los carruseles del país (30 días, ordenados por GMV y visitas):
   ```bash
   ~/nav-venv/bin/python scripts/social1_carruseles.py fr --dias 30 --paginas 25 \
       --salida /tmp/s1_fr.json      # ~12 por página, tarda: en segundo plano
   ```
   Cada fila trae `url` (la de TikTok, para `replicar_carrusel`), `producto`,
   `tienda`, `gmv`, `view_gain`, `is_ad`. Abre su pestaña propia y la cierra.
3. Elige los mejores: con GMV (vende) o muchas visitas ganadas, sin niños, sin
   promesas de salud, nada de marcas que no estén en España.
   **Descarta los de dibujos animados** (Simpsons, Bob Esponja, memes de
   personajes que se ponen la ropa o enseñan el producto): TikTok los puede
   sancionar (Néstor, 27/10). Los que ponen un **precio fijo** sí valen, pero el
   precio se cambia por algo que no sea precio fijo («a precio de chollo»,
   «revisa si tienes cupones», «mira la oferta en el carrito»). No repitas: mira
   antes `producto_carrusel()` / la lista de «Tus carruseles» (`carrusel_url`).
4. **Solo el MISMO producto, enlazable desde España** (Néstor, 27/10). Los
   productos de las tiendas de FR/DE/IT salen «Este artículo solo está
   disponible en FR» y no se pueden añadir al escaparate. Valen los
   internacionales (tiendas que venden en varios países): cruza `product_id` y
   tienda con lo recogido en España y, si no, abre
   `https://www.tiktok.com/view/product/<product_id>` en el **Mi 8**: tiene que
   salir «Comprar» / «Añadir al escaparate» sin ese aviso. Social1 no dice si
   hay envío internacional. **Nunca un producto «parecido»** (riesgo de sanción
   por producto incoherente): si no es el mismo, se descarta.
5. `replicar_carrusel(..., url=<url>, pais="FR")` y sigue §2-§4 como cualquier
   carrusel (fotos en Flow, subir, quemar, Mis tandas con semáforo).
6. Apaga tu pestaña al terminar; el navegador se apaga solo a los 45 min.

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

`replicar_carrusel(catalogo, carpeta, producto, url=<enlace>, pais="ES")` (con el
catálogo nuevo: `catalogo="carruseles_virales"`).

**Virales de otros países (Néstor, 27/10):** se replican tal cual, EN SU IDIOMA.
`pais` = ES, FR, DE, IT, AT, BE, NL, PL, IE o GB (los 10 de TikTok Shop Europa
que pueden comprar con carrito). Textos, caption y hashtags salen en ese idioma
y el carrusel lleva la bandera en la web y en Mis tandas. En Social1, `region`
fr/de/it/uk. El producto tiene que estar en NUESTRO catálogo de España (la
cuenta solo enlaza productos de ES): busca el equivalente. En otros países solo
carruseles, no vídeos. «Replicar otra vez» conserva el país.

**Cuenta árabe (Mi 8, `pais="AR"`, 29/10):** no es un país, es la cuenta para el
público árabe/magrebí (ver `docs/CUENTA_ARABE.md`). Se replican virales de las
TIENDAS ÁRABES que venden (oujdia, chef.nadia, saritasara…) **con su estilo y sus
textos**, no los nuestros: misma mezcla de español y darija/árabe, y el PRECIO de
nuestra ficha donde lo lleve el original. Los hashtags de TikTok son los árabes
fijos (`HASHTAGS_ARABE`) más 3 de la IA. El texto mixto con números ya se pinta
bien (Tajawal + bidi, `src/texto_arabe.py`), pero mira la imagen: precio legible
y dentro de la zona segura. ~1 min, una
llamada de Gemini Flash (céntimos). Hasta 12 diapositivas. Devuelve `id`,
`formato` (3:4 o 9:16, el del original; **genera SIEMPRE las fotos en 3:4**, aunque el original sea 9:16 — decisión de Néstor del 20/10/2026; las fotos reales de la ficha se encajan también a 1080×1440), `apto`, `caption`, `hashtags` y por
diapositiva: `rol`, `texto_original`, `texto` (el nuestro), `usa_foto_producto`,
`prompt_imagen` y `original` (enlace a la foto del viral, ábrela con `ver`).

Si `apto` es `false`, díselo al operador y no sigas sin su «sí».
Revisa los textos: sin promesas de salud ni resultados, nada que no diga la
ficha, y **cupones nunca afirmados** («revisa si tienes cupones», jamás «tu
cupón»). Si hay que corregir uno: `descargar_carrusel(id, texto_n=N, texto=…)`.
El caption se cambia con `descargar_carrusel(id, caption=…)`; también rehace el de sus publicaciones de Meta que sigan en cola (`meta_actualizadas`).
**Caption (Néstor, 23/10 — el de los carruseles que mejor salieron):** parte del caption del viral (`referencia`) pero REESCRITO, nunca copiado literal (texto duplicado = contenido no original, y suele traer precios o promesas): misma idea y tono, otras palabras. UNA o dos frases en primera persona o de gancho que nombran el producto (marca + qué es + qué incluye) y cierran con «Lo tienes en el carrito naranja 🧡» y/o «Revisa si tienes cupones». Sin precios, cifras, stock ni urgencia. Ej.: «Pack rutina de Maybelline con máscara, corrector y labial. Revisa si tienes cupones disponibles 🧡» · «Convierte tu dormitorio en un cielo de estrellas antes de dormir 🌌 Lo tienes en el carrito naranja.»
**Textos de las diapositivas:** los del viral, CASI literales (mismo gancho, mismos emojis, mismos cortes de línea), quitando precios, «menos de X €», «queda poco stock», «corre que vuelan» y lo que la ficha no diga (cambia «temas» por «discos» si la ficha dice discos).

## 3. Generar (en la WEB, nunca por API)

En **Google Flow (Nano Banana)**, una imagen por diapositiva, en su `formato`:
- con `usa_foto_producto: true`, adjunta la **foto limpia del producto** como
  referencia (la bajas con `preparar_bandeja` o `ver` del POV BOF);
- pega el `prompt_imagen` tal cual (ya pide imagen sin texto).

Antes de subir, revisa (`comun/revision-calidad.md`): producto idéntico a la
ficha y a tamaño real, nada flotando, **ningún texto ni letras en la imagen**
(lo pone la app), sin niños, sin pantallas con números.

**Replicar lo máximo posible (Néstor, 27/10 — SIEMPRE):** todo lo del viral
está ahí por algo. Antes de generar, pon cada `prompt_imagen` al lado de su
foto original y corrígelo si no pide lo mismo: misma hora y luz (puesta de sol
→ puesta de sol), mismo sitio y fondo (estadio, lago, tienda…), mismas poses y
gestos, mismo encuadre, mismos colores. Al bajarlas, hoja viral arriba /
nuestra abajo: si una foto no se parece (p. ej. cielo de día donde el viral
tiene atardecer), se REGENERA. No es copia: la imagen se hace desde cero y la
persona es otra.

### Letra: la que se parezca al viral

Por defecto el texto sale como el nativo de TikTok (blanco, contorno negro).
Mira las fotos del viral (`original` de cada diapositiva) y elige la letra que
más se le parezca, para TODO el carrusel:
`descargar_carrusel(id, estilo_texto=…, texto_y=…, texto_tam=…)` — `tiktok`, `clasico`
(TikTok sin contorno grueso), `pildora` (negra sobre píldora blanca),
`pildora_negra` (blanca sobre píldora oscura), `maquina` (máquina de
escribir), `elegante` (serif gruesa), `manuscrita`, `rotulador`, `impacto`
(mayúsculas condensadas). `texto_y` = altura del bloque (0.05 arriba … 0.95
abajo; si el viral lo lleva abajo, ~0.75).)
`texto_tam` = multiplicador del tamaño (0.5-1.6; sin él, el del estilo; los
virales suelen llevar la letra pequeña: prueba ~0.7-0.8). Vuelve a quemar todas
las fotos.

Copiar el texto NATIVO de TikTok (TikTok Sans, la fuente de la app):
- `tiktok_sans` — letra blanca, contorno fino y sombra, SIN caja. El texto
  clásico de TikTok sobre la foto.
- `tiktok_medio` — la misma, más fina (medium): la de los textos normales de
  TikTok, pequeños y sin negrita. Medido en los virales: `texto_tam` 0.75 (texto pequeño a media altura) a 0.95 (gancho arriba).
- `tiktok_crema` — la `tiktok_medio` en color crema (amarillo pálido, sin contorno
  marcado): virales de regalo tipo «Do you have a girlfriend…». 0.8 de tamaño.
- `tiktok_amarillo` — la letra de TikTok en amarillo con contorno oscuro
  (el texto amarillo de muchos virales de hogar y regalos).
- `fondo_negro` — blanca sobre caja negra opaca, líneas unidas en una sola forma
  (el «texto con fondo» de TikTok). Si el viral lleva el texto sobre una barra
  negra.
- `fondo_blanco` — negra sobre caja blanca opaca unida (fondo blanco de TikTok).
- `fondo_trans` — blanca sobre caja negra semitransparente unida.
- `fondo_rosa` — fucsia sobre caja rosa claro unida (virales de maquillaje y belleza).
- `pildora_tiktok` — negra con la letra de TikTok (medium) sobre píldora blanca por línea: el texto «con fondo» de la app en la mayoría de virales («Juste ici⤵️», «S'il porte une doudoune…»). NO uses `pildora` (Rubik, otra letra) si el viral lleva la de TikTok.
- `pildora_impacto` — mayúsculas condensadas negras sobre píldora blanca («EN PROMO‼️», «DISPO ICI👀»).
- `impacto_fino` — mayúsculas condensadas blancas solo con sombra (sin el contorno gordo de `impacto`).
- `editorial` / `editorial_negra` / `redonda_oscura` / `anuncio_azul` — letra OSCURA sin caja ni contorno para los virales que son anuncios de diseño (título arriba sobre pared o cielo claro): serif fina marrón (Cormorant), serif gruesa casi negra (PT Serif), redondeada granate (Fredoka) o sans azul marino (Poppins). Pide en el prompt de la foto esa zona despejada y clara donde va el texto. Llevan detrás un resplandor blanco difuminado (como los virales de anuncio) que las deja leer aunque la pared tenga cuadros o plantas. Si el viral lleva el texto a un lado, `texto_alinear` = `izquierda` / `derecha` (margen del 7 %); los espacios duros apenas lo mueven.
- `anuncio_blanco` — blanca gruesa con sombra de los anuncios de fondo oscuro. En cualquier estilo, `*palabra*` va en amarillo (viral con una palabra resaltada en otro color).
- `snap` — la barra de Snapchat: banda negra translúcida de lado a lado y letra pequeña (medium). Muchos virales de ropa la usan; ponla a la altura del viral con `texto_y`.
**Textos (SIEMPRE, Néstor 27/10):** misma letra o la más parecida, mismo
efecto (píldora, contorno, sombra, barra, mayúsculas, color) y en el MISMO SITIO
de la foto que en el viral: si el viral pone una etiqueta sobre cada persona o
cada objeto («Ich» / «Meine Mama», «Ohne sie» / «Mit ihr»), la nuestra también,
encima de lo mismo, con los mismos cortes de línea y emojis en su sitio. Nunca
una letra que no se parece ni el texto movido «porque queda mejor».
**Mismo estilo, misma letra y mismo tamaño que el viral** (Néstor, 22/10 y 27/10: «eso influye mucho»; la letra más parecida Y el mismo aspecto: píldora si el viral lleva píldora, misma fuente dentro de la píldora, mayúsculas si van en mayúsculas): quema la diapositiva 1, ponla al lado de la original y ajusta `estilo_texto`, `texto_tam` y `texto_y` hasta que no se distingan. Si el viral MEZCLA letras (barra de Snapchat en la 1ª y texto normal en la 2ª), pon primero el estilo general y luego el de esa diapositiva con `estilo_n`; compara TODAS, no solo la 1ª. Fíjate también en los cortes de línea del viral y cópialos con `\n` en el texto.
Los tres `fondo_*` salen ya a ~0.78 del tamaño base; afina con `texto_tam`.
**Cómo se clava (lo que funcionó, 23/10):**
- Compara SIEMPRE el carrusel entero: fila de arriba el viral, abajo el nuestro ya quemado (baja el ZIP y monta la hoja). Ajusta hasta que, de un vistazo, no se distingan letra, tamaño, altura y cortes.
- Altura y tamaño **por diapositiva** si el viral los cambia (gancho arriba en la 1ª, texto a media altura en las demás): estilo general con `descargar_carrusel(id, estilo_texto, texto_y, texto_tam)` y luego cada una con `estilo_n=N` + `texto_y` + `texto_tam`.
- **Dos textos en la misma diapositiva** (uno arriba y otro abajo, típico del CTA final): un solo texto con líneas vacías en medio (líneas con un espacio duro U+00A0); sube o baja el número de líneas hasta que cada bloque quede a la altura del viral.
- Valores que salieron bien: proyector (texto pequeño medio) `tiktok_medio` 0.75 a y≈0.4-0.6; boxeo (gancho arriba) `tiktok_medio` 0.95 a y≈0.17; maquillaje `fondo_rosa` 0.9 a y≈0.8; proteína/belleza `tiktok_sans` 0.7-0.95.
- **Consistencia antes que texto:** todas las diapositivas con la foto del producto como referencia y el producto IDÉNTICO a la ficha (forma, piezas, cómo se conecta: si va directo al enchufe por USB, nada de base ni cable aparte). Si una sale distinta, se REGENERA esa diapositiva añadiendo al prompt la descripción exacta de la pieza que falló; Nano Banana en Flow es ilimitado, no se aprueba nada «casi igual».
**Que se lea siempre**: comprueba la hoja final; si el texto pisa algo claro y
se pierde, cambia `texto_y` o usa `pildora`/`pildora_negra`. Nunca letra oscura
suelta sobre la foto.

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
3. **Música** (`musica` en `descargar_carrusel(id)` y en `mis_tandas(fotos=True)`):
   - `musica.tiktok` — la canción del viral (`titulo`, `autor`, `enlace` al
     sonido). Es la que se pone en TikTok, a mano, al publicar. Casi siempre es
     un «original sound» de una cuenta de edits: **solo vale en TikTok**.
     La app la adjunta SOLA al crear la réplica (la del viral, original o canción con nombre): no hay que buscarla; usa siempre esa al publicar en TikTok.
   - `musica.meta` — para Instagram/Facebook/Threads: una pista Mixkit sin
     copyright del banco de Multiplataforma (`estilo`, `pista`, `fichero`
     relativo a `Multiplataforma/`, `url`). Fija por carrusel: úsala tal cual,
     nunca la del viral fuera de TikTok.
   En la web sale debajo del caption, en Replicar carrusel y en Mis tandas › Fotos,
   con botón «Canción» para copiar el título y buscarlo en TikTok. Al lado va la
   miniatura del producto con «Ver producto» (su ficha de TikTok Shop) o «Título»
   para copiarlo si el catálogo no tiene la URL.
4. Antes de darlo por hecho, revísalo (todas las diapositivas contra la ficha)
   y ponle semáforo: `semaforo_tanda(id="car|<id>", color, motivo)`. Sin
   semáforo (o en rojo) no entra en el ZIP de Mis tandas › Fotos.
5. Lo publica el operador (TikTok y, si toca, Instagram) con el caption y los
   hashtags (en TikTok, los MISMOS de los vídeos — configuración de hashtags
   del POV BOF — más los de moda si es ropa/calzado/bolsos; los de la IA,
   `hashtags_ia`, se usan en Meta), y lo marca **Subido** en Mis tandas › Fotos
   (`marcar_tanda(id, subido=True, fotos=True)`, solo si te lo pide).
6. **Instagram/Facebook/Threads**: con su enlace de Amazon/SHEIN, se programa
   con `encolar_carrusel` (ver `guia("multiplataforma")` › Carruseles).

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
- **Sin precios**: ni cifras («8,45 €», «por menos de 10 €», «sin gastar 300 €»)
  en los textos ni en el caption. El precio cambia y el enlace de Meta es otro.
- **Revisa los `prompt_imagen` ANTES de generar** (Gemini se equivoca): el
  producto sale idéntico a la ficha (nunca «un proyector genérico»), en un sitio
  donde tiene sentido, y lo que va con corriente (lámparas, proyectores, mesitas
  con carga, tocadores con luces) junto a la pared con el cable a un enchufe
  visible. Fuera bocadillos, pantallas con texto o precios e iconos de apps. Si
  la foto limpia es una infografía o lleva sellos, usa otra como referencia.
