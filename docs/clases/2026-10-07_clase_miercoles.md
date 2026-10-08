# Clase en directo del miércoles 7 oct 2026 (TikTok Shop AI Pro, Jonny)

Grabación de pantalla del móvil (1h18m) en `Drive › NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/_clases/clase_07_octubre.mp4`.
**El audio está vacío (-91 dB en toda la pista)**: Zoom no deja grabar el sonido
desde la grabación de pantalla del móvil. Todo sale de leer con OCR los subtítulos
en directo de Zoom (`2026-10-07_transcripcion_ocr.txt`, con hablante y minuto,
con errores de OCR) y de los fotogramas de su pantalla.
Método (reutilizable cada semana): `~/work/clase_07oct/` → `ffmpeg fps=1` recorta la
franja de subtítulos (y=1900-2330) y la de pantalla (y=870-1570), `ocr.py` (tesseract
`spa`, salta franjas vacías, invierte, 4 procesos: ~5 min para 78 min) y `build.py`
(deduplica y pone hablante).

## Resumen en una línea
Jonny lleva **el MISMO contenido de TikTok a Instagram + Facebook + Threads**
(Instagram Shop recién abierto en España «y sin sanciones por ahora»), monetizando
con **Amazon afiliados** donde no hay carrito, y lo automatiza con **Codex** (sube
historias con enlace desde el móvil por AirDroid, analiza la biblioteca de anuncios
de Meta, lanza y vigila campañas). Además estrena en la web del curso un
**replicador de carruseles virales** y enseña **Trybe** (marcas que pagan por vídeo).

## Lo nuevo, por bloques

### 1. Replicador de carruseles virales (web del curso, `ttshopaiproapp.com/#carruseles`) — min 0-2
- Se busca un carrusel viral en **social1** (filtro *Content Type › Slideshows only*,
  *Last 7 days*, *Trending*). Ejemplo: el carrusel del teckel «Un perrito por 1500 €?» →
  «Qué te parecen 24 😭» → «Un perrito cada uno de los 24 días antes de Navidad 🎁 (Enlace
  más barato)» (calendario de Adviento, @saludconsciente, 1,8 M vistas).
- Se pega el enlace de TikTok → **«Réplica viral diapositiva a diapositiva»**: el
  analizador desglosa cada foto con su papel (*1 Introductory · 2 Product Reveal ·
  3 Call to Action*) y marca en cuáles sale el producto (*Sin producto / Producto
  detectado*) → «Recreando ambientes…» → **«Compara tu carrusel»**: original arriba,
  generado abajo, **mismos textos, otra habitación/ambiente, mismo producto**.
- ~1 minuto por carrusel. Gasta **créditos de imagen: 1 imagen = 1 crédito, 150/mes**
  (100 gratis al mes para quien pagó el año, acumulables, «da para 20-30 carruseles»;
  se pueden comprar más).
- Él lo sube a TikTok **y a Instagram** (y el mismo producto lo tiene en Amazon).
- Un alumno (Alejandro) replicó 3 carruseles con social1 → **una venta con cada uno**, y
  la comisión de carrusel era igual que la de directo en los tres. Su cuenta piloto
  ya tiene carruseles activados al mes.

### 2. Multiplataforma Meta: Instagram + página de Facebook + Threads — min 4-15
- Montaje: **perfil personal de Facebook** (la base) → dentro, **una página de
  Facebook por nicho** con el mismo nombre y marca que su Instagram (él: su marca,
  ropa y «Medicina Saludable», que es su apuesta del Q4) → en Instagram, **Centro de
  cuentas** vincula el Facebook principal y, en *Editar perfil*, se enlaza la página
  correspondiente.
- Con eso, **cada reel de Instagram se publica solo en la página de Facebook y en
  Threads**. Si el reel lleva producto etiquetado de IG Shop, no deja cruzarlo: hay
  que subirlo aparte.
- **Facebook y Threads permiten enlaces en el título y en comentarios** (Instagram no):
  ahí pone el **enlace de afiliado directo** (Amazon). Además la página vinculada le
  deja hacer **campañas de Meta Ads** que salen en IG y FB a la vez.
- Facebook tiene público de 40-60 años: encaja con nichos como salud y «hay menos
  posibilidad de que reconozcan que es contenido de IA».
- Ejemplo a seguir: el creador **«Alex» de benefits** (EE. UU., >500 k $ de GMV en
  TikTok Shop) está metiendo **los mismos vídeos de TikTok en Instagram** con la cestita
  de IG Shop y lo que no tiene, a Amazon. Jonny ha dado la orden en su comunidad
  privada de hacer lo mismo.
- **Ritmo en Instagram: 2 vídeos al día (uno «de prueba» y uno normal) + 1 carrusel**,
  «Instagram no es como TikTok, que se come 20». Alejandro dice que a él le deja subir
  7 al día sin que se los entierre. Jonny: «a lo mejor con IG Shop es distinto, es
  nuevo».
- **Para etiquetar productos en IG Shop hacen falta 1000 seguidores**: escalar ya la
  cuenta de Instagram con vídeos de la estrategia de viralización (los «personajes»).
- Creadora a vigilar: **@flormedrano.21** (Instagram), casi todo viral, muy dinámico,
  aún no usa IG Shop.
- Alejandro: IG Shop quita fricción frente al «comenta X y te mando el enlace por MD».

### 3. Codex como empleado (lo que se ve en su pantalla) — min 4-8 y 73-77
- Proyecto «Ads TTShop AI Pro» en Codex (GPT-5.6) con navegador. Le pide: **«súbeme a las
  historias de mi móvil de Instagram todas las publicaciones con sus links, una por
  una»** → Codex sube los 20 creativos y la lista de enlaces de afiliado al Drive,
  **controla el móvil por AirDroid** (web.airdroid.com), abre Drive e Instagram y
  prepara cada historia con su enlace; enseña la primera antes de publicar el lote.
- «Búscame los 10 creativos de moda mujer que más estén funcionando en la **biblioteca de
  anuncios de Meta**»: Meta no enseña ROAS, así que ordena por señales públicas
  (antigüedad del anuncio activo, variantes, repetición del concepto). Regla de Jonny:
  **un anuncio activo desde hace meses = convierte**; muchos creativos nuevos de la
  misma marca = está testeando.
- Codex le lanzó una campaña (10 €/día, 5 € cada una, hasta el 14 oct) para su marca
  personal. Propone un **activador cada 4 h que pare los anuncios con ROAS < 2**.
- Copia de infoproducto: «copio el enlace de este tío en Codex y en 10 minutos tengo
  el producto y la web de ventas».

### 4. Contenido real para calentar la cuenta (nueva estrategia) — min 28-30 y 41-46
- **Mezclar contenido REAL con el de IA** (en vídeos separados, no en el mismo): al
  principio, ~**2 semanas** de vídeos reales de productos baratos que estén en TikTok
  Shop (KitKat, Coca-Cola, Kinder Bueno). Si la cuenta no está «caliente» de contenido
  real, sanciones de **baja calidad**; así caen las cuentas nuevas.
- El contenido real casi no tiene sanción de **producto inconsistente**: la IA de TikTok
  reconoce el producto real; en IA «le falta no sé qué» y salta.
- Se puede grabar un producto **sin huella de compra** en TikTok (su cafetera De'Longhi
  Magnifica). Lo de «tiene que verse el producto al 100%» es para los directos. Un alumno
  calentando la cuenta vendió un dron sin querer.
- **Generador de guiones de la web**: se arrastra la ficha (solo la de TikTok, nunca
  la de Amazon: si hay sanción, la apelación se defiende con la captura de la ficha de
  TikTok). Guiones: *Punto de valor, Beneficio principal, Venta inversa* (nuevo; 5
  ganchos, el recomendado marcado), duración hasta 60 s, y **devuelve también la
  toma a grabar en cada frase**. La voz con IA no hace que el vídeo real se marque
  como IA.
- Producción en serie: generar **5 voces** del mismo producto → grabar un vídeo de 2-3
  minutos moviendo el producto y cambiando de sitio → en CapCut cada voz sobre un tramo
  distinto = **5 vídeos de un tirón**. Truco: TikTok no deja meter audio, pero sí
  **superposiciones de vídeo** con audio. Y los **sonidos propios se reutilizan** desde
  la propia app (mantener grabar con el sonido ya subido).
- Alejandro graba 20 vídeos en 15 min moviéndose «como un boxeador» para que cada toma
  sea distinta; pone en la descripción el texto de la ficha.

### 5. Elegir producto con la estrategia GMV Max — min 50-56
- Producto que explota → todos lo venden → sin stock. Mejor: marca fuerte con buena
  inversión (mirar en Kalodata) → **en el móvil, entrar en su tienda y ordenar por
  NOVEDADES** → pedir la recién añadida con **menos de 200 creadores**: el
  presupuesto de anuncios del producto se reparte entre menos vídeos.
- No hace falta activar a mano la publicidad de cada vídeo (con el interruptor general
  basta), pero él lo activa «por si acaso».
- Organización: un top de EE. UU. graba miércoles y jueves y el resto edita/programa.
  Editor externo a ~2-3 $ por vídeo.

### 6. Herramientas y plataformas mencionadas
- **Trybe** (portal de creadores, «empezó este año y ha facturado 7 M»): marcas
  (Happy Howl, Plus Ultra, Blackline…) que **pagan por vídeo** (no por venta): subes un
  portafolio con tus 5 mejores vídeos y conectas redes, pides colaborar, firmas y ellos
  **distribuyen tu vídeo por todas las plataformas y le meten anuncios**. «Sin
  sanciones». De momento EE. UU.; Jonny ha mandado solicitudes. Vídeo de referencia en
  YouTube: «5 Things That Took Me From $0 to $30,000 On Trybe».
- **Grupo de cuentas compartidas** por Discord (~20 $/mes vía Whop: Kalodata, FastMoss,
  ChatGPT, ElevenLabs, Canva…). Kalodata va mejor que el de 7 $ del classroom. Son
  cuentas revendidas (contra los términos de esas webs): **no lo recomiendo**.
- **FastMoss** (la «rosa»): más métricas de anuncios, pero capado desde España.
- **Avatares de IA en Instagram** (p. ej. charles.robinson62, «Creative Partner
  @higgsfield», ~1 M de seguidores en 5 días): se monetizan con **colaboraciones de
  marca** por historias, no con TikTok («de TikTok olvídate al 100%»).
- **Contenido de remedios caseros con Veo** («vierte agua oxigenada en tus pies y mira
  lo que pasa»): lo enseñará el **viernes**. Se monetiza con infoproductos.
- Amazon: **Amazon Associates** (cualquiera con un Gmail; hay que hacer alguna venta en
  los primeros ~180 días o la cierran) ≠ **Amazon Influencers** (validan el perfil y
  mandan muestras; como SHEIN).
- Cuentas de IA: él subió **50 creativos de imagen al día** en una cuenta sin
  sanciones ni límite.

## Qué podemos automatizar nosotros (propuesta)

Lo que ya tenemos y sirve tal cual: **Mis tandas** tiene todos los vídeos montados
(POV BOF, Largo, Multimodo), con nombre del producto quemado y subtítulos; el
**semáforo** dice cuáles son seguros; el **nicho Carruseles** y **Replicar viral**
ya hacen la mitad del trabajo; y hay **control del móvil por adb/scrcpy**
(`asistentes/juego/pantalla.py`).

### A. Reels a Instagram + Facebook + Threads (prioridad 1)
1. Néstor crea (una vez, a mano): página de Facebook por cuenta/nicho, Instagram como
   **cuenta profesional** (creador/empresa), vinculados en el Centro de cuentas, y una
   **app de Meta** con la API de publicación de contenido (permiso `instagram_content_publish`).
2. Nosotros: menú «📤 Multiplataforma» que coge los 🟢 de Mis tandas que ya están subidos
   a TikTok y publica **2 reels/día + 1 carrusel/día** por cuenta de IG con la API oficial
   (programado por cola). FB y Threads salen solos por la vinculación (sin etiqueta de
   producto). Caption: el de TikTok sin hashtags de TikTok Shop.
3. Antes de subir: **quitar todo lo que sea de TikTok Shop** del vídeo (rótulos «toca el
   carrito naranja», CTA de la voz «añádelo al carrito»). Variante de montaje sin CTA de
   TikTok o con CTA neutra («enlace en el comentario/en la bio»).
4. Hasta tener 1000 seguidores no hay etiqueta de IG Shop: se monetiza con el enlace de
   **Amazon Associates** en el título del reel de Facebook/Threads y en el primer
   comentario.

### B. Historias de Instagram con enlace (prioridad 2)
La API de Meta publica historias pero **no pone el sticker de enlace**: hay que hacerlo
desde el móvil, como hace Jonny con AirDroid. Nosotros tenemos adb: un agente sube N
historias con su sticker de enlace (Amazon/IG Shop), enseña la primera y sigue.

### C. Replicador de carruseles virales (prioridad 2)
Calco de lo que hace la web del curso, encima de lo que ya hay:
enlace de TikTok → tikwm (ya devuelve `images` en los carruseles: hoy `replicar_viral`
los rechaza) → Gemini analiza cada foto (papel, texto, si sale producto, ambiente) →
**prompt de Flow (Nano Banana) por diapositiva** con la foto del producto y el texto en
español → el agente genera en Flow (imágenes ilimitadas, sin coste) → se quema el texto
con el motor de Carruseles → se publica en TikTok **y** en Instagram. Sale gratis frente a
los créditos de la web. Por ahora se puede usar la web del curso (100 créditos/mes).

### D. Amazon Associates (prioridad 3, necesita a Néstor)
Alta en `afiliados.amazon.es` (gratis). Para cada producto nuestro buscar el mismo
en Amazon y guardar su enlace de afiliado en la ficha (campo nuevo). Ojo: es lo
que monetiza IG/FB/Threads mientras no hay IG Shop.

### E. Calentar cuentas nuevas con contenido real (Cuenta Piloto)
Encaja con la **Cuenta Piloto** (vídeo orgánico, voz IA): 2 semanas de vídeos reales
antes de meter IA. El flujo «5 voces + un vídeo largo grabado = 5 vídeos» se puede
automatizar: Néstor graba 2-3 min de un producto, nosotros cortamos tramos distintos y
ponemos 5 guiones de Fish con subtítulos.

### F. Lo que NO montaría (todavía)
- Meta Ads con presupuesto propio: requiere producto propio/afiliado validado y dinero;
  primero orgánico.
- Trybe: solo EE. UU. y pide portafolio; apuntarse cuando tengamos 5 vídeos fuertes.
- Avatares de IA en Instagram y remedios caseros: otro modelo de negocio (colaboraciones
  e infoproductos). Esperar a la clase del viernes.
- Cuentas compartidas de Discord: contra los términos de servicio.

## Investigación 8/10 — qué se automatiza y qué no

| Plataforma | Por API desde el VPS | Límite/día | Enlace | Ojo |
|---|---|---|---|---|
| Instagram Reels | ✅ `/{ig}/media` `media_type=REELS` (+ `trial_params` = reel de prueba) | 50 | No clicable; bio/historia | Cuenta profesional + app de Meta propia (sin App Review si solo cuentas nuestras) |
| IG Historias | ⚠️ API sí, pero SIN sticker de enlace | — | Solo a mano/adb | Historias con enlace → móvil por adb (`pantalla.py`) |
| Facebook Página (reel) | ✅ `/{page}/video_reels` (se publica aparte, no hay «compartir» por API) | 30 | Mejor 1.er comentario | 3-90 s |
| Threads | ✅ API propia | 250 | URL en texto (máx 5) | Tarjeta de enlace solo en posts de texto |
| Pinterest | ✅ API v5 pin de vídeo con `link` | — | ✅ clicable en el pin | Necesita acceso Standard (vídeo del OAuth + privacidad); prohíbe automatizar sin API aprobada; enlace directo, sin acortador |
| Amazon Afiliados | Enlace `dp/<ASIN>?tag=` | — | — | Aviso literal obligatorio; sin acortadores que oculten Amazon; precios solo de Amazon; ~3 ventas en 180 días |
| SHEIN | Enlace de afiliado (programa propio o Awin/CJ/Admitad) | — | — | ~10-20 %, cookie 30 días, pago desde 20 $; sin mínimo oficial de seguidores; el contador «24 h» SIN CONFIRMAR (probar con enlace real) |

Plan: un job programado en el VPS (cola de la app + timer systemd/cron cada X h) que coge vídeos ya
montados (versión sin carrito), y publica IG reel (+prueba), FB reel + comentario con enlace,
Threads y Pinterest con el enlace de Amazon/SHEIN del producto. Solo las historias con enlace
quedan para el móvil (adb). Alternativa sin programar: Metricool/Buffer (de pago por canal).
