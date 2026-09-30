"""Multimodo de Moda Mujer: formatos mudos elegidos producto a producto."""

from src.nicho_ropa import config
from src.nicho_ropa.repos import product_repo


class TestFormatos:
    def test_todos_los_formatos_tienen_sus_dos_prompts_y_son_mudos(self):
        for modo in config.modos_multimodo():
            estilos = config.prompts_mof10("mujer", False, modo)
            assert len(estilos) == 1, modo
            e = estilos[0]
            assert e["imagen"].strip() and e["guion"].strip(), modo
            assert e["voz"] is False, modo
            assert not config.modo_habla(modo), modo

    def test_la_vista_de_todos_no_tiene_prompts(self):
        assert config.prompts_mof10("mujer", False, config.MODO_MULTI) == []

    def test_los_de_chica_aleatoria_llevan_el_personaje_delante(self):
        e = config.prompts_mof10("mujer", False, "mm_espejo")[0]
        assert e["personaje"] is True
        assert e["imagen"].startswith("IMPORTANT — CHARACTER OVERRIDE")

    def test_solo_salen_en_su_modalidad(self):
        claves = {m["clave"] for m in config.modos_de("mujer", "multimodo")}
        assert claves == set(config.modos_multimodo())
        assert not claves & {m["clave"] for m in config.modos_de("mujer", "aleatorios")}


class TestTipo:
    def test_por_titulo(self):
        assert config.tipo_multimodo("Botas altas de piel") == "botas"
        assert config.tipo_multimodo("Bolso de hombro acolchado") == "bolso"
        assert config.tipo_multimodo("Zapatillas deportivas blancas") == "calzado"
        assert config.tipo_multimodo("Camiseta básica oversize") == "camiseta"
        assert config.tipo_multimodo("Gafas de sol retro") == "gafas"
        assert config.tipo_multimodo("Vestido midi de punto") == "ropa"

    def test_sin_titulo_manda_el_catalogo(self):
        assert config.tipo_multimodo("", "mujer_zapatos_web__Carpeta_3") == "calzado"
        assert config.tipo_multimodo("", "mujer_accesorios_web__Carpeta_1") == "bolso"


class TestCatalogos:
    def test_zapatos_y_accesorios_son_de_mujer_pero_no_de_ropa(self):
        assert config.sexo_de_carpeta("mujer_zapatos_web__Carpeta_1") == "mujer"
        assert config.catalogo_de_genero("mujer_zapatos_web") == "zapatos"
        assert config.catalogo_de_genero("mujer_accesorios_web") == "accesorios"
        assert config.catalogo_de_genero("mujer_web") == "web"
        assert config.catalogo_de_genero("hombre_tareas") == "tareas"
        assert config.es_carpeta_conocida("mujer_accesorios_web__Carpeta_2")


class TestVistaDeTodos:
    def test_saca_el_video_mas_reciente_de_cualquier_formato(self):
        prod = {"modos": {
            "mm_bolso_1": {"video_path": "/a.mp4", "video_listo_at": 10},
            "mm_espejo": {"video_path": "/b.mp4", "video_listo_at": 20},
            "espejo": {"video_path": "/c.mp4", "video_listo_at": 99},
        }}
        v = product_repo.video_de(prod, config.MODO_MULTI)
        assert v["video_path"] == "/b.mp4"
        assert v["formato"] == "mm_espejo"

    def test_el_progreso_va_junto(self):
        assert config.clave_progreso("mm_bolso_2") == config.MODO_MULTI
        assert config.clave_progreso(config.MODO_MULTI) == config.MODO_MULTI
        assert config.clave_progreso("espejo") == "espejo"


class TestRotuloVintage:
    """El rótulo otoñal de los Vintage lo pone el montaje, no la imagen."""

    def test_el_prompt_de_imagen_ya_no_pide_el_texto(self):
        for modo in ("mm_bolso_1", "mm_bolso_3", "mm_botas_2", "mm_botas_largas_2"):
            imagen = config.prompts_mof10(modo=modo)[0]["imagen"]
            assert "Añade directamente sobre la fotografía" not in imagen
            assert "Sin más texto" in imagen

    def test_frase_por_prenda_y_sin_grado(self):
        a = config.texto_de_modo("mm_bolso_1", "c/1")
        assert a["titulo"] and a["segundos"] == 0.0
        assert a == config.texto_de_modo("mm_bolso_1", "c/1")  # remontar no la cambia
        assert not config.lleva_grado("mm_bolso_1")
        assert config.lleva_grado("mm_espejo_escenas")

    def test_halloween_solo_en_su_ventana(self):
        import datetime as dt
        assert config.es_halloween(dt.date(2026, 10, 20))
        assert not config.es_halloween(dt.date(2026, 9, 27))
        assert not config.es_halloween(dt.date(2026, 11, 5))


class TestMusica:
    def test_cada_formato_trae_su_busqueda(self):
        for modo in config.modos_multimodo():
            if config.lleva_fish(modo):
                # Los de 20s hablan (voz de Fish): sin música que buscar.
                assert config.musica_de(modo, "c/1") == {}, modo
                continue
            m = config.musica_de(modo, "c/1")
            assert m["busqueda"] and m["estilo"], modo
            assert m["busqueda"] not in m["alternativas"]

    def test_estable_por_producto(self):
        assert config.musica_de("mm_bolso_1", "c/3") == config.musica_de("mm_bolso_1", "c/3")


class TestMovimientoSinTexto:
    def test_el_prompt_de_video_prohibe_el_texto(self):
        for modo in ("mm_bolso_1", "mm_botas_largas_2"):
            p = config.prompts_mof10(modo=modo)[0]
            video = p.get("guion") or p.get("video") or ""
            assert "se mantiene est" not in video
            assert "No aparece ningún texto" in video

    def test_todos_los_formatos_mudos_prohiben_texto(self):
        for modo in config.modos_multimodo():
            ps = config.prompts_mof10(modo=modo)
            assert ps, modo
            assert "sin ningún texto sobreimpreso" in ps[0]["guion"], modo

    def test_calzado_fija_los_pies_y_zapatos(self):
        espejo = config.prompts_mof10(modo="mm_zapatillas_espejo")[0]["guion"]
        assert "exactamente dos zapatillas" in espejo
        assert espejo.rstrip().endswith("el vídeo tampoco.")
        pov = config.prompts_mof10(modo="mm_zapatos_pov")[0]["guion"]
        assert "el pie descalzo sigue descalzo" in pov
        assert "exactamente dos" not in config.prompts_mof10(modo="mm_bolso_1")[0]["guion"]

    def test_los_bolsos_llevan_una_mano_que_da_movimiento(self):
        for modo in ("mm_bolso_1", "mm_bolso_2", "mm_bolso_3"):
            guion = config.prompts_mof10(modo=modo)[0]["guion"]
            assert "nunca pasa por delante de la cámara" in guion, modo
            assert guion.rstrip().endswith("el vídeo tampoco."), modo


class TestOrdenParaPublicar:
    def _v(self, formato, t, subido=False, t_sub=0):
        return {"formato": formato, "video_listo_at": t, "uploaded": subido, "uploaded_at": t_sub}

    def test_mezcla_tipos_y_formatos(self):
        vids = [self._v("mm_bolso_1", 1), self._v("mm_bolso_1", 2), self._v("mm_bolso_2", 3),
                self._v("mm_botas_2", 4), self._v("mm_botas_2", 5), self._v("mm_espejo", 6)]
        orden = [v["formato"] for v in config.orden_para_publicar(vids)]
        assert orden[:3] == ["mm_bolso_1", "mm_botas_2", "mm_espejo"]
        assert orden[3] == "mm_bolso_2"  # el segundo bolso ya no repite formato
        for a, b in zip(orden, orden[1:]):
            assert a != b

    def test_un_video_rehecho_conserva_su_puesto(self):
        viejo = {**self._v("mm_bolso_1", 999), "primer_listo_at": 1}
        otro = self._v("mm_bolso_1", 2)
        assert config.orden_para_publicar([otro, viejo])[0] is viejo

    def test_lo_subido_va_primero_y_no_se_mueve(self):
        vids = [self._v("mm_bolso_1", 1), self._v("mm_botas_2", 2, True, 50),
                self._v("mm_espejo", 3, True, 40)]
        orden = config.orden_para_publicar(vids)
        assert [v["formato"] for v in orden] == ["mm_espejo", "mm_botas_2", "mm_bolso_1"]


class TestRotuloEnZonaSegura:
    def test_centrado_en_la_franja_y_dentro_de_margenes(self, tmp_path):
        from PIL import Image

        from src.nicho_pov_bof import config as pov
        from src.nicho_ropa.pipeline import video_editor

        png = tmp_path / "t.png"
        Image.new("RGBA", (1000, 300)).save(png)
        x, y = video_editor._posicion_segura(png, 0.9)
        w, h = Image.open(png).size
        assert x >= int(1080 * pov.SAFE_X[0]) and x + w <= int(1080 * pov.SAFE_X[1])
        assert y >= int(1920 * pov.SAFE_Y[0]) and y + h <= int(1920 * pov.SAFE_Y[1])


class _RedisFalso:
    def __init__(self):
        self.datos = {}

    def is_available(self):
        return True

    def get_json(self, key):
        return self.datos.get(key)

    def set_json(self, key, value):
        self.datos[key] = value
        return True


class TestOrdenFijo:
    """Marcar un vídeo como subido no puede mover las tandas ya bajadas."""

    def _v(self, carpeta, producto, formato, t, subido=False, t_sub=0):
        return {"carpeta": carpeta, "producto": producto, "formato": formato,
                "video_listo_at": t, "uploaded": subido, "uploaded_at": t_sub}

    def test_marcar_subido_no_reordena_y_lo_nuevo_va_al_final(self, monkeypatch):
        falso = _RedisFalso()
        monkeypatch.setattr(product_repo, "get_nicho_ropa_redis", lambda: falso)
        vids = [self._v("a", str(i), f, i) for i, f in
                enumerate(["mm_bolso_1", "mm_botas_2", "mm_espejo", "mm_bolso_2"])]
        antes = [product_repo.clave_multimodo(v) for v in
                 product_repo.fijar_orden_multimodo(vids, "ana", config.orden_para_publicar)]

        vids[3]["uploaded"], vids[3]["uploaded_at"] = True, 99
        vids.append(self._v("b", "1", "mm_espejo", 50))
        despues = [product_repo.clave_multimodo(v) for v in
                   product_repo.fijar_orden_multimodo(vids, "ana", config.orden_para_publicar)]
        assert despues[:4] == antes
        assert despues[4] == "b|1"

    def test_un_video_que_desaparece_no_ocupa_sitio(self, monkeypatch):
        falso = _RedisFalso()
        monkeypatch.setattr(product_repo, "get_nicho_ropa_redis", lambda: falso)
        vids = [self._v("a", str(i), "mm_espejo", i) for i in range(3)]
        product_repo.fijar_orden_multimodo(vids, "ana", config.orden_para_publicar)
        quedan = product_repo.fijar_orden_multimodo(
            [vids[0], vids[2]], "ana", config.orden_para_publicar)
        assert [v["producto"] for v in quedan] == ["0", "2"]


class _RedisDocs(_RedisFalso):
    def set_nx(self, key, value, ttl_s):
        return True

    def delete(self, key):
        return True

    def mget_json(self, keys):
        return [self.datos.get(k) for k in keys]


class TestRehacer:
    def test_el_video_nuevo_quita_el_rehacer_y_queda_rehecho(self, monkeypatch):
        falso = _RedisDocs()
        monkeypatch.setattr(product_repo, "get_nicho_ropa_redis", lambda: falso)
        c = "mujer_web__Carpeta_3"
        product_repo.guardar_video(c, "3", "mm_espejo", "/v1.mp4", 1, "ana")
        product_repo.update_personal(c, "3", "ana", rehacer=True, rehacer_nota="móvil en el aire")
        v = product_repo.videos_multimodo([c], "ana")[0]
        assert v["rehacer"] and v["rehacer_nota"] == "móvil en el aire" and not v["rehecho"]

        product_repo.guardar_video(c, "3", "mm_espejo", "/v2.mp4", 2, "ana")
        v = product_repo.videos_multimodo([c], "ana")[0]
        assert not v["rehacer"] and v["rehecho"]
        assert v["video_path"] == "/v2.mp4" and v["primer_listo_at"] == 1


class TestSinStock:
    def test_es_del_producto_y_se_ve_en_las_tandas_de_todos(self, monkeypatch):
        """Como en el POV BOF: va al documento común, así que lo ve cualquier
        usuario, y el vídeo sigue en la lista (no se borra ni se mueve)."""
        falso = _RedisDocs()
        monkeypatch.setattr(product_repo, "get_nicho_ropa_redis", lambda: falso)
        c = "mujer_web__Carpeta_3"
        product_repo.guardar_video(c, "3", "mm_espejo", "/v1.mp4", 1, "ana")
        product_repo.guardar_video(c, "4", "mm_espejo", "/v2.mp4", 2, "ana")
        product_repo.update_product(c, "3", sin_stock=True)
        vs = {v["producto"]: v for v in product_repo.videos_multimodo([c], "ana")}
        assert vs["3"]["sin_stock"] and not vs["4"]["sin_stock"]
        assert vs["3"]["video_path"] == "/v1.mp4"
        product_repo.update_product(c, "3", sin_stock=False)
        assert not product_repo.videos_multimodo([c], "ana")[0]["sin_stock"]


class TestFlechaOpcional:
    def test_se_pone_solo_si_se_pide_y_mas_corta(self, monkeypatch, tmp_path):
        from src.nicho_ropa.pipeline import video_editor as ve

        puestas: list = []
        monkeypatch.setattr(ve, "_flecha", lambda s, log, sem="", seg=ve.FLECHA_SEGUNDOS: puestas.append(seg))
        monkeypatch.setattr(ve, "_limpiar", lambda *a, **k: None)
        v = tmp_path / "v.mp4"
        ve._rematar(v, "mm_espejo", "c/1", lambda *_: None)
        assert puestas == []  # el multimodo no la trae
        ve._rematar(v, "mm_espejo", "c/1", lambda *_: None, flecha=True)
        assert puestas == [ve.FLECHA_OPCIONAL_SEGUNDOS]
        # Y se puede quitar en un formato que sí la lleva.
        ve._rematar(v, "calle_dividido", "c/1", lambda *_: None, flecha=False)
        assert puestas == [ve.FLECHA_OPCIONAL_SEGUNDOS]
        assert ve.pone_flecha("mm_espejo", None) is False
        assert ve.pone_flecha("calle_dividido", None) is True

    def test_queda_apuntado_en_el_video_para_comparar(self, monkeypatch):
        falso = _RedisDocs()
        monkeypatch.setattr(product_repo, "get_nicho_ropa_redis", lambda: falso)
        c = "mujer_web__Carpeta_3"
        product_repo.guardar_video(c, "3", "mm_espejo", "/v1.mp4", 1, "ana", flecha=True)
        product_repo.guardar_video(c, "4", "mm_bolso_1", "/v2.mp4", 2, "ana", flecha=False)
        vs = {v["producto"]: v for v in product_repo.videos_multimodo([c], "ana")}
        assert vs["3"]["flecha"] is True and vs["4"]["flecha"] is False
