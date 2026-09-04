# Estándar visual de las pantallas de nicho (Tiktok Shop AI Pro)

> Cómo se construye una pantalla de nicho. **Obligatorio** para las nuevas y
> para cualquier retoque de las que ya hay.
>
> El motivo no es estético: son **once nichos** y los usan **tres personas**
> (ness, Ana, Mauro), que además se turnan. Quien aprende un nicho tiene que
> saber usar los otros sin que se lo expliquen. Cada pantalla que se inventa su
> propio diseño obliga a aprenderla aparte — y a mantenerla aparte.

**Las dos de referencia** (son casi iguales entre sí a propósito):

| Pantalla | Fichero |
|---|---|
| Nicho POV BOF | [`frontend/app/tiktok-shop-ai-pro/nicho-pov-bof/page.tsx`](frontend/app/tiktok-shop-ai-pro/nicho-pov-bof/page.tsx) |
| POV BOF Largo | [`frontend/app/tiktok-shop-ai-pro/pov-bof-largo/page.tsx`](frontend/app/tiktok-shop-ai-pro/pov-bof-largo/page.tsx) |

Ante la duda, **se copia de ahí**. Si algo no encaja, la solución es añadir la
pieza a los componentes comunes y usarla desde todos, nunca inventar un diseño
propio en una pantalla.

**Esto estandariza la FORMA, no obliga a tener la función.** Lo que un nicho no
necesita, no se pone: el POV BOF marca "Vendió" porque su catálogo tiene
ranking de ventas y la ropa de la web no entra en él, así que ahí la fila de
estado son dos botones y no tres. La regla es al revés de como suena: *si lo
tienes, se ve igual que en los demás; si no lo tienes, no lo inventes para
parecerte*. Un botón de adorno que no lleva a ningún sitio confunde más que una
pantalla con menos botones.

---

## 1. Anatomía de la pantalla

Siempre este orden. El contenedor es
`mx-auto w-full max-w-4xl space-y-3 p-3 pb-24 sm:space-y-4`.

```
1. <header>            quién eres y qué hace este nicho     ← TEXTO, nunca portada
2. <Caja "Dónde trabajas">  catálogo · carpetas · modo      ← con chips y barra
3. <Paso n=1..N>       el trabajo, numerado y por colores
4. tarjetas de producto   grid-cols-1 gap-2 sm:grid-cols-2
5. modales             foto, vídeo, escaparate, vendidos
```

### 1. Cabecera

De texto: icono + `h1` + una línea de qué hace + un párrafo de contexto (de
dónde salen los productos y qué progreso es de este nicho).

**Nunca la portada del curso.** Ocupa media pantalla en el móvil y dice menos
que dos líneas; lo primero que hay que ver es dónde estás trabajando. Solo la
conservan las pantallas que no tienen catálogo que elegir.

### 2. "Dónde trabajas"

`<Caja icono="📁" titulo="Dónde trabajas" hint="…" extra="X/Y hechas">`, con un
`<Sub>` por bloque (`Catálogo`, `Carpetas`, `Modo de grabación`…).

- **Catálogo**: botones en `grid grid-cols-2 gap-1.5 sm:grid-cols-4`.
- **Carpetas**: contador + barra (`h-1.5 w-full rounded-full bg-muted` con
  relleno `bg-emerald-500`) + **chips**: `flex flex-wrap gap-1`, cada uno
  `rounded border px-2 py-1 text-[10px]`, `✓ ` delante si está hecha y una
  píldora `text-[9px]` con `hechas/total` — **ámbar si falta algo, esmeralda si
  está completo**. Un número solo ("9") no dice si faltan cosas; `9/10` sí.
- Botones grandes de dos columnas para las carpetas **no**: con veinte hay que
  hacer scroll para saber en cuál estás.

### 3. Los pasos

`<Paso n={1} color="violeta" titulo="…" hint="…" extra="0/10">`. Los colores
son fijos **y significan lo mismo en todos los nichos**:

| Color | Paso |
|---|---|
| violeta | preparar la carpeta (leer textos, fotos) |
| fucsia | generar fuera (los clips, en Flow/Omni) |
| esmeralda | copiar el prompt |
| azul | descargar lo ya montado |
| ámbar | modo especial activo (p. ej. gancho de punto de dolor) |

Un paso que traiga decenas de miniaturas va `plegable`.

### 4. Las tarjetas

`grid grid-cols-1 gap-2 sm:grid-cols-2`. En una sola columna hay que bajar diez
pantallas para ver una carpeta entera, y el trabajo es ir saltando de producto
en producto.

---

## 2. Anatomía de la tarjeta de producto

El mismo orden en todos los nichos. Lo que un nicho no tenga, se salta — pero
no se reordena.

```
┌──────────────────────────────────────────────┐
│ [foto 56px] [nº] Título del producto         │  ← abre el modal de foto
│             descripción / título de TikTok    │
│             píldoras de ESTADO                │  ← sin stock · también en Drive · ventas
│             precio (tachado + final) · plazos │
├──────────────────────────────────────────────┤
│ [Caption] [URL] [más ▾]                       │  ← copiar; los de diario fuera
├──────────────────────────────────────────────┤
│ opciones del montaje (duración, voz, tools)   │  ← plegables
├──────────────────────────────────────────────┤
│ [Subir clip 1] [Subir clip 2]                 │
│ [Ver vídeo] [Descargar]  · Montado el …       │
├──────────────────────────────────────────────┤
│ [Escaparate] [Subido] [Vendió]                │  ← SIEMPRE la última fila
└──────────────────────────────────────────────┘
```

Reglas de la tarjeta:

- **La fila de estado va abajo y siempre igual**: Escaparate · Subido · Vendió.
  Es lo que se toca después de publicar y se busca a ciegas.
- **Copiar**: solo Caption y URL a la vista; el resto (Título TikTok, Tienda,
  hashtags…) detrás de `más ▾`. Siete botones en fila hacen que encontrar el de
  siempre cueste mirar. Se usa [`CopyChip`](frontend/components/tiktok-shop-ai-pro/CopyChip.tsx),
  que además deja el botón DESACTIVADO —no lo esconde— cuando el dato falta:
  así se ve que ese producto no lo tiene.
- **Pintado optimista con deshacer**: los tres botones de estado se pintan al
  pulsar y se revierten si la API falla. Sin revertir, el botón se desmarca
  solo un rato después y parece "no me deja marcar".
- **El precio va pegado al producto**, con el precio de lista tachado si lo hay:
  explica por qué un producto de 34,70 € no lleva plazos.
- Nada de acciones destructivas sueltas: borrar y limpiar piden confirmación en
  la propia tarjeta (`confirmar*` en estado local).

---

## 3. Tokens

**Tamaños de texto** (móvil primero, `sm:` para subir):

| Uso | Clase |
|---|---|
| Título de pantalla | `text-base font-bold sm:text-lg` |
| Título de caja o paso | `text-xs font-semibold sm:text-sm` |
| Cuerpo | `text-[11px]` |
| Secundario / hint | `text-[10px] text-muted-foreground` |
| Píldora | `text-[9px] font-semibold` |

**El color SIGNIFICA algo.** No se elige por gusto:

| Color | Qué dice |
|---|---|
| esmeralda | hecho, completo, correcto |
| ámbar | falta algo, aviso, "prepárate" |
| naranja | montado pero sin subir |
| rosa/rojo | error, sin stock |
| azul | lo que tienes abierto ahora (y aún no está hecho) |
| violeta | la acción principal de la pantalla |
| fucsia | algo recuperado o excepcional |

**Formas**: `rounded-xl` las secciones, `rounded-lg` los botones, `rounded` los
chips, `rounded-full` las píldoras y las barras.

**Móvil**: `grid-cols-2 sm:grid-cols-N`, diálogos
`w-[calc(100vw-2rem)] max-h-[90vh] overflow-y-auto`, `truncate` en los valores
largos. La app se usa desde el móvil y desde la APK.

---

## 4. Piezas que se reutilizan (no se reescriben)

| Pieza | Para qué |
|---|---|
| [`Paso.tsx`](frontend/components/tiktok-shop-ai-pro/Paso.tsx) | `Paso`, `Caja`, `Sub`, `OSepara` — el esqueleto entero |
| [`CopyChip.tsx`](frontend/components/tiktok-shop-ai-pro/CopyChip.tsx) | copiar un texto, con estado "no lo tiene" |
| [`BotonUrl.tsx`](frontend/components/tiktok-shop-ai-pro/BotonUrl.tsx) | abrir la ficha de TikTok Shop |
| [`BotonDescarga.tsx`](frontend/components/tiktok-shop-ai-pro/BotonDescarga.tsx) | descargar con nombre normalizado |
| [`FotoModal.tsx`](frontend/components/tiktok-shop-ai-pro/FotoModal.tsx) · [`video-modal`](frontend/components/ui/video-modal.tsx) | ver foto / vídeo |
| [`EscaparateModal.tsx`](frontend/components/tiktok-shop-ai-pro/EscaparateModal.tsx) · [`VendidosModal.tsx`](frontend/components/tiktok-shop-ai-pro/VendidosModal.tsx) | los dos índices transversales |
| [`MontadoEl.tsx`](frontend/components/tiktok-shop-ai-pro/MontadoEl.tsx) | "Montado 2 sept · 16:44" |
| [`ChipAjuste.tsx`](frontend/components/tiktok-shop-ai-pro/ChipAjuste.tsx) | ajuste plegable dentro de la tarjeta |
| [`FiltroSoloUrl.tsx`](frontend/components/tiktok-shop-ai-pro/FiltroSoloUrl.tsx) | "solo los que tienen ficha" |
| [`MagnificSpaces.tsx`](frontend/components/tiktok-shop-ai-pro/MagnificSpaces.tsx) | enlaces a los spaces de generación |

Antes de escribir un botón nuevo: **mirar si ya existe aquí**. Si de verdad
falta, se añade a esta carpeta y se documenta en la tabla — no se deja dentro
de la página de un nicho, que es como acabaron duplicadas las que hubo que
unificar.

---

## 5. Checklist antes de dar por buena una pantalla

- [ ] Cabecera de texto, sin portada
- [ ] `Caja` "Dónde trabajas" con `Sub`, contador y barra
- [ ] Carpetas como chips con `hechas/total` en ámbar/esmeralda
- [ ] Pasos numerados, con los colores de la tabla
- [ ] Tarjetas en `sm:grid-cols-2`
- [ ] Fila de estado la última y optimista — con los estados que ese nicho
      tenga de verdad (Escaparate · Subido · Vendió)
- [ ] Copiar: Caption y URL fuera, el resto tras `más ▾`
- [ ] Probado en ancho de móvil (no solo en el navegador grande)
- [ ] `npm run typecheck` y `npm run build` limpios
