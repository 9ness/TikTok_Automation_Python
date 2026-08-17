"""Las fotos de referencia que hay que adjuntar en Flow.

Los dos prompts del curso son de imagen-a-imagen ("genera una imagen SIMILAR",
"cambia el producto de la primera imagen por el de la segunda"), así que sin
referencia no hay nada que generar. Antes estaban solo en el Drive del curso y
había que ir a buscarlas cada vez.

Dos referencias:

- `chica` — la foto de la chica sorprendida. Sale del Drive compartido del
  curso (`Productos España/Carruseles/Pronts Carruseles`), que es de SOLO
  LECTURA: se descarga por CLI y se cachea, como cualquier otra foto de ahí.
- `producto` — la composición de la foto 2 (un producto colocado en un sitio
  bonito). El curso no da ninguna, así que empieza vacía y la pone el operador.

Cualquiera de las dos se puede sustituir por una propia, que vive en SU Drive y
gana siempre: cuando una referencia deja de funcionar, cambiarla no puede
depender de que alguien toque el Drive del curso.

La de la chica admite además una POR ESCENARIO. Es lo que de verdad decide cómo
sale la foto: la del curso es una mujer de unos 35 en una cocina, y con ella
salían así también las del sofá o las de la playa, donde el público es otro.
Orden: la del escenario → la general → la del curso.
"""

from __future__ import annotations

import time
from pathlib import Path

from src.nicho_carruseles import config

TIPOS = ("chica", "producto")
_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# Carpeta del curso donde está la foto de la chica de referencia.
_CARPETA_CURSO = "Productos España/Carruseles/Pronts Carruseles"

# La del curso no cambia nunca, pero resolver su ID cuesta una llamada a
# rclone: se recuerda en memoria mientras viva el proceso.
_ID_CURSO: tuple[float, str, str] | None = None
_TTL_S = 3600.0


def _propia(tipo: str, usuario: str, escenario: str = "") -> Path | None:
    """La referencia que haya subido el operador, si la hay.

    Con `escenario` se busca la de ESE escenario (`referencia_chica_sofa.jpg`).
    Existe porque la referencia es lo que de verdad manda en la foto: la del
    curso es una mujer de unos 35 en una cocina, y de ahí salían todas —también
    las del sofá o la playa, donde el público es otro. Poniendo una por
    escenario, cada tanda sale como tiene que salir.
    """
    base = config.carruseles_dir() / (usuario or "ness")
    nombre = f"referencia_{tipo}" + (f"_{escenario}" if escenario else "")
    for ext in _EXTS:
        p = base / f"{nombre}{ext}"
        if p.is_file():
            return p
    return None


def _del_curso() -> Path | None:
    """La foto de la chica del Drive del curso, descargada y cacheada."""
    global _ID_CURSO

    from src.nicho_pov_bof import config as pov_config
    from src.nicho_pov_bof.services import drive_client

    if not (_ID_CURSO and time.monotonic() < _ID_CURSO[0]):
        try:
            ficheros = drive_client._lsjson(
                f"{pov_config.DRIVE_REMOTE}{_CARPETA_CURSO}", files_only=True,
            )
        except Exception:  # noqa: BLE001 — sin rclone o sin Drive: no hay referencia
            return None
        imagen = next(
            (
                f for f in ficheros
                if Path(str(f.get("Name") or "")).suffix.lower() in _EXTS
            ),
            None,
        )
        if not imagen:
            return None
        _ID_CURSO = (
            time.monotonic() + _TTL_S,
            str(imagen.get("ID") or ""),
            Path(str(imagen.get("Name") or "")).suffix.lower() or ".jpg",
        )

    _, file_id, suffix = _ID_CURSO
    if not file_id:
        return None
    try:
        return drive_client.fetch_photo(file_id, suffix=suffix)
    except Exception:  # noqa: BLE001
        return None


def obtener(tipo: str, usuario: str = "", escenario: str = "") -> Path | None:
    """La referencia que toca: la del escenario, si no la general, si no la del
    curso."""
    if tipo not in TIPOS:
        raise ValueError(f"referencia desconocida: {tipo!r}")
    if escenario:
        suya = _propia(tipo, usuario, escenario)
        if suya:
            return suya
    propia = _propia(tipo, usuario)
    if propia:
        return propia
    # Del curso solo hay la de la chica.
    return _del_curso() if tipo == "chica" else None


def guardar(
    tipo: str, usuario: str, datos: bytes, *, filename: str = "", escenario: str = "",
) -> Path:
    """Sustituye la referencia por una propia (general o de un escenario)."""
    if tipo not in TIPOS:
        raise ValueError(f"referencia desconocida: {tipo!r}")
    if escenario and escenario not in config.ESCENARIOS:
        raise ValueError(f"escenario desconocido: {escenario!r}")
    base = config.carruseles_dir() / (usuario or "ness")
    base.mkdir(parents=True, exist_ok=True)
    nombre = f"referencia_{tipo}" + (f"_{escenario}" if escenario else "")
    for ext in _EXTS:
        (base / f"{nombre}{ext}").unlink(missing_ok=True)
    ext = Path(filename or "").suffix.lower()
    destino = base / f"{nombre}{ext if ext in _EXTS else '.jpg'}"
    destino.write_bytes(datos)
    invalidar(usuario)
    return destino


def borrar(tipo: str, usuario: str, escenario: str = "") -> bool:
    """Quita la propia y vuelve a la de arriba (la general o la del curso)."""
    p = _propia(tipo, usuario, escenario)
    if not p:
        return False
    p.unlink(missing_ok=True)
    invalidar(usuario)
    return True


# El listado + los `stat()` de las once referencias se pagan contra el Drive
# montado: en frío eran cuarenta segundos, y esto se pide en CADA carga de la
# pantalla. Se guarda el resultado; subir o quitar una referencia lo tira, y el
# precalentado de `fotos.py` lo rehace cada pocos minutos.
_TTL_S = 600.0
_ESTADOS: dict[str, tuple[float, dict[str, dict]]] = {}


def invalidar(usuario: str = "") -> None:
    """Tras cambiar una referencia. Sin usuario, tira todo."""
    if usuario:
        _ESTADOS.pop(usuario or "ness", None)
    else:
        _ESTADOS.clear()


def estado(usuario: str = "", *, refrescar: bool = False) -> dict[str, dict]:
    """Qué referencias hay, para pintar el menú.

    `propia` distingue la que ha puesto el operador de la del curso: es lo que
    dice si el botón de "volver a la del curso" tiene sentido.

    Se lista la carpeta UNA vez en vez de preguntar fichero a fichero: son 11
    referencias × 4 extensiones = 44 comprobaciones contra el Drive montado, y
    esta pantalla ya va justa de espera.
    """
    import time as _time

    clave = usuario or "ness"
    if not refrescar:
        hit = _ESTADOS.get(clave)
        if hit and _time.monotonic() < hit[0]:
            return hit[1]

    base = config.carruseles_dir() / (usuario or "ness")
    try:
        ficheros = {
            f.stem: f for f in base.iterdir()
            if f.is_file() and f.suffix.lower() in _EXTS
        }
    except OSError:
        ficheros = {}

    def _mtime(f: Path) -> str:
        try:
            return f"{int(f.stat().st_mtime)}"
        except OSError:
            return ""

    salida: dict[str, dict] = {}
    for tipo in TIPOS:
        propia = ficheros.get(f"referencia_{tipo}")
        # Del curso solo hay la de la chica, y resolverla cuesta una llamada a
        # rclone: solo se pregunta si no hay propia.
        ruta = propia or (_del_curso() if tipo == "chica" else None)
        salida[tipo] = {
            "hay": bool(ruta),
            "propia": bool(propia),
            "version": _mtime(ruta) if ruta else "",
        }
    # Y la de cada escenario, para saber cuáles tienen la suya y cuáles tiran
    # de la general.
    for escenario in config.ESCENARIOS:
        suya = ficheros.get(f"referencia_chica_{escenario}")
        salida[f"chica_{escenario}"] = {
            "hay": bool(suya or salida["chica"]["hay"]),
            "propia": bool(suya),
            "version": _mtime(suya) if suya else salida["chica"]["version"],
        }
    _ESTADOS[clave] = (_time.monotonic() + _TTL_S, salida)
    return salida
