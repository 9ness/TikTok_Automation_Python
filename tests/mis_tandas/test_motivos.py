"""Motivos del semáforo agrupados (`src/mis_tandas/motivos.py`). Módulo puro."""

from __future__ import annotations

import pytest

from src.mis_tandas import motivos

DIA = 86400.0
AHORA = 1_800_000_000.0


@pytest.mark.parametrize("frase,esperadas", [
    # Frases reales del semáforo.
    ("La suela sale color caramelo (en la foto es gris oscuro) y cambia de tono entre clips.",
     {"producto_distinto", "cambia_entre_clips"}),
    ("Estrella encendida sin enchufe ni interruptor, a escala gigante y luego en interior; sin subtítulos de la voz.",
     {"fisica_imposible", "encendido", "texto", "voz_guion"}),
    ("La mano roza la caja de la pulidora (5-6 s).", {"mano_toca"}),
    ("Kit de varias piezas; revisar que estén todas, idénticas en los 3 clips", {"complejo"}),
    ("Movimiento al límite: clip 2 1,19, riesgo de -4 estático (Admin 7/11)", {"movimiento"}),
    ("Producto infantil (caja para bloques de construcción de niños, la ficha dice Kids): regla sin niños.",
     {"ninos", "producto_distinto"}),
    ("Chaqueta igual a la ficha y diálogo bien, pero el subtítulo pone «minobia» en vez de «mi novia».",
     {"texto", "voz_guion", "producto_distinto"}),
    ("Descartado: viral con famosos reales (El Hormiguero)", {"descartado"}),
    ("Bandas negras arriba y abajo: Flow estaba en 3:4", {"formato"}),
    ("Bien, pero la tira de luz va encendida", {"encendido"}),
])
def test_clasifica_frases_reales(frase, esperadas):
    assert esperadas <= set(motivos.clasificar(frase))


@pytest.mark.parametrize("frase", ["", "   ", "marcado a mano", "🔴 marcado a mano", "REHACER", "Rehacer.", "ok"])
def test_frases_que_no_dicen_nada_son_sin_motivo(frase):
    assert motivos.clasificar(frase) == [motivos.SIN_MOTIVO]


def test_lo_que_no_encaja_va_a_otros():
    assert motivos.clasificar("Hacia los 7,5 s mira a cámara durante medio segundo.") == [motivos.OTROS]


def test_toda_categoria_tiene_titulo_y_consejo():
    claves = [c for c, *_ in motivos.CATEGORIAS]
    assert len(claves) == len(set(claves))
    for c in claves + [motivos.SIN_MOTIVO, motivos.OTROS]:
        assert motivos.TITULOS[c] and motivos.CONSEJOS[c]


def _sem(color, motivo="", hace_dias=1.0):
    return {"color": color, "motivo": motivo, "por": "agente", "listo_at": 1.0, "at": AHORA - hace_dias * DIA}


@pytest.fixture
def semaforos():
    return {
        "largo|a|b|1|": _sem("verde", "taza lisa"),
        "largo|a|b|2|": _sem("ambar", "Kit de varias piezas", 2),
        "largo|a|b|3|": _sem("ambar", "La mano toca la cafetera", 40),
        "rv|1": _sem("rojo", "El disco cambia entre el plano parado y el del agua", 3),
        "rv|2": _sem("rojo", "La cinta cambia de tono entre clips", 1),
        "rv|3": _sem("rojo", "marcado a mano", 5),
        "rv|4": _sem("verde"),
        "car|9": _sem("verde", "igual en todas"),
        "raro": {"color": "azul", "at": AHORA},      # color que no existe: se ignora
        "roto": "no es un dict",
    }


def test_resumen_cuenta_colores_y_agrupa(semaforos):
    r = motivos.resumen(semaforos, ahora=AHORA)
    assert r["revisados"] == 8 and r["colores"] == {"verde": 3, "ambar": 2, "rojo": 3}
    assert r["pct_rojo"] == 37.5 and r["pct_ambar"] == 25.0

    rojo = {x["categoria"]: x for x in r["rojo"]}
    assert rojo["cambia_entre_clips"]["videos"] == 2 and rojo["cambia_entre_clips"]["pct"] == 67
    # Ejemplos: el más reciente primero, con su id para ir a verlo.
    assert rojo["cambia_entre_clips"]["ejemplos"][0] == {"id": "rv|2", "motivo": "La cinta cambia de tono entre clips"}
    assert rojo["cambia_entre_clips"]["que_hacer"]
    assert rojo["sin_motivo"]["videos"] == 1
    # «sin motivo» y «otros» van al final aunque sean muchos.
    assert r["rojo"][0]["categoria"] == "cambia_entre_clips" and r["rojo"][-1]["categoria"] == "sin_motivo"
    assert {x["categoria"] for x in r["ambar"]} == {"complejo", "mano_toca"}


def test_resumen_por_nicho_y_plazo(semaforos):
    r = motivos.resumen(semaforos, ahora=AHORA)
    nichos = {x["nicho"]: x for x in r["por_nicho"]}
    assert nichos["rv"] == {"nicho": "rv", "verde": 1, "ambar": 0, "rojo": 3, "pct_rojo": 75.0}
    assert nichos["largo"]["ambar"] == 2 and nichos["car"]["verde"] == 1
    assert r["por_nicho"][0]["nicho"] == "rv"  # el que más vídeos tiene, primero

    # Solo los últimos 30 días: el ámbar de hace 40 no entra.
    r = motivos.resumen(semaforos, dias=30, ahora=AHORA)
    assert r["dias"] == 30 and r["colores"]["ambar"] == 1
    assert [x["categoria"] for x in r["ambar"]] == ["complejo"]


def test_resumen_vacio():
    r = motivos.resumen({}, ahora=AHORA)
    assert r["revisados"] == 0 and r["rojo"] == [] and r["ambar"] == [] and r["pct_rojo"] == 0.0
    assert motivos.resumen(None, ahora=AHORA)["por_nicho"] == []


def test_ejemplos_limitados():
    sem = {f"rv|{i}": _sem("rojo", f"el producto cambia entre clips {i}", i) for i in range(1, 9)}
    r = motivos.resumen(sem, ahora=AHORA, ejemplos=2)
    assert r["rojo"][0]["videos"] == 8 and [e["id"] for e in r["rojo"][0]["ejemplos"]] == ["rv|1", "rv|2"]
