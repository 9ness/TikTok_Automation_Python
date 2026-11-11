from src.editor_auto.tools.vip_overlays import VipOverlaysTool, _sanitize, _clean_text


def _cfg(**kw):
    c = VipOverlaysTool().default_config()
    c.update(kw)
    return c


def test_sanitize_quita_solapes_y_recorta():
    plan = {
        "gancho": {"texto": "si tocan tu moto...", "dato": "110 dB", "clip": {"t0": 50, "t1": 54}},
        "rotulos": [
            {"texto": "1 manillar", "t0": 10, "t1": 11.5, "rol": "dato"},
            {"texto": "2 disco", "t0": 10.3, "t1": 12, "rol": "dato"},   # pisa al anterior casi entero
            {"texto": "fuera", "t0": 70, "t1": 72, "rol": "alerta"},     # fuera del vídeo
            {"texto": "pronto", "t0": 1.0, "t1": 2.0, "rol": "ok"},      # dentro del gancho
            {"texto": "raro", "t0": 20, "t1": 21, "rol": "inventado"},
        ],
        "zooms": [{"t0": 5, "t1": 8, "nivel": 3}, {"t0": 7, "t1": 9, "nivel": 1.1}],
        "fotos": [{"busqueda": "moto calle", "t0": 30, "t1": 33}],
    }
    out = _sanitize(plan, 60.0, _cfg(fotos_internet=True))
    assert out["gancho"]["texto"] == "SI TOCAN TU MOTO..."
    assert out["gancho"]["clip"] == {"t0": 50.0, "t1": 53.0}  # máx 3 s
    textos = [r["texto"] for r in out["rotulos"]]
    assert textos == ["1 MANILLAR", "RARO"]
    assert out["rotulos"][1]["rol"] == "neutro"
    assert len(out["zooms"]) == 1 and out["zooms"][0]["nivel"] == 1.22
    assert out["fotos"][0]["busqueda"] == "moto calle"


def test_sanitize_respeta_estilo_apagado():
    plan = {"gancho": {"texto": "hola", "clip": {"t0": 10, "t1": 12}},
            "zooms": [{"t0": 1, "t1": 3}], "fotos": [{"busqueda": "x", "t0": 5, "t1": 7}]}
    out = _sanitize(plan, 30.0, _cfg(gancho=False, gancho_clip=False, zooms=False, fotos=False))
    assert out["gancho"] == {"texto": "", "dato": "", "clip": None, "foto": ""}
    assert out["zooms"] == [] and out["fotos"] == []


def test_zoom_nunca_mas_de_la_mitad():
    plan = {"zooms": [{"t0": i * 4.5, "t1": i * 4.5 + 4} for i in range(6)]}
    out = _sanitize(plan, 24.0, _cfg())
    assert sum(z["t1"] - z["t0"] for z in out["zooms"]) <= 12.0


def test_clean_text_sin_emojis():
    assert _clean_text("activada ✅🔥") == "ACTIVADA"
    assert _clean_text("menos de 20 €") == "MENOS DE 20 €"


def test_clean_text_respeta_decibelios():
    assert _clean_text("110 dB") == "110 dB"
    assert _clean_text("110db") == "110 dB"


class TestEstiloFlujo:
    """El estilo de la referencia también rellena subtítulos y flecha."""

    def test_subs(self):
        from src.editor_auto.services.estilo_vip import _subs_cfg
        cfg = _subs_cfg({"hay": True, "palabras": 3, "y_pct": 68, "color_texto": "#ffffff",
                         "resaltado": "color", "color_resaltado": "#ffd600", "mayusculas": True})
        assert cfg == {"highlight_mode": "color_swap", "text_color": "#FFFFFF",
                       "highlight_color": "#FFD600", "max_words": 3, "y_position": 0.68,
                       "case_mode": "UPPERCASE"}
        assert _subs_cfg({"hay": False}) == {}

    def test_flecha_triple_naranja(self, tmp_path, monkeypatch):
        from src.editor_auto.services import estilo_vip
        for n in ("flecha_roja.mov", "flecha_naranja.mov", "flecha_abajo_triple_naranja.mov",
                  "flecha_abajo_triple_roja.mov", "flecha_triple_naranja.mov"):
            (tmp_path / n).write_bytes(b"x")
        monkeypatch.setattr("src.editor_auto.tools.sticker_arrow.arrows_folder", lambda: str(tmp_path))
        cfg = estilo_vip._flecha_cfg({"hay": True, "color": "#F7931E", "triple": True,
                                      "x_pct": 50, "y_pct": 88})
        assert cfg == {"sticker_file": "flecha_abajo_triple_naranja.mov", "color_mode": "fixed",
                       "position_x_pct": 50.0, "position_y_pct": 88.0}
        sola = estilo_vip._flecha_cfg({"hay": True, "color": "#E02020", "triple": False})
        assert sola["sticker_file"] == "flecha_roja.mov"

    def test_texto_solo_cambia_lo_que_dice(self):
        from src.editor_auto.services.estilo_vip import _a_config
        cfg = _a_config({"zooms": False, "notas_estilo": "Sin zooms."}, {})
        assert cfg == {"zooms": False, "notas_estilo": "Sin zooms."}  # ni preset ni defectos
        cfg = _a_config({"color_dato": "#ffd600"}, {})
        assert cfg == {"color_dato": "#FFD600", "preset": "personalizado"}


def test_extras_compartido_por_defecto_vacio():
    from src.editor_auto.tools.base import ToolContext
    a = ToolContext(user_id="u", user_name="u", job_id="j", temp_folder="/tmp",
                    on_log=lambda m: None, on_progress=lambda *a: None)
    b = ToolContext(user_id="u", user_name="u", job_id="j", temp_folder="/tmp",
                    on_log=lambda m: None, on_progress=lambda *a: None)
    a.extras["x"] = 1
    assert b.extras == {}  # cada job empieza limpio; el orquestador pasa el suyo


class TestStock:
    def test_stock_colores_y_agotados(self):
        from src.editor_auto.tools.vip_overlays import _sanitize
        cfg = {"densidad_rotulos": "media", "fotos": False, "zooms": False, "gancho": False}
        plan = {"stock": {"t0": 40, "t1": 42.5, "quedan": ["rojo", "amarilla", "fucsia"],
                          "agotados": 2}}
        st = _sanitize(plan, 60.0, cfg)["stock"]
        assert st["quedan"] == ["#E53935", "#FDD835"] and st["agotados"] == 2
        plan["rotulos"] = [{"texto": "QUEDAN 2", "t0": 41, "t1": 43, "rol": "dato"},
                           {"texto": "SE AGOTA", "t0": 36, "t1": 38, "rol": "alerta"}]
        out = _sanitize(plan, 60.0, cfg)
        assert [r["texto"] for r in out["rotulos"]] == ["SE AGOTA"] and out["stock"]

    def test_sin_colores_no_hay_stock(self):
        from src.editor_auto.tools.vip_overlays import _sanitize
        cfg = {"densidad_rotulos": "media", "fotos": False, "zooms": False, "gancho": False}
        assert _sanitize({"stock": {"t0": 1, "t1": 3, "quedan": []}}, 60.0, cfg)["stock"] is None


def test_clip_por_sonido_no_corta_palabras():
    from src.editor_auto.tools.vip_overlays import _clip_por_sonido
    ev = [{"t0": 1.0, "t1": 1.6, "db_sobre_fondo": 40}, {"t0": 34.5, "t1": 35.4, "db_sobre_fondo": 30}]
    words = [{"start": 33.9, "end": 34.4}, {"start": 35.6, "end": 36.2}]
    assert _clip_por_sonido(ev, words) == {"t0": 33.9, "t1": 36.2}
    assert _clip_por_sonido(ev[:1], words) is None


def test_tono_elige_paleta_sin_colores():
    from src.editor_auto.services.estilo_vip import _a_config
    assert _a_config({"tono": "limpio", "notas_estilo": "x"}, {})["preset"] == "limpio"
    assert _a_config({"tono": "limpio", "color_dato": "#FFD600"}, {})["preset"] == "personalizado"


def test_pildora_clara_texto_oscuro():
    from src.subtitles import _claro
    assert _claro("#FFD600") and _claro((255, 255, 255)) and not _claro("#E61E2D")


def test_foto_del_gancho_solo_con_fotos():
    from src.editor_auto.tools.vip_overlays import _sanitize
    plan = {"gancho": {"texto": "¿TE GUSTA ELSA PATAKY?", "foto": "Elsa Pataky"}}
    cfg = {"densidad_rotulos": "media", "fotos": True, "zooms": False, "gancho": True,
           "fotos_internet": True, "max_fotos": 3}
    assert _sanitize(plan, 30.0, cfg)["gancho"]["foto"] == "Elsa Pataky"
    assert _sanitize(plan, 30.0, {**cfg, "fotos": False})["gancho"]["foto"] == ""


def test_sin_permiso_no_hay_fotos_de_internet():
    """Por defecto nada de internet: otras marcas = «producto incoherente», famosos = derechos."""
    plan = {"gancho": {"texto": "¿TE GUSTA ELSA PATAKY?", "foto": "Elsa Pataky"},
            "fotos": [{"busqueda": "colageno marino bote", "t0": 5, "t1": 8}]}
    out = _sanitize(plan, 30.0, _cfg())
    assert out["gancho"]["foto"] == "" and out["fotos"] == []


def test_frases_enteras_o_nada():
    assert _clean_text("enlace en el carrito naranja", 30, entera=True) == "ENLACE EN EL CARRITO NARANJA"
    assert _clean_text("enlace en el", 30, entera=True) == ""  # a medias
    assert _clean_text("¿a ti te gusta tanto el colágeno de Elsa Pataky?", 30, entera=True) == ""
    plan = {"rotulos": [{"texto": "enlace en el carrito naranja", "t0": 5, "t1": 7, "rol": "ok"}]}
    assert _sanitize(plan, 30.0, _cfg(gancho=False))["rotulos"][0]["texto"] == "ENLACE EN EL CARRITO NARANJA"


def test_pildora_larga_va_a_dos_lineas(tmp_path, monkeypatch):
    from PIL import Image
    from src.editor_auto.tools import vip_overlays as v
    partes = []
    orig = v._dos_lineas
    monkeypatch.setattr(v, "_dos_lineas", lambda t: partes.append(t) or orig(t))
    cfg = _cfg()
    v._pill("15 €/KG", (255, 214, 0, 255), 84, 930, cfg, str(tmp_path / "a.png"))
    assert partes == []
    p = v._pill("ESTO ES LO QUE NECESITAS PARA ENTRENAR", (255, 214, 0, 255), 84, 930, cfg,
                str(tmp_path / "b.png"))
    assert len(partes) == 1 and Image.open(p).size[0] <= 930 + 40


def test_rotulo_fuera_de_cara_y_subtitulos():
    from src.editor_auto.tools.vip_overlays import _y_libre
    H = 1920
    subs, cara = (int(0.55 * H), int(0.69 * H)), (int(0.10 * H), int(0.40 * H))
    y = _y_libre(180, int(0.16 * H), [subs, cara], H)
    for a, b in (subs, cara):
        assert y + 180 <= a or y >= b
    # sin sitio libre, antes la cara que los subtítulos
    y = _y_libre(900, int(0.16 * H), [subs, (0, H)], H)
    assert y + 900 <= subs[0] or y >= subs[1]


def test_borde_vip_en_subtitulos():
    from src.editor_auto.tools.subs_auto import _borde_contraste
    assert _borde_contraste("#FFD600") == "#000000"
    assert _borde_contraste("#111111") == "#FFFFFF"


def test_corregir_nombres_en_subs():
    from src.editor_auto.tools.subs_auto import _corregir_nombres
    w = [{"word": "tanto", "start": 0, "end": .3}, {"word": "el", "start": .3, "end": .4},
         {"word": "Sapataki,", "start": .4, "end": .9}, {"word": "como", "start": .9, "end": 1.1}]
    assert _corregir_nombres(w, [{"oido": "el sapataky", "bien": "Elsa Pataky"}]) == 1
    assert [x["word"] for x in w] == ["tanto", "Elsa", "Pataky,", "como"]
    w2 = [{"word": "de", "start": 0, "end": .2}, {"word": "in", "start": .2, "end": .3},
          {"word": "cite", "start": .3, "end": .6}]
    _corregir_nombres(w2, [{"oido": "in cite", "bien": "Incite"}])
    assert [x["word"] for x in w2] == ["de", "Incite"] and w2[1]["end"] == .6


def test_texto_no_se_corta_a_mitad_de_palabra():
    from src.editor_auto.tools.vip_overlays import _clean_text
    assert _clean_text("¿A ti te gusta Elsa Pataky?", 28) == "¿A TI TE GUSTA ELSA PATAKY?"
    assert _clean_text("¿A ti te gusta Elsa Pataky?", 22) == "¿A TI TE GUSTA ELSA"


def test_sin_flecha_apaga_el_paso():
    from src.editor_auto.services.estilo_vip import _a_config
    cfg = _a_config({"flecha": {"hay": False}, "notas_estilo": "Sin flecha."}, {})
    assert cfg["_flujo"]["sticker_arrow"] == {"enabled": False}


def test_probe_gira_video_vertical(monkeypatch):
    import json as _j
    from src.editor_auto.tools import vip_overlays as v
    out = {"streams": [{"codec_type": "video", "width": 1280, "height": 720, "r_frame_rate": "30/1",
                        "side_data_list": [{"rotation": -90}]}], "format": {"duration": "10"}}
    monkeypatch.setattr(v.subprocess, "check_output", lambda *a, **k: _j.dumps(out).encode())
    info = v._probe("x.mp4")
    assert (info["w"], info["h"]) == (720, 1280)


def test_subs_gigantes_y_pildora_con_letra_oscura():
    from src.editor_auto.services.estilo_vip import _subs_cfg
    assert _subs_cfg({"tamano": "gigante"})["font_scale"] == 0.075
    cfg = _subs_cfg({"resaltado": "pildora", "color_texto": "#0F0F0F", "palabras": 3})
    assert cfg["max_words"] == 1
