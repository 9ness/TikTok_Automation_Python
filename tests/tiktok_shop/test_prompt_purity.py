"""Tests de pureza de prompts (.md) — anti few-shot poisoning.

Verifican que los system prompts de Gemini NO contienen ejemplos sesgados
hacia un nicho concreto que provoque que el modelo regurgite contenido
literal cuando el producto del input coincide casualmente con ese nicho.

Contexto del bug (mayo 2026): para PRIMAL PUMP (gominolas creatina) el
strategist devolvía "POV: descubres las gominolas... compañero de gym...
lima limón" y el director generaba prompts Atlas tipo "torso of person
in gym setting holding the jar" → Atlas i2v ignoraba la foto del bote y
generaba espaldas de gym, bocas con limón, etc.

Causa raíz: el few-shot del strategist usaba EXACTAMENTE ese producto
(creatina gummies) y el few-shot del director CTA mostraba "torso en gym".

Fix: few-shots reescritos a nichos opuestos (cosmético + cocina) y reglas
de fidelidad explícitas en el director.
"""

from __future__ import annotations

import re

from src.tiktok_shop.api.gemini import load_system_prompt


def _normalize(text: str) -> str:
    """Lowercase + colapsa whitespace para que las assertions matchen
    across saltos de línea e indentación de los .md."""
    return re.sub(r"\s+", " ", text.lower())


# ---------------------------------------------------------------------------
# content_strategist.md — sin few-shot poisoning
# ---------------------------------------------------------------------------
class TestStrategistNoCreatinaPollution:
    def setup_method(self):
        self.prompt = _normalize(load_system_prompt("content_strategist.md"))

    def test_no_creatina_gummies_voiceover_literal(self):
        """El few-shot NO debe contener voiceover de creatina/gym.

        Si Gemini ve este texto y el producto del input es creatina gummies
        o cualquier suplemento fitness, copiará el texto literalmente
        (poisoning). Ahora los few-shots son cosmético + cocina.
        """
        contaminating_phrases = [
            "lima limón",
            "compañero de gym",
            "pov: descubres las gominolas",
            "cuatro mil quinientos miligramos",
            "creatina en polvo",
            "sin grumos, sin batidoras",
        ]
        for phrase in contaminating_phrases:
            assert phrase not in self.prompt, (
                f"❌ Frase contaminante '{phrase}' sigue en el few-shot del strategist. "
                "Producirá poisoning para productos fitness."
            )

    def test_no_gym_setting_in_visual_description(self):
        """visual_description del few-shot NO debe pedir gym/dumbbells.

        Estas escenas las debe inventar el strategist según el producto
        real, NO copiarlas del few-shot.
        """
        for forbidden in ["gym con bote en mano", "gym con bote", "compañero de gym"]:
            assert forbidden not in self.prompt, (
                f"❌ '{forbidden}' aparece en few-shot. Producirá visual_description "
                "con escenarios de gym aunque el producto no tenga nada que ver."
            )

    def test_has_two_distinct_niche_examples(self):
        """Debe haber 2+ few-shots de nichos distintos para evitar poisoning."""
        # Nichos opuestos esperados: cosmético + cocina
        assert "sérum" in self.prompt or "serum" in self.prompt, (
            "Falta few-shot del nicho cosmético (sérum facial)."
        )
        assert "tabla" in self.prompt and "cortar" in self.prompt, (
            "Falta few-shot del nicho cocina (tabla de cortar)."
        )

    def test_explicit_warning_not_to_copy_few_shot(self):
        """Debe haber warning explícito sobre NO copiar el few-shot literalmente."""
        # Buscamos al menos uno de varios markers de "no copiar literal"
        markers = [
            "no copiar literal",
            "nunca copies",
            "adapta al producto",
            "adapta al producto real",
            "no copies el few-shot",
        ]
        assert any(m in self.prompt for m in markers), (
            "Falta warning explícito de 'no copiar el few-shot literalmente'. "
            "Sin esto el modelo tiende a regurgitar el ejemplo."
        )


# ---------------------------------------------------------------------------
# seedance_image_to_video_director.md — fidelidad a la foto
# ---------------------------------------------------------------------------
class TestDirectorRespectsReference:
    def setup_method(self):
        self.prompt = _normalize(load_system_prompt("seedance_image_to_video_director.md"))

    def test_no_gym_torso_dumbbells_few_shot(self):
        """El few-shot CTA original ('torso of person in gym setting,
        dumbbells out of focus') está ELIMINADO. Si vuelve, Atlas i2v
        genera espaldas de gym aunque la foto sea un bote sobre fondo blanco.
        """
        # El few-shot anterior tenía estas frases LITERALES:
        forbidden_substrings = [
            "torso of a person (no face) holding the jar in gym setting",
            "blurred gym in background, dumbbells out of focus",
            "cool natural gym light",
            "lifestyle aspirational",
        ]
        for s in forbidden_substrings:
            assert s.lower() not in self.prompt, (
                f"❌ Frase contaminante en director: '{s}'. "
                "Atlas la copia y genera espaldas de gym aunque la foto sea solo el producto."
            )

    def test_has_critical_fidelity_rules(self):
        """Debe haber reglas explícitas de fidelidad a la foto de referencia."""
        # Reglas mínimas exigidas en el .md
        required_markers = [
            # 1. ALWAYS keep exact product visible
            "exact product",
            # 2. NEVER replace subject with people/scenes not in ref
            "never replace",
            # 3. Animate THAT product, not generic content
            "animate that product",
            # 4. If visual_description mentions setting not in photo, IGNORE it
            "ignore that setting",
        ]
        for m in required_markers:
            assert m in self.prompt, (
                f"❌ Falta regla crítica '{m}' en seedance_image_to_video_director.md. "
                "Sin esto el director sigue generando escenarios inventados."
            )

    def test_few_shots_use_neutral_camera_not_settings(self):
        """Los few-shots deben describir movimientos de cámara neutros,
        no escenarios de nicho."""
        # Verbos de cámara que SÍ deben aparecer
        camera_terms = ["push-in", "orbit", "macro"]
        for t in camera_terms:
            assert t in self.prompt, f"Falta verb cámara '{t}' en few-shots."

        # NO debe haber settings de nicho específicos en los few-shots
        # (gym, kitchen, street pueden aparecer en NEGATIVES — eso está OK)
        # Aquí verificamos que el subject del few-shot dice "exact product
        # from the reference image" en lugar de "fitness gummies" o similar.
        assert "exact product from the reference" in self.prompt, (
            "Los few-shots deben anclar SUBJECT a la foto de referencia, "
            "no a un producto/nicho concreto."
        )

    def test_few_shot_no_fitness_gummies_literal(self):
        """El few-shot anterior decía 'jar of fitness gummies' — eliminado."""
        assert "jar of fitness gummies" not in self.prompt, (
            "El SUBJECT del few-shot todavía dice 'jar of fitness gummies'. "
            "Debe ser neutro: 'the exact product from the reference image'."
        )


# ---------------------------------------------------------------------------
# seedance_pro_director.md — mismas reglas de fidelidad
# ---------------------------------------------------------------------------
class TestProDirectorRespectsReference:
    def setup_method(self):
        self.prompt = _normalize(load_system_prompt("seedance_pro_director.md"))

    def test_no_gym_in_few_shot(self):
        forbidden = [
            "blurred gym background",
            "hands holding the jar in lifestyle context",
            "jar of fitness gummies",
        ]
        for s in forbidden:
            assert s not in self.prompt, (
                f"❌ '{s}' sigue en seedance_pro_director.md. "
                "Pro generará escenarios de gym aunque las fotos sean solo el producto."
            )

    def test_has_critical_fidelity_rules(self):
        required_markers = [
            "exact product",
            "never replace",
            "ignore that setting",
        ]
        for m in required_markers:
            assert m in self.prompt, (
                f"❌ Falta regla '{m}' en seedance_pro_director.md."
            )

    def test_negatives_block_invented_scenery(self):
        """El cierre del few-shot Pro debe pedir 'do not invent background
        scenery or people not visible in the reference photos'."""
        assert "do not invent background scenery" in self.prompt, (
            "Falta cláusula 'do not invent background scenery' en Pro. "
            "Sin esto el modelo añade gimnasios/cocinas que no están en las fotos."
        )
