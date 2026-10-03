# Mis tandas — guía para agentes

> Pantalla: `/tiktok-shop-ai-pro/mis-tandas` (la PRIMERA del menú «Tiktok Shop
> AI Pro», para ness, Mauro y Ana). Código: `src/mis_tandas/`,
> `src/api/routers/mis_tandas.py`, `frontend/components/tiktok-shop-ai-pro/MisTandas.tsx`.

## Qué es (y qué NO es)

Es la lista de **vídeos ya montados** del usuario, de **todos sus nichos**
(POV BOF, POV BOF Largo en cualquiera de sus modos, Moda Mujer · Multimodo y
Moda Mujer · Aleatorios —Tienda Colores, Calle Dividido…—),
de **diez en diez** y en el orden en que toca publicarlos. Cada tanda abierta
lleva una **fecha orientativa** (una tanda al día; si hoy ya hay 8 subidos,
empieza mañana) y su **época** («🍂 Otoño», «🎃 Halloween», «❄️ Invierno ·
Black Friday», «🎄 Navidad»).

**No es un nicho y no se le sube nada.** Tú sigues trabajando en el menú de
siempre (generar, `subir_clip`, montar). Cuando el vídeo queda montado en su
nicho, **aparece solo al final** de Mis tandas. No hay ninguna herramienta
para «añadir a Mis tandas», y no hace falta.

## Cómo se reparte (calendario)

El orden de base es fijo (lo nuevo entra al final), con tres reglas que lo
ajustan sin bloquear a los demás:
- **Fecha mínima de las carpetas especiales** (`desde` en
  `nicho_pov_bof.config.CARPETAS_ESPECIALES`: Épico Octubre 3 oct, Venta
  Inversa 6 oct, Productos Q4 28 oct). Nada se pone en una tanda anterior, y en
  cuanto llega su día **tiene prioridad** sobre lo normal (caduca). Calendario:
  `docs/CALENDARIO_POV_BOF_LARGO.md`.
- **El mismo producto no sale dos veces en menos de 7 días**
  (`SEPARACION_MISMO_PRODUCTO`): otro modo del Largo, la copia de Q4… El
  segundo espera. Cuenta también lo ya subido.
- **Las tandas que se enseñan quedan FIJADAS** (`mis_tandas:fijas:<usuario>`:
  las dos primeras abiertas y toda tanda llena). Un vídeo **no sale nunca** de
  su tanda: subido o sin stock se queda en su sitio con su marca y NO entra uno
  de la siguiente (el operador ya la ha bajado). Lo nuevo va siempre detrás.
- **Única excepción: rehacer.** Marcado para rehacer sigue en su tanda (con
  🔁); cuando se vuelve a montar (sube su `video_listo_at`) sale de ella y
  entra en una tanda nueva.
- **Una tanda solo se cierra con «Tanda completada»**: aunque esté toda subida
  sigue a la vista hasta que el operador la complete.
- **Lo que aún no está en ninguna tanda y está sin stock no ocupa sitio**: sale
  en «⏳ Esperando stock» y, al quitarle el 🚫, entra en la siguiente que toque.

Por eso puede haber tandas de menos de 10 al final (lo que espera su fecha).

## Sincronía

Mis tandas no guarda estados propios. Cada botón escribe en el documento del
NICHO del vídeo:

| Botón | POV BOF | POV BOF Largo | Multimodo y Aleatorios |
|---|---|---|---|
| ✓ Subido | `uploaded` del POV (y la cuota del día) | `uploaded` del Largo **en el modo del vídeo** | `/multimodo/subido` |
| 🚫 Sin stock | textos del POV (es del PRODUCTO: lo ven todos) | textos del POV | `/multimodo/sin-stock` |
| 🔁 Rehacer | — (el POV corto no tiene) | `rehacer` + nota | `/multimodo/rehacer` (Aleatorios: no tiene) |

Marcar en Mis tandas = marcar en la pantalla del nicho, y al revés. `para_rehacer(menu)`
sigue sacando lo marcado para rehacer, se marque donde se marque.

Lo único propio es el **orden**: Redis `viralizacion:mis_tandas:orden:<usuario>`.
Se fija una vez y lo nuevo entra al final; marcar subido no mueve nada. En el
multimodo se respeta su propio orden (`multimodo:orden:<usuario>`), que
intercala formatos.

## Quitar de la lista

Lo que el operador ya no va a subir (p. ej. vídeos viejos del POV BOF) se
**quita** con el botón 👁‍🗨 de la fila (pide confirmación): sale de las tandas
y su hueco lo ocupa el siguiente. No se borra nada del nicho. «Ver los N
quitados» los lista con «Devolver». Se guarda por usuario en
`viralizacion:mis_tandas:ocultos:<usuario>`. MCP: `marcar_tanda(id, quitar=True)`.

## Tanda completada

Botón «✓ Tanda completada» en la cabecera (pide confirmación): CIERRA la tanda
y la siguiente queda la primera (`POST /api/v1/mis-tandas/completar {ids}`
con TODOS los de la tanda). **No marca nada como subido**: lo que no se subió
se queda sin subir dentro de esa tanda («Ver las N tandas cerradas»), y ahí
sigue teniendo su botón Subido. Un agente no lo usa salvo que el operador lo
pida.

## Descargas

Cada fila baja su vídeo con un enlace normal (como el POV BOF Largo): se
pueden pedir varios a la vez. La cabecera de la tanda tiene **Todos (N)** y
**Pendientes (M)** (solo lo que falta por subir); lo sin stock no se baja.

## Colores

Cada vídeo enseña su **nicho** (píldora fuerte), su **modo o estilo**
(píldora suave: Largo precio ámbar, dolor rosa, épico rojo, venta inversa
turquesa; en el multimodo un color por familia: espejo, camisetas,
zapatillas, zapatos, botas, bolsos, zapatillas 20 s) y su **catálogo**
(píldora con borde: Inventario General, Productos Web, Mujer zapatos, Mujer
accesorios…). La cabecera de cada tanda resume cuántos lleva de cada modo.

**Si creas un modo nuevo** (estilo de guion, formato del multimodo) o metes
un nicho nuevo en Mis tandas, **asígnale color** en
`frontend/lib/tiktok-shop-ai-pro/coloresModo.ts` en el mismo cambio:
`tests/mis_tandas/test_colores.py` falla si no.

## Con el MCP

- `mis_tandas()` — las tandas abiertas con sus vídeos: `id`, nicho, modo,
  catálogo (`source`), carpeta, producto, título, caption, `product_url`,
  estados y `descargar` (enlace directo al MP4). `todas=True` trae también
  las ya subidas; `fresco=True` relee los nichos (si acabas de montar algo y
  aún no sale: la lista se recuerda ~45 s).
- `marcar_tanda(id, subido=…, sin_stock=…, rehacer=…, nota_rehacer=…)` —
  **solo si el operador te lo pide**. Subido es lo que ha publicado ÉL.

Para rehacer un vídeo que el operador marcó aquí: con su `nicho`, `source`,
`carpeta` y `producto` vas a su menú (`plan_producto`) como siempre. Al
montarse el vídeo nuevo, se quita el «rehacer» y conserva su puesto en la tanda.

## Lo que no entra (todavía)

UGC (Nicho General), BOF Cinematográfico, Cuenta Piloto, Ropa con Personas,
los otros modos de Moda Mujer y Ropa Hombre: o no guardan «subido» por
usuario o no tienen fecha de montaje. Si el operador los quiere aquí, se
añade un lector en `src/mis_tandas/fuentes.py`.

## Moda Mujer · Aleatorios (id `alea|carpeta|producto|modo`)

Los vídeos de los modos de Moda Mujer que **no** son del multimodo (los que
hablan: Tienda Colores, Calle Dividido…). Uno por producto y modo. El
«subido» y el «sin stock» son del **producto** (los mismos campos que el
multimodo): si un producto tiene vídeo en los dos, al marcar uno queda el
otro, y el reparto los separa 7 días como a cualquier producto repetido.
Al aparecer se **intercalan** en lo pendiente, uno cada `ALEA_CADA` (5),
sin tocar las `ALEA_SIN_TOCAR` (2) primeras tandas abiertas, que el operador
puede tener ya bajadas.

