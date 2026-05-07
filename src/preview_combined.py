"""Preview combinado 9:16 que muestra HOOK + SUBTÍTULOS sobre un canvas
con las zonas seguras de TikTok marcadas.

Sirve para confirmar VISUALMENTE que el hook y los subs no caen sobre la
UI nativa de TikTok (avatar, like/comment/share, descripción, sound bar)
— condición para que el vídeo cumpla los estándares de calidad del
Creator Reward Program.

Las zonas inseguras se pintan con un overlay rojo semitransparente:
- Top: 0–8% (handle + descripción superior)
- Right: 86–100% (botones laterales: avatar, like, comment, share, sound)
- Bottom: 80–100% (caption + sound bar + handle inferior)
- Left: 0–4% (margen izq mínimo)

El fondo del canvas es un gradiente oscuro neutro (placeholder del vídeo).
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


# Zonas seguras TikTok (% sobre W o H)
SAFE_X = (0.04, 0.86)
SAFE_Y = (0.08, 0.80)

# Colores del overlay
UNSAFE_FILL = (220, 30, 30, 70)        # rojo translúcido
UNSAFE_BORDER = (255, 80, 80, 180)     # rojo más opaco para los bordes
SAFE_BORDER = (60, 200, 100, 200)      # verde para el borde de la zona segura
GRID_COLOR = (255, 255, 255, 18)       # grid muy sutil


def _make_background(W: int, H: int) -> Image.Image:
    """Fondo gradient gris oscuro con un grid sutil — simula un frame de
    vídeo real para que el preview no quede plano."""
    bg = Image.new("RGB", (W, H), (28, 30, 38))
    # Gradiente vertical leve
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / max(1, H - 1)
        # interpolar entre dos grises
        r = int(28 + (52 - 28) * t)
        g = int(30 + (52 - 30) * t)
        b = int(38 + (62 - 38) * t)
        grad.putpixel((0, y), (r, g, b))
    grad = grad.resize((W, H))
    bg.paste(grad)

    # Grid sutil cada 10% del ancho/alto
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(1, 10):
        x = int(W * i / 10)
        od.line([(x, 0), (x, H)], fill=GRID_COLOR, width=1)
        y = int(H * i / 10)
        od.line([(0, y), (W, y)], fill=GRID_COLOR, width=1)
    bg = Image.alpha_composite(bg.convert("RGBA"), overlay)
    return bg


def _draw_safe_zones(canvas: Image.Image) -> Image.Image:
    """Pinta el overlay rojo en zonas inseguras + borde verde en la zona segura."""
    W, H = canvas.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    sx0, sx1 = int(W * SAFE_X[0]), int(W * SAFE_X[1])
    sy0, sy1 = int(H * SAFE_Y[0]), int(H * SAFE_Y[1])

    # 4 rectángulos rojos translúcidos (zonas inseguras)
    od.rectangle([0, 0, W, sy0], fill=UNSAFE_FILL)            # top
    od.rectangle([0, sy1, W, H], fill=UNSAFE_FILL)            # bottom
    od.rectangle([0, sy0, sx0, sy1], fill=UNSAFE_FILL)        # left
    od.rectangle([sx1, sy0, W, sy1], fill=UNSAFE_FILL)        # right

    # Borde verde alrededor de la zona segura (donde el contenido SÍ puede ir)
    od.rectangle([sx0, sy0, sx1, sy1], outline=SAFE_BORDER, width=4)

    # Etiquetas "UI TikTok" en zonas inseguras (pequeñas, opacas)
    try:
        # Fuente grande para que se lea aunque escalemos al ancho del componente
        font_label_size = max(20, int(H * 0.018))
        label_font = ImageFont.load_default()
        try:
            from src.font_resolver import safe_truetype
            label_font = safe_truetype(r"C:\Windows\Fonts\arialbd.ttf", font_label_size)
        except Exception:
            pass

        # TOP — handle del usuario
        od.text((W // 2, sy0 // 2), "UI TikTok (handle)",
                font=label_font, fill=(255, 220, 220, 220), anchor="mm")
        # BOTTOM — descripción
        od.text((W // 2, (sy1 + H) // 2), "UI TikTok (caption + sound)",
                font=label_font, fill=(255, 220, 220, 220), anchor="mm")
        # RIGHT — botones laterales
        od.text(((sx1 + W) // 2, H // 2), "UI",
                font=label_font, fill=(255, 220, 220, 220), anchor="mm")
    except Exception:
        pass

    return Image.alpha_composite(canvas, overlay)


def _draw_y_marker(canvas: Image.Image, y_pct: float, label: str,
                   color: tuple) -> Image.Image:
    """Marca horizontal punteada con etiqueta a la izquierda, indicando
    la posición Y configurada."""
    W, H = canvas.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    y = int(H * y_pct)
    # Línea punteada
    dash, gap = 14, 8
    x = 0
    while x < W:
        od.line([(x, y), (min(x + dash, W), y)], fill=color, width=2)
        x += dash + gap

    # Etiqueta (esquina izquierda, dentro del canvas)
    try:
        from src.font_resolver import safe_truetype
        font = safe_truetype(r"C:\Windows\Fonts\arialbd.ttf", max(20, int(H * 0.018)))
    except Exception:
        font = ImageFont.load_default()
    od.text((10, y - 6), label, font=font, fill=color, anchor="lb")

    return Image.alpha_composite(canvas, overlay)


def _draw_subs_max_width(
    canvas: Image.Image,
    max_width_pct: float,
    y_pct: float,
    sub_block_h_px: int,
) -> Image.Image:
    """Dibuja un recuadro blanco sutil indicando el ancho máximo del bloque
    de subtítulos. Sirve para que el usuario vea visualmente cuánto se
    expandirá el texto antes de pasar a otra línea."""
    W, H = canvas.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    mw = max(0.20, min(1.0, float(max_width_pct)))
    box_w = int(W * mw)
    x0 = (W - box_w) // 2
    x1 = x0 + box_w

    y_center = int(H * y_pct)
    half_h = max(60, sub_block_h_px // 2 + 20)  # un poco de aire alrededor
    y0 = max(0, y_center - half_h)
    y1 = min(H, y_center + half_h)

    # Recuadro blanco semi-transparente con esquinas suaves
    od.rounded_rectangle(
        [x0, y0, x1, y1],
        radius=10,
        outline=(255, 255, 255, 130),
        width=3,
    )

    # Etiqueta arriba a la derecha del recuadro
    try:
        from src.font_resolver import safe_truetype
        font = safe_truetype(r"C:\Windows\Fonts\arialbd.ttf", max(18, int(H * 0.016)))
    except Exception:
        font = ImageFont.load_default()
    od.text(
        (x1 - 8, y0 - 8),
        f"ancho máx {int(mw * 100)}%",
        font=font,
        fill=(255, 255, 255, 200),
        anchor="rb",
    )

    return Image.alpha_composite(canvas, overlay)


def render_combined_preview(
    hook_text: str | None,
    hook_style: dict | None,
    sub_text: str,
    sub_style: dict | None,
    sub_highlight_idx: int = 1,
    video_size: tuple[int, int] = (1080, 1920),
    show_safe_zones: bool = True,
    show_y_markers: bool = True,
    show_subs_width_box: bool = True,
) -> Image.Image:
    """Renderiza un frame 9:16 con el hook y los subtítulos en sus posiciones
    reales, marcando las zonas seguras de TikTok.

    Pasa `hook_text=None` para no dibujar el hook (ej: hook desactivado).
    Pasa `sub_text=""` para no dibujar subtítulos.
    """
    W, H = video_size
    canvas = _make_background(W, H)

    # 1. Zonas seguras (capa más baja)
    if show_safe_zones:
        canvas = _draw_safe_zones(canvas)

    # 2. Hook box (si está activo)
    if hook_text and hook_style:
        try:
            from src.text_hook import render_hook_box, DEFAULT_HOOK_STYLE
            hs = {**DEFAULT_HOOK_STYLE, **(hook_style or {})}
            hook_img = render_hook_box(hook_text, hs, (W, H))
            # render_hook_box devuelve canvas del ancho del vídeo y altura
            # variable. Lo posicionamos centrado verticalmente en hook_y_position.
            y_center = int(H * hs.get("y_position_pct", 0.33))
            y_top = max(0, y_center - hook_img.size[1] // 2)
            canvas.alpha_composite(hook_img, (0, y_top))
        except Exception as e:
            print(f"[preview_combined] error hook: {e}")

    # 3. Subtítulos (si está activo)
    sub_block_h = 0
    sub_y_pct = 0.62
    sub_max_width_pct = None
    if sub_text and sub_style:
        try:
            from src.subtitles import render_chunk_image, DEFAULT_STYLE
            ss = {**DEFAULT_STYLE, **(sub_style or {})}
            words = [{"word": w, "start": 0.0, "end": 1.0}
                     for w in sub_text.split() if w.strip()]
            if words:
                idx = max(0, min(sub_highlight_idx, len(words) - 1))
                chunk_img = render_chunk_image(words, idx, ss, (W, H))
                # La función devuelve un canvas con altura justo del bloque
                # de texto. Lo posicionamos en y_position_pct.
                sub_y_pct = ss.get("y_position_pct", 0.62)
                y_center = int(H * sub_y_pct)
                y_top = max(0, y_center - chunk_img.size[1] // 2)
                canvas.alpha_composite(chunk_img, (0, y_top))
                sub_block_h = chunk_img.size[1]
                # max_width_pct: None ⇒ usa el ancho seguro TikTok ≈ 0.73
                sub_max_width_pct = ss.get("max_width_pct")
                if sub_max_width_pct is None:
                    sub_max_width_pct = SAFE_X[1] - SAFE_X[0]
        except Exception as e:
            print(f"[preview_combined] error subs: {e}")

    # 3b. Recuadro blanco sutil mostrando el ancho máximo configurado
    # del bloque de subtítulos (capa antes de los markers Y).
    if show_subs_width_box and sub_text and sub_style and sub_max_width_pct:
        try:
            canvas = _draw_subs_max_width(
                canvas, sub_max_width_pct, sub_y_pct, sub_block_h,
            )
        except Exception as e:
            print(f"[preview_combined] error width box: {e}")

    # 4. Líneas Y indicativas (capa superior, para que se vean sobre el contenido)
    if show_y_markers:
        if hook_text and hook_style:
            y_pct = (hook_style or {}).get("y_position_pct", 0.33)
            canvas = _draw_y_marker(canvas, y_pct, f"hook Y={y_pct:.2f}",
                                    color=(255, 215, 0, 200))
        if sub_text and sub_style:
            y_pct = (sub_style or {}).get("y_position_pct", 0.62)
            canvas = _draw_y_marker(canvas, y_pct, f"subs Y={y_pct:.2f}",
                                    color=(0, 200, 255, 200))

    return canvas
