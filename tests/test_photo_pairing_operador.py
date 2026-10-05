"""Emparejado en los catálogos del operador: manda el nombre (`N` / `N(1)`)."""
from src.nicho_pov_bof.services import photo_pairing as pp


def _foto(name: str, size: int) -> dict:
    return {"id": name, "name": name, "size": size, "rol": pp.rol_por_nombre(name)}


def test_rol_por_nombre():
    assert pp.rol_por_nombre("3.jpg") == "limpia"
    assert pp.rol_por_nombre("3(1).png") == "ficha"
    assert pp.rol_por_nombre("3(2).jpg") is None
    assert pp.rol_por_nombre("IMG_0245.jpg") is None


def test_ficha_generada_que_pesa_menos_no_pasa_por_limpia():
    # Temporada Q4: la ficha generada (PNG) pesa menos que la foto y hay extras.
    par = pp.pair_folder([
        _foto("8(1).png", 33757), _foto("8(2).jpg", 65522),
        _foto("8(3).jpg", 128851), _foto("8.jpg", 105471),
    ])[0]
    assert par["clean"]["name"] == "8.jpg"
    assert par["titled"]["name"] == "8(1).png"
    assert {x["name"] for x in par["extras"]} == {"8(2).jpg", "8(3).jpg"}
    assert par["confident"] and par["reason"] == "nombre"


def test_sin_rol_sigue_decidiendo_por_peso():
    # El Drive del curso no marca `rol`: comportamiento de siempre.
    par = pp.split_pair([
        {"id": "a", "name": "1.png", "size": 300},
        {"id": "b", "name": "1(1).png", "size": 100},
    ])
    assert par["clean"]["name"] == "1(1).png"
    assert par["reason"] == "peso"
