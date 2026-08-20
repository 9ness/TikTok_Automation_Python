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

## Cómo se genera

GitHub → Actions → **"APK de prueba (descargas)"** → Run workflow.
