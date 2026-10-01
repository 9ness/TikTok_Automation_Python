# Plan Multimodo · cuenta de Ana · Q4 2026

> Hecho el 1 oct 2026 leyendo Redis y el Drive (solo lectura). Fuente de verdad del
> trabajo de cada día: este fichero + `src/agente_mcp/guias/moda-mujer-multimodo.md`.
> Una tanda = un día de publicación (10 vídeos). Tanda 6 → 2 oct, y así seguido.

## 1. Dónde estamos (1 oct)

- **67 vídeos montados en 7 tandas**, 47 subidos, 3 sin stock (puestos 24, 33, 37).
- Tanda 5: los puestos 44 (HOBIBEAR barefoot retro) y 45 (bolso negro de hombro) no
  se subieron porque el enlace no corresponde. Se quedan así.
- Tanda 6: 2/10 subidos → se termina el **2 oct**. Tanda 7: 7 hechos, faltan 3 → **3 oct**.
- Reparto hasta hoy: 21 bolsos, 20 botas, 12 zapatillas/zapatos y **solo 14 de ropa**.
  Sin estrenar: Maniquí, Sarcástica, Zapatos Multi Escena y los dos 🎙️ de 20 s.
  Ninguno lleva todavía la flecha ➡️.

## 2. Problemas encontrados y qué se ha hecho

**Rótulos con mes.** «Colección de Otoño · la elegancia de septiembre» salía en los
bolsos. Ya publicados: 41 y 50 (nada que hacer). **Pendientes de subir: 60, 63 y 67**
→ hay que remontarlos tras el despliegue: bajar su clip de Magnific (`/app/api/creations`,
por prompt) o regenerarlo, y `subir_clip` otra vez (el vídeo conserva su puesto).
Mientras tanto, si toca publicarlos, mejor saltarlos al final de su tanda.

**Cambios en `src/nicho_ropa/config.py` (pendientes de desplegar):**
- Rótulos **por temporada** según el día en que se PUBLICARÁ (hoy + 3): otoño hasta el
  31 oct (Halloween 🎃 solo si se publica del 10 al 31), **invierno** del 1 al 30 nov,
  **Navidad** del 1 dic al 6 ene. Ningún rótulo lleva un mes. Invierno y Navidad
  llevan sus emojis (❄️ 🤍 ☕ 🎄 ✨ 🎁) en vez de las hojas.
- Espejo Multi Escena y Zapatos POV ya no llevan todos «AUTUMN · cozy season»: 3-4
  frases por temporada.
- **Música**: cada formato tiene ahora 3-4 estilos (pop de tendencia, indie, folk,
  dream pop, house, jazz, bossa nova, francesa, pop de los 60, soul/funk 70s, country,
  folk rock, blues, r&b, lo-fi…) y a cada vídeo le toca uno; más una búsqueda de
  temporada (otoño / Halloween / invierno / Navidad). En las tandas de abajo: 92
  búsquedas distintas en 204 vídeos (antes, 3-4 por formato). La app la enseña sola
  en «🎵» de cada fila; la de la tabla es la que saldrá ese día.

**Productos repetidos.** El catálogo de la web repite producto entre carpetas (a
veces el mismo, a veces otro color). Ya publicados dos veces: bolso de cera (puestos
29 y 48) y hobo de cuero (25 y 41). En las tandas pendientes no hay repetidos. Para
lo que viene, cada producto sale UNA vez; la lista de lo que se descarta está al final.

## 3. Reglas de cada tanda nueva

- **Mezcla**: 5-6 ropa · 4 calzado (1 zapatilla muda, 1 botín, 1 bota alta y 1 🎙️ de
  20 s) · 1 bolso cada dos tandas mientras queden (solo hay 5).
- **Formatos**: ropa alterna 🪞 Espejo ↔ 🎞️ Espejo Multi Escena (con Lucía);
  camisetas → 🧍 Maniquí; zapatillas alternan 👟 Espejo ↔ 👀 POV; botines 🍂 Botas 1 ↔
  2; botas altas 🍂 Largas 1 ↔ 2; bolsos 1 → 2 → 3.
- **🎙️ 20 s**: uno por tanda, alternando 🎙️ POV (zapatillas y botines) ↔ 🎙️ Sentado
  (botas altas). Dos imágenes en Flow, dos clips de 10 s en Magnific, ambos mudos; la
  app escribe el guion, locuta con Fish y monta al subir el clip 2. El **primero que
  se monte se enseña al operador** antes de seguir.
- **➡️ Flecha** (prueba): 3 por tanda (1 de cada 3), repartida entre Multi Escena,
  calzado/bolso y otra ropa. Solo si abajo el fondo está despejado al final del clip;
  si no, sin flecha y se pasa a otro de la tanda. Los 🎙️ ya la llevan.
- **Fuera**: `mm_zapatos_escenas` (la imagen va de ingrediente → vídeo en Flow, y el
  vídeo va siempre en Magnific), `mm_sarcastica` (ninguna camiseta lleva frase), gafas.
- **Imágenes** en Google Flow (Nano Banana 2) · **clips** en Magnific (Kling 2.5, 10 s,
  720p, de 2 en 2). Revisión fotograma a fotograma antes de subir.
- **Orden de montaje = orden de la tanda.** La app fija el orden la primera vez que
  ve un vídeo: montar las 10 de una tanda y abrir «Vídeos listos» (o `tandas`) antes
  de empezar la siguiente, para que no se mezclen.

## 4. Antes de empezar

1. **Desplegar** el cambio de rótulos y música (antes de montar nada nuevo).
2. **URL del MCP de Ana** (no está en `MCP_URLS.local.md`).
3. **Extraer textos** de las carpetas sin ellos: Ropa C4-C10 y C17, Zapatos C5-C17
   (sin título no hay `tipo_multimodo` fiable ni guion para los 🎙️). Gemini, poco coste.
4. **Importar ZIPs nuevos** de la web del curso (ver § 6): con lo de hoy, el catálogo
   útil se acaba el **23 oct**.

## 5. Octubre — tandas 7 a 28

Fase otoño: entretiempo y otoño mezclados; las prendas más abrigadas, hacia el final.
Del 10 al 31 aparecen solos los rótulos y búsquedas de Halloween.

#### Tanda 7 · sáb 3 oct (completar: ya tiene 7)

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C1·2 | Suéter Corina de punto | 🎞️ Espejo Multi Escena | ➡️ | indie suave y acogedor, vibra de vlog → «bedroom pop chill» | AUTUMN · cozy season |
| Ropa C1·6 | Conjunto deportivo pantalón ancho | 🪞 Espejo |  | pop con actitud, de pasarela casera → «fall aesthetic» |  |
| Ropa C2·1 | Camiseta de rayas Ütopya | 🧍 Maniquí |  | beat minimal de desfile → «minimal house fashion» |  |

#### Tanda 8 · dom 4 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C4·1 | Conjunto beige top manga larga + pantalón | 🪞 Espejo | ➡️ | pop con actitud, de pasarela casera → «main character energy» |  |
| Ropa C2·6 | Conjunto dos piezas estampado retro | 🎞️ Espejo Multi Escena | ➡️ | indie suave y acogedor, vibra de vlog → «aesthetic vlog music» | AUTUMN · cozy season |
| Ropa C5·4 | Pantalón ancho azul marino con cinturón | 🪞 Espejo |  | pop con actitud, de pasarela casera → «catwalk sound» |  |
| Ropa C4·2 | Conjunto estampado porcelana manga larga | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «indie folk acoustic» | AUTUMN LOOK · cozy & chic |
| Ropa C6·1 | Chaqueta de punto crema con capucha | 🪞 Espejo |  | pop con actitud, de pasarela casera → «confident walk song» |  |
| Accesorios C3·4 | Bolso hobo de ante (ciervo) | 👜 Bolso 1 | ➡️ | pop de los 60 con encanto → «retro 60s pop» | Otoño esencial · colección de temporada |
| Zapatos C4·3 | HOBIBEAR barefoot ligeros gris | 👟 Zapatillas Espejo |  | r&b suave → «late night rnb» |  |
| Zapatos C11·8 | Botín de montaña mostaza | 🍂 Botas 1 |  | country y folk vintage → «vintage country aesthetic» | Fall Favorites · must have de otoño |
| Zapatos C10·4 | Bota alta marrón slouch | 🍂 Botas Largas 1 |  | country y folk vintage → «cowboy aesthetic song» | Autumn Boots · cozy season |
| Zapatos C5·2 | Zapatilla-bota mostaza | 🎙️ POV 20s |  | — (voz Fish) |  |

#### Tanda 9 · lun 5 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C7·1 | Falda beige con botones | 🎞️ Espejo Multi Escena | ➡️ | dream pop envolvente → «dreamy indie pop» | FALL EDIT · outfit de temporada |
| Ropa C5·3 | Falda larga azul marino | 🪞 Espejo | ➡️ | pop con actitud, de pasarela casera → «main character energy» |  |
| Ropa C8·1 | Traje gris blazer + pantalón | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «soft indie» | AUTUMN LOOK · cozy & chic |
| Ropa C6·3 | Pantalón blanco ancho | 🪞 Espejo |  | pop con actitud, de pasarela casera → «main character energy» |  |
| Ropa C9·2 | Conjunto cárdigan + pantalón marino | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «soft guitar aesthetic» | AUTUMN · cozy season |
| Ropa C7·2 | Conjunto chaleco y pantalón beige | 🪞 Espejo |  | dance o house ligero de get ready → «autumn lofi» |  |
| Zapatos C6·1 | Zapatilla crema y beige | 👀 Zapatos POV | ➡️ | bossa nova de cafetería → «brazilian jazz chill» | AUTUMN · cozy season |
| Zapatos C12·9 | Botín de ante con hebilla | 🍂 Botas 2 |  | country y folk vintage → «western aesthetic» | Boots Season · cozy vibes |
| Zapatos C11·4 | Bota cowboy alta marrón | 🍂 Botas Largas 2 |  | folk rock de carretera → «fall aesthetic» | Nueva Colección · otoño paso a paso |
| Zapatos C12·8 | Bota cowboy negra | 🎙️ Sentado 20s |  | — (voz Fish) |  |

#### Tanda 10 · mar 6 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C10·1 | Conjunto sudadera + pantalón marino | 🎞️ Espejo Multi Escena | ➡️ | dream pop envolvente → «dreamy indie pop» | AUTUMN LOOK · cozy & chic |
| Ropa C8·2 | Pantalón blanco ancho | 🪞 Espejo | ➡️ | pop pegadizo de tendencia, para enseñar el outfit → «outfit check» |  |
| Ropa C11·1 | Chaqueta ARMONIAS Teresa | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «bedroom pop chill» | AUTUMN · cozy season |
| Ropa C9·5 | Blusa celeste con lazo | 🪞 Espejo |  | pop con actitud, de pasarela casera → «catwalk sound» |  |
| Ropa C14·6 | Vestido Armonias tejano | 🎞️ Espejo Multi Escena |  | dream pop envolvente → «ethereal pop» | AUTUMN · cozy season |
| Accesorios C3·5 | Bolso tote minimalista crema | 👜 Bolso 2 | ➡️ | bossa nova suave → «cozy autumn» | Hojas y café · el bolso que combina con todo |
| Zapatos C7·2 | Zapatilla verde menta | 👟 Zapatillas Espejo |  | r&b suave → «smooth rnb aesthetic» |  |
| Zapatos C13·1 | Botín chelsea marrón | 🍂 Botas 1 |  | blues y guitarra vintage → «slow blues aesthetic» | Otoño esencial · paso a paso |
| Zapatos C13·2 | Bota alta de cordones negra | 🍂 Botas Largas 1 |  | blues y guitarra vintage → «vintage rock ballad» | Fall Favorites · must have de otoño |
| Zapatos C8·2 | Zapatilla trail camel | 🎙️ POV 20s |  | — (voz Fish) |  |

#### Tanda 11 · mié 7 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C15·1 | Vestido Armonias Marta | 🪞 Espejo | ➡️ | pop pegadizo de tendencia, para enseñar el outfit → «fall aesthetic» |  |
| Ropa C10·8 | Camisa marino con lazo | 🎞️ Espejo Multi Escena | ➡️ | dream pop envolvente → «dreamy indie pop» | FALL EDIT · outfit de temporada |
| Ropa C16·1 | Pichi denim Massima Grazia | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «outfit of the day song» |  |
| Ropa C11·5 | Jeans Miss Super | 🎞️ Espejo Multi Escena |  | dream pop envolvente → «ethereal pop» | FALL EDIT · outfit de temporada |
| Ropa C17·1 | Chaqueta pata de gallo | 🪞 Espejo |  | pop con actitud, de pasarela casera → «girly pop aesthetic» |  |
| Ropa C13·6 | Kimono Armonias Loures | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «soft indie» | FALL EDIT · outfit de temporada |
| Zapatos C9·1 | Zapatilla crema trenzada | 👀 Zapatos POV | ➡️ | lo-fi jazz → «study jazz lofi» | FALL VIBES · paso a paso |
| Zapatos C14·3 | Botín militar plataforma | 🍂 Botas 2 |  | country y folk vintage → «western aesthetic» | Nueva Colección · otoño paso a paso |
| Zapatos C14·1 | Bota de caña plisada negra | 🍂 Botas Largas 2 |  | country y folk vintage → «vintage country aesthetic» | Nueva Colección · otoño paso a paso |
| Zapatos C15·1 | Bota alta negra de tacón ancho | 🎙️ Sentado 20s |  | — (voz Fish) |  |

#### Tanda 12 · jue 8 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C18·2 | Gabardina Claudete verde | 🪞 Espejo | ➡️ | dance o house ligero de get ready → «house music get ready» |  |
| Ropa C14·1 | Falda vaquera cargo | 🎞️ Espejo Multi Escena | ➡️ | dream pop envolvente → «ethereal pop» | AUTUMN · cozy season |
| Ropa C19·3 | Cazadora de cuero Lunara | 🪞 Espejo |  | dance o house ligero de get ready → «get ready with me song» |  |
| Ropa C15·2 | Blusa satinada Massima Grazia | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «soft indie» | FALL EDIT · outfit de temporada |
| Ropa C20·3 | Chaleco espiga formal | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «autumn lofi» |  |
| Accesorios C3·6 | TANTOMI bolso de mano elegante | 👜 Bolso 3 | ➡️ | pop de los 60 con encanto → «retro 60s pop» | Autumn Essentials · cozy season |
| Zapatos C10·2 | Zapatilla retro blanca y negra | 👟 Zapatillas Espejo |  | r&b suave → «fall aesthetic» |  |
| Zapatos C15·2 | Botín de hebillas beige | 🍂 Botas 1 |  | soul o funk de los 70 → «autumn lofi» | Otoño a tus pies · nueva temporada |
| Zapatos C16·1 | Bota alta negra de ante | 🍂 Botas Largas 1 |  | blues y guitarra vintage → «vintage rock ballad» | Fall Favorites · must have de otoño |
| Zapatos C11·1 | Zapatilla de ante chocolate | 🎙️ POV 20s |  | — (voz Fish) |  |

#### Tanda 13 · vie 9 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C22·8 | Conjunto chándal Lumiira | 🎞️ Espejo Multi Escena | ➡️ | dream pop envolvente → «ethereal pop» | FALL EDIT · outfit de temporada |
| Ropa C16·5 | Chaleco de punto a rayas | 🪞 Espejo | ➡️ | pop con actitud, de pasarela casera → «main character energy» |  |
| Ropa C23·2 | Blazer pata de gallo Lavender | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «autumn vibes» | AUTUMN · cozy season |
| Ropa C17·3 | Camisa blanca oversize | 🪞 Espejo |  | pop con actitud, de pasarela casera → «main character energy» |  |
| Ropa C24·3 | Suéter canalé manga murciélago | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «bedroom pop chill» | AUTUMN · cozy season |
| Ropa C20·4 | Camisa de rayas Nefe | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «outfit of the day song» |  |
| Zapatos C12·1 | Zapatilla blanca chunky | 👀 Zapatos POV | ➡️ | jazz de cafetería, tranquilo → «coffee shop jazz» | FALL VIBES · paso a paso |
| Zapatos C16·2 | Botín plataforma con cordones | 🍂 Botas 2 |  | blues y guitarra vintage → «blues guitar vintage» | Otoño a tus pies · nueva temporada |
| Zapatos C17·1 | Bota slouch taupe | 🍂 Botas Largas 2 |  | folk rock de carretera → «autumn vibes» | Autumn Edit · step into style |
| Zapatos C10·5 | Bota alta negra de tacón | 🎙️ Sentado 20s |  | — (voz Fish) |  |

#### Tanda 14 · sáb 10 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C25·1 | Pantalón de cuadros | 🎞️ Espejo Multi Escena | ➡️ | indie suave y acogedor, vibra de vlog → «aesthetic vlog music» | FALL EDIT · outfit de temporada |
| Ropa C21·1 | Blusa Miel con volantes | 🪞 Espejo | ➡️ | pop con actitud, de pasarela casera → «autumn vibes» |  |
| Ropa C26·1 | Suéter de punto con volante | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «aesthetic vlog music» | FALL EDIT · outfit de temporada |
| Ropa C22·4 | Camiseta 2 piezas Katia | 🧍 Maniquí |  | deep house de tienda chic → «deep house fashion» |  |
| Ropa C27·3 | Gabardina larga oversize | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «outfit of the day song» |  |
| Accesorios C3·7 | Bolso mini vintage bandolera | 👜 Bolso 1 | ➡️ | pop de los 60 con encanto → «retro 60s pop» | Hojas y café · el bolso que combina con todo |
| Zapatos C4·6 | HOBIBEAR trail running | 👟 Zapatillas Espejo |  | r&b suave → «rnb chill vibe» |  |
| Zapatos C17·2 | Botín blanco de cordones | 🍂 Botas 1 |  | country y folk vintage → «halloween aesthetic» | Pasos de Otoño · botas de temporada |
| Zapatos C12·10 | Bota slouch de tacón fino | 🍂 Botas Largas 1 |  | country y folk vintage → «vintage country aesthetic» | Fall Favorites · must have de otoño |
| Zapatos C5·3 | Zapatilla gris y azul | 🎙️ POV 20s |  | — (voz Fish) |  |

#### Tanda 15 · dom 11 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C28·4 | Jersey YOLANDA | 🎞️ Espejo Multi Escena | ➡️ | dream pop envolvente → «ethereal pop» | FALL EDIT · outfit de temporada |
| Ropa C23·1 | Conjunto deportivo Popilush rojo | 🪞 Espejo | ➡️ | pop con actitud, de pasarela casera → «catwalk sound» |  |
| Ropa C2·5 | Camisa de encaje manga larga burdeos | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «halloween aesthetic» | AUTUMN · cozy season |
| Ropa C24·1 | Pantalón doble franja lateral | 🪞 Espejo |  | dance o house ligero de get ready → «party getting ready» |  |
| Ropa C4·5 | Chaqueta acolchada gris cremallera | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «autumn lofi» | AUTUMN · cozy season |
| Ropa C28·9 | Pantalones anchos lila | 🪞 Espejo |  | pop con actitud, de pasarela casera → «fall aesthetic» |  |
| Zapatos C6·3 | Zapatilla azul agua | 👀 Zapatos POV | ➡️ | jazz de cafetería, tranquilo → «piano jazz morning» | COZY SEASON · mi par favorito |
| Zapatos C11·10 | Botín militar negro con cordones | 🍂 Botas 2 |  | soul o funk de los 70 → «retro funk groove» | Boots Season · cozy vibes |
| Zapatos C13·4 | Bota alta marrón de montar | 🍂 Botas Largas 2 |  | soul o funk de los 70 → «retro funk groove» | Autumn Edit · step into style |
| Zapatos C14·2 | Bota alta marrón con hebilla | 🎙️ Sentado 20s |  | — (voz Fish) |  |

#### Tanda 16 · lun 12 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C6·5 | Blazer de cuadros | 🎞️ Espejo Multi Escena | ➡️ | folk acústico tranquilo → «spooky season» | NUEVA TEMPORADA · otoño con estilo |
| Ropa C29·3 | Pantalones anchos deportivos | 🪞 Espejo | ➡️ | pop con actitud, de pasarela casera → «confident walk song» |  |
| Ropa C7·7 | Chaqueta tweed crema | 🎞️ Espejo Multi Escena |  | dream pop envolvente → «dream pop aesthetic» | AUTUMN · cozy season |
| Ropa C1·10 | Top manga larga cuello V | 🪞 Espejo |  | dance o house ligero de get ready → «pop dance trend» |  |
| Ropa C9·9 | Vestido marino manga larga | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «slow morning vlog» | AUTUMN · cozy season |
| Accesorios C3·9 | Bolso de hombro con flecos | 👜 Bolso 2 | ➡️ | pop de los 60 con encanto → «cozy autumn» | Autumn Mood · tu bolso de temporada |
| Zapatos C7·4 | Zapatilla running lila | 👟 Zapatillas Espejo |  | r&b suave → «late night rnb» |  |
| Zapatos C13·3 | Botín de ante beige | 🍂 Botas 1 |  | soul o funk de los 70 → «70s soul aesthetic» | Otoño a tus pies · nueva temporada |
| Zapatos C15·5 | Bota alta marrón con correa | 🍂 Botas Largas 1 |  | blues y guitarra vintage → «vintage rock ballad» | Boots Season · cozy vibes |
| Zapatos C8·4 | Zapatilla de ante marrón | 🎙️ POV 20s |  | — (voz Fish) |  |

#### Tanda 17 · mar 13 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C10·2 | Cazadora de cuero negra | 🪞 Espejo | ➡️ | pop pegadizo de tendencia, para enseñar el outfit → «autumn lofi» |  |
| Ropa C4·3 | Vestido largo marrón sin mangas | 🎞️ Espejo Multi Escena | ➡️ | dream pop envolvente → «ethereal pop» | AUTUMN LOOK · cozy & chic |
| Ropa C11·2 | Blazer ARMONIAS de cuadros | 🪞 Espejo |  | pop con actitud, de pasarela casera → «girly pop aesthetic» |  |
| Ropa C5·6 | Pantalón azul con botones laterales | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «fall aesthetic» | AUTUMN LOOK · cozy & chic |
| Ropa C14·10 | Conjunto de punto Massima Grazia | 🪞 Espejo |  | pop con actitud, de pasarela casera → «girly pop aesthetic» |  |
| Ropa C6·4 | Camiseta burdeos manga corta | 🧍 Maniquí |  | deep house de tienda chic → «halloween aesthetic» |  |
| Zapatos C9·2 | Zapatilla negra de piel | 👀 Zapatos POV | ➡️ | lo-fi jazz → «spooky season» | COZY SEASON · mi par favorito |
| Zapatos C14·5 | Botín de cordones marrón | 🍂 Botas 2 |  | folk rock de carretera → «folk rock 70s» | Pasos de Otoño · botas de temporada |
| Zapatos C16·3 | Bota de cordones plataforma | 🍂 Botas Largas 2 |  | soul o funk de los 70 → «autumn vibes» | Halloween Vibes · otoño con un toque oscuro |
| Zapatos C17·3 | Bota slouch camel de tacón | 🎙️ Sentado 20s |  | — (voz Fish) |  |

#### Tanda 18 · mié 14 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C15·3 | Vestido velvet de cuadros | 🎞️ Espejo Multi Escena | ➡️ | folk acústico tranquilo → «indie folk acoustic» | FALL EDIT · outfit de temporada |
| Ropa C7·3 | Falda satinada azul | 🪞 Espejo | ➡️ | pop con actitud, de pasarela casera → «autumn lofi» |  |
| Ropa C16·3 | Camiseta cuello vuelto negra | 🧍 Maniquí |  | techno elegante → «dark minimal techno fashion» |  |
| Ropa C17·2 | Pantalón de rayas ancho | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «bedroom pop chill» | AUTUMN LOOK · cozy & chic |
| Ropa C18·4 | Gabardina Odette beige | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «fit check trend» |  |
| Ropa C19·9 | Jersey de rayas holgado | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «spooky season» | AUTUMN · cozy season |
| Zapatos C10·6 | Zapatilla de punto gris | 👟 Zapatillas Espejo |  | lo-fi urbano → «halloween aesthetic» |  |
| Zapatos C15·3 | Botín cowboy negro con tachuelas | 🍂 Botas 1 | ➡️ | blues y guitarra vintage → «spooky season» | Autumn Boots · cozy season |
| Zapatos C13·7 | Bota slouch marrón con hebillas | 🍂 Botas Largas 1 |  | soul o funk de los 70 → «halloween aesthetic» | Autumn Edit · step into style |
| Zapatos C11·6 | Zapatilla camel y negra | 🎙️ POV 20s |  | — (voz Fish) |  |

#### Tanda 19 · jue 15 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C20·5 | Falda Arena con botones | 🪞 Espejo | ➡️ | pop con actitud, de pasarela casera → «girly pop aesthetic» |  |
| Ropa C8·9 | Vestido azul marino manga campana | 🎞️ Espejo Multi Escena | ➡️ | indie suave y acogedor, vibra de vlog → «bedroom pop chill» | AUTUMN LOOK · cozy & chic |
| Ropa C23·3 | Pantalón ancho efecto piel | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «fashion trending sound» |  |
| Ropa C24·4 | Chaqueta estampado animal | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «soft indie» | NUEVA TEMPORADA · otoño con estilo |
| Ropa C25·3 | Conjunto chaleco de punto + camisa | 🪞 Espejo |  | dance o house ligero de get ready → «get ready with me song» |  |
| Ropa C26·3 | Jersey liso crema | 🎞️ Espejo Multi Escena |  | dream pop envolvente → «dream pop aesthetic» | AUTUMN LOOK · cozy & chic |
| Zapatos C4·9 | HOBIBEAR correr punta ancha | 👀 Zapatos POV | ➡️ | bossa nova de cafetería → «spooky season» | AUTUMN · cozy season |
| Zapatos C16·4 | Botín de ante con anilla | 🍂 Botas 2 |  | soul o funk de los 70 → «retro funk groove» | Nueva Colección · otoño paso a paso |
| Zapatos C14·4 | Bota alta con hebilla gris | 🍂 Botas Largas 2 |  | soul o funk de los 70 → «old vinyl aesthetic» | Otoño esencial · paso a paso |
| Zapatos C15·6 | Bota alta cognac con hebilla | 🎙️ Sentado 20s |  | — (voz Fish) |  |

#### Tanda 20 · vie 16 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C27·5 | Conjunto Alba de suéter | 🪞 Espejo | ➡️ | dance o house ligero de get ready → «get ready with me song» |  |
| Ropa C10·10 | Conjunto top + pantalón campana marrón | 🎞️ Espejo Multi Escena | ➡️ | folk acústico tranquilo → «autumn lofi» | NUEVA TEMPORADA · otoño con estilo |
| Ropa C28·5 | Camiseta cuello alto volantes | 🧍 Maniquí |  | techno elegante → «model walk beat» |  |
| Ropa C2·9 | Blazer Mariana corte recto | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «outfit check» |  |
| Ropa C6·9 | Gabardina-vestido camisero beige | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «cozy autumn» | AUTUMN · cozy season |
| Ropa C7·8 | Jersey marrón con pañuelo | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «autumn lofi» |  |
| Zapatos C5·6 | Zapatilla crema caña media | 👟 Zapatillas Espejo |  | r&b suave → «late night rnb» |  |
| Zapatos C13·5 | Botín negro de punta | 🍂 Botas 1 | ➡️ | soul o funk de los 70 → «70s soul aesthetic» | Otoño a tus pies · nueva temporada |
| Zapatos C16·6 | Bota alta de cordones camel | 🍂 Botas Largas 1 |  | country y folk vintage → «vintage country aesthetic» | Boots Season · cozy vibes |
| Zapatos C6·5 | Zapatilla alta vaquera azul | 🎙️ POV 20s |  | — (voz Fish) |  |

#### Tanda 21 · sáb 17 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C10·3 | Conjunto jersey cuello alto + pantalón | 🎞️ Espejo Multi Escena | ➡️ | indie suave y acogedor, vibra de vlog → «aesthetic vlog music» | FALL EDIT · outfit de temporada |
| Ropa C13·10 | Falda cargo Massima Grazia Telma | 🪞 Espejo | ➡️ | pop con actitud, de pasarela casera → «confident walk song» |  |
| Ropa C11·4 | Chaqueta ARMONIAS de polipiel | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «fall aesthetic» | AUTUMN · cozy season |
| Ropa C15·5 | Jersey cuello Massima Grazia | 🪞 Espejo |  | pop con actitud, de pasarela casera → «girly pop aesthetic» |  |
| Ropa C16·4 | Falda animal print | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «witchy vibes» | AUTUMN · cozy season |
| Ropa C17·4 | Cárdigan de rayas | 🪞 Espejo |  | pop con actitud, de pasarela casera → «catwalk sound» |  |
| Zapatos C7·6 | Zapatilla lila de tela | 👀 Zapatos POV | ➡️ | lo-fi jazz → «lofi jazz» | AUTUMN · cozy season |
| Zapatos C15·9 | Botín cuña plataforma marrón | 🍂 Botas 2 |  | folk rock de carretera → «cozy autumn» | Autumn Edit · step into style |
| Zapatos C13·8 | Bota motera con tachuelas | 🍂 Botas Largas 2 |  | soul o funk de los 70 → «halloween aesthetic» | Nueva Colección · otoño paso a paso |
| Zapatos C14·9 | Bota mosquetera de ante beige | 🎙️ Sentado 20s |  | — (voz Fish) |  |

#### Tanda 22 · dom 18 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C18·7 | Gabardina larga Útopya | 🎞️ Espejo Multi Escena | ➡️ | indie suave y acogedor, vibra de vlog → «cozy autumn» | AUTUMN · cozy season |
| Ropa C14·4 | Jeans Laulia wide leg | 🪞 Espejo | ➡️ | pop con actitud, de pasarela casera → «spooky season» |  |
| Ropa C23·6 | Cárdigan argyle | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «witchy vibes» | AUTUMN · cozy season |
| Ropa C24·5 | Pantalón bombacho animal print | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «fit check trend» |  |
| Ropa C25·4 | Chaleco de punto con lazos | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «fall aesthetic» | AUTUMN LOOK · cozy & chic |
| Ropa C27·10 | Camiseta manga larga con botones | 🧍 Maniquí |  | techno elegante → «model walk beat» |  |
| Zapatos C8·9 | Zapatilla blanca suela roja | 👟 Zapatillas Espejo |  | lo-fi urbano → «autumn lofi» |  |
| Zapatos C16·7 | Botín calcetín de tacón | 🍂 Botas 1 | ➡️ | folk rock de carretera → «halloween aesthetic» | Autumn Boots · cozy season |
| Zapatos C15·7 | Bota alta negra plataforma | 🍂 Botas Largas 1 |  | soul o funk de los 70 → «70s soul aesthetic» | Fall Favorites · must have de otoño |
| Zapatos C9·6 | Zapatilla retro negra franjas | 🎙️ POV 20s |  | — (voz Fish) |  |

#### Tanda 23 · lun 19 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C2·10 | Poncho Valentina drapeado | 🪞 Espejo | ➡️ | pop con actitud, de pasarela casera → «main character energy» |  |
| Ropa C15·4 | Camisa Armonias Mara | 🎞️ Espejo Multi Escena | ➡️ | dream pop envolvente → «halloween aesthetic» | FALL EDIT · outfit de temporada |
| Ropa C6·10 | Conjunto burdeos estampado manga larga | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «outfit of the day song» |  |
| Ropa C7·9 | Chaleco de punto crochet | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «soft guitar aesthetic» | AUTUMN LOOK · cozy & chic |
| Ropa C10·6 | Cazadora verde oliva | 🪞 Espejo |  | pop con actitud, de pasarela casera → «girly pop aesthetic» |  |
| Ropa C11·9 | Chaqueta Armonias Renata | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «halloween aesthetic» | AUTUMN · cozy season |
| Zapatos C10·9 | Zapatilla retro marrón | 👀 Zapatos POV | ➡️ | lo-fi jazz → «witchy vibes» | COZY SEASON · mi par favorito |
| Zapatos C13·6 | Botín cowboy taupe | 🍂 Botas 2 |  | country y folk vintage → «witchy vibes» | Nueva Colección · otoño paso a paso |
| Zapatos C16·9 | Bota alta marrón plataforma | 🍂 Botas Largas 2 |  | country y folk vintage → «vintage country aesthetic» | Nueva Colección · otoño paso a paso |
| Zapatos C13·10 | Bota calcetín plataforma | 🎙️ Sentado 20s |  | — (voz Fish) |  |

#### Tanda 24 · mar 20 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C15·8 | Blazer de pana Massima Grazia | 🪞 Espejo | ➡️ | dance o house ligero de get ready → «pop dance trend» |  |
| Ropa C16·7 | Blusa acampanada | 🎞️ Espejo Multi Escena | ➡️ | dream pop envolvente → «dream pop aesthetic» | FALL EDIT · outfit de temporada |
| Ropa C16·8 | Vestido oversize morado | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «fit check trend» |  |
| Ropa C17·9 | Chaqueta negra con cinturón | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «soft indie» | AUTUMN · cozy season |
| Ropa C23·8 | Cárdigan de punto a rayas | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «outfit check» |  |
| Ropa C24·7 | Suéter con lazos en la manga | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «spooky season» | FALL EDIT · outfit de temporada |
| Zapatos C4·10 | HOBIBEAR barefoot caña alta | 👟 Zapatillas Espejo |  | r&b suave → «smooth rnb aesthetic» |  |
| Zapatos C13·9 | Botín chelsea plataforma negro | 🍂 Botas 1 | ➡️ | folk rock de carretera → «spooky season» | Nueva Colección · otoño paso a paso |
| Zapatos C14·10 | Bota motera negra | 🍂 Botas Largas 1 |  | blues y guitarra vintage → «vintage rock ballad» | Otoño esencial · paso a paso |
| Zapatos C5·7 | Zapatilla negra suela crepe | 🎙️ POV 20s |  | — (voz Fish) |  |

#### Tanda 25 · mié 21 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C17·10 | Gabardina beige | 🪞 Espejo | ➡️ | dance o house ligero de get ready → «house music get ready» |  |
| Ropa C20·9 | Camisa de rayas Afra | 🎞️ Espejo Multi Escena | ➡️ | indie suave y acogedor, vibra de vlog → «soft indie» | NUEVA TEMPORADA · otoño con estilo |
| Ropa C23·10 | Pantalón de punto ancho | 🪞 Espejo |  | dance o house ligero de get ready → «party getting ready» |  |
| Ropa C24·8 | Jogger baggy de cuadros | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «indie folk acoustic» | AUTUMN LOOK · cozy & chic |
| Ropa C24·9 | Falda midi de cuadros | 🪞 Espejo |  | pop con actitud, de pasarela casera → «autumn lofi» |  |
| Ropa C21·3 | Blusa Ares con lazo | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «halloween aesthetic» | AUTUMN · cozy season |
| Zapatos C6·7 | Zapatilla trekking marrón | 👀 Zapatos POV | ➡️ | lo-fi jazz → «cozy autumn» | COZY SEASON · mi par favorito |
| Ropa C22·7 | Blusa Angela escote pico | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «soft indie» | FALL EDIT · outfit de temporada |
| Ropa C28·10 | Conjunto deportivo gris | 🎞️ Espejo Multi Escena |  | dream pop envolvente → «ethereal pop» | AUTUMN · cozy season |
| Ropa C5·8 | Falda negra con cordón | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «cozy autumn» | AUTUMN LOOK · cozy & chic |

#### Tanda 26 · jue 22 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C6·6 | Pantalón azul con flor | 🪞 Espejo | ➡️ | pop pegadizo de tendencia, para enseñar el outfit → «fashion trending sound» |  |
| Ropa C7·5 | Camisa celeste | 🎞️ Espejo Multi Escena | ➡️ | dream pop envolvente → «dream pop aesthetic» | AUTUMN · cozy season |
| Ropa C14·5 | Pantalón Armonias combinado | 🪞 Espejo |  | pop con actitud, de pasarela casera → «spooky season» |  |
| Ropa C15·6 | Blusa Armonias estampada | 🎞️ Espejo Multi Escena |  | folk acústico tranquilo → «halloween aesthetic» | NUEVA TEMPORADA · otoño con estilo |
| Ropa C16·9 | Jeans ARMONIAS corte recto | 🪞 Espejo |  | dance o house ligero de get ready → «witchy vibes» |  |
| Ropa C20·10 | Pantalón Agnes elegante | 🎞️ Espejo Multi Escena |  | dream pop envolvente → «fall aesthetic» | AUTUMN LOOK · cozy & chic |
| Zapatos C7·10 | Zapatilla verde caqui | 👟 Zapatillas Espejo |  | r&b suave → «late night rnb» |  |
| Zapatos C8·10 | Zapatilla beige ante | 🎙️ POV 20s |  | — (voz Fish) |  |
| Ropa C21·4 | Falda Lupe | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «spooky season» | AUTUMN LOOK · cozy & chic |
| Ropa C22·9 | Blusa Lumiira cuello de flor | 🎞️ Espejo Multi Escena |  | dream pop envolvente → «halloween aesthetic» | FALL EDIT · outfit de temporada |

#### Tanda 27 · vie 23 oct

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Ropa C5·10 | Falda satinada estampada | 🪞 Espejo | ➡️ | pop pegadizo de tendencia, para enseñar el outfit → «outfit check» |  |
| Ropa C7·6 | Falda verde estampada | 🎞️ Espejo Multi Escena | ➡️ | indie suave y acogedor, vibra de vlog → «witchy vibes» | AUTUMN LOOK · cozy & chic |
| Ropa C14·7 | Falda vaquera larga Laulia Ávila | 🪞 Espejo |  | pop pegadizo de tendencia, para enseñar el outfit → «spooky season» |  |
| Ropa C15·7 | Falda vaquera Laulia | 🎞️ Espejo Multi Escena |  | dream pop envolvente → «dreamy indie pop» | AUTUMN · cozy season |
| Ropa C21·7 | Camisa blanca Priscilla | 🪞 Espejo |  | dance o house ligero de get ready → «autumn lofi» |  |
| Ropa C14·8 | Jeans Armonias ruedo | 🎞️ Espejo Multi Escena |  | indie suave y acogedor, vibra de vlog → «bedroom pop chill» | AUTUMN · cozy season |
| Zapatos C9·8 | Zapatilla beige fruncida | 👀 Zapatos POV | ➡️ | jazz de cafetería, tranquilo → «coffee shop jazz» | AUTUMN · cozy season |
| Ropa C14·9 | Conjunto Armonias Aire | 🎞️ Espejo Multi Escena |  | dream pop envolvente → «ethereal pop» | AUTUMN LOOK · cozy & chic |
| Zapatos C4·8 | HOBIBEAR senderismo caña alta | 👀 Zapatos POV |  | bossa nova de cafetería → «cozy autumn» | FALL VIBES · paso a paso |
| Zapatos C6·10 | Zapatilla blanca franja granate | 👀 Zapatos POV |  | lo-fi jazz → «autumn lofi» | FALL VIBES · paso a paso |

#### Tanda 28 · sáb 24 oct (solo 1: se acaba el catálogo)

| Producto | Qué es | Formato | ➡️ | 🎵 Música (estilo → búsqueda) | Rótulo |
|---|---|---|:-:|---|---|
| Zapatos C9·10 | Zapatilla camel de ante | 👟 Zapatillas Espejo |  | r&b suave → «smooth rnb aesthetic» |  |

### 24-31 oct (resto de la tanda 28 y tandas 29-35, ~79 vídeos): hueco

Con lo que hay no llega. Por orden de preferencia:
1. Productos de los ZIP nuevos (otoño-invierno).
2. Adelantar la reserva de invierno (abajo): abrigos y botas forradas publicados a
   finales de octubre funcionan; el rótulo aún sale de otoño.
3. HOBIBEAR casi idénticos (34 en reserva): como mucho 1 por tanda.

## 6. Noviembre y diciembre

**Noviembre (tandas 36-65) — invierno y previa de Black Friday.** Rótulo de invierno
automático desde el 1 nov. Abrigo, plumífero, punto grueso, botas forradas, bufandas,
bolsos de invierno. Campañas: Front Run 11-17 nov, Mid 18-24, **Peak 25-29** (vie 27),
Cyber Monday 30. El rótulo NO promete descuentos (sancionan); el ángulo es «para el
frío / de temporada». Más 🎙️ de 20 s si funcionan los primeros.

Reserva de invierno (17): Ropa C4·4 Abrigo negro largo · Ropa C4·6 Abrigo de pelo crema · Ropa C4·7 Chaleco acolchado con capucha · Ropa C7·4 Abrigo gris cruzado · Ropa C8·5 Abrigo de pelo a rayas marrón · Ropa C11·6 Chaqueta Armonias Amelie de pelo · Ropa C17·6 Abrigo de pelo marrón · Ropa C17·8 Chaleco acolchado rojo · Ropa C18·9 Abrigo London clásico · Ropa C20·8 Vestido de punto Margaret · Ropa C21·9 Jersey cuello alto Ütopya · Ropa C23·5 Chaqueta de punto con cremallera · Zapatos C14·7 Botín forrado de pelo mostaza · Zapatos C15·10 Botín forrado blanco · Zapatos C16·5 Botín chelsea blanco forrado · Zapatos C4·7 HOBIBEAR botas de nieve · Accesorios C3·10 Bolso acolchado impermeable.

**Diciembre (tandas 66-96) — Navidad y fiesta.** Rótulo navideño automático del
1 dic al 6 ene («Holiday Season», «Ideas de regalo»…). Terciopelo, brillo,
lentejuelas, rojo, botas de pelo, bolsos de fiesta.

Reserva de fiesta (19): Ropa C7·10 Chaqueta tweed blanca ribeteada · Ropa C8·6 Blusa negra transparente con volantes · Ropa C10·5 Vestido de punto burdeos manga larga · Ropa C11·3 Vestido ARMONIAS de encaje rojo · Ropa C15·9 Poncho de terciopelo · Ropa C15·10 Vestido de terciopelo · Ropa C16·2 Falda plisada Armonias Brillo · Ropa C16·6 Chaqueta de terciopelo · Ropa C18·5 Vestido Stella negro · Ropa C18·8 Falda larga brillo violeta · Ropa C19·5 Falda Nilsa estampado oriental · Ropa C19·6 Vestido largo negro manga larga · Ropa C19·10 Vestido corto brillo rojo · Ropa C20·6 Vestido Bardot crema · Ropa C20·7 Falda midi brillo Anabel · Ropa C24·6 Jersey rojo con volantes · Zapatos C7·8 Zapatilla roja de ante · Zapatos C14·8 Botas de pelo rojas · Zapatos C16·8 Bota de cordones de tacón.

Hacen falta **~600 productos nuevos** para nov-dic a 10/día (más ~70 para el final de octubre): pide en la web del curso
los ZIP nuevos de Ropa Mujer, Zapatos Mujer y Accesorios Mujer (sobre todo **bolsos**,
que se acaban en la tanda 16) y se importan como siempre. Cuando entren, se clasifican
igual (invierno / fiesta) y se completa este plan.

## 7. Descartes (no se hacen)

VERANO: R1.5 R1.8 R2.2 R2.3 R2.4 R2.7 R2.8 R4.8 R4.9 R4.10 R5.1 R5.2 R5.5 R5.7 R5.9 R6.2 R6.7 R8.3 R8.4 R8.7 R8.8 R8.10 R9.1 R9.3 R9.6 R9.7 R9.8 R9.10 R10.4 R10.7 R10.9 R11.7 R11.8 R11.10 R12.* R13.1-5 R13.7-9 R14.2 R14.3 R19.1 R20.1 R21.2 R21.5 R21.6 R21.8 R22.2 R22.3 R24.2 R24.10 R25.2 R25.5-10 R26.2 R26.4-10 R27.1 R27.6 R28.2 R28.6 R29.1 R29.2 R29.4-7 · Z2.8 (sandalia de cuña)
DUPLICADOS (se hace UNO): R27.7=R4.1 · R6.8=R4.3 · R23.4=R4.5 · R23.7=R4.6 · R23.9=R4.7 · R25.9=R5.3 · R25.2=R5.6 · R25.6=R5.8 · R29.5=R5.10 · R9.4=R19.8=R6.6 · R21.10=R7.1 · R18.1=R7.7 · R22.6=R7.9 · R20.2=R8.9 · R19.2=R9.2 · R18.3=R10.1 · R18.10=R10.2 · R18.6=R10.3 · R19.4=R10.6 · R16.10=R11.2 · R22.1=R17.7 · R22.5=R2.1 · R28.3=R2.10 · R28.7=R28.8 · R27.1=R28.2 · R26.5=R5.1
YA PUBLICADOS en otra carpeta: R26.8 y R27.2 (=Conjunto Palermo, R3.9) · R13.5 (Palermo fucsia) · R27.4 (=R3.8) · R27.9 (=R3.7) · R28.1 (=R3.4) · R27.8 (≈R3.6, dudoso) · A3.8 (=A1.6 YOHI) · Z11.9 (=Z3.5) · Z12.3 (=Z3.4) · Z12.4 (≈Z3.1) · Z12.6 (=Z1.10) · Z12.7 (≈Z1.6)
YA EN TANDAS PENDIENTES: Z12.2 (=Z3.6, puesto 53) · Z16.10 (=Z2.6, puesto 61) · Z12.5 (≈Z2.1, puesto 59) · Z5.1 (=Z4.5, puesto 44)
REPETIDOS DENTRO DE ZAPATOS: Z4.4=Z4.3 · Z14.6=Z14.5 · Z15.4=Z15.3 · Z15.8=Z15.6 · Z9.7=Z9.6
HOBIBEAR casi idénticos (no se usan, saturarían): Z5.4 Z5.5 Z5.8 Z5.9 Z5.10 Z6.2 Z6.4 Z6.6 Z6.8 Z6.9 Z7.1 Z7.3 Z7.5 Z7.7 Z7.9 Z8.1 Z8.3 Z8.5 Z8.6 Z8.7 Z8.8 Z9.3 Z9.4 Z9.5 Z9.9 Z10.1 Z10.3 Z10.7 Z10.8 Z10.10 Z11.2 Z11.3 Z11.5 Z11.7 (reserva si falta calzado)
OTROS: R1.9 (la foto limpia es una captura) · A1.1/A1.2 gafas
