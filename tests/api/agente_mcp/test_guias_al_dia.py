"""«MCP y guías al día» (CLAUDE.md › Convenciones), comprobado por un test.

Los vídeos los hacen agentes que solo saben lo que dicen las guías: una
herramienta que ninguna guía nombra no la usa nadie, y una guía que manda
llamar a una herramienta que ya no existe deja al agente parado. Sin red.
"""

from __future__ import annotations

import asyncio
import re

import pytest

pytest.importorskip("mcp")

from src.agente_mcp import config, servidor  # noqa: E402

# Llamadas que salen en las guías con forma de herramienta y no lo son
# (JavaScript del navegador, funciones del repo). Añade aquí solo eso.
NO_SON_HERRAMIENTAS = {"fetch"}


def _herramientas() -> set[str]:
    return {t.name for t in asyncio.run(servidor.mcp.list_tools())}


def _guias() -> dict[str, str]:
    return {p.relative_to(config.GUIAS_DIR).as_posix(): p.read_text(encoding="utf-8")
            for p in config.GUIAS_DIR.rglob("*.md")}


def _nombra(texto: str, nombre: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(nombre)}(?!\w)", texto) is not None


def test_cada_herramienta_sale_en_alguna_guia():
    todo = "\n".join(_guias().values())
    sin_guia = sorted(n for n in _herramientas() if not _nombra(todo, n))
    assert not sin_guia, (
        f"Herramientas del MCP que ninguna guía nombra: {sin_guia}. Añádelas a la guía de su "
        "menú (src/agente_mcp/guias/) en el mismo cambio: el agente solo usa lo que lee ahí.")


def test_las_guias_no_mandan_llamar_a_herramientas_que_no_existen():
    existen = _herramientas()
    malas = []
    for guia, texto in _guias().items():
        # `nombre(…)` entre comillas invertidas, con algún guion bajo o igual
        # de largo que una herramienta: así se citan en todas las guías.
        for nombre in set(re.findall(r"`([a-z][a-z0-9_]{3,})\(", texto)):
            if nombre not in existen and nombre not in NO_SON_HERRAMIENTAS:
                malas.append(f"{guia}: {nombre}()")
    assert not malas, (
        f"Las guías citan herramientas que el MCP no tiene: {sorted(malas)}. Renombradas o "
        "borradas: corrige la guía (o añade el nombre a NO_SON_HERRAMIENTAS si no es del MCP).")


def test_las_instrucciones_del_servidor_solo_nombran_herramientas_que_existen():
    existen = _herramientas()
    citadas = set(re.findall(r"`([a-z][a-z0-9_]{3,})(?:\([^`]*\))?`", servidor.INSTRUCCIONES))
    # Palabras entre comillas que son argumentos o campos, no herramientas.
    con_forma = {c for c in citadas if "_" in c or c in existen}
    falsas = sorted(c for c in con_forma if c not in existen and not c.endswith(("_0", "_1")))
    assert not falsas, f"INSTRUCCIONES nombra herramientas que no existen: {falsas}"


def test_toda_herramienta_explica_que_hace():
    cortas = sorted(t.name for t in asyncio.run(servidor.mcp.list_tools())
                    if len((t.description or "").strip()) < 40)
    assert not cortas, f"Herramientas sin docstring útil (es lo único que lee el agente): {cortas}"
