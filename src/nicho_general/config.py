"""Nicho General · "UGC Desde 0" — configuración del módulo.

El formato que publicó el curso el 4 sep 2026 para el Q4: un anuncio UGC de
TRES clips, cada uno generado por separado y pegados después.

Dos cosas mandan aquí y las dos se eligen en la pantalla:

- El **gancho** (`GANCHOS`), que es lo mismo que los estilos de guion del POV
  BOF Largo: el documento del curso es el mismo salvo las escenas 1 y 2.
- La **duración** (`DURACIONES`), que no es un ajuste de vídeo sino del GUION:
  en 8 segundos no cabe lo mismo que en 10, así que son textos distintos y por
  tanto vídeos distintos. Por eso el guion y el vídeo se guardan por
  `gancho + duración` y no solo por gancho.
"""

from __future__ import annotations

import os
from pathlib import Path


def redis_prefix() -> str:
    return os.getenv("NICHO_GENERAL_REDIS_PREFIX", "nicho_general:")


# Los dos enfoques del curso. `fichero` es el documento entero, no un bloque:
# ver la cabecera de los `.md`.
GANCHOS: dict[str, dict[str, str]] = {
    "dolor": {"label": "Punto de dolor", "fichero": "guion_dolor.md"},
    "general": {"label": "General", "fichero": "guion_general.md"},
}
GANCHO_DEFECTO = "dolor"

# Cuánto dura cada clip, según con qué se genere. Los caracteres salen de la
# proporción del propio curso —170 para 10 s, que sus ejemplos cumplen (162)—
# y es lo único que hay que mover: el resto del prompt es igual.
DURACIONES: dict[str, dict] = {
    "10": {"label": "10 s · Omni", "segundos": 10, "caracteres": 170},
    "8": {"label": "8 s · GenAI Pro (Veo)", "segundos": 8, "caracteres": 136},
}
DURACION_DEFECTO = "10"

# Tres escenas SIEMPRE: es la estructura del anuncio (dolor/gancho → producto →
# urgencia y CTA), no un parámetro.
ESCENAS = 3


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def _limpio(fichero: str) -> str:
    """El `.md` sin su nota `<!-- ... -->` de cabecera."""
    from src.nicho_pov_bof.config import limpiar_prompt

    return limpiar_prompt((prompts_dir() / fichero).read_text(encoding="utf-8"))


def gancho_valido(gancho: str) -> str:
    return gancho if gancho in GANCHOS else GANCHO_DEFECTO


def duracion_valida(duracion: str) -> str:
    return str(duracion) if str(duracion) in DURACIONES else DURACION_DEFECTO


def clave_guion(gancho: str, duracion: str) -> str:
    """Con qué se escribió: `dolor_10`, `general_8`… Es la clave del documento.

    El guion de 8 s NO es el de 10 recortado —se escribe entero para caber—,
    así que cada combinación es un trabajo distinto y guarda su propio vídeo.
    """
    return f"{gancho_valido(gancho)}_{duracion_valida(duracion)}"


def prompt_guion(
    gancho: str = GANCHO_DEFECTO,
    duracion: str = DURACION_DEFECTO,
    *,
    plazos: bool = False,
    sexo_personaje: str = "",
) -> str:
    """El documento del curso listo para pegar en DeepSeek/ChatGPT.

    `plazos` y `sexo_personaje` es lo que sabemos nosotros y el documento no
    puede saber: si el producto ofrece pago a plazos —su CTA lo nombra siempre,
    y prometerlo cuando no lo hay no se puede arreglar luego porque lo dice la
    persona del vídeo— y si quien habla es un hombre o una mujer, para que la
    identidad vocal no salga al azar y contradiga al personaje.
    """
    meta = DURACIONES[duracion_valida(duracion)]
    texto = _limpio(GANCHOS[gancho_valido(gancho)]["fichero"])

    extras = []
    if not plazos:
        extras.append(
            "IMPORTANTE: este producto NO ofrece pago a plazos. En la escena 3 "
            "no lo menciones y cierra igual de natural, invitando a ir al "
            "carrito naranja y a revisar los cupones."
        )
    if sexo_personaje in ("hombre", "mujer"):
        quien = "un hombre" if sexo_personaje == "hombre" else "una mujer"
        extras.append(
            f"IMPORTANTE: quien aparece y habla en el anuncio es {quien}. La "
            "identidad vocal tiene que corresponder con esa persona."
        )
    bloque = ("\n".join(extras) + "\n") if extras else ""

    return (
        texto.replace("{{SEGUNDOS}}", str(meta["segundos"]))
        .replace("{{TOTAL}}", str(meta["segundos"] * ESCENAS))
        .replace("{{CARACTERES}}", str(meta["caracteres"]))
        .replace("{{EXTRAS}}", bloque)
    )


def prompt_personaje() -> str:
    """El de crear la referencia de la persona (se usa una vez por personaje)."""
    return _limpio("personaje.md")
