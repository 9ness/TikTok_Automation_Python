# Replicar virales (vídeo ya montado): guía para agentes

> ⛔ **REGLA Nº 1 (Néstor, 18/10/2026): un vídeo NO está terminado hasta que
> se comprueba.** Cada vídeo montado se revisa (≥7 fotogramas por clip contra la
> ficha + voz y subtítulos) y lleva `semaforo_tanda` ANTES de decir que está
> hecho. Nunca digas que una tanda está lista con `sin_revisar` > 0 en
> `mis_tandas`. La web ya no deja bajar para publicar un vídeo sin semáforo o en
> rojo. Por saltarse esto: -24 a la Estrella de Belén (réplica de Navidad con
> IA, se encendía sola y el Nacimiento aparecía de la nada) y la cuenta a 118.

> **Navidad y productos que se encienden o se despliegan:** nada de unboxing con
> IA donde el producto sale de la caja ya encendido, sin cable/interruptor, o
> con piezas que aparecen o desaparecen entre planos. Mismo tamaño en todos los
> planos. Si no sale idéntico a la ficha, 🔴 y se rehace o se descarta.

> Pantalla: `/tiktok-shop-ai-pro/replicar-virales`. Código: `src/replicar_viral/video.py`,
> API `/api/v1/replicar-viral/video*`, MCP `registrar_replica_video` /
> `listar_replicas_video` / `borrar_replica_video`, `guia("replicar-virales")`.

## Qué es (y qué no es)

Aquí el viral lo replicas **tú, entero**, y lo que entra en la app es el
**MP4 ya montado**. Sale solo en **Mis tandas** (id `rv|<id>`), con descargar,
subido, sin stock, rehacer, semáforo y época, igual que los vídeos de los nichos.

No es `replicar_viral` (guía [`replicar-viral.md`](replicar-viral.md)): esa
herramienta solo escribe el guion de voz y los prompts de dos clips mudos, y el
vídeo se monta en el POV BOF Largo. Si el encargo encaja ahí, hazlo ahí.

Hay tres modos (`modo`):

| Modo | Qué es |
|---|---|
| `con_ia` | Clips generados con **Omni** (GenAI Pro · Omni 1.1, 10 s), con la foto del producto como ingrediente |
| `genjutsu` | El viral entero rehecho con **Genjutsu de Higgsfield** (se cambia su producto por el nuestro). Sale con su color propio en Mis tandas |
| `sin_ia` | Vídeo **real** (grabado) o montaje sin IA del viral con nuestro producto |

Antes de empezar, confirma con el operador lo de siempre: que el viral sigue
con carrito naranja, **qué producto nuestro** va (mismo estilo que el del
viral) y su **enlace de TikTok Shop**. Sin enlace no se registra: es lo que
cruza TikTok para sancionar por «producto incoherente».

## 1. Con IA (Omni)

1. Mira el viral entero (gancho, ritmo, planos) y escribe los prompts de los
   clips de **10 s** para Omni de GenAI Pro (`comun/plataformas.md`). Uno por
   tramo del viral, y cada clip enseña lo que dice la voz en ese tramo.
2. En cada clip va la **foto limpia del producto como ingrediente**. Desde el
   clip 2, además, la imagen del clip 1 como referencia: el producto tiene que
   salir **idéntico** en todos. Si el producto tiene **dos caras distintas**
   (portada y contraportada, frente y espalda) y el clip lo gira, mete las dos
   fotos y di en el prompt cuál es cuál («image 2 = BACK cover, show it when
   turned»). Si no, Omni pinta la portada por los dos lados. Lo más seguro es
   que el clip no lo gire.
3. Di cuántos clips vas a lanzar y **espera el «sí»** antes de generar.
   Siempre en la web, nunca por API.
4. Revisa cada clip con `ver` (unos 7 fotogramas): agarres reales, nada que se
   mueva solo, producto igual que en la ficha y sin texto inventado, y que
   **la física tenga sentido**: nada atraviesa nada, cada tapa en su
   recipiente, el agua o la luz salen por donde salen en el producto real
   (`comun/revision-calidad.md`). Si falla, se rehace el clip aunque cueste
   un crédito más.
5. Monta con ffmpeg:
   - **Encuadre anti-marca** (quita la marca de agua del generador), en cada clip:
     `-vf "scale=1232:2188,crop=1080:1920:(in_w-out_w)/2:0"`
   - **Rótulo**: el gancho del viral, adaptado, y el **nombre del producto**,
     quemados en pantalla. Si hay voz, también subtítulos de lo que dice.
   - **Metadatos limpios**: `-map_metadata -1 -map_chapters -1` (como
     `limpiar_metadatos` del POV BOF) y `-c:v libx264 -pix_fmt yuv420p -c:a aac`.
   - **Flecha al carrito** los últimos ~4 s, SIEMPRE: la de la app
     (`src/nicho_ropa/pipeline/video_editor._flecha(salida, on_log)`, que coge
     una flecha real de `ready_video._arrows_dir()` con el color del fondo).
   - **Música: NUNCA con copyright; solo libre de derechos verificada y
     documentada** (Néstor, 16/10/2026). TikTok le silenció el Belén por una
     canción comercial, y después de «comprobar vídeo» ya no deja añadir
     música, así que se mezcla en el montaje. Fuentes, por este orden:
     villancicos de dominio público en grabación libre (Musopen PD/CC0,
     YouTube Audio Library sin atribución), o Mixkit/Pixabay comprobando la
     licencia de la pista (uso comercial en redes; si la ficha avisa de
     Content ID, se descarta). Nunca música comercial ni sonidos de TikTok.
     Cada pista va al banco con su URL y su licencia en un `LICENCIAS.md`
     (navideña: `_agente/ness/alisa_z/musica_navidad/`). Volumen bajo,
     ~-22 LUFS; con voz, por debajo de ella.
   - **Voz bien alta**: `loudnorm=I=-14:TP=-2:LRA=11` sobre la voz; la clonada de
     Néstor sale floja de Fish, súbele antes `volume=4dB`. Escúchala al final.
   - **Cierre con sentido**, una frase entera y natural, nunca «En el carrito
     naranja» suelto: p. ej. «Te lo dejo en el carrito naranja, y revisa si
     tienes cupones antes de comprar.» (nunca «tu cupón», ver memoria
     no-afirmar-cupones). Con voz clonada, en primera persona.
6. Registra (ver 3).

## 2. Sin IA (real)

El operador graba (o te pasa las tomas) y montas el viral con ellas: mismos
cortes y mismo gancho, con **nuestro** producto a la vista desde el primer
segundo. Igual que con IA (todo el punto 5): rótulo con el gancho y el nombre
del producto, subtítulos si hay voz, flecha, música solo libre de derechos documentada (nunca con copyright), voz alta,
cierre con sentido y metadatos limpios. Si las tomas llevan marca de agua
o un borde, aplica el mismo encuadre.

## 2b. Gancho con IA + producto real (Casca Chollos, 19/10/2026)

Receta de los virales de reacción (referencias en
`_agente/_referencias/ganchos_reaccion/` con su `LEEME.md`). El producto sale
del catálogo **«📦 Productos físicos»** (`productos_fisicos`): los que Néstor
tiene en casa, subidos por él con foto limpia + ficha + URL de TikTok Shop
(campo opcional del alta: el producto nace enlazado). Se suben desde el menú **«Subir productos»**
(`/tiktok-shop-ai-pro/subir-productos`), eligiendo carpeta o automática. Si Néstor lo tiene en casa porque lo pidió como muestra, va AQUÍ (Productos físicos) y no a «Muestras productos» (que queda para lo que se trabaja solo con IA); si la tienda pide ventas para devolverla, el alta trae el check «💸 Muestra reembolsable» (ventas necesarias + días; también en la tarjeta y por MCP `marcar_reembolsable(..., catalogo="productos_fisicos")`; ver `pov-bof.md` §6). Qué grabar primero: `prioridades(solo_fisicos=True)`; la carpeta con las tomas reales de cada producto va en su marca `clips_reales` (`marcar_producto`, `pov-bof.md` §7). Casca Chollos: **máx.
3 vídeos/día**.

**Reparto del trabajo.** Néstor solo da de alta el producto (foto + ficha +
enlace) y, cuando puede, sube sus tomas reales en bruto, sin cortar ni editar, a
`TIKTOK_SHOP_AI_PRO/_agente/_clips_reales/<cuenta>/` (`nestor2` o `ana`). Si
el nombre del fichero no dice de qué producto es, se averigua comparando los
fotogramas con las fotos del catálogo. TODO lo demás lo hace el agente cuando se
le pide el vídeo: elige gancho y texto, genera el gancho IA, corta las tomas
reales en los planos que quiera, monta, revisa y registra. Al usar una toma, la
mueve a `usados/` (puede volver a servir para otro vídeo con otros cortes).
Sin tomas reales del producto, el agente no se inventa el plano de Néstor:
monta con planos de IA de calidad (receta del punto 4) o deja el producto para
cuando lleguen.

**Variante «sitio real + producto con Omni» (Casca Chollos, 19/10/2026).** Sirve
para productos del Inventario General que Néstor NO tiene en casa. Néstor graba
rincones de su piso, sin producto, en tomas de ~30 s con 3 huecos donde iría el
producto (uno cada ~12 s), y las sube a `_agente/_clips_reales/nestor2/sitios/`
con nombre por sitio (`cocina_1.mp4`…). El agente corta trozos de 10-12 s (uno
por producto, sin repetir trozo), los pasa a SDR 1080×1920 H.264 y en **Omni de
Magnific** (vídeo + foto limpia → vídeo, 720p, **1.600 créditos el clip**) pone
el producto en la escena. Va con el gancho IA y el texto de abajo, y se registra
`con_ia`. Sin productos con luces ni pantallas. Créditos: plan Premium+ con
~24.000 al mes, que **no se acumulan** (se reinician con el cobro, el día 24
de cada mes), y el Unlimited sigue suspendido. Avisa del coste antes de lanzar
cada tanda.

1. **Gancho IA, 2-3 s, SIN el producto** (así no hay nada que la IA pueda
   deformar): el cascanueces naranja reacciona — se le cae el vaso, se desmaya,
   se queda boquiabierto y señala, barrido de cámara hacia donde mira. Varias
   versiones por producto, rotando; nunca el mismo gancho dos días seguidos.
2. **Gancho de texto** quemado desde el segundo 0 (corto, curiosidad, sin
   precio ni promesas que la ficha no tenga): «No sabía que esto existía»,
   «Esto me lo tenía que haber comprado antes»…
3. **Néstor en primera persona ~2 s** enseñando el producto en la mano.
4. **Funcionalidades con muchos cambios de plano** (1-2 s cada uno): tomas
   REALES de Néstor siempre que se pueda (es lo que la política AIGC no
   puede tocar). IA solo en planos donde el producto quede idéntico a la ficha
   y sin hacer nada irreal (nada se enciende, despliega ni mueve solo).
5. Acabado del punto 1.5 (nombre del producto, subtítulos si hay voz, flecha,
   música solo libre de derechos documentada, metadatos limpios) y etiqueta
   «Contenido generado por IA» al publicar si lleva planos de IA.

Se registra como `sin_ia` si todo lo que enseña el producto es real (el
gancho no lo enseña) y `con_ia` si algún plano del producto es generado.

**Variante «cambiar el producto en una toma real» (camas, 22/10/2026).**
Néstor graba su propio mueble (su cama, levantando el canapé, apretando el
colchón…) y Omni lo SUSTITUYE por el producto vendido del catálogo; la mano, el
cuarto y el movimiento se quedan. Se monta como un vídeo normal del POV BOF
Largo (dos clips de 6 s), no como réplica. Pasos en Magnific
(`/app/ai-video-generator`, sesión del Chrome 9222; si sale «Log in», Néstor
entra con Google por Accesos › Navegador remoto):
1. Corta trozos de 6 s de la toma, uno por clip, y no repitas ninguno entre vídeos.
2. **Recarga la página antes de cada clip**: es lo único que vacía las
   referencias (ni «Remove @vid1» ni la X van fiables).
3. Comprueba el modelo: si vuelve a «Auto» (1080 / 5"), elige
   **Gemini Omni 1.1** y ponlo a **720p / 6" / 9:16**. Botón «Generate 960»: 960
   créditos el clip.
4. Add media → el trozo (@vid1) → la foto limpia (@img1) → en el clip 2, un
   fotograma del clip 1 YA GENERADO (@img2). Sin @img2, el clip 2 cambió el
   dibujo y el color del colchón (hexágonos → rombos, gris → blanco).
5. Prompt: «Replace the bed in @vid1 with … from @img1 … Keep everything else
   from @vid1 exactly as it is (room, hand with the same bracelet, movement,
   camera, light)», describe el producto (color, dibujo, laterales, grosor), cita
   @img2 («the same … already filmed in this room») y cierra con «Nothing moves
   by itself, no text, no logos». Si se ve el bajo del canapé, descríbelo igual
   en los dos clips (somier de láminas en marco de metal negro): si no, cada clip
   inventa uno.
6. Si falta duración, usa **rebote** (el final invertido), nunca cámara lenta.
7. Para subirlo: en aleatorios, antes de `/clip/upload` pon el estilo del
   catálogo (`/estilo-guion`) en el mismo estilo con el que se escribió el guion
   del producto; si no, da «Primero escribe el guion». Sube clip 1 y clip 2
   seguidos (al llegar el 2 se monta). Un guion de menos de ~200 car. a veces
   pide 3 clips: rehazlo hasta que `clips_necesarios` sea 2.

### Variante ropa (Ana, su catálogo «📦 Productos físicos», `productos_fisicos_ana`)

Vídeo de 12-15 s, muy variado:
1. **Gancho IA en una tienda, 2-3 s**, sin la prenda: dos chicas se desmayan,
   se quedan boquiabiertas, se giran de golpe… + gancho de texto fuerte.
2. **Clip real de Ana** (sin IA): tira la prenda al sofá y la estira o la
   toca. Es el segundo gancho. Las tomas en bruto llegan a
   `_agente/_clips_reales/ana/`, y el reparto del trabajo es el mismo de
   arriba: los cortes los decide el agente.
3. **La chica probándosela frente al espejo, ~4 s en varias tomas** distintas
   (IA con la foto limpia como ingrediente: diseño, color, estampado, corte y
   largo idénticos a la foto).
4. La música la pone Ana al publicar (en ropa no ha habido sanciones por
   producto incoherente, de momento sin «comprobar vídeo»). El semáforo en Mis
   tandas sigue siendo obligatorio.

**Mientras Ana no tenga los clips reales** (19/10/2026) sube vídeos SOLO de IA,
de calidad. Hasta el 24/10 su cuenta está limitada a 1 vídeo/día: la apelación
se rechazó y no se vuelve a apelar. Después, 3-4 al día como mucho y nunca dos
de IA parecidos seguidos (misma chica, encuadre o plantilla). Cuando lleguen los
clips reales, se pasa a esta receta.

Hay dos «📦 Productos físicos»: `productos_fisicos` (solo ness y nestor2) y `productos_fisicos_ana` (solo Ana, ropa y lo que tenga en casa); ninguno ve el del otro.

## 3. Registrar → Mis tandas → semáforo

Deja el MP4 en tu bandeja (`TIKTOK_SHOP_AI_PRO/_agente/<usuario>/`, por
ejemplo `replicas/<producto>.mp4`) y regístralo. No se sube nada: la app lo
copia de la bandeja a `TIKTOK_SHOP_AI_PRO/Replicar_Viral/<usuario>/<id>.mp4`.

```
registrar_replica_video(
  modo="con_ia",
  titulo="Lámpara LED de mesa recargable",
  ruta_bandeja="replicas/lampara_led.mp4",
  product_url="https://www.tiktok.com/view/product/1729123456789",
  url_viral="https://www.tiktok.com/@cuenta/video/7420000000000000000",
  caption="La lámpara que no sabías que necesitabas ✨",
  hashtags=["lampara", "deco", "tiktokshop"],
  prompts=["<prompt del clip 1>", "<prompt del clip 2>"],
  catalogo="productos_fisicos", carpeta="<carpeta>", producto_ref="<nº>",
)
```

- `titulo` es obligatorio: el nombre del producto, el mismo que va quemado.
- `product_url` o `product_id`: con uno de los dos basta, y la app normaliza
  el enlace a `https://www.tiktok.com/view/product/<id>`.
- Opcionales: `tienda`, `notas`. Guarda siempre los `prompts`, porque sin
  ellos no hay forma de rehacerlo.
- También vale `archivo_id` (subido a `/subir`) o `url` en vez de `ruta_bandeja`.
- `para="ana"` registra para otro usuario. Solo funciona con un token de admin.
- `catalogo` + `carpeta` + `producto_ref`: si el producto está en un catálogo
  del operador (Productos físicos, Muestras, Tareas…), pásalos SIEMPRE. Al
  marcarlo subido cuenta en el contador por formato de ese producto (con_ia y
  genjutsu = 🔁 Viral, sin_ia = 🎥 Físico; guía `pov-bof.md` §7). Una réplica ya
  registrada se ata después repitiendo la llamada con `replica_id`.

Devuelve `id`, `id_tandas` (`rv|<id>`) y `descargar`. Después:

1. Pon el **semáforo** con `semaforo_tanda(id="rv|<id>", color=…, motivo=…)`,
   con los mismos criterios que el resto (`mis-tandas.md` › Semáforo). En
   rojo se marca también «rehacer».
2. Pon la **época** con `epoca_video(id="rv|<id>", epoca=…)`.

**Rehacer** (tras un 🔴 o un «rehacer» del operador): vuelve a montar y
registra con `replica_id="<id>"`. La réplica no cambia, su vídeo se sustituye,
se quita el «rehacer» y el vídeo sale de su tanda para entrar en una nueva.

Para verlas: `listar_replicas_video(modo="")`. Con `id`, la réplica entera con
sus prompts. `borrar_replica_video(id, confirmar=True)` solo se usa si el
operador lo pide.
