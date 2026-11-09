"""mano.detectar() manda sus lecturas a Haiku (tarea "guion"), no a Sonnet.

Con fotos y sin `tarea`, el cliente Claude pasa solo a "lectura" (Sonnet).
El A/B del 9/11/2026 dio el mismo sexo con Haiku: cada llamada debe llevar
la tarea explícita o el gasto vuelve a Sonnet sin que nadie lo note.
"""
from pathlib import Path

from src.nicho_pov_bof.services import mano
from src.tiktok_shop.api import claude


def test_las_tres_llamadas_van_a_haiku(monkeypatch, tmp_path):
    tareas: list[str] = []
    respuestas = iter([
        {"fotogramas": []},  # 1ª tanda: sin mano → reintento
        {"fotogramas": [{"hay_mano": True, "hombre": True, "senal": "vello"},
                        {"hay_mano": True, "hombre": True}]},  # sospecha → confirmar
        {"fotogramas": [{"hay_mano": True, "hombre": False}]},
    ])

    def falso(system, user, *, tarea="texto", images=None, **kw):
        tareas.append(tarea)
        return next(respuestas)

    monkeypatch.setattr(claude, "generate_json", falso)
    monkeypatch.setattr(mano, "_fotogramas_de", lambda *a, **k: ["f.jpg"])
    monkeypatch.setattr(mano, "_rotundo", lambda lecturas: False)

    mano.detectar(Path(tmp_path / "v.mp4"))

    assert tareas == ["guion", "guion", "guion"]
    assert claude.MODELOS[mano.TAREA_CLAUDE] == "claude-haiku-5-5"
