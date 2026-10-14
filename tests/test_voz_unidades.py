from src.nicho_pov_bof_largo.services.voz import para_fish


def test_unidades_en_letra_para_fish():
    assert para_fish("24,4 g de proteína") == "24,4 gramos de proteína"
    assert para_fish("bote de 1 kg y de 2 kg") == "bote de 1 kilo y de 2 kilos"
    assert para_fish("hasta 25 km/h y 250 W") == "hasta 25 kilómetros por hora y 250 vatios"
    assert para_fish("pack de 500g") == "pack de 500 gramos"


def test_sin_cifra_no_se_toca():
    assert para_fish("la g de gato y el kg suelto") == "la g de gato y el kg suelto"
    assert para_fish("cobertura 5G") == "cobertura 5G"
