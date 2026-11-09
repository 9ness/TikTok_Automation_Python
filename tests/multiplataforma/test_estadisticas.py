"""Estadísticas de Meta: lectura de la Graph API (sin red) e informe semanal en Markdown."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from src.multiplataforma.services import informe

RAIZ = Path(__file__).resolve().parents[2]


def _cargar_script():
    spec = importlib.util.spec_from_file_location("mp_est", RAIZ / "scripts" / "multiplataforma_estadisticas.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


est = _cargar_script()


# ── lectura de la API ──────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status: int, cuerpo):
        self.status_code = status
        self._cuerpo = cuerpo

    def json(self):
        if isinstance(self._cuerpo, Exception):
            raise self._cuerpo
        return self._cuerpo


def test_leer_ok_y_token_no_sale_en_errores(monkeypatch):
    vistos = {}

    def get(url, params, timeout):
        vistos.update(params)
        return _Resp(200, {"data": [{"name": "views", "total_value": {"value": 7}}]})

    monkeypatch.setattr(est.httpx, "get", get)
    errores: list[str] = []
    datos = est.leer("https://g/x", "SECRETO", errores, "ig cuenta", metric="views")
    assert est.metricas(datos, ("views", "reach")) == {"views": 7, "reach": None}
    assert vistos["access_token"] == "SECRETO" and errores == []


def test_leer_token_caducado_anota_codigo_sin_token(monkeypatch):
    cuerpo = {"error": {"code": 190, "message": "Error validating access token: Session has expired"}}
    monkeypatch.setattr(est.httpx, "get", lambda url, params, timeout: _Resp(400, cuerpo))
    errores: list[str] = []
    assert est.leer("https://g/x?access_token=SECRETO", "SECRETO", errores, "fb perfil") == {}
    assert errores and "(190)" in errores[0] and "SECRETO" not in errores[0]


def test_leer_red_caida_y_json_roto(monkeypatch):
    def caida(url, params, timeout):
        raise httpx.ConnectTimeout("lento")

    monkeypatch.setattr(est.httpx, "get", caida)
    errores: list[str] = []
    assert est.leer("u", "t", errores, "th perfil") == {}
    monkeypatch.setattr(est.httpx, "get", lambda url, params, timeout: _Resp(200, ValueError("no json")))
    assert est.leer("u", "t", errores, "th cuenta") == {}
    assert errores == ["th perfil: ConnectTimeout", "th cuenta: ValueError"]


def test_valor_suma_values_y_none_si_no_hay():
    assert est.valor({"values": [{"value": 2}, {"value": 3}, {"value": None}]}) == 5
    assert est.valor({"values": []}) is None
    assert est.valor({}) is None
    assert est.valor({"total_value": {"value": 0}}) == 0


def test_resumen_por_tipo_ignora_sin_dato():
    medidas = [{"tipo": "producto", "instagram": {"views": 10}, "facebook": {"fb_reels_total_plays": None}},
               {"tipo": "producto", "instagram": {"views": 30}}]
    r = est.resumen_por_tipo(medidas)
    assert r == {"producto": {"instagram": {"n": 2, "media": 20.0, "max": 30}}}


# ── informe ────────────────────────────────────────────────────────────────

AHORA = dt.datetime(2026, 11, 9, 21, 0).timestamp()


def _pub(pid, dias_atras, ig, tipo="producto", titulo="Producto", fb=0, hora="20:30"):
    ts = AHORA - dias_atras * 86400
    d = dt.datetime.fromtimestamp(ts)
    m = {"id": pid[:8], "pid": pid, "tipo": tipo, "titulo": titulo, "fecha": d.strftime("%Y-%m-%d"),
         "hora": hora, "ts": int(ts), "instagram": {"views": ig, "likes": 1, "comments": 0, "shares": 0, "saved": 0}}
    if fb is not None:
        m["facebook"] = {"fb_reels_total_plays": fb}
    return m


def _foto(pubs_por_cuenta, seguidores=10, errores=None):
    return {"cuentas": {c: {"instagram": {"seguidores": seguidores}, "facebook": {"seguidores": 0},
                            "threads": {"seguidores": 0}, "publicaciones": ps, "errores": errores or [],
                            "salud": {"estados": {"instagram:publicado": len(ps), "pinterest:simulado": 1,
                                                  "facebook:fallido": 1}}, "en_cola": 5}
                        for c, ps in pubs_por_cuenta.items()}}


def test_publicaciones_se_quedan_con_la_lectura_mas_reciente():
    viejo = _foto({"viva_shop": [_pub("aaaa1111", 3, 10)]})
    nuevo = _foto({"viva_shop": [_pub("aaaa1111", 3, 90)]})
    pubs = informe.publicaciones([("2026-11-06", viejo), ("2026-11-09", nuevo)])
    assert len(pubs) == 1 and pubs[0]["instagram"]["views"] == 90 and pubs[0]["leido"] == "2026-11-09"


def test_lectura_vieja_sin_pid_ni_hora():
    m = {"id": "abc", "tipo": "producto", "fecha": "2026-11-01", "instagram": {"views": 5}}
    pubs = informe.publicaciones([("2026-11-02", {"cuentas": {"ama_shop": {"publicaciones": [m]}}})])
    assert informe._ts(pubs[0]) is not None
    assert informe.franja(pubs[0]) is None and informe.dia_semana(pubs[0]) == "domingo"


def test_formato_por_titulo():
    assert informe.formato({"tipo": "prueba_viral", "titulo": "La reflexión de Pablo Motos"}) == "viral_pablo_motos"
    assert informe.formato({"tipo": "producto", "titulo": "Remedios 09 · agua"}) == "remedios"
    assert informe.formato({"tipo": "carrusel", "titulo": "Tendedero"}) == "carrusel"


def test_interaccion_none_sin_vistas_o_sin_datos():
    assert informe.interaccion_ig({"instagram": {"views": 0, "likes": 3}}) is None
    assert informe.interaccion_ig({"instagram": {"views": 10}}) is None
    assert informe.interaccion_ig({"instagram": {"views": 10, "likes": 1, "saved": None}}) == 10


def test_flojas_y_despegaron():
    pubs = [dict(_pub(f"p{i:07d}", 3 + i * 0.1, 100), cuenta="viva_shop") for i in range(5)]
    pubs.append(dict(_pub("floja000", 3, 5), cuenta="viva_shop"))
    pubs.append(dict(_pub("reciente", 1, 1), cuenta="viva_shop"))  # < 48 h: no se juzga
    pubs.append(dict(_pub("viral000", 2, 5000), cuenta="viva_shop"))
    flo = [m["pid"] for m in informe.flojas(pubs, AHORA)]
    assert flo == ["floja000"]
    assert [m["pid"] for m in informe.despegaron(pubs)] == ["viral000"]


def test_facebook_a_cero_ignora_sin_dato():
    pubs = [_pub("a", 1, 1, fb=0), _pub("b", 1, 1, fb=2), _pub("c", 1, 1, fb=None)]
    assert informe.facebook_a_cero(pubs) == (2, 2)
    assert informe.facebook_a_cero([_pub("d", 1, 1, fb=40)] + pubs) == (2, 3)


def test_recomendacion_exige_datos_y_ventaja():
    pubs = ([dict(_pub(f"v{i}", 2, 400, tipo="prueba_viral", titulo="Pablo Motos"), cuenta="ama_shop") for i in range(3)]
            + [dict(_pub(f"p{i}", 2, 100), cuenta="ama_shop") for i in range(3)]
            + [dict(_pub("x", 2, 100), cuenta="viva_salud")])
    rec = "\n".join(informe.recomendaciones(pubs))
    assert "`viral_pablo_motos` rinde 4.0×" in rec
    assert "**viva_salud**: pocos datos" in rec


def test_foto_anterior_busca_la_de_hace_una_semana():
    fotos = [("2026-11-01", {}), ("2026-11-02", {}), ("2026-11-07", {}), ("2026-11-09", {})]
    assert informe.foto_anterior(fotos)[0] == "2026-11-02"
    assert informe.foto_anterior([("2026-11-08", {}), ("2026-11-09", {})]) is None


def test_generar_markdown_completo(tmp_path):
    vieja = _foto({"viva_shop": [_pub("aaaa1111", 8, 50)]}, seguidores=40)
    nueva = _foto({"viva_shop": [_pub(f"b{i:07d}", 2 + i * 0.2, 100 + i) for i in range(5)]
                   + [_pub("viral999", 3, 9000, tipo="prueba_viral", titulo="Pablo Motos", fb=None)]},
                  seguidores=42, errores=["fb perfil: HTTP 400 (190) caducado"])
    for fecha, inf in (("2026-11-02", vieja), ("2026-11-09", nueva)):
        (tmp_path / f"{fecha}.json").write_text(json.dumps(inf), encoding="utf-8")
    (tmp_path / "semanal_2026-11-02.md").write_text("ignorar")
    (tmp_path / "2026-11-05.json").write_text("{roto")  # JSON roto: se salta

    fotos = informe.cargar(tmp_path)
    assert [f for f, _ in fotos] == ["2026-11-02", "2026-11-09"]
    md = informe.generar(fotos, ahora=AHORA)
    assert "Facebook a cero" in md
    assert "(190)" in md
    assert "| viva_shop | instagram | 42 | +2 |" in md
    assert "Despegaron" in md and "9.000" in md
    assert "20-21 h" in md
    assert "pinterest:simulado" not in md and "facebook:fallido" in md


def test_generar_sin_datos():
    assert "Sin datos" in informe.generar([])


@pytest.mark.parametrize("v,txt", [(None, "—"), (25226, "25.226"), (4279.75, "4.279,8"), (120.0, "120")])
def test_formato_numeros(v, txt):
    assert informe._n(v) == txt
