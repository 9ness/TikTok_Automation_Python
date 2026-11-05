"""Catálogo común de flechas y subtítulos (src/catalogo_edicion)."""
from __future__ import annotations

from src.catalogo_edicion import cargar, flechas, subtitulos, es_de_entrada

# El orden de rotación de las cuentas de TikTok Shop NO puede cambiar al pasar
# al catálogo (cada producto cae en la misma flecha que antes).
_TIKTOK_SHOP_DE_SIEMPRE = [
    "flecha_roja.mov", "flecha_negra.mov", "flecha_blanca.mov",
    "flecha_amarilla.mov", "flecha_cyan.mov", "flecha_verde.mov",
    "flecha_avanza_blanca.mov", "flecha_avanza_roja.mov",
    "flecha_triple_blanca.mov", "flecha_3d_roja.mov",
    "flecha_3d_amarilla.mov", "flecha_abajo_triple_blanca.mov",
]


def test_flechas_bien_formadas():
    cat = cargar()
    grupos = {g["id"] for g in cat["grupos_flecha"]}
    vistos = set()
    for f in cat["flechas"]:
        assert f["fichero"] not in vistos, f["fichero"]
        vistos.add(f["fichero"])
        assert f["grupo"] in grupos, f
        assert f.get("animacion", "bucle") in ("bucle", "entrada")
        assert f["nombre"]
        if f.get("animacion") == "entrada":
            # Las animaciones no entran en el sorteo del modo Inteligente ni
            # en la rotación de TikTok Shop, y traen su colocación.
            assert not f.get("inteligente") and not f.get("tiktok_shop")
            c = f["colocacion"]
            assert 0 < c["ancho"] <= 100 and 0 <= c["x"] <= 100 and 0 <= c["y"] <= 100


def test_ficheros_rotos_fuera():
    nombres = {f["fichero"] for f in flechas()}
    for roto in ("flecha_ige.mov", "flecha_rada.mov", "flecha_sa.mov", "flecha_roja_source.mov"):
        assert roto not in nombres


def test_tiktok_shop_mismo_orden():
    assert [f["fichero"] for f in flechas("tiktok_shop")] == _TIKTOK_SHOP_DE_SIEMPRE


def test_navidad_es_de_entrada():
    assert es_de_entrada("navidad_caja_flecha_rojo_oro.mov")
    assert not es_de_entrada("flecha_roja.mov")
    assert not es_de_entrada("no_existe.mov")


def test_subtitulos_bien_formados():
    ids = [s["id"] for s in subtitulos(None)]
    assert len(ids) == len(set(ids))
    for s in subtitulos(None):
        assert s["modo"] in ("word", "phrase")
        m = s["motor"]
        for k in ("text", "hl", "stroke", "sw", "mode", "pill", "font"):
            assert k in m, (s["id"], k)
        assert "css" in s["web"]
    # Los de siempre siguen (clientes con el estilo guardado) + FrutiNovelas.
    for i in ("clean", "red-pill", "anton-white", "fruti-rosa", "fruti-chismes", "fruti-verde"):
        assert i in ids


# --- style_mapper ----------------------------------------------------------
def _subs_cfg(steps):
    return next(s.config for s in steps if s.tool_id == "subs_auto")


def test_mapper_estilo_frutinovelas():
    from src.editor_auto.services.style_mapper import build_tool_flow
    cfg = _subs_cfg(build_tool_flow({"subtitle": {"presetId": "fruti-chismes", "mode": "word"}}))
    assert cfg["stroke_color"] == "#16A34A" and cfg["max_words"] == 1
    cfg = _subs_cfg(build_tool_flow({"subtitle": {"presetId": "fruti-verde", "mode": "phrase"}}))
    assert cfg["highlight_color"] == "#22C55E" and cfg["max_words"] == 2
    cfg = _subs_cfg(build_tool_flow({"subtitle": {"presetId": "red-pill", "mode": "phrase"}}))
    assert cfg["max_words"] == 4 and cfg["pill_enabled"] is True


def test_mapper_preset_desconocido_cae_a_limpio():
    from src.editor_auto.services.style_mapper import build_tool_flow
    cfg = _subs_cfg(build_tool_flow({"subtitle": {"presetId": "no-existe"}}))
    assert cfg["highlight_mode"] == "none" and cfg["text_color"] == "#FFFFFF"


def _arrow_cfg(monkeypatch, arr, en_disco):
    from src.editor_auto.services import style_mapper as sm
    monkeypatch.setattr("os.listdir", lambda _p: list(en_disco))
    steps = sm.build_tool_flow({"subtitle": {"enabled": False}, "arrow": {"enabled": True, **arr}})
    return next(s.config for s in steps if s.tool_id == "sticker_arrow")


def test_inteligente_sin_navidad_ni_rotas(monkeypatch):
    en_disco = ["flecha_roja.mov", "flecha_azul.mov", "flecha_ige.mov",
                "navidad_lazo_rojo_oro.mov", "flecha_roja_source.mov"]
    cfg = _arrow_cfg(monkeypatch, {"shapeId": "auto"}, en_disco)
    assert cfg["color_mode"] == "smart"
    assert cfg["candidate_stickers"] == ["flecha_azul.mov", "flecha_roja.mov"]


def test_flecha_fuera_del_catalogo_cae_a_roja(monkeypatch):
    cfg = _arrow_cfg(monkeypatch, {"shapeId": "flecha_ige.mov"}, ["flecha_roja.mov", "flecha_ige.mov"])
    assert cfg["sticker_file"] == "flecha_roja.mov"


def test_navidad_ancho_hasta_100(monkeypatch):
    cfg = _arrow_cfg(monkeypatch, {"shapeId": "navidad_lluvia_rojo_oro.mov", "scale": 4, "x": 0.5, "y": 0.75},
                     ["navidad_lluvia_rojo_oro.mov", "flecha_roja.mov"])
    assert cfg["sticker_file"] == "navidad_lluvia_rojo_oro.mov"
    assert cfg["scale_width_pct"] == 100.0


# --- sticker_arrow: animación de entrada -----------------------------------
def _cmd_overlay(monkeypatch, de_entrada):
    from src.editor_auto.tools import sticker_arrow as sa
    vistos = {}

    class _P:
        returncode = 0
        stderr = b""

    def fake_run(cmd, **_k):
        vistos["cmd"] = cmd
        return _P()

    monkeypatch.setattr(sa.subprocess, "run", fake_run)
    monkeypatch.setattr(sa, "_probe_video_size", lambda _p: (1080, 1920))
    sa._apply_overlay_ffmpeg(input_path="in.mp4", sticker_path="s.mov", output_path="o.mp4",
                             windows=[(3.0, 10.0)], position_x_pct=35, position_y_pct=81,
                             scale_width_pct=70, log=lambda _m: None, de_entrada=de_entrada)
    return vistos["cmd"]


def test_overlay_de_entrada_sin_bucle(monkeypatch):
    cmd = _cmd_overlay(monkeypatch, True)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "-stream_loop" not in cmd
    assert "setpts=PTS-STARTPTS+3.000/TB" in fc and "eof_action=repeat" in fc


def test_overlay_normal_en_bucle(monkeypatch):
    cmd = _cmd_overlay(monkeypatch, False)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "-stream_loop" in cmd and "setpts" not in fc
