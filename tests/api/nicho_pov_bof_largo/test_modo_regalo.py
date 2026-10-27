"""Modo «Regalo» del POV BOF Largo: prompt nuestro, sin promesas de campaña."""
from src.agente_mcp import menus
from src.nicho_pov_bof_largo import config


def test_regalo_es_un_estilo_con_su_prompt():
    assert config.ESTILOS_GUION["regalo"]["fichero"] == "guion_regalo.md"
    assert "regalo" in menus.MENUS["pov_bof_largo"].opciones["estilo_guion"]
    assert config.estilo_texto_valido("", "regalo") == "regalo"


def test_prompt_regalo_rellena_la_cta_y_no_lleva_la_cabecera():
    p = config.prompt_guion(plazos=False, estilo="regalo", segundos=16)
    assert "{{" not in p and "<!--" not in p
    assert config.CTA_CUPONES in p
    assert "GANCHO DE REGALO" in p
    # Lo que trae sanciones en campaña tiene que estar prohibido en el prompt.
    for veto in ("envoltorio", "fechas de entrega", "ADULTOS"):
        assert veto in p
    # El cupón se sugiere, no se afirma, en el texto nuevo.
    assert "Revisa si tienes cupones" in p
