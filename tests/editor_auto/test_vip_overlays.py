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
    out = _sanitize(plan, 60.0, _cfg())
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
    assert out["gancho"] == {"texto": "", "dato": "", "clip": None}
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
