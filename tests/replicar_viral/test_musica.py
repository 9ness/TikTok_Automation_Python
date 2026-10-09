from src.replicar_viral import musica


def test_de_tikwm_saca_cancion_y_enlace():
    d = {"music_info": {"id": "7674053498023200778", "title": "Saltwater Aperture",
                        "author": "Marla Hinkley", "original": False}}
    r = musica.de_tikwm(d)
    assert r["titulo"] == "Saltwater Aperture" and r["autor"] == "Marla Hinkley"
    assert r["enlace"] == "https://www.tiktok.com/music/saltwater-aperture-7674053498023200778"
    assert musica.de_tikwm({}) == {}


def test_completa_no_consulta_tikwm_si_ya_hay_cancion(monkeypatch):
    from src.replicar_viral import servicio

    monkeypatch.setattr(servicio, "consultar_tikwm", lambda *_: (_ for _ in ()).throw(AssertionError))
    tk = {"titulo": "x", "original": True, "id": "1", "enlace": "e"}
    r = musica.completa({"id": "abc", "musica": {"tiktok": tk}})
    assert r["tiktok"] == tk and isinstance(r["meta"], dict)
