# Cómo se maneja la app (común a todos los menús)

## Entrar

- No hay página de login: al abrir la app sale un modal **«¿Quién eres?»**
  con un desplegable de usuario (`ness`, `ana`, `mauro`…), el campo **PIN** y
  el botón **«Entrar»**. La sesión dura 30 días (cookie).
- **No lo rellenes tú**: pide al operador que entre. Si ya estás dentro, el
  usuario activo es el que manda (el progreso, lo subido y los vídeos son POR
  USUARIO). Confirma con el operador que es la cuenta correcta.
- `ana` y `mauro` (perfil «pro») solo ven POV BOF, POV BOF Largo, Moda Mujer,
  Creativos y Carruseles, y **no** pueden «Obtener textos»: les sale «⏳ Faltan
  textos… los prepara la cuenta de ness». Si te pasa, avisa: lo tiene que
  hacer `ness`.

## Navegar

- Sidebar izquierda → grupo **«Tiktok Shop AI Pro»** → el menú. En el móvil la
  sidebar es un botón de menú arriba.
- Cada menú abre en la última carpeta en la que se trabajó.

## Anatomía de TODAS las pantallas de nicho

Siempre en este orden, de arriba abajo:

1. **Cabecera de texto** (qué hace el nicho).
2. **Caja «📁 Dónde trabajas»**:
   - **Catálogo** (botones: «📦 Inventario General», «🌐 Productos Web»,
     «Muestras productos», «Tareas Productos», «Top vendidos»…).
   - **Modo** (solo en los que tienen: Moda, POV BOF Largo).
   - **Carpetas** como **chips** pequeños. Cada chip: `✓` = hecha,
     `📤` = pendiente de subir, y una píldora `x/y` (ámbar si falta algo,
     verde si está completa). Clic en el chip = abrir esa carpeta.
   - Botones **«Completada» / «Pendiente»** de la carpeta abierta. **No los
     pulses** salvo que te lo pidan.
3. **Pasos numerados** (`Paso 1`, `Paso 2`…). Son bloques plegables: si no
   ves los botones, haz clic en el TÍTULO del paso para abrirlo. Colores fijos:
   - violeta = **preparar** (textos, guiones),
   - fucsia = **generar fuera** (fotos, enlaces a Flow/GenAI Pro),
   - esmeralda = **copiar el prompt**,
   - azul = **descargar lo ya montado**.
4. **Tarjetas de producto**, una por producto de la carpeta (dos columnas en
   PC). En cada tarjeta, de arriba abajo: miniatura + título, chips
   («✍️ Caption», «URL», «más ▾»), guion, voz, **huecos de subida**
   («Subir clip» o «Clip 1», «Clip 2»…), «▶ Ver vídeo» / «Descargar», y la
   **última fila siempre**: «🏪 Escaparate · 📤 Subido · 💰 Vendió».

## Botones de copiar

- Los botones con icono de portapapeles copian un texto (prompt, guion,
  caption) al portapapeles y sale un aviso abajo («Copiado…»).
- Para pegarlo en otra web: pestaña de destino → clic en el campo → `Ctrl+V`
  (`Cmd+V` en Mac).
- Si no puedes leer o usar el portapapeles, saca el texto por la API (cada
  guía dice el `GET`) o pide al operador que te lo pegue.

## Bajar ficheros

- Los botones de descarga en lote («Fotos x/y», «Vídeos x/y», «Todas (N)»)
  bajan los ficheros UNO A UNO, con pausas. Espera a que terminen todos antes
  de moverlos. El navegador puede pedir permiso para «descargar varios
  archivos»: hay que aceptarlo.
- «🔗 Con URL (n)» baja solo los productos que ya tienen ficha de TikTok: es
  lo normal, porque sin ficha no se puede publicar con carrito.

## Subir ficheros (clips, fotos)

- Los botones de subir («Subir clip», «Clip 1», «Subir», «Foto limpia»…) son
  una etiqueta con un `<input type="file">` escondido. Haz clic en la etiqueta
  y elige el fichero en el diálogo, o usa la herramienta de adjuntar fichero
  de tu entorno sobre ese input.
- Sube cada clip **en su tarjeta y en su hueco**: el «Clip 1» es el que abre el
  vídeo. Cuando están todos los huecos llenos, la app **encola el montaje sola**
  («Los clips están: montando el vídeo.»).
- Si no puedes subir ficheros desde tu entorno, para en la parada C y díselo al
  operador (los clips le quedan en la carpeta de trabajo).

## La cola de trabajos

- Guiones, textos, importaciones y montajes van a una cola. El icono de cola
  (arriba) abre el cajón con el progreso.
- Un montaje tarda ~1-3 min. La tarjeta dice «montando…» y cuando acaba
  aparece «▶ Ver vídeo» y «Montado el …».
- Si un trabajo falla, la tarjeta o la cola dicen por qué. No reintentes más de
  una vez sin avisar.

## Cosas que la app ya comprueba (y tú tienes que mirar)

- **«⚠️ El caption dice «X»…»** → el caption promete algo que la ficha no
  respalda. No se publica sin que el operador lo revise.
- **«🖼️ …» (aviso de foto)** → la app no sabe bien cuál es la foto limpia y
  cuál la ficha. Mira la foto antes de usarla.
- **«🚫 Sin stock»** → sáltate el producto.
- **«precio sin detectar · ponlo»** → falta el precio; afecta a la frase de
  plazos. Avisa.
