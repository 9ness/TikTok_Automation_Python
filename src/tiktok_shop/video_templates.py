"""Plantillas de vídeo REUTILIZABLES por tipo de producto (sin coste IA).

Idea (del operador de 100€/día): no analizar cada producto a fondo para
testear a volumen. En su lugar, prompts FIJOS por nicho — solo cambias la
variable {product} y adjuntas la foto del producto al pegarlos.
Cero llamadas a Gemini = gratis + permite volumen.

Flujo del operador (Magnific Premium+ con Kling 2.5 i2v ilimitado):
1) Genera la FOTO del primer frame en Nano Banana con `first_frame` (adjuntando
   la foto real del producto como referencia exacta).
2) Pasa esa foto como start-frame a Kling con `kling` (motion).
Cada plantilla trae además `prompt` (Veo 3 texto-a-vídeo) como alternativa.

Reglas comunes:
- Usa la foto adjunta como referencia EXACTA del producto.
- NADA de caras ni personas completas IA — solo POV / manos / pies.
- Estética nativa UGC (foto de móvil, luz natural), no anuncio pulido.
- Sin texto en pantalla (los overlays/subtítulos se añaden después).
"""

from __future__ import annotations

# Sufijo común que fija las reglas en TODAS las plantillas Veo 3.
_RULES = (
    " Use the attached product photo as the EXACT reference (same colors, "
    "labels, shape). 8-second 9:16 vertical video. Slow cinematic camera. "
    "Native UGC phone-shot look, natural lighting. NO human faces, NO full "
    "person — only hands / feet / POV. No on-screen text. Single continuous shot."
)

# Reglas para la FOTO del primer frame (Nano Banana, imagen estática).
_FF_RULES = (
    " Photorealistic vertical 9:16 photo for the FIRST FRAME of a video. Use the "
    "attached product photo as the EXACT reference (same colors, labels, shape). "
    "Native UGC phone-shot look, natural lighting. NO human faces, NO full person "
    "— only hands / feet / POV. No on-screen text. Sharp, well-lit, realistic."
)

# Reglas para Kling (image-to-video desde el primer frame).
_KLING_RULES = (
    " Image-to-video from the attached first frame. 5-second 9:16 vertical clip. "
    "Animate with subtle realistic motion only — NO morphing, do not change the "
    "product shape/labels. Native UGC handheld feel, natural lighting. NO human "
    "faces, NO full person — only hands / feet / POV. No on-screen text. "
    "Single continuous shot."
)


VIDEO_TEMPLATES: list[dict] = [
    # ── Universales (sirven para casi cualquier producto) ──
    {
        "id": "pov_unboxing",
        "name": "POV · te acaba de llegar",
        "niches": ["universal"],
        "prompt": (
            "POV: you just received {product}. First-person hands opening the "
            "package and revealing the product on a cozy home surface, excited "
            "reveal moment, soft natural light." + _RULES
        ),
        "first_frame": (
            "POV first-person shot: hands holding the still-closed package of "
            "{product} on a cozy home surface, soft natural window light, "
            "anticipation moment before opening."
        ),
        "motion": (
            "Hands open the package and reveal {product}, excited reveal moment, "
            "slight push-in toward the product."
        ),
        "notes": "El gancho universal. Funciona para casi todo.",
    },
    {
        "id": "demo_closeup",
        "name": "Demo · primer plano en uso",
        "niches": ["universal"],
        "prompt": (
            "Close-up product demo of {product}: hands using/showing it and its "
            "key details, slow orbit and push-in on the texture and features, "
            "clean home/desk background." + _RULES
        ),
        "first_frame": (
            "Close-up of {product} held in hands on a clean desk/home background, "
            "key details facing the camera, crisp even lighting."
        ),
        "motion": (
            "Slow orbit and push-in over the texture and features while the hands "
            "gently rotate {product} to show its details."
        ),
        "notes": "Explicativo de producto, sirve para casi todo.",
    },
    # ── Por nicho ──
    {
        "id": "skincare_apply",
        "name": "Belleza/Skincare · aplicación",
        "niches": ["skincare", "belleza", "beauty", "cosmetica"],
        "prompt": (
            "ASMR close-up of {product}: hands dispensing the product and "
            "applying it on skin (only hand/forearm visible), showing texture "
            "and absorption, bright clean bathroom vanity, dewy aesthetic." + _RULES
        ),
        "first_frame": (
            "Hands holding {product} next to skin (only hand/forearm visible) on "
            "a bright clean bathroom vanity, dewy aesthetic, soft glowy light."
        ),
        "motion": (
            "Dispense the product and apply it on the skin, showing the texture "
            "and absorption in a slow ASMR close-up."
        ),
        "notes": "Textura + aplicación en mano/brazo.",
    },
    {
        "id": "fitness_supplement",
        "name": "Fitness/Suplemento · preparación",
        "niches": ["fitness", "suplementos", "creatina", "proteina", "gym"],
        "prompt": (
            "Hands scooping {product} into a shaker, mixing it, gym bag and "
            "weights blurred in the background, energetic morning light, "
            "satisfying prep ritual." + _RULES
        ),
        "first_frame": (
            "Hands holding a scoop over an open tub of {product} next to a shaker, "
            "gym bag and weights blurred behind, energetic morning light."
        ),
        "motion": (
            "Scoop {product} into the shaker, close it and shake, satisfying "
            "pre-workout prep ritual."
        ),
        "notes": "Scoop + shaker + ambiente gym.",
    },
    {
        "id": "home_before_after",
        "name": "Hogar/Gadget · antes y después",
        "niches": ["hogar", "home", "cocina", "kitchen", "organizador", "gadget"],
        "prompt": (
            "Before-and-after of a messy space transformed using {product}: "
            "hands installing/using it, the space goes from cluttered to tidy, "
            "satisfying reveal, real home setting." + _RULES
        ),
        "first_frame": (
            "A cluttered, messy home space with {product} placed in frame ready "
            "to be used, real home setting, honest natural light (the 'before')."
        ),
        "motion": (
            "Hands install/use {product} and the space transforms from cluttered "
            "to tidy in a satisfying before-and-after reveal."
        ),
        "notes": "Transformación del espacio, muy compartible.",
    },
    {
        "id": "fashion_feet_walk",
        "name": "Moda/Calzado · sin cara",
        "niches": ["moda", "calzado", "zapatos", "crocs", "fashion", "ropa"],
        "prompt": (
            "Lifestyle shot of {product} worn: feet/lower legs walking on a "
            "nice street or home floor (face out of frame), plus a clean "
            "flat-lay close-up, aspirational casual aesthetic." + _RULES
        ),
        "first_frame": (
            "Clean flat-lay / low-angle close-up of {product} (footwear) on a "
            "nice floor, feet about to step into them, face out of frame, "
            "aspirational casual aesthetic."
        ),
        "motion": (
            "Feet and lower legs walking on a nice street or home floor wearing "
            "{product}, face out of frame, relaxed confident pace."
        ),
        "notes": "Pies/piernas caminando + flat-lay. Sin cara.",
    },
    {
        "id": "tech_unbox_features",
        "name": "Tech/Gadget · features",
        "niches": ["tech", "tecnologia", "gadget", "electronica", "auriculares"],
        "prompt": (
            "Hands unboxing {product} and showing its main features one by one, "
            "macro close-ups of the buttons/ports/screen, modern desk setup, "
            "crisp lighting." + _RULES
        ),
        "first_frame": (
            "Hands holding the closed box of {product} on a modern desk setup, "
            "crisp clean lighting, ready to unbox."
        ),
        "motion": (
            "Unbox {product} and show its main features one by one with macro "
            "close-ups on the buttons/ports/screen."
        ),
        "notes": "Unboxing + macro de características.",
    },
    {
        "id": "food_satisfying",
        "name": "Comida/Bebida · satisfying",
        "niches": ["comida", "food", "bebida", "snack", "gominolas"],
        "prompt": (
            "Satisfying close-up of {product}: hands opening it and a slow "
            "macro of the texture/pour, appetizing natural light, kitchen "
            "counter background." + _RULES
        ),
        "first_frame": (
            "{product} closed on a kitchen counter with hands resting near it, "
            "appetizing natural light, mouth-watering close-up framing."
        ),
        "motion": (
            "Hands open {product} and a slow appetizing macro of the texture / "
            "pour fills the frame."
        ),
        "notes": "Macro apetitoso + manos.",
    },
]


def render_template(prompt_template: str, product_name: str) -> str:
    """Rellena {product} con el nombre del producto."""
    return prompt_template.replace("{product}", product_name or "the product")


def render_first_frame(tpl: dict, product_name: str) -> str:
    """Prompt para Nano Banana: la FOTO del primer frame del vídeo."""
    return render_template(tpl.get("first_frame", "") + _FF_RULES, product_name)


def render_kling(tpl: dict, product_name: str) -> str:
    """Prompt para Kling (image-to-video) desde el primer frame."""
    return render_template(tpl.get("motion", "") + _KLING_RULES, product_name)


def templates_for_niche(niche: str | None) -> list[dict]:
    """Plantillas universales + las que matcheen el nicho/categoría dada."""
    if not niche:
        return list(VIDEO_TEMPLATES)
    n = niche.lower()
    out = []
    for t in VIDEO_TEMPLATES:
        tags = t["niches"]
        if "universal" in tags or any(tag in n or n in tag for tag in tags):
            out.append(t)
    return out or list(VIDEO_TEMPLATES)
