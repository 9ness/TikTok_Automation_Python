"""Rutas del Drive relativas en Redis (`src/rutas_drive.py`) y su enganche en las bases Redis."""

from __future__ import annotations

import importlib
import json
import urllib.parse

import pytest


@pytest.fixture
def rd(monkeypatch):
    """Módulo recargado con el montaje del contenedor y sin alias."""
    monkeypatch.setenv("DRIVE_MOUNT_ROOT", "/mnt/drive")
    monkeypatch.delenv("NEBULABS_DRIVE_DIR", raising=False)
    monkeypatch.delenv("AI_PRO_DRIVE_DIR", raising=False)
    monkeypatch.delenv("DRIVE_ALIAS_JSON", raising=False)
    import src.rutas_drive as m
    return importlib.reload(m)


@pytest.fixture
def rd_movido(monkeypatch):
    """Como queda tras mover el proyecto a Nebulabs/TikTok y el AI Pro a TikTok Shop."""
    monkeypatch.setenv("DRIVE_MOUNT_ROOT", "/mnt/drive")
    monkeypatch.setenv("NEBULABS_DRIVE_DIR", "Nebulabs/TikTok")
    monkeypatch.setenv("AI_PRO_DRIVE_DIR", "Nebulabs/TikTok/TikTok Shop")
    monkeypatch.delenv("DRIVE_ALIAS_JSON", raising=False)
    import src.rutas_drive as m
    yield importlib.reload(m)
    monkeypatch.delenv("NEBULABS_DRIVE_DIR")
    monkeypatch.delenv("AI_PRO_DRIVE_DIR")
    importlib.reload(m)


V = "/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Replicar_Viral/ness/a.mp4"


def test_ida_y_vuelta(rd):
    rel = rd.a_relativa(V)
    assert rel == "drive:NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Replicar_Viral/ness/a.mp4"
    assert rd.a_absoluta(rel) == V
    # idempotente
    assert rd.a_relativa(rel) == rel
    assert rd.a_absoluta(V) == V


def test_montaje_del_host_se_entiende(rd):
    host = "/home/nebulabsai/gdrive/NEBULABS_AUTOMATED_TIKTOK/x.mp4"
    assert rd.a_relativa(host) == "drive:NEBULABS_AUTOMATED_TIKTOK/x.mp4"
    assert rd.a_absoluta(host) == "/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/x.mp4"


def test_lo_que_no_es_drive_no_se_toca(rd):
    for s in ["", "hola", "/app/assets/fonts/Rubik-Bold.ttf", "/mnt/driveX/a", "https://x/y", "drive", None, 3]:
        assert rd.a_relativa(s) == s
        assert rd.a_absoluta(s) == s


def test_sufijo_mtime_se_conserva(rd):
    s = "/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF/1.png#1789989112"
    assert rd.a_absoluta(rd.a_relativa(s)) == s


def test_recorre_estructuras_y_no_toca_claves(rd):
    doc = {"video_path": V, "lista": [V, {"x": V}], "n": 3, V: "clave"}
    rel = rd.relativizar(doc)
    assert rel["video_path"].startswith("drive:")
    assert rel["lista"][1]["x"].startswith("drive:")
    assert V in rel  # las claves no cambian
    assert rd.absolutizar(rel) == doc


def test_alias_lleva_lo_viejo_a_lo_nuevo(rd_movido):
    nuevo = "/mnt/drive/Nebulabs/TikTok/TikTok Shop/Replicar_Viral/ness/a.mp4"
    assert rd_movido.a_absoluta(V) == nuevo
    assert rd_movido.a_absoluta("drive:NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Replicar_Viral/ness/a.mp4") == nuevo
    assert rd_movido.a_relativa(V) == "drive:Nebulabs/TikTok/TikTok Shop/Replicar_Viral/ness/a.mp4"
    # Lo del proyecto que no es AI Pro sigue al proyecto
    assert rd_movido.a_absoluta("/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP/_products/a.jpg") == \
        "/mnt/drive/Nebulabs/TikTok/TIKTOK_SHOP/_products/a.jpg"
    # Lo ya nuevo no se toca
    assert rd_movido.a_absoluta(nuevo) == nuevo
    assert rd_movido.AI_PRO_REL == "Nebulabs/TikTok/TikTok Shop"


def test_alias_por_env(monkeypatch):
    monkeypatch.setenv("DRIVE_MOUNT_ROOT", "/mnt/drive")
    monkeypatch.setenv("DRIVE_ALIAS_JSON", json.dumps({"MASTERPICKS_TIKTOK": "Nebulabs/Master Picks/TikTok"}))
    import src.rutas_drive as m
    m = importlib.reload(m)
    try:
        assert m.a_absoluta("drive:MASTERPICKS_TIKTOK/C1/x.jpg") == "/mnt/drive/Nebulabs/Master Picks/TikTok/C1/x.jpg"
    finally:
        monkeypatch.delenv("DRIVE_ALIAS_JSON")
        importlib.reload(m)


class _RestFalso:
    """Imita la API REST de Upstash sobre un dict, para probar las bases Redis de verdad."""

    def __init__(self):
        self.kv: dict[str, str] = {}
        self.sets: dict[str, set] = {}

    def get(self, path, timeout=10):
        partes = [urllib.parse.unquote(p) for p in path.split("/")]
        cmd, args = partes[0], partes[1:]
        if cmd == "get":
            return self.kv.get(args[0])
        if cmd == "mget":
            return [self.kv.get(a) for a in args]
        if cmd == "smembers":
            return sorted(self.sets.get(args[0], set()))
        if cmd == "sismember":
            return 1 if args[1] in self.sets.get(args[0], set()) else 0
        raise AssertionError(cmd)

    def post(self, path, body=None, timeout=10):
        partes = [urllib.parse.unquote(p) for p in path.split("/")]
        cmd, args = partes[0], partes[1:]
        if cmd == "set":
            self.kv[args[0]] = body.decode("utf-8") if body else args[1]
            return "OK"
        if cmd == "sadd":
            self.sets.setdefault(args[0], set()).add(args[1])
            return 1
        if cmd == "srem":
            self.sets.setdefault(args[0], set()).discard(args[1])
            return 1
        raise AssertionError(cmd)


@pytest.mark.parametrize("modulo,clase", [
    ("src.nicho_pov_bof.repos.redis_base", "NichoPovBofRedis"),
    ("src.viralizacion.repos.redis_base", None),
    ("src.multiplataforma.repos.redis_base", None),
    ("src.tiktok_shop.repos.redis_base", None),
])
def test_bases_redis_guardan_relativo_y_devuelven_absoluto(rd, monkeypatch, modulo, clase):
    mod = importlib.import_module(modulo)
    cls = getattr(mod, clase) if clase else next(
        v for k, v in vars(mod).items() if isinstance(v, type) and hasattr(v, "set_json") and v.__module__ == modulo)
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "http://falso")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "t")
    r = cls()
    falso = _RestFalso()
    monkeypatch.setattr(r, "_get", falso.get)
    monkeypatch.setattr(r, "_post", falso.post)

    assert r.set_json("doc", {"video_path": V, "otro": "x"})
    crudo = next(iter(falso.kv.values()))
    assert "/mnt/drive" not in crudo and "drive:NEBULABS_AUTOMATED_TIKTOK" in crudo
    assert r.get_json("doc") == {"video_path": V, "otro": "x"}

    r.sadd("ing", V)
    assert next(iter(falso.sets.values())) == {rd.a_relativa(V)}
    assert r.smembers("ing") == [V]
    if hasattr(r, "sismember"):
        assert r.sismember("ing", V)
        # dato viejo (absoluto, sin migrar) también se encuentra
        falso.sets[next(iter(falso.sets))] = {V}
        assert r.sismember("ing", V)


def test_dato_viejo_absoluto_se_lee_bien(rd, monkeypatch):
    from src.nicho_pov_bof.repos.redis_base import NichoPovBofRedis
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "http://falso")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "t")
    r = NichoPovBofRedis()
    falso = _RestFalso()
    monkeypatch.setattr(r, "_get", falso.get)
    falso.kv[r._full_key("doc")] = json.dumps({"video_path": V.replace("/mnt/drive", "/home/nebulabsai/gdrive")})
    assert r.get_json("doc") == {"video_path": V}
