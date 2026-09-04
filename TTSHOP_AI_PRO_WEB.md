# La web del curso — TTShop AI Pro (`ttshopaiproapp.com`)

> **Para qué es este documento.** La plataforma del curso está detrás del
> usuario y la contraseña del operador, así que **ningún agente puede entrar a
> mirarla**. Todo lo que sabemos de ella se escribe aquí, a partir de las
> capturas y explicaciones que pasa el operador. Si algo de nuestro código
> copia un prompt, una convención de nombres o un formato de esa web, el
> "porqué" vive aquí.
>
> Se va renovando: la web crece y este documento va detrás. Al añadir algo,
> poner la FECHA — así se sabe qué es viejo cuando algo deje de cuadrar.

**Acceso:** `https://ttshopaiproapp.com` (se entra desde Skool). Disponible
desde el 4 de septiembre de 2026, sustituye a la web anterior de la que salen
los ZIP de productos y las fichas que se pegan hoy.

---

## Estado de esta documentación

| Sección | Estado |
|---|---|
| Mapa general de la plataforma | ✅ los 10 pasos de su guía |
| Catálogo de productos (el que sustituye a los ZIP) | ⬜ pendiente |
| Formatos y prompts por nicho | ✅ las 5 categorías y los 11 formatos; ⬜ falta el texto de cada prompt |
| Automatizaciones que trae la web | 🟨 lo esencial (qué es gratis y qué se paga) |
| Qué usamos nosotros y qué no | ⬜ pendiente |

---

## 1. Mapa general

_Documentado a partir de la propia guía de la plataforma ("GUÍA DE LA
PLATAFORMA", 10 pasos), que se puede saltar y volver a abrir._

### La barra de arriba (4 sep 2026)

De izquierda a derecha, con el usuario ya dentro:

| Botón | Para qué |
|---|---|
| Avatar + "Bienvenido, \<nombre\>" | La cuenta con la que se entra. |
| 🏠 **Inicio** | El panel principal. |
| 💳 **Membresía** | El plan contratado. |
| 👤 **Mi perfil** | Los datos del alumno. |
| 💰 **Saldo `0,00 US$`** | Monedero de la plataforma. Se compran **servicios, vídeos y recursos** con él, así que hay cosas de pago aparte de la membresía. |
| ◆ **Alumno Premium** | El nivel de la cuenta. Lo que se ve en el panel **depende de la membresía y del perfil**. |
| 🔔 | Avisos. |
| 🌐 EN | Idioma. |
| **Salir** | Cerrar sesión. |

En una cinta arriba del todo van rotando tres reclamos, que ya dicen por dónde
va la plataforma:

- «PREMIUM · Crea guiones y carruseles profesionales con inteligencia artificial»
- «Compra servicios, vídeos y recursos directamente desde tu saldo»
- «Participa en la comunidad privada y consulta tus menciones»

### Paso 1 de 10 — Panel principal

> "Este es tu centro de control privado. Los botones disponibles **se adaptan
> automáticamente a tu membresía y a tu perfil**."

Etiquetas del paso: `Tus herramientas`, `Acceso privado`, `Siempre
disponible`.

**Lo que interesa a efectos nuestros:** el panel es *variable* según el plan.
Cualquier cosa que documentemos aquí puede no estar en otra cuenta, así que
conviene apuntar con qué membresía se vio (aquí: **Alumno Premium**).

### Cómo se saca esto sin poder entrar (4 sep 2026)

Ningún agente puede mirar la web (está tras el login), así que el mapa se
extrae con un pegote en la consola y se pega aquí. Lo que hay que saber de su
DOM para no empezar de cero cada vez:

- La navegación es una SPA sin rutas: cada tarjeta es `div.mod[data-vista]`
  (`mi-area`, `alumno-comunidad`, `asistente`, `alumno-compras`, y dentro
  `prompts`, `guiones`, `carruseles`, `resumenes`, `ia`). Se navega
  haciendo `click()` en ellas y se vuelve con `#btnHome`.
- El contenido de la pantalla vive siempre en `#main`.
- **El segundo nivel no siempre son `.mod`**: en Mi Área, Comunidad y Compras
  las tarjetas son `<button>` sueltos, así que un crawler que busque solo
  `.mod` se queda en la puerta.
- Chrome bloquea el primer pegado en la consola: hay que escribir a mano
  `allow pasting` una vez por perfil.

### El menú de verdad (4 sep 2026)

La guía de 10 pasos vende la plataforma; el menú real es **cuatro secciones**
en el panel principal, cada una con sus tarjetas. Ojo: **"Productos" NO es una
sección de primer nivel** — cuelga de Comunidad.

```
Inicio
├── 👤 Mi Área ......... perfil, saldo, membresía y configuración
│   ├── Mis creaciones ......... vídeos generados listos para descargar y publicar
│   ├── Mi perfil .............. datos personales, foto y privacidad
│   ├── Saldo .................. recarga y saldo disponible
│   ├── Mis compras ............ compras activas y en preparación
│   ├── Pedidos y entregas ..... pedidos completados y descargas
│   ├── Membresía .............. gestiona la membresía en Skool
│   ├── Programa de afiliados .. invitaciones y recompensas recurrentes
│   ├── Centro legal ........... condiciones, privacidad y reglas del servicio
│   └── Mis guiones ............ historial, escenas y REVISIÓN DE SEGURIDAD
│
├── 💬 Comunidad ....... chat, productos, ranking, eventos y recursos
│   ├── Productos .............. productos seleccionados e inventarios organizados
│   ├── Chat General ........... chat privado en directo para Alumnos Premium
│   ├── Comunidad Skool ........ abre la comunidad oficial
│   ├── Ranking de creadores ... clasificación privada de rendimiento mensual
│   ├── Peticiones de mejora ... enviar ideas para mejorar la plataforma
│   ├── Eventos presenciales
│   ├── Sanciones y normativa .. actualizaciones oficiales y prácticas seguras
│   └── Calendario ............. llamadas y eventos publicados
│
├── 🤖 Asistente IA .... vídeos, guiones, carruseles, resúmenes y plataformas
│   ├── Generador de vídeos .... formatos y generación MANUAL o AUTOMÁTICA guiada
│   ├── Generador de guiones ... guiones de venta, ideas y planes de grabación
│   ├── Generador de carruseles  carruseles interactivos listos para TikTok Shop
│   ├── Resumen IA ............. resúmenes de la comunidad y llamadas semanales
│   └── Plataformas AI ......... herramientas recomendadas y enlaces de afiliación
│
└── 🛒 Compras ......... servicios, generaciones adicionales, pedidos y entregas
    ├── Vídeos de IA ........... packs de vídeos generados con IA
    ├── Generaciones adicionales  generaciones ACUMULABLES de guiones
    ├── Automatizaciones ....... automatización GESTIONADA de cuentas
    └── Estrategias de viralización  packs de contenido para escalar
```

**Lo que se lee entre líneas, y hay que confirmar:**

- **Las generaciones de guiones están limitadas** — si se venden "generaciones
  adicionales acumulables", la membresía trae una cuota. Nosotros generamos
  con nuestra propia clave de Gemini, sin tope suyo.
- **"Automatización gestionada de cuentas"** suena a servicio con personas
  detrás, no a herramienta que se usa. Preguntar qué hace exactamente antes de
  compararlo con nuestra cola.
- **Mis guiones → "revisión de seguridad"**: parece que pasan los guiones por
  un filtro de políticas. Interesa ver qué marcan: nosotros ya avisamos de
  captions arriesgados (`caption_arriesgado`) y de promesas que el producto no
  cumple.
- El panel de **Inicio** enseña las dos banderas (🇪🇸 🇺🇸): la plataforma es
  de los dos mercados, aunque nosotros nos quedemos con España.

### Paso 2 de 10 — Productos

> "Encuentra productos seleccionados. Consulta **inventarios de España y
> Estados Unidos** organizados por **categorías y carpetas**."

Etiquetas: `Inventarios`, `España y USA`, `GMV Max`.

**Ojo:** hay inventario de **Estados Unidos**, no solo de España. Todo lo
nuestro asume España (precios en €, "Productos España", las CTA en español).
Si algún día se trabaja el de USA, no vale con traducir: cambian la moneda,
las promesas de la ficha (plazos, envío) y el idioma del guion.

Y aparece **GMV Max**, que es la estrategia que ya persigue nuestro Radar de
Productos (`tiktok_shop/services/ads_signal.py`): productos con ADS inyectados
y pocos creadores.

### Paso 3 de 10 — Guiones

> "Guiones TOF y BOF. Accede a guiones orientados a captar atención, convertir
> y aumentar tus ventas."

Etiquetas: `TOF`, `BOF`, `Ventas`.

**Nuevo para nosotros:** lo que tenemos montado es todo **BOF** (el producto
en primer plano, urgencia de precio, CTA al carrito). Los **TOF** —captar
atención arriba del embudo— no existen en el repo.

### Paso 4 de 10 — Prompts / Formatos

> "Crea contenido con IA. Consulta **prompts, formatos, ejemplos y
> categorías** para producir contenido con inteligencia artificial."

Etiquetas: `Prompts`, `Formatos`, `Ejemplos`.

Esta es **la sección de la que salen los prompts que ya están copiados en el
repo** (tabla de arriba). Al mirarla hay que anotar qué formatos hay hoy y
cuáles nos faltan — es lo que decide si un nicho necesita modos nuevos.

### Paso 5 de 10 — Compras (servicios y recursos)

> "Compra **vídeos de IA, estrategias de viralización y automatizaciones**, y
> consulta después tus entregas."

Etiquetas: `Vídeos IA`, `Automatizaciones`, `Mis compras`.

Aquí es donde se gasta el **saldo en dólares** de la barra de arriba. Es la
parte de pago por uso, y la que hay que mirar con cuidado: buena parte de eso
—generar el vídeo, montar, publicar— ya lo hacemos nosotros sin pagar por
unidad. Antes de comprar nada, comparar con lo que ya está montado.

### Paso 6 de 10 — Ranking de creadores

> "Consulta la clasificación por **GMV** manteniendo protegida la identidad
> real de los perfiles de TikTok."

Etiquetas: `GMV`, `Privacidad`, `Clasificación`.

Es una clasificación entre alumnos, no una fuente de productos. No afecta al
código; sirve para comparar resultados.

### Paso 7 de 10 — Comunidad (chat de alumnos)

> "Chat privado de alumnos. Participa en el chat general, comparte avances y
> recibe menciones y notificaciones."

Etiquetas: `Chat en directo`, `Menciones`, `Comunidad`. Es la campana de la
barra de arriba.

### Paso 8 de 10 — Comunidad Skool (formación y soporte)

> "Accede directamente a la comunidad de Skool, sus contenidos y el
> acompañamiento del equipo."

Etiquetas: `Formación`, `Soporte`, `Llamadas`. El curso en sí sigue viviendo
en Skool; la plataforma es la herramienta.

### Paso 9 de 10 — Saldo recargable

> "Recarga y utiliza tu saldo disponible para realizar compras dentro de
> TTShop AI Pro."

Etiquetas: `Recargas`, `Compras`, `Historial`. Es el monedero que gasta la
sección de Compras (paso 5).

### Paso 10 de 10 — Mi perfil

> "Cambia tu nombre, fotografía y contraseña, y **administra los perfiles
> vinculados**."

Etiquetas: `Datos`, `Fotografía`, `Seguridad`.

Lo de los **perfiles vinculados** conviene mirarlo: nosotros trabajamos con
varias cuentas de TikTok (el progreso y el escaparate van por usuario —
`ness`, `ana`, `mauro`), y si su plataforma también las contempla, puede que
haya algo que cruzar.

## 2. Catálogo de productos

_(pendiente: cómo se navegan y descargan los productos, en qué formato salen,
si sigue habiendo ZIP y con qué convención de nombres)_

**Lo que hoy da por hecho nuestro código** — hay que confirmarlo contra la web
nueva antes de tocar nada:

- Los ZIP traen las fotos con la convención AL REVÉS de la nuestra: `N` es la
  captura de la ficha y `N.1` la foto limpia
  (`nicho_pov_bof/services/productos_web.py`).
- Las carpetas son de diez productos y se llaman como el ZIP (`Carpeta 26`).
- Las fichas de TikTok se traen copiando el DOM de su listado y pegándolo
  (`POST /api/v1/nicho-pov-bof/urls/importar`).

## 3. Formatos y prompts por nicho

### Lo que hay dentro de "Prompts/Formatos" (4 sep 2026)

`Asistente IA › Generador de vídeos` NO es un generador: es el catálogo de
formatos, agrupados en cinco categorías, cada una con sus vídeos de ejemplo.
El número dice cuántos formatos tiene hoy — o sea, cuánto queda por copiar:

| Categoría | Formatos | Nuestro nicho |
|---|---|---|
| 👔 Moda Hombre | 4 | Ropa Mujer/Hombre (`nicho_ropa`, género `hombre_web`) |
| 👗 Moda Mujer | 2 | Ropa (mujer) — el del espejo y el de percha |
| 🎥 Nichos POV | 4 | POV BOF, POV BOF Largo, BOF Cine |
| 🧿 Nicho General | 0 | vacío — aún no ha publicado nada |
| 🎨 Creativos y Carruseles | 1 | Creativos Pro y Carruseles |

### Los 11 formatos, uno a uno (4 sep 2026)

`Asistente IA › 🎬 Generador de vídeos` → categoría. El **prompt de cada
formato no está en el DOM**: la tarjeta solo trae el vídeo de ejemplo y los
botones ▶ / ⛶, así que hay que abrirlo y copiarlo a mano — un crawler no lo
saca.

| Categoría | Formato | Nuestro equivalente |
|---|---|---|
| 👔 Moda Hombre | BOF Frente a Espejo 10s | `nicho_ropa` espejo (`hombre_web`) |
| 👔 Moda Hombre | BOF Selfie 10s | ⬜ no lo tenemos |
| 👔 Moda Hombre | Situación Real 1 10s | ⬜ no lo tenemos |
| 👔 Moda Hombre | Situación Real 2 10s | ⬜ no lo tenemos |
| 👗 Moda Mujer | MOF MUJER 10s FRENTE A ESPEJO (imagen→vídeo, ONMI) | `nicho_ropa` espejo (`mujer_web`) |
| 👗 Moda Mujer | BOLSO MOF MUJER POV ONMI 10S | ⬜ no lo tenemos |
| 🎥 Nichos POV | POV MOF ESP/USA 20 SEGUNDOS GANCHO PUNTO DE DOLOR | `nicho_pov_bof_largo/prompts/guion_dolor.md` |
| 🎥 Nichos POV | POV MOF ESP/USA 20 SEGUNDOS GANCHO URGENCIA DE PRECIO | `nicho_pov_bof_largo/prompts/guion.md` |
| 🎥 Nichos POV | POV/BOF 10 SEGUNDOS ONMI | `nicho_pov_bof/prompts/guion_producto.md` |
| 🎥 Nichos POV | POV/BOF ESPAÑA PLANTILLA | ⬜ por contrastar |
| 🎨 Creativos y Carruseles | CREATIVOS PUBLICITARIOS | Creativos Pro |
| 🧿 Nicho General | _(vacío, 0 formatos)_ | — |

Los dos ganchos del POV MOF de 20s son exactamente los dos estilos del POV
BOF Largo (`ESTILOS_GUION`), y confirman que ese formato es de 20 segundos —
por eso el vídeo son DOS clips y no uno.

### Volcados del mapa

`docs/web-curso/mapa-<fecha>.json` — cada pantalla con su `firma` (hash de su
texto). Para ver si han cambiado cosas, se saca otro volcado y se comparan las
firmas; no hay que releer nada. El del 4 sep 2026: 31 pantallas únicas de 172
rutas recorridas (la misma vista se alcanza por varios caminos).

### Cuotas de su generador (no nos afectan, pero explican su negocio)

- **Guiones: 120 al mes** (`Asistente IA › Generador de guiones`).
- **Carruseles: 31 al mes** (uno al día, `Generador de carruseles`).
- **Resumen IA**: la pantalla está hecha pero sin datos — "falta activar su
  actualización de base de datos".

Nosotros generamos con nuestra clave de Gemini, así que estos topes solo
importan para saber qué venden como "generaciones adicionales acumulables".

### Plataformas AI que recomienda (enlaces de afiliado suyos)

FLOW · DEEPSEEK · KLING · VMOS CLOUD · ADSPOWER · **FISH AUDIOS** — esta
última es la que ya usamos para la voz del POV BOF Largo (`FISH_API_KEY`).

**Lo que ya está copiado en el repo**, para no duplicar trabajo:

| Nuestro nicho | Prompts que vienen de la web |
|---|---|
| POV BOF | `src/nicho_pov_bof/prompts/guion_producto.md` |
| POV BOF Largo | `src/nicho_pov_bof_largo/prompts/guion.md`, `guion_dolor.md`, `guion_plazos.md` |
| Ropa (sin humanos / hombre-mujer) | `src/nicho_ropa/prompts/*.md` (espejo, percha, MOF 10s) |

## 4. Automatizaciones de la web

### Lo GRATIS es todo el método (4 sep 2026)

Con el curso pagado, la plataforma da **los prompts y todo lo necesario para
hacerlo a mano**. No hay que pagar nada para trabajar: se copian los prompts,
se generan los vídeos por tu cuenta y se publica. Es exactamente de donde sale
lo que ya tenemos copiado en el repo.

### Lo de PAGO es delegar el trabajo, no desbloquear funciones

Lo que se compra con el saldo en dólares no son funciones extra, sino que
**otro haga el trabajo**:

| Lo que vendes | Qué es en realidad |
|---|---|
| **Packs de vídeos de IA** | Alguien te genera los vídeos que tú harías a mano. Se paga por no hacerlos. |
| **Estrategias de viralización** | Packs de contenido ya preparados para escalar. |
| **Automatizaciones** | Un **móvil en la nube** configurado, y alguien que sube el contenido a ese móvil: la cuenta queda automatizada al 100%. |
| Generaciones adicionales | Generaciones acumulables de guiones _(por confirmar si hay cuota en su generador)_. |

**Por qué esto nos importa poco por ahora:** vamos por delante. El editor ya
está montado y el tiempo que ahorra es justo lo que se compra en los packs de
vídeos. Pagar por eso sería pagar por lo que ya tenemos.

El **móvil en la nube** es otra historia — automatizar la publicación al 100%
es lo único que hoy no hacemos—, pero es para más adelante.

## 5. Qué usamos y qué no

Decisiones tomadas, con su motivo. Lo que no esté aquí es que aún no se ha
mirado.

| Funcionalidad suya | Decisión | Por qué |
|---|---|---|
| **Inventario de Estados Unidos** | ❌ No, por ahora (4 sep 2026) | Se sigue solo con España hasta escalar a buenos números con varias cuentas. Todo lo nuestro asume España: precios en €, plazos y envío de la ficha española, guiones en español. |
| **Guiones TOF** | 🔎 Por comprobar | La sospecha del operador es que su TOF equivale a nuestro **POV BOF Largo**. Hay que comparar los textos antes de dar por hecho que falta algo. |
| Ranking de creadores | ➖ Informativo | Clasificación entre alumnos, no toca el código. |
| Comunidad y Skool | ➖ Informativo | Formación y soporte, fuera del flujo de trabajo. |
| **Packs de vídeos de IA** (de pago) | ❌ No (4 sep 2026) | Se paga por que otro genere los vídeos. Nuestro editor ya ahorra ese tiempo: sería pagar por lo que ya tenemos montado. |
| **Estrategias de viralización** (packs) | ❌ No, por ahora | Mismo motivo: contenido preparado que ya sabemos producir. |
| **Automatizaciones** (móvil en la nube + alguien subiendo) | ⏸️ Más adelante | Es lo ÚNICO que hoy no hacemos: publicar solo, al 100%. Interesa cuando el cuello de botella sea publicar y no producir. |
| Prompts y método a mano | ✅ Sí, es lo que usamos | Va incluido con el curso; de ahí salen los prompts del repo. |
