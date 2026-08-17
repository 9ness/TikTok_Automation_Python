"""La chica de la casa: una ficha JSON con su cara, para crear las referencias.

Viene del Nicho Ropa Con Personas, donde el operador sube una foto de internet
y Gemini la mete en la plantilla del curso. Aquí se usa para lo mismo pero con
otro fin: las FOTOS DE REFERENCIA de cada escenario.

Por qué hace falta. La referencia manda sobre el prompt en imagen-a-imagen, así
que la edad y el tipo de chica salen de ella, no de lo que pidas por escrito
(con la del curso —una mujer de ~35 en una cocina— salían todas así). Se puede
crear la referencia desde cero con un párrafo, pero un párrafo no clava a una
persona: la ficha sí, porque describe rasgos, pelo, piel y edad en campos
separados que el modelo respeta mucho mejor.

El flujo queda: buscas una chica que te guste → ficha → una referencia por
escenario con ESA chica → y en cada tanda ya salen caras distintas pero de su
edad y su estilo.

Es POR USUARIO: la cara es la identidad de la cuenta, igual que en Ropa Con
Personas. Key: `nicho_carruseles:chica:<usuario>`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from src.nicho_carruseles import config
from src.nicho_carruseles.repos.redis_base import get_nicho_carruseles_redis
from src.tiktok_shop.api.gemini import generate_json

OnLog = Callable[[str], None]
_noop: OnLog = lambda _: None

# Lo que se restaura de la plantilla pase lo que pase. El prompt ya lo pide,
# pero el modelo se despista y reescribe el encuadre o la expresión — y sin la
# cara de sorpresa esto no es un carrusel, es una foto de perfil.
BLOQUES_INTOCABLES = ("expression", "framing", "photography", "clothing", "output")


def _key(usuario: str, escenario: str = "") -> str:
    """La ficha es POR ESCENARIO: cada nicho tiene su chica (una de 20 en la
    calle, una de 32 en la cocina). Sin escenario es la general, que se usa de
    respaldo cuando ese escenario no tiene la suya."""
    base = f"chica:{usuario or 'ness'}"
    return f"{base}:{escenario}" if escenario else base


def plantilla() -> dict:
    ruta = config.prompts_dir() / "plantilla_chica.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def crear_desde_foto(foto: Path | bytes, *, on_log: OnLog = _noop) -> dict:
    """Ficha de la plantilla con la chica de la foto dentro."""
    base = plantilla()
    user_prompt = (
        "Plantilla JSON a modificar:\n"
        f"{json.dumps(base, ensure_ascii=False, indent=2)}\n\n"
        "La imagen adjunta es la chica que tiene que aparecer. Devuelve la "
        "plantilla con ella dentro."
    )
    on_log("[chica] pidiendo la ficha a Gemini…")
    imagen = foto if isinstance(foto, bytes) else str(foto)
    raw = generate_json(
        config.leer_prompt("crear_chica"), user_prompt, images=[imagen], temperature=0.4,
    )
    if not isinstance(raw, dict):
        raise ValueError("Gemini devolvió algo que no es una ficha.")
    # Se le pregunta explícitamente en vez de deducirlo comparando textos: el
    # modelo varía una coma entre llamadas y el aviso dejaba de saltar.
    if raw.get("hay_chica") is False:
        raise ValueError(
            "En esa foto no se ve a ninguna chica de la que sacar los rasgos. "
            "Prueba con una foto donde se le vea bien la cara."
        )
    ficha = raw.get("ficha")
    if not isinstance(ficha, dict) or not ficha:
        raise ValueError("Gemini no devolvió la ficha.")
    for bloque in BLOQUES_INTOCABLES:
        if bloque in base:
            ficha[bloque] = base[bloque]
    return ficha


def guardar(usuario: str, ficha: dict, escenario: str = "") -> dict:
    r = get_nicho_carruseles_redis()
    if not r.is_available():
        raise RuntimeError(
            "Redis (Upstash) no está configurado — no se puede guardar la chica."
        )
    doc = {"ficha": ficha, "creada_at": time.time(), "escenario": escenario}
    r.set_json(_key(usuario, escenario), doc)
    return doc


def leer(usuario: str, escenario: str = "") -> dict:
    """La ficha de ese escenario; si no tiene, la general."""
    r = get_nicho_carruseles_redis()
    if not r.is_available():
        return {}
    if escenario:
        suya = r.get_json(_key(usuario, escenario))
        if isinstance(suya, dict) and suya.get("ficha"):
            return suya
    return r.get_json(_key(usuario)) or {}


def borrar(usuario: str, escenario: str = "") -> None:
    r = get_nicho_carruseles_redis()
    if r.is_available():
        r.delete(_key(usuario, escenario))


def prompt_referencia(usuario: str, escenario: str) -> str:
    """El JSON con el que se crea la foto de referencia de un escenario.

    Siempre JSON, con ficha o sin ella: es lo que mejor respeta el modelo (la
    plantilla del curso del Nicho Ropa va igual) y evita que la edad o el estilo
    se pierdan en un párrafo. Con ficha guardada sale la chica del operador; sin
    ella, la de la plantilla.

    Se genera SIN adjuntar ninguna imagen: es la única forma de fijar la edad,
    porque con una foto delante el modelo copia la cara y con ella los años.
    """
    doc = leer(usuario, escenario)
    guardada = doc.get("ficha") if isinstance(doc, dict) else None
    ficha = guardada if isinstance(guardada, dict) and guardada else plantilla()

    escena = config.ESCENA_EN.get(escenario) or config.ESCENA_EN["generico"]
    ficha = json.loads(json.dumps(ficha).replace("{escena}", f"She is {escena}"))
    # La edad la manda el escenario, no la foto que subió: una de 20 no vale
    # para anunciar un colchón (ver `foto_chica_<escenario>.md`).
    if isinstance(ficha.get("subject"), dict):
        ficha["subject"]["age"] = config.EDAD_REFERENCIA.get(escenario, "20 years old")
    return json.dumps(ficha, ensure_ascii=False, indent=2)
