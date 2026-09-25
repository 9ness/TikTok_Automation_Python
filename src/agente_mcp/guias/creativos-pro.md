# Creativos Pro — `/tiktok-shop-ai-pro/creativos-profesionales`

Lee antes [`README.md`](README.md) y las tres guías de [`comun/`](comun/).

## Qué sale

**No hay vídeo ni montaje.** Una **imagen publicitaria 3:4** por producto
(un creativo de anuncio), generada en **Google Flow (Nano Banana 2)**. No se
sube a la app: se deja en la carpeta y el operador la publica desde la
galería del móvil.

## Paso a paso

1. Abre `/tiktok-shop-ai-pro/creativos-profesionales` → «📁 Dónde trabajas»
   → catálogo → chip de la carpeta.
2. **Paso 1 (violeta) · «Preparar los textos»** → «Obtener textos (x/y)» si
   falta. «🏷️ IDs de producto… opcional · PC»: sáltalo.
3. **Paso 2 (fucsia) · «Generar el creativo fuera»**:
   1. **«Fotos de la ficha (N)»** (o «Con URL (N)») → baja las capturas de la
      **FICHA** (no la limpia): el creativo saca los beneficios de ahí y así
      no se inventa nada.
   2. **«Prompt imagen»** → el mismo para todos.
   3. Por producto, en Flow: imagen, Nano Banana 2, **3:4**, 1 resultado,
      adjunta su foto de ficha + pega → `creativo.png`.
   4. Revisa: producto idéntico al de la ficha, **ningún beneficio, cifra,
      precio u oferta que la ficha no diga**, texto bien escrito (sin letras
      inventadas), sin logos ajenos.
4. Guarda los buenos en `<Carpeta>/creativos/<nº>_<título>.png`.
5. **Paso 3 (azul) · «Publicar»** es del operador. «📤 Subido» solo si te lo
   pide.

## API útil (solo lectura)

- `GET /api/v1/nicho-creativos/prompt`
- `GET /api/v1/nicho-pov-bof/productos?source=<catálogo>&folder=<carpeta>`
  (comparte catálogo y textos con el POV BOF).

## Con el MCP

Con el MCP: `menu="creativos"`. `plan_producto` da el prompt y el formato 3:4; no hay nada que subir.
