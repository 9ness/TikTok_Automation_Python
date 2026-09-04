# `android-app/` — la APK

WebView propio que carga `https://factory.nebulabsmedia.com/`. El porqué
de no ser una TWA, cómo se construye y qué ya costó una vez está en
[`../APK.md`](../APK.md) — esto es solo el mapa de los ficheros.

| Fichero | Qué hace |
|---|---|
| `MainActivity.java` | El WebView. Descargas (`DownloadManager` → `Download/TTShopAIPro/`), selector de ficheros (`onShowFileChooser`), puente JS para las subidas, deslizar-para-recargar, permisos. |
| `AvisoDescargas.java` | La notificación con la marca: una sola para toda la tanda, con "3 de 10" y los MB del fichero que va. |
| `ServicioSubidas.java` | Servicio en primer plano que sube los ficheros. Es lo que permite bloquear el móvil a media tanda. |
| `Avisador.java` | Callback para contarle al frontend, fichero a fichero, que ya subió. |
| `Actualizaciones.java` | Al arrancar, compara su `versionCode` con el de la release `apk-latest` y avisa si hay una nueva. |

Lo que se toca al publicar: **`versionCode` y `versionName` en
`app/build.gradle`**. El workflow falla si el `versionCode` no sube.
