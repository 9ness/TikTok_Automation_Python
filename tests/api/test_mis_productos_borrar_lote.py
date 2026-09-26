"""Borrado en lote de los catálogos propios (Muestras / Tareas).

De uno en uno cada producto listaba la carpeta del Drive montado y limpiaba los
datos de todos los nichos por separado: vaciar una carpeta de diez tardaba
minutos. En lote es una pasada de ficheros y una de datos.
"""

from __future__ import annotations

from src.nicho_pov_bof.services import mis_productos


def _prepara(tmp_path, monkeypatch):
    carpeta = tmp_path / "Tareas Productos 4"
    carpeta.mkdir()
    for n in (1, 2, 3):
        (carpeta / f"{n}.jpg").write_bytes(b"x")
        (carpeta / f"{n}(1).jpg").write_bytes(b"x")
    (carpeta / "desktop.ini").write_text("x")
    monkeypatch.setattr(mis_productos, "_dir", lambda source="": tmp_path)
    llamadas: list = []
    from src.nicho_pov_bof.services import reanclaje

    monkeypatch.setattr(
        reanclaje, "borrar_productos",
        lambda source, folder, numeros: llamadas.append((folder, list(numeros))) or 0,
    )
    monkeypatch.setattr(mis_productos, "_invalidar", lambda source="": None)
    return carpeta, llamadas


def test_borra_solo_los_pedidos_con_una_sola_limpieza(tmp_path, monkeypatch):
    carpeta, llamadas = _prepara(tmp_path, monkeypatch)
    r = mis_productos.borrar_lote("Tareas Productos 4", ["1", "3"], source="tareas_productos")
    assert r["borrados"] == ["1", "3"] and r["ficheros"] == 4
    assert sorted(f.name for f in carpeta.iterdir()) == ["2(1).jpg", "2.jpg", "desktop.ini"]
    assert llamadas == [("Tareas Productos 4", ["1", "3"])]
    assert r["carpeta_borrada"] is False


def test_sin_lista_vacia_y_quita_la_carpeta(tmp_path, monkeypatch):
    carpeta, llamadas = _prepara(tmp_path, monkeypatch)
    r = mis_productos.borrar_lote("Tareas Productos 4", None, source="tareas_productos")
    assert r["borrados"] == ["1", "2", "3"]
    assert r["carpeta_borrada"] is True and not carpeta.exists()
    # Una sola limpieza de datos, que cubre también números sin fotos.
    assert len(llamadas) == 1 and "1" in llamadas[0][1] and "9" in llamadas[0][1]


def test_carpeta_que_no_existe(tmp_path, monkeypatch):
    _prepara(tmp_path, monkeypatch)
    assert mis_productos.borrar_lote("No existe", None)["borrados"] == []
