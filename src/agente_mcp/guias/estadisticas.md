# Estadísticas de ventas (solo ness)

Pantalla `/estadisticas` (menú lateral, solo la ve `ness`): GMV, ventas,
impresiones y clics por mes, comisiones, conversión clics → ventas con su
previsión, día a día, y los productos con venta por tipo y país. Arriba,
«Última actualización»: la fecha de la última lectura.

Los datos NO salen de ninguna API: se leen de la app de TikTok en el móvil
(OPPO por ADB, ver `comun/` y la memoria del móvil) y se guardan con el MCP.

## Dónde se leen

1. Inicio de creador («¡Hola, Viva Shop!») → la flecha `>` junto a
   Hoy / Últimos 7 días → página **Datos**.
2. Filtro de fecha: Hoy · Ayer · 7D · **Personalizado** → Personalizado /
   Semana / **Mes** / Día → Listo.
3. **Datos clave › Resumen**: GMV atr., Ventas de artículos atr.,
   Impresiones del producto, Clics en el producto.
   **Datos clave › Comisiones**: GMV de comisiones, Artículos vendidos con
   comisión, Base de la comisión, Comisiones estimadas.
4. «El rendimiento de tus productos» → **Ver todo** → lista de productos del
   mismo periodo, ordenada por GMV. **Se lee hasta el primer «0 €» y se
   para**: lo de debajo no vendió y leerlo es perder el tiempo. Ojo, hay
   productos de otros países (ES, DE, IT, FR, NL…).
5. Día a día: **«Ver tendencias»** de Datos clave, con el mes puesto. Es una
   hoja con una gráfica por métrica (chips GMV atr. · Ventas de artículos ·
   Impresiones; **Clics** sale al deslizar los chips a la izquierda).

## Lo rápido: los scripts (`scripts/estadisticas_movil/`)

No lo hagas a mano: está todo resuelto y un mes tarda ~3 min.

- `mes.py MM` → `m_2026-MM.json`: Resumen + Comisiones + productos con venta.
- `tend.py MM` → `d_2026-MM.json`: GMV, ventas, impresiones y clics por día.
  **No toca día a día** (10 s por punto, 20 min al mes): hace UNA captura de
  cada gráfica y lee la altura de la línea en la columna de cada día
  (`graf.py`). La escala no se saca del eje (el OCR de sus etiquetas falla y
  el eje no siempre empieza en 0): se tocan el día más alto y uno de los
  planos de abajo y se leen sus valores exactos en la cabecera
  («may 13 | GMV atr. 124,74 €»). Dos capturas con el punto tocado en sitios
  distintos, porque el círculo y el globo del punto tapan la línea.
  Comprobado en mayo: suma de ventas 32 = total del mes, GMV ±0,5 %.
- `conv.py` junta los `m_*.json` en `doc.json` con números y `tipo`.

Trampas: las hojas inferiores (Tendencias, calendario) NO salen en
`uiautomator dump`; el dump a veces vuelve vacío (reintentar antes de creer
que no estás en Datos); la lista de productos va por GMV y el «0 €» lleva
espacio duro (`\xa0`); nunca `pkill -f` con un patrón que esté en tu propio
comando; si tocan el móvil a mitad, la pantalla queda en otra parte (los
scripts vuelven a Datos con BACK, y desde el inicio de creador con la flecha).

Lectura por texto: `uiautomator dump` + `exec-out cat` (más fiable que
mirar capturas). Al terminar: borrar `/sdcard/u.xml`, cerrar TikTok y
bloquear el móvil.

## Cómo se guardan

`guardar_estadisticas(meses=[...], dias=[...], cuenta="Viva Shop",
actualizado="AAAA-MM-DD", notas=[...])` — números, no texto («3,9K» → 3900).
Se fusiona por `mes` / `fecha`, así que basta con mandar lo nuevo. A cada
producto se le pone `tipo` (Suplementos, Hogar, Ropa, Calzado, Belleza,
Deporte, Muebles, Jardín, Electrónica…) a criterio por el título: TikTok no
da la categoría. `notas` son las conclusiones que salen en la pantalla.

`estadisticas_ventas()` devuelve lo guardado.
