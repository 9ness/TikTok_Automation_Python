# APK de PRUEBA — dónde caen las descargas

No es la app. Es un experimento de usar y tirar para responder UNA pregunta
antes de tocar la APK de verdad:

> ¿Un WebView puede guardar las descargas en `Download/TTShopAIPro/`?

La app real es una **TWA** (Chrome sin barra), y ahí las descargas las gestiona
Chrome: no hay forma de elegir carpeta. La alternativa es un WebView, pero
`APK.md` la descartó en su día porque dentro de un WebView `<a download>` no
baja nada por sí solo. Esta prueba mide si la alternativa funciona DE VERDAD en
el móvil del operador, y en concreto los dos casos que tiene la app:

1. **De una en una** (`<a href="https://…" download>`): lo hace el
   `DownloadListener` + `DownloadManager`. Es lo que se da por seguro.
2. **En tanda** (`URL.createObjectURL(blob)`): el `DownloadListener` NI SE
   DISPARA con `blob:`. Hay que pasar los bytes al lado Java. Esta es la parte
   que hay que ver si aguanta con vídeos de 20 MB.

Se instala AL LADO de la app buena (otro `applicationId`), así que no la pisa.
Cuando se decida, esta carpeta se borra.

## Lo que va saliendo (hallazgos)

- **El selector de ficheros hay que implementarlo.** Tocar "Clip 1" no hacía
  NADA: en un WebView el `<input type="file">` no abre nada si la app no
  implementa `onShowFileChooser`. En la TWA funciona solo porque es Chrome.
  O sea que migrar no es solo rehacer las descargas: también las SUBIDAS.
- **Las descargas en tanda SÍ van, y con la app cerrada.** Era la duda que
  decidía el experimento. Resulta que las tandas del POV BOF y del Largo NO
  usan `blob:`: van con la URL directa, así que las coge el gestor de Android y
  siguen aunque se salga de la app. El camino de `blob:` (base64) solo lo usa
  **Carruseles**, y son fotos, mucho más pequeñas.
- **Deslizar para recargar hay que montarlo** (`SwipeRefreshLayout`): un
  WebView no lo trae, lo pone Chrome.
- **La notificación hay que montarla.** El gestor de Android pone UNA por
  fichero (diez vídeos = diez avisos iguales) y en Android 13+ ni eso, si la
  app no pide `POST_NOTIFICATIONS`. `AvisoDescargas` las apaga y publica una
  sola con el progreso de la tanda. Es trabajo que en la TWA sale gratis
  porque lo hace Chrome, pero el resultado se puede dejar MEJOR que el suyo.
- **La subida en segundo plano SÍ se puede, y mejor.** Al principio se dio por
  perdida: la app usa Background Fetch (`sw-subidas.js`), que es de Chrome. Pero
  el equivalente nativo —un servicio en primer plano— es MÁS fiable, porque a
  Background Fetch lo corta Chrome cuando quiere (de ahí que "a veces no se
  suben"). Montado en `ServicioSubidas`: sube en streaming desde el
  `content://`, con wake lock y notificación propia. La web solo dice qué y a
  dónde; el reparto y la cola siguen donde estaban.

## Cuidado

- Los PNG hay que meterlos con **`git add -f`**: el `.gitignore` tiene un
  `*.png` global. Sin ellos el build muere con `resource mipmap/ic_launcher not
  found`. Es el mismo tropiezo que ya está apuntado en `APK.md` para la APK
  buena.

## Cómo se genera

GitHub → Actions → **"APK de prueba (descargas)"** → Run workflow.
