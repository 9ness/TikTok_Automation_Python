# Replicar virales (vídeo ya montado): guía para agentes

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
   mueva solo, producto igual que en la ficha y sin texto inventado.
5. Monta con ffmpeg:
   - **Encuadre anti-marca** (quita la marca de agua del generador), en cada clip:
     `-vf "scale=1232:2188,crop=1080:1920:(in_w-out_w)/2:0"`
   - **Rótulo**: el gancho del viral, adaptado, y el **nombre del producto**,
     quemados en pantalla. Si hay voz, también subtítulos de lo que dice.
   - **Metadatos limpios**: `-map_metadata -1 -map_chapters -1` (como
     `limpiar_metadatos` del POV BOF) y `-c:v libx264 -pix_fmt yuv420p -c:a aac`.
6. Registra (ver 3).

## 2. Sin IA (real)

El operador graba (o te pasa las tomas) y montas el viral con ellas: mismos
cortes y mismo gancho, con **nuestro** producto a la vista desde el primer
segundo. Igual que con IA: rótulo con el gancho y el nombre del producto,
subtítulos si hay voz y metadatos limpios. Si las tomas llevan marca de agua
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
