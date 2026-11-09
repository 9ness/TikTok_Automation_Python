"""Lectura de las pantallas de TikTok Studio del Mi 8 (cuenta árabe) sin móvil.

Fixtures: OCR (tesseract spa --psm 11) de capturas reales de la página Datos guardadas el 4-5/11/2026.
Valores esperados = los que se apuntaron en el panel esos días.
"""
import datetime
import json
import pathlib
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts" / "estadisticas_movil"))
import studio_ocr as so  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures"


def pal(dia):
    return [tuple(p) for p in json.loads((FIX / f"datos_{dia}.json").read_text(encoding="utf-8"))]


@pytest.mark.parametrize("dia, esperado", [
    ("2026-11-03", {"gmv": 37.75, "ventas": 1, "impresiones": 4400, "clics": 98, "comision": 3.74}),
    ("2026-11-01", {"gmv": 0, "ventas": 0, "impresiones": 3900, "clics": 139, "comision": 0}),
    ("2026-10-29", {"gmv": 0, "ventas": 0, "impresiones": 341, "clics": 7, "comision": 0}),
])
def test_resumen_dia(dia, esperado):
    r = so.extraer_resumen(pal(dia), datetime.date.fromisoformat(dia))
    assert r["fecha"] == dia
    for k, v in esperado.items():
        assert r[k] == v, k


def test_resumen_cifra_no_leida_queda_none():
    # 4/11: el OCR de pantalla entera no lee «1,1K» de impresiones → None (lo relee dias_mi8 por zona)
    r = so.extraer_resumen(pal("2026-11-04"), datetime.date(2026, 11, 4))
    assert r["impresiones"] is None
    assert r["clics"] == 31 and r["ventas"] == 0


def test_pagina_de_otro_dia_falla():
    with pytest.raises(ValueError):
        so.extraer_resumen(pal("2026-11-03"), datetime.date(2026, 11, 4))


@pytest.mark.parametrize("dia", ["2026-11-03", "2026-11-04", "2026-11-01", "2026-10-29"])
def test_cabecera_es_del_dia(dia):
    f = datetime.date.fromisoformat(dia)
    assert so.es_dia(so.cabecera_resumen(pal(dia)), f)


@pytest.mark.parametrize("texto, valor", [
    ("37,75 €", 37.75), ("4,4K", 4400), ("11K", 11000), ("1.234", 1234), ("1/1K", 1100),
    ("O", 0), ("—", None), (None, None), ("98", 98),
])
def test_num(texto, valor):
    assert so.num(texto) == valor


def test_es_dia_tolera_0ct_y_cero_delante():
    assert so.es_dia("29 0ct 2026 gmt+1", datetime.date(2026, 10, 29))
    assert so.es_dia("03 nov 2026", datetime.date(2026, 11, 3))
    assert not so.es_dia("13 nov 2026", datetime.date(2026, 11, 3))


@pytest.mark.parametrize("lecturas, valor", [
    (["1/1K", "11K", "11K"], 1100),     # la coma solo sale a una escala: gana
    (["11K", "11K", "11K"], 11000),
    (["4,4K", "4,4K", "4,4K"], 4400),
    (["", "abc", "7"], 7),
    (["", ""], None),
])
def test_elegir_lectura(lecturas, valor):
    assert so.elegir_lectura(lecturas) == valor


def test_zona_cifra_por_columna():
    assert so.zona_cifra((80, 1238)) == (60, 1320, 460, 90)
    assert so.zona_cifra((592, 1245))[0] == 570


def test_comision_pestana():
    p = [(80, 900, 200, 31, "Comisiones"), (290, 900, 160, 31, "estimadas"),
         (80, 990, 120, 45, "3,74"), (80, 1060, 100, 30, "-12%")]
    assert so.extraer_comision(p) == 3.74
    assert so.extraer_comision([(80, 900, 100, 30, "Nada")]) is None


def test_pestanas_comision():
    p = [(300, 500, 100, 30, "Resumen"), (600, 505, 140, 30, "Comisiones"), (80, 900, 200, 31, "Comisiones")]
    assert so.pestanas_comision(p) == [(600, 505)]


def test_parse_tsv_filtra_confianza_y_vacios():
    tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
           "5\t1\t1\t1\t1\t1\t10\t20\t30\t40\t95.1\tGMV\n"
           "5\t1\t1\t1\t1\t2\t10\t20\t30\t40\t12\truido\n"
           "5\t1\t1\t1\t1\t3\t10\t20\t30\t40\t90\t \n"
           "4\t1\t1\t1\t1\t0\t0\t0\t0\t0\t-1\t\n")
    assert so.parse_tsv(tsv) == [(10, 20, 30, 40, "GMV")]


def test_parse_volcado():
    xml = ('<node text="TikTok Studio" bounds="[100,800][356,886]"/>'
           '<node text="" content-desc="Ver detalles" bounds="[700,700][900,760]"/>'
           '<node text="A &amp; B" bounds="[0,0][10,10]"/>')
    assert so.parse_volcado(xml) == [(228, 843, "TikTok Studio"), (800, 730, "Ver detalles"), (5, 5, "A & B")]


def test_ver_detalles_por_volcado_y_por_ocr():
    nodos = [(300, 730, "Ver detalles"), (800, 730, "Ver detalles")]
    assert so.boton_ver_detalles(nodos) == (800, 730)          # la tarjeta de la derecha
    ocr = [(250, 720, 50, 30, "Ver"), (310, 720, 110, 30, "detalles"),
           (750, 720, 50, 30, "Ver"), (810, 720, 110, 30, "detalles"), (100, 300, 90, 30, "detalles")]
    assert so.boton_ver_detalles([], ocr) == (825, 735)
    assert so.boton_ver_detalles([], []) is None


@pytest.mark.parametrize("dia", ["2026-11-03", "2026-11-04", "2026-11-01", "2026-10-29"])
def test_pagina_datos_no_es_puzle(dia):
    assert not so.hay_puzle_ocr(pal(dia))


def test_puzle_por_ocr():
    assert so.hay_puzle_ocr([(100, 900, 300, 40, "Verifica"), (420, 900, 200, 40, "para"), (630, 900, 200, 40, "continuar")])
    assert so.hay_puzle_ocr([(100, 900, 300, 40, "Arrastra"), (420, 900, 200, 40, "el"), (630, 900, 200, 40, "control")])
