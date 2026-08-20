# APK (Android)

La app es un **WebView** propio (`android-app/`): la APK no lleva la web dentro,
la carga, pero el contenedor es nuestro y por eso puede hacer cosas que un
navegador no deja hacer.

## Por qué WebView y ya no TWA

Antes era una **TWA** (Chrome con la barra oculta). Se eligió así justamente por
las descargas: dentro de un WebView el `<a download>` no baja nada de serie
—no hay gestor de descargas— y aquí media app son descargas. Lo que cambió es
que aparecieron dos necesidades que en una TWA **no tienen solución**, porque
quien manda es Chrome y no nosotros:

- **Guardar en una carpeta propia.** En la TWA todo caía mezclado en
  `Download/` (y en el móvil, revuelto con los vídeos de la galería). Ahora va a
  `Download/TTShopAIPro/`.
- **Subir en segundo plano.** Al subir los clips de ocho productos había que
  quedarse mirando la pantalla: al bloquear el móvil, Chrome paraba. Ahora lo
  hace un servicio en primer plano con wake lock y se puede bloquear.

De paso se ganó lo que la TWA no daba: una **notificación con la marca** y
progreso agregado ("3 de 10" + los MB del fichero actual) en vez de diez avisos
iguales, **deslizar para recargar**, y el **aviso de versión nueva**.

Antes de migrar se hizo una APK de usar y tirar que se instalaba AL LADO de la
buena, para comprobar en el móvil real que cada una de esas cosas funcionaba.
Mereció la pena: salieron por el camino el `.bin` en vez de `.mp4` y las tildes
rotas, y se arreglaron sin tocar la app que estaba en uso.

Sigue habiendo un caso que va por otro camino: los **carruseles** bajan por
`blob:`, que hay que pasar por base64. Funciona, pero no se ha probado con
tandas grandes.

## Instalar

Descarga desde la web (sale un aviso abajo al entrar desde Android) o del enlace
fijo:
<https://github.com/9ness/TikTok_Automation_Python/releases/download/apk-latest/tiktok-auto.apk>

Android pedirá permitir "orígenes desconocidos". En iPhone no hay APK: Safari →
Compartir → Añadir a pantalla de inicio.

La app **avisa sola** cuando hay una versión nueva: al arrancar compara su
`versionCode` con el que va escrito en las notas de la release `apk-latest`, y
si es mayor saca una notificación que lleva a la descarga.

## ¿Cuándo hay que regenerarla?

Los cambios de la **web** siguen llegando solos con cada deploy, sin reinstalar.
Hay que rehacer la APK cuando se toca algo **de la app**: `android-app/`, el
dominio, el icono o el nombre.

## Cómo se genera

1. Sube `versionCode` (y `versionName`) en `android-app/app/build.gradle`.
2. GitHub → **Actions** → **APK (app)** → **Run workflow**.

Deja la APK en la release `apk-latest` (el enlace de arriba) y como artifact.
El workflow **falla a propósito** si el `versionCode` no supera al ya publicado:
sin eso Android se negaría a instalarla encima y el aviso de actualización no
llegaría nunca.

No hace falta que el servidor esté encendido (eso era cosa de Bubblewrap, que
descargaba el manifest del dominio real).

## Volver atrás

`android-apk-twa.yml` sigue ahí y reconstruye la TWA. Publica en la **misma**
release `apk-latest`, así que lanzarlo pisa la app buena — no se lanza sin
querer.

## Cosas que ya costaron una vez

- **Instalar encima exige la misma clave y el mismo `applicationId`.**
  `com.nebulabsai.tiktokauto` firmado con `android-keys/tiktok.keystore` (alias
  `tiktok`, contraseña `tiktokauto`). Si cambiara la firma habría que
  desinstalar primero, y eso borra los datos.
- **La sesión NO sobrevive a la migración.** La TWA guardaba las cookies en
  Chrome y el WebView tiene su propio almacén: al pasar de una a otra hay que
  volver a entrar con el PIN. Una vez. Le pasa a todos los usuarios, no solo al
  admin.
- **Los ficheros bajaban como `.bin`.** El servidor mandaba
  `application/octet-stream` y Android renombra por el MIME. Se arregló
  deduciendo el tipo real en `/api/v1/queue` (`_tipo_de`).
- **Las tildes salían rotas** (`Ergon?mica`). Había una cabecera
  `Content-Disposition` puesta a mano que pisaba la que genera Starlette con
  RFC 5987; se quitó y la app parsea `filename*=utf-8''`.
- **`readAllBytes` es API 33** y el mínimo aquí es 29. Compila y peta en el
  móvil.
- Los iconos hay que meterlos con **`git add -f`**: el `.gitignore` tiene un
  `*.png` global.
- El workflow necesita **`permissions: contents: write`**. El `GITHUB_TOKEN` por
  defecto es de solo lectura y la release moría con `HTTP 403` con la APK ya
  construida y firmada.
- `frontend/public/.well-known/assetlinks.json` era de la TWA (la huella que
  quitaba la barra de direcciones). Ya no hace nada, pero se deja por si hay que
  volver atrás.

## Se cierra sola

Había DOS causas distintas y se confundían entre sí.

### 1. Se quedaba sin memoria en las pantallas de fotos (esta sí era culpa nuestra)

Lo que ocupa en el móvil no es el fichero, es el **bitmap descodificado**: ancho
× alto × 4 bytes. Una ficha de Drive es 1320×2868 → **15 MB por foto**, y una
carpeta de diez productos son veinte fotos → ~300 MB.

Arreglado sirviendo las fotos encogidas (`?w=` en `/nicho-pov-bof/photo`,
`services/thumbs.py`): 400 px en las cuadrículas —1,4 MB, 10× menos— y 900 px al
abrir el visor, que es una sola foto. El original se sigue sirviendo donde
importa: las descargas (`/foto-limpia`) y el montaje del vídeo.

### 2. Android matando el proceso

Cuando el sistema necesita memoria mata la app. Lo que se hace:

- `alwaysRetainTaskState` + `launchMode="singleTask"` en el manifest, para no
  acabar en la pantalla de inicio al volver desde el lanzador.
- `RestaurarPantalla` (frontend): al arrancar de cero **con la app instalada**,
  si estabas en otra pantalla hace menos de 6 h, vuelve a ella. En el navegador
  normal no actúa, que ahí sería un secuestro.
- La app **pide** salir del ahorro de batería al arrancar, que es lo que más
  corta las tandas largas. Si se rechaza: **Ajustes → Apps → TikTok Auto →
  Batería → Sin restricciones**.
