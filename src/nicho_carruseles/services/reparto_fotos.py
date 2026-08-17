"""De qué producto es cada foto 2 que sube el operador en tanda.

Mismo problema que "Traer los clips generados" del POV BOF: las fotos se
generan FUERA (Flow) y vuelven con nombres que no dicen nada. Allí se resuelve
comparando fotogramas contra el catálogo de la carpeta abierta —cinco
productos—, y aquí no sirve: la tanda es de TODOS los catálogos a la vez y los
candidatos son cientos. Mandarle a Gemini cien fotos de catálogo en una llamada
devuelve 504 (ya pasó con diez en el emparejador de vídeo).

Por eso va en dos pasos:

1. **Mirar las fotos** (una llamada por cada 12): de cada una se saca qué
   producto es y sus detalles distintivos, en texto.
2. **Repartir por texto**: esas descripciones contra los TÍTULOS de los
   productos que esperan foto. Sin imágenes, así caben cientos de candidatos en
   una sola llamada y cuesta una fracción.

Nunca decide a ciegas: lo que no reconoce se queda "sin asignar" y la pantalla
lo enseña para colocarlo a mano. Tirar una generación de Flow porque el modelo
dudó sería lo peor que puede hacer esto.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from src.nicho_carruseles import config
from src.tiktok_shop.api.gemini import generate_json

OnLog = Callable[[str], None]
_noop: OnLog = lambda _: None

# Fotos por llamada al mirar. Doce es lo que aguanta bien: con más, el modelo
# empieza a saltarse alguna y a devolver menos filas de las pedidas.
POR_LOTE = 12
# Ancho al que se encogen antes de mandarlas. Las de Flow vienen a 1-2 MB y a
# ese tamaño la llamada tarda el triple sin reconocer mejor (mismo criterio que
# `emparejador.ANCHO`).
ANCHO = 540


def _miniatura(foto: Path) -> str:
    from src.nicho_pov_bof.services import thumbs

    try:
        return str(thumbs.miniatura(foto, ANCHO))
    except Exception:  # noqa: BLE001 — si falla se manda a tamaño original
        return str(foto)


def describir(fotos: list[Path], *, on_log: OnLog = _noop) -> list[str]:
    """Una frase por foto con qué producto sale. Vacía si no se ha reconocido."""
    prompt = config.leer_prompt("describir_fotos")
    salida: list[str] = [""] * len(fotos)
    for inicio in range(0, len(fotos), POR_LOTE):
        lote = fotos[inicio:inicio + POR_LOTE]
        on_log(f"[carruseles] mirando fotos {inicio + 1}-{inicio + len(lote)}…")
        try:
            raw = generate_json(
                prompt,
                f"Son {len(lote)} fotos, numeradas de 1 a {len(lote)} en el orden "
                "en que te llegan.",
                images=[_miniatura(f) for f in lote],
                temperature=0.1,
            )
        except Exception as e:  # noqa: BLE001
            on_log(f"[carruseles] no se pudieron mirar esas fotos: {e}")
            continue
        for fila in (raw or {}).get("fotos") or []:
            try:
                n = int(fila.get("n", 0)) - 1
            except (TypeError, ValueError):
                continue
            if not 0 <= n < len(lote):
                continue
            que = str(fila.get("que_es") or "").strip()
            detalles = str(fila.get("detalles") or "").strip()
            salida[inicio + n] = ". ".join(x for x in (que, detalles) if x)
    return salida


def repartir(
    fotos: list[Path], candidatos: list[dict], *, on_log: OnLog = _noop,
) -> list[dict]:
    """`[{foto: <índice>, ref, por_que}]`, uno por foto subida.

    `candidatos` son `{ref, titulo, tienda, folder}` de los productos que
    esperan foto; `ref` es lo que devuelve la asignación (y lo que identifica al
    producto: fuente + carpeta + número). Los que no se reconocen vuelven con
    `ref` vacío.
    """
    vacio = [{"foto": i, "ref": "", "por_que": ""} for i in range(len(fotos))]
    if not fotos or not candidatos:
        return vacio

    descripciones = describir(fotos, on_log=on_log)
    mirados = [i for i, d in enumerate(descripciones) if d]
    if not mirados:
        on_log("[carruseles] no se ha reconocido el producto de ninguna foto")
        return vacio

    peticion = {
        "fotos": [{"n": i + 1, "descripcion": descripciones[i]} for i in mirados],
        "catalogo": [
            {
                "id": c["ref"],
                "titulo": c.get("titulo") or "",
                "tienda": c.get("tienda") or "",
                "carpeta": c.get("folder") or "",
            }
            for c in candidatos
        ],
    }
    on_log(
        f"[carruseles] repartiendo {len(mirados)} foto(s) entre "
        f"{len(candidatos)} producto(s)…"
    )
    try:
        raw = generate_json(
            config.leer_prompt("emparejar_fotos"),
            json.dumps(peticion, ensure_ascii=False),
            temperature=0.1,
        )
    except Exception as e:  # noqa: BLE001
        on_log(f"[carruseles] el reparto falló: {e}")
        return vacio

    validos = {c["ref"] for c in candidatos}
    usados: set[str] = set()
    salida = {i: {"foto": i, "ref": "", "por_que": ""} for i in range(len(fotos))}
    for fila in (raw or {}).get("fotos") or []:
        try:
            n = int(fila.get("n", 0)) - 1
        except (TypeError, ValueError):
            continue
        ref = str(fila.get("id") or "").strip()
        # Se ignora lo que no cuadre: una referencia inventada o un producto
        # que ya se llevó otra foto. Vale más dejarla sin asignar que meterle
        # a un producto la foto de otro.
        if n not in salida or ref not in validos or ref in usados:
            continue
        usados.add(ref)
        salida[n] = {
            "foto": n, "ref": ref, "por_que": str(fila.get("por_que") or "")[:80],
        }

    hechas = sum(1 for x in salida.values() if x["ref"])
    on_log(f"[carruseles] {hechas}/{len(fotos)} fotos repartidas")
    return [salida[i] for i in range(len(fotos))]
