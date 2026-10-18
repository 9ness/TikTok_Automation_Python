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

Hay dos modos (`modo`):

| Modo | Qué es |
|---|---|
| `con_ia` | Clips generados con **Omni** (GenAI Pro · Omni 1.1, 10 s), con la foto del producto como ingrediente |
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
)
```

- `titulo` es obligatorio: el nombre del producto, el mismo que va quemado.
- `product_url` o `product_id`: con uno de los dos basta, y la app normaliza
  el enlace a `https://www.tiktok.com/view/product/<id>`.
- Opcionales: `tienda`, `notas`. Guarda siempre los `prompts`, porque sin
  ellos no hay forma de rehacerlo.
- También vale `archivo_id` (subido a `/subir`) o `url` en vez de `ruta_bandeja`.
- `para="ana"` registra para otro usuario. Solo funciona con un token de admin.

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
