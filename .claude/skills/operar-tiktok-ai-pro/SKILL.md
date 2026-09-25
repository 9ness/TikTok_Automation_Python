---
name: operar-tiktok-ai-pro
description: Hacer por el operador el trabajo de un menú de "Tiktok Shop AI Pro" en la web de la app (POV BOF, POV BOF Largo, Moda Mujer, Ropa Hombre, UGC, Carruseles, Creativos) — bajar fotos, generar imágenes y clips en Google Flow / GenAI Pro / Magnific, revisarlos, subirlos a editar y dejar los vídeos en una carpeta. Úsala cuando pidan "hazme la carpeta N de <nicho>", "genera las fotos/vídeos de…", "revisa estas fotos" o similar.
---

# Operar Tiktok Shop AI Pro

Las instrucciones están en las **guías para agentes**, que viven en el repo y
se sirven también en la app:

- Repo: `src/agente_mcp/guias/README.md`
- Web: `<URL de la app>/api/v1/agente/guias/README.md`

Pasos:

1. Lee `src/agente_mcp/guias/README.md` entero y las tres de `comun/`
   (`app.md`, `plataformas.md`, `revision-calidad.md`).
2. Lee la guía del menú que te piden (tabla del README).
3. Haz las **preguntas de arranque** del README (menú y modo, catálogo y
   carpeta, hasta dónde llegar, plataforma y duración del clip, qué productos)
   en UN mensaje, con opciones.
4. Antes de generar nada, di cuántas imágenes y clips vas a lanzar (cuestan
   créditos) y espera el «sí».
5. Revisa cada imagen y clip con `comun/revision-calidad.md` antes de subirlo.
6. Termina con el informe por producto que pide el README.

Si la pantalla no coincide con la guía, para y avisa: la guía se ha quedado
vieja y hay que actualizarla (`src/agente_mcp/guias/`).
