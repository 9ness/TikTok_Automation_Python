# Catálogo común de edición (flechas CTA + estilos de subtítulos)

`catalogo.json` es la ÚNICA lista de flechas y estilos de subtítulos que usan:

| Quién | Qué lee | Dónde |
|---|---|---|
| Editor Auto (clientes de Nebulabs Media) | `editor_auto: true` | `editor_auto/services/style_mapper.py`, `tools/sticker_arrow.py` |
| Cuentas propias de TikTok Shop (POV BOF, Largo, Ropa…) | `tiktok_shop: true`, en ese orden | `tiktok_shop/pipeline/ready_video._ARROW_FILES` |
| Web de Nebulabs Media (selector del cliente) | `editor_auto: true` | `nebulabs-media/lib/catalogo-edicion.json` (exportado) |

Los `.mov` viven en el Drive: `Nebulabs/TikTok/TIKTOK_EDITOR/Assets/flechas/`.

## Nada entra solo (revisión a mano)
Un fichero que aparece en la carpeta sin estar en el catálogo no se ofrece a nadie.

```bash
export TIKTOK_EDITOR_ROOT_PATH=~/gdrive/Nebulabs/TikTok/TIKTOK_EDITOR   # fuera del contenedor
python3 scripts/catalogo_edicion.py pendientes                       # qué hay sin aprobar
python3 scripts/catalogo_edicion.py aprobar flecha_x.mov --grupo simple --color roja [--tiktok-shop]
python3 scripts/catalogo_edicion.py ocultar flecha_x.mov             # deja de ofrecerse al cliente
python3 scripts/catalogo_edicion.py web --repo ~/proyectos/nebulabs-media   # exportar a la web
```
Tras `web`: commit + push en nebulabs-media (Vercel despliega) y commit del
catálogo aquí + deploy de la API.

## Navidad
Las animaciones del acabado «regalo» del POV BOF (`nicho_pov_bof/pipeline/regalo.py`:
caja que se abre, nieve, lazo × 5 paletas) se renderizan como `.mov` con
`python3 scripts/catalogo_edicion.py navidad --salida <dir>` y se copian a
`Assets/flechas/`. Son `animacion: "entrada"`: se reproducen UNA vez desde que
aparece la flecha y se quedan en el último fotograma (sin bucle), con su
`colocacion` medida para señalar el carrito de TikTok. Sin sonido (el del
POV BOF se sintetiza aparte).

## Subtítulos
Cada estilo trae `web.css` (vista previa) y `motor` (claves de `subs_auto`:
text/hl/stroke/sw/mode/pill/font, `case`, `max_palabras`). Los `fruti-*` son
los de FrutiNovelas (`montar.py --subs rosa/chismes/verde`).
