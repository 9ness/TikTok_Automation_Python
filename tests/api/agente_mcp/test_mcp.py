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


def test_plan_largo_pide_una_imagen_por_clip_segun_lo_que_dice_la_voz():
    api = ApiFalsa({
        f"{menus.LARGO}/productos": {"items": [{
            "producto": "3", "titulo": "Cama\npara perros",
            "guion": "Tu perro duerme mal. Esta cama es mullida y lavable. Ve al carrito naranja.",
            "clips_necesarios": 3, "clip_s": 8, "product_url": "https://x",
        }]},
        f"{menus.POV}/prompts": {"imagen": "PROMPT IMAGEN", "video": "PROMPT VIDEO"},
    })
    c = menus.Ctx(menus.MENUS["pov_bof_largo"], api, "inventario_general", "Carpeta_24")
    plan = asyncio.run(menus.plan(c, "3"))
    assert plan["producto"]["titulo"] == "Cama para perros"
    assert [i["prompt"] for i in plan["imagenes"]] == ["PROMPT IMAGEN"] * 3
    assert [cl["clip"] for cl in plan["clips"]] == [1, 2, 3]
    assert [cl["imagen"] for cl in plan["clips"]] == ["imagen_1.png", "imagen_2.png", "imagen_3.png"]
    assert not any(cl["habla"] for cl in plan["clips"])
    assert [i["dice_la_voz_en_este_clip"] for i in plan["imagenes"]] == [
        "Tu perro duerme mal.", "Esta cama es mullida y lavable.", "Ve al carrito naranja."]
    # Clip de 8 s y mudo: valen las tres plataformas.
    assert set(plan["clips"][0]["plataformas"]) == {menus.FLOW, menus.GENAIPRO, menus.MAGNIFIC}


def test_plataformas_omni_de_genai_pro_primero():
    # Omni 1.1 de GenAI Pro (oct 2026) habla, admite ingredientes y hace 10 s.
    assert menus._plataformas(True, False, 10) == [menus.GENAIPRO, menus.FLOW]
    assert menus._plataformas(False, True, 8) == [menus.GENAIPRO, menus.FLOW]  # ingredientes
    assert menus._plataformas(False, False, 10)[0] == menus.GENAIPRO


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

    r = _rpc(app_client, url, "tools/call", {"name": "guia", "arguments": {"menu": "genjutsu"}})
    assert not r.get("isError")
    receta = r["content"][0]["text"]
    assert "cuenta NUEVA" in receta and "Flow" in receta and "Voice Changer" in receta
    assert "https://mcp.higgsfield.ai/mcp" in receta and "@Imagen 1" in receta

    r = _rpc(app_client, url, "tools/call", {"name": "menus_disponibles", "arguments": {}})
    assert "moda_mujer" in {m["menu"] for m in json.loads(r["content"][0]["text"])}

    # Los errores le llegan al agente con su mensaje, no «Error executing tool».
    r = _rpc(app_client, url, "tools/call", {"name": "guia", "arguments": {"menu": "nada"}})
    assert r["isError"] and "Menú desconocido" in r["content"][0]["text"]


def test_token_malo_401(app_client, usuarios):
    r = app_client.post("/api/mcp/ness.malo", headers=H, json={})
    assert r.status_code == 401
    assert app_client.get("/api/mcp/ness.malo/archivo", params={"b": "x"}).status_code == 401


# ---------------------------------------------------------------------------
# Enlaces firmados
# ---------------------------------------------------------------------------
def _consulta(url: str) -> dict:
    from urllib.parse import parse_qs, urlsplit

    return {k: v[0] for k, v in parse_qs(urlsplit(url).query, keep_blank_values=True).items()}


@pytest.fixture
def bandeja(usuarios, monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_COOKIE_KEY", "clave")
    monkeypatch.setenv("AGENTE_BANDEJA_DIR", str(tmp_path))
    (tmp_path / "ness").mkdir()
    (tmp_path / "ness" / "a ñ.txt").write_text("hola")
    (tmp_path / "ness" / "otro.txt").write_text("secreto")
    return tmp_path


def test_enlace_sin_token_y_descarga(app_client, bandeja):
    url = archivos.enlace_bandeja("ness", "a ñ.txt")
    assert config.token_de("ness") not in url
    assert config.token_de("ness").split(".")[1] not in url
    assert "/api/mcp-archivo?" in url
    r = app_client.get("/api/mcp-archivo", params=_consulta(url))
    assert r.status_code == 200 and r.text == "hola"
    assert r.headers["cache-control"] == "no-store"
    assert "filename*=UTF-8''a%20%C3%B1.txt" in r.headers["content-disposition"]


def test_enlace_interno_lleva_la_ruta_con_su_consulta(bandeja, monkeypatch):
    url = archivos.enlace_interno("ness", "/api/v1/mis-tandas/fotos/zip?tanda=3&x=a b")
    q = _consulta(url)
    assert q["r"] == "/api/v1/mis-tandas/fotos/zip?tanda=3&x=a b" and q["b"] == ""
    assert config.comprobar_enlace(q["u"], q["r"], q["b"], q["exp"], q["s"]) == "ok"
    assert archivos.enlace_interno("ness", "") == ""


def test_enlace_caduca_a_las_24_horas(app_client, bandeja, monkeypatch):
    ahora = 1_800_000_000
    monkeypatch.setattr(config.time, "time", lambda: ahora)
    q = _consulta(archivos.enlace_bandeja("ness", "a ñ.txt"))
    assert int(q["exp"]) == ahora + 24 * 3600
    monkeypatch.setattr(config.time, "time", lambda: ahora + 24 * 3600 - 1)
    assert app_client.get("/api/mcp-archivo", params=q).status_code == 200
    monkeypatch.setattr(config.time, "time", lambda: ahora + 24 * 3600)
    assert app_client.get("/api/mcp-archivo", params=q).status_code == 410


@pytest.mark.parametrize("campo,valor", [
    ("b", "otro.txt"),            # otro fichero
    ("u", "ana"),                 # otro usuario
    ("exp", "9999999999"),        # alargar la fecha
    ("exp", "mañana"),
    ("s", "0" * 40),
    ("s", ""),
    ("s", "ñ"),                   # no ASCII: no debe dar 500
])
def test_enlace_manipulado_403(app_client, bandeja, campo, valor):
    q = _consulta(archivos.enlace_bandeja("ness", "a ñ.txt"))
    assert app_client.get("/api/mcp-archivo", params={**q, campo: valor}).status_code == 403


def test_enlace_no_cambia_de_ruta_a_bandeja(app_client, bandeja):
    q = _consulta(archivos.enlace_interno("ness", "/api/v1/x"))
    assert app_client.get("/api/mcp-archivo", params={**q, "r": "", "b": "/api/v1/x"}).status_code == 403


def test_enlace_de_usuario_borrado_403(app_client, bandeja, monkeypatch):
    from src.api import users

    q = _consulta(archivos.enlace_bandeja("ness", "a ñ.txt"))
    monkeypatch.setattr(users, "existe", lambda u: False)
    assert app_client.get("/api/mcp-archivo", params=q).status_code == 403


def test_enlace_ruta_fuera_de_la_api_400(app_client, bandeja):
    q = _consulta(config.enlace_firmado("ness", ruta="/etc/passwd"))
    assert app_client.get("/api/mcp-archivo", params=q).status_code == 400


def test_cambiar_la_sal_anula_los_enlaces(app_client, bandeja, monkeypatch):
    q = _consulta(archivos.enlace_bandeja("ness", "a ñ.txt"))
    monkeypatch.setenv("MCP_TOKEN_SALT", "otra")
    assert app_client.get("/api/mcp-archivo", params=q).status_code == 403


def test_el_token_del_mcp_no_firma_enlaces(bandeja):
    """Quien tenga un enlace no saca de él nada que valga para otro fichero."""
    q = _consulta(archivos.enlace_bandeja("ness", "a ñ.txt"))
    assert q["s"] != config.token_de("ness").split(".")[1]


def test_guias_publicas_y_sin_salirse(app_client):
    r = app_client.get("/api/v1/agente/guias/comun/app.md")
    assert r.status_code == 200 and "text/markdown" in r.headers["content-type"]
    r = app_client.get("/api/v1/agente/guias/genjutsu-higgsfield.md")
    assert r.status_code == 200 and "Genjutsu de Higgsfield" in r.text
    assert app_client.get("/api/v1/agente/guias/../config.py").status_code == 404


def test_todas_las_guias_del_menu_existen():
    for m in menus.MENUS.values():
        assert (config.GUIAS_DIR / f"{m.guia}.md").is_file(), m.guia


def test_registrar_replica_video_desde_la_bandeja(app_client, usuarios, tmp_path, monkeypatch):
    """`registrar_replica_video` con `ruta_bandeja`: el MP4 no se sube, se
    copia de la bandeja al Drive y sale en `listar_replicas_video`."""
    from src.replicar_viral import servicio, video
    from tests.replicar_viral.test_video import MP4, FakeRedis

    r = FakeRedis()
    monkeypatch.setattr(servicio, "_redis", lambda: r)
    monkeypatch.setattr(video, "_raiz", lambda: tmp_path / "drive")
    monkeypatch.setenv("AGENTE_BANDEJA_DIR", str(tmp_path / "bandeja"))
    (config.bandeja_dir("ness") / "replicas").mkdir(parents=True, exist_ok=True)
    (config.bandeja_dir("ness") / "replicas" / "final.mp4").write_bytes(MP4)

    url = f"/api/mcp/{config.token_de('ness')}"
    res = _rpc(app_client, url, "tools/call", {"name": "registrar_replica_video", "arguments": {
        "modo": "con_ia", "titulo": "Lámpara LED", "ruta_bandeja": "replicas/final.mp4",
        "product_url": "https://www.tiktok.com/view/product/1729123456789",
        "prompts": ["clip 1", "clip 2"]}})
    assert not res.get("isError"), res
    doc = json.loads(res["content"][0]["text"])
    assert doc["id_tandas"] == f"rv|{doc['id']}" and "descargar" in doc
    assert (tmp_path / "drive" / "ness" / f"{doc['id']}.mp4").read_bytes() == MP4

    res = _rpc(app_client, url, "tools/call", {"name": "registrar_replica_video", "arguments": {
        "modo": "con_ia", "titulo": "X", "ruta_bandeja": "../../fuera.mp4"}})
    assert res["isError"] and "fuera de tu bandeja" in res["content"][0]["text"]

    res = _rpc(app_client, url, "tools/call", {"name": "listar_replicas_video", "arguments": {}})
    assert [i["id"] for i in json.loads(res["content"][0]["text"])["items"]] == [doc["id"]]


def test_registrar_variante_video_solo_de_un_verde_y_con_su_espera(app_client, usuarios, tmp_path, monkeypatch):
    """`registrar_variante_video`: la variante hereda el producto del original en
    verde, entra sin semáforo y la lista dice por qué hoy no se puede subir."""
    from src.mis_tandas import servicio as mt
    from src.replicar_viral import servicio, video
    from tests.replicar_viral.test_video import MP4, FakeRedis

    r = FakeRedis()
    monkeypatch.setattr(servicio, "_redis", lambda: r)
    monkeypatch.setattr(video, "_raiz", lambda: tmp_path / "drive")
    monkeypatch.setenv("AGENTE_BANDEJA_DIR", str(tmp_path / "bandeja"))
    colores: dict = {}
    monkeypatch.setattr(mt, "semaforos", lambda u: colores)
    (config.bandeja_dir("ness") / "variantes").mkdir(parents=True, exist_ok=True)
    (config.bandeja_dir("ness") / "variantes" / "o_var1.mp4").write_bytes(MP4 + b"1")
    (tmp_path / "o.mp4").write_bytes(MP4)
    orig = video.registrar("ness", modo="con_ia", origen=tmp_path / "o.mp4", titulo="Copas navideñas",
                           product_url="https://www.tiktok.com/view/product/1729123456789", caption="Para la cena")

    url = f"/api/mcp/{config.token_de('ness')}"
    args = {"origen_id": f"rv|{orig['id']}", "ruta_bandeja": "variantes/o_var1.mp4", "n": 1,
            "gancho": "Mira cómo quedan en la mesa antes de la cena 🥂"}
    res = _rpc(app_client, url, "tools/call", {"name": "registrar_variante_video", "arguments": args})
    assert res["isError"] and "verde" in res["content"][0]["text"]

    colores[f"rv|{orig['id']}"] = {"color": "verde"}
    res = _rpc(app_client, url, "tools/call", {"name": "registrar_variante_video", "arguments": args})
    assert not res.get("isError"), res
    v = json.loads(res["content"][0]["text"])
    assert v["variante"]["de"] == orig["id"] and v["titulo"] == "Copas navideñas" and v["caption"] == "Para la cena"
    assert "original" in v["espera"] and "descargar" in v
    assert (tmp_path / "drive" / "ness" / f"{v['id']}.mp4").read_bytes() == MP4 + b"1"

    res = _rpc(app_client, url, "tools/call", {"name": "listar_replicas_video", "arguments": {}})
    items = {i["id"]: i for i in json.loads(res["content"][0]["text"])["items"]}
    assert items[v["id"]]["espera"] and items[orig["id"]]["espera"] == "" and items[orig["id"]]["variante"] is None


class ApiSubida(ApiFalsa):
    def __init__(self, respuestas):
        super().__init__(respuestas)
        self.formularios = []

    async def post_form(self, ruta, datos, fichero):
        self.formularios.append((ruta, datos))
        return {"ok": True}


@pytest.mark.parametrize("menu,ruta_lista,ruta_subida", [
    ("pov_bof_largo", f"{menus.LARGO}/productos", f"{menus.LARGO}/clip/upload"),
    ("pov_bof", f"{menus.POV}/productos", f"{menus.POV}/video/upload"),
])
def test_subir_clip_manda_explicitas_las_herramientas_de_montaje(menu, ruta_lista, ruta_subida):
    # FastAPI pone a False un bool de Form con default True si no llega: el
    # MCP tiene que mandarlos todos o el vídeo sale sin textos ni subtítulos.
    api = ApiSubida({ruta_lista: {"items": [{"producto": "3", "clips_necesarios": 2}]}})
    c = menus.Ctx(menus.MENUS[menu], api, "mis_productos", "Carpeta_1")
    asyncio.run(menus.subir_clip(c, "3", 1, b"x", "clip_1.mp4"))
    ruta, datos = api.formularios[0]
    assert ruta == ruta_subida
    for k in ("con_gancho", "con_titulo", "con_cta", "con_flecha", "con_subtitulos"):
        assert datos[k] is True, k
    asyncio.run(menus.subir_clip(c, "3", 2, b"x", "clip_2.mp4", flecha=False))
    assert api.formularios[1][1]["con_flecha"] is False


def test_ruta_vieja_con_token_sigue_descargando(app_client, bandeja):
    r = app_client.get(f"/api/mcp/{config.token_de('ness')}/archivo", params={"b": "a ñ.txt"})
    assert r.status_code == 200 and r.text == "hola"


def test_enlace_nombre_con_salto_de_linea_no_entra_en_la_cabecera(app_client, bandeja):
    (bandeja / "ness" / 'mal\r\nX-Otra: 1".txt').write_text("hola")
    url = archivos.enlace_bandeja("ness", 'mal\r\nX-Otra: 1".txt')
    r = app_client.get("/api/mcp-archivo", params=_consulta(url))
    assert r.status_code == 200 and "x-otra" not in r.headers
    assert 'filename="mal__X-Otra: 1_.txt"' in r.headers["content-disposition"]


def test_enlace_firmado_no_sale_de_la_bandeja(app_client, bandeja):
    (bandeja / "ana").mkdir()
    (bandeja / "ana" / "suyo.txt").write_text("de ana")
    (bandeja / "ness" / "atajo.txt").symlink_to(bandeja / "ana" / "suyo.txt")
    for b in ("../ana/suyo.txt", "atajo.txt"):
        r = app_client.get("/api/mcp-archivo", params=_consulta(config.enlace_firmado("ness", bandeja=b)))
        assert r.status_code != 200 and "de ana" not in r.text


def test_enlace_lo_abre_un_pro_con_sesion(app_client, bandeja, monkeypatch):
    from src.api import main

    monkeypatch.setattr(main, "usuario_de_request", lambda _r: "ana")
    monkeypatch.setattr(main._users, "es_admin", lambda _u: False)
    r = app_client.get("/api/mcp-archivo", params=_consulta(archivos.enlace_bandeja("ness", "a ñ.txt")))
    assert r.status_code == 200 and r.text == "hola"
