# Cuenta árabe (Mi 8) y usuario web `nes_bugallo`

> Decidido con Néstor el 29/10/2026. Socio: **Bugallo** (usuario web `nes_bugallo`, nombre visible «Ness/Bugallo»).
> Informe del nicho con los datos (ventas, ritmo, cara/sin cara):
> Drive `TIKTOK_SHOP_AI_PRO/_agente/nestor2/NICHO_ARABE_ES_2026-10-28.md`.
> Lista de productos: Drive `TIKTOK_SHOP_AI_PRO/_agente/nestor2/arabe/PRODUCTOS_ARABE.md`.

## 1. Qué es

Una cuenta antigua de TikTok Shop España (como la de Viva Shop): Néstor le cambia
el nombre y la foto. Va dirigida al **público árabe/magrebí** de España y Europa.
TikTok reparte cada publicación por su idioma: un carrusel con texto en francés
fue en más de un 85 % a Francia.

| | |
|---|---|
| Móvil | **Xiaomi Mi 8** (ADB por Tailscale `100.115.12.26:5555`, 1080x2248, MIUI, Android 10) |
| Formatos | Carruseles de fotos con **precio** + vídeos **POV sin cara** (mano enseñando el producto) |
| Ritmo | Primeros días: 15 carruseles + 5-10 vídeos. Después **45 carruseles + 10 vídeos/día**. Más adelante, 20 vídeos |
| Horario | Subida automática desde las **00:00**: primero los carruseles, luego los vídeos |
| Presupuesto noviembre | 22-25 € (300 cr de GenAI Pro = 8 €; Veo = 1 cr por clip) |
| Objetivo | ~10.000 € de ventas en noviembre (Black Friday). Si deja ~1.000 € de comisión, en diciembre se reinvierte (Genjutsu, más cuentas, avatar para vídeos largos) |

El Mi 8 **también lo usa el agente de stock** (`scripts/stock_tiktok_movil.py`)
y la cuenta servirá para buscar vídeos y stock. Las subidas van de noche y el
resto de trabajos fuera de esa franja. Nunca a la vez: comprueba antes que no hay
otro proceso con el móvil:
`ps -eo pid,etime,args | grep -E "stock_tiktok|subir_" | grep -v grep`.

## 2. Regla de oro: el estilo es el de ELLOS

**No se ponen nuestros textos de venta ni nuestro estilo** (rótulos con brillo,
«CUPÓN DESCUENTO», «APROVECHA AHORA»…). Se miran los textos y el estilo visual
que les funcionan a las tiendas árabes que venden (oujdia, chef.nadia,
saritasara, beldi…) y **se replican tal cual**. Como mucho se añade un plus
visual encima. Lo calibrado para España no vale para este público (Néstor,
29/10).

Lo que llevan ellos (visto en el Mi 8):
- **Texto**: el nombre del producto en español, una frase en darija o árabe
  («بثمن همزة» = a precio de ganga, «لطلب من هنا 👇» = pídelo aquí) y el
  **precio**. Mezclan los dos alfabetos en la misma línea.
- **Hashtags árabes**: `#إسبانيا🇪🇸_ايطاليا🇮🇹_البرتغال #فرنسا🇨🇵_بلجيكا🇧🇪_المانيا🇩🇪 #المغرب🇲🇦تونس🇹🇳الجزائر🇩🇿`
  más `#tiktokshop #oferta`.
- **Vídeos**: mano o percha con el producto, sin cara ni voz, con música o
  sonido ambiente. Duran 23-74 s. Los que venden suben 12-16 vídeos al día.

**Texto mixto (español + árabe + números): ya se pinta bien** (`src/texto_arabe.py`):
- Con árabe se usa la fuente **Tajawal**, que también trae letras latinas.
- La línea se lee en el sentido de su primera letra.
- Los números, los precios y los trozos latinos van aislados: «39,90 €» y
  «24-48h» no se desordenan, y el 👇 sale en el lado bueno.

Lo usan el bloque de texto del POV y las fotos de los carruseles.
**Revisa siempre la imagen**: que se lea el precio y que todo quede dentro de la
zona segura (`x 0.05-0.78`, `y 0.15-0.75`).

## 3. Carruseles

1. Busca un carrusel viral de una tienda árabe (las de arriba, más las que
   encuentre el agente de carruseles en otros países).
2. `replicar_carrusel(..., url=<viral>, pais="AR")`. El país `AR` es la cuenta
   árabe:
   - Copia el idioma y la mezcla del original: si mezcla español y darija,
     igual; si solo usa español, solo español.
   - Pone el **precio de nuestra ficha** donde el original lleva el suyo.
   - Los hashtags de TikTok son los árabes fijos (`HASHTAGS_ARABE` en
     `src/replicar_viral/carrusel.py`) más 3 de la IA.
3. Imágenes en Flow, `subir_imagen_carrusel`, semáforo, como siempre (guía
   `replicar-carrusel.md`).
4. Producto del carrusel **en el escaparate** de la cuenta árabe antes de
   subirlo.

## 4. Vídeos POV (sin cara)

Se hacen con **«Replicar virales» en modo `con_ia`** (guía
`replicar-virales.md`; MCP `registrar_replica_video`). Así el agente rehace el
vídeo de referencia **con sus textos, su estilo y su sonido**, sin pasar por el
rótulo del POV BOF.

- **Clips**: Veo en GenAI Pro (1 cr cada uno), 8 s por clip.
  - Prueba A/B: 1 clip (8 s) contra 2-3 clips (16-24 s).
  - Mano o percha con el producto, como en el original.
- **Texto**: el del vídeo de referencia, con nuestro producto y precio. Para
  quemarlo, `texto_foto.quemar` o `video_editor._render_text_line`, que ya
  pintan árabe.
- **Sonido**: ambiente realista de Veo o un sonido árabe de la biblioteca de
  TikTok al subir. Con producto enlazado, TikTok solo deja «Sonidos
  comerciales». **Nada de música con copyright**; ojo con Omni, que mete
  sirenas y pitidos que TikTok silencia (`learnings.md`).
- **Anti-sanción** (obligatorio):
  - el nombre del producto, en pantalla;
  - `limpiar_metadatos`;
  - subtítulos solo si hay voz.
- **Semáforo** antes de darlo por hecho; nada de niños; nunca afirmar cupones.
- Se registra con `para="nes_bugallo"` para que no se mezcle con las tandas de
  Néstor. Ya funciona vía `carrusel.destino()`.

## 5. Subida automática desde el Mi 8 (PENDIENTE)

Se hace cuando la cuenta esté puesta en el móvil: las coordenadas cambian con la
cuenta (las de Shop enseñan «Añadir enlace»), así que no se calibra antes.

| Pieza | Estado | Qué falta |
|---|---|---|
| Carruseles: `scripts/subir_carrusel_movil.py` | Calibrado para el OPPO (1440x3168), coordenadas fijas | Perfil de coordenadas del Mi 8 (`MOVIL_ADB=100.115.12.26:5555`), mejor por `uiautomator dump` que por coordenadas. Probar sin publicar hasta el editor |
| Vídeos: script nuevo `scripts/subir_video_movil.py` | No existe | Galería → vídeo → texto/caption → enlace del producto → **«Comprobar contenido»** (hasta 10 al día: evita infracciones) → publicar |
| Programación nocturna | No existe | Tarea del VPS a las 00:00: carruseles (los del día con semáforo verde), luego vídeos. Al terminar, `registrar_subidas` |

Reglas del Mi 8:
- **Despertar**: `keyevent 26`. Si sale la guía del sensor de proximidad,
  VOLUME_UP y en seguida VOLUME_DOWN (autorizado por Néstor), y deslizar
  `540 1900 → 540 500`. Nunca VOLUME_UP suelto.
- **Perfiles**: `snssdk1233://user/profile/<uid>` (el https abre una web con
  banner de cookies).
- **En bucles de bash**: `adb ... </dev/null`, si no adb se come la entrada.
- **Prohibido**: «Crear ahora» y «Retirar».
- **Al acabar**: `rm /sdcard/u.xml`, HOME y bloquear.

## 6. Usuario web `nes_bugallo`

Entra con su PIN (lo elige la primera vez) y **solo ve dos pantallas**:

- **Subidas** (`/subidas`): vídeos y carruseles publicados cada día, con el total
  del mes y la media frente al objetivo (45 + 10). La rellenan los agentes con
  el MCP. Guía `subidas.md`:
  - `registrar_subidas(fecha, videos, carruseles, nota, modo="sumar"|"fijar")`;
  - `ver_subidas(mes)`.
- **Estadísticas** (`/estadisticas`): las ventas de SU cuenta, con el mismo
  formato que las de Néstor (`estadisticas:ventas:nes_bugallo`). Se leen del Mi 8
  **cada semana** y se guardan con `guardar_estadisticas` (guía
  `estadisticas.md`).
  - PENDIENTE: los scripts de `scripts/estadisticas_movil/` están calibrados
    para el OPPO; adaptarlos al Mi 8.

Sin «Mis tandas»: el contenido lo preparan los agentes.

## 7. Pendientes (orden)

1. Néstor pone la cuenta en el Mi 8 y dice su @ y el nombre nuevo.
2. Calibrar la subida de carruseles en el Mi 8 y subir los primeros 15 a mano
   asistida (sin la tarea nocturna).
3. Script de vídeos con «Comprobar contenido» y primeros 5-10 vídeos (A/B de
   1 contra 2 clips).
4. Tarea nocturna 00:00 y apunte automático en Subidas.
5. Estadísticas del Mi 8 cada lunes.
6. Medir a la semana: ventas por formato (carrusel / POV) y por número de clips;
   decidir si se sube a 20 vídeos.
