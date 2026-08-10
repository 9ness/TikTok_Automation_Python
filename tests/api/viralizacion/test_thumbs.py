"""Miniaturas: lo que impide que la APK se cierre sola.

No es una optimización de red. El móvil guarda cada foto DESCODIFICADA (ancho ×
alto × 4 bytes), así que una ficha de 1320×2868 son 15 MB de RAM y una carpeta
de diez productos pedía ~300 MB: Chrome mataba la pestaña y, dentro de la APK,
eso se ve igual que "se ha cerrado la app".

Por eso los tests miran el TAMAÑO en píxeles y no el peso del fichero: lo que
tumbaba el móvil eran los píxeles.
"""

from __future__ import annotations

import pytest

from src.nicho_pov_bof.services import thumbs

Image = pytest.importorskip("PIL.Image")


@pytest.fixture(autouse=True)
def cache_temporal(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(thumbs.config, "photo_cache_dir", lambda: str(tmp_path))
    return tmp_path


def _foto(tmp_path, nombre="f.png", size=(1320, 2868), mode="RGB"):
    p = tmp_path / nombre
    Image.new(mode, size, (10, 20, 30) if mode == "RGB" else (10, 20, 30, 0)).save(p)
    return p


class TestEncoge:
    def test_baja_al_ancho_pedido_y_respeta_la_proporcion(self, tmp_path):
        chica = Image.open(thumbs.miniatura(_foto(tmp_path), 400))
        assert chica.size == (400, 869)

    def test_una_foto_ya_pequena_no_se_agranda(self, tmp_path):
        """Estirarla no añadiría detalle y sí memoria."""
        p = _foto(tmp_path, size=(200, 300))
        assert Image.open(thumbs.miniatura(p, 400)).size == (200, 300)

    def test_el_original_se_queda_intacto(self, tmp_path):
        """La foto de Drive es la que se monta en el vídeo: ni tocarla."""
        p = _foto(tmp_path)
        thumbs.miniatura(p, 400)
        assert Image.open(p).size == (1320, 2868)


class TestCache:
    def test_la_segunda_vez_devuelve_la_misma(self, tmp_path):
        p = _foto(tmp_path)
        assert thumbs.miniatura(p, 400) == thumbs.miniatura(p, 400)

    def test_cada_ancho_va_por_su_lado(self, tmp_path):
        p = _foto(tmp_path)
        assert thumbs.miniatura(p, 400) != thumbs.miniatura(p, 900)

    def test_si_cambia_la_foto_de_esa_ruta_cambia_la_miniatura(self, tmp_path):
        """En «Mis productos» el identificador es la RUTA, y la ruta se
        REUTILIZA: borras un producto, subes otro y `Mis Productos 1/1.png` es
        otra foto distinta. Sin esto se serviría la miniatura de la anterior —
        el mismo bug que ya nos comimos con la caché del navegador."""
        p = _foto(tmp_path)
        antes = thumbs.miniatura(p, 400)
        Image.new("RGB", (900, 900), (200, 0, 0)).save(p)
        assert thumbs.miniatura(p, 400) != antes


class TestNoRompeNunca:
    """Una foto pesada es un problema; una foto que no sale es peor."""

    def test_un_fichero_ilegible_devuelve_el_original(self, tmp_path):
        roto = tmp_path / "roto.png"
        roto.write_bytes(b"esto no es una imagen")
        assert thumbs.miniatura(roto, 400) == roto

    def test_una_foto_que_no_existe_devuelve_la_ruta_tal_cual(self, tmp_path):
        fantasma = tmp_path / "no_esta.png"
        assert thumbs.miniatura(fantasma, 400) == fantasma

    def test_la_transparencia_queda_en_BLANCO_y_no_en_negro(self, tmp_path):
        """Muchas fotos de producto vienen recortadas. Convertir a RGB a secas
        pinta el fondo de negro y la ficha se ve como si estuviera rota."""
        p = _foto(tmp_path, "alpha.png", size=(1200, 1200), mode="RGBA")
        assert Image.open(thumbs.miniatura(p, 400)).getpixel((5, 5)) == (255, 255, 255)
