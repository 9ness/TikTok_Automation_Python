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

# Los NICHOS de producto, sacados de contar los 734 títulos que hay extraídos
# (sep 2026). No son categorías de tienda: son "quién sale en el vídeo", que es
# lo único que decide qué personaje le toca a un producto.
#
# Cada nicho trae el `sexo` que le pega, que es el personaje que hay que crear:
# UNO por nicho, ocho en total. El sexo se puede cambiar por producto (hay
# cosas que funcionan con cualquiera de los dos), pero entonces hace falta
# haber creado también ese personaje.
#
# Lo que no se pueda clasificar cae en `generico`, que existe para eso: un
# producto sin personaje no se puede grabar.
NICHOS: dict[str, dict[str, str]] = {
    "belleza": {
        "label": "Belleza y bienestar",
        "sexo": "mujer",
        # TRES personas distintas: es el nicho con ~190 productos y con una
        # sola la misma cara saldría en 190 vídeos de la cuenta, que es un
        # patrón que se ve desde fuera. Al subir una más, se sube este número.
        "personas": 3,
        # La pista para clasificar. La lee Gemini, así que se escribe como se
        # le explicaría a una persona.
        "descripcion": (
            "cosmética, cuidado de la piel y el pelo, maquillaje, perfumes y "
            "SUPLEMENTOS en cápsulas o polvo que no sean deportivos (colágeno, "
            "vitaminas, moringa, coenzima Q10, melatonina)"
        ),
    },
    "hogar": {
        "label": "Hogar y cocina",
        "sexo": "mujer",
        "descripcion": (
            "orden, limpieza, almacenaje, textil, plantas, menaje y pequeño "
            "electrodoméstico de cocina, y accesorios de mascotas"
        ),
    },
    "exterior": {
        "label": "Exterior y bricolaje",
        "sexo": "hombre",
        "descripcion": (
            "jardín, terraza, piscina, playa, camping, barbacoa, herramientas, "
            "bicicletas y patinetes, y todo lo que hay que montar"
        ),
    },
    "tech": {
        "label": "Tecnología y gaming",
        "sexo": "hombre",
        "descripcion": (
            "electrónica, gaming, escritorios y sillas de ordenador, "
            "iluminación inteligente, audio, cargadores y gadgets"
        ),
    },
    "fitness": {
        "label": "Fitness",
        "sexo": "hombre",
        "descripcion": (
            "material de entrenamiento y suplementos DEPORTIVOS: proteína, "
            "creatina, pre-entreno. Los demás suplementos son de belleza"
        ),
    },
    "bebe": {
        "label": "Bebé y crianza",
        "sexo": "mujer",
        "descripcion": "todo lo de bebés y niños pequeños: biberones, pañales, cunas, juguetes",
    },
    "viaje": {
        "label": "Viaje",
        "sexo": "mujer",
        "descripcion": "maletas, mochilas de cabina, neceseres y accesorios de viaje",
    },
    "generico": {
        "label": "Genérico",
        "sexo": "mujer",
        "descripcion": (
            "lo que no encaje claramente en los demás. Se usa cuando dudes: "
            "vale más un genérico que un nicho equivocado"
        ),
    },
}
NICHO_DEFECTO = "generico"

# De cada nicho hay dos personajes. El sexo se elige por producto: hay cosas
# que funcionan igual con cualquiera de los dos y alternar evita que todos los
# vídeos de la cuenta salgan con la misma cara.
SEXOS = {"mujer": "Mujer", "hombre": "Hombre"}
SEXO_DEFECTO = "mujer"


def nicho_valido(nicho: str) -> str:
    return nicho if nicho in NICHOS else NICHO_DEFECTO


def sexo_valido(sexo: str) -> str:
    return sexo if sexo in SEXOS else SEXO_DEFECTO


def sexo_de_nicho(nicho: str) -> str:
    """El personaje que le toca a ese nicho si no se ha elegido otro."""
    return str(NICHOS[nicho_valido(nicho)].get("sexo") or SEXO_DEFECTO)


def personas_de(nicho: str) -> int:
    """Cuántas personas distintas hay creadas para ese nicho (mínimo una)."""
    return max(1, int(NICHOS[nicho_valido(nicho)].get("personas") or 1))


def clave_personaje(nicho: str, sexo: str = "", persona: int = 1) -> str:
    """`belleza_mujer`, `belleza_mujer_2`, `tech_hombre`… El nombre de su foto.

    La primera va sin número: así, al añadir una segunda persona a un nicho,
    lo que ya estaba grabado sigue apuntando a la misma cara.
    """
    nicho = nicho_valido(nicho)
    base = f"{nicho}_{sexo_valido(sexo) if sexo else sexo_de_nicho(nicho)}"
    persona = max(1, min(int(persona or 1), personas_de(nicho)))
    return base if persona == 1 else f"{base}_{persona}"


def reparte_persona(nicho: str, folder: str, producto: str) -> int:
    """Qué persona del nicho le toca a un producto, repartiendo por igual.

    Determinista y sin estado: sale del nombre de la carpeta y del número de
    producto, así que el mismo producto SIEMPRE cae en la misma persona —
    reordenar la carpeta o rehacer los guiones no le cambia la cara— y a la
    vez los diez de una carpeta se reparten entre las que haya.

    Se puede cambiar a mano por producto; esto es solo el reparto por defecto,
    para no tener que elegir en doscientas tarjetas.
    """
    cuantas = personas_de(nicho)
    if cuantas <= 1:
        return 1
    try:
        n = int("".join(c for c in str(producto) if c.isdigit()) or 0)
    except ValueError:
        n = 0
    # La carpeta entra en la cuenta para que dos carpetas distintas no empiecen
    # las dos por la misma persona.
    return (n + sum(ord(c) for c in str(folder))) % cuantas + 1


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


# Lo que hay que decirle al prompt del curso y él no dice: la persona sale con
# lo que lleve en la foto de Pinterest, y ahí casi todo el mundo lleva bolso.
# Ese bolso se queda en las TRES escenas de todos sus vídeos y estorba justo
# cuando tiene que sujetar el producto.
_SIN_ESTORBOS = (
    "\n\nAÑADE ESTAS CONDICIONES AL PROMPT FINAL:\n"
    "- La persona NO lleva bolso, mochila, cartera ni ningún objeto en las "
    "manos. Los dos brazos caen relajados a los lados, con las manos vacías y "
    "visibles: después tendrá que sostener productos.\n"
    "- Sin gafas de sol ni nada que tape la cara.\n"
    "- Nada de texto, marcas de agua ni logotipos en la imagen."
)


def ficha_personaje(clave: str) -> str:
    """La descripción de UN personaje ya creado, si la tenemos.

    Es lo que se pega en Flow para volver a generar su imagen: no se usa a
    diario —lo que se adjunta es la foto—, pero sin ella habría que buscar otra
    vez la referencia de Pinterest cada vez que se quiera rehacer.

    Cadena vacía si ese personaje aún no está hecho, que es lo normal mientras
    se van creando.
    """
    fichero = prompts_dir() / "personajes" / f"{clave}.md"
    if not fichero.exists():
        return ""
    from src.nicho_pov_bof.config import limpiar_prompt

    return limpiar_prompt(fichero.read_text(encoding="utf-8"))


def personajes_hechos() -> set[str]:
    """Los personajes que ya tienen ficha escrita."""
    carpeta = prompts_dir() / "personajes"
    if not carpeta.is_dir():
        return set()
    return {f.stem for f in carpeta.glob("*.md") if f.stem != "README"}


def prompt_personaje() -> str:
    """El de crear la referencia de la persona (se usa una vez por personaje).

    Al texto del curso se le añaden tres condiciones nuestras: sin bolso, con
    las manos libres y sin gafas. Se descubrió al crear el primero — salió con
    un bolso en la mano y otra en el bolsillo, y esa pose se habría repetido en
    los tres clips de todos sus vídeos.
    """
    return _limpio("personaje.md") + _SIN_ESTORBOS
