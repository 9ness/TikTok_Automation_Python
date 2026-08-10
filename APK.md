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

## Se cierra sola

Había DOS causas distintas y se confundían entre sí.

### 1. Se quedaba sin memoria en las pantallas de fotos (esta sí era culpa nuestra)

Lo que ocupa en el móvil no es el fichero, es el **bitmap descodificado**: ancho
× alto × 4 bytes. Una ficha de Drive es 1320×2868 → **15 MB por foto**, y una
carpeta de diez productos son veinte fotos → ~300 MB. Chrome mata la pestaña por
memoria y en una TWA eso se ve exactamente igual que "Android ha cerrado la
app". Por eso pasaba "a veces": dependía de la pantalla.

Arreglado sirviendo las fotos encogidas (`?w=` en `/nicho-pov-bof/photo`,
`services/thumbs.py`): 400 px en las cuadrículas —1,4 MB, 10× menos— y 900 px al
abrir el visor, que es una sola foto. El original se sigue sirviendo donde
importa: las descargas (`/foto-limpia`) y el montaje del vídeo.

### 2. Android matando el proceso (esta no tiene arreglo)

Cuando el sistema necesita memoria mata la app, y eso **no se puede evitar**
desde una app web. Lo que sí se ha hecho:

- `alwaysRetainTaskState` ya viene puesto por Bubblewrap (el workflow lo
  comprueba y falla si algún día dejara de ponerlo). Eso evita el caso de
  "vuelvo del lanzador y me deja en la pantalla de inicio".
- `RestaurarPantalla` (frontend): al arrancar de cero **con la app instalada**,
  si estabas en otra pantalla hace menos de 6 h, vuelve a ella. En el navegador
  normal no actúa, que ahí sería un secuestro.

Lo que más ayuda está en el móvil y no en el código: **Ajustes → Apps → TikTok
Auto → Batería → Sin restricciones**. Con la optimización agresiva (Xiaomi,
Samsung, Huawei…) el sistema la mata a los pocos minutos.
