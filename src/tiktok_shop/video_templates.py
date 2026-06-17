"""Plantillas de vídeo REUTILIZABLES por tipo de producto (sin coste IA).

Idea (del operador de 100€/día): no analizar cada producto a fondo para
testear a volumen. En su lugar, prompts FIJOS por nicho — solo cambias la
variable {product} y adjuntas la foto del producto al pegarlos en Veo 3 /
Gemini chat. Cero llamadas a Gemini = gratis + permite volumen.

Cada plantilla es un prompt listo para Veo 3 (8s, 9:16). Reglas comunes:
- Usa la foto adjunta como referencia EXACTA del producto.
- NADA de caras ni personas completas IA — solo POV / manos / pies.
- Estética nativa UGC (foto de móvil, luz natural), no anuncio pulido.
- Sin texto en pantalla (los overlays/subtítulos se añaden después).

`render_template(tpl, product_name)` rellena {product}. El frontend lista las
plantillas (filtrables por nicho) y el operador copia + adjunta la foto.
"""

from __future__ import annotations

# Sufijo común que fija las reglas en TODAS las plantillas.
_RULES = (
    " Use the attached product photo as the EXACT reference (same colors, "
    "labels, shape). 8-second 9:16 vertical video. Slow cinematic camera. "
    "Native UGC phone-shot look, natural lighting. NO human faces, NO full "
    "person — only hands / feet / POV. No on-screen text. Single continuous shot."
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
        "notes": "Macro apetitoso + manos.",
    },
]


def render_template(prompt_template: str, product_name: str) -> str:
    """Rellena {product} con el nombre del producto."""
    return prompt_template.replace("{product}", product_name or "the product")


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
