# Guías para agentes de IA — Tiktok Shop AI Pro

> **Para quién es esto.** Para una IA (Claude en Chrome / Cowork, ChatGPT
> Agent / Atlas, Claude Code o Codex en el VPS) a la que el operador le pide
> que haga por él el trabajo de un menú de la app: bajar las fotos, generar
> las imágenes y los clips fuera, revisarlos, subirlos a editar y dejarle los
> vídeos listos. Aquí está el proceso EXACTO que hace él a mano.
>
> Se sirven en la propia app, sin login:
> `https://factory.nebulabsmedia.com/api/v1/agente/guias/<fichero>.md`
> (botón «Guía IA» en la cabecera de cada nicho). En el repo viven en
> `src/agente_mcp/guias/`. Si tienes el **MCP** conectado, la herramienta
> `guia` te las da igual.

## 0. Dos maneras de trabajar

- **Con el MCP «tiktok-shop-ai-pro»** (lo preferible). La app hace de
  herramientas: `carpetas`, `productos`, `preparar_carpeta`, `plan_producto`,
  `preparar_bandeja`, `ver`, `subir_clip`, `videos_montados`… Así no clicas la
  app ni copias del portapapeles: solo usas el navegador para **generar** en
  Google Flow / GenAI Pro / Magnific. Detalles en la sección 7.
- **Solo con el navegador**: haces lo mismo pulsando los botones de la app,
  como se describe en cada guía.

Los pasos, las preguntas al operador, las reglas y la revisión de calidad son
los mismos en los dos casos.

## 1. Antes de tocar nada: lee esto en orden

1. **Esta página** (reglas y preguntas de arranque).
2. [`comun/app.md`](comun/app.md) — cómo se maneja la app (login, pantallas,
   pasos, tarjetas, subir y descargar ficheros).
3. [`comun/plataformas.md`](comun/plataformas.md) — Google Flow, GenAI Pro y
   Magnific: dónde se hace cada foto y cada clip, y cómo.
4. [`comun/revision-calidad.md`](comun/revision-calidad.md) — cómo decidir si
   una foto o un clip generado vale o se repite.
5. La guía del **menú** que te han pedido (tabla de abajo).

## 2. Una guía por menú

| Menú de la app (sidebar «Tiktok Shop AI Pro») | Ruta | Guía |
|---|---|---|
| POV BOF Largo | `/tiktok-shop-ai-pro/pov-bof-largo` | [`pov-bof-largo.md`](pov-bof-largo.md) |
| Nicho POV BOF | `/tiktok-shop-ai-pro/nicho-pov-bof` | [`pov-bof.md`](pov-bof.md) |
| Moda Mujer · Aleatorios | `/tiktok-shop-ai-pro/nicho-ropa-mujer` | [`moda-mujer-aleatorios.md`](moda-mujer-aleatorios.md) |
| Moda Mujer · Marca Personal | `/tiktok-shop-ai-pro/moda-mujer-marca` | [`moda-mujer-marca.md`](moda-mujer-marca.md) |
| Ropa Hombre | `/tiktok-shop-ai-pro/nicho-ropa-hombre` | [`ropa-hombre.md`](ropa-hombre.md) |
| Nicho General · UGC | `/tiktok-shop-ai-pro/nicho-general` | [`ugc.md`](ugc.md) |
| Carruseles | `/tiktok-shop-ai-pro/carruseles` | [`carruseles.md`](carruseles.md) |
| Creativos Pro | `/tiktok-shop-ai-pro/creativos-profesionales` | [`creativos-pro.md`](creativos-pro.md) |

Los menús que no están en la tabla (BOF Cinematográfico, Gorras, Cuenta
Piloto, Sin Humanos, Nicho Ropa, Nicho Zapatos, Viralización, Plantillas,
Configuración) **no tienen guía**: si te piden uno, dilo y pregunta antes de
improvisar.

## 3. Preguntas de arranque (hazlas SIEMPRE, todas en un mensaje)

El operador suele pedir cosas como «hazme la carpeta 24 de Moda Mujer». Antes
de empezar, confirma lo que falte de esta lista — con opciones, no en abierto:

1. **Menú y modo.** Qué menú y, si tiene modos (Moda Mujer tiene seis), cuál.
   En POV BOF Largo: modo del guion «Precio» o «Punto de dolor».
2. **Catálogo y carpeta.** Ej.: «📦 Inventario / Carpeta_24», «🌐 Productos
   Web / Carpeta 12», «Muestras productos», «Tareas Productos».
3. **Hasta dónde llegas.** Una de estas paradas:
   - **A · Solo preparar**: textos, guiones y fotos descargadas.
   - **B · Hasta las imágenes**: generadas y revisadas, sin vídeo.
   - **C · Hasta los clips**: generados y revisados, sin subir a la app.
   - **D · Hasta el montaje**: clips subidos, vídeo editado por la app y
     descargado a la carpeta de salida.
   - **E · Solo revisar**: comprobar fotos/clips ya generados (no generas nada).
4. **Dónde generar el vídeo** (si el formato lo permite — ver
   [`comun/plataformas.md`](comun/plataformas.md)):
   - **Google Flow**: el único que habla. 8 s o 10 s.
   - **GenAI Pro**: mudo, 8 s, 1080p.
   - **Magnific**: mudo, 8 s o 10 s, con el prompt ya dentro del «space».

   Si el clip tiene que llevar la voz dentro (Moda hablada, UGC), solo vale
   Flow: no preguntes, dilo.
5. **Duración del clip: 8 s o 10 s** (en los menús que la dejan elegir).
   Dato para decidir: en Flow un clip de 8 s cuesta 12 créditos y uno de
   10 s, 15.
6. **Qué productos.** Todos los de la carpeta, solo los que tienen ficha de
   TikTok («🔗 Con URL»), o una lista concreta.
7. **Qué haces si una generación sale mal**: repetir hasta N veces (propón 2)
   o apartarla y seguir.

No preguntes lo que la app ya dice: cuántos clips necesita cada producto lo
enseña su tarjeta (huecos «Clip 1», «Clip 2»…), y la duración del guion la
decide la app.

## 4. Reglas que no se saltan

- **Las imágenes y los vídeos se generan SIEMPRE en la web** (Google Flow,
  GenAI Pro, Magnific), con la cuenta del operador abierta en el navegador,
  igual que los hace él. **Nunca por API** (Gemini, Veo, Seedance…): cuesta
  mucho más. Si no puedes controlar el navegador, prepara todo y para.
  Si eres un agente del **VPS** (Claude Code, Codex) sin navegador: existe la
  opción de un Chrome remoto en el propio VPS con la sesión del operador
  (`deploy/NAVEGADOR_REMOTO.md`). Mira si está montado
  (`systemctl is-active navegador-chrome`). Si no lo está, propónselo al
  operador con ese documento y NO lo montes sin su «sí».
- **Nunca gastes sin permiso.** Cada imagen y cada clip cuesta créditos. Antes
  de generar, di cuántas imágenes y clips vas a lanzar y espera el «sí».
- **Máximo 10 vídeos al día por cuenta nueva** (Moda Mujer, Ropa Hombre);
  ~20 en la cuenta de `ness`. No propongas más aunque se pueda.
- **El producto del vídeo tiene que ser EL de la ficha.** Es lo que más caro
  sale: una infracción de «promoción de productos incoherente» cuesta 8
  puntos de la cuenta. Revisa con [`comun/revision-calidad.md`](comun/revision-calidad.md)
  cada imagen y cada clip ANTES de subirlo.
- **No publiques en TikTok** ni marques «📤 Subido», «🏪 Escaparate» o
  «💰 Vendió» salvo que te lo pidan: esas marcas dicen lo que ha hecho la
  persona en su cuenta.
- **No toques Configuración**, ni borres productos, clips o carpetas, ni
  pulses «Rehacer…/Reescribir…» sobre lo que ya está hecho sin preguntar.
- **No pegues el PIN ni credenciales en ningún chat.** Si la app pide
  «¿Quién eres?», pide al operador que entre él.
- Si la pantalla no coincide con la guía (un botón que no está, otro nombre),
  **para y avisa**: la guía puede haberse quedado vieja. Apunta qué viste.

## 5. Dónde dejar las cosas

Trabaja en la **bandeja**: una carpeta del Drive que ven a la vez tú, el
operador y la app. Con el MCP la crea `preparar_bandeja`; sin él, créala tú
con la misma forma:

```
Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/_agente/<usuario>/<menú>/<Carpeta N>/
  <nº>_<título corto>/
    PLAN.md                ← qué generar y con qué prompt (lo escribe el MCP)
    foto_limpia.jpg        ← bajada de la app (y foto_ficha.jpg)
    imagen_1.png           ← la que generas (imagen_2.png si hay dos)
    clip_1.mp4, clip_2.mp4 ← los clips generados, en orden
    RECHAZADAS/            ← lo que no pasó la revisión (no se borra)
  informe.md               ← qué se hizo con cada producto (ver abajo)
  videos/                  ← los montados (`videos_montados(copiar_a_bandeja=True)`)
```

- **Agente en el PC del operador (Cowork / Chrome / Atlas):** es la carpeta
  de su Google Drive para escritorio (`G:\Mi unidad\…` o similar). Si no
  tienes acceso al Drive, usa una carpeta en *Descargas* con la misma forma y
  sube los clips con `/subir` o con los botones de la app.
- **Agente en el VPS:** `~/gdrive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/_agente/<usuario>/`.
  Los vídeos que monta la app quedan además en
  `~/gdrive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/<Nicho>/videos/...`
  (cada guía dice la ruta).
- El Drive tarda un poco en sincronizar: si el MCP dice que un fichero «no
  existe», espera un minuto y reintenta.

El **informe final** (en el chat y en `informe.md`): una línea por producto con
«✅ montado / 🖼️ imágenes hechas / ⚠️ rechazado (motivo) / ⏭️ saltado (motivo)»,
créditos gastados y lo que necesita que decida él.

## 6. Si puedes usar la API en vez de clicar

La app tiene API REST (`/api/v1/...`, doc en `/api/docs`). Si estás en el
mismo navegador en el que el operador ya entró, la cookie de sesión vale y
puedes abrir los `GET` en una pestaña para leer los prompts o el estado de los
productos en JSON en vez de copiar del portapapeles. Cada guía lista los
endpoints útiles. **Solo lectura** con la API salvo que la guía diga otra
cosa: las acciones (subir clips, escribir guiones) hazlas con los botones — o
mejor, con el MCP.

## 7. Con el MCP: el flujo

El operador conecta la URL personal que sale en la app, en **Settings ›
Conectar una IA (MCP)**. Todo lo que hagas va a SU nombre (su progreso, sus
vídeos).

1. `guia()` y `guia(menu)` → estas instrucciones.
2. `menus_disponibles()` → menús, modos y opciones válidas.
3. `carpetas(menu, catalogo)` → carpetas y su progreso. Acepta nombres
   aproximados («inventario», «carpeta 24»).
4. `productos(menu, catalogo, carpeta, …)` → estado de cada producto.
5. `preparar_carpeta(…)` → textos y guiones que falten (devuelve un
   `tarea_id`; sigue con `estado(id)` y luego `estado()` para la cola).
6. `preparar_bandeja(…)` → deja en el Drive, por producto,
   `foto_limpia.jpg`, `foto_ficha.jpg` y `PLAN.md` con cada imagen y clip a
   generar (prompt literal, qué adjuntar, frame inicial o ingredientes,
   segundos, plataformas válidas). Ruta:
   `Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/_agente/<usuario>/<menú>/<carpeta>/<producto>/`.
   Si no ves el Drive, `plan_producto` te da lo mismo en JSON, con enlaces de
   descarga para las fotos.
7. Generas en Flow / GenAI Pro / Magnific y guardas **en esa misma carpeta**
   con el nombre que dice el plan (`imagen_1.png`, `clip_1.mp4`, …).
8. `ver(ruta_bandeja=…)` → te enseña la imagen o fotogramas del clip para
   revisarlo contra `ver_producto(…)` (foto limpia y ficha). Checklist en
   [`comun/revision-calidad.md`](comun/revision-calidad.md).
9. `subir_clip(…, clip=N, ruta_bandeja=…)` o `subir_clips_de_bandeja(…)`
   para toda la carpeta. Si no escribes en el Drive: sube el fichero por HTTP
   (`curl -F file=@clip_1.mp4 <URL del MCP>/subir` → `archivo_id`) o pasa
   una `url` pública. Al llenar el último hueco, la app monta sola (UGC:
   `montar`).
10. `estado()` hasta que acabe → `videos_montados(…, copiar_a_bandeja=True)`
    deja los vídeos editados en `<carpeta>/videos/` de la bandeja.
11. `marcar_carpeta(menu, catalogo, carpeta, pendiente=True)` al terminar los
    vídeos de una carpeta: es el «📤 Pendiente» que le dice al operador que
    tiene que subirlos. `completada=True` solo si él lo pide.
12. `marcar(…)` solo si el operador lo pide (Subido / Escaparate / Vendió). En
    POV BOF Largo, `rehacer` + `nota_rehacer` es la marca «🔁 Rehacer»; la pone
    él al revisar y los productos marcados te salen en `avisos`.
13. `borrar_productos(catalogo, carpeta, productos?, confirmar=True)`: solo en
    los catálogos propios (Muestras / Tareas) y solo si el operador lo pide.
    Sin `productos` vacía la carpeta entera. No se deshace.

Lo que el MCP **no** hace: generar imágenes o vídeos (Flow, GenAI Pro y
Magnific no tienen API) ni publicar en TikTok. Carruseles aún no tiene
herramientas: hazlo por la web con [`carruseles.md`](carruseles.md).
