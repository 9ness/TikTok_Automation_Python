# Mis tandas — guía para agentes

> Pantalla: `/tiktok-shop-ai-pro/mis-tandas` (la PRIMERA del menú «Tiktok Shop
> AI Pro», para ness, Mauro y Ana). Código: `src/mis_tandas/`,
> `src/api/routers/mis_tandas.py`, `frontend/components/tiktok-shop-ai-pro/MisTandas.tsx`.

## Qué es (y qué NO es)

Es la lista de **vídeos ya montados** del usuario, de **todos sus nichos**
(POV BOF, POV BOF Largo en cualquiera de sus modos, Moda Mujer · Multimodo),
de **diez en diez** y en el orden en que toca publicarlos. Cada tanda abierta
lleva una **fecha orientativa** (una tanda al día; si hoy ya hay 8 subidos,
empieza mañana) y su **época** («🍂 Otoño», «🎃 Halloween», «❄️ Invierno ·
Black Friday», «🎄 Navidad»).

**No es un nicho y no se le sube nada.** Tú sigues trabajando en el menú de
siempre (generar, `subir_clip`, montar). Cuando el vídeo queda montado en su
nicho, **aparece solo al final** de Mis tandas. No hay ninguna herramienta
para «añadir a Mis tandas», y no hace falta.

## Sincronía

Mis tandas no guarda estados propios. Cada botón escribe en el documento del
NICHO del vídeo:

| Botón | POV BOF | POV BOF Largo | Multimodo |
|---|---|---|---|
| ✓ Subido | `uploaded` del POV (y la cuota del día) | `uploaded` del Largo **en el modo del vídeo** | `/multimodo/subido` |
| 🚫 Sin stock | textos del POV (es del PRODUCTO: lo ven todos) | textos del POV | `/multimodo/sin-stock` |
| 🔁 Rehacer | — (el POV corto no tiene) | `rehacer` + nota | `/multimodo/rehacer` |

Marcar en Mis tandas = marcar en la pantalla del nicho, y al revés. `para_rehacer(menu)`
sigue sacando lo marcado para rehacer, se marque donde se marque.

Lo único propio es el **orden**: Redis `viralizacion:mis_tandas:orden:<usuario>`.
Se fija una vez y lo nuevo entra al final; marcar subido no mueve nada. En el
multimodo se respeta su propio orden (`multimodo:orden:<usuario>`), que
intercala formatos.

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
