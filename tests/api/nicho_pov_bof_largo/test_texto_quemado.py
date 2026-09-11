"""El bloque de texto quemado, que el Largo reusa del POV BOF corto.

Vive aquí y no en un paquete propio porque es el Largo quien lo llama
(`pipeline/video_editor.montar` → `nicho_pov_bof.build_video`) y es donde
reventó: un vídeo entero montado para morir en la última pantalla.
"""

from __future__ import annotations

import pytest


class Corta(Exception):
    """Para parar el montaje justo después de lo que se quiere comprobar."""


class TestElColorDelRotulo:
    def test_le_llega_la_foto_del_producto(self, tmp_path, monkeypatch):
        """`_burn_text_block` usaba `foto_producto` sin recibirlo.

        El color del rótulo lo decide también el producto (de la foto limpia
        sale el color de la marca; en el vídeo no se puede medir porque medio
        encuadre es la mano). El parámetro se añadió a `build_video` pero no se
        pasó hasta aquí, así que el montaje moría con `NameError` cuando ya
        estaban la voz, los clips y el encaje hechos — 2m25s tirados por job.
        """
        from src.nicho_pov_bof.pipeline import video_editor as ve

        visto: dict = {}

        def fake_paleta(video, textos, semilla, on_log, foto=None):
            visto["foto"] = foto
            raise Corta

        monkeypatch.setattr(ve, "_elegir_paleta", fake_paleta)
        foto = tmp_path / "limpia.jpg"
        foto.write_bytes(b"no importa el contenido")

        with pytest.raises(Corta):
            ve._burn_text_block(
                tmp_path / "v.mp4", {"titulo": "Lo que sea"},
                tmp_path / "out.mp4", lambda _m: None,
                semilla="7", foto_producto=foto,
            )
        assert visto["foto"] == foto

    def test_sin_foto_sigue_montando(self, tmp_path, monkeypatch):
        """Es opcional: los formatos que no la tienen no pueden quedarse sin
        vídeo por el color del rótulo."""
        from src.nicho_pov_bof.pipeline import video_editor as ve

        visto: dict = {}

        def fake_paleta(video, textos, semilla, on_log, foto=None):
            visto["foto"] = foto
            raise Corta

        monkeypatch.setattr(ve, "_elegir_paleta", fake_paleta)
        with pytest.raises(Corta):
            ve._burn_text_block(
                tmp_path / "v.mp4", {"titulo": "Lo que sea"},
                tmp_path / "out.mp4", lambda _m: None, semilla="7",
            )
        assert visto["foto"] is None


class TestQueAcabadoLeToca:
    """El acabado del texto sale del gancho cuando nadie ha elegido."""

    def test_dolor_va_en_blanco_liso_y_precio_en_color(self):
        from src.nicho_pov_bof_largo import config

        assert config.estilo_texto_valido("", "dolor") == "blanco"
        # "" ES el clásico para el montador: no es que falte el dato.
        assert config.estilo_texto_valido("", "precio") == ""

    def test_lo_que_elige_el_operador_manda_sobre_el_gancho(self):
        from src.nicho_pov_bof_largo import config

        assert config.estilo_texto_valido("clasico", "dolor") == ""
        assert config.estilo_texto_valido("blanco", "precio") == "blanco"

    def test_el_clasico_no_se_convierte_en_blanco_por_el_camino(self):
        """Se resuelve UNA vez, al encolar.

        El montaje volvía a pasar el valor por `estilo_texto_valido`, y como
        para esa función "" significa "no me lo han dicho", el clásico se
        convertía otra vez en blanco: elegirlo en la tarjeta no servía de nada.
        """
        from src.nicho_pov_bof_largo import config

        encolado = config.estilo_texto_valido("clasico", "dolor")
        assert encolado == ""
        # Lo que llega al montador es este mismo valor, sin re-resolver.
        assert config.estilo_texto_valido(encolado, "dolor") == "blanco", (
            "si esto cambia, es que alguien ha vuelto a resolverlo dos veces"
        )
