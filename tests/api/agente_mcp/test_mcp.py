"""El MCP para agentes: token, guías, protocolo y el plan de un producto.

No sale a la red ni toca Drive: el plan se prueba con una API falsa y el
protocolo con las herramientas que no leen nada de fuera (guía y menús).
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("mcp")

from src.agente_mcp import archivos, config, menus  # noqa: E402
from src.agente_mcp.interno import ErrorApp  # noqa: E402

H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def usuarios(monkeypatch):
    from src.api import users

    monkeypatch.setattr(users, "existe", lambda u: u in {"ness", "ana"})


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------
def test_token_vale_para_su_usuario_y_no_se_puede_cambiar(usuarios, monkeypatch):
    monkeypatch.setenv("AUTH_COOKIE_KEY", "clave")
    t = config.token_de("ness")
    assert config.usuario_de_token(t) == "ness"
    # Cambiar el usuario delante de la firma no cuela.
    assert config.usuario_de_token("ana." + t.split(".", 1)[1]) is None
    assert config.usuario_de_token("ness.malo") is None
    assert config.usuario_de_token("") is None


def test_cambiar_la_sal_revoca_todos(usuarios, monkeypatch):
    monkeypatch.setenv("AUTH_COOKIE_KEY", "clave")
    t = config.token_de("ness")
    monkeypatch.setenv("MCP_TOKEN_SALT", "2")
    assert config.usuario_de_token(t) is None


# ---------------------------------------------------------------------------
# Nombres aproximados → exactos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pedido,esperado", [
    ("Carpeta_24", "Carpeta_24"),
    ("carpeta 24", "Carpeta_24"),
    ("24", "Carpeta_24"),
    ("inventario", "inventario_general"),
])
def test_elegir_casa_nombres_aproximados(pedido, esperado):
    ops = ["Carpeta_2", "Carpeta_24", "inventario_general", "mis_productos"]
    assert menus._elegir(pedido, ops, "x") == esperado


def test_elegir_dice_las_opciones_si_no_encuentra():
    with pytest.raises(ErrorApp, match="Carpeta_1"):
        menus._elegir("carpeta 99", ["Carpeta_1"], "la carpeta")


# ---------------------------------------------------------------------------
# Ficheros
# ---------------------------------------------------------------------------
def test_la_bandeja_no_deja_salirse(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTE_BANDEJA_DIR", str(tmp_path))
    with pytest.raises(ErrorApp):
        archivos.ruta_en_bandeja("ness", "../../etc/passwd")
    assert archivos.ruta_en_bandeja("ness", "a/b.png") == tmp_path / "ness" / "a" / "b.png"


def test_url_interna_rechazada():
    with pytest.raises(ErrorApp):
        archivos._no_interna("http://127.0.0.1:8000/api/health")


# ---------------------------------------------------------------------------
# El plan de un producto (POV BOF Largo) con una API falsa
# ---------------------------------------------------------------------------
class ApiFalsa:
    def __init__(self, respuestas: dict[str, dict]):
        self.respuestas = respuestas

    async def get(self, ruta, **params):
        return self.respuestas[ruta]


def test_plan_largo_pide_un_clip_por_hueco_desde_la_misma_imagen():
    api = ApiFalsa({
        f"{menus.LARGO}/productos": {"items": [{
            "producto": "3", "titulo": "Cama\npara perros", "guion": "…",
            "clips_necesarios": 3, "clip_s": 8, "product_url": "https://x",
        }]},
        f"{menus.POV}/prompts": {"imagen": "PROMPT IMAGEN", "video": "PROMPT VIDEO"},
    })
    c = menus.Ctx(menus.MENUS["pov_bof_largo"], api, "inventario_general", "Carpeta_24")
    plan = asyncio.run(menus.plan(c, "3"))
    assert plan["producto"]["titulo"] == "Cama para perros"
    assert [i["prompt"] for i in plan["imagenes"]] == ["PROMPT IMAGEN"]
    assert [cl["clip"] for cl in plan["clips"]] == [1, 2, 3]
    assert all(cl["imagen"] == "imagen_1.png" and not cl["habla"] for cl in plan["clips"])
    # Clip de 8 s y mudo: valen las tres plataformas.
    assert set(plan["clips"][0]["plataformas"]) == {menus.FLOW, menus.GENAIPRO, menus.MAGNIFIC}


def test_plataformas_si_habla_solo_flow():
    assert menus._plataformas(True, False, 8) == [menus.FLOW]
    assert menus._plataformas(False, True, 8) == [menus.FLOW]  # ingredientes
    assert menus.GENAIPRO not in menus._plataformas(False, False, 10)  # GenAI Pro llega a 8 s


# ---------------------------------------------------------------------------
# Protocolo + rutas HTTP
# ---------------------------------------------------------------------------
def _rpc(client, url, method, params=None):
    r = client.post(url, headers=H, json={"jsonrpc": "2.0", "id": 1, "method": method,
                                          "params": params or {}})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_protocolo_mcp(app_client, usuarios):
    url = f"/api/mcp/{config.token_de('ness')}"
    init = _rpc(app_client, url, "initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"}})
    assert init["serverInfo"]["name"] == "tiktok-shop-ai-pro"

    nombres = {t["name"] for t in _rpc(app_client, url, "tools/list")["tools"]}
    assert {"guia", "carpetas", "plan_producto", "subir_clip", "ver"} <= nombres

    r = _rpc(app_client, url, "tools/call", {"name": "guia", "arguments": {"menu": "pov_bof_largo"}})
    assert not r.get("isError") and "POV BOF Largo" in r["content"][0]["text"]

    r = _rpc(app_client, url, "tools/call", {"name": "menus_disponibles", "arguments": {}})
    assert "moda_mujer" in {m["menu"] for m in json.loads(r["content"][0]["text"])}

    # Los errores le llegan al agente con su mensaje, no «Error executing tool».
    r = _rpc(app_client, url, "tools/call", {"name": "guia", "arguments": {"menu": "nada"}})
    assert r["isError"] and "Menú desconocido" in r["content"][0]["text"]


def test_token_malo_401(app_client, usuarios):
    r = app_client.post("/api/mcp/ness.malo", headers=H, json={})
    assert r.status_code == 401
    assert app_client.get("/api/mcp/ness.malo/archivo", params={"b": "x"}).status_code == 401


def test_guias_publicas_y_sin_salirse(app_client):
    r = app_client.get("/api/v1/agente/guias/comun/app.md")
    assert r.status_code == 200 and "text/markdown" in r.headers["content-type"]
    assert app_client.get("/api/v1/agente/guias/../config.py").status_code == 404


def test_todas_las_guias_del_menu_existen():
    for m in menus.MENUS.values():
        assert (config.GUIAS_DIR / f"{m.guia}.md").is_file(), m.guia
