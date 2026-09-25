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
        assert e["caracteres"] == 200
        assert e["caracteres_clip"] == 100
        # Los marcadores de duración y plazos vienen ya rellenos; los de
        # FAMILIA siguen puestos a propósito (los rellena `con_familia` con
        # el tipo de prenda de cada producto).
        for marcador in ("{{CARACTERES}}", "{{MINIMO}}", "{{SEGUNDOS}}", "{{FRASE_PLAZOS}}"):
            assert marcador not in e["guion"] and marcador not in e["imagen"]
        limpio = config.con_familia(e["guion"], "Pantalón wide leg")
        assert "{{" not in limpio
        assert "{{" not in config.con_familia(e["imagen"], "Pantalón wide leg")

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
        assert "de espaldas" in v2 and "de espaldas" not in v1
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

    def test_reordenar_enumeracion(self):
        r = guionista.reordenar_enumeracion
        assert r("Beige, marron, taupe y verde militar. Mira.", ["beige", "marron", "verde militar", "taupe"]) == "Beige, marron, verde militar y taupe. Mira."
        assert r("Azul claro, azul, gris y verde. Mira.", ["azul", "gris", "verde", "azul claro"]) == "Azul, gris, verde y azul claro. Mira."
        # Con acento en la frase también casa.
        assert r("Beige, marrón y taupe. Mira.", ["beige", "taupe", "marron"]).startswith("Beige, taupe y marron.")
        # Sin enumeración al principio, no se toca.
        assert r("Mira este pantalón beige.", ["beige", "taupe"]) == "Mira este pantalón beige."

    def test_forzar_enumeracion(self):
        f = guionista.forzar_enumeracion
        # Nombra un color que no tiene y le falta otro: manda la lista.
        assert f("Beige, marrón, verde militar y azul marino. Tejido suave.", ["negro", "verde militar", "azul marino", "beige"]) == "Negro, verde militar, azul marino y beige. Tejido suave."
        # No nombra ninguno: se abre con la lista.
        assert f("Mira este vestido. Qué escote.", ["granate", "negro"]) == "Granate y negro. Mira este vestido. Qué escote."
        # Ya casa (con otro orden o acentos): solo se reordena.
        assert f("Beige, marrón y negro. Mira.", ["negro", "beige", "marron"]).startswith("Negro, beige y marron.")
        # Una frase de adjetivos no es una lista de colores.
        assert f("Suave, fresca y cómoda. Mola.", ["rosa", "negro"]) == "Rosa y negro. Suave, fresca y cómoda. Mola."
        # Con un color no hay lista.
        assert f("Mira esta chaqueta.", ["negro"]) == "Mira esta chaqueta."

    def test_el_color_puesto_va_el_ultimo(self, monkeypatch):
        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        import src.tiktok_shop.api.gemini as gemini

        monkeypatch.setattr(gemini, "generate_json", lambda s, u, **k: {
            "colores": ["beige", "marron", "taupe", "verde militar"],
            "color_puesto": "Taupe",
            "clips": ["Beige, marron, taupe y verde militar. Mira este culotte.", "Por detrás queda genial. Elige el tuyo."],
        })
        salida = guionista.escribir(
            prompt=e["guion"], titulo="x", partes=2, caracteres_clip=119, segundos_clip=8, colores=True,
        )
        assert salida["colores"] == ["beige", "marron", "verde militar", "taupe"]
        assert salida["dice"].startswith("Beige, marron, verde militar y taupe.")
        assert "«Beige, marron, verde militar y taupe. Mira este culotte.»" in salida["videos"][0]

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
        assert "de espaldas" in salida["videos"][1] and "de espaldas" not in salida["videos"][0]
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

        monkeypatch.setattr(colores, "RECOLOR_IA", True)
        # El recolor sobre el vídeo se deja apagado salvo que el caso lo pida:
        # con él encendido no se llega a la rama de las fotos.
        monkeypatch.setattr(colores, "RECOLOR_VIDEO", False)
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

        monkeypatch.setattr(colores, "RECOLOR_IA", True)
        # El recolor sobre el vídeo se deja apagado salvo que el caso lo pida:
        # con él encendido no se llega a la rama de las fotos.
        monkeypatch.setattr(colores, "RECOLOR_VIDEO", False)
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

        monkeypatch.setattr(colores, "RECOLOR_IA", True)
        # El recolor sobre el vídeo se deja apagado salvo que el caso lo pida:
        # con él encendido no se llega a la rama de las fotos.
        monkeypatch.setattr(colores, "RECOLOR_VIDEO", False)
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

        monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
        assert variantes.ruta("mujer_web__Carpeta 1", "3") is None
        variantes.guardar("mujer_web__Carpeta 1", "3", b"img", "captura.PNG")
        f = variantes.ruta("mujer_web__Carpeta 1", "3")
        assert f and f.suffix == ".png" and f.read_bytes() == b"img"
        # En el volumen local, no en el Drive montado (ver el docstring del módulo).
        assert f.parent.parent.name == "variantes"
        assert variantes.tienen("mujer_web__Carpeta 1") == {"3"}
        # Sustituir con otra extensión no deja dos.
        variantes.guardar("mujer_web__Carpeta 1", "3", b"img2", "otra.jpg")
        assert variantes.ruta("mujer_web__Carpeta 1", "3").suffix == ".jpg"
        assert len(list(f.parent.iterdir())) == 1
        assert variantes.quitar("mujer_web__Carpeta 1", "3")
        assert variantes.ruta("mujer_web__Carpeta 1", "3") is None

    def test_rechaza_lo_que_no_es_imagen(self, tmp_path, monkeypatch):
        from src.nicho_ropa.services import variantes

        monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
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

    def test_si_bloquea_tambien_sin_fotos_manda_solo_las_instrucciones(self, monkeypatch):
        import src.tiktok_shop.api.gemini as gemini

        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        llamadas = []

        def falso(system_prompt, user_prompt, images=None, **kw):
            llamadas.append((len(system_prompt), images))
            if "Movimiento clip" in system_prompt:
                raise gemini.GeminiBlockedError("Gemini bloqueó la petición (4)")
            return {"colores": ["rosa", "verde"], "clips": ["Rosa y verde. Mira.", "Por detrás. Elige."]}

        monkeypatch.setattr(gemini, "generate_json", falso)
        salida = guionista.escribir(
            prompt=e["guion"], titulo="x", fotos=[Path("/tmp/a.jpg")], partes=2,
            caracteres_clip=119, segundos_clip=8, colores=True,
        )
        assert len(llamadas) == 3 and llamadas[2][1] is None
        assert llamadas[2][0] < llamadas[0][0]
        # El bloque de vídeo se monta con el prompt ENTERO: la voz y el
        # movimiento vuelven aunque a Gemini no se le mandaran.
        assert "Movimiento:" in salida["videos"][1] and "de espaldas" in salida["videos"][1]

    def test_solo_instrucciones_corta_en_la_voz(self):
        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        corto = guionista.solo_instrucciones(e["guion"])
        assert "«" in corto and "Voz femenina" not in corto and "Movimiento" not in corto
        assert guionista.solo_instrucciones("sin voz aquí") == "sin voz aquí"

    def test_los_leidos_de_la_ficha(self):
        from src.nicho_ropa.services import variantes

        assert variantes.leidos({}) == {"colores": [], "hex": {}}
        assert variantes.leidos({"variantes": {"colores": ["beige", ""], "hex": {"beige": "#d9cdb8", "x": ""}}}) == {
            "colores": ["beige"], "hex": {"beige": "#d9cdb8"},
        }


class TestFotosDeColorSubidas:
    """Las fotos de cada color las hace Flow (gratis) y las sube el operador:
    son las que se cortan. Gemini solo si se enciende a propósito."""

    def _monta(self, tmp_path, monkeypatch, fotos_colores, ia=True, video=False):
        import src.nicho_pov_bof.pipeline.video_editor as pov

        # Con las dos vías apagadas la edición no toca nada (es lo normal
        # desde que los colores los trae el vídeo), así que estos casos
        # encienden la de IA para poder probar la rama de las fotos.
        monkeypatch.setattr(colores, "RECOLOR_IA", ia)
        # El recolor sobre el vídeo se deja apagado salvo que el caso lo pida:
        # con él encendido no se llega a la rama de las fotos.
        monkeypatch.setattr(colores, "RECOLOR_VIDEO", video)
        work = tmp_path / "w"
        monkeypatch.setattr(pov, "_transcribir_voz", lambda *a, **k: _palabras(("rosa", 0.1), ("beige", 0.9), ("verde", 1.7)))
        monkeypatch.setattr(colores, "_run", lambda cmd, on_log: Path(cmd[-1]).write_bytes(b"jpg"))
        pagadas = []
        monkeypatch.setattr(recolor, "recolorear", lambda *a, **k: pagadas.append(1) or b"png")
        superpuesto = {}
        monkeypatch.setattr(colores, "_superponer", lambda clip, fotos, tiempos, destino, on_log: superpuesto.update(fotos=fotos))
        clip = tmp_path / "clip1.mp4"
        clip.write_bytes(b"")
        avisos = []
        salida = colores.aplicar(clip, ["rosa", "beige", "verde"], work, on_log=avisos.append, fotos_colores=fotos_colores)
        return salida, pagadas, superpuesto, avisos

    def test_con_todas_las_fotos_no_se_paga_nada(self, tmp_path, monkeypatch):
        fotos = {"rosa": tmp_path / "rosa.png", "Beige": tmp_path / "beige.png"}
        salida, pagadas, sup, _ = self._monta(tmp_path, monkeypatch, fotos)
        assert salida.name == "clip1_colores.mp4"
        assert not pagadas
        assert sup["fotos"] == [tmp_path / "rosa.png", tmp_path / "beige.png"]

    def test_sin_ia_el_color_sin_foto_se_salta_y_avisa(self, tmp_path, monkeypatch):
        salida, pagadas, sup, avisos = self._monta(
            tmp_path, monkeypatch, {"rosa": tmp_path / "rosa.png"}, ia=False, video=True,
        )
        assert not pagadas
        assert sup["fotos"] == [tmp_path / "rosa.png", None]
        assert any("sin foto para: beige" in a for a in avisos)

    def test_sin_ninguna_foto_el_clip_sale_tal_cual(self, tmp_path, monkeypatch):
        salida, pagadas, sup, _ = self._monta(tmp_path, monkeypatch, {}, ia=False, video=True)
        assert salida.name == "clip1.mp4" and not pagadas and not sup

    def test_con_ia_encendida_recolorea_lo_que_falte(self, tmp_path, monkeypatch):
        monkeypatch.setattr(colores, "RECOLOR_IA", True)
        _, pagadas, sup, _ = self._monta(tmp_path, monkeypatch, {"rosa": tmp_path / "rosa.png"})
        assert len(pagadas) == 1
        assert sup["fotos"][0] == tmp_path / "rosa.png" and sup["fotos"][1].name.startswith("color_beige")

    def test_guardar_y_listar_fotos_por_color(self, tmp_path, monkeypatch):
        from src.nicho_ropa.services import variantes

        monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
        variantes.guardar_color("mujer_web__C 1", "4", "Verde militar", b"img", "a.PNG")
        variantes.guardar_color("mujer_web__C 1", "4", "beige", b"img", "b.jpg")
        assert variantes.ruta_color("mujer_web__C 1", "4", "verde militar").name == "4__verde_militar.png"
        assert set(variantes.fotos_de_colores("mujer_web__C 1", "4", ["beige", "taupe", "verde militar"])) == {"beige", "verde militar"}
        assert variantes.colores_con_foto("mujer_web__C 1") == {"4": {"verde_militar", "beige"}}
        # La captura del selector (sin `__`) no cuenta como foto de color.
        variantes.guardar("mujer_web__C 1", "4", b"cap", "c.jpg")
        assert variantes.colores_con_foto("mujer_web__C 1") == {"4": {"verde_militar", "beige"}}
        assert variantes.quitar_color("mujer_web__C 1", "4", "beige")
        assert variantes.ruta_color("mujer_web__C 1", "4", "beige") is None

    def test_el_estilo_trae_la_plantilla_de_flow(self):
        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        # Ya no nombra el color: lo manda la foto de producto adjunta.
        assert "foto de producto que adjunto" in e["imagen_color"] and "<!--" not in e["imagen_color"]
        assert "{{" not in config.con_familia(e["imagen_color"], "Cárdigan largo")
        from src.api.schemas.nicho_ropa.models import EstiloMof10

        assert EstiloMof10(**e).imagen_color == e["imagen_color"]


class TestFotosDeColorDelZip:
    def _zip(self, tmp_path):
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Carpeta 7/Producto_3_Principal.jpeg", b"limpia3")
            zf.writestr("Carpeta 7/Producto_3_Ficha.png", b"ficha3")
            zf.writestr("Carpeta 7/Producto_3_Color_2.jpeg", b"c32")
            zf.writestr("Carpeta 7/Producto_3_Color_1.jpeg", b"c31")
            zf.writestr("Carpeta 7/Producto_3_Trasera.jpeg", b"tras")
            zf.writestr("Carpeta 7/Producto_4_Principal.jpeg", b"limpia4")
            zf.writestr("Carpeta 7/Producto_4_Ficha.png", b"ficha4")
        return buf.getvalue()

    def test_se_guardan_en_colores_y_no_rompen_el_emparejado(self, tmp_path):
        from src.nicho_pov_bof.services import productos_web as pov_web

        r = pov_web.importar_zip(self._zip(tmp_path), "Carpeta 7.zip", raiz=tmp_path)
        assert r["nuevos"] == ["3", "4"]
        carpeta = tmp_path / r["carpeta"]
        fotos = pov_web.fotos_color_de(carpeta, "3")
        assert [f.name for f in fotos] == ["3_1.jpeg", "3_2.jpeg"]
        assert fotos[0].read_bytes() == b"c31"
        assert pov_web.fotos_color_de(carpeta, "4") == []
        # En la carpeta de la prenda siguen solo la limpia y la ficha.
        assert sorted(f.name for f in carpeta.iterdir() if f.is_file()) == ["3(1).png", "3.jpeg", "4(1).png", "4.jpeg"]

    def test_resubir_el_zip_anade_los_colores_a_lo_ya_importado(self, tmp_path):
        from src.nicho_pov_bof.services import productos_web as pov_web

        pov_web.importar_zip(self._zip(tmp_path), "Carpeta 7.zip", raiz=tmp_path)
        carpeta = tmp_path / "Carpeta 7"
        for f in (carpeta / "colores").iterdir():
            f.unlink()
        r = pov_web.importar_zip(self._zip(tmp_path), "Carpeta 7.zip", raiz=tmp_path)
        assert r["iguales"] == ["3", "4"]
        assert len(pov_web.fotos_color_de(carpeta, "3")) == 2


class TestMiniaturasDeLaCaptura:
    def _captura(self, tmp_path, n=4):
        """Una captura falsa: fondo blanco y n tarjetas con borde gris en fila."""
        from PIL import Image, ImageDraw

        W, H = 1440, 3168
        im = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(im)
        colores = [(200, 180, 150), (90, 60, 45), (140, 130, 115), (110, 140, 100), (30, 30, 30)]
        for i in range(n):
            x = 54 + i * 315
            d.rectangle((x, 2244, x + 277, 2244 + 340), outline=(200, 200, 200), width=3)
            d.rectangle((x + 40, 2270, x + 237, 2470), fill=colores[i])
        f = tmp_path / "cap.jpg"
        im.save(f, "JPEG", quality=92)
        return f

    def test_detecta_la_fila_de_tarjetas(self, tmp_path):
        from src.nicho_ropa.services import variantes

        cajas = variantes.detectar_miniaturas(self._captura(tmp_path))
        assert len(cajas) == 4
        assert [c[0] for c in cajas] == sorted(c[0] for c in cajas)
        assert all(abs(c[1] - 2244) < 6 for c in cajas)

    def test_recorta_por_orden_y_solo_si_cuadra(self, tmp_path, monkeypatch):
        from PIL import Image

        from src.nicho_ropa.services import variantes

        monkeypatch.setenv("API_TEMP_ROOT", str(tmp_path))
        cap = self._captura(tmp_path)
        assert variantes.recortar_miniaturas(cap, ["beige", "marron", "taupe", "verde militar"], "c", "4") == ["beige", "marron", "taupe", "verde militar"]
        f = variantes.ruta_miniatura("c", "4", "verde militar")
        assert f and f.name == "4__ref__verde_militar.jpg"
        with Image.open(f) as im:
            r, g, b = im.resize((1, 1)).getpixel((0, 0))
        assert g > r and g > b  # el cuarto recorte es el verdoso
        assert variantes.miniaturas_de("c", "4", ["beige", "negro", "taupe"]) == ["beige", "taupe"]
        # Tres nombres para cuatro tarjetas: no se recorta nada.
        assert variantes.recortar_miniaturas(cap, ["a", "b", "c"], "c", "5") == []
        # Y los recortes no cuentan como fotos de color subidas ni como captura.
        assert variantes.colores_con_foto("c") == {}
        assert variantes.tienen("c") == set()


class TestRecolorEnVideo:
    def _frame(self, color_bgr, top_bgr=(250, 250, 250)):
        import numpy as np

        f = np.zeros((400, 200, 3), dtype=np.uint8)
        f[:, :] = (200, 200, 200)          # fondo gris claro
        f[60:150, 60:140] = top_bgr        # top blanco arriba
        f[160:380, 50:150] = color_bgr     # pantalón
        return f

    def test_aisla_un_rosa_y_no_un_gris(self):
        from src.nicho_ropa.pipeline import recolor_video as rv

        rosa = rv.color_prenda(self._frame((217, 208, 246)))   # BGR de #f6d0d9
        gris = rv.color_prenda(self._frame((150, 150, 150)))
        assert rv.aislable(rosa) and not rv.aislable(gris)

    def test_recolorea_el_pantalon_y_respeta_el_top(self):
        import numpy as np

        from src.nicho_ropa.pipeline import recolor_video as rv

        f = self._frame((217, 208, 246))
        origen = rv.color_prenda(f)
        out = rv.recolorear_frame(f, origen, rv.hex_a_lab("#1a1a1a"))
        assert out[270, 100].mean() < 80          # el pantalón, ahora oscuro
        assert out[100, 100].mean() > 240         # el top, intacto
        assert abs(int(out[30, 30].mean()) - 200) < 3  # el fondo, intacto

    def test_sin_hex_para_un_color_se_cae_a_las_fotos(self, tmp_path, monkeypatch):
        import src.nicho_pov_bof.pipeline.video_editor as pov

        monkeypatch.setattr(colores, "RECOLOR_VIDEO", True)
        monkeypatch.setattr(colores, "RECOLOR_IA", False)
        work = tmp_path / "w"
        monkeypatch.setattr(pov, "_transcribir_voz", lambda *a, **k: _palabras(("rosa", 0.0), ("verde", 0.8)))
        monkeypatch.setattr(colores, "_run", lambda cmd, on_log: Path(cmd[-1]).write_bytes(b"jpg"))
        sup = {}
        monkeypatch.setattr(colores, "_superponer", lambda clip, fotos, tiempos, destino, on_log: sup.update(fotos=fotos))
        clip = tmp_path / "clip1.mp4"
        clip.write_bytes(b"")
        avisos = []
        colores.aplicar(clip, ["rosa", "verde"], work, on_log=avisos.append, tonos={}, fotos_colores={"rosa": tmp_path / "rosa.png"})
        assert any("sin tono" in a for a in avisos)
        assert sup["fotos"] == [tmp_path / "rosa.png"]


class TestMinimoDeVariantes:
    """El formato vive de enseñar colores: una prenda de un solo color no
    vale, y la pantalla la filtra con el número que dice el estilo."""

    def test_el_estilo_pide_tres_colores(self):
        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        assert e["minimo_variantes"] == 3
        assert config.minimo_variantes("tienda_colores") == 3
        from src.api.schemas.nicho_ropa.models import EstiloMof10

        assert EstiloMof10(**e).minimo_variantes == 3

    def test_los_demas_formatos_no_piden_ninguno(self):
        for modo in ("espejo", "calle_dividido", "camara"):
            assert config.minimo_variantes(modo) == 0
            (e,) = config.prompts_mof10("mujer", False, modo)
            assert e["minimo_variantes"] == 0

    def test_el_importador_cuenta_los_colores_del_zip(self, tmp_path):
        import io
        import zipfile

        from src.nicho_pov_bof.services import productos_web as pov_web

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            # Producto 1: principal + 3 colores = 4 variantes (apto).
            zf.writestr("Carpeta 9/Producto_1_Principal.jpeg", b"a")
            zf.writestr("Carpeta 9/Producto_1_Ficha.png", b"b")
            for k in (1, 2, 3):
                zf.writestr(f"Carpeta 9/Producto_1_Color_{k}.jpeg", f"c{k}".encode())
            # Producto 2: solo la principal = 1 variante (no apto).
            zf.writestr("Carpeta 9/Producto_2_Principal.jpeg", b"d")
            zf.writestr("Carpeta 9/Producto_2_Ficha.png", b"e")
        r = pov_web.importar_zip(buf.getvalue(), "Carpeta 9.zip", raiz=tmp_path)
        carpeta = tmp_path / r["carpeta"]
        assert 1 + len(pov_web.fotos_color_de(carpeta, "1")) == 4
        assert 1 + len(pov_web.fotos_color_de(carpeta, "2")) == 1


class TestFamiliasDePrenda:
    """El formato vale para cualquier prenda, pero el gesto y los planos
    cambian: un pantalón se sube, a un jersey se le tira del bajo y un
    cárdigan se abre (medido en diez virales)."""

    @pytest.mark.parametrize(
        "titulo,familia",
        [
            ("STELLARSEEK Pantalón Wide Leg deportivo", "pantalon"),
            ("Falda midi plisada", "pantalon"),
            ("Jersey oversize de cuello alto", "punto"),
            ("Chaleco de punto con volantes", "punto"),
            ("Cárdigan largo de punto abierto", "abierta"),
            ("Chaqueta de pana", "abierta"),
            ("Sudadera larga con capucha y cremallera", "capucha"),
            ("Mono palabra de honor pierna ancha", "mono"),
            ("Vestido midi satinado", "mono"),
            ("Algo que no se sabe qué es", "pantalon"),
        ],
    )
    def test_familia_por_el_titulo(self, titulo, familia):
        assert config.familia_de(titulo) == familia

    def test_la_capucha_gana_a_la_sudadera(self):
        # "sudadera" es de punto y "capucha" de cremallera: manda la capucha.
        assert config.familia_de("Sudadera con capucha") == "capucha"
        assert config.familia_de("Sudadera básica") == "punto"

    def test_los_prompts_se_rellenan_enteros(self):
        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        for titulo in ("Pantalón wide leg", "Jersey de punto", "Cárdigan", "Sudadera con capucha", "Mono largo"):
            for campo in ("imagen", "guion", "video_omni", "video_omni2", "imagen_color", "imagen2"):
                t = config.con_familia(e[campo], titulo)
                sobran = [x for x in ("GESTO", "FINAL_GESTO", "DETALLE_1", "DETALLE_2", "DETALLE_3", "PRUEBA", "ZONAS", "POSE_IMAGEN", "MANOS_IMAGEN", "ROPA_BASE", "POSE_COLOR", "ESPALDA_IMAGEN", "CUERPO_IMAGEN") if "{{" + x + "}}" in t]
                assert not sobran, (titulo, campo, sobran)

    @pytest.mark.parametrize("titulo", ["Chaqueta de punto", "Vestido de encaje", "Sudadera con capucha"])
    def test_solo_el_pantalon_dice_pantalon(self, titulo):
        """Las imágenes de color, la de espaldas y los clips decían
        "pantalón" y "bolsillos traseros" para cualquier prenda."""
        (e,) = config.prompts_mof10("mujer", False, "tienda_colores")
        for campo in ("imagen_color", "imagen2", "video_omni", "video_omni2"):
            t = config.con_familia(e[campo], titulo).lower()
            assert "pantal" not in t and "bolsillos traseros" not in t, (titulo, campo)

    def test_cada_familia_dice_algo_distinto(self):
        gestos = {f["gesto"] for f in config.FAMILIAS_PRENDA.values()}
        assert len(gestos) == len(config.FAMILIAS_PRENDA)
        # Y el pantalón es el único que se sube.
        sube = [k for k, f in config.FAMILIAS_PRENDA.items() if "hacia arriba" in f["gesto"]]
        assert sube == ["pantalon"]

    def test_la_tabla_que_va_a_la_pantalla(self):
        from src.api.schemas.nicho_ropa.models import PromptsRopaResponse

        fams = config.familias_para_pantalla()
        assert set(fams) == set(config.FAMILIAS_PRENDA)
        assert all(f["label"] and f["zonas"] and f["pose_imagen"] for f in fams.values())
        # El esquema la deja pasar tal cual (Pydantic tira lo que no declara).
        assert PromptsRopaResponse(
            imagen="x", video_con_manos="x", video_sin_manos="x", familias=fams,
        ).familias["punto"]["gesto"]


class TestContadorDeCarpeta:
    def test_cuenta_las_prendas_con_colores_suficientes(self, tmp_path, monkeypatch):
        from src.nicho_pov_bof.services import productos_web as pov_web
        from src.nicho_ropa.services import prendas_web

        raiz = tmp_path / "mujer_web" / "Carpeta 5"
        (raiz / pov_web.SUBDIR_COLORES).mkdir(parents=True)
        # Producto 1: 3 fotos de color + la principal = 4 (apto).
        # Producto 2: 1 foto  = 2 colores (no apto). Producto 3: ninguna.
        for n in (1, 2, 3):
            (raiz / pov_web.SUBDIR_COLORES / f"1_{n}.jpg").write_bytes(b"x")
        (raiz / pov_web.SUBDIR_COLORES / "2_1.jpg").write_bytes(b"x")
        monkeypatch.setattr(prendas_web, "_dir_genero", lambda g: tmp_path / g)
        prendas_web._invalidar()
        slug = config.slug_web("mujer_web", "Carpeta 5")
        assert prendas_web.cuantas_con_colores(slug, 3) == 1
        assert prendas_web.cuantas_con_colores(slug, 2) == 2
        # Los modos que no piden colores no cuentan nada (ni leen el disco).
        assert prendas_web.cuantas_con_colores(slug, 0) == 0


class TestTextosPorLaCola:
    def test_el_modo_de_trabajo_existe_y_tiene_runner(self):
        from src.queue.models import JobMode, MODE_LABELS
        from src.queue.runners import _RUNNERS

        assert JobMode.NICHO_ROPA_TEXTOS in _RUNNERS
        assert MODE_LABELS[JobMode.NICHO_ROPA_TEXTOS]

    def test_el_runner_guarda_lo_leido(self, monkeypatch):
        from src.nicho_ropa.repos import product_repo
        from src.nicho_ropa.services import text_extractor
        from src.queue.models import Job, JobMode
        from src.queue.runners import run_nicho_ropa_textos

        monkeypatch.setattr(text_extractor, "extract_texts", lambda c, on_log=None: {"1": {"titulo": "X"}})
        guardado = {}
        monkeypatch.setattr(product_repo, "save_extracted_texts", lambda c, t: guardado.update(carpeta=c, textos=t))
        job = Job(mode=JobMode.NICHO_ROPA_TEXTOS, params={"carpeta": "mujer_web__Carpeta_1"})
        assert "1 prenda" in run_nicho_ropa_textos(job, lambda _m: None, lambda _p, _m: None)
        assert guardado["carpeta"] == "mujer_web__Carpeta_1"

    def test_sin_textos_falla_en_vez_de_guardar_vacio(self, monkeypatch):
        from src.nicho_ropa.services import text_extractor
        from src.queue.models import Job, JobMode
        from src.queue.runners import run_nicho_ropa_textos

        monkeypatch.setattr(text_extractor, "extract_texts", lambda c, on_log=None: {})
        job = Job(mode=JobMode.NICHO_ROPA_TEXTOS, params={"carpeta": "c"})
        with pytest.raises(RuntimeError, match="ningún texto"):
            run_nicho_ropa_textos(job, lambda _m: None, lambda _p, _m: None)
