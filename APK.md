# APK (Android)

La app es una **TWA** (Trusted Web Activity): la APK no lleva la web dentro, la
**abre**. Por dentro es Chrome con la barra oculta, no un WebView.

Se eligió TWA y no Capacitor —que es lo que usan `planificador-viajes` y
`fitness-life`— por las **descargas**: dentro de un WebView el `<a download>` no
baja nada porque no hay gestor de descargas, y aquí media app son descargas (las
fotos de las fichas se bajan de once en once, y los vídeos montados también).
Los otros dos proyectos lo esquivan abriendo el navegador del sistema, que vale
para bajar UNA apk pero no para el botón "Fotos ficha".

## Instalar

Descarga desde la web (sale un aviso abajo al entrar desde Android) o del enlace
fijo:
<https://github.com/9ness/TikTok_Automation_Python/releases/download/apk-latest/tiktok-auto.apk>

Android pedirá permitir "orígenes desconocidos". En iPhone no hay APK: Safari →
Compartir → Añadir a pantalla de inicio.

## ¿Cuándo hay que regenerarla?

**Casi nunca.** Los cambios de la web llegan solos con cada deploy, sin
reinstalar nada. Solo hace falta rehacerla si cambia:

- el **dominio**,
- el **icono** o el **nombre**,
- algo de `android/twa-manifest.json`.

## Cómo se genera

GitHub → **Actions** → **Build Android APK** → **Run workflow**. Deja el campo
de dominio vacío para usar el de `android/twa-manifest.json`. Al terminar deja
la APK en la release `apk-latest` (enlace de arriba) y como artifact del run.

El servidor tiene que estar **encendido y con el Funnel activo**: Bubblewrap
descarga el manifest y los iconos del dominio real. El workflow lo comprueba
antes de empezar y avisa en claro si no responde.

## Cosas que ya costaron una vez

- **`splashScreenFadeOutDuration` es obligatorio** en `twa-manifest.json`.
  Bubblewrap lo vuelca tal cual en `app/build.gradle`; si falta escribe
  `splashScreenFadeOutDuration: ,` y Groovy falla con `Unexpected input: ','`,
  un error que no menciona ni el campo ni el manifest.
- El workflow necesita **`permissions: contents: write`**. El `GITHUB_TOKEN` por
  defecto es de solo lectura y la release moría con `HTTP 403: Resource not
  accessible by integration` con la APK ya construida.
- Los iconos hay que meterlos con **`git add -f`**: el `.gitignore` tiene un
  `*.png` global, y sin ellos el manifest apunta a 404 y Bubblewrap no arranca.
- La **huella SHA-256** de `android-keys/tiktok.keystore` está en
  `frontend/public/.well-known/assetlinks.json`. Es lo que quita la barra de
  direcciones. Si se regenera la clave hay que actualizar ese fichero, o la app
  se abre con barra de navegador.
- De `android/` **solo se versiona `twa-manifest.json`**; el resto del proyecto
  Android lo regenera Bubblewrap en cada build.
