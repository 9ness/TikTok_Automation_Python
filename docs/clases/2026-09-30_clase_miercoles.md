# Clase en directo del miércoles 30 sep 2026 (TikTok Shop AI Pro, Jonny)

Grabación de pantalla del móvil (1h46m) en `Drive › NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/_clases/`.
El audio se oye mal y la segunda mitad está muda; esto sale de leer con OCR los
subtítulos en directo de Zoom (`2026-09-30_transcripcion_ocr.txt`, con errores
de OCR) y de los fotogramas de su pantalla.

## Lo nuevo que no tenemos

### 1. Clonar un vídeo viral que ya vende (lo más importante de la clase)
1. **Buscar la idea** en **social1.ai** (ranking de vídeos virales por país,
   con GMV del creador, etiquetas `Ad`/`AI`, botones «AI Insights» y
   «Transcribe»). También en Kalodata. Mejor si son vídeos cortos.
2. **Comprobar que el vídeo SIGUE teniendo carrito**: si no lo tiene, al
   creador le han sancionado (inconsistencia, etc.) y no se copia.
3. Sacar el producto: el enlace del vídeo → móvil → carrito → captura de la
   ficha → añadir al escaparate.
4. **tagshop.ai › Ad Clone** («Clone viral ads in minutes»): se pega la URL de
   TikTok + la foto y la ficha del producto, y **GRATIS** (0 créditos) devuelve
   el **plan plano a plano** con los tiempos («0-3 s primer plano en una tienda…,
   corte directo…»). No hace falta pagar el vídeo, solo se usa el plan.
5. **submagic.co › TikTok transcript generator** (gratis) → el guion del vídeo.
6. Pasar las dos cosas a DeepSeek: «traduce», «mételo en un vídeo de 15 s» y
   pegarle el guion: devuelve el plan adaptado. Hay que quitar lo que copie de
   los textos en pantalla del original.
7. El primer fotograma: captura del gancho del original → «replica esta
   imagen, elimina los gráficos y cambia el fondo» (para que no se vea igual).
8. Generar en **Omni** con la imagen del primer fotograma y el producto como
   **ingredientes** (no como fotograma inicial), para que se invente el resto
   de escenas: la primera mitad del guion en un clip de 10 s y la segunda en
   otro de ~6 s. También lo probó en **Grok (SuperGrok)**. (Lo confirma el
   resumen de una alumna, que añade que en social1 filtra por «Contenido con
   IA».)
9. CapCut: quitar silencios, subir un poco la velocidad, subtítulos en una
   sola línea.

La conclusión de Jonny: hay dos estrategias, menos vídeos y más trabajados que
copian ideas ya probadas (España o EE. UU.), o volumen. Va a subir un módulo
«Cómo replicar contenido viral» al classroom.

### 2. Copiar carruseles virales
Mismo flujo con carruseles de social1, por ejemplo una luz LED con 3 M de
vistas («Rojo para Netflix», «Azul para relajarse»…): en Flow con Nano Banana,
«esta idea, pero cambia la habitación, texto en español y elimina los gráficos
de TikTok», un color en cada foto. Puede ir en **inglés** si el almacén vende
en varios países de la UE. Unos 10 min por carrusel y gratis. Según él, en
carruseles **no hay límite (~50/día)**, aunque han bajado algo la comisión.
Propone pagar a un editor de Fiverr/Workana (~20 € por 50-80) o automatizarlo
con Codex.

### 3. Gancho de texto largo encima del primer clip (formato de un alumno)
Primero un clip real/orgánico con un **texto largo que da curiosidad** y aún no
enseña el producto, para que se queden leyendo 2-3 s, y después el clip del
producto. Ejemplo: «Los que compraron este limpiador hace unos días mejor que
NO miren la oferta que tiene ahora porque os vais a enfadar 😭». Usa un chat de
DeepSeek ya enseñado: se le pasa la ficha y devuelve **3 variaciones en líneas
de 4 palabras, una encima de otra, sin separaciones**. Para el Q4 / Black
Friday encaja muy bien.

### 4. Varios cortes dentro de un mismo clip de 10 s
En Omni/Veo, aunque haya fotograma inicial, el prompt puede pedir planos con
tiempo: «del segundo 1 al 3…, del 3 al 6 en una calle peatonal…». Salen
microcortes y el clip es más dinámico. Su nuevo prompt de UGC lleva 3 escenas
con cortes dentro.
- **Fotograma inicial**: el vídeo empieza exactamente ahí.
- **Ingrediente/referencia**: se inventa la escena y hay más riesgo de que
  cambie los atributos del producto.

### 5. Avisos y otros datos
- **Cuidado con las webs baratas de vídeo**: suelen usar motores parecidos y
  no los originales, y salen deformaciones (bocas, poses). El analizador de
  TikTok las marca como baja calidad y sanciona. Mejor Flow / Omni / Veo
  oficiales. Un clip real al principio ayuda a que no lo marque como baja
  calidad.
- Edición: zoom con keyframe en los clips estáticos para darles movimiento,
  subtítulos en una línea y con una fuente que tenga tildes (mucha gente lo ve
  sin sonido).
- **Cuentas nuevas: 7 vídeos al día** (antes decía 10) y vídeos más largos;
  si son cortos, subir menos.
- **Instagram Shop**: ya vende por ahí. Pide crear cuentas de Instagram (1
  vídeo al día) y viralizarlas. La «multiplataforma» (IG Shop, Pinterest,
  Facebook) aún la está probando.
- Cuentas extra: al graduarte, más cuentas al llegar a 1000 seguidores.
- Gancho de acción del UGC (no nos interesa por ahora): por ejemplo, alguien
  que casi se cae de una escalera vieja y luego la escalera nueva. Hay que
  revisar los fallos de la IA (le faltaba un peldaño).

## Qué cuestan las webs (comprobado el 2 oct 2026)
- **submagic.co › TikTok transcript generator**: gratis.
- **tagshop.ai**: desde 14 $/mes (anual). En la clase sacó el plan de escenas
  con 0 créditos; si eso sigue siendo gratis no está documentado.
- **social1.ai**: Pro a 24,95 €/mes con 7 días gratis; 200 créditos al mes y
  «AI Insights»/«Transcribe» gastan 1 cada uno. Sin cuenta solo enseña EE. UU.
  desde el puesto #61. Bloquea el Chrome del VPS (control antibots de Vercel,
  «Code 11»), así que se busca desde el móvil y se pasan los enlaces. Filtros
  útiles: país ES/US, *Top Converters* o *Biggest Hits*, embudo › *AI Content*
  y *Content Type* vídeo o foto.
- Alternativa para carruseles: **carouscale.com**, que indexa carruseles de
  TikTok Shop de más de 5000 vistas en 6 mercados (España incluida). Desde
  29 €/mes; el plan gratis da una sola réplica.

Para nosotros el análisis de tagshop + submagic lo puede hacer Gemini con el
vídeo (plan de escenas + transcripción en una sola llamada). El vídeo serían
DOS clips mudos de 8 s (GenAI Pro / Magnific) con la voz de Fish encima: Omni
con voz gasta más créditos.
