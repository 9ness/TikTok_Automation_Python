"""Modo «Épico» del POV BOF Largo: golpes en el guion, dónde caen en la voz y
el prompt. El montaje de vídeo se prueba aparte (necesita ffmpeg)."""

from __future__ import annotations

from src.nicho_pov_bof_largo import config
from src.nicho_pov_bof_largo.pipeline import insertos


GUION = (
    "¿Tu espalda ya no aguanta más? [[GOLPE: ESPALDA DESTROZADA | la silla de frente]] "
    "Si pasas horas sentado, esto te interesa. Tiene reposapiés extraíble. "
    "[[GOLPE: reposapiés extraíble | el reposapiés sacado]] "
    "Han ajustado el precio. Ve al carrito naranja y aplica tus cupones."
)


def test_separa_golpes_y_limpia_el_guion():
    limpio, golpes = insertos.separar_golpes(GUION)
    assert "[[" not in limpio and "GOLPE" not in limpio
    assert limpio.startswith("¿Tu espalda ya no aguanta más? Si pasas horas")
    assert [g["texto"] for g in golpes] == ["ESPALDA DESTROZADA", "REPOSAPIÉS EXTRAÍBLE"]
    assert golpes[0]["tras"] == "¿Tu espalda ya no aguanta más?"
    assert golpes[1]["tras"] == "Tiene reposapiés extraíble."
    assert golpes[1]["escena"] == "el reposapiés sacado"


def test_respeta_el_maximo_y_sin_marcas_no_hay_golpes():
    _, golpes = insertos.separar_golpes(GUION, maximo=1)
    assert len(golpes) == 1
    limpio, golpes = insertos.separar_golpes("Un guion normal. Sin marcas.")
    assert golpes == [] and limpio == "Un guion normal. Sin marcas."


def _w(word, start, end):
    return {"word": word, "start": start, "end": end}


def test_localiza_el_final_de_la_frase_y_la_siguiente_palabra():
    palabras = [
        _w("¿Tu", 0.0, 0.2), _w("espalda", 0.2, 0.6), _w("ya", 0.6, 0.7), _w("no", 0.7, 0.8),
        _w("aguanta", 0.8, 1.2), _w("más?", 1.2, 1.6), _w("Si", 2.0, 2.1), _w("pasas", 2.1, 2.4),
        _w("tiene", 5.0, 5.2), _w("reposapiés", 5.2, 5.8), _w("extraíble.", 5.8, 6.4),
        _w("Han", 6.9, 7.0),
    ]
    _, golpes = insertos.separar_golpes(GUION)
    t = insertos.localizar(palabras, golpes)
    assert t[0] == (1.6, 2.0)
    assert t[1] == (6.4, 6.9)


def test_golpe_no_encontrado_es_none():
    _, golpes = insertos.separar_golpes(GUION)
    assert insertos.localizar([_w("otra", 0, 1), _w("cosa", 1, 2)], golpes) == [None, None]


def test_prompt_epico_es_el_de_dolor_mas_el_bloque():
    p = config.prompt_guion(False, "epico", False, 24)
    assert "MODO ÉPICO" in p and "[[GOLPE:" in p
    assert "VARIOS PUNTOS DE DOLOR" in p          # el del curso, literal
    assert "Bloque que se AÑADE" not in p         # la cabecera no va a Gemini
    assert "MODO ÉPICO" not in config.prompt_guion(False, "dolor", False, 24)
    assert config.es_epico("epico") and not config.es_epico("dolor")
    assert config.estilo_texto_de("epico") == "blanco"


def test_el_primer_golpe_siempre_tras_el_gancho():
    g = "¿Te irrita afeitarte? Esto te interesa. [[GOLPE: PIEL IRRITADA | de frente]] Tiene cabezal 9D."
    limpio, golpes = insertos.separar_golpes(g)
    assert golpes[0]["tras"] == "¿Te irrita afeitarte?"


def test_dos_marcas_tras_la_misma_frase_son_un_golpe():
    g = ("¿Tu setup ya no cabe? [[GOLPE: SIN ESPACIO | de frente]] Tiene forma de L y luces RGB. "
         "[[GOLPE: FORMA DE L | de lado]] [[GOLPE: LUCES RGB | las luces]] Ve al carrito naranja.")
    _, golpes = insertos.separar_golpes(g)
    assert [x["texto"] for x in golpes] == ["SIN ESPACIO", "FORMA DE L"]


def test_localiza_aunque_whisper_oiga_mal():
    palabras = [_w("Si", 0.0, 0.14), _w("rita", 0.14, 0.42), _w("feitarte", 0.42, 0.82),
                _w("cada", 0.82, 0.94), _w("mañana", 0.94, 1.4), _w("esto", 1.74, 2.0)]
    golpes = [{"tras": "¿Te irrita afeitarte cada mañana?", "texto": "X", "escena": ""}]
    assert insertos.localizar(palabras, golpes) == [(1.4, 1.74)]


def test_sonidos_por_video_y_boom_en_blanco(tmp_path):
    for n in (*config.SONIDOS_OSCURO, config.SONIDO_BLANCO):
        (tmp_path / n).write_bytes(b"x")
    s = insertos.elegir_sonidos(tmp_path, tmp_path / "1 Banco.mp4", [False, True, False])
    assert s[1].name == config.SONIDO_BLANCO
    assert s[0] == s[2] and s[0].name in config.SONIDOS_OSCURO     # uno por vídeo
    # el mismo vídeo suena igual al remontarlo
    assert insertos.elegir_sonidos(tmp_path, tmp_path / "1 Banco.mp4", [False])[0] == s[0]
    # con un fichero suelto, todos iguales
    f = tmp_path / config.SONIDO_BLANCO
    assert insertos.elegir_sonidos(f, tmp_path / "x.mp4", [False, True]) == [f, f]


def test_venta_inversa_prompt_y_cierre():
    p = config.prompt_guion(True, "inversa", True, 16)
    assert "VENTA INVERSA" in p and "El único problema es que" in p
    assert "pagarlo en cómodos plazos" not in p          # sin bloque de plazos
    assert "aperturas de precio" not in p
    g = "El gran problema de este banco es que no hay excusas. " + config.CTA_INVERSA
    assert config.es_cierre_inverso(g)
    # el recorte por precio no le cambia el cierre
    assert config.recortar_cta(g, plazos=False, envio=False) == g
    assert config.ctas_posibles(False, False, inversa=True)[0].startswith("Te lo dejo")
    assert not config.es_cierre_inverso("Y es bueno. Ve al carrito naranja y aplica tus cupones.")
    assert config.estilo_texto_de("inversa") == "blanco"
    # una sola duración: tres clips, pida lo que pida el producto
    assert config.segundos_de_estilo("inversa", 16) == config.SEGUNDOS_INVERSA == 24
    assert config.segundos_de_estilo("dolor", 16) == 16
    assert config.CTA_INVERSA in config.prompt_guion(False, "inversa", True, 24)


def test_venta_inversa_siempre_cierra_con_disponibilidad():
    g = "No compres este cubo si no quieres tres compartimentos. El único problema es que ordena."
    assert config.cerrar_guion(g, "inversa").endswith(config.CTA_INVERSA)
    assert config.cerrar_guion(g, "dolor") == g
    cerrado = config.cerrar_guion(g, "inversa")
    assert config.cerrar_guion(cerrado, "inversa") == cerrado


def test_carpetas_especiales_con_modo_fijo():
    from src.nicho_pov_bof import config as pov_config
    assert pov_config.modo_de_carpeta("Venta Inversa") == "inversa"
    assert pov_config.modo_de_carpeta("Épico Octubre") == "epico"
    assert pov_config.modo_de_carpeta("Carpeta_3") == ""


def test_replica_viral(monkeypatch):
    import sys, types
    from src.nicho_pov_bof import config as pov_config
    falso = types.ModuleType("src.replicar_viral.repos")
    falso.obtener = lambda rid: {"adaptacion": {"guion": "Mira esto. Ve al carrito naranja y aplica tus cupones."}} if rid == "abc" else None
    monkeypatch.setitem(sys.modules, "src.replicar_viral.repos", falso)
    e = config.guion_de_replica("abc", "Termómetro\nMomcozy")
    assert e["guion"].endswith("cupones.") and e["nombre"] == "Termómetro Momcozy"
    import pytest
    with pytest.raises(ValueError):
        config.guion_de_replica("nada")
    assert config.segundos_de_estilo("viral", 40) == 16
    assert pov_config.modo_de_carpeta("Réplicas virales") == "viral"
    assert pov_config.ve_carpeta_especial("Réplicas virales", "mauro")
    assert not pov_config.ve_carpeta_especial("Épico Octubre", "mauro")
