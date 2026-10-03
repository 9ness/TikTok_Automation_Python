"""Todo modo, estilo y nicho que sale en «Mis tandas» tiene su color.

Si este test falla es que se ha creado un modo nuevo (estilo de guion del
Largo, formato del multimodo o nicho nuevo en Mis tandas) sin asignarle color
en `frontend/lib/tiktok-shop-ai-pro/coloresModo.ts`. Añádelo allí: un color
que no use otro modo del mismo nicho.
"""

from __future__ import annotations

import re
from pathlib import Path

COLORES = Path(__file__).resolve().parents[2] / "frontend/lib/tiktok-shop-ai-pro/coloresModo.ts"


def _bloque(nombre: str) -> str:
    texto = COLORES.read_text(encoding="utf-8")
    i = texto.index(f"const {nombre}")
    return texto[i:texto.index("};" if "Record" in texto[i:i + 80] else "];", i)]


def test_cada_estilo_del_largo_tiene_color():
    from src.nicho_pov_bof_largo import config as largo_config

    claves = set(re.findall(r"^\s*(\w+):", _bloque("ESTILOS_LARGO"), re.M))
    faltan = set(largo_config.ESTILOS_GUION) - claves
    assert not faltan, f"Estilos del Largo sin color en coloresModo.ts: {sorted(faltan)}"


def test_cada_formato_del_multimodo_tiene_familia_y_color():
    from src.agente_mcp import menus

    prefijos = re.findall(r'\[\s*"(mm_[a-z0-9_]+)"', _bloque("FAMILIAS_MM"))
    formatos = [m for m in menus.MENUS["moda_mujer_multimodo"].modos if m.startswith("mm_")]
    faltan = [f for f in formatos if not any(f.startswith(p) for p in prefijos)]
    assert not faltan, f"Formatos del multimodo sin familia/color en coloresModo.ts: {faltan}"


def test_cada_nicho_de_mis_tandas_tiene_color():
    from src.mis_tandas import config

    claves = set(re.findall(r"^\s*(\w+):", _bloque("COLOR_NICHO"), re.M))
    faltan = set(config.NICHOS) - claves
    assert not faltan, f"Nichos de Mis tandas sin color en coloresModo.ts: {sorted(faltan)}"


def test_estilo_viral_tiene_color():
    claves = set(re.findall(r"^\s*(\w+):", _bloque("ESTILOS_LARGO"), re.M))
    assert "viral" in claves


def test_cada_modo_de_aleatorios_con_video_tiene_color():
    """Los modos de Moda Mujer · Aleatorios que salen en Mis tandas."""
    claves = set(re.findall(r"^\s*(\w+):", _bloque("MODOS_ALEA"), re.M))
    for modo in ("tienda_colores", "calle_dividido"):
        assert modo in claves, f"Modo de Aleatorios sin color en coloresModo.ts: {modo}"
