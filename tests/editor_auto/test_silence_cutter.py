"""Tests unitarios de la lógica de cortes del `silence_cutter`.

NO ejecutan FFmpeg, NO llaman a OpenAI, NO descargan Silero VAD. Solo
validan las funciones puras:
  - `_merge_intervals`
  - `_invert_intervals`
  - `_compute_head_tail_cuts`
  - `_parse_ai_cuts` (con el shape de respuesta del prompt analyst v2)

Coste: $0. Sin red.
"""

from __future__ import annotations

from src.editor_auto.tools.silence_cutter import (
    _compute_head_tail_cuts,
    _compute_inter_word_gap_cuts,
    _count_by_reason,
    _count_by_source,
    _detect_repeated_ngrams,
    _filter_cuts_outside_words,
    _filter_phantom_words,
    _invert_intervals,
    _merge_intervals,
    _parse_ai_cuts,
    _split_silero_cuts_by_confidence,
    _trim_cuts_to_avoid_words,
    _verdict_for_score,
)


# ---------------------------------------------------------------------------
# _merge_intervals
# ---------------------------------------------------------------------------
class TestMergeIntervals:
    def test_empty(self):
        assert _merge_intervals([]) == []

    def test_no_overlap(self):
        assert _merge_intervals([(0.0, 1.0), (2.0, 3.0)]) == [(0.0, 1.0), (2.0, 3.0)]

    def test_overlap_merged(self):
        assert _merge_intervals([(0.0, 1.5), (1.0, 2.0)]) == [(0.0, 2.0)]

    def test_adjacent_merged(self):
        # Tolerancia 0.01 — intervalos que casi se tocan deben fusionarse
        assert _merge_intervals([(0.0, 1.0), (1.005, 2.0)]) == [(0.0, 2.0)]

    def test_unsorted_input(self):
        assert _merge_intervals([(5.0, 6.0), (0.0, 1.0), (2.0, 3.0)]) == [
            (0.0, 1.0), (2.0, 3.0), (5.0, 6.0),
        ]

    def test_multiple_overlaps_chain(self):
        # 3 intervalos solapados encadenados → uno solo
        result = _merge_intervals([(0.0, 1.0), (0.5, 2.0), (1.8, 3.0)])
        assert result == [(0.0, 3.0)]

    def test_contained(self):
        # B totalmente dentro de A → A sin cambios
        assert _merge_intervals([(0.0, 5.0), (1.0, 2.0)]) == [(0.0, 5.0)]


# ---------------------------------------------------------------------------
# _invert_intervals
# ---------------------------------------------------------------------------
class TestInvertIntervals:
    def test_empty_cuts_returns_full(self):
        assert _invert_intervals([], 10.0) == [(0.0, 10.0)]

    def test_zero_duration(self):
        assert _invert_intervals([(0.0, 1.0)], 0.0) == []

    def test_single_cut_middle(self):
        # Cortar [3, 5] de un vídeo 10s → conservar [0,3] y [5,10]
        assert _invert_intervals([(3.0, 5.0)], 10.0) == [(0.0, 3.0), (5.0, 10.0)]

    def test_cut_at_start(self):
        assert _invert_intervals([(0.0, 2.0)], 10.0) == [(2.0, 10.0)]

    def test_cut_at_end(self):
        assert _invert_intervals([(8.0, 10.0)], 10.0) == [(0.0, 8.0)]

    def test_full_cut_returns_empty(self):
        assert _invert_intervals([(0.0, 10.0)], 10.0) == []

    def test_multiple_cuts(self):
        assert _invert_intervals([(1.0, 2.0), (5.0, 6.0)], 10.0) == [
            (0.0, 1.0), (2.0, 5.0), (6.0, 10.0),
        ]

    def test_cuts_clamped_to_duration(self):
        # Cut que se sale del rango se clampea
        assert _invert_intervals([(8.0, 15.0)], 10.0) == [(0.0, 8.0)]


# ---------------------------------------------------------------------------
# _compute_head_tail_cuts
# ---------------------------------------------------------------------------
def _w(idx: int, start: float, end: float) -> dict:
    """Helper para fabricar words."""
    return {"idx": idx, "word": f"w{idx}", "start": start, "end": end}


class TestHeadTailCuts:
    def test_empty_words(self):
        assert _compute_head_tail_cuts([], 10.0) == []

    def test_zero_duration(self):
        assert _compute_head_tail_cuts([_w(0, 0.0, 1.0)], 0.0) == []

    def test_no_silence_no_cuts(self):
        # Habla desde t=0 a t=10 sin gaps
        words = [_w(0, 0.0, 5.0), _w(1, 5.0, 10.0)]
        assert _compute_head_tail_cuts(words, 10.0) == []

    def test_head_silence_10s(self):
        # 10s sin hablar al principio (caso real del usuario)
        words = [_w(0, 10.0, 11.0), _w(1, 11.0, 12.0)]
        cuts = _compute_head_tail_cuts(words, 15.0)
        # Cut head: [0, 10 - 0.15 = 9.85]
        assert (0.0, 9.85) in cuts

    def test_tail_silence(self):
        # Termina de hablar a t=8, video dura 15s → cortar [8.05, 15]
        # (tail pad 0.05 — más agresivo que head para evitar colas residuales)
        words = [_w(0, 0.0, 1.0), _w(1, 7.0, 8.0)]
        cuts = _compute_head_tail_cuts(words, 15.0)
        assert (8.05, 15.0) in cuts

    def test_both_head_and_tail(self):
        words = [_w(0, 5.0, 6.0), _w(1, 10.0, 11.0)]
        cuts = _compute_head_tail_cuts(words, 20.0)
        assert len(cuts) == 2
        assert (0.0, 4.85) in cuts        # head pad 0.15
        assert (11.05, 20.0) in cuts      # tail pad 0.05

    def test_silence_below_threshold_not_cut(self):
        # Solo 0.3s de silencio inicial — bajo umbral 0.5s
        words = [_w(0, 0.3, 1.0)]
        assert _compute_head_tail_cuts(words, 10.0) == [
            # Solo tail, no head — tail pad 0.05
            (1.05, 10.0),
        ]

    def test_pad_doesnt_eat_words(self):
        # Si la primera palabra empieza en t=0.6, el pad de 0.15 deja 0.45
        # — no debe nunca cortar dentro de la palabra
        words = [_w(0, 0.6, 1.0)]
        cuts = _compute_head_tail_cuts(words, 10.0)
        head = next((c for c in cuts if c[0] == 0.0), None)
        assert head is not None
        assert head[1] < 0.6


# ---------------------------------------------------------------------------
# _parse_ai_cuts — convierte JSON del prompt a intervalos temporales
# ---------------------------------------------------------------------------
class TestParseAiCuts:
    WORDS = [
        _w(0, 1.0, 1.5),
        _w(1, 1.5, 2.0),
        _w(2, 2.0, 2.5),
        _w(3, 2.5, 3.0),
        _w(4, 5.0, 5.5),   # gap [3.0, 5.0] = posible noise_gap
        _w(5, 5.5, 6.0),
    ]
    DURATION = 10.0

    def test_empty(self):
        assert _parse_ai_cuts([], words=self.WORDS, video_duration=self.DURATION) == []

    def test_word_based_cut(self):
        # Cortar palabras 0-2 → [1.0, 2.5]
        cuts = _parse_ai_cuts(
            [{"start_word_idx": 0, "end_word_idx": 2, "reason": "false_start"}],
            words=self.WORDS,
            video_duration=self.DURATION,
        )
        assert cuts == [(1.0, 2.5)]

    def test_explicit_time_override_for_noise_gap(self):
        # noise_gap: cut entre palabra 3 y palabra 4. El modelo envía
        # t_start/t_end explícitos = (3.0, 5.0). Esto debe prevalecer.
        cuts = _parse_ai_cuts(
            [{
                "start_word_idx": 3, "end_word_idx": 4,
                "t_start": 3.0, "t_end": 5.0,
                "reason": "noise_gap",
            }],
            words=self.WORDS,
            video_duration=self.DURATION,
        )
        assert cuts == [(3.0, 5.0)]

    def test_head_silence_minus_one(self):
        cuts = _parse_ai_cuts(
            [{
                "start_word_idx": -1, "end_word_idx": -1,
                "t_start": 0.0, "t_end": 0.85,
                "reason": "head_silence",
            }],
            words=self.WORDS,
            video_duration=self.DURATION,
        )
        assert cuts == [(0.0, 0.85)]

    def test_tail_silence_minus_two(self):
        cuts = _parse_ai_cuts(
            [{
                "start_word_idx": -2, "end_word_idx": -2,
                "t_start": 6.15, "t_end": 10.0,
                "reason": "tail_silence",
            }],
            words=self.WORDS,
            video_duration=self.DURATION,
        )
        assert cuts == [(6.15, 10.0)]

    def test_head_silence_without_explicit_times_skipped(self):
        # Si -1 viene sin t_start/t_end es inválido → se ignora
        assert _parse_ai_cuts(
            [{"start_word_idx": -1, "end_word_idx": -1}],
            words=self.WORDS,
            video_duration=self.DURATION,
        ) == []

    def test_invalid_indices_skipped(self):
        # idx fuera de rango → skip
        cuts = _parse_ai_cuts(
            [
                {"start_word_idx": 99, "end_word_idx": 100},
                {"start_word_idx": 0, "end_word_idx": 1},
            ],
            words=self.WORDS,
            video_duration=self.DURATION,
        )
        assert cuts == [(1.0, 2.0)]

    def test_negligible_cut_skipped(self):
        # cut t1 - t0 = 0.02s, menor que el threshold 0.05 → se ignora
        cuts = _parse_ai_cuts(
            [{
                "start_word_idx": 0, "end_word_idx": 0,
                "t_start": 1.0, "t_end": 1.02,
            }],
            words=self.WORDS,
            video_duration=self.DURATION,
        )
        assert cuts == []

    def test_clamping_to_duration(self):
        # cut se extiende más allá del vídeo → clamp
        cuts = _parse_ai_cuts(
            [{
                "start_word_idx": -2, "end_word_idx": -2,
                "t_start": 9.5, "t_end": 999.0,
            }],
            words=self.WORDS,
            video_duration=self.DURATION,
        )
        assert cuts == [(9.5, 10.0)]


# ---------------------------------------------------------------------------
# Integración: cuts → merge → invert → keep_intervals
# ---------------------------------------------------------------------------
class TestFullCutsPipeline:
    """Simula el flujo completo del silence_cutter sin ejecutar FFmpeg.

    Caso real: vídeo 20s con
      - 10s de silencio inicial (sin palabras de Whisper)
      - 1 false start [11, 12]
      - 1 noise gap [13.5, 14.2] (tos)
      - Termina de hablar a t=18, 2s de tail silence
    """

    def test_combined_cuts(self):
        duration = 20.0
        words = [
            _w(0, 10.0, 11.0),   # primera palabra real
            _w(1, 11.0, 12.0),   # parte del false start
            _w(2, 12.0, 13.5),
            _w(3, 14.2, 15.0),   # tras la tos
            _w(4, 17.0, 18.0),   # última
        ]
        # 1) Auto head/tail
        head_tail = _compute_head_tail_cuts(words, duration)
        # 2) IA reportaría: false_start palabras 0-1, noise_gap entre 2 y 3
        ai_raw = [
            {"start_word_idx": 0, "end_word_idx": 1, "reason": "false_start"},
            {
                "start_word_idx": 2, "end_word_idx": 3,
                "t_start": 13.5, "t_end": 14.2, "reason": "noise_gap",
            },
        ]
        ai_cuts = _parse_ai_cuts(ai_raw, words=words, video_duration=duration)

        all_cuts = head_tail + ai_cuts
        merged = _merge_intervals(all_cuts)
        keep = _invert_intervals(merged, duration)

        # Head [0, 9.85] + false_start [10, 12] se solapan parcialmente con
        # auto-trim si el padding lo deja — verifico que el primer keep
        # arranca DESPUÉS del false start (palabra 2 = 12.0).
        # Tras merge, los cortes acumulados son aprox:
        #   [0, 10-0.15=9.85] + [10, 12] + [13.5, 14.2] + [18.15, 20]
        # → keep: [9.85, 10], [12, 13.5], [14.2, 18.15]
        keep_starts = [s for s, _ in keep]
        # Asegurar que conservamos contenido después del false_start
        assert any(abs(s - 12.0) < 0.01 for s in keep_starts), keep
        # No deberíamos conservar nada después del tail
        assert all(e <= 18.15 + 0.01 for _, e in keep)

    def test_no_cuts_returns_full_keep(self):
        # Sin cortes (vídeo perfecto sin silencios) → conservar todo
        words = [_w(0, 0.0, 5.0), _w(1, 5.0, 10.0)]
        head_tail = _compute_head_tail_cuts(words, 10.0)
        assert head_tail == []
        keep = _invert_intervals([], 10.0)
        assert keep == [(0.0, 10.0)]


# ---------------------------------------------------------------------------
# Edge case: prompt devuelve cuts solapados → merge los resuelve
# ---------------------------------------------------------------------------
def test_overlapping_ai_cuts_merge_correctly():
    # IA aveces emite cuts que se solapan accidentalmente — el merge
    # debe consolidarlos para que el ffmpeg luego solo vea intervalos
    # disjuntos.
    duration = 20.0
    words = [_w(i, float(i), float(i) + 0.5) for i in range(20)]
    ai_raw = [
        {"start_word_idx": 5, "end_word_idx": 8, "reason": "false_start"},
        {"start_word_idx": 7, "end_word_idx": 10, "reason": "abandoned_tangent"},
    ]
    ai_cuts = _parse_ai_cuts(ai_raw, words=words, video_duration=duration)
    merged = _merge_intervals(ai_cuts)
    # Original: [5.0, 8.5] y [7.0, 10.5] → fusionados [5.0, 10.5]
    assert len(merged) == 1
    assert merged[0] == (5.0, 10.5)


# ---------------------------------------------------------------------------
# Edge case: vídeo cuyas únicas palabras son ruido — IA cuts mayoría del clip
# ---------------------------------------------------------------------------
def test_aggressive_cuts_dont_leave_empty():
    # Si los cuts cubren TODO el vídeo, keep_intervals debe quedar vacío.
    # El runner debe detectar esto y lanzar error (no swallowed).
    duration = 10.0
    cuts = [(0.0, 10.0)]
    keep = _invert_intervals(cuts, duration)
    assert keep == []


# ---------------------------------------------------------------------------
# _filter_cuts_outside_words — no cortar voz aunque el detector dé falso
# positivo (caso: "ejem" que Whisper SÍ transcribió, no podemos cortar ahí)
# ---------------------------------------------------------------------------
class TestFilterCutsOutsideWords:
    def test_no_words_returns_cuts_unchanged(self):
        cuts = [(0.0, 1.0), (3.0, 4.0)]
        # Sin transcript: no podemos verificar → conservar como vinieron
        assert _filter_cuts_outside_words(cuts, words=[]) == cuts

    def test_cut_entirely_outside_words_kept(self):
        # Cut en [5.0, 6.0]; palabras están en [0,1] y [7,8] → fuera → keep
        words = [_w(0, 0.0, 1.0), _w(1, 7.0, 8.0)]
        cuts = [(5.0, 6.0)]
        assert _filter_cuts_outside_words(cuts, words=words, pad_s=0.0) == cuts

    def test_cut_overlapping_word_dropped(self):
        # Cut [0.5, 1.5] solapa con palabra [0, 1] → eliminar para no
        # comer audio audible.
        words = [_w(0, 0.0, 1.0)]
        cuts = [(0.5, 1.5)]
        assert _filter_cuts_outside_words(cuts, words=words, pad_s=0.0) == []

    def test_safety_pad_prevents_eating_word_edges(self):
        # Cut [1.05, 2.0] técnicamente NO solapa con palabra [0, 1.0],
        # pero con pad_s=0.1 sí (la palabra "ocupa" [0.0, 1.1]) → drop.
        words = [_w(0, 0.0, 1.0)]
        cuts = [(1.05, 2.0)]
        assert _filter_cuts_outside_words(cuts, words=words, pad_s=0.1) == []

    def test_multiple_cuts_partially_filtered(self):
        words = [_w(0, 5.0, 6.0)]
        cuts = [
            (0.0, 1.0),       # fuera → keep
            (5.5, 7.0),       # solapa [5,6] → drop
            (10.0, 11.0),     # fuera → keep
        ]
        result = _filter_cuts_outside_words(cuts, words=words, pad_s=0.0)
        assert result == [(0.0, 1.0), (10.0, 11.0)]


# ---------------------------------------------------------------------------
# _detect_repeated_ngrams — heurística determinística (sin IA) que detecta
# n-gramas consecutivos repetidos en el transcript. Cubre el caso real
# donde GPT-4o devolvió "Clean transcript" pero había repeticiones obvias.
# ---------------------------------------------------------------------------
class TestDetectRepeatedNgrams:
    def test_empty(self):
        assert _detect_repeated_ngrams([]) == []

    def test_no_repetition(self):
        words = [_w(i, i * 0.5, i * 0.5 + 0.4) for i in range(8)]
        for i, w in enumerate(words):
            w["word"] = ["hola", "que", "tal", "estás", "yo", "bien", "y", "tú"][i]
        assert _detect_repeated_ngrams(words) == []

    def test_2gram_repetition(self):
        # "esto costaba esto costaba doce euros" → detecta "esto costaba" [0-1]
        # como repetido en [2-3]. Mantiene el segundo.
        words = [
            {"idx": 0, "word": "esto",    "start": 0.0, "end": 0.3},
            {"idx": 1, "word": "costaba", "start": 0.3, "end": 0.7},
            {"idx": 2, "word": "esto",    "start": 0.9, "end": 1.2},
            {"idx": 3, "word": "costaba", "start": 1.2, "end": 1.6},
            {"idx": 4, "word": "doce",    "start": 1.7, "end": 2.0},
            {"idx": 5, "word": "euros",   "start": 2.0, "end": 2.4},
        ]
        cuts = _detect_repeated_ngrams(words, min_n=2, max_n=6)
        assert len(cuts) == 1
        assert cuts[0]["start_word_idx"] == 0
        assert cuts[0]["end_word_idx"] == 1
        assert cuts[0]["first_attempt"] == "esto costaba"
        assert cuts[0]["kept_version"] == "esto costaba"
        assert cuts[0]["kind"] == "exact_ngram_repetition"

    def test_3gram_preferred_over_2gram(self):
        # "el casco salva el casco salva vidas" → debe detectar "el casco
        # salva" (3-grama) como repetido, no solo "el casco" (2-grama).
        # Preferimos el mayor n-grama posible.
        words = [
            {"idx": 0, "word": "el",     "start": 0.0, "end": 0.2},
            {"idx": 1, "word": "casco",  "start": 0.2, "end": 0.5},
            {"idx": 2, "word": "salva",  "start": 0.5, "end": 0.9},
            {"idx": 3, "word": "el",     "start": 1.0, "end": 1.2},
            {"idx": 4, "word": "casco",  "start": 1.2, "end": 1.5},
            {"idx": 5, "word": "salva",  "start": 1.5, "end": 1.9},
            {"idx": 6, "word": "vidas",  "start": 2.0, "end": 2.4},
        ]
        cuts = _detect_repeated_ngrams(words, min_n=2, max_n=6)
        assert len(cuts) == 1
        assert cuts[0]["end_word_idx"] - cuts[0]["start_word_idx"] + 1 == 3
        assert cuts[0]["first_attempt"] == "el casco salva"

    def test_case_and_punctuation_insensitive(self):
        # "Esto, costaba esto costaba euros" → comilla y mayúsculas no
        # impiden la detección
        words = [
            {"idx": 0, "word": "Esto,",   "start": 0.0, "end": 0.3},
            {"idx": 1, "word": "costaba", "start": 0.3, "end": 0.7},
            {"idx": 2, "word": "esto",    "start": 0.9, "end": 1.2},
            {"idx": 3, "word": "costaba", "start": 1.2, "end": 1.6},
            {"idx": 4, "word": "euros",   "start": 1.7, "end": 2.0},
        ]
        cuts = _detect_repeated_ngrams(words)
        assert len(cuts) == 1

    def test_long_gap_skips_detection(self):
        # "ojo" [pausa larga 2s] ... "ojo" — NO es repetición sino mención
        # legítima de la misma palabra en otra frase.
        words = [
            {"idx": 0, "word": "ojo",  "start": 0.0, "end": 0.3},
            {"idx": 1, "word": "mira", "start": 0.3, "end": 0.6},
            {"idx": 2, "word": "ojo",  "start": 2.8, "end": 3.0},
            {"idx": 3, "word": "mira", "start": 3.0, "end": 3.3},
        ]
        # gap entre "mira" (0.6) y "ojo" (2.8) = 2.2s >> 0.6s threshold
        cuts = _detect_repeated_ngrams(
            words, max_gap_between_grams_s=0.6,
        )
        assert cuts == []

    def test_user_real_failure_scenario(self):
        """Caso del usuario: GPT-4o devolvió 'Clean transcript' pero había
        repetición evidente antes de 'esto costaba 12 euros'.
        """
        # Simulación del transcript con repetición
        words = [
            {"idx": 0, "word": "antes",    "start": 0.0, "end": 0.3},
            {"idx": 1, "word": "esto",     "start": 0.4, "end": 0.6},
            {"idx": 2, "word": "costaba",  "start": 0.6, "end": 1.0},
            {"idx": 3, "word": "esto",     "start": 1.1, "end": 1.3},
            {"idx": 4, "word": "costaba",  "start": 1.3, "end": 1.7},
            {"idx": 5, "word": "doce",     "start": 1.8, "end": 2.0},
            {"idx": 6, "word": "euros",    "start": 2.0, "end": 2.5},
        ]
        cuts = _detect_repeated_ngrams(words)
        assert len(cuts) >= 1
        # Detectó "esto costaba" como repetido — esto es el fix concreto al
        # bug reportado donde el LLM falló pero la heurística no.
        cut = cuts[0]
        assert "esto costaba" in cut["first_attempt"].lower()

    def test_overlap_not_detected_twice(self):
        # "a b a b a b" → puede detectar tanto [0-1]=[2-3] como [2-3]=[4-5].
        # El algoritmo "consume" las palabras → solo el primer match.
        words = [
            {"idx": 0, "word": "a", "start": 0.0, "end": 0.2},
            {"idx": 1, "word": "b", "start": 0.2, "end": 0.4},
            {"idx": 2, "word": "a", "start": 0.5, "end": 0.7},
            {"idx": 3, "word": "b", "start": 0.7, "end": 0.9},
            {"idx": 4, "word": "a", "start": 1.0, "end": 1.2},
            {"idx": 5, "word": "b", "start": 1.2, "end": 1.4},
        ]
        cuts = _detect_repeated_ngrams(words, min_n=2, max_n=2)
        # Solo 1 cut, no se overlapan. Sería raro detectar 2 cuts solapados.
        assert len(cuts) == 1


# ---------------------------------------------------------------------------
# _split_silero_cuts_by_confidence — alta confianza pasa sin filtro
# ---------------------------------------------------------------------------
class TestSplitSileroCutsByConfidence:
    def test_empty(self):
        high, normal = _split_silero_cuts_by_confidence([])
        assert high == [] and normal == []

    def test_all_short(self):
        # Todos < 0.8s → todos normal
        cuts = [(0.0, 0.5), (1.0, 1.6), (2.0, 2.7)]
        high, normal = _split_silero_cuts_by_confidence(
            cuts, high_confidence_threshold_s=0.8,
        )
        assert high == []
        assert normal == cuts

    def test_all_long(self):
        # Todos ≥ 0.8s → todos high
        cuts = [(0.0, 1.0), (2.0, 4.0)]
        high, normal = _split_silero_cuts_by_confidence(
            cuts, high_confidence_threshold_s=0.8,
        )
        assert high == cuts
        assert normal == []

    def test_mixed(self):
        # El caso real del diagnostico: silencio [48.4, 49.4] = 1.0s
        # → alta confianza, NO debe pasar por filtro de palabras
        cuts = [(26.6, 27.1), (48.4, 49.4), (29.2, 30.8)]
        high, normal = _split_silero_cuts_by_confidence(
            cuts, high_confidence_threshold_s=0.8,
        )
        assert (48.4, 49.4) in high  # 1.0s → high
        assert (29.2, 30.8) in high  # 1.6s → high
        assert (26.6, 27.1) in normal  # 0.5s → normal


# ---------------------------------------------------------------------------
# _filter_phantom_words: nueva regla overlap > 50% (extiende fixture original)
# ---------------------------------------------------------------------------
class TestFilterPhantomWordsOverlap:
    def test_partial_overlap_majority_detected(self):
        # Caso real: palabra Whisper [48.3, 48.95], silencio Silero [48.4, 49.4]
        # Overlap = min(48.95, 49.4) - max(48.3, 48.4) = 48.95 - 48.4 = 0.55s
        # Dur palabra = 0.65s → overlap_pct = 0.55/0.65 = 84% → fantasma
        words = [{"idx": 75, "word": "y", "start": 48.3, "end": 48.95}]
        silero_silences = [(48.4, 49.4)]
        _, phantoms = _filter_phantom_words(
            words, silero_silences,
            min_silence_for_phantom_s=0.7, min_overlap_pct=0.6,
        )
        assert len(phantoms) == 1
        assert phantoms[0]["idx"] == 75

    def test_partial_overlap_minority_kept(self):
        # Palabra [48.0, 48.7] solo solapa 0.3s con silencio [48.4, 49.4]
        # Dur palabra = 0.7s → overlap_pct = 0.3/0.7 = 43% → NO fantasma
        words = [{"idx": 75, "word": "real", "start": 48.0, "end": 48.7}]
        silero_silences = [(48.4, 49.4)]
        _, phantoms = _filter_phantom_words(
            words, silero_silences,
            min_silence_for_phantom_s=0.7, min_overlap_pct=0.6,
        )
        assert phantoms == []  # No es fantasma — la palabra es mayoritariamente fuera

    def test_overlap_threshold_configurable(self):
        # Misma palabra, threshold más permisivo (30%) → marcada fantasma
        words = [{"idx": 75, "word": "real", "start": 48.0, "end": 48.7}]
        silero_silences = [(48.4, 49.4)]
        _, phantoms = _filter_phantom_words(
            words, silero_silences,
            min_silence_for_phantom_s=0.7, min_overlap_pct=0.3,
        )
        assert len(phantoms) == 1


# ---------------------------------------------------------------------------
# _filter_phantom_words — detecta alucinaciones de Whisper dentro de
# silencios reales detectados por Silero. CRÍTICO: sin esto, las palabras
# fantasma "protegen" silencios reales y los cuts acústicos no se aplican.
# Reproduce los 3 fallos del diagnóstico real (job 9cae8cba).
# ---------------------------------------------------------------------------
class TestFilterPhantomWords:
    def test_no_silero_intervals_returns_all_words(self):
        words = [_w(0, 0.0, 0.5), _w(1, 1.0, 1.5)]
        clean, phantoms = _filter_phantom_words(words, [])
        assert clean == words
        assert phantoms == []

    def test_short_silero_silences_dont_trigger(self):
        # Silero detecta silencio corto (<0.7s por defecto) → no marca fantasmas
        # aunque haya palabras dentro
        words = [_w(0, 1.0, 1.2)]
        silero_silences = [(0.9, 1.4)]  # 0.5s < threshold 0.7s
        clean, phantoms = _filter_phantom_words(
            words, silero_silences, min_silence_for_phantom_s=0.7,
        )
        assert phantoms == []
        assert clean == words

    def test_word_inside_long_silence_is_phantom(self):
        # Palabra "fantasma" Whisper completamente dentro de silencio Silero ≥0.7s
        words = [_w(0, 0.0, 0.3), _w(1, 1.0, 1.2), _w(2, 3.0, 3.2)]
        silero_silences = [(0.5, 2.5)]  # 2s, contiene la palabra idx=1
        clean, phantoms = _filter_phantom_words(
            words, silero_silences, min_silence_for_phantom_s=0.7,
        )
        assert len(phantoms) == 1
        assert phantoms[0]["idx"] == 1
        assert len(clean) == 2
        assert [w["idx"] for w in clean] == [0, 2]

    def test_short_word_midpoint_in_silence_is_phantom(self):
        # Palabra cuyo MIDPOINT cae dentro del silencio + es corta (<0.6s)
        # también se considera fantasma (aunque borde sobresalga ligeramente).
        words = [_w(0, 1.0, 1.3)]  # mid=1.15, dur=0.3
        silero_silences = [(0.9, 1.8)]  # 0.9s, mid 1.15 dentro
        _, phantoms = _filter_phantom_words(
            words, silero_silences, min_silence_for_phantom_s=0.7,
        )
        assert len(phantoms) == 1

    def test_long_word_in_silence_not_phantom(self):
        # Si la "palabra" dura >0.6s y no cabe entera dentro, NO es fantasma
        # — probablemente Silero falló (palabra real con audio bajo)
        words = [_w(0, 1.0, 2.0)]  # dur=1.0s
        silero_silences = [(0.9, 1.5)]  # 0.6s, contiene mid pero word es larga
        _, phantoms = _filter_phantom_words(
            words, silero_silences, min_silence_for_phantom_s=0.5,
        )
        # midpoint=1.5 está en el borde, no estrictamente dentro;
        # y dur>0.6 → no se marca fantasma
        assert len(phantoms) == 0

    def test_real_diagnostic_scenario_fallo_1(self):
        """Reproduce el FALLO 1 del diagnóstico real (job 9cae8cba):
        - 'momento' (idx 74, end 48.0)
        - <fantasma idx 75 entre medias>
        - 'lo' (idx 76, start 49.56)
        - Silero detectó silencio [48.4, 49.4] = 1.0s
        - User espera que el silencio se corte.
        """
        words = [
            _w(74, 47.6, 48.0),    # "momento"
            _w(75, 48.7, 48.95),   # FANTASMA Whisper alucinó algo aquí
            _w(76, 49.56, 49.68),  # "lo"
        ]
        silero_silences = [(48.4, 49.4)]  # 1.0s silencio real
        clean, phantoms = _filter_phantom_words(
            words, silero_silences, min_silence_for_phantom_s=0.7,
        )
        # La palabra idx=75 cuyo mid=48.825 cae dentro de [48.4, 49.4]
        # y dur=0.25<0.6 → se marca como fantasma
        assert len(phantoms) == 1
        assert phantoms[0]["idx"] == 75
        # clean_words tiene solo las reales → IWG ahora ve gap entre
        # 'momento' (48.0) y 'lo' (49.56) = 1.56s → cortará ese silencio.
        assert len(clean) == 2

    def test_real_diagnostic_scenario_fallo_2(self):
        """Reproduce el FALLO 2: 'cesta amarilla y' [pausa] 'date prisa'.
        - 'y' (idx 137, end 75.19)
        - 'date' (idx 138) tiene timestamp impreciso ~76.5 cuando se dice
          realmente en 78s — Whisper se equivocó
        - 'prisa' (idx 139, start 78.09)
        - Silero detectó silencio [76.5, 78.0] como gap entre 'date' real y 'prisa'
        """
        words = [
            _w(137, 74.71, 75.19),   # "y"
            _w(138, 76.0, 76.4),     # "date" — fantasma o timing impreciso
            _w(139, 78.09, 78.59),   # "prisa"
        ]
        # Silero sí detectó el silencio audible
        silero_silences = [(76.5, 78.0)]
        _, phantoms = _filter_phantom_words(
            words, silero_silences, min_silence_for_phantom_s=0.7,
        )
        # La "palabra" idx=138 cuyo end=76.4 está fuera de [76.5, 78.0] →
        # NO se marca fantasma. Este es un caso límite — Silero no la cubre
        # del todo, así que el filtro NO la elimina (correcto).
        # Para este caso debemos confiar en el cut acústico con pad bajo.
        assert 138 not in [p["idx"] for p in phantoms]


# ---------------------------------------------------------------------------
# _trim_cuts_to_avoid_words — recorta cuts en vez de descartarlos cuando
# rozan palabras. Antes perdíamos 65% de cuts válidos por rozar bordes.
# ---------------------------------------------------------------------------
class TestTrimCutsToAvoidWords:
    def test_no_words_returns_cuts_unchanged(self):
        cuts = [(0.0, 1.0), (3.0, 4.0)]
        assert _trim_cuts_to_avoid_words(cuts, words=[]) == cuts

    def test_cut_entirely_outside_kept(self):
        # Cut [5, 6] está fuera de palabras [0,1] y [7,8]
        words = [_w(0, 0.0, 1.0), _w(1, 7.0, 8.0)]
        assert _trim_cuts_to_avoid_words(
            [(5.0, 6.0)], words=words, pad_s=0.0,
        ) == [(5.0, 6.0)]

    def test_cut_with_word_inside_splits(self):
        # Cut [0.5, 3.0] contiene palabra [1.0, 2.0] → split en
        # [0.5, 1.0] y [2.0, 3.0]
        words = [_w(0, 1.0, 2.0)]
        result = _trim_cuts_to_avoid_words(
            [(0.5, 3.0)], words=words, pad_s=0.0, min_remaining_s=0.1,
        )
        assert result == [(0.5, 1.0), (2.0, 3.0)]

    def test_cut_with_word_at_start_trimmed(self):
        # Cut [0.5, 3.0]; palabra [0.0, 1.0] → la parte solapada se quita
        # y el cut queda [1.0, 3.0]
        words = [_w(0, 0.0, 1.0)]
        result = _trim_cuts_to_avoid_words(
            [(0.5, 3.0)], words=words, pad_s=0.0, min_remaining_s=0.1,
        )
        assert result == [(1.0, 3.0)]

    def test_cut_with_word_at_end_trimmed(self):
        # Cut [0.0, 2.5]; palabra [2.0, 3.0] → cut queda [0.0, 2.0]
        words = [_w(0, 2.0, 3.0)]
        result = _trim_cuts_to_avoid_words(
            [(0.0, 2.5)], words=words, pad_s=0.0, min_remaining_s=0.1,
        )
        assert result == [(0.0, 2.0)]

    def test_remaining_below_threshold_dropped(self):
        # Cut [0.95, 3.0]; palabra [1.0, 2.0] → split en
        # [0.95, 1.0] (0.05s, <0.15) y [2.0, 3.0] (1.0s, keep)
        # El primero se descarta por ser < min_remaining_s
        words = [_w(0, 1.0, 2.0)]
        result = _trim_cuts_to_avoid_words(
            [(0.95, 3.0)], words=words, pad_s=0.0, min_remaining_s=0.15,
        )
        assert result == [(2.0, 3.0)]

    def test_safety_pad_applied(self):
        # Palabra [1.0, 2.0] con pad 0.1 → "ocupa" [0.9, 2.1]
        # Cut [0.0, 1.5] solapa con la versión padded → trim a [0.0, 0.9]
        words = [_w(0, 1.0, 2.0)]
        result = _trim_cuts_to_avoid_words(
            [(0.0, 1.5)], words=words, pad_s=0.1, min_remaining_s=0.1,
        )
        assert result == [(0.0, 0.9)]

    def test_diagnostic_scenario_amplitude_cuts_preserved(self):
        """Reproducción del bug real visto en producción.

        Amplitude detectó 23 silencios, el filtro antiguo solo dejó 8 porque
        muchos rozaban bordes de palabras. Con `_trim_cuts_to_avoid_words`
        esos cuts SIGUEN existiendo (recortados, pero presentes), cortando
        las pausas de 2s que antes se quedaban en el vídeo final.
        """
        # Simulación: 3 silencios reales entre pares de palabras consecutivas
        words = [
            _w(0, 0.0, 0.5),
            _w(1, 2.5, 3.0),    # gap [0.5, 2.5] = 2s real silence
            _w(2, 5.0, 5.5),    # gap [3.0, 5.0] = 2s real silence
            _w(3, 8.0, 8.5),    # gap [5.5, 8.0] = 2.5s real silence
        ]
        # Amplitude detecta los gaps con bordes "tocando" las palabras
        amp_cuts = [
            (0.45, 2.55),   # roza ambas palabras
            (2.95, 5.05),   # roza ambas palabras
            (5.45, 8.05),   # roza ambas palabras
        ]
        # Con filter antiguo → todos descartados (overlap).
        old_result = _filter_cuts_outside_words(
            amp_cuts, words=words, pad_s=0.05,
        )
        assert len(old_result) == 0  # confirma el bug

        # Con trim → todos recortados pero conservados
        new_result = _trim_cuts_to_avoid_words(
            amp_cuts, words=words, pad_s=0.05, min_remaining_s=0.5,
        )
        # 3 cuts, cada uno con duración aprox 2s entre las palabras
        assert len(new_result) == 3
        # Suma de duraciones ≈ 6s (vs 0s con el filtro antiguo)
        total = sum(e - s for s, e in new_result)
        assert total > 5.0


# ---------------------------------------------------------------------------
# _count_by_source — agrupador trivial usado en el diagnóstico
# ---------------------------------------------------------------------------
class TestCountBySource:
    def test_empty(self):
        assert _count_by_source([]) == {}

    def test_groups_correctly(self):
        cuts = [
            (0.0, 1.0, "auto_trim"),
            (5.0, 6.0, "ai"),
            (8.0, 9.0, "acoustic"),
            (10.0, 11.0, "ai"),
            (12.0, 13.0, "auto_trim"),
        ]
        assert _count_by_source(cuts) == {
            "auto_trim": 2, "ai": 2, "acoustic": 1,
        }


# ---------------------------------------------------------------------------
# _compute_inter_word_gap_cuts — la capa CRÍTICA del caso "1-2s entre frases".
# Determinística (no IA), basada solo en word_timings de Whisper.
# ---------------------------------------------------------------------------
class TestInterWordGapCuts:
    def test_empty_words(self):
        assert _compute_inter_word_gap_cuts(
            [], threshold_s=0.6, keep_ms=200,
        ) == []

    def test_no_gaps_above_threshold(self):
        # Todas las palabras consecutivas con gap 0.1s
        words = [_w(i, i * 1.0, i * 1.0 + 0.9) for i in range(5)]
        assert _compute_inter_word_gap_cuts(
            words, threshold_s=0.6, keep_ms=200,
        ) == []

    def test_single_long_gap(self):
        # Palabra 0 termina en 1.0, palabra 1 empieza en 3.0 → gap 2.0s
        words = [_w(0, 0.0, 1.0), _w(1, 3.0, 3.5)]
        cuts = _compute_inter_word_gap_cuts(
            words, threshold_s=0.6, keep_ms=200,
        )
        assert len(cuts) == 1
        # keep_ms=200 = 0.2s repartido (0.1 cada lado)
        # cut_start = 1.0 + 0.1 = 1.1, cut_end = 3.0 - 0.1 = 2.9
        assert cuts[0]["t_start"] == 1.1
        assert cuts[0]["t_end"] == 2.9
        assert cuts[0]["gap_s"] == 2.0
        assert cuts[0]["after_word_idx"] == 0
        assert cuts[0]["before_word_idx"] == 1

    def test_multiple_gaps_real_scenario(self):
        # Vídeo de motivación: "ojo, esto es importante" [pausa 1.5s]
        # "el casco salva vidas" [pausa 2.2s] "y siempre, siempre" [pausa 0.4s no se corta]
        # "úsalo"
        words = [
            _w(0, 0.0, 0.5),   # "ojo"
            _w(1, 0.6, 1.0),   # "esto"
            _w(2, 1.1, 1.4),   # "es"
            _w(3, 1.5, 2.3),   # "importante"        ← gap 1.5s
            _w(4, 3.8, 4.0),   # "el"
            _w(5, 4.1, 4.5),   # "casco"
            _w(6, 4.6, 5.0),   # "salva"
            _w(7, 5.1, 5.5),   # "vidas"             ← gap 2.2s
            _w(8, 7.7, 8.0),   # "y"
            _w(9, 8.1, 8.6),   # "siempre"
            _w(10, 8.7, 9.2),  # "siempre"           ← gap 0.4s (NO se corta)
            _w(11, 9.6, 9.9),  # "úsalo"
        ]
        cuts = _compute_inter_word_gap_cuts(
            words, threshold_s=0.6, keep_ms=200,
        )
        # Esperamos 2 cuts (los gaps de 1.5s y 2.2s). El de 0.4s queda.
        assert len(cuts) == 2
        assert cuts[0]["gap_s"] == 1.5
        assert cuts[0]["after_word_idx"] == 3   # "importante"
        assert cuts[0]["before_word_idx"] == 4  # "el"
        assert cuts[1]["gap_s"] == 2.2
        assert cuts[1]["after_word_idx"] == 7   # "vidas"
        assert cuts[1]["before_word_idx"] == 8  # "y"

    def test_keep_ms_respected(self):
        # Con keep_ms=0 → corta TODO el gap entero
        words = [_w(0, 0.0, 1.0), _w(1, 3.0, 4.0)]
        cuts = _compute_inter_word_gap_cuts(
            words, threshold_s=0.6, keep_ms=0,
        )
        assert cuts[0]["t_start"] == 1.0
        assert cuts[0]["t_end"] == 3.0

    def test_keep_ms_larger_than_gap_skips(self):
        # gap es 0.7s pero keep_ms=1500 (1.5s) → no queda nada que cortar
        words = [_w(0, 0.0, 1.0), _w(1, 1.7, 2.0)]
        cuts = _compute_inter_word_gap_cuts(
            words, threshold_s=0.6, keep_ms=1500,
        )
        assert cuts == []

    def test_threshold_zero_disabled(self):
        # threshold_s=0 → función debe devolver vacío (caso "off")
        words = [_w(0, 0.0, 1.0), _w(1, 5.0, 6.0)]
        assert _compute_inter_word_gap_cuts(
            words, threshold_s=0.0, keep_ms=200,
        ) == []


# ---------------------------------------------------------------------------
# _verdict_for_score — texto humano del quality score
# ---------------------------------------------------------------------------
class TestVerdictForScore:
    def test_excellent(self):
        assert "EXCELENTE" in _verdict_for_score(100)
        assert "EXCELENTE" in _verdict_for_score(95)

    def test_good(self):
        assert "BIEN" in _verdict_for_score(80)
        assert "BIEN" in _verdict_for_score(70)

    def test_regular(self):
        assert "REGULAR" in _verdict_for_score(50)
        assert "REGULAR" in _verdict_for_score(60)

    def test_bad(self):
        assert "MAL" in _verdict_for_score(0)
        assert "MAL" in _verdict_for_score(30)


# ---------------------------------------------------------------------------
# _count_by_reason — agrupador por `reason` del JSON del LLM
# ---------------------------------------------------------------------------
class TestCountByReason:
    def test_empty(self):
        assert _count_by_reason([]) == {}

    def test_groups_by_reason(self):
        raw = [
            {"reason": "head_silence"},
            {"reason": "false_start"},
            {"reason": "false_start"},
            {"reason": "noise_gap"},
            {},  # sin reason → "unknown"
        ]
        assert _count_by_reason(raw) == {
            "head_silence": 1, "false_start": 2,
            "noise_gap": 1, "unknown": 1,
        }
