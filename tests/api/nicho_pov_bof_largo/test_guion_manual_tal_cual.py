"""El guion escrito a mano (`guardar_guion`) se locuta TAL CUAL.

GMV Max Viva 15/11/2026: siete vídeos salieron con «cómodos plazos» o «envío
gratis» en el cierre aunque el operador los había quitado del texto. El
encaje de la voz cambiaba el cierre por la escalera de CTAs del producto.
"""

from __future__ import annotations

import pytest

TEXTO = "Mira qué invento. Lo tienes en el carrito naranja."


class _Corta(Exception):
    pass


def _job(params):
    class Job:
        id = "j1"
        enqueued_by = "ness"

    j = Job()
    j.params = params
    return j


def _montar(monkeypatch, tmp_path, guardado):
    from src.nicho_pov_bof_largo.repos import product_repo
    from src.nicho_pov_bof_largo.services import guionista, voz as voz_svc
    from src.queue import runners

    clips = []
    for n in (1, 2):
        c = tmp_path / f"c{n}.mp4"
        c.write_bytes(b"x")
        clips.append(c)
    monkeypatch.setattr(product_repo, "textos_producto", lambda *a, **k: {
        "titulo": "Bici", "precio": "600", "plazos": True, "envio_gratis": True,
    })
    monkeypatch.setattr(product_repo, "get_product", lambda *a, **k: dict(guardado))
    monkeypatch.setattr(product_repo, "update_product", lambda *a, **k: None)
    monkeypatch.setattr(runners, "_es_plazos", lambda t: True)
    monkeypatch.setattr(runners, "_segundos_de_video", lambda *a, **k: 16.0)
    monkeypatch.setattr(
        guionista, "escribir",
        lambda **k: pytest.fail("no debe reescribir un guion manual"),
    )
    visto = {}

    def sintetizar(texto, audio, **k):
        visto["texto"], visto["ctas"] = texto, k.get("ctas")
        raise _Corta

    monkeypatch.setattr(voz_svc, "sintetizar", sintetizar)
    with pytest.raises(_Corta):
        runners.run_nicho_pov_bof_largo_video(
            _job({
                "source": "mis_productos", "folder": "C1", "producto": "3",
                "clip1_path": str(clips[0]), "clip2_path": str(clips[1]),
                "sexo": "mujer",
            }),
            lambda *a, **k: None, lambda *a, **k: None,
        )
    return visto


def test_manual_sin_encaje_ni_reescritura(monkeypatch, tmp_path):
    # guion_plazos=False con producto de plazos: antes se reescribía con Gemini.
    visto = _montar(monkeypatch, tmp_path, {
        "guion": TEXTO, "guion_manual": True, "guion_plazos": False,
    })
    assert visto["texto"] == TEXTO
    assert not visto["ctas"]


def test_no_manual_sigue_con_el_encaje(monkeypatch, tmp_path):
    visto = _montar(monkeypatch, tmp_path, {
        "guion": TEXTO, "guion_plazos": True,
    })
    assert visto["ctas"]


def test_el_lote_no_corrige_la_cta_de_un_manual(monkeypatch):
    from src.nicho_pov_bof import config as pov_config
    from src.nicho_pov_bof.repos import product_repo as pov_repo
    from src.nicho_pov_bof_largo import config as largo_config
    from src.nicho_pov_bof_largo.repos import product_repo
    from src.queue import runners

    monkeypatch.setattr(pov_repo, "load_folder_para", lambda *a, **k: {
        "productos": {"3": {"titulo": "Bici"}, "4": {"titulo": "Otra"}},
    })
    guion_plazos = "Mira. " + largo_config.CTA_PLAZOS
    monkeypatch.setattr(product_repo, "load_folder", lambda *a, **k: {"productos": {
        "3": {"guion": guion_plazos, "guion_manual": True},
        "4": {"guion": guion_plazos},
    }})
    monkeypatch.setattr(pov_config, "hay_plazos", lambda t: False)
    monkeypatch.setattr(largo_config, "hay_envio_gratis", lambda t: False)
    salen = [
        pid for _, pid, _, _ in runners._con_guion_desfasado(
            "mis_productos", ["C1"], "ness", product_repo, pov_config, largo_config,
        )
    ]
    assert "3" not in salen
    assert "4" in salen
