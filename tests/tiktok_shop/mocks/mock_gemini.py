"""Mocks de Gemini para los 4 directors + 2 prompt-only.

Cada función devuelve el shape JSON/string que devolvería el modelo real,
hardcoded con valores realistas. Útiles tanto para tests del runner como
para reemplazar al vuelo `generate_json` / `generate_text` del módulo gemini.

Patrón de uso:

    monkeypatch.setattr(
        'src.tiktok_shop.pipeline.analyzer.generate_json',
        lambda *a, **kw: fake_analyzer_json(),
    )
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# product_analyst.md → JSON de ficha de producto
# ---------------------------------------------------------------------------
def fake_analyzer_json(*_args, **_kwargs) -> dict:
    return {
        "product_type": "fitness supplement",
        "category": "fitness_supplements",
        "subcategory": "creatine",
        "key_features": [
            "Gominolas sabor lima-limón",
            "4500mg por dosis",
            "90 unidades por bote",
            "Sin azúcar añadido",
        ],
        "materials_visual": ["plastic jar", "matte label"],
        "has_complex_packaging_text": True,
        "best_camera_angles": ["packshot", "in_use", "macro", "lifestyle"],
        "suggested_audiences": [
            "Hombres 18-35 fitness",
            "Estudiantes deportistas",
            "Gym lovers principiantes",
            "Atletas amateur",
            "Personas que odian el polvo de creatina",
        ],
        "selling_points": [
            "Más fácil que tomar polvo",
            "Sabor agradable a fruta",
            "Dosificación cómoda",
        ],
        "photos_quality_assessment": "high",
        "needs_nano_banana_regeneration": False,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# content_strategist.md → estrategia + voiceover_script + estructura
# ---------------------------------------------------------------------------
def fake_strategist_json(*_args, **_kwargs) -> dict:
    return {
        "hook_text": "POV: descubres las gominolas que sustituyen tu creatina en polvo.",
        "voiceover_script": (
            "POV: descubres las gominolas que sustituyen tu creatina en polvo. "
            "Cuatro mil quinientos miligramos en una sola dosis. Sabor lima-limón, "
            "sin grumos, sin batidoras. Toca el cesto y pruébalo."
        ),
        "captions_emphasis": ["GOMINOLAS", "4500MG", "SIN POLVO"],
        "cta_text": "Toca el cesto y pruébalo.",
        "video_structure": [
            {
                "clip_number": 1, "duration_seconds": 5, "purpose": "hook",
                "visual_description": "macro shot del bote desde arriba con luz suave",
                "voiceover_segment": "POV: descubres las gominolas que sustituyen tu creatina en polvo.",
            },
            {
                "clip_number": 2, "duration_seconds": 5, "purpose": "demo",
                "visual_description": "manos cogiendo una gominola del bote",
                "voiceover_segment": "Cuatro mil quinientos miligramos en una sola dosis.",
            },
            {
                "clip_number": 3, "duration_seconds": 5, "purpose": "cta",
                "visual_description": "lifestyle: chico fitness sonriendo con el bote",
                "voiceover_segment": "Toca el cesto y pruébalo.",
            },
        ],
        "human_presence_required": True,
        "tiktok_hashtags": ["#fyp", "#fitness", "#creatina", "#gimnasio", "#suplementos"],
    }


# ---------------------------------------------------------------------------
# seedance_image_to_video_director.md → list[clip dicts]
# ---------------------------------------------------------------------------
def fake_seedance_director_list(*_args, **_kwargs) -> list[dict]:
    return [
        {
            "clip_idx": 0, "duration": 5, "ref_photo_index": 0,
            "use_first_frame_anchor": False,
            "anchor_to_previous_clip_end": None,
            "prompt": (
                "[CAMERA]: slow push-in from upper-right. "
                "[SUBJECT]: producto sobre superficie blanca minimalista. "
                "[LIGHTING]: soft daylight, warm. "
                "[STYLE]: cinematic commercial. "
                "[NEGATIVES]: text artifacts, faces, fast cuts."
            ),
        },
        {
            "clip_idx": 1, "duration": 5, "ref_photo_index": 1,
            "use_first_frame_anchor": True,
            "anchor_to_previous_clip_end": 0,
            "prompt": (
                "[CAMERA]: hands picking gummy from jar, slow orbit. "
                "[SUBJECT]: mano cogiendo gominola, no rostro. "
                "[STYLE]: ASMR macro warm tones. "
                "[NEGATIVES]: full face, fingers deformity."
            ),
        },
        {
            "clip_idx": 2, "duration": 5, "ref_photo_index": 2,
            "use_first_frame_anchor": True,
            "anchor_to_previous_clip_end": 1,
            "prompt": (
                "[CAMERA]: wide lifestyle shot, slow dolly. "
                "[SUBJECT]: torso (no cara) con bote en mano. "
                "[STYLE]: lifestyle aspirational. "
                "[NEGATIVES]: gym equipment, multiple people."
            ),
        },
    ]


# ---------------------------------------------------------------------------
# seedance_pro_director.md → dict único multi-shot
# ---------------------------------------------------------------------------
def fake_pro_director_dict(*_args, **_kwargs) -> dict:
    return {
        "duration": 15,
        "ref_photos_indices": [0, 1, 2],
        "ref_videos": [],
        "ref_audios": [],
        "prompt": (
            "Shot 1 (0-5s): slow push-in on product, soft studio lighting, cinematic. "
            "Shot 2 (5-10s): orbit close-up showing texture detail, same warm lighting. "
            "Shot 3 (10-15s): hand holding the product, lifestyle context. "
            "Smooth transitions between shots. Consistent product appearance and lighting."
        ),
    }


# ---------------------------------------------------------------------------
# veo3_director.md → string prompt
# ---------------------------------------------------------------------------
def fake_veo3_prompt_text(*_args, **_kwargs) -> str:
    return (
        "[CAMERA]: slow push-in from upper-right, gentle dolly. "
        "[SUBJECT]: jar of fitness creatine gummies on minimalist white surface. "
        "[ENVIRONMENT]: clean studio with soft window light. "
        "[LIGHTING]: warm daylight from upper-left, soft shadows. "
        "[STYLE]: cinematic commercial, premium feel. "
        "[NEGATIVE]: text smaller than 30% of frame, multiple faces, fast cuts. "
        "9:16 vertical format, 8 seconds, single continuous shot."
    )


# ---------------------------------------------------------------------------
# nano_banana_director.md → string prompt para generar fotos
# ---------------------------------------------------------------------------
def fake_nano_banana_text(*_args, **_kwargs) -> str:
    return (
        "Generate professional product photography of Primal Pump Gummies from "
        "the attached reference images:\n"
        "1. Front view, clean white background, soft studio lighting.\n"
        "2. 3/4 angle view, same studio lighting, same background.\n"
        "3. Hand holding the jar, lifestyle context, warm natural light.\n"
        "4. Macro detail of gummies texture and color.\n"
        "5. Top-down view on minimalist white surface.\n\n"
        "CRITICAL: Maintain EXACT product appearance across all images — same "
        "colors, same labels, same proportions, same shape. Only angle and "
        "context vary.\n"
        "9:16 vertical format. Ultra high quality. Photorealistic. No watermarks."
    )
