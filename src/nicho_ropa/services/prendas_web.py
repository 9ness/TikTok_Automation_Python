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
    """`[(genero, carpeta)]` de los dos géneros, para el selector."""
    return [(g, c) for g in config.GENEROS_WEB for c in carpetas(g)]


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
