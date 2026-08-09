"""«Mis productos»: la tercera fuente del POV BOF, la que sube el operador.

La idea de fondo es que un producto propio sea INDISTINGUIBLE de uno del curso
en todo lo que viene después. Eso se consigue guardando las fotos con el mismo
convenio de nombres del Drive compartido (`3.png` limpia, `3(1).png` ficha),
así que lo que hay que blindar con tests es justamente eso: el convenio y el
llenado de carpetas de diez en diez.

Si alguien "mejora" el nombrado, el emparejado deja de funcionar y el producto
aparece sin foto o con la ficha cambiada — y eso no se ve hasta que sale el
vídeo con el título equivocado.
"""

from __future__ import annotations

import pytest

from src.nicho_pov_bof import config
from src.nicho_pov_bof.services import mis_productos, photo_pairing


@pytest.fixture(autouse=True)
def raiz_temporal(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mis_productos.config, "mis_productos_dir", lambda: tmp_path)
    # Los listados se cachean (el Drive montado es lentísimo en frío) y la
    # caché vive en el módulo, no en la instancia: sin limpiarla, un test
    # heredaría las carpetas del tmp_path del anterior.
    mis_productos._invalidar()
    return tmp_path


def _subir(n: int = 1, con_ficha: bool = True) -> list[dict]:
    return [
        mis_productos.guardar_producto(
            b"limpia", b"ficha" if con_ficha else None,
            nombre_limpia="foto.png", nombre_ficha="ficha.png",
        )
        for _ in range(n)
    ]


class TestConvenioDeNombres:
    def test_las_fotos_se_llaman_como_las_del_curso(self, raiz_temporal):
        """`3.png` y `3(1).png`: de esto depende TODO lo de después."""
        _subir(3)
        nombres = sorted(p.name for p in (raiz_temporal / "Mis Productos 1").iterdir())
        assert nombres == [
            "1(1).png", "1.png", "2(1).png", "2.png", "3(1).png", "3.png",
        ]

    def test_el_emparejador_de_siempre_las_reconoce(self, raiz_temporal):
        """Sin tocar `photo_pairing`: es la prueba de que son indistinguibles."""
        _subir(2)
        fotos = mis_productos.listar_fotos_como_drive("Mis Productos 1")
        # Se simulan las dimensiones (la limpia cuadrada, la ficha alta), que
        # es lo que mira el emparejador para saber cuál es cuál.
        for f in fotos:
            alto = "(1)" in f["name"]
            f.update(width=600 if alto else 800, height=1300 if alto else 800)
        pares = photo_pairing.pair_folder(fotos)
        assert len(pares) == 2
        for p in pares:
            assert p["clean"]["name"] == f"{p['producto']}.png"
            assert p["titled"]["name"] == f"{p['producto']}(1).png"

    def test_la_ficha_es_opcional(self, raiz_temporal):
        _subir(1, con_ficha=False)
        nombres = [p.name for p in (raiz_temporal / "Mis Productos 1").iterdir()]
        assert nombres == ["1.png"]


class TestCarpetasDeDiez:
    def test_los_diez_primeros_van_juntos(self):
        creados = _subir(10)
        assert {c["carpeta"] for c in creados} == {"Mis Productos 1"}
        assert [c["producto"] for c in creados] == [str(i) for i in range(1, 11)]

    def test_el_once_abre_carpeta_nueva(self):
        creados = _subir(11)
        assert creados[10]["carpeta"] == "Mis Productos 2"
        # Y la numeración arranca de 1 DENTRO de la carpeta nueva, como en las
        # del curso (cada carpeta va del 1 al 10).
        assert creados[10]["producto"] == "1"

    def test_cuenta_productos_y_no_ficheros(self):
        """Cada producto son DOS fotos: contando ficheros, la carpeta se daría
        por llena a los cinco productos."""
        creados = _subir(10)
        assert creados[-1]["carpeta"] == "Mis Productos 1"

    def test_sigue_por_donde_iba_tras_reiniciar(self):
        """El estado está en el disco, no en memoria: no hay contador que
        perder al reiniciar la API."""
        _subir(10)
        assert mis_productos.carpeta_actual() == "Mis Productos 2"
        assert mis_productos.siguiente_producto("Mis Productos 1") == "11"


class TestBorrado:
    def test_borra_las_dos_fotos(self, raiz_temporal):
        _subir(2)
        assert mis_productos.borrar_producto("Mis Productos 1", "1") is True
        quedan = sorted(p.name for p in (raiz_temporal / "Mis Productos 1").iterdir())
        assert quedan == ["2(1).png", "2.png"]

    def test_borrar_lo_que_no_existe_devuelve_false(self):
        _subir(1)
        assert mis_productos.borrar_producto("Mis Productos 1", "99") is False

    def test_no_confunde_el_1_con_el_10(self, raiz_temporal):
        """Borrar el 1 no puede llevarse el 10, el 11…"""
        _subir(11)
        mis_productos.borrar_producto("Mis Productos 1", "1")
        quedan = {p.name for p in (raiz_temporal / "Mis Productos 1").iterdir()}
        assert "10.png" in quedan and "1.png" not in quedan


class TestFuenteEnElMenu:
    def test_esta_registrada_como_fuente(self):
        assert "mis_productos" in config.SOURCES
        assert config.SOURCES["mis_productos"]["label"] == "Mis productos"

    def test_es_propia_y_las_del_curso_no(self):
        assert config.es_fuente_propia("mis_productos")
        assert not config.es_fuente_propia("aleatorios_1")
        assert not config.es_fuente_propia("aleatorios_2")


class TestCacheDeFotos:
    """Las fotos propias NO se pueden cachear como las del curso.

    Un file ID de Drive es inmutable: ese contenido no cambia nunca, así que
    se cachea un día. Pero en «Mis productos» el identificador es la RUTA, y
    la ruta se REUTILIZA — borras un producto, subes otro y
    `Mis Productos 1/1.jpg` pasa a ser una foto distinta con la MISMA URL.

    Pasó de verdad: el operador subió tres productos y la pantalla le enseñó
    las fotos de antes durante 24h. El servidor mandaba los bytes correctos;
    era el navegador.
    """

    def test_las_propias_no_se_cachean(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        from src.api.main import app
        import src.nicho_pov_bof.services.drive_client as dc

        foto = tmp_path / "1.jpg"
        foto.write_bytes(b"\xff\xd8\xff")
        monkeypatch.setattr(
            dc, "list_photos",
            lambda *a, **k: [{"id": str(foto), "name": "1.jpg", "mime": "image/jpeg"}],
        )
        c = TestClient(app)
        r = c.get(
            "/api/v1/nicho-pov-bof/photo",
            params={"source": "mis_productos", "folder": "F", "file_id": str(foto)},
        )
        assert r.status_code == 200
        assert "no-cache" in r.headers.get("cache-control", "")

    def test_las_del_curso_siguen_cacheando(self, tmp_path, monkeypatch):
        """No hay que perder el cacheo donde SÍ es correcto: son 2.200 fotos
        y sin caché la pantalla va a tirones."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        import src.nicho_pov_bof.services.drive_client as dc

        foto = tmp_path / "1.jpg"
        foto.write_bytes(b"\xff\xd8\xff")
        monkeypatch.setattr(
            dc, "list_photos",
            lambda *a, **k: [{"id": str(foto), "name": "1.jpg", "mime": "image/jpeg"}],
        )
        c = TestClient(app)
        r = c.get(
            "/api/v1/nicho-pov-bof/photo",
            params={"source": "aleatorios_1", "folder": "F", "file_id": str(foto)},
        )
        assert "max-age=86400" in r.headers.get("cache-control", "")
