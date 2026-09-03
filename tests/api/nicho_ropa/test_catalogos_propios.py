"""Los catálogos propios del Nicho Ropa (mujer/hombre × muestras/tareas).

Se montan como un GÉNERO más de los del ZIP (`hombre_tareas__Tareas 1`), y ahí
está el riesgo: el resto del nicho pregunta por el slug en varios sitios y
basta con que uno solo mire únicamente los géneros de la web para que la
carpeta se cree, salga en el selector y al abrirla conteste "Carpeta
desconocida". Pasó al estrenarlos.
"""

from __future__ import annotations

import pytest

from src.nicho_ropa import config


class TestSlugsDelOperador:
    @pytest.mark.parametrize("genero", sorted(config.GENEROS_OPERADOR))
    def test_su_carpeta_es_conocida(self, genero):
        """La puerta que se dejó cerrada la primera vez."""
        assert config.es_carpeta_conocida(config.slug_web(genero, "Tareas 1"))

    @pytest.mark.parametrize("genero", sorted(config.GENEROS_OPERADOR))
    def test_tiene_etiqueta_propia(self, genero):
        etiqueta = config.carpeta_label(config.slug_web(genero, "Muestras 2"))
        assert genero not in etiqueta       # se traduce, no se enseña el slug
        assert "Muestras 2" in etiqueta

    def test_las_del_zip_y_las_inventadas_siguen_igual(self):
        assert config.es_carpeta_conocida("mujer_web__Carpeta 3")
        assert config.es_carpeta_conocida("bikinis")
        assert not config.es_carpeta_conocida("loquesea__x")
        assert not config.es_carpeta_conocida("hombre_tareas__")

    def test_el_genero_lleva_el_sexo_dentro(self):
        """De esto depende que el prompt salga en masculino o femenino."""
        for genero in config.GENEROS_OPERADOR:
            assert genero.startswith(("mujer", "hombre"))


class TestPlazosEnElPrompt:
    """El prompt no puede prometer plazos por defecto.

    En este nicho la voz la pone el propio vídeo (la persona habla), así que
    lo que diga el ejemplo es lo que dirá el clip. Si promete financiación y
    la prenda no la tiene, no hay arreglo posterior: hay que generar el vídeo
    otra vez. Por eso el interruptor va apagado.
    """

    def _prompts(self, plazos: bool):
        from fastapi.testclient import TestClient
        from src.api.main import app

        r = TestClient(app).get(
            "/api/v1/nicho-ropa/prompts",
            params={"carpeta": "mujer_web__Carpeta 1", **({"plazos": 1} if plazos else {})},
        )
        assert r.status_code == 200, r.text
        return r.json()

    def test_por_defecto_no_los_menciona(self):
        datos = self._prompts(False)
        assert "plazos" not in datos["video_espejo"].lower()
        for estilo in datos["mof10"]:
            assert "plazos" not in estilo["guion"].lower()

    def test_con_el_interruptor_si(self):
        datos = self._prompts(True)
        assert "plazos" in datos["video_espejo"].lower()

    def test_no_se_escapa_ningun_marcador(self):
        for plazos in (True, False):
            datos = self._prompts(plazos)
            assert "{{" not in datos["video_espejo"]
            for estilo in datos["mof10"]:
                assert "{{" not in estilo["guion"] and "{{" not in estilo["imagen"]


class TestAltaDeUnaPrenda:
    """El recorrido entero: subirla, verla y pedir su prompt."""

    @pytest.fixture(autouse=True)
    def raiz_temporal(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "mis_prendas_dir", lambda: tmp_path)
        from src.nicho_ropa.services import prendas_web

        prendas_web._invalidar()
        return tmp_path

    def _cliente(self):
        from fastapi.testclient import TestClient
        from src.api.main import app

        return TestClient(app)

    def test_se_sube_y_luego_se_puede_abrir(self, raiz_temporal):
        c = self._cliente()
        alta = c.post(
            "/api/v1/nicho-ropa/mis-prendas?genero=hombre_tareas",
            files={
                "foto_limpia": ("a.jpg", b"limpia", "image/jpeg"),
                "foto_ficha": ("b.jpg", b"ficha", "image/jpeg"),
            },
        )
        assert alta.status_code == 200, alta.text
        slug = alta.json()["slug"]
        assert slug == "hombre_tareas__Tareas 1"
        # Y la carpeta se abre: esto es lo que devolvía 400.
        listado = c.get("/api/v1/nicho-ropa/prendas", params={"carpeta": slug})
        assert listado.status_code == 200, listado.text
        assert [p["producto"] for p in listado.json()["items"]] == ["1"]

    def test_el_prompt_sale_en_el_sexo_del_catalogo(self, raiz_temporal):
        c = self._cliente()
        for genero, sexo in (("hombre_tareas", "hombre"), ("mujer_muestras", "mujer")):
            c.post(
                f"/api/v1/nicho-ropa/mis-prendas?genero={genero}",
                files={"foto_limpia": ("a.jpg", b"limpia", "image/jpeg")},
            )
            slug = config.slug_web(
                genero, "Tareas 1" if genero.endswith("tareas") else "Muestras 1",
            )
            r = c.get("/api/v1/nicho-ropa/prompts", params={"carpeta": slug})
            assert r.status_code == 200, r.text
            assert r.json()["sexo"] == sexo

    def test_no_se_puede_subir_a_un_genero_del_zip(self):
        r = self._cliente().post(
            "/api/v1/nicho-ropa/mis-prendas?genero=mujer_web",
            files={"foto_limpia": ("a.jpg", b"limpia", "image/jpeg")},
        )
        assert r.status_code == 400, r.text

    def test_la_foto_se_puede_ver(self, raiz_temporal):
        """La miniatura salía rota: el endpoint validaba el id con el patrón
        de Drive y estas fotos llevan la RUTA como id, igual que las del ZIP."""
        c = self._cliente()
        alta = c.post(
            "/api/v1/nicho-ropa/mis-prendas?genero=mujer_muestras",
            files={"foto_limpia": ("a.jpg", b"\xff\xd8\xffdata", "image/jpeg")},
        ).json()
        listado = c.get(
            "/api/v1/nicho-ropa/prendas", params={"carpeta": alta["slug"]},
        ).json()
        foto = listado["items"][0]["clean_photo_id"]
        assert foto.startswith("/")          # es una ruta, no un ID de Google
        r = c.get("/api/v1/nicho-ropa/foto", params={"file_id": foto})
        assert r.status_code == 200, r.text
        # Y NO se cachea: la ruta se reutiliza al borrar y volver a subir.
        assert "no-cache" in r.headers.get("cache-control", "")

    def test_la_foto_limpia_se_descarga(self, raiz_temporal):
        c = self._cliente()
        alta = c.post(
            "/api/v1/nicho-ropa/mis-prendas?genero=mujer_muestras",
            files={"foto_limpia": ("a.jpg", b"\xff\xd8\xffdata", "image/jpeg")},
        ).json()
        r = c.get(
            "/api/v1/nicho-ropa/foto-limpia",
            params={"producto": "1", "carpeta": alta["slug"]},
        )
        assert r.status_code == 200, r.text

    def test_lo_de_mujer_no_aparece_en_hombre(self, raiz_temporal):
        c = self._cliente()
        c.post(
            "/api/v1/nicho-ropa/mis-prendas?genero=mujer_muestras",
            files={"foto_limpia": ("a.jpg", b"limpia", "image/jpeg")},
        )
        vacia = c.get(
            "/api/v1/nicho-ropa/prendas",
            params={"carpeta": "hombre_muestras__Muestras 1"},
        )
        assert vacia.status_code == 200, vacia.text
        assert vacia.json()["items"] == []
