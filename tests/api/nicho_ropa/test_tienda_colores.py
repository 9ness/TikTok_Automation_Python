"""El formato "Tienda Colores 15s" del Nicho Ropa (Moda Mujer, aleatorios).

Lo que lo separa del de calle dividido y hay que proteger:
- el guion devuelve la lista de colores (el puesto el último) y se guarda;
- cada clip lleva SU bloque de movimiento (de frente / de espaldas);
- el montaje encuentra en la voz cuándo dice cada color, y si no, se rinde
  con una cadencia fija en vez de romper el vídeo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.nicho_ropa import config
from src.nicho_ropa.pipeline import colores
from src.nicho_ropa.services import guionista, recolor


class TestConfig:
    def test_el_modo_existe_solo_para_mujer_aleatorios(self):
        claves = [m["clave"] for m in config.modos_de("mujer")]
        assert "tienda_colores" in claves
        assert "tienda_colores" not in [m["clave"] for m in config.modos_de("hombre")]
        assert "tienda_colores" not in [m["clave"] for m in config.modos_de("mujer", "marca")]

    def test_es_un_formato_de_dos_clips_con_todo_el_remate(self):
        assert config.partes_de_modo("tienda_colores") == 2
        assert config.lleva_subtitulos("tienda_colores")
        assert config.lleva_flecha("tienda_colores")
        assert config.lleva_colores("tienda_colores")
        # Y el de calle dividido NO lleva los cortes de color.
        assert not config.lleva_colores("calle_dividido")

    def test_los_prompts_traen_lo_que_pinta_la_pantalla(self):
        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        assert e["colores"] is True
        assert e["partes"] == 2
        assert e["imagen2"].strip()
        assert "DE ESPALDAS" in e["imagen2"]
        assert e["escrito_fuera"]  # lleva {{CARACTERES}}: hay botón de guiones
        assert e["caracteres"] == 230
        assert e["caracteres_clip"] == 119
        assert "{{" not in e["guion"] and "{{" not in e["imagen"]

    def test_el_esquema_de_la_api_no_pierde_el_campo(self):
        """Pydantic descarta las claves que no declara (learnings 878)."""
        from src.api.schemas.nicho_ropa.models import EstiloMof10, PrendaInfo

        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        assert EstiloMof10(**e).colores is True
        assert PrendaInfo(
            producto="1", guion_colores=["rosa", "verde"], uploaded=False, uploaded_at=0,
            video_path=None, video_listo_at=0, montando=False,
        ).guion_colores == ["rosa", "verde"]


class TestGuionPorClip:
    @pytest.fixture
    def guion(self):
        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        return e["guion"]

    def test_cada_clip_lleva_solo_su_movimiento(self, guion):
        v1 = guionista._montar_video(guion, "Rosa y verde. Mira esta cintura.", parte=1)
        v2 = guionista._montar_video(guion, "Por detrás sienta fenomenal.", parte=2)
        assert "«Rosa y verde. Mira esta cintura.»" in v1
        assert "«Por detrás sienta fenomenal.»" in v2
        assert "Movimiento clip" not in v1 and "Movimiento clip" not in v2
        assert "\nMovimiento:\n" in v1 and "\nMovimiento:\n" in v2
        assert "No se gira" in v1 and "No se gira" not in v2
        assert "DE ESPALDAS" in v2 and "DE ESPALDAS" not in v1
        # La voz es común y va en los dos.
        assert "Voz femenina" in v1 and "Voz femenina" in v2

    def test_los_prompts_de_un_solo_movimiento_no_cambian(self):
        (c,) = config.prompts_mof10("mujer", False, "calle_dividido")
        assert guionista._montar_video(c["guion"], "x", parte=2) == guionista._montar_video(c["guion"], "x")

    def test_sin_bloque_para_esa_parte_se_queda_el_primero(self):
        cuerpo = "Voz.\n\nMovimiento clip 1:\n\nde frente\n\nMovimiento clip 2:\n\nde espaldas"
        assert guionista.solo_parte(cuerpo, 3).endswith("Movimiento:\n\nde frente")

    def test_el_formato_pide_los_colores_solo_en_este_formato(self):
        con = guionista._formato_clips(2, 119, 8, colores=True)
        sin = guionista._formato_clips(2, 119, 8)
        assert '"colores"' in con and "ÚLTIMO" in con and "misma tienda" in con
        assert '"colores"' not in sin and "sitios distintos" in sin

    def test_limpiar_hex(self):
        assert guionista.limpiar_hex(
            {"Rosa": "e7b8c4", "beige": "#zz", "verde": "#5A6B4F", "otro": "#000000"},
            ["rosa", "beige", "verde"],
        ) == {"rosa": "#e7b8c4", "verde": "#5a6b4f"}
        assert guionista.limpiar_hex(["#000"], ["rosa"]) == {}

    def test_limpiar_colores(self):
        assert guionista.limpiar_colores(["Rosa,", " Verde ", "rosa", "", 3, "x" * 40]) == ["rosa", "verde"]
        assert guionista.limpiar_colores("rosa") == []
        assert len(guionista.limpiar_colores(list("abcdefgh"))) == 6

    def test_escribir_devuelve_los_colores(self, monkeypatch):
        """Con Gemini simulado: la lista sale saneada y cada clip con su bloque."""
        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        import src.tiktok_shop.api.gemini as gemini

        def falso(system_prompt, user_prompt, **kw):
            assert '"colores"' in system_prompt
            return {
                "colores": ["Rosa", "beige", "negro", "Verde"],
                "colores_hex": {"rosa": "#e7b8c4", "verde": "#5a6b4f", "fucsia": "#ff00ff"},
                "clips": [
                    "Rosa, beige, negro y verde. Mira esta cintura alta con cordón y bolsillos de verdad.",
                    "Por detrás sienta fenomenal y al agacharme no se baja nada. Varios colores en tienda, elige el tuyo.",
                ],
            }

        monkeypatch.setattr(gemini, "generate_json", falso)
        salida = guionista.escribir(
            prompt=e["guion"], titulo="Pantalón palazzo", partes=2,
            caracteres_clip=119, segundos_clip=8, colores=True,
        )
        assert salida["colores"] == ["rosa", "beige", "negro", "verde"]
        assert salida["colores_hex"] == {"rosa": "#e7b8c4", "verde": "#5a6b4f"}
        assert len(salida["videos"]) == 2
        assert "DE ESPALDAS" in salida["videos"][1] and "DE ESPALDAS" not in salida["videos"][0]
        assert salida["videos"][0].rstrip().endswith("sin cortar ninguna palabra.")

    def test_sin_colores_no_se_pide_nada(self, monkeypatch):
        (e,) = config.prompts_mof10("mujer", False, "calle_dividido")
        import src.tiktok_shop.api.gemini as gemini

        monkeypatch.setattr(
            gemini, "generate_json",
            lambda s, u, **kw: {"clips": ["Hola qué tal.", "Adiós."]},
        )
        salida = guionista.escribir(
            prompt=e["guion"], titulo="x", partes=2, caracteres_clip=119, segundos_clip=8,
        )
        assert "colores" not in salida


def _palabras(*pares):
    """`[("rosa", 0.0), ("beige", 0.9), …]` → lo que devuelve Whisper."""
    return [{"word": w, "start": t, "end": t + 0.3} for w, t in pares]


class TestTiemposDeColores:
    def test_los_encuentra_en_orden(self):
        palabras = _palabras(
            ("rosa,", 0.0), ("beche,", 0.9), ("negro", 1.7), ("y", 2.1), ("verde.", 2.4),
            ("Mira", 2.9), ("esto,", 3.0),
        )
        assert colores.tiempos_de_colores(palabras, ["rosa", "beige", "negro", "verde"]) == [0.0, 0.9, 1.7, 2.4]

    def test_dos_colores_que_empiezan_igual(self):
        """"Azul claro, azul, gris y verde": el segundo azul no casa con el primero."""
        palabras = _palabras(
            ("Azul", 0.0), ("claro,", 0.4), ("azul,", 1.1), ("gris", 1.7), ("y", 2.2), ("verde,", 2.5),
        )
        assert colores.tiempos_de_colores(palabras, ["azul claro", "azul", "gris", "verde"]) == [0.0, 1.1, 1.7, 2.5]

    def test_interpola_el_que_no_oye(self):
        palabras = _palabras(("verde,", 0.0), ("rrrosa", 0.7), ("negro", 1.5), ("kawki.", 2.3))
        t = colores.tiempos_de_colores(palabras, ["verde", "rosa", "negro", "caqui"])
        assert t[0] == 0.0 and t[2] == 1.5
        assert 0.0 < t[1] < 1.5
        assert t[3] > 1.5

    def test_se_rinde_si_no_oye_ni_la_mitad(self):
        palabras = _palabras(("hola", 0.0), ("mira", 0.5), ("esto", 1.0))
        assert colores.tiempos_de_colores(palabras, ["rosa", "beige", "verde"]) == []
        assert colores.tiempos_de_colores([], ["rosa", "verde"]) == []

    def test_no_busca_pasada_la_ventana(self):
        palabras = _palabras(("hola", 0.0), ("verde", 9.0), ("rosa", 9.5))
        assert colores.tiempos_de_colores(palabras, ["verde", "rosa"]) == []

    def test_cadencia_por_defecto_arranca_con_la_voz(self):
        assert colores._tiempos_por_defecto(_palabras(("hola", 0.42)), 3) == [
            pytest.approx(0.42), pytest.approx(1.22), pytest.approx(2.02),
        ]


class TestRecolor:
    def test_describe_el_color_en_ingles(self):
        assert recolor.describir_color("Beige") == "a light sand / cream beige colour"
        assert recolor.describir_color("azul marino") == "navy blue"
        assert recolor.describir_color("Marrón oscuro") == "dark chocolate brown"
        assert recolor.describir_color("verde agua").startswith("green (verde agua")
        assert "Spanish colour name" in recolor.describir_color("ocre quemado")

    def test_el_prompt_lleva_el_color_y_nada_de_notas(self):
        p = config.prompt_recolor("navy blue")
        assert "navy blue" in p and "<!--" not in p and "{{" not in p
        assert "Target shade" not in p
        assert "approximately #8b7d6b" in config.prompt_recolor("taupe", "#8b7d6b")

    def test_reintenta_una_vez_y_luego_lanza(self, monkeypatch):
        llamadas = []

        def falla(*a, **k):
            llamadas.append(1)
            raise RuntimeError("IMAGE_OTHER")

        monkeypatch.setattr(recolor, "_recolorear", falla)
        with pytest.raises(RuntimeError, match="IMAGE_OTHER"):
            recolor.recolorear(b"x", "beige")
        assert len(llamadas) == recolor._INTENTOS

    def test_sin_key_lanza(self, monkeypatch):
        import src.tiktok_shop.api.gemini as gemini

        monkeypatch.setattr(gemini, "_get_gemini_keys", lambda: [])
        with pytest.raises(RuntimeError, match="sin key"):
            recolor._recolorear(b"x", "rosa", "image/jpeg", lambda _m: None)


class TestAplicar:
    def test_con_un_solo_color_no_toca_el_clip(self, tmp_path):
        clip = tmp_path / "c.mp4"
        clip.write_bytes(b"")
        assert colores.aplicar(clip, ["verde"], tmp_path / "w") == clip
        assert colores.aplicar(clip, [], tmp_path / "w") == clip

    def test_reutiliza_las_fotos_ya_recoloreadas(self, tmp_path, monkeypatch):
        """Volver a montar el mismo producto no vuelve a pagar las imágenes."""
        import src.nicho_pov_bof.pipeline.video_editor as pov

        work = tmp_path / "w"
        work.mkdir()
        (work / "color_rosa.png").write_bytes(b"png")
        monkeypatch.setattr(pov, "_transcribir_voz", lambda *a, **k: _palabras(("rosa", 0.0), ("verde", 0.8)))
        monkeypatch.setattr(colores, "_run", lambda cmd, on_log: Path(cmd[-1]).write_bytes(b"jpg"))
        pagadas = []
        monkeypatch.setattr(recolor, "recolorear", lambda *a, **k: pagadas.append(k.get("tono")) or b"png")
        superpuesto = {}
        monkeypatch.setattr(
            colores, "_superponer",
            lambda clip, fotos, tiempos, destino, on_log: superpuesto.update(fotos=fotos, tiempos=tiempos),
        )
        clip = tmp_path / "clip1.mp4"
        clip.write_bytes(b"")
        salida = colores.aplicar(clip, ["rosa", "verde"], work)
        assert salida.name == "clip1_colores.mp4"
        assert not pagadas
        assert superpuesto["fotos"] == [work / "color_rosa.png"]
        assert superpuesto["tiempos"] == [0.0, 0.8]

    def test_el_tono_de_cada_color_llega_al_recolor(self, tmp_path, monkeypatch):
        import src.nicho_pov_bof.pipeline.video_editor as pov

        work = tmp_path / "w"
        monkeypatch.setattr(pov, "_transcribir_voz", lambda *a, **k: _palabras(("rosa", 0.0), ("beige", 0.8), ("verde", 1.6)))
        monkeypatch.setattr(colores, "_run", lambda cmd, on_log: Path(cmd[-1]).write_bytes(b"jpg"))
        tonos = []
        monkeypatch.setattr(recolor, "recolorear", lambda base, color, **k: tonos.append((color, k.get("tono"))) or b"png")
        monkeypatch.setattr(colores, "_superponer", lambda *a, **k: None)
        clip = tmp_path / "clip1.mp4"
        clip.write_bytes(b"")
        colores.aplicar(clip, ["rosa", "Beige", "verde"], work, tonos={"Rosa": "#e7b8c4"})
        assert tonos == [("rosa", "#e7b8c4"), ("Beige", "")]

    def test_cada_color_con_el_fotograma_de_su_palabra(self, tmp_path, monkeypatch):
        """En el viral cada color es otra toma: se coge el fotograma del
        instante en que lo nombra, no el mismo para todos."""
        import src.nicho_pov_bof.pipeline.video_editor as pov

        work = tmp_path / "w"
        monkeypatch.setattr(pov, "_transcribir_voz", lambda *a, **k: _palabras(("rosa", 0.1), ("beige", 0.9), ("verde", 1.7)))
        instantes = []

        def run(cmd, on_log):
            if "-ss" in cmd:
                instantes.append(float(cmd[cmd.index("-ss") + 1]))
            Path(cmd[-1]).write_bytes(b"jpg")

        monkeypatch.setattr(colores, "_run", run)
        monkeypatch.setattr(recolor, "recolorear", lambda base, color, **k: b"png")
        monkeypatch.setattr(colores, "_superponer", lambda *a, **k: None)
        clip = tmp_path / "clip1.mp4"
        clip.write_bytes(b"")
        colores.aplicar(clip, ["rosa", "beige", "verde"], work)
        assert instantes == [0.1, 0.9]


class TestVariantes:
    def test_guardar_ver_y_quitar(self, tmp_path, monkeypatch):
        from src.nicho_ropa.services import variantes

        monkeypatch.setattr(config, "prendas_web_dir", lambda: tmp_path)
        assert variantes.ruta("mujer_web__Carpeta 1", "3") is None
        variantes.guardar("mujer_web__Carpeta 1", "3", b"img", "captura.PNG")
        f = variantes.ruta("mujer_web__Carpeta 1", "3")
        assert f and f.suffix == ".png" and f.read_bytes() == b"img"
        # No cuelga de ningún género: `_variantes` no sale en los selectores.
        assert f.parent.parent.name == "_variantes"
        assert variantes.tienen("mujer_web__Carpeta 1") == {"3"}
        # Sustituir con otra extensión no deja dos.
        variantes.guardar("mujer_web__Carpeta 1", "3", b"img2", "otra.jpg")
        assert variantes.ruta("mujer_web__Carpeta 1", "3").suffix == ".jpg"
        assert len(list(f.parent.iterdir())) == 1
        assert variantes.quitar("mujer_web__Carpeta 1", "3")
        assert variantes.ruta("mujer_web__Carpeta 1", "3") is None

    def test_rechaza_lo_que_no_es_imagen(self, tmp_path, monkeypatch):
        from src.nicho_ropa.services import variantes

        monkeypatch.setattr(config, "prendas_web_dir", lambda: tmp_path)
        with pytest.raises(ValueError):
            variantes.guardar("c", "1", b"x", "captura.pdf")
        with pytest.raises(ValueError):
            variantes.guardar("c", "1", b"", "captura.jpg")


class TestBloqueoDeGemini:
    def test_si_bloquea_con_fotos_se_reintenta_sin_ellas(self, monkeypatch):
        import src.tiktok_shop.api.gemini as gemini

        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        llamadas = []

        def falso(system_prompt, user_prompt, images=None, **kw):
            llamadas.append(images)
            if images:
                raise gemini.GeminiBlockedError("Gemini bloqueó la petición (PROHIBITED_CONTENT)")
            return {"colores": ["rosa", "verde"], "clips": ["Rosa y verde. Mira.", "Por detrás. Elige."]}

        monkeypatch.setattr(gemini, "generate_json", falso)
        salida = guionista.escribir(
            prompt=e["guion"], titulo="x", fotos=[Path("/tmp/a.jpg")], partes=2,
            caracteres_clip=119, segundos_clip=8, colores=True,
        )
        assert salida["colores"] == ["rosa", "verde"]
        assert llamadas == [["/tmp/a.jpg"], None]

    def test_los_leidos_de_la_ficha(self):
        from src.nicho_ropa.services import variantes

        assert variantes.leidos({}) == {"colores": [], "hex": {}}
        assert variantes.leidos({"variantes": {"colores": ["beige", ""], "hex": {"beige": "#d9cdb8", "x": ""}}}) == {
            "colores": ["beige"], "hex": {"beige": "#d9cdb8"},
        }
