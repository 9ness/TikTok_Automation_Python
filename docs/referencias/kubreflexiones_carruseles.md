# @kubreflexiones — cómo hace sus carruseles (referencia, 19/10/2026)

Cuenta del curso (2,5K seguidores) que vive de carruseles de FOTOS con carrito
de TikTok Shop España (todos `is_ec_video`, muchos además promocionados). Se
estudiaron sus 44 últimos carruseles + los más vistos («Popular», 50-110K
vistas). Es el criterio para «Replicar carrusel» (`src/agente_mcp/guias/replicar-carrusel.md`).

## Estructura que repite

- **Cortos: 2-3 diapositivas** (la mitad son de 2). Los de 4-6 son «mini-guía»
  de cosmética (problema → causas numeradas → producto → «úsalo así»).
- **Diapositiva 1 = gancho de situación, sin producto o con el producto de
  fondo**: una escena cotidiana que duele o hace gracia («Llegué del curro y mi
  novio me dijo que había tendido la ropa», «Necesito otro salón para poner otro
  tendal», «es invierno… deja de andar con zapatos blancos sucios»).
- **Última = el producto en uso + llamada a abajo**: «Esto es lo que quería
  decir yo con tender la ropa», «Vale, ESTO es lo que me convenció», «(AQUÍ
  TIENES EL ENLACE)», «Enlace abajo 👇», a veces una flecha roja dibujada hacia
  el carrito.
- **Formatos que se repiten** (de más a menos):
  1. Antes/después en dos fotos (habitación desordenada → burro de ropa).
  2. Comparación partida en vertical con ❌/✅ («Oculta todo lo bueno» vs
     «Muestra las partes más atractivas»: ropa de hombre).
  3. Captura falsa de red social o chat (post de Facebook «Chicos… aprovechad»,
     WhatsApp «¿qué perfume usas?») y en la 2 el producto.
  4. Guía editorial de cosmética: fondo crema, titular serif con palabra en
     cursiva de color, viñetas pequeñas, producto con flechas de ingredientes.
  5. Ilustración tipo cómic/Pixar (chica con la colada) — solo 1-2.
- **Texto**: poco, 1-2 frases por foto, en primera persona y coloquial, con
  1-2 emojis (😅🤣😍👀). Letra del propio TikTok: blanca con contorno o
  **negra sobre píldora blanca** (la más usada), centrada en el tercio medio o
  abajo. En las guías de cosmética, serif editorial arriba.
- **Producto**: aparece SIEMPRE en la última foto y suele ser foto de estilo
  «real» hecha con IA (mano sujetándolo en la calle, burro montado en un
  dormitorio, bolso + paraguas en París/Londres). Las fotos están etiquetadas
  como IA («Creator labeled as AI-generated»).
- **Precio**: lo mete a veces («Suele costar 22 €…», «¿Unos jeans por 44 €?») y
  usa «Revisa tu cupón descuento…» en la portada fijada. **Nosotros no**: sin
  precios y cupones solo sugeridos («revisa si tienes cupones»).
- **Productos**: moda (sudaderas, jeans, pack de camisetas, bolsos, paraguas),
  hogar (tendederos/burros de ropa), cosmética (Medicube, Nivea), perfumes
  árabes, limpiador de zapatillas, libros. Productos baratos y de compra por
  impulso. Caption casi siempre vacío; música de tendencia.

## Cómo lo aplicamos

1. Mismo producto que su carrusel (el `product_id` sale del ancla del post en
   la web MÓVIL de TikTok, ver `learnings.md`), mismo papel por diapositiva,
   otro ambiente, otras personas y texto reescrito (nunca literal).
2. 2-3 diapositivas como él; letra `pildora` o `tiktok` a media altura salvo
   las guías editoriales (`elegante` arriba).
3. Fuera: niños (sus carruseles de libros infantiles muestran críos), capturas
   con nombres reales, precios y cupones afirmados.

## Lo que costó en Flow (oct 2026)

- Flow rechaza por política algunas referencias (paraguas, perfumes, pijama de
  encaje) y escenas íntimas o de coqueteo, aunque no lleven referencia. Se
  genera sin referencia y con el producto descrito al detalle, y se compara
  con la ficha. Si no sale idéntico, el carrusel se descarta.
- «no brand logos» hace que Flow borre la marca del PROPIO producto (Monster,
  medicube). Hay que pedir que se mantenga, y prohibir solo los logos ajenos.
- Describir un emblema como «swoosh» saca el logo de Nike. Hay que nombrar la
  forma real (p. ej. el planeta con anillo).
- Una sola foto en la ficha = un solo color. No inventar variantes.
- Salud y belleza: textos de rutina y uso, sin promesas («sin poros», «como
  nuevas», «líneas»). En ámbar si la foto sugiere un antes/después.
- Semáforo por carrusel: `semaforo_tanda(id="car|<id>")`. Si resubes una
  diapositiva, vuelve a «sin revisar».
