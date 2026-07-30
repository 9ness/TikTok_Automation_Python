"""Montaje del vídeo final del Nicho POV BOF (Programa 4 — Tiktok Shop AI Pro).

El operador sube un vídeo bruto (generado fuera con Veo3 o Kling) + elige la
voz/frase; esta pieza hace TODA la edición hasta dejar el MP4 listo para
Drive.

Orden del pipeline (cada paso escribe un fichero intermedio en `work_dir`
para poder depurar si algo falla a mitad de camino):

  1. (ya no hay paso de marca de agua: Veo3 dejó de ponerla en 2026-07, y
     Kling nunca la puso, así que no había nada que quitar)
  2. Normalizar a 1080x1920 @ 30fps (cover-fit + crop). Se hace ANTES de
     cuadrar duración porque `duration_match` asume que el vídeo YA tiene el
     tamaño final: solo toca duración, no resolución.
  3. Cuadrar la duración del vídeo con la del audio (`duration_match`, ya
     existente — se reusa tal cual, sin tocarlo).
  4. Quemar el bloque de 3 líneas de texto (gancho / título / CTA).
  5. Superponer la flecha `.mov` (alpha nativo) en el instante detectado con
     Whisper sobre el audio locutado.
  6. Mux del audio final sobre el vídeo (el vídeo llega mudo: los pasos
     2 y 3 lo dejan sin pista de audio).

Reutiliza a propósito el "motor" de texto+emoji+flecha de
`tiktok_shop/pipeline/ready_video.py` (helpers privados, ver
`NICHO_POV_BOF_MODULE.md` → tabla "Piezas del repo que se reutilizan"): es
una decisión de diseño explícita del módulo, no una mezcla accidental de
lógica de programas. Los valores de posición/escala de la flecha en
`ready_video.py` (`_ARROW_CX/_ARROW_CY/_ARROW_SCALE_W`) coinciden con los de
`config.ARROW_CX/CY/SCALE_W` de este módulo, así que reusar su función de
overlay es seguro.
"""

from __future__ import annotations

import random
import re
import subprocess
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from src.font_resolver import _bundled_fonts_dir
import cv2

from src.nicho_pov_bof import config
from src.nicho_pov_bof.pipeline.duration_match import (
    _run,
    match_video_to_audio,
    probe_duration,
)
from src.tiktok_shop.pipeline.ready_video import (
    _ARROW_FILES,
    _emoji_run_img,
    _overlay_arrow_ffmpeg,
    _pick_arrow,
    _seg_width,
    _split_runs,
)

OnLog = Callable[[str], None]
OnProgress = Callable[[float, str], None]
_noop: OnLog = lambda _msg: None
_noop_progress: OnProgress = lambda _pct, _label: None

# ---------------------------------------------------------------------------
# Colores del glow (ver spec: gancho magenta/rosa, CTA cyan).
# ---------------------------------------------------------------------------
# Sombra NEGRA, no halo de color. La referencia que montó el operador en
# CapCut es blanco con borde y sombra oscura; el halo magenta/cyan que había
# antes rompía la armonía del bloque. Para volver al halo de color basta con
# poner aquí los colores y subir `_SOMBRA_RADIO`.
# Destello (neón) del gancho y el CTA: SIMÉTRICO y ancho. Aquí el halo es el
# efecto buscado, así que no se desplaza; desplazarlo lo convierte en sombra y
# se pierde el neón.
# Radio pequeño + realce moderado: el destello tiene que ABRAZAR la letra y
# apagarse hacia fuera. Con radio 9 e intensidad 3.4 se convertía en una barra
# de color maciza detrás del texto.
_SOMBRA_RADIO = 6
_SOMBRA_PASADAS = 3
_SOMBRA_OFFSET = (0, 0)
_DESTELLO_INTENSIDAD = 2.3
# El título no lleva neón de color: sombra oscura y desplazada, para que
# destaque sobre el plano sin competir con el gancho.
_TITULO_SOMBRA = (0, 0, 0)
_TITULO_SOMBRA_OFFSET = (5, 7)
_TITLE_STROKE = (0, 0, 0)          # título: blanco con borde negro, sin glow


# Tipografía de referencia del operador (montada a mano en CapCut): todo
# Montserrat, con el gancho y el CTA en CURSIVA y el nombre del producto
# recto y más pequeño. La jerarquía de tamaños es lo que da armonía; con
# los tres al mismo cuerpo el bloque quedaba plano y "muy básico".
_FUENTE_CURSIVA = "Montserrat-BlackItalic.ttf"
_FUENTE_RECTA = "Montserrat-ExtraBold.ttf"


def _font_path(name: str = "Montserrat-ExtraBold.ttf") -> str:
    """Misma resolución de fuente que `ready_video.py`: bundled del repo, o
    fallback a DejaVu si el asset no está presente en el entorno."""
    p = Path(_bundled_fonts_dir()) / name
    return str(p) if p.exists() else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


# ---------------------------------------------------------------------------
# Paso 1 — Marca de agua
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Paso 2 — Normalizar resolución/fps
# ---------------------------------------------------------------------------
def _normalize_resolution(video_in: Path, out_path: Path, on_log: OnLog) -> Path:
    """Cover-fit (escala cubriendo el frame + recorte centrado) a
    1080x1920 @ 30fps. `setsar=1` evita que un SAR raro del vídeo de origen
    deforme el recorte."""
    w, h, fps = config.TARGET_W, config.TARGET_H, config.TARGET_FPS
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},fps={fps},setsar=1"
    )
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video_in),
        "-vf", vf, "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        str(out_path),
    ], on_log)
    return out_path


# ---------------------------------------------------------------------------
# Paso 4 — Bloque de texto (gancho / título / CTA)
# ---------------------------------------------------------------------------
def _render_text_line(
    text: str, *, font_size: int, max_w: int,
    fill: tuple, stroke: tuple, max_lines: int = 1,
    fuente: str = _FUENTE_RECTA,
) -> "Image.Image | None":
    """Renderiza una línea (o varias, hasta `max_lines`) de texto+emoji a
    PNG con relleno + borde. Mismo enfoque que `ready_video._render_text_png`
    pero con límite de líneas (el título puede ocupar hasta 2)."""
    text = (text or "").strip()
    if not text:
        return None
    d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))

    def _repartir(size: int) -> tuple[list[str], "ImageFont.FreeTypeFont", int, int]:
        """Reparte el texto en líneas con ese cuerpo de letra.

        Los saltos que ya trae el texto se RESPETAN: Gemini devuelve el título
        repartido en columnas de <=4 palabras y ese reparto está pensado para
        leerse de un vistazo. Solo se re-parte una línea si aun así no cabe.
        """
        f = ImageFont.truetype(_font_path(fuente), size)
        e_size = int(size * 0.92)
        g = int(size * 0.06)

        def w(sub: str) -> float:
            return _seg_width(_split_runs(sub), f, d0, e_size, g)

        out: list[str] = []
        for bloque in text.split("\n"):
            bloque = bloque.strip()
            if not bloque:
                continue
            cur = ""
            for word in bloque.split():
                test = (cur + " " + word).strip()
                if w(test) <= max_w or not cur:
                    cur = test
                else:
                    out.append(cur)
                    cur = word
            if cur:
                out.append(cur)
        return out, f, e_size, g

    # Si no cabe en `max_lines`, se ENCOGE la letra hasta que quepa. Antes se
    # descartaban las líneas sobrantes y el texto salía mutilado sin avisar:
    # un CTA de "COMPRUÉBALO TÚ MISMO 👀" aparecía como "COMPRUÉBALO TÚ".
    for size in range(font_size, max(12, int(font_size * 0.5)) - 1, -2):
        lines, font, emoji_size, gap = _repartir(size)
        if len(lines) <= max_lines:
            font_size = size
            break
    else:
        # Ni al mínimo cabe (texto larguísimo): recortar es el último recurso.
        lines = lines[:max_lines]

    stroke_w = max(3, int(font_size * 0.13))

    def w_of(sub: str) -> float:
        return _seg_width(_split_runs(sub), font, d0, emoji_size, gap)

    line_h = int(font_size * 1.22)
    pad = stroke_w + 10
    line_ws = [w_of(ln) for ln in lines]
    W = int(max(line_ws, default=0)) + pad * 2
    H = line_h * len(lines) + pad * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        x = (W - line_ws[i]) / 2
        y = pad + i * line_h
        for k, t in _split_runs(ln):
            if k == "emoji":
                em = _emoji_run_img(t, emoji_size)
                if em is not None:
                    ey = int(y + (font_size - emoji_size) / 2 + font_size * 0.10)
                    img.paste(em, (int(x), ey), em)
                    x += em.width + gap
            else:
                d.text((x, y), t, font=font, fill=fill,
                       stroke_width=stroke_w, stroke_fill=stroke)
                x += d0.textlength(t, font=font)
    return img


def _add_glow(
    img: "Image.Image", color: tuple, *,
    radius: int = _SOMBRA_RADIO, passes: int = _SOMBRA_PASADAS,
    offset: tuple[int, int] = _SOMBRA_OFFSET,
    intensity: float = _DESTELLO_INTENSIDAD,
) -> "Image.Image":
    """Sombra proyectada detrás del texto.

    Usa el canal alpha del PNG como máscara, la rellena de `color`, la
    difumina y la pega DESPLAZADA (`offset`): una sombra simétrica se lee como
    un halo difuso, no como sombra, y era lo que hacía que el bloque pareciera
    plano. El texto original va encima nítido.
    """
    pad = radius * 3 + max(abs(offset[0]), abs(offset[1]))
    W, H = img.size
    canvas = Image.new("RGBA", (W + pad * 2, H + pad * 2), (0, 0, 0, 0))
    alpha = img.split()[-1]
    glow_alpha = Image.new("L", canvas.size, 0)
    glow_alpha.paste(alpha, (pad + offset[0], pad + offset[1]))
    glow_layer = Image.new("RGBA", canvas.size, tuple(color) + (0,))
    glow_layer.putalpha(glow_alpha)
    for _ in range(max(1, passes)):
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius))
    # Cada pasada de blur reparte el alpha y lo deja translúcido: el neón
    # salía lavado. Se REALZA el alpha ya difuminado para que el color quede
    # denso pegado a la letra y se apague hacia fuera, que es como se ve un
    # neón de verdad.
    if intensity > 1:
        a = glow_layer.split()[-1].point(lambda v: min(255, int(v * intensity)))
        glow_layer.putalpha(a)
    canvas = Image.alpha_composite(canvas, glow_layer)
    canvas.paste(img, (pad, pad), img)
    return canvas


# Palabras que no pueden cerrar el título: cortar en ellas lo deja colgando
# ("Cochecito para Perros Gatos / Plegable 2 en").
_TITULO_COLGANTES = {
    "y", "o", "de", "del", "la", "el", "los", "las", "para", "con", "sin",
    "en", "a", "al", "un", "una", "por", "que", "su", "sus", "e", "u",
}

# Líneas del título que se pintan y palabras por línea. El extractor devuelve
# el nombre ENTERO en columnas de 4 palabras (puede dar 7 líneas); en el
# vídeo solo caben las primeras, que es lo que el operador ponía a mano.
_TITULO_MAX_LINEAS = 2
_TITULO_PALABRAS_LINEA = 4

# Donde acaba el nombre y empieza la ficha técnica. El prompt pide cortar
# aquí, pero Gemini no lo respeta ("…Viaje Elegantes: Carcasa Ligera de ABS,
# Cerradura Numérica…"), así que se corta también en código, que es
# determinista y no cuesta una nueva extracción.
_TITULO_CORTES = (":", "|", " - ", " – ", ",")
# Por debajo de esto el trozo de delante no nombra el producto ("Freshly -")
# y se sigue leyendo hasta el siguiente separador.
_TITULO_MIN_CHARS = 18


def _titulo_para_video(textos: dict) -> str:
    """Título que se quema en el vídeo: el nombre del producto, sin ficha.

    `titulo` viene del extractor (`prompts/text_extractor.md`) como el nombre
    LITERAL repartido en columnas de 4 palabras. Aquí se corta la cola de
    keywords SEO y se deja en `_TITULO_MAX_LINEAS` líneas. Nada de
    reformular: el `titulo_tiktok_completo` existe para BUSCAR el producto en
    el Centro de Afiliados, no para pintarlo.
    """
    bruto = (textos.get("titulo") or "").strip()
    if not bruto:
        bruto = (textos.get("titulo_tiktok_completo") or "").strip()
    if not bruto:
        return ""

    # Se aplana y se limpia la basura de escapado de las fichas ("\\Impermeable").
    plano = re.sub(r"\s+", " ", bruto.replace("\n", " ").replace("\\", " ")).strip()

    for sep in _TITULO_CORTES:
        cabeza = plano.split(sep, 1)[0].strip()
        if len(cabeza) >= _TITULO_MIN_CHARS:
            plano = cabeza

    palabras = plano.split()[:_TITULO_MAX_LINEAS * _TITULO_PALABRAS_LINEA]
    while palabras and palabras[-1].lower().strip(".,-–|:") in _TITULO_COLGANTES:
        palabras.pop()

    return "\n".join(
        " ".join(palabras[i:i + _TITULO_PALABRAS_LINEA])
        for i in range(0, len(palabras), _TITULO_PALABRAS_LINEA)
    ).strip(" .,-–|:\n")


def _crop_visible(img: "Image.Image", thresh: int = 45, margin: int = 3) -> "Image.Image":
    """Recorta el PNG a lo que se ve de verdad, ignorando la cola casi
    transparente del halo. `margin` deja un pelín para no cortarlo en seco."""
    alpha = img.split()[-1].point(lambda a: 255 if a > thresh else 0)
    box = alpha.getbbox()
    if not box:
        return img
    x0, y0, x1, y1 = box
    return img.crop((
        max(0, x0 - margin), max(0, y0 - margin),
        min(img.width, x1 + margin), min(img.height, y1 + margin),
    ))


def _destello(img: "Image.Image", color: tuple, rot: dict) -> "Image.Image":
    """Aplica el acabado del rótulo (ancho, densidad y desplazamiento)."""
    return _add_glow(
        img, color,
        radius=rot["radio"], passes=rot["pasadas"],
        offset=rot["offset"], intensity=rot["intensidad"],
    )


def _render_text_block_png(
    textos: dict,
    layout: str = "gancho_cta_titulo",
    piezas: "set[str] | None" = None,
    paleta: dict | None = None,
    rotulo: dict | None = None,
    on_log: OnLog = _noop,
) -> "Image.Image | None":
    """Compone las 3 líneas (gancho / título / CTA) en un único PNG
    apilado verticalmente y centrado, listo para hacer overlay estático
    sobre el vídeo.

    `layout` decide el orden de las líneas. Se prueban DOS disposiciones a la
    vez (mitad de los productos cada una) para comparar cuál rinde mejor con
    datos reales, en vez de elegir a ojo:

    - `gancho_cta_titulo`: gancho, CTA y el nombre del producto debajo. Es la
      que usa el curso de referencia.
    - `gancho_titulo_cta`: el nombre en medio y la llamada cerrando el bloque.
    """
    # `piezas` elige qué líneas se pintan ("gancho", "titulo", "cta"). None =
    # todas, que es el comportamiento de siempre.
    quiere = piezas if piezas is not None else {"gancho", "titulo", "cta"}
    pal = paleta or _PALETAS[0]
    rot = rotulo or _ROTULOS[0]
    gancho = (textos.get("gancho") or "").strip() if "gancho" in quiere else ""
    if gancho:
        gancho = _texto_seguro(gancho, _GANCHO_SEGURO, "gancho", on_log)
    titulo = _titulo_para_video(textos) if "titulo" in quiere else ""
    cta = (textos.get("cta") or "").strip() if "cta" in quiere else ""
    if cta:
        cta = _texto_seguro(cta, _CTA_SEGURO, "CTA", on_log)
    max_w = int(config.TARGET_W * (config.SAFE_X[1] - config.SAFE_X[0]))

    def _render_gancho():
        if not gancho:
            return None
        # Gancho: MAYÚSCULAS, relleno blanco + glow magenta/rosa.
        im = _render_text_line(
            gancho.upper(), font_size=config.HOOK_FONT_SIZE, max_w=max_w,
            fill=pal["gancho_fill"], stroke=(0, 0, 0), max_lines=1,
            fuente=rot["titular"],
        )
        return _destello(im, pal["gancho_glow"], rot) if im is not None else None

    def _render_titulo():
        if not titulo:
            return None
        # Título: blanco con borde negro, hasta 2 líneas, SIN glow.
        im = _render_text_line(
            titulo, font_size=config.TITLE_FONT_SIZE, max_w=max_w,
            fill=(255, 255, 255), stroke=_TITLE_STROKE, max_lines=_TITULO_MAX_LINEAS,
            fuente=rot["titulo"],
        )
        # El nombre va SIEMPRE en blanco (es lo informativo y tiene que leerse
        # sobre cualquier plano), pero con la misma sombra que el resto para
        # que el bloque se vea de una pieza.
        if im is None:
            return None
        # Algunos rótulos dejan el título con SOLO el trazo negro del propio
        # texto: la sombra ayuda a despegarlo del plano pero engorda el bloque
        # y en fondos oscuros no aporta nada.
        if not rot.get("titulo_sombra", True):
            return im
        return _add_glow(im, _TITULO_SOMBRA, radius=6, passes=3,
                         offset=_TITULO_SOMBRA_OFFSET, intensity=1.9)

    def _render_cta():
        if not cta:
            return None
        # CTA: relleno blanco + glow cyan.
        im = _render_text_line(
            cta.upper(), font_size=config.CTA_FONT_SIZE, max_w=max_w,
            fill=pal["cta_fill"], stroke=(0, 0, 0), max_lines=1,
            fuente=rot["titular"],
        )
        return _destello(im, pal["cta_glow"], rot) if im is not None else None

    orden = (
        (_render_gancho, _render_titulo, _render_cta)
        if layout == "gancho_titulo_cta"
        else (_render_gancho, _render_cta, _render_titulo)
    )
    parts = [im for im in (render() for render in orden) if im is not None]

    if not parts:
        return None

    # El `_add_glow` devuelve un canvas con margen transparente a cada lado.
    # Al apilar tal cual, ese margen se sumaba entre líneas y el bloque salía
    # con huecos enormes. `getbbox()` a secas no vale: la cola tenue del halo
    # son píxeles no nulos y el recorte apenas quitaba nada, así que se mide
    # sobre el alpha UMBRALIZADO (lo que de verdad se ve).
    parts = [_crop_visible(p) for p in parts]

    # Bloque COMPACTO: cada parte ya trae su propio margen (el destello se
    # recorta a lo que se ve, pero deja unos píxeles), y con 14 quedaba un
    # hueco visible entre gancho y CTA. El bloque va arriba y cuanto menos
    # ocupe, menos tapa el producto.
    line_gap = 4
    block_w = max(p.width for p in parts)
    block_h = sum(p.height for p in parts) + line_gap * (len(parts) - 1)

    # Red de seguridad: el ajuste por palabras mide solo el TEXTO, pero cada
    # línea añade después el borde y el halo, así que el bloque puede acabar
    # más ancho que la zona segura y salir cortado por los lados en TikTok.
    # Si pasa, se reescala el bloque entero (mejor un texto algo menor que uno
    # recortado).
    if block_w > max_w:
        factor = max_w / block_w
        parts = [
            p.resize((max(1, int(p.width * factor)), max(1, int(p.height * factor))),
                     Image.LANCZOS)
            for p in parts
        ]
        block_w = max(p.width for p in parts)
        block_h = sum(p.height for p in parts) + line_gap * (len(parts) - 1)

    block = Image.new("RGBA", (block_w, block_h), (0, 0, 0, 0))
    y = 0
    for p in parts:
        block.paste(p, (int((block_w - p.width) / 2), y), p)
        y += p.height + line_gap
    return block


# ---------------------------------------------------------------------------
# Cumplimiento TikTok Shop: qué se puede afirmar en pantalla
# ---------------------------------------------------------------------------
# TikTok sanciona el contenido que afirma una BAJADA DE PRECIO o una oferta que
# luego puede no existir (el precio sube y el vídeo sigue publicado diciendo
# "rebajado"). Hablar del CUPÓN sí es seguro: o está en la ficha o no está, y
# no promete que el precio vaya a seguir igual.
#
# Este filtro es la última barrera antes de QUEMAR el texto en el vídeo: si la
# IA se pasa de frenada, aquí se sustituye por algo neutro y se avisa en el
# log. No se aborta el montaje por esto.
_TERMINOS_RIESGO = (
    "oferta", "oferton", "ofertazo", "rebaj", "chollo", "robo", "regalo",
    "gratis", "barat", "bajon", "bajada", "precio de risa", "precio de locura",
    "preciazo", "imperdible", "liquidacion", "saldo", "mitad de precio",
    "descuentazo", "ultima", "ultimas", "solo hoy", "se agota", "aprovecha",
    # El operador descartó "CUPÓN SORPRESA": prometer sorpresa es prometer algo
    # que no se puede verificar en la ficha.
    "sorpresa", "locura", "increible", "brutal", "flipa", "no te lo pierdas",
)
# Reemplazos neutros, que dicen la verdad sin prometer nada.
_GANCHO_SEGURO = "🏷️ CUPÓN DESCUENTO 🏷️"
_CTA_SEGURO = "👇 MÍRALO ABAJO 👇"


def _sin_acentos(txt: str) -> str:
    import unicodedata

    plano = unicodedata.normalize("NFKD", txt)
    return "".join(c for c in plano if not unicodedata.combining(c)).lower()


def texto_arriesgado(txt: str) -> str | None:
    """Término problemático que contiene `txt`, o None si es seguro.

    "cupón descuento" es seguro; "descuento" a secas afirma una rebaja.
    """
    plano = _sin_acentos(txt or "")
    if "cupon" in plano:
        # Con cupón por delante, hablar de descuento es describir el cupón.
        plano = plano.replace("descuent", "")
    for t in _TERMINOS_RIESGO:
        if t in plano:
            return t
    if "descuent" in plano:
        return "descuento (sin mencionar el cupón)"
    return None


# El caption no se quema en el vídeo — lo copia el operador al publicar — así
# que aquí no se sustituye nada, solo se AVISA en la ficha.
#
# Su riesgo es distinto al del gancho: no es el precio, es prometer un
# RESULTADO ("tu piel perfecta", "elimina las manchas"). Nada de eso lo
# respalda la ficha del producto, y en salud/belleza/suplementos es motivo de
# sanción. El caption solo debe reformular lo que ya pone el título.
_TERMINOS_PROMESA = (
    "perfecta", "perfecto", "elimina", "eliminan", "borra", "cura", "curan",
    "sana", "adelgaz", "rejuvenec", "milagro", "milagros", "garantiz",
    "resultados en", "en 7 dias", "en 30 dias", "para siempre",
    "adios a", "olvidate de", "te cambia la vida", "cambia tu vida",
    "el mejor del mercado", "la mejor del mercado", "numero 1", "n1",
    "sin esfuerzo", "al instante", "100%", "definitivamente",
)


def caption_arriesgado(txt: str) -> str | None:
    """Promesa o afirmación de precio en el caption, o None si es seguro."""
    plano = _sin_acentos(txt or "")
    for t in _TERMINOS_PROMESA:
        if t in plano:
            return t
    # El caption arrastra además las mismas reglas de precio que el gancho.
    return texto_arriesgado(txt)


def _texto_seguro(txt: str, respaldo: str, etiqueta: str, on_log: OnLog) -> str:
    riesgo = texto_arriesgado(txt)
    if not riesgo:
        return txt
    on_log(
        f"[3/5] ⚠️ {etiqueta} {txt!r} puede incumplir las normas de TikTok Shop "
        f"(término {riesgo!r}) → se usa {respaldo!r}"
    )
    return respaldo


# ---------------------------------------------------------------------------
# Rótulos: tipografía + acabado del destello
# ---------------------------------------------------------------------------
# Sin variar esto, todos los vídeos salían con la misma letra y el mismo neón
# y el feed se veía repetitivo. Cada rótulo combina una tipografía (todas
# gruesas y legibles en vertical) con un acabado distinto del destello:
#   - radio/pasadas/intensidad → lo ancho y denso del neón
#   - offset → si el destello va centrado (neón) o desplazado (sombra dura)
# El nombre del producto lleva su propia fuente, siempre recta y legible.
_ROTULOS = (
    {
        "nombre": "montserrat-neon",
        "titular": "Montserrat-BlackItalic.ttf", "titulo": "Montserrat-ExtraBold.ttf",
        "radio": 6, "pasadas": 3, "intensidad": 2.3, "offset": (0, 0),
        "titulo_sombra": True,
    },
    {
        "nombre": "montserrat-recto",
        "titular": "Montserrat-Black.ttf", "titulo": "Montserrat-ExtraBold.ttf",
        "radio": 5, "pasadas": 2, "intensidad": 2.6, "offset": (0, 0),
        # Solo trazo negro, sin sombra: más limpio y tapa menos producto.
        "titulo_sombra": False,
    },
    {
        # Condensada: entra más texto por línea y pega fuerte de titular.
        "nombre": "anton",
        "titular": "anton.ttf", "titulo": "Montserrat-ExtraBold.ttf",
        "radio": 7, "pasadas": 3, "intensidad": 2.1, "offset": (0, 0),
        "titulo_sombra": False,
    },
    {
        # Neón ancho y suave, más "aura" que borde.
        "nombre": "rubik-aura",
        "titular": "Rubik-Bold.ttf", "titulo": "Rubik-Bold.ttf",
        "radio": 11, "pasadas": 3, "intensidad": 1.7, "offset": (0, 0),
        "titulo_sombra": True,
    },
    {
        # Sombra DURA de color (sin difuminar, desplazada): look de cartel.
        "nombre": "bangers-cartel",
        "titular": "Bangers-Regular.ttf", "titulo": "Montserrat-ExtraBold.ttf",
        "radio": 1, "pasadas": 1, "intensidad": 6.0, "offset": (7, 8),
        "titulo_sombra": False,
    },
    {
        "nombre": "luckiest",
        "titular": "LuckiestGuy-Regular.ttf", "titulo": "Rubik-Bold.ttf",
        "radio": 6, "pasadas": 2, "intensidad": 2.4, "offset": (3, 4),
        "titulo_sombra": True,
    },
)


def _elegir_rotulo(semilla: str) -> dict:
    """Rótulo de este vídeo. Determinista por producto: el mismo producto
    re-montado sale igual, pero dos productos seguidos no comparten letra."""
    return _ROTULOS[sum(ord(c) for c in str(semilla)) % len(_ROTULOS)]


# ---------------------------------------------------------------------------
# Paleta de color del bloque de texto
# ---------------------------------------------------------------------------
# Los textos NO van todos en blanco: el gancho habla de precio/cupón y el
# color vende tanto como la palabra. Cada paleta es una combinación que
# funciona en vídeo vertical: el gancho en el color fuerte, el CTA en uno que
# acompañe sin competir, y el nombre del producto siempre en BLANCO (es la
# parte informativa y tiene que leerse sobre cualquier fondo).
#
# Cada línea lleva RELLENO y DESTELLO (glow de color) por separado, que es lo
# que hace el operador a mano: en sus vídeos el gancho sale cian con neón azul
# o blanco con neón rosa, y el CTA verde con neón verde cuando el emoji es ✅.
# El destello es el efecto, no un adorno: sin él el bloque parece plano.
# El nombre del producto va siempre blanco con borde negro (es lo informativo).
#
# `familias` son los emojis con los que casa cada paleta, y `tono` el matiz
# dominante en grados HSV (0=rojo, 60=amarillo, 120=verde, 180=cian) — se usa
# para elegir una que CONTRASTE con el fondo del vídeo.
_PALETAS = (
    {
        "nombre": "oro",
        "gancho_fill": (255, 255, 255), "gancho_glow": (255, 176, 0),
        "cta_fill": (255, 214, 64),     "cta_glow": (255, 110, 0),
        "tono": 45, "familias": "💰🤑💸💵🏷️⚠️",
    },
    {
        "nombre": "rosa-lima",   # el de la silla gaming del operador
        "gancho_fill": (255, 255, 255), "gancho_glow": (255, 32, 100),
        "cta_fill": (126, 255, 128),    "cta_glow": (0, 190, 60),
        "tono": 340, "familias": "🫣😱🤯🤭❗",
    },
    {
        "nombre": "cian-rojo",   # el de las maletas del operador
        "gancho_fill": (120, 240, 255), "gancho_glow": (40, 60, 255),
        "cta_fill": (255, 255, 255),    "cta_glow": (255, 30, 60),
        "tono": 200, "familias": "🎁👀💧❄️🧊",
    },
    {
        "nombre": "lima",
        "gancho_fill": (176, 255, 106), "gancho_glow": (0, 176, 46),
        "cta_fill": (255, 255, 255),    "cta_glow": (0, 130, 255),
        "tono": 100, "familias": "🌿✅🥗♻️💚",
    },
    {
        "nombre": "magenta",
        "gancho_fill": (255, 255, 255), "gancho_glow": (226, 0, 208),
        "cta_fill": (255, 226, 96),     "cta_glow": (255, 130, 0),
        "tono": 310, "familias": "💖✨🎀🥳🌟",
    },
    {
        "nombre": "fuego",
        "gancho_fill": (255, 214, 92),  "gancho_glow": (255, 46, 0),
        "cta_fill": (255, 255, 255),    "cta_glow": (255, 120, 0),
        "tono": 20, "familias": "🔥🌞🧨🚀",
    },
)


def _tono_dominante(video: Path) -> tuple[float, float]:
    """Matiz dominante del vídeo y su luminosidad media (0-255).

    Se muestrean tres fotogramas repartidos y se mira SOLO la zona donde va
    el texto: lo que importa es contra qué se va a leer, no el resto.
    """
    import colorsys

    muestras = []
    for frac in (0.15, 0.5, 0.85):
        f = video.with_name(f"_tono_{int(frac*100)}.jpg")
        try:
            dur = probe_duration(video)
            _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{dur*frac:.2f}",
                  "-i", str(video), "-frames:v", "1", "-vf", "scale=160:-1",
                  str(f)], _noop)
            img = cv2.imread(str(f))
            f.unlink(missing_ok=True)
        except Exception:
            img = None
        if img is None:
            continue
        h, w = img.shape[:2]
        banda = img[: int(h * 0.45), :]        # el bloque va arriba
        b, g, r = [float(x) / 255 for x in banda.reshape(-1, 3).mean(axis=0)]
        hh, _ss, vv = colorsys.rgb_to_hsv(r, g, b)
        muestras.append((hh * 360, vv * 255))
    if not muestras:
        return 0.0, 128.0
    return (
        sum(m[0] for m in muestras) / len(muestras),
        sum(m[1] for m in muestras) / len(muestras),
    )


def _elegir_paleta(video: Path, textos: dict, semilla: str, on_log: OnLog) -> dict:
    """Paleta para este producto: que pegue con los emojis y contraste con el vídeo.

    Tres criterios, en este orden de peso:
      1. **Emoji**: si el gancho lleva 🔥 la paleta cálida es la que cuadra;
         con 👀 pide fría. Es la señal más fuerte de intención.
      2. **Contraste con el fondo**: se penaliza la paleta cuyo matiz esté
         cerca del dominante del vídeo — un texto naranja sobre un plano
         naranja no se lee aunque combine.
      3. **Variedad**: a igualdad de puntos, desempata el nº de producto, así
         dos productos seguidos de la misma tienda no salen calcados.
    """
    emojis = (textos.get("gancho") or "") + (textos.get("cta") or "")
    tono_fondo, _luz = _tono_dominante(video)
    desempate = sum(ord(c) for c in str(semilla))

    def puntos(i_p):
        i, pal = i_p
        p = 0.0
        p += 6.0 * sum(1 for e in pal["familias"] if e in emojis)
        # distancia circular de matiz, normalizada a 0-1
        d = abs(pal["tono"] - tono_fondo) % 360
        d = min(d, 360 - d) / 180
        p += 3.0 * d
        p += ((desempate + i) % len(_PALETAS)) * 0.1
        return p

    elegida = max(enumerate(_PALETAS), key=puntos)[1]
    on_log(
        f"[3/5] paleta '{elegida['nombre']}' (fondo ~{tono_fondo:.0f}°, "
        f"emojis {emojis.strip() or '—'})"
    )
    return elegida


def _burn_text_block(video_in: Path, textos: dict, out_path: Path, on_log: OnLog,
                     layout: str = "gancho_cta_titulo",
                     piezas: "set[str] | None" = None,
                     semilla: str = "") -> Path:
    paleta = _elegir_paleta(video_in, textos or {}, semilla, on_log)
    rotulo = _elegir_rotulo(semilla)
    on_log(f"[3/5] rótulo '{rotulo['nombre']}'")
    block = _render_text_block_png(
        textos or {}, layout, piezas, paleta, rotulo, on_log,
    )
    if block is None:
        on_log("[3/5] sin textos que quemar — se copia el vídeo tal cual")
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(video_in), "-c", "copy",
              str(out_path)], on_log)
        return out_path

    png_path = out_path.with_suffix(".png")
    block.save(png_path)

    # Centro del bloque en TEXT_BLOCK_Y (dentro de la zona segura vertical);
    # clamp para que no se salga por arriba si el bloque es muy alto (3
    # líneas con emojis grandes).
    y_center = config.TEXT_BLOCK_Y * config.TARGET_H
    y_top = int(y_center - block.height / 2)
    safe_top = int(config.SAFE_Y[0] * config.TARGET_H)
    y_top = max(safe_top, y_top)

    _run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video_in), "-i", str(png_path),
        "-filter_complex", f"[0:v][1:v]overlay=(main_w-overlay_w)/2:{y_top}[v]",
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "copy",
        str(out_path),
    ], on_log)
    on_log(f"[3/5] texto quemado (bloque {block.width}x{block.height}px @ y={y_top})")
    return out_path


# ---------------------------------------------------------------------------
# Paso 5 — Flecha .mov
# ---------------------------------------------------------------------------
def _to_wav_16k_mono(audio_path: Path, out_wav: Path, on_log: OnLog) -> None:
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(audio_path),
        "-ac", "1", "-ar", "16000", str(out_wav),
    ], on_log)


def _find_arrow_window(
    audio_path: Path, work_dir: Path, on_log: OnLog, video_dur: float | None = None,
) -> tuple[float, float]:
    """Devuelve `(t0, t1)`: ventana en la que debe verse la flecha.

    Una vez que aparece se queda HASTA EL FINAL: es la llamada a la acción,
    y desaparecer a los 3,5s deja el cierre del vídeo sin nada a lo que
    apuntar (decisión del operador tras ver el primer montaje).

    Transcribe el audio locutado con Whisper y busca la primera palabra que
    contenga alguna de `config.ARROW_KEYWORDS`. La flecha entra
    `ARROW_LEAD_S` segundos ANTES de esa palabra. Si Whisper no detecta
    ninguna palabra gatillo (o falla), la flecha sale desde el principio del
    vídeo — nunca abortamos el pipeline por esto (asset/paso opcional)."""
    try:
        from src.subtitles import transcribe

        wav_path = work_dir / "arrow_audio_16k.wav"
        _to_wav_16k_mono(audio_path, wav_path, on_log)
        words = transcribe(str(wav_path), model_size="base", language="es")
    except Exception as exc:  # noqa: BLE001 — nunca abortar por esto
        on_log(f"[flecha] Whisper falló ({str(exc)[:120]}) — flecha desde el inicio")
        return 0.0, _arrow_end(0.0, video_dur)

    hit = None
    for w in words:
        token = re.sub(r"[^a-záéíóúñ]", "", (w.get("word") or "").lower())
        if any(kw in token for kw in config.ARROW_KEYWORDS):
            hit = w
            break

    if hit is None:
        on_log("[flecha] sin palabra gatillo detectada — flecha desde el inicio")
        return 0.0, _arrow_end(0.0, video_dur)

    t0 = max(0.0, float(hit["start"]) - config.ARROW_LEAD_S)
    on_log(f"[flecha] '{hit['word']}' detectada en {hit['start']:.2f}s → flecha en {t0:.2f}s")
    return t0, _arrow_end(t0, video_dur)


def _arrow_end(t0: float, video_dur: float | None) -> float:
    """Fin de la flecha: el final del vídeo (con un pelín de margen para que
    ffmpeg no corte el último fotograma). Sin duración conocida se cae al
    valor fijo de config."""
    if video_dur and video_dur > t0:
        return video_dur + 1.0
    return t0 + config.ARROW_DURATION_S


def _overlay_arrow(video_in: Path, audio_path: Path, work_dir: Path, out_path: Path, on_log: OnLog) -> Path:
    t0, t1 = _find_arrow_window(audio_path, work_dir, on_log, probe_duration(video_in))
    # Rotamos el punto de partida de la lista de flechas al azar por vídeo:
    # aquí no hay concepto de "versión" (a diferencia de ready_video), así
    # que un índice aleatorio basta para dar variedad entre productos.
    arrow_mov = _pick_arrow(random.randrange(len(_ARROW_FILES)))
    if not arrow_mov:
        on_log("[4/5] sin flechas disponibles en disco — se continúa sin ella")
        return video_in
    # OJO: NO se puede reusar `_overlay_arrow_ffmpeg` de ready_video aquí.
    # Esa función se apoya en `-shortest` para cortar el `-stream_loop -1` de
    # la flecha, y eso solo funciona si el vídeo lleva pista de AUDIO. En este
    # pipeline el audio se mezcla DESPUÉS (paso 6), así que el vídeo llega
    # mudo, `-shortest` no tiene nada que acotar y el bucle de la flecha
    # generaba un vídeo de 28 MINUTOS a partir de uno de 13 segundos.
    # Aquí se acota con `-t` explícito, que no depende de que haya audio.
    dur = probe_duration(video_in)
    sw_px = int(config.TARGET_W * config.ARROW_SCALE_W)
    enable = f"between(t,{t0:.3f},{t1:.3f})"
    filter_complex = (
        f"[1:v]scale={sw_px}:-2,format=rgba[s];"
        f"[0:v][s]overlay="
        f"x=(main_w*{config.ARROW_CX})-(overlay_w/2):"
        f"y=(main_h*{config.ARROW_CY})-(overlay_h/2):"
        f"enable='{enable}'[v]"
    )
    try:
        _run([
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video_in),
            "-stream_loop", "-1", "-i", arrow_mov,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-movflags", "+faststart", str(out_path),
        ], on_log)
    except RuntimeError as e:
        on_log(f"[4/5] overlay de flecha falló ({e}) — se continúa sin ella")
        return video_in
    return out_path


# ---------------------------------------------------------------------------
# Paso 6 — Mezcla de audio
# ---------------------------------------------------------------------------
# Cadena de voz: compresor suave + realce de habla. Sube el cuerpo de la voz
# sin dejar que los picos suban con ella, que es lo que permite después
# normalizar alto sin saturar.
_VOZ_CADENA = (
    "acompressor=threshold=-20dB:ratio=4:attack=5:release=120:makeup=2,"
    "speechnorm=e=8:r=0.0008:l=1"
)
# Objetivo de sonoridad. Los audios llegan a -17/-21 LUFS y así quedan en
# torno a -12, que es "tocando la línea roja" con picos por debajo de -1 dBTP.
# Subir +16 dB a pelo, como pedía el operador, saturaría: sus audios ya traen
# picos en -0,7 dBTP. Medido: mujer1 pasa de -20,9 a -11,8 LUFS (+9 dB).
_VOZ_LUFS = -11.0
# Pico objetivo con margen: con TP=-1.0 y el limitador a 0.97 el resultado
# medía +0,2 dBTP (el pico REAL, con sobremuestreo, se cuela por encima del
# pico de muestra) y eso recorta al codificar a AAC.
_VOZ_TP = -1.5


def _medir_voz(audio_in: Path, on_log: OnLog) -> dict[str, str]:
    """Primera pasada de `loudnorm`: mide para poder clavar el objetivo.

    En una sola pasada `loudnorm` va a ciegas y se queda corto; con la medida
    delante aplica la ganancia exacta sin pasarse del pico permitido.
    """
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(audio_in), "-af",
         f"{_VOZ_CADENA},loudnorm=I={_VOZ_LUFS}:TP={_VOZ_TP}:LRA=7:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    medidas: dict[str, str] = {}
    for clave in ("input_i", "input_tp", "input_lra", "input_thresh"):
        m = re.search(rf'"{clave}"\s*:\s*"?(-?[\d.]+)"?', r.stderr)
        if m:
            medidas[clave] = m.group(1)
    if len(medidas) < 4:
        on_log("[5/5] ⚠️ no pude medir la sonoridad — se normaliza en una pasada")
        return {}
    return medidas


def _filtro_voz(audio_in: Path, on_log: OnLog) -> str:
    med = _medir_voz(audio_in, on_log)
    norm = f"loudnorm=I={_VOZ_LUFS}:TP={_VOZ_TP}:LRA=7"
    if med:
        norm += (
            f":measured_I={med['input_i']}:measured_TP={med['input_tp']}"
            f":measured_LRA={med['input_lra']}:measured_thresh={med['input_thresh']}"
        )
        on_log(f"[5/5] voz a {_VOZ_LUFS} LUFS (venía a {med['input_i']})")
    # El limitador es la red de seguridad para transitorios sueltos.
    # `level=disabled` es IMPRESCINDIBLE: por defecto `alimiter` RE-NIVELA la
    # salida hacia el límite, así que bajar el límite subía el volumen en vez
    # de bajarlo y el pico acababa por encima de 0 dBTP.
    return f"{_VOZ_CADENA},{norm},alimiter=limit=0.9:level=disabled"


def _mux_audio(video_in: Path, audio_in: Path, out_path: Path, on_log: OnLog) -> Path:
    """Sustituye la pista de audio del vídeo por `audio_in` (la locución ya
    recortada de silencios). El vídeo llega mudo desde el paso 3
    (`duration_match` genera el resultado con `-an`), así que esto es un mux
    directo, no una mezcla de varias pistas."""
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video_in), "-i", str(audio_in),
        "-map", "0:v:0", "-map", "1:a:0",
        "-af", _filtro_voz(audio_in, on_log),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(out_path),
    ], on_log)
    return out_path


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------
def build_video(
    *,
    raw_video: Path,
    audio_path: Path,
    textos: dict,
    # Se conserva por compatibilidad con jobs ya encolados; ya no se usa.
    origen: str = "",
    output_path: Path,
    work_dir: Path,
    layout: str = "gancho_cta_titulo",
    # Herramientas de edición, cada una por separado. Todas activas = el
    # montaje completo de siempre; ninguna = vídeo limpio (solo se mantienen
    # quitado de marca, encuadre y audio, que hacen falta igualmente).
    con_gancho: bool = True,
    con_titulo: bool = True,
    con_cta: bool = True,
    con_flecha: bool = True,
    on_log: OnLog = _noop,
    on_progress: OnProgress = _noop_progress,
) -> Path:
    """Monta el vídeo final de un producto del Nicho POV BOF.

    `textos` = {"gancho", "titulo", "cta"} (strings, cualquiera puede venir
    vacío — el bloque de texto omite las líneas ausentes).
    Las cuatro herramientas (`con_gancho`, `con_titulo`, `con_cta`,
    `con_flecha`) se eligen por separado: se puede pedir solo el nombre del
    producto, solo la flecha, o cualquier combinación. Con las cuatro a
    False el vídeo sale limpio, solo con la voz.

    Devuelve `output_path`. Nunca deja un archivo a medias en destino: solo
    se escribe ahí en el último paso (mux de audio), tras el cual el vídeo
    ya está completo.
    """
    raw_video = Path(raw_video)
    audio_path = Path(audio_path)
    output_path = Path(output_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    on_progress(0.0, "Preparando…")

    # 1) Normalizar resolución/fps. Antes había un paso previo de quitado de
    # marca de agua para Veo3; dejó de ponerla (2026-07) y Kling nunca la
    # puso, así que el paso solo re-encodeaba el vídeo para nada.
    on_log("[1/5] Normalizando a 1080x1920 @ 30fps…")
    normalized = _normalize_resolution(raw_video, work_dir / "01_normalized.mp4", on_log)
    on_progress(0.28, "Normalizado")

    # 3) Cuadrar duración con el audio (módulo ya existente, tal cual)
    on_log("[2/5] Cuadrando duración con el audio…")
    audio_dur = probe_duration(audio_path)
    matched = match_video_to_audio(
        normalized, audio_dur, work_dir / "duration", on_log=on_log,
    )
    on_progress(0.48, "Duración cuadrada")

    piezas = {
        nombre for nombre, activa in (
            ("gancho", con_gancho), ("titulo", con_titulo), ("cta", con_cta),
        ) if activa
    }

    # 4) Bloque de texto
    if piezas:
        on_log(f"[3/5] Quemando texto ({'/'.join(sorted(piezas))})…")
        texted = _burn_text_block(
            matched, textos or {}, work_dir / "04_texted.mp4", on_log, layout,
            piezas, semilla=str(output_path.stem),
        )
        on_progress(0.66, "Texto quemado")
    else:
        on_log("[3/5] Sin textos: se omite el bloque de texto")
        texted = matched
        on_progress(0.66, "Sin textos")

    # 5) Flecha .mov
    if con_flecha:
        on_log("[4/5] Superponiendo flecha…")
        arrowed = _overlay_arrow(
            texted, audio_path, work_dir, work_dir / "05_arrow.mp4", on_log,
        )
        on_progress(0.84, "Flecha superpuesta")
    else:
        on_log("[4/5] Sin flecha")
        arrowed = texted
        on_progress(0.84, "Sin flecha")

    # 6) Mux de audio final → destino
    on_log("[5/5] Mezclando audio final…")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _mux_audio(arrowed, audio_path, output_path, on_log)
    on_progress(1.0, "Listo")

    dur_out = probe_duration(output_path)
    on_log(f"✅ Vídeo final: {output_path.name} ({dur_out:.2f}s)")
    return output_path


# Un CTA que dice "abajo" o "en el enlace" tiene que ser la ÚLTIMA línea:
# puesto en medio, la flecha y el carrito quedan por debajo del nombre del
# producto y la mirada no sigue el recorrido.
_CTA_APUNTA_ABAJO = ("abajo", "enlace", "ficha", "aqui debajo", "te lo dejo")


def layout_for_producto(producto: str, cta: str = "") -> str:
    """Orden de las tres líneas del bloque.

    Si el CTA apunta hacia abajo manda eso y se pone al final. Si no, se
    reparten las dos disposiciones mitad y mitad por número de producto —
    determinista a propósito: el producto 3 siempre sale igual, así que al
    comparar resultados se sabe qué orden llevaba sin anotarlo aparte.
    """
    if any(t in _sin_acentos(cta) for t in _CTA_APUNTA_ABAJO):
        return "gancho_titulo_cta"
    try:
        n = int("".join(c for c in str(producto) if c.isdigit()) or 0)
    except ValueError:
        n = 0
    return "gancho_cta_titulo" if n % 2 else "gancho_titulo_cta"
