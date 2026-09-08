# Web del curso — TTShop AI Pro (`ttshopaiproapp.com`)

> La web de Jonny (el curso). Es de dónde salen los ZIP de productos, los
> enlaces de ficha y los prompts que usa el Programa 4. Recorrida el
> 2026-09-08 con la cuenta `ness` (Alumno Premium). Actualízalo si cambia.

Es una SPA con rutas por hash (`#…`). Los enlaces de abajo abren la pantalla
directamente; los clics sobre tarjetas fallan a la primera tras cargar (hay
que esperar ~2s o clicar dos veces).

---

## Mapa de menús

| Menú | Hash | Qué hay |
|---|---|---|
| Inicio | `/` | 4 bloques: Mi Área · Comunidad · Asistente IA · Compras. Campana con 2 pestañas (Comunidad / Mis compras). "Guía del panel" abajo a la izquierda |
| Mi Área | `#mi-area` | Mis creaciones (`#mis-creaciones`, vídeos generados en su web), Mi perfil, Saldo, Mis compras, Pedidos y entregas, Membresía (abre Skool), Programa de afiliados (`#afiliados`, "falta activar BD"), Centro legal, Mis guiones |
| Comunidad | `#alumno-comunidad` | **Productos** (`#productos`), Chat General, Comunidad Skool, **Ranking de creadores** (`#ranking`, GMV mensual estimado por alumno; ness 3º con 380 US$), **Peticiones de mejora** (`#mejoras`), Eventos presenciales, Sanciones y normativa (`#sanciones`, vacío), Calendario (`#calendario-comunidad`, vacío), Mensajes directos |
| Asistente IA | `#asistente` | **Generador de vídeos = Prompts/Formatos** (`#prompts`), Generador de guiones (`#guiones`, **120 generaciones/mes gratis**, sin usar), Revisor de guiones externos (`#revisor-guiones`, ES/US, 15.000 car.), Generador de carruseles (BLOQUEADO para Premium), Resumen IA, Plataformas AI (`#ia`: Flow, DeepSeek, Kling, Vmos Cloud, AdsPower, Fish Audios — enlaces de afiliado) |
| Compras | `#compras` | Nueva compra (`#compras/nueva`), Mis compras, Pasar a VIP (1.999 € Hotmart, Lifetime) |

## Productos (inventarios)

`#productos` → país (`esp` / `usa`) → inventario → carpetas.

| Inventario | Hash | Estado 2026-09-08 |
|---|---|---|
| España · Inventario General | `#panel/esp/general` | 31 carpetas × 10 (la 31 con 8) |
| España · Moda Mujer | `#panel/esp/mujer` (sub: Ropa / Zapatos / Accesorios) | 27 carpetas de ropa |
| España · Moda Hombre | `#panel/esp/hombre` | 2 carpetas (la 2 con 1 producto) |
| USA · Inventario General | `#panel/usa/general` | 12 carpetas (la 12 con 2) |
| USA · Moda Mujer / Hombre | `#productos/usa/mujer` … | Sub: Ropa / Zapatos / Accesorios |

Cada carpeta: cabecera **acordeón** (abrir una cierra la anterior y REPINTA
la lista) + botón "⬇ Descargar carpeta" (el ZIP) + "N productos". Dentro, por
producto: `Producto N`, dos fotos (limpia + ficha con precio), botón
"Producto" (descarga sus fotos) y enlace "🛍️ TikTok" (`a.chip[href]`). Si
está agotado pone "SIN STOCK" en vez del enlace; si Jonny no ha puesto ficha,
no hay ni enlace ni cartel.

**Lo que NO tiene** (base de las peticiones de mejora): fecha o etiqueta
"nuevo/actualizado" por carpeta o producto, "Descargar todo", buscador,
"expandir todo", fecha en el SIN STOCK, aviso en la campana de catálogo o
prompts, título/tienda/precio como texto.

Cómo entra en nuestra app:
- **ZIP** → `productos_web.importar_zip` (POV BOF, fuente `productos_web`) y
  `prendas_web.importar_zip` (Ropa, `mujer_web__Carpeta N`). Convención del
  ZIP AL REVÉS de la nuestra: `N.png` = ficha, `N.1.jpeg` = limpia.
- **Enlaces y stock** → pegote de consola (`PanelUrls.tsx:GUION`) que recorre
  `div.carp` → `.carp-head b` / `.prod` → `.p-head b` + `a.chip[href]` +
  texto "SIN STOCK", baja `fichas.json` y se sube en Configuración →
  `/urls/importar`. Mujer y hombre numeran igual: el género lo pone el
  selector, no el pegote.

## Prompts / Formatos (`#prompts`)

| Categoría | Hash | Formatos |
|---|---|---|
| Moda Mujer | `#prompts/mujer` | BOF Frente a Espejo 10s · BOF Selfie 10s · Situación Real 1 10s · Situación Real 2 10s · Zapatillas Vista POV 20s · Zapatillas Vista Sentado 20s · Gafas en Coche 10s · Camisetas Sarcásticas 10s · Camiseta Maniquí 10s |
| Moda Hombre | `#prompts/hombre` | Los mismos 9 títulos |
| Nichos POV | `#prompts/pov` | POV MOF ESP/USA 20s Gancho **Punto de Dolor** · POV MOF ESP/USA 20s Gancho **Urgencia de Precio** |
| Nicho General | `#prompts/general` | UGC Desde 0 Gancho Punto de Dolor |

Cada formato es una tarjeta con vídeo de ejemplo. Al abrirla: selector de
producto del inventario (Carpeta N · Producto M, con "Descargar fotos" y
"Abrir TikTok"), botón "Prompts Vídeo del formato" y **"Generar · Próximamente"**
— Jonny va a montar el vídeo dentro de su web. Sin versión ni fecha en los
prompts. Aviso fijo: mezclar formatos, no más de 10 vídeos/día.

Lo que ya tenemos en `src/*/prompts/` sale de aquí y de los `.docx` del Drive
(ver `tasks.md`, "Drive Productos España"); lo que no publica (MOF móvil
mujer, gancho de dolor en 10s) está DERIVADO por nosotros.

## Compras (`#compras/nueva`) — precios USD, pago Stripe

| Servicio | Hash | Precio |
|---|---|---|
| Estrategia de viralización (vídeos hechos) | `#compras/nueva/viralizacion` | 20 → $30 · 40 → $50 · 60 → $70 · 80 → $90 · 100 → $100 |
| Vídeos de IA (packs 30-600, wizard país → formato → productos → datos) | `#compras/nueva/ia` | no llegado al precio |
| Automatizaciones (gestión de cuenta, 200-600 vídeos) | `#compras/nueva/automation` | wizard con guía |
| Generaciones de guiones (acumulables) | `#compras/nueva/guiones` | 50 → $5 · 100 → $10 · 300 → $20 |
| Carruseles | — | "Próximamente" |
| Membresía TTShop AI Pro + Skool | — | 49 $/mes · 299 $/año |

Su "Estrategia de viralización" es lo que hace gratis nuestro Viralización 1K.

## Peticiones de mejora (`#mejoras`)

Formulario: título + categoría (Experiencia / Contenido / Automatización /
Otro) + texto + imagen. "Las ideas integradas podrán recibir créditos".
Enviar de una en una, redactadas como ventaja para todos los alumnos:

1. Avisos de catálogo y prompts en la campana + etiqueta Nuevo/Actualizado
   con fecha (Automatización). Nos ahorra rebajar los 31 ZIP para ver qué cambió.
2. Descargar todo / solo lo nuevo, buscador y varias carpetas abiertas
   (Experiencia). Nos ahorra la subida ZIP a ZIP y el pegote acordeón.
3. Agotado con fecha + filtro + aviso al volver; fecha de última revisión
   en cada prompt (Contenido). Se quitó lo de hombre/mujer (su web ya tiene
   los 9 formatos de moda en los dos sexos) y lo de pedir POV en 10s (los
   20s son a propósito: se prioriza contenido largo).

Textos listos para pegar: `Escritorio\Peticiones TTShop AI Pro.txt`.

Estado: **las tres enviadas el 2026-09-08**, en "pending". Si alguna se
integra, revisar qué se puede quitar de nuestro lado (subida ZIP a ZIP,
pegote de consola, backup diario del Drive) y si dan créditos.
