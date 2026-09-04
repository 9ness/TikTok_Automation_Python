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
| Mapa general de la plataforma | ⬜ pendiente |
| Catálogo de productos (el que sustituye a los ZIP) | ⬜ pendiente |
| Formatos y prompts por nicho | ⬜ pendiente |
| Automatizaciones que trae la web | ⬜ pendiente |
| Qué usamos nosotros y qué no | ⬜ pendiente |

---

## 1. Mapa general

_(pendiente: qué secciones tiene el menú y para qué sirve cada una)_

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

_(pendiente: qué formatos publica para cada nicho y cuáles ya tenemos)_

**Lo que ya está copiado en el repo**, para no duplicar trabajo:

| Nuestro nicho | Prompts que vienen de la web |
|---|---|
| POV BOF | `src/nicho_pov_bof/prompts/guion_producto.md` |
| POV BOF Largo | `src/nicho_pov_bof_largo/prompts/guion.md`, `guion_dolor.md`, `guion_plazos.md` |
| Ropa (sin humanos / hombre-mujer) | `src/nicho_ropa/prompts/*.md` (espejo, percha, MOF 10s) |

## 4. Automatizaciones de la web

_(pendiente: qué automatiza ella. Interesa saber qué se solapa con lo que ya
tenemos montado y qué no)_

## 5. Qué usamos y qué no

_(pendiente: decisión por funcionalidad — la usamos, la ignoramos, o la
copiamos a nuestro flujo. Con el motivo, que es lo que se olvida)_
