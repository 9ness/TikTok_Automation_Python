"""_protect_unique_content: no re-anexar un arranque abandonado que se repite justo después."""
from src.editor_auto.tools.silence_cutter import _protect_unique_content


def _w(txt):
    return [{"word": t, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, t in enumerate(txt.split())]


def test_retoma_no_se_reanexa():
    w = _w("chicas cómo son estos shorts pantaloncitos así chicas cómo son estos pantaloncitos cortos así con caída")
    keep = set(range(7, len(w)))  # el holístico quitó la primera toma
    sug = []
    k2, n = _protect_unique_content(w, keep, sug)
    assert n == 0 and k2 == keep and sug == []


def test_contenido_unico_si_se_reanexa_y_se_sugiere():
    w = _w("hola los dos ingredientes son proteína y crema de arroz y ya está mezclado")
    keep = set(range(0, 2)) | set(range(10, len(w)))
    sug = []
    k2, n = _protect_unique_content(w, keep, sug)
    assert n == 1 and set(range(2, 10)) <= k2
    assert len(sug) == 1 and "proteína" in sug[0]["text"]


def test_sugeridos_vigentes_quita_lo_ya_cortado():
    from src.editor_auto.tools.silence_cutter import _sugeridos_vigentes
    sug = [
        {"start": 75.0, "end": 76.7, "text": "ya cortado", "motivo": "barrido"},
        {"start": 4.2, "end": 5.6, "text": "sigue", "motivo": "barrido"},
    ]
    keeps = [(3.4, 5.7), (69.9, 75.2), (76.8, 77.8)]
    assert [s["text"] for s in _sugeridos_vigentes(sug, keeps)] == ["sigue"]
