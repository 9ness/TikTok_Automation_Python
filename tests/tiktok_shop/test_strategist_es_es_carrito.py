"""Tests del idioma ES-ES + terminología "carrito naranja" (BUG 2 mayo 2026).

Verifican que el system prompt `content_strategist.md`:
1. Tiene la sección IDIOMA OBLIGATORIO ES-ES con vocabulario peninsular.
2. Tiene la sección Terminología TikTok Shop España con CTAs correctos.
3. NO contiene "cesto" en few-shots (era CTA prohibido — no es termi-
   nología TikTok ni España).
4. Sí contiene "carrito naranja" en CTAs y few-shots.
5. Lista palabras LATAM como prohibidas (wey, chévere, ahorita, etc.).

También verifica que el `_mock_strategy` (modo Gemini-no-configurado)
devuelve un `cta_text` con "carrito naranja", NO "cesto".
"""

from __future__ import annotations

import re

from src.tiktok_shop.api.gemini import load_system_prompt
from src.tiktok_shop.pipeline.strategist import _mock_strategy


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


# ---------------------------------------------------------------------------
# Strategist .md — terminología TikTok Shop
# ---------------------------------------------------------------------------
class TestStrategistUsesCarritoNaranja:
    def setup_method(self):
        self.prompt = _normalize(load_system_prompt("content_strategist.md"))

    def test_no_cesto_in_few_shots_or_rules(self):
        """`cesto` está PROHIBIDO en CTAs y few-shots de TikTok Shop España.

        El icono shoppable se llama "carrito (naranja)", NO cesto.
        """
        # Buscamos "cesto" en CTAs o como verbo de instrucción ("toca el cesto")
        forbidden_substrings = [
            "toca el cesto",
            'el cesto"',  # cesto como CTA prohibido — siempre debería estar en una lista negra
        ]
        # En la sección "PROHIBIDOS" sí puede aparecer en formato negativo:
        # `❌ "Toca el cesto"` — eso ESTÁ permitido como anti-ejemplo.
        # Pero los CTAs reales NO deben usarlo.

        # Test: el voiceover_script de los few-shots NO debe contener "cesto"
        # Buscamos `voiceover_script": "...cesto...` (literal en JSON examples)
        match = re.search(
            r'"voiceover_script"\s*:\s*"[^"]*cesto[^"]*"',
            self.prompt, re.IGNORECASE,
        )
        assert match is None, (
            f"❌ Few-shot voiceover_script contiene 'cesto': {match.group(0)[:100] if match else ''}"
        )

        # Test: los `cta_text` de few-shots NO deben contener "cesto"
        match = re.search(
            r'"cta_text"\s*:\s*"[^"]*cesto[^"]*"',
            self.prompt, re.IGNORECASE,
        )
        assert match is None, (
            "❌ Few-shot cta_text contiene 'cesto'."
        )

    def test_has_carrito_naranja_terminology_section(self):
        """Debe haber sección explícita sobre 'carrito naranja' como CTA correcto."""
        assert "carrito naranja" in self.prompt, (
            "Falta terminología 'carrito naranja' en el .md."
        )
        # Debe enseñar varias formas correctas
        cta_forms_expected = [
            "carrito naranja para",  # "para que lo pilles tú", etc
            "dale al carrito naranja",
            "pulsa el carrito",
        ]
        for cta in cta_forms_expected:
            assert cta in self.prompt, f"Falta CTA correcto '{cta}' en el .md."

    def test_has_prohibited_cta_section(self):
        """Debe listar CTAs prohibidos: cesto, link in bio, compra ahora."""
        # Buscamos la sección con estos prohibidos listados
        prohibited_markers = [
            "cesto",  # mencionado como prohibido en la sección PROHIBIDOS
            "link in bio",
            "compra ahora",
        ]
        for m in prohibited_markers:
            assert m in self.prompt, (
                f"Falta '{m}' en lista de CTAs prohibidos."
            )

    def test_few_shots_use_carrito_in_cta_text(self):
        """Los `cta_text` de los few-shots deben usar 'carrito'.

        Filtra la línea del schema template ('Final call to action') que
        no es un few-shot real sino la descripción del shape esperado.
        """
        cta_matches = re.findall(
            r'"cta_text"\s*:\s*"([^"]+)"', self.prompt
        )
        # Excluir el schema template (placeholder en inglés)
        few_shot_ctas = [
            c for c in cta_matches
            if c.lower() != "final call to action"
        ]
        assert len(few_shot_ctas) >= 2, (
            f"Esperaba 2+ few-shots con cta_text. Encontrados: {few_shot_ctas}"
        )
        for cta in few_shot_ctas:
            assert "carrito" in cta, (
                f"❌ cta_text de few-shot NO usa 'carrito': '{cta}'"
            )


# ---------------------------------------------------------------------------
# Strategist .md — idioma ES-ES (no LATAM)
# ---------------------------------------------------------------------------
class TestStrategistEsEsNoLatam:
    def setup_method(self):
        self.prompt = _normalize(load_system_prompt("content_strategist.md"))

    def test_has_es_es_language_section(self):
        """Debe haber sección IDIOMA OBLIGATORIO con español de España."""
        markers = [
            "español de españa",
            "no latam",
        ]
        for m in markers:
            assert m in self.prompt, (
                f"Falta marker '{m}' en sección de idioma."
            )

    def test_lists_es_es_vocabulary_correct(self):
        """Debe listar vocabulario correcto ES-ES."""
        es_es_words = ["móvil", "ordenador", "vale", "tío", "ahora mismo"]
        for w in es_es_words:
            assert w in self.prompt, (
                f"Falta palabra ES-ES recomendada '{w}' en el .md."
            )

    def test_lists_latam_words_as_prohibited(self):
        """Debe listar palabras LATAM como NO usar."""
        latam_words = [
            "celular", "computadora", "ahorita", "chévere", "wey",
            "okey", "padre", "platicar",
        ]
        for w in latam_words:
            assert w in self.prompt, (
                f"Falta palabra LATAM '{w}' marcada como prohibida en el .md."
            )

    def test_voiceover_few_shots_no_latam_contamination(self):
        """Los voiceovers de los few-shots NO deben contener LATAM literal."""
        voiceover_matches = re.findall(
            r'"voiceover_script"\s*:\s*"([^"]+)"', self.prompt
        )
        assert len(voiceover_matches) >= 2

        # Frases LATAM que no deberían aparecer en voiceovers ejemplares
        # (sí pueden aparecer en la sección "Ejemplos prohibidos" pero NO
        # como voiceover_script de un few-shot):
        forbidden_in_voiceover = [
            "wey,",
            "chévere",
            "ahorita",
            "celular",
            "computadora",
        ]
        for vo in voiceover_matches:
            vo_lower = vo.lower()
            for f in forbidden_in_voiceover:
                assert f not in vo_lower, (
                    f"❌ voiceover_script contiene LATAM '{f}': '{vo[:80]}…'"
                )


# ---------------------------------------------------------------------------
# _mock_strategy (Gemini no configurado) — CTA sin cesto
# ---------------------------------------------------------------------------
class TestMockStrategyCarritoNaranja:
    def test_es_mock_uses_carrito_naranja(self):
        """En modo mock español, el cta_text debe usar 'carrito naranja'."""
        result = _mock_strategy(duration=15, language="es")
        cta = result["cta_text"]
        assert "carrito" in cta.lower(), (
            f"❌ Mock cta_text no usa 'carrito': '{cta}'"
        )
        assert "cesto" not in cta.lower(), (
            f"❌ Mock cta_text sigue usando 'cesto': '{cta}'"
        )

    def test_en_mock_unchanged(self):
        """El mock inglés NO debe ser afectado por el cambio ES."""
        result = _mock_strategy(duration=15, language="en")
        assert "carrito" not in result["cta_text"].lower()
        # tap the basket sigue sirviendo en inglés
        assert "tap" in result["cta_text"].lower() or "basket" in result["cta_text"].lower()
