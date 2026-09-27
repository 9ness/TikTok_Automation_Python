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
