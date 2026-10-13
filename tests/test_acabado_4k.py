from src.nicho_pov_bof import config


def test_acabado_4k_apagado_y_encendido():
    assert config.ACABADO_4K not in config.filtro_encuadre(zoom=1.0, acabado=False)
    assert config.filtro_encuadre(zoom=1.0, acabado=True).endswith(config.ACABADO_4K)
    assert config.filtro_encuadre(zoom=1.07, esquina="centro", acabado=True).endswith(config.ACABADO_4K)
    assert config.acabado_4k(False) == ""
