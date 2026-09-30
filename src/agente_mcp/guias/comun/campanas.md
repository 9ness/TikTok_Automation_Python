# Campañas de TikTok Shop: Black Friday y Navidad

Del **11 de noviembre al 16 de diciembre de 2026** TikTok Shop EU tiene campañas
seguidas. Afectan a qué productos conviene sacar y a cómo se escriben los
guiones. La fuente de verdad está en `src/cuotas/campanas.py`: el operador la ve
como una franja debajo del contador de vídeos, y tú la tienes con la
herramienta **`campanas`** del MCP (sin MCP: `GET /api/v1/cuotas/campanas`).
Consúltala; no te fíes de las fechas copiadas aquí si ha cambiado el año.

| Fechas | Campaña | Qué pedir |
|---|---|---|
| 11–17 nov | 🛒 Black Friday · Front Run Week (vs Amazon) | Ofertas adelantadas: chollo, buen precio |
| 18–24 nov | 🎁 Black Friday · Mid Week (festival de marcas; 23-24 Live All-Star) | Productos con marca y reseñas |
| 25–29 nov | 🔥 **Black Friday Peak** (día fuerte: vie 27) | Urgencia máxima; volumen al tope diario |
| 30 nov | 🛍️ Cyber Monday | «Hoy es el último día» |
| 1–16 dic | 🎄 Navidad | Ángulo regalo; la última semana, «llega antes de Nochebuena» |

## Cuándo preparar

Un vídeo tarda días en coger tracción, así que **lo de una campaña se publica
antes de que empiece**. La app avisa 14 días antes de cada hito: el 28 oct
(Black Friday), el 11 nov (el pico), el 16 nov (Cyber Monday) y el 17 nov
(Navidad). Cuando `campanas` devuelve `avisos`, díselo al operador al empezar
y propón qué productos de la carpeta encajan mejor.

## Cómo orientar un guion o un prompt

- `campanas` trae `contexto_guion`: una frase con el ángulo de la campaña del
  momento. Vacía = no hay campaña cerca, escribe como siempre.
- Úsalo como **ángulo**, no como relleno: una línea de gancho o de CTA («el
  regalo perfecto para tu madre», «el precio de Black Friday dura hasta el
  domingo»). El resto del guion sigue la guía del menú.
- **Regla que no se salta:** no prometas descuento, «precio de Black Friday»,
  regalo o envío que la ficha del producto NO tenga. Es «promoción
  incoherente» y sanciona la cuenta (la de `ness` va al límite). Sin oferta
  real, usa el ángulo que sí es cierto: regalo, llega a tiempo, lo más vendido
  de la semana.
- En la imagen o el clip, nada de rótulos de «Black Friday» o «-50 %»: las
  imágenes generadas van sin texto (ver `revision-calidad.md`).
