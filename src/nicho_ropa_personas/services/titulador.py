"""Pone nombre a las prendas MIRANDO la foto.

Las carpetas de ropa de mujer no traen captura de la ficha, así que no hay
ningún texto que leer — el extractor del módulo 8 no tiene de dónde sacar el
título. Pero la foto sí enseña la prenda, y describirla es justo lo que hace
falta: lo que se quema en el centro del vídeo es un nombre corto ("Mono blanco
de tirantes"), no el título kilométrico del listado de TikTok.

Así el operador no tiene que teclear 38 títulos a mano; los corrige si alguno
no le encaja, que es otra cosa.

Una llamada con todas las fotos de la carpeta, como el extractor del POV BOF:
en lotes grandes el modelo se deja alguna suelta, así que se reintentan las que
falten.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from src.tiktok_shop.api.gemini import generate_json

OnLog = Callable[[str], None]
_noop: OnLog = lambda _msg: None

# Cuántas fotos por llamada. Con más, el modelo empieza a saltarse
# identificadores; con menos se pagan llamadas de sobra.
LOTE = 10


def _system_prompt() -> str:
    from src.nicho_ropa_personas import config

    return (config.prompts_dir() / "titulo_desde_foto.md").read_text(encoding="utf-8")


def titular(pares: list[dict], fetch: Callable[[str], Path], *, on_log: OnLog = _noop) -> dict[str, dict]:
    """`{producto: {"titulo": ...}}` a partir de la foto de cada prenda.

    `fetch` descarga una foto por file ID (cacheado). Se usa la foto LIMPIA:
    es la que enseña la prenda sola.
    """
    trabajo: list[tuple[str, Path]] = []
    for par in pares:
        foto = par.get("clean") or par.get("titled")
        if not foto or not foto.get("id"):
            continue
        try:
            trabajo.append((par["producto"], fetch(foto["id"])))
        except Exception as e:
            on_log(f"[titulador] no se pudo bajar la foto de {par['producto']}: {e}")

    if not trabajo:
        return {}

    system_prompt = _system_prompt()
    salida: dict[str, dict] = {}

    for i in range(0, len(trabajo), LOTE):
        lote = trabajo[i:i + LOTE]
        ids = [pid for pid, _ in lote]
        on_log(f"[titulador] nombrando {len(lote)} prendas ({ids})…")
        user_prompt = (
            "Identificadores en el MISMO orden que las imágenes adjuntas "
            f"(imagen 1 = primer identificador, etc.): {json.dumps(ids, ensure_ascii=False)}"
        )
        try:
            raw = generate_json(
                system_prompt, user_prompt,
                images=[str(p) for _pid, p in lote], temperature=0.5,
            )
        except Exception as e:
            # Que falle un lote no debe tirar los demás: la carpeta sigue
            # navegable y se puede reintentar el botón sin perder nada.
            on_log(f"[titulador] Gemini falló en este lote: {e}")
            continue
        if not isinstance(raw, dict):
            on_log(f"[titulador] respuesta inesperada: {type(raw).__name__}")
            continue
        for pid in ids:
            entrada = raw.get(pid)
            if not isinstance(entrada, dict):
                continue
            titulo = str(entrada.get("titulo") or "").strip()
            if titulo:
                salida[pid] = {"titulo": titulo}

    faltan = [pid for pid, _ in trabajo if pid not in salida]
    if faltan:
        on_log(f"[titulador] sin nombre: {faltan} (se pueden escribir a mano)")
    return salida
