"""Buscador de aprendizajes y secciones de guía (`aprendizajes`, `guia_seccion`).

Sin red ni IA: el cuaderno y las guías son ficheros de prueba, salvo el test
que recorre las guías reales para comprobar que se trocean bien.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp")

from src.agente_mcp import buscador, config  # noqa: E402

from .test_mcp import _rpc  # noqa: E402

CUADERNO = """# Learnings

## 2026
- 2026-11-08 · Omni copia la estrella de Gemini al clip → zoom del 14 % abajo.
- 2026-11-06 · vídeos con bandas negras dentro de un MP4 1080x1920 → cropdetect antes del semáforo.
- 2026-10-27 · Mi 8: subir el volumen despierta la casa → nunca VOLUME_UP.
- 2026-10-20 · MiniMax devolvía 80 caracteres de más → recortar.
- [2026-09-01] carruseles: la música es la del viral.
texto suelto sin fecha
- sin fecha tampoco
"""


@pytest.fixture
def cuaderno(tmp_path, monkeypatch):
    p = tmp_path / "learnings.md"
    p.write_text(CUADERNO, encoding="utf-8")
    monkeypatch.setenv("APRENDIZAJES_MD", str(p))
    return p


@pytest.fixture
def guias(tmp_path):
    d = tmp_path / "guias"
    (d / "comun").mkdir(parents=True)
    (d / "mis-tandas.md").write_text(
        "Entrada antes del primer título.\n\n# Mis tandas\nLo montado, de diez en diez.\n\n"
        "## El semáforo antes de subir\nVerde, ámbar o rojo. Sin semáforo no se descarga.\n\n"
        "```bash\n# esto es un comentario, no un título\ncurl x\n```\n\n"
        "## Carruseles\nLos carruseles llevan la música del viral.\n", encoding="utf-8")
    (d / "comun" / "plataformas.md").write_text(
        "# Plataformas\n\n### Veo — clips mudos\nSolo vídeo, mudo, 1 crédito.\n\n"
        "### Omni\nHablados. Trae la estrella de Gemini abajo a la derecha.\n", encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# Palabras
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tema,esperado", [
    ("Carruseles con música", ["carrusel", "musica"]),
    ("el semáforo de la tanda", ["semaforo", "tanda"]),
    ("Mi 8", ["mi", "8"]),
    ("de la y", []),
    ("niños", ["niño"]),
])
def test_palabras_sin_acentos_sin_vacias_y_en_singular(tema, esperado):
    assert buscador.palabras(tema) == esperado


def test_cortas_y_numeros_solo_casan_enteros():
    # «mi» no es «minimax» y «8» no es «80» ni «1080».
    assert buscador._puntos("minimax devolvia 80 caracteres en 1080", ["mi", "8"]) == (0, 0)
    assert buscador._puntos("el mi 8 de noche", ["mi", "8"]) == (2, 2)
    # Las largas casan por el principio: «omni» encuentra «omniflash».
    assert buscador._puntos("omniflash descartado", ["omni"]) == (1, 1)
    assert buscador._puntos("komni", ["omni"]) == (0, 0)


# ---------------------------------------------------------------------------
# Aprendizajes
# ---------------------------------------------------------------------------
def test_lee_solo_lineas_con_fecha(cuaderno):
    e = buscador.leer_aprendizajes()
    assert [x.fecha for x in e] == ["2026-11-08", "2026-11-06", "2026-10-27", "2026-10-20", "2026-09-01"]
    assert e[-1].texto.startswith("carruseles")


def test_sin_cuaderno_lista_vacia(tmp_path, monkeypatch):
    monkeypatch.setenv("APRENDIZAJES_MD", str(tmp_path / "no_esta.md"))
    assert buscador.leer_aprendizajes() == []


def test_busca_aprendizajes(cuaderno):
    e = buscador.leer_aprendizajes()
    assert [x["fecha"] for x in buscador.buscar_aprendizajes("bandas negras", e)] == ["2026-11-06"]
    # Con dos palabras, una sola suelta no vale («estrella» sí, «puzle» no).
    assert buscador.buscar_aprendizajes("estrella puzle", e) == []
    # «Mi 8» no trae el de MiniMax con 80.
    assert [x["fecha"] for x in buscador.buscar_aprendizajes("Mi 8", e)] == ["2026-10-27"]
    assert [x["fecha"] for x in buscador.buscar_aprendizajes("carrusel", e)] == ["2026-09-01"]
    assert buscador.buscar_aprendizajes("la de", e) == []


def test_lo_mas_reciente_primero_y_recortado():
    e = [buscador.Aprendizaje("2026-01-01", "omni viejo"), buscador.Aprendizaje("2026-05-01", "omni " + "x" * 600)]
    r = buscador.buscar_aprendizajes("omni", e, maximo=5)
    assert [x["fecha"] for x in r] == ["2026-05-01", "2026-01-01"]
    assert r[0]["texto"].endswith("…") and len(r[0]["texto"]) <= 421
    assert len(buscador.buscar_aprendizajes("omni", e, maximo=1)) == 1


# ---------------------------------------------------------------------------
# Guías por secciones
# ---------------------------------------------------------------------------
def test_trocea_por_titulos_sin_confundir_el_codigo(guias):
    secs = buscador.secciones(guias)
    assert [(s.guia, s.titulo) for s in secs] == [
        ("comun/plataformas.md", "Plataformas"),
        ("comun/plataformas.md", "Veo — clips mudos"),
        ("comun/plataformas.md", "Omni"),
        ("mis-tandas.md", "(inicio)"),
        ("mis-tandas.md", "Mis tandas"),
        ("mis-tandas.md", "El semáforo antes de subir"),
        ("mis-tandas.md", "Carruseles"),
    ]
    semaforo = secs[5]
    assert "esto es un comentario" in semaforo.texto and semaforo.texto.startswith("## El semáforo")


def test_busca_en_guias_y_lee_la_seccion(guias):
    secs = buscador.secciones(guias)
    r = buscador.buscar_guias("semáforo", secs)
    assert r[0]["guia"] == "mis-tandas.md" and r[0]["seccion"] == "El semáforo antes de subir"
    assert r[0]["letras"] > 20 and "semáforo" in r[0]["extracto"].lower()
    assert buscador.buscar_guias("estrella gemini", secs)[0]["seccion"] == "Omni"

    # Título por trozo y sin acentos; guía con o sin .md y sin «comun/».
    assert buscador.leer_seccion("mis-tandas", "semaforo", secs).titulo == "El semáforo antes de subir"
    assert buscador.leer_seccion("plataformas", "omni", secs).guia == "comun/plataformas.md"
    assert buscador.leer_seccion("comun/plataformas.md", "Veo — clips mudos", secs)
    assert buscador.leer_seccion("mis-tandas.md", "no existe", secs) is None
    assert buscador.leer_seccion("mis-tandas.md", "", secs) is None
    assert [x["seccion"] for x in buscador.indice("plataformas", secs)] == ["Plataformas", "Veo — clips mudos", "Omni"]
    assert buscador.indice("nada", secs) == []


def test_las_guias_reales_se_trocean_enteras():
    """Nada se pierde al trocear: cada guía sale y ninguna sección queda vacía."""
    secs = buscador.secciones()
    ficheros = {p.relative_to(config.GUIAS_DIR).as_posix() for p in config.GUIAS_DIR.rglob("*.md")}
    assert {s.guia for s in secs} == ficheros
    assert all(s.texto.strip() for s in secs)
    # Para eso está: una sección es mucho más corta que su guía.
    total = sum(len(s.texto) for s in secs)
    assert total / len(secs) < 4000


# ---------------------------------------------------------------------------
# Quién ve el cuaderno
# ---------------------------------------------------------------------------
def test_quien_ve_los_aprendizajes(monkeypatch):
    monkeypatch.delenv("MCP_APRENDIZAJES_USUARIOS", raising=False)
    assert buscador.ve_aprendizajes("ness") and buscador.ve_aprendizajes("ana")
    assert not buscador.ve_aprendizajes("mauro")
    monkeypatch.setenv("MCP_APRENDIZAJES_USUARIOS", "mauro")
    assert buscador.ve_aprendizajes("mauro") and not buscador.ve_aprendizajes("ana")
    assert buscador.ve_aprendizajes("ness")  # el admin, siempre
    monkeypatch.setenv("MCP_APRENDIZAJES_USUARIOS", "")
    assert not buscador.ve_aprendizajes("ana")


# ---------------------------------------------------------------------------
# Las dos herramientas, por el protocolo
# ---------------------------------------------------------------------------
@pytest.fixture
def usuarios(monkeypatch):
    from src.api import users

    monkeypatch.setattr(users, "existe", lambda u: u in {"ness", "ana", "mauro"})
    monkeypatch.delenv("MCP_APRENDIZAJES_USUARIOS", raising=False)


def _llamar(client, usuario, nombre, **args):
    r = _rpc(client, f"/api/mcp/{config.token_de(usuario)}", "tools/call", {"name": nombre, "arguments": args})
    return r, r["content"][0]["text"]


def test_herramienta_aprendizajes(app_client, usuarios, cuaderno):
    r, texto = _llamar(app_client, "ness", "aprendizajes", tema="bandas negras")
    assert not r.get("isError")
    d = json.loads(texto)
    assert [x["fecha"] for x in d["aprendizajes"]] == ["2026-11-06"]
    assert d["guias"] and {"guia", "seccion", "letras", "extracto"} <= set(d["guias"][0])

    # Mauro (usuario de fuera) busca en las guías pero no ve el cuaderno.
    r, texto = _llamar(app_client, "mauro", "aprendizajes", tema="bandas negras")
    d = json.loads(texto)
    assert "aprendizajes" not in d and d["guias"]

    r, texto = _llamar(app_client, "ness", "aprendizajes", tema="de la")
    assert r["isError"] and "tema" in texto

    r, texto = _llamar(app_client, "ness", "aprendizajes", tema="zzzqqq")
    assert "Nada con esas palabras" in json.loads(texto)["aviso"]


def test_aprendizajes_sin_cuaderno_avisa_y_sigue_con_las_guias(app_client, usuarios, tmp_path, monkeypatch):
    monkeypatch.setenv("APRENDIZAJES_MD", str(tmp_path / "no_esta.md"))
    r, texto = _llamar(app_client, "ness", "aprendizajes", tema="semáforo")
    d = json.loads(texto)
    assert not r.get("isError") and d["aprendizajes"] == [] and d["guias"]
    assert "no está en este servidor" in d["aviso"]


def test_herramienta_guia_seccion(app_client, usuarios):
    r, texto = _llamar(app_client, "ana", "guia_seccion", guia="mis-tandas")
    indice = json.loads(texto)["secciones"]
    assert len(indice) > 3 and all(x["letras"] > 0 for x in indice)

    titulo = indice[1]["seccion"]
    r, texto = _llamar(app_client, "ana", "guia_seccion", guia="mis-tandas.md", seccion=titulo)
    assert not r.get("isError") and texto.startswith(f"<!-- mis-tandas.md › {titulo} -->")
    assert len(texto) < 20000

    r, texto = _llamar(app_client, "ana", "guia_seccion", guia="mis-tandas", seccion="esto no existe")
    assert r["isError"] and "Secciones:" in texto
    r, texto = _llamar(app_client, "ana", "guia_seccion", guia="nada")
    assert r["isError"] and "No hay guía" in texto
