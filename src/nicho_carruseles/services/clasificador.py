"""Decide qué productos de una carpeta valen para carrusel.

Lee los títulos que YA extrajo el Nicho POV BOF — no vuelve a mirar las fotos.
Es la llamada más barata del proyecto (texto suelto, sin imágenes) y evita el
error de re-extraer textos que ya costaron su cuota de Gemini una vez.

Los productos sin título todavía no se pueden clasificar: se devuelven como
`otro` sin preguntar, porque no hay nada que leer.
"""

from __future__ import annotations

import json
from typing import Callable

from src.nicho_carruseles import config
from src.tiktok_shop.api.gemini import generate_json

OnLog = Callable[[str], None]
_noop: OnLog = lambda _: None


def clasificar(productos: dict[str, dict], *, on_log: OnLog = _noop) -> dict[str, str]:
    """`{producto: {titulo, tienda}}` → `{producto: categoria}`.

    Nunca revienta: si Gemini falla, se devuelve `{}` y la carpeta se queda sin
    clasificar (el botón se puede volver a pulsar sin perder nada).
    """
    con_titulo = {
        pid: prod for pid, prod in productos.items()
        if str(prod.get("titulo") or "").strip()
    }
    if not con_titulo:
        on_log("[carruseles] ningún producto con título: extrae los textos primero")
        return {}

    lista = [
        {
            "id": pid,
            "titulo": str(prod.get("titulo") or "").strip(),
            "tienda": str(prod.get("tienda") or "").strip(),
        }
        for pid, prod in sorted(con_titulo.items(), key=lambda kv: kv[0])
    ]
    on_log(f"[carruseles] clasificando {len(lista)} productos…")
    try:
        raw = generate_json(
            config.leer_prompt("clasificar"),
            json.dumps(lista, ensure_ascii=False),
            # Clasificar no es escribir: se quiere el mismo veredicto siempre,
            # no variedad.
            temperature=0.1,
        )
    except Exception as e:  # noqa: BLE001 — Gemini caído, cuota, JSON inválido
        on_log(f"[carruseles] la clasificación falló: {e}")
        return {}

    if not isinstance(raw, dict):
        on_log(f"[carruseles] respuesta inesperada: {type(raw).__name__}")
        return {}

    salida: dict[str, str] = {}
    for pid in con_titulo:
        entrada = raw.get(pid)
        categoria = ""
        if isinstance(entrada, dict):
            categoria = str(entrada.get("categoria") or "").strip().lower()
        elif isinstance(entrada, str):
            # El modelo a veces contesta el valor pelado en vez del objeto.
            categoria = entrada.strip().lower()
        # Lo que no reconozcamos cuenta como `otro`: es el lado seguro (un
        # producto de más en la lista se ve enseguida, uno de menos no).
        salida[pid] = categoria if categoria in config.CATEGORIAS else "otro"

    aptos = sum(1 for c in salida.values() if c in config.CATEGORIAS_APTAS)
    on_log(f"[carruseles] {aptos}/{len(salida)} productos valen para carrusel")
    return salida
