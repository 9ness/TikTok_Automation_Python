# El navegador del VPS — generar en Flow / Magnific / GenAI Pro sin el PC

> Estado (29-sep-2026): **montado y con las tres sesiones abiertas** (Magnific,
> Flow Pro y GenAI Pro, cuenta del operador). Detalle de la instalación y de
> por qué está así: [`deploy/NAVEGADOR_REMOTO.md`](../../../../deploy/NAVEGADOR_REMOTO.md).

Si eres un agente que trabaja **desde el VPS** (Claude Code, Codex), aquí está lo
que tienes que saber para usar ese Chrome tú solo, **sin pedirle nada al
operador** salvo que aparezca un login, una verificación o un CAPTCHA.

## 1. Qué hay

- Un **Chrome estable con pantalla virtual** que guarda las sesiones en su perfil
  (`/mnt/HC_Volume_106974679/navegador/perfil`; **no borrarlo**).
- Entra el operador desde **Accesos** en la app (`/accesos` → «Abrir navegador»)
  y **tú lo controlas por CDP** en `127.0.0.1:9222`. Los dos a la vez: lo que
  haces tú se ve en su pantalla.
- **Apagado no gasta nada.** Se enciende y se apaga a demanda; se apaga solo a
  los 45 min sin nadie conectado (ni VNC ni tú por CDP).

## 2. Encenderlo, mirarlo y apagarlo

```bash
navegador on        # enciende pantalla + Chrome + visor (tarda unos segundos)
navegador estado    # ¿está activo? MB que gasta Chrome y memoria libre
navegador json      # lo mismo en JSON, con las pestañas abiertas
navegador off       # apagar (libera 1-2 GB de RAM)
```

(Desde fuera del VPS: `ssh root@62.238.19.31 navegador on`.)

**Antes de encenderlo** mira que el servidor tenga aire: la cola de vídeos y
Chrome compiten por la RAM (8 GB). Con jobs `running` en la cola de montaje o
menos de ~2,5 GB disponibles, espera o no lo enciendas.

## 3. Controlarlo (`cdp.py`)

Playwright conectado al Chrome que ya está abierto (**nunca** lances otro Chrome:
no tendría la sesión). Ayudante ya instalado en `/home/nebulabsai/cdp.py`
(fuente: `deploy/navegador/cdp.py`), con su venv:

```bash
PY=/home/nebulabsai/nav-venv/bin/python
$PY /home/nebulabsai/cdp.py tabs                       # pestañas abiertas
$PY /home/nebulabsai/cdp.py open  <url>                # pestaña nueva
$PY /home/nebulabsai/cdp.py goto  <sub> <url>          # navegar ESA pestaña
$PY /home/nebulabsai/cdp.py shot  <sub> /tmp/x.png     # captura (mírala: es tu vista)
$PY /home/nebulabsai/cdp.py click <sub> <x> <y>        # coordenadas de la captura
$PY /home/nebulabsai/cdp.py wheel <sub> <x> <y> <dy>   # scroll
$PY /home/nebulabsai/cdp.py upload <sub> <fichero>     # sube al <input type=file>
$PY /home/nebulabsai/cdp.py paste <sub> <fich.txt>     # pega texto (contenteditable/inputs)
$PY /home/nebulabsai/cdp.py type|press <sub> <texto|tecla>
$PY /home/nebulabsai/cdp.py evalf <sub> <fich.js>      # JS de un fichero (evita líos de comillas)
$PY /home/nebulabsai/cdp.py close <sub>                # cerrar pestaña
```

`<sub>` es un trozo de la URL de la pestaña (`magnific.com`, `flow.google`,
`genaipro`). La ventana mide **1439×812**: las coordenadas salen de tus capturas.
Trae siempre la pestaña al frente (una en segundo plano no pinta y las capturas
se cuelgan). Para `paste`: hay que haber hecho `click` antes en el cuadro de texto.

## 4. Cuidar CPU y memoria (importante: es un servidor compartido)

El VPS tiene 8 GB y 4 CPU y ahí corren la API, la web y los montajes de vídeo.
Medido el 29-sep: **Chrome con el Space de Magnific abierto gasta 1,5-2 GB**;
Flow o GenAI Pro, ~0,5 GB cada uno. Chrome tiene tope de 2,2 GB y, si falta
memoria, muere él antes que la API.

- **Cerrar la ÚLTIMA pestaña cierra Chrome entero** (y el servicio queda apagado):
  si vas a seguir, abre la siguiente ANTES de cerrar la anterior, o termina con
  `navegador off`. `navegador on` lo reabre en Magnific.
- **UNA pestaña a la vez.** Abre la que necesitas, haz el trabajo y `close`
  antes de pasar a otra. No dejes Flow y el Space abiertos a la vez. Cerrar la
  pestaña no pierde la sesión (va en el perfil).
- **El Space de Magnific es lo que más pesa** (lista con 70+ vídeos). Recarga o
  cierra y reabre la pestaña entre tandas para soltar memoria; no la dejes horas
  abierta.
- **Vigila con `navegador estado`** al empezar, cada tanda y al acabar. Si
  Chrome pasa de ~2 GB o la memoria disponible baja de ~1,5 GB: cierra
  pestañas, y si sigue, `navegador off` y vuelve a `on`.
- **No hagas bucles de capturas** ni sondees cada segundo: cada captura cuesta
  CPU. Espera con calma (un clip de Kling tarda 5-30 min) y mira cada 30-60 s.
- **Al terminar todo: `navegador off`.** Si dejas trabajo a medias, dilo; se
  apaga solo a los 45 min sin uso, pero no cuentes con eso.

**Medido en la primera prueba real (29-sep, un clip de bolso):** encender + Space
abierto ≈ 1,6-2,0 GB de Chrome; con solo el Space y sin las otras pestañas ≈ 0,8-1,6 GB;
un clip de Kling tardó ~12 min (5 en cola + procesado); el mp4 en bruto pesa ~17 MB;
tras borrar y `navegador off` la RAM libre vuelve a ~4 GB.

## 5. Descargas y limpieza de disco

Todo lo que descargas (fotos de producto, imágenes generadas, clips) va al
**disco extra**, no al del sistema, y **se borra en cuanto ya no hace falta**:

- Carpeta de trabajo: `/mnt/HC_Volume_106974679/navegador/trabajo/<tanda>/` (créala
  tú). Chrome descarga en `.../navegador/descargas/` (caché de Chrome ≤200 MB).
- **Cuando un vídeo ya está subido y montado** (`estado(id=<job>)` → `done`),
  borra sus ficheros: imagen, clip en bruto, recodificado.
- **Al acabar la tanda**, borra la carpeta entera de la tanda y lo que quede en
  `descargas/` y `/tmp` (`rm -rf` solo de TUS ficheros; nunca `perfil/`).
- Con menos de ~10 GB libres en `df -h /mnt/HC_Volume_106974679`, borra ya, sin
  esperar al final de la tanda.
- Los vídeos definitivos viven en el Drive/la app (`subir_clip`), no aquí: en el
  VPS no se guarda nada «por si acaso».

## 6. El Space de los clips de Magnific (ya montado)

**«Copy of Copy of Foto con IA a Video»**:
`https://www.magnific.com/app/spaces/a2d7c31b-50c3-4cfa-812d-db143394e0f9?page=1`
(Kling 2.5 · 9:16 · 10 s · 720p, que es lo ilimitado). Lo abres tú con
`open`/`goto`; el operador no tiene que abrirlo. Pasos probados desde el VPS
(coordenadas con la ventana de 1439×812 y el Space al 66 %):

1. `goto magnific.com <url del Space>`; la **primera vez** sale una pantalla
   «Welcome»: «Skip overview» en (609, 702).
2. Clic en el nodo de entrada (475, 250) → «＋» (353, 348) → `upload` de la imagen
   → «Add» (1274, 726).
3. Modo selección ◎ en (541, 348) (la vista de cuadrícula está en (580, 348); si
   sale la lista, vuelve a la cuadrícula) → `wheel` hasta el final → deja marcada
   **solo** la imagen que toca (quita las demás con su casilla).
4. Clic en el texto del generador (930, 580) → `paste` del prompt de movimiento
   (`plan_producto` → `clips[0].prompt`) → clic en el título del generador
   (930, 200) para seleccionarlo → comprueba abajo **Kling 2.5 · 9:16 · 10s · 720p**.
5. ▶ en (843, 142). **Tandas de 2 clips** como mucho (la cola de Kling es de la
   cuenta y otros también la usan).
6. Espera preguntando a `/app/api/creations?limit=3` con `evalf` (estado
   `queued` → `processing` → `completed`, con `metadata.url` para bajar el mp4).
7. Baja el mp4 con `curl` a tu carpeta de trabajo, **revísalo fotograma a
   fotograma** (`revision-calidad.md`), recodifica (`ffmpeg -c:v libx264 -crf 21
   -an`) y sube con `subir_clip` (moda multimodo: **la cuenta de Ana**, ver
   `moda-mujer-multimodo.md`).

Las imágenes se generan en **Flow** (mismo procedimiento: proyecto nuevo, «＋» →
«Subir archivo» con la foto del producto, pegar el prompt, Enter, descargar 1K).
GenAI Pro solo como respaldo de vídeo en POV BOF Largo.

## 7. Reglas que no cambian

- Di cuántas imágenes y clips vas a lanzar y espera el «sí» (cuestan créditos).
- No toques ajustes de las cuentas ni cambies contraseñas.
- **Login, verificación de Google o CAPTCHA: para y avisa al operador**, que entra
  desde **Accesos** (móvil o PC). No los resuelvas tú ni pruebes contraseñas.
- No cierres la sesión de ninguna web ni borres cookies del perfil.
