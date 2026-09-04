"""Las prendas de la web del curso, importadas por ZIP.

Su web tiene dos inventarios de ropa —mujer y hombre—, cada uno con 31
carpetas de diez prendas. Este nicho, en cambio, estaba montado PLANO: cuatro
categorías fijas y todas las prendas dentro de cada una.

En vez de meterle un nivel al nicho entero, cada carpeta importada se comporta
como una categoría más, con slug `mujer_web__Carpeta 23`. Para el resto del
código sigue siendo "una carpeta", así que fotos, textos, estado y vídeo
funcionan sin tocarse.

La convención de nombres del ZIP es la misma que en POV BOF y viene AL REVÉS
que la nuestra (`N` es la ficha, `N.1` la limpia), así que se reutiliza el
importador de allí en vez de duplicar esa lógica — que es justo la que si se
equivoca deja las diez parejas cambiadas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from src.nicho_ropa import config

_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_TTL_S = 900.0
_LISTADOS: dict[str, tuple[float, Any]] = {}


def _memo(clave: str, calcular: Callable[[], Any]) -> Any:
    import time

    guardado = _LISTADOS.get(clave)
    if guardado and time.monotonic() < guardado[0]:
        return guardado[1]
    valor = calcular()
    _LISTADOS[clave] = (time.monotonic() + _TTL_S, valor)
    return valor


def _invalidar() -> None:
    _LISTADOS.clear()


def _dir_genero(genero: str) -> Path:
    """La raíz de ese género. Los del operador viven aparte de los del ZIP.

    Se separan en Drive porque son cosas distintas —los de la web se
    ACTUALIZAN resubiendo el mismo ZIP, y los del operador los sube él uno a
    uno— pero para el resto del código son el mismo tipo de carpeta.
    """
    if config.es_genero_operador(genero):
        return config.mis_prendas_dir() / genero
    return config.prendas_web_dir() / genero


def carpetas(genero: str) -> list[str]:
    """Carpetas importadas de ese género, en orden natural (1, 2, 10…)."""
    from src.nicho_pov_bof import config as pov_config

    def leer() -> list[str]:
        raiz = _dir_genero(genero)
        if not raiz.is_dir():
            return []
        return sorted(
            (d.name for d in raiz.iterdir() if d.is_dir() and not d.name.startswith(".")),
            key=pov_config.natural_sort_key,
        )

    return _memo(f"carpetas:{genero}", leer)


def todas_las_carpetas() -> list[tuple[str, str]]:
    """`[(genero, carpeta)]` de los géneros de la web, para el selector."""
    return [(g, c) for g in config.GENEROS_WEB for c in carpetas(g)]


def carpetas_del_operador() -> list[tuple[str, str]]:
    """`[(genero, carpeta)]` de los cuatro catálogos propios (mujer/hombre ×
    muestras/tareas).

    Los cuatro salen SIEMPRE, aunque no tengan nada: son sitios fijos donde
    dejar prendas, y un catálogo que no aparece hasta que subes algo obliga a
    adivinar que existe. La primera carpeta se nombra sola (`Muestras 1`) y no
    se crea en Drive hasta que entra la primera prenda.
    """
    salida: list[tuple[str, str]] = []
    for genero in config.GENEROS_OPERADOR:
        suyas = carpetas(genero)
        salida += [(genero, c) for c in suyas] or [(genero, f"{_prefijo(genero)} 1")]
    return salida


# ---------------------------------------------------------------------------
# Alta de prendas propias
# ---------------------------------------------------------------------------
# Mismo planteamiento que "Mis productos" del POV BOF, y por el mismo motivo:
# las fotos se guardan con el convenio de nombres de siempre (`3.jpg` la
# limpia, `3(1).jpg` la ficha), así que el emparejado, los textos, los prompts
# y el montaje funcionan sin una línea extra. Lo único propio de aquí es que
# el género forma parte del slug, así que lo que subes en mujer se queda en
# mujer.
_PREFIJO_CARPETA = {"muestras": "Muestras", "tareas": "Tareas"}


def _prefijo(genero: str) -> str:
    for clave, nombre in _PREFIJO_CARPETA.items():
        if genero.endswith(clave):
            return nombre
    return "Carpeta"


def _num_carpeta(nombre: str) -> int:
    import re

    m = re.search(r"(\d+)\s*$", nombre or "")
    return int(m.group(1)) if m else 0


def _prendas_en(genero: str, carpeta: str) -> set[str]:
    """Números de prenda que ya hay en la carpeta."""
    import re

    numeros: set[str] = set()
    for foto in listar_fotos_como_drive(config.slug_web(genero, carpeta)):
        m = re.match(r"^(\d+)", Path(foto["name"]).stem)
        if m:
            numeros.add(m.group(1))
    return numeros


def cuantas_prendas(genero: str, carpeta: str) -> int:
    """Cuántas prendas hay en la carpeta, MEMOIZADO.

    Lo pide el chip de cada carpeta del selector, o sea una vez por carpeta y
    en cada carga de la pantalla. Contarlas es listar el Drive montado y en
    frío eso tarda: con once carpetas, el listado llegó a tardar 25 s y la
    pantalla se quedaba cargando. El TTL es el mismo que el de los listados
    (`_TTL_S`), y subir un ZIP invalida la caché igual que antes.
    """
    return _memo(f"cuantas:{genero}:{carpeta}", lambda: len(_prendas_en(genero, carpeta)))


def carpeta_actual(genero: str) -> str:
    """La carpeta donde toca guardar: la última con hueco, o una nueva."""
    existentes = carpetas(genero)
    if existentes:
        ultima = existentes[-1]
        if len(_prendas_en(genero, ultima)) < config.MIS_PRENDAS_POR_CARPETA:
            return ultima
        return f"{_prefijo(genero)} {_num_carpeta(ultima) + 1}"
    return f"{_prefijo(genero)} 1"


def _extension(nombre: str) -> str:
    ext = Path(nombre or "").suffix.lower()
    return ext if ext in _EXTS else ".jpg"


def guardar_prenda(
    genero: str, limpia: bytes, ficha: bytes | None, *,
    nombre_limpia: str = "", nombre_ficha: str = "",
) -> dict:
    """Guarda las fotos de una prenda propia. Devuelve `{slug, carpeta, prenda}`.

    La ficha es opcional, como en el POV BOF: sin ella la prenda existe igual
    y los textos se escriben a mano o con otra captura.
    """
    if not config.es_genero_operador(genero):
        raise ValueError(f"{genero!r} no es un catálogo tuyo")

    carpeta = carpeta_actual(genero)
    destino = _dir_genero(genero) / carpeta
    destino.mkdir(parents=True, exist_ok=True)
    usados = {int(n) for n in _prendas_en(genero, carpeta) if n.isdigit()}
    prenda = str(1 + max(usados, default=0))

    # Guardarraíl del POV BOF: el número sale de un listado cacheado y si
    # alguien tocó la carpeta a mano se escribiría ENCIMA de una prenda.
    if any((destino / f"{prenda}{ext}").exists() for ext in _EXTS):
        _invalidar()
        carpeta = carpeta_actual(genero)
        destino = _dir_genero(genero) / carpeta
        destino.mkdir(parents=True, exist_ok=True)
        usados = {int(n) for n in _prendas_en(genero, carpeta) if n.isdigit()}
        prenda = str(1 + max(usados, default=0))

    (destino / f"{prenda}{_extension(nombre_limpia)}").write_bytes(limpia)
    if ficha:
        (destino / f"{prenda}(1){_extension(nombre_ficha)}").write_bytes(ficha)

    # Sin esto el operador sube la prenda y no la ve hasta que vence el TTL.
    _invalidar()
    return {
        "slug": config.slug_web(genero, carpeta),
        "carpeta": carpeta,
        "prenda": prenda,
    }


def listar_fotos_como_drive(slug: str) -> list[dict]:
    """Mismo shape que `drive_client.list_photos`, leyendo del disco.

    El `id` es la RUTA con el mtime pegado: es lo que deja cachear la foto un
    día en el móvil y que al sustituirla se vuelva a pedir.
    """
    from src.nicho_pov_bof import config as pov_config

    genero, carpeta = config.partes_web(slug)

    def leer() -> list[dict]:
        d = _dir_genero(genero) / carpeta
        if not d.is_dir():
            return []
        fotos = [
            {
                "id": f"{f}#{int(f.stat().st_mtime)}",
                "name": f.name,
                "size": f.stat().st_size,
                "mime": "image/png" if f.suffix.lower() == ".png" else "image/jpeg",
                "mtime": "",
            }
            for f in d.iterdir()
            if f.is_file() and f.suffix.lower() in _EXTS
        ]
        fotos.sort(key=lambda p: pov_config.natural_sort_key(p["name"]))
        return fotos

    return _memo(f"fotos:{slug}", leer)


def importar_zip(datos: bytes, nombre_zip: str, genero: str) -> dict:
    """Mete un ZIP de la web en el género que toque. Repetible.

    Se apoya en el importador del POV BOF: la convención del ZIP es idéntica y
    duplicarla sería duplicar el punto donde más fácil es equivocarse.
    """
    if genero not in config.GENEROS_WEB:
        raise ValueError(f"Género desconocido: {genero!r}")

    from src.nicho_pov_bof.services import productos_web as pov_web

    destino = _dir_genero(genero)
    destino.mkdir(parents=True, exist_ok=True)
    r = pov_web.importar_zip(datos, nombre_zip, raiz=destino)
    _invalidar()
    return {**r, "genero": genero, "slug": config.slug_web(genero, r["carpeta"])}
