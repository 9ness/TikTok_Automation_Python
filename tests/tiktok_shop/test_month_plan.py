"""El calendario por meses y las estadísticas por formato.

Lo que se protege aquí: que las estadísticas se puedan calcular SIN leer
productos (es lo que las hace escalar), y que el mes sea un documento
independiente (cargar julio no debe depender de junio).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.tiktok_shop.models.month_plan import (  # noqa: E402
    DayEntry,
    MonthPlan,
    month_of,
)


def _e(date: str, pid: str, **kw) -> DayEntry:
    return DayEntry(date=date, product_id=pid, name=f"prod {pid}", **kw)


def test_month_of() -> None:
    assert month_of("2026-07-15") == "2026-07"
    assert month_of("2026-01-01") == "2026-01"
    assert month_of("") == ""


def test_by_date_agrupa() -> None:
    p = MonthPlan(month="2026-07", entries=[
        _e("2026-07-15", "a"), _e("2026-07-15", "b"), _e("2026-07-16", "c"),
    ])
    d = p.by_date()
    assert sorted(d) == ["2026-07-15", "2026-07-16"]
    assert len(d["2026-07-15"]) == 2


def test_stats_cuenta_ventas_por_formato() -> None:
    """El punto de las 3 versiones: saber QUÉ formato vende."""
    p = MonthPlan(month="2026-07", entries=[
        _e("2026-07-15", "a", uploaded=True, sold=True, sold_version=1,
           sold_format="Dramatización del problema", revenue_eur=12.14),
        _e("2026-07-15", "b", uploaded=True, sold=True, sold_version=1,
           sold_format="Dramatización del problema", revenue_eur=8.0),
        _e("2026-07-16", "c", uploaded=True, sold=True, sold_version=0,
           sold_format="UGC hablando a cámara", revenue_eur=5.0),
        _e("2026-07-16", "d", uploaded=True),          # subido, no vendió
        _e("2026-07-17", "e"),                          # ni subido
    ])
    s = p.stats()
    assert s["products"] == 5
    assert s["uploaded"] == 4
    assert s["sold"] == 3
    assert s["revenue_eur"] == 25.14
    assert s["conversion_pct"] == 75.0          # 3 de 4 subidos
    assert s["by_format"]["Dramatización del problema"]["sold"] == 2
    assert s["by_format"]["UGC hablando a cámara"]["sold"] == 1


def test_stats_no_necesita_productos() -> None:
    """`sold_format` está en la ENTRADA, no en el Product → las estadísticas
    se calculan sin leer productos. Si esto se rompe, el informe pasaría a
    hacer N lecturas y se caería justo cuando hay histórico."""
    e = _e("2026-07-15", "a", uploaded=True, sold=True, sold_format="POV / demo")
    assert MonthPlan(month="2026-07", entries=[e]).stats()["by_format"] == {
        "POV / demo": {"sold": 1},
    }


def test_stats_sin_subidos_no_divide_por_cero() -> None:
    assert MonthPlan(month="2026-07", entries=[_e("2026-07-15", "a")]).stats()[
        "conversion_pct"] == 0.0
    assert MonthPlan(month="2026-07").stats()["products"] == 0


def test_vendido_sin_formato_no_ensucia_el_informe() -> None:
    """Si se marca vendido sin decir qué versión, cuenta en `sold` pero no
    inventa un formato."""
    p = MonthPlan(month="2026-07", entries=[
        _e("2026-07-15", "a", uploaded=True, sold=True),
    ])
    s = p.stats()
    assert s["sold"] == 1 and s["by_format"] == {}


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ✅ {name}")
            except AssertionError as e:
                fails += 1
                print(f"  ❌ {name}: {e}")
    print(f"\n{'todos OK' if not fails else f'{fails} FALLOS'}")
    sys.exit(1 if fails else 0)
