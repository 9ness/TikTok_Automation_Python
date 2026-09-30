"""La carpeta de temporada «Productos Q4»: copias de productos del Inventario.

Se copian fotos y textos (con la duración del guion y el origen) para grabar un
vídeo nuevo sin pisar el del original, y el manifiesto hace que añadir el mismo
producto dos veces no lo duplique.
"""

from __future__ import annotations

from src.nicho_pov_bof import config
from src.nicho_pov_bof.services import productos_q4


class _Redis:
    def __init__(self) -> None:
        self.d: dict = {}

    def is_available(self) -> bool:
        return True

    def get_json(self, k):
        return self.d.get(k)

    def set_json(self, k, v):
        self.d[k] = v
        return True


def _prepara(tmp_path, monkeypatch):
    origen = tmp_path / "Carpeta_22"
    origen.mkdir()
    for n in (3, 4):
        (origen / f"{n}.png").write_bytes(b"limpia")
        (origen / f"{n}(1).jpeg").write_bytes(b"ficha")
    destino = tmp_path / config.CARPETA_Q4
    redis = _Redis()
    guardados: dict = {}

    from src.nicho_pov_bof.repos import product_repo
    from src.nicho_pov_bof.services import drive_client, photo_pairing

    monkeypatch.setattr(productos_q4, "get_nicho_pov_bof_redis", lambda: redis)
    monkeypatch.setattr(productos_q4, "_dir", lambda: destino.mkdir(exist_ok=True) or destino)
    monkeypatch.setattr(productos_q4, "_invalidar", lambda: None)
    monkeypatch.setattr(drive_client, "list_photos", lambda s, f, **k: [
        {"id": str(p), "name": p.name} for p in sorted(origen.iterdir())
    ])
    monkeypatch.setattr(drive_client, "probe_dimensions", lambda f: f)
    monkeypatch.setattr(photo_pairing, "pair_folder", lambda fotos: [
        {"producto": n, "clean": {"id": str(origen / f"{n}.png")},
         "titled": {"id": str(origen / f"{n}(1).jpeg")}}
        for n in (3, 4)
    ])
    monkeypatch.setattr(drive_client, "fetch_photo", lambda i, suffix="": __import__("pathlib").Path(i))
    monkeypatch.setattr(product_repo, "get_product", lambda s, f, p, u="": {
        "titulo": f"Producto {p}", "tienda": "Tienda", "precio": 9.9, "vacio": "",
    })
    monkeypatch.setattr(
        product_repo, "save_extracted_texts",
        lambda s, f, t: guardados.setdefault((s, f), {}).update(t),
    )
    return destino, redis, guardados


def test_copia_fotos_y_textos_con_duracion_y_origen(tmp_path, monkeypatch):
    destino, redis, guardados = _prepara(tmp_path, monkeypatch)
    r = productos_q4.anadir(
        ["inventario_general|Carpeta_22|3", "inventario_general|Carpeta_22|4"],
        segundos_guion=24,
    )
    assert [a["producto"] for a in r["añadidos"]] == ["1", "2"]
    assert sorted(f.name for f in destino.iterdir()) == ["1(1).jpeg", "1.png", "2(1).jpeg", "2.png"]
    textos = guardados[(config.CATALOGO_Q4, config.CARPETA_Q4)]
    assert textos["1"]["titulo"] == "Producto 3"
    assert textos["1"]["segundos_guion"] == 24.0
    assert textos["2"]["origen"] == "inventario_general|Carpeta_22|4"
    assert "vacio" not in textos["1"]


def test_no_duplica_y_no_recicla_numeros(tmp_path, monkeypatch):
    destino, redis, _ = _prepara(tmp_path, monkeypatch)
    productos_q4.anadir(["inventario_general|Carpeta_22|3"])
    r = productos_q4.anadir(["inventario_general|Carpeta_22|3", "inventario_general|Carpeta_22|4"])
    assert r["ya_estaban"] == [{"ref": "inventario_general|Carpeta_22|3", "producto": "1"}]
    assert [a["producto"] for a in r["añadidos"]] == ["2"]
    # Aunque se borren las fotos del 2, el siguiente no reutiliza su número.
    for f in destino.glob("2*"):
        f.unlink()
    redis.d[productos_q4._MANIFIESTO]["x|y|z"] = "2"
    assert productos_q4._siguiente_numero(destino, redis.d[productos_q4._MANIFIESTO]) == 3


def test_refs_mal_formadas_y_sin_foto(tmp_path, monkeypatch):
    _prepara(tmp_path, monkeypatch)
    r = productos_q4.anadir(["mal", "inventario_general|Carpeta_22|99",
                             f"inventario_general|{config.CARPETA_Q4}|1"])
    assert not r["añadidos"] and len(r["omitidos"]) == 3


def test_solo_ness_ve_la_carpeta():
    assert config.ve_carpeta_q4("ness")
    assert not config.ve_carpeta_q4("ana")


def test_el_guion_de_temporada_lleva_el_angulo_regalo_sin_promesas():
    from src.nicho_pov_bof_largo import config as largo

    normal = largo.prompt_guion(False, "dolor", False, 24)
    q4 = largo.prompt_guion(False, "dolor", False, 24, temporada=True)
    assert "TEMPORADA" not in normal
    assert "TEMPORADA" in q4 and "REGALO" in q4
    assert "Black Friday" in q4 and "fechas de entrega" in q4
    # La cabecera del fichero es para el repo, no para Gemini.
    assert "Bloque que se AÑADE" not in q4
