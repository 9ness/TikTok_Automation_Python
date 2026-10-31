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
### Receta probada: 10 POV replicados en un día (ronda 8, 31/10)

Scripts en [`scripts/cuenta_arabe_pov/`](../scripts/cuenta_arabe_pov/README.md): se copian
a la carpeta de la ronda (`/mnt/HC_Volume_106974679/navegador/trabajo/hmizat_rondaN/`) y se
ejecutan desde ahí con `~/nav-venv/bin/python`. Coste de la ronda 8: 21 créditos de GenAI
(unos 0,6 €) para 10 vídeos; imágenes y voz gratis.

1. **Virales**: los perfiles de las tiendas árabes de §2, mirados en Social1 (Chrome 9222).
   Solo POV de producto (mano y sin cara) de productos que tengamos en stock y se puedan enlazar.
   `tikwm_hojas.py` baja de cada viral el caption, el audio y una hoja de fotogramas.
2. **Idioma, al pie de la letra.**
   - El texto en pantalla va en el idioma del ORIGINAL, que se mira en sus fotogramas:
     español si es español, árabe si es árabe (las marcas en latino: `WISECEE F206`).
   - No se mezcla en un mismo bloque ni se añade darija porque la cuenta sea árabe.
   - **El caption es el del original, literal, con sus hashtags** (incluso erratas como
     `#blakfriday`). Solo se colapsan los espacios.
   - Los precios o «-X %» del original se cambian por «Mira la oferta en el carrito».
3. **¿Habla o es música?** Se transcribe el audio del original con Whisper `small`
   (`language="ar"`, con `nice` y 1-2 hilos, nunca `large`; al modelo se le pasa un array de
   numpy, porque con la ruta del fichero falla av).
   - **Si habla** (en la ronda 8, 9 de 10 en darija): guion darija condensado del suyo,
     de 2-3 frases cortas (`audio/guiones.json`). Locución con Fish (`voz8.py`, modelo
     `s2.1-pro-free`, voz automática; lee bien la darija). Los subtítulos van alineados por
     palabra con Whisper (`alinear8.py`), y el montaje parte en dos las frases de más de
     6 palabras. Con `silencedetect` salían descuadrados: las comas también hacen pausa.
   - **Si es música**: el montaje sale sin voz y en `SUBIDA.json` se pone un sonido
     comercial parecido, que se añade al subir (ver §5).
4. **Imágenes** (gratis): Google Flow, Nano Banana 2, en un proyecto PROPIO.
   - Dos escenas por vídeo. La ficha va como ingrediente y, en la escena 2, también la
     imagen 1, para que el producto sea idéntico.
   - Sufijo común: casa española real, una sola mano adulta, el producto idéntico a las
     referencias y sin texto.
   - `gen_todas.sh` las hace en bucle. Cada imagen se revisa contra la ficha antes del clip
     (la cafetera salió sin el portafiltro y se rehízo).
5. **Clips**: GenAI Pro → `?ws=video&mode=frames&model=veo` → Frames, con solo el fotograma
   inicial, Portrait y «Cost: 1 credit».
   - Si se abre el modal de modelos, Escape ×2.
   - `generar_veo8.py` lleva `GENERACIONES.json` con un tope de créditos y como mucho un
     reintento por clip.
   - **Prompts cortos (~25 palabras) con una sola acción física**, terminando en «Calm,
     realistic handheld phone shot. Soft ambient room sound.». Los largos o los que llevan
     «no music» o listas de prohibiciones disparan el **«audio safety filter»** de Veo: falla
     y devuelve el crédito.
   - Nada que se despliegue o se transforme (la mesa plegable se deformó). Mejor el producto
     quieto y una mano que lo toca o lo usa.
   - **Plan B**: si un clip falla dos veces, la imagen de Flow con zoom suave (Ken Burns,
     2-3 s).
6. **Revisión**: hoja de fotogramas de cada clip.
   - El producto tiene que ser igual a la ficha en TODO el clip, nada debe atravesar nada y
     solo puede haber una mano.
   - Veo suele estropear el final (a la aspiradora le sale una manguera, aparecen manos de
     más, la fregona desaparece): se recorta a la parte buena en `CONTROL_CALIDAD.json`.
7. **Montaje** (`montar8.py N`): los 2 clips a 1080×1920 y 30 fps, con un acabado más
   cuidado que el suyo.
   - Cabecera de 2 líneas (nombre del producto + gancho del original) en Tajawal ExtraBold
     con caja, que entra con fundido y deslizamiento.
   - Cierre en los últimos 2,8 s: «راجعي القسائم المتاحة» + «لطلب من هنا» en árabe, o
     «Revisa si tienes cupones» + «PINCHA AQUÍ PARA COMPRAR» en español, con una flecha
     naranja que rebota hacia el carrito.
   - Whoosh y pops suaves sintetizados con ffmpeg.
   - Si hay voz: subtítulos encima del cierre, voz con `loudnorm=I=-14:TP=-2.0` y efectos
     al 40 %.
   - `clean_metadata` y una hoja de 15 fotogramas en `revision/`.
8. **Registro y semáforo**: `registrar_app.py N [replica_id_a_reemplazar]` (MCP
   `registrar_replica_video`, `para="nes_bugallo"`).
   - ⚠️ El semáforo por MCP se guarda en el usuario del TOKEN (ness). Hay que ponerlo dentro
     del contenedor: `docker exec tiktok-api python -c "from src.mis_tandas import servicio
     as s; s.poner_semaforo('nes_bugallo','rv|<id>','verde','<motivo>','agente')"`.
   - Lo electrónico que se enciende o tiene pantalla va en ámbar.
9. **Subida**: `SUBIDA.json` de la ronda (`voz.si=true` en los hablados, `sonido` propio en
   los de música) + `scripts/subir_video_movil.py` (§5) y `registrar_subidas`.

Navegador: Flow y GenAI Pro en pestañas propias, con ENTRA/SALE en `~/navegador_turnos.log`
y nunca los dos a la vez si queda poca RAM.

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
- **Sonido por vídeo** (31/10): si el viral lleva música, `sonido` en `SUBIDA.json` trae
  `{busqueda, sugerencia ("" = pulsar «Buscar», Intro no busca), fila (regex OCR de su línea
  «N publicaciones»), comprobar}`; si falla dos veces, vuelve a «Suns». La búsqueda de
  sonidos no tiene filtro de «comerciales». Ejemplo para la música jbala/árabe:
  «Arab Romantic Lover» (Zahidan Beats, 1,2M). Los vídeos con voz (`voz.si`) no llevan sonido.
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
