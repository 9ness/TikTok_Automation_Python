"""Cruce banco árabe ↔ vídeos en verde de otras cuentas (scripts/cuenta_arabe_pov/reaprovechar.py)."""
import importlib.util
import os
from pathlib import Path

_RUTA = Path(__file__).resolve().parents[1] / "scripts" / "cuenta_arabe_pov" / "reaprovechar.py"
_spec = importlib.util.spec_from_file_location("reaprovechar", _RUTA)
rea = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rea)

PID = "1729948518973020649"


def _clip(ruta: Path, mtime: float | None = None) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"x")
    if mtime:
        os.utime(ruta, (mtime, mtime))
    return ruta


def _fila(**k):
    base = {"usuario": "ness", "id": "largo|inventario_general|Épico Octubre|43|epico",
            "color": "verde", "titulo": "Lavabo", "video_path": "/v.mp4", "video_listo_at": 2000.0,
            "product_url": f"https://www.tiktok.com/view/product/{PID}"}
    base.update(k)
    return base


def test_id_en_url_entiende_las_dos_formas_de_ficha():
    assert rea.id_en_url(f"https://www.tiktok.com/view/product/{PID}?x=1") == PID
    assert rea.id_en_url(f"https://shop.tiktok.com/es/pdp/{PID}?_d=abc") == PID
    assert rea.id_en_url("https://vm.tiktok.com/ZG9A4cKDjh6fs-X61YE/") == ""
    assert rea.id_en_url("") == ""


def test_partes_fila_solo_largo():
    p = rea.partes_fila("largo|mis_productos|Mis Productos 15|6|regalo")
    assert p == {"fuente": "mis_productos", "carpeta": "Mis Productos 15", "producto": "6", "modo": "regalo"}
    assert rea.partes_fila("rv|ff01a26b7538") is None
    assert rea.partes_fila("pov|aleatorios_1|7 Pront Flow|5") is None


def test_brutos_bandeja_por_carpeta_y_numero_sin_confundir_43_con_4(tmp_path):
    base = tmp_path / "ness" / "pov_bof_largo" / "Epico_Octubre"
    _clip(base / "4_Otra_cosa" / "clip_1.mp4")
    _clip(base / "43_Lavabo_de_acero" / "clip_2.mp4")
    _clip(base / "43_Lavabo_de_acero" / "clip_1.mp4")
    _clip(base / "43_Lavabo_de_acero" / "imagen_1.png")
    clips = rea.brutos_bandeja(tmp_path, "ness", "Épico Octubre", "43")
    assert [c.name for c in clips] == ["clip_1.mp4", "clip_2.mp4"]
    assert clips[0].parent.name == "43_Lavabo_de_acero"
    assert rea.brutos_bandeja(tmp_path, "ness", "Épico Octubre", "44") == []
    assert rea.brutos_bandeja(tmp_path, "ana", "Épico Octubre", "43") == []


def test_brutos_subidos_coge_la_ultima_subida_anterior_al_video(tmp_path):
    for nombre in ("inventario_general__pico_Octubre_43_clip1_1000.mp4",
                   "inventario_general__pico_Octubre_43_clip1_1500.mp4",
                   "inventario_general__pico_Octubre_43_clip1_2500.mp4",   # posterior: otro montaje
                   "inventario_general__pico_Octubre_43_clip2_1501.mp4",
                   "inventario_general__pico_Octubre_4_clip1_1400.mp4"):   # otro producto
        _clip(tmp_path / nombre)
    clips = rea.brutos_subidos(tmp_path, "inventario_general", "Épico Octubre", "43", 2000.0)
    assert [c.name for c in clips] == ["inventario_general__pico_Octubre_43_clip1_1500.mp4",
                                       "inventario_general__pico_Octubre_43_clip2_1501.mp4"]


def test_cruzar_solo_verdes_del_banco_y_por_id(tmp_path):
    bandejas, subidos = tmp_path / "b", tmp_path / "s"
    _clip(bandejas / "ness/pov_bof_largo/Epico_Octubre/43_Lavabo/clip_1.mp4", 1900)
    corto = "https://vm.tiktok.com/ZGabc/"
    filas = [
        _fila(),
        _fila(id="largo|tareas_productos|Tareas Productos 21|1|dolor", color="ambar"),
        _fila(id="largo|x|Otra|9|dolor", product_url="https://www.tiktok.com/view/product/1111111111111"),
        _fila(id="largo|temporada_q4|Temporada Q4 1|4|regalo", product_url=corto),
        _fila(id="rv|abc", usuario="ana"),
        _fila(id="largo|x|Sin Enlace|2|dolor", product_url=""),
    ]
    banco = {PID: {"producto": "Lavabo de acero", "precio": 19.9}}
    cands = rea.cruzar(filas, banco, {}, {corto: PID}, bandejas=bandejas, subidos=subidos)
    assert [c["fila"] for c in cands] == [
        "largo|inventario_general|Épico Octubre|43|epico",   # con brutos, el primero
        "largo|temporada_q4|Temporada Q4 1|4|regalo",        # enlace corto resuelto, sin brutos
        "rv|abc",                                            # verde pero no es Largo
    ]
    assert cands[0]["origen_brutos"] == "bandeja" and cands[0]["aviso"] == ""
    assert cands[1]["brutos"] == [] and "sin clips brutos" in cands[1]["aviso"]
    assert "no es POV BOF Largo" in cands[2]["aviso"]
    assert rea.resumen(cands) == {"productos_en_verde": 1, "productos_con_brutos": 1,
                                  "productos_con_brutos_sin_hacer": 1, "juegos_de_clips": 1}


def test_cruzar_avisa_si_la_bandeja_cambio_despues_del_verde_y_marca_lo_ya_hecho(tmp_path):
    _clip(tmp_path / "ness/pov_bof_largo/Epico_Octubre/43_Lavabo/clip_1.mp4", 9000)
    cands = rea.cruzar([_fila()], {PID: {"producto": "Lavabo"}}, {PID: ["hmizat_ronda9:4"]}, {},
                       bandejas=tmp_path, subidos=tmp_path / "nada")
    assert "POSTERIORES" in cands[0]["aviso"]
    assert cands[0]["ya_hecho"] == ["hmizat_ronda9:4"]
    assert rea.resumen(cands)["productos_con_brutos_sin_hacer"] == 0


def test_cruzar_usa_el_id_de_la_ficha_si_la_fila_no_tiene_enlace(tmp_path):
    filas = [_fila(id="largo|mis_productos|Mis Productos 5|8|dolor", product_url="",
                   product_id=PID)]
    cands = rea.cruzar(filas, {PID: {"producto": "Lavabo"}}, {}, {},
                       bandejas=tmp_path, subidos=tmp_path / "nada")
    assert [c["product_id"] for c in cands] == [PID]
