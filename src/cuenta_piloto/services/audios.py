"""El banco de voces PROPIO de cada operador.

En la Cuenta Piloto la voz no sale del banco compartido del curso: cada persona
(Ana, Mauro…) se graba los diez guiones con SU voz y los vídeos de SU cuenta se
montan con ellos. Es lo que distingue una cuenta de otra cuando el producto y la
edición son los mismos.

Diez sitios fijos por sexo — cinco normales y cinco de plazos—, no una lista que
crece: los guiones son esos y así se ve de un vistazo cuáles faltan por grabar.
El sitio manda el nombre del fichero (`normal3.mp3`), así que volver a grabar
uno pisa el anterior y no hay que llevar ninguna cuenta aparte.

Viven en el Drive montado, en la carpeta del operador
(`TIKTOK_SHOP_AI_PRO/Cuenta_Piloto/<usuario>/audios/<sexo>/`) y NO en
`api_uploads/`, que se purga a las 24h.

Todo entra convertido a mp3 mono 44.1k: el navegador graba en webm/opus y ffmpeg
no siempre lo lleva bien dentro del montaje. Convertir una vez al subir sale más
barato que hacerlo en cada vídeo.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from src.cuenta_piloto import config

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

TIPOS = ("normal", "plazos")
POR_TIPO = 5
SEXOS = ("hombre", "mujer")


def guiones() -> list[dict]:
    """Los diez guiones a grabar: `{tipo, n, texto}`.

    Los de plazos se IMPORTAN del Nicho POV BOF en vez de copiarse: son los
    mismos textos y con dos copias acabarían diciendo cosas distintas.
    """
    from src.nicho_pov_bof import config as pov_config

    ruta = Path(__file__).resolve().parent.parent / "prompts" / "guiones_audio.md"
    normales = [
        linea[2:].strip()
        for linea in ruta.read_text(encoding="utf-8").splitlines()
        if linea.startswith("- ") and len(linea) > 40
    ]
    plazos = pov_config.guiones_plazos()
    salida = []
    for tipo, textos in (("normal", normales), ("plazos", plazos)):
        for i in range(POR_TIPO):
            salida.append({
                "tipo": tipo,
                "n": i + 1,
                # Si algún día hay menos guiones que sitios, el hueco se queda
                # vacío en vez de descuadrar la numeración.
                "texto": textos[i] if i < len(textos) else "",
            })
    return salida


def _validar(sexo: str, tipo: str, n: int) -> None:
    if sexo not in SEXOS:
        raise ValueError(f"sexo debe ser {' o '.join(SEXOS)}, recibido: {sexo!r}")
    if tipo not in TIPOS:
        raise ValueError(f"tipo debe ser {' o '.join(TIPOS)}, recibido: {tipo!r}")
    if not 1 <= int(n) <= POR_TIPO:
        raise ValueError(f"n debe ir de 1 a {POR_TIPO}, recibido: {n}")


def carpeta(usuario: str, sexo: str) -> Path:
    d = config._raiz_usuario(usuario) / "audios" / sexo
    d.mkdir(parents=True, exist_ok=True)
    return d


def ruta(usuario: str, sexo: str, tipo: str, n: int) -> Path:
    _validar(sexo, tipo, n)
    return carpeta(usuario, sexo) / f"{tipo}{int(n)}.mp3"


def listar(usuario: str, sexo: str) -> list[dict]:
    """Los diez guiones con si están grabados y cuándo."""
    salida = []
    for g in guiones():
        f = ruta(usuario, sexo, g["tipo"], g["n"])
        hay = f.is_file() and f.stat().st_size > 0
        salida.append({
            **g,
            "grabado": hay,
            "grabado_at": int(f.stat().st_mtime) if hay else 0,
            "segundos": _duracion(f) if hay else 0.0,
        })
    return salida


def _duracion(f: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(f)],
            capture_output=True, text=True, check=True,
        )
        return round(float(out.stdout.strip()), 1)
    except Exception:
        return 0.0


def guardar(
    usuario: str, sexo: str, tipo: str, n: int, origen: Path, *, on_log: OnLog = _noop,
) -> Path:
    """Convierte a mp3 y lo deja en su sitio, pisando el anterior si lo había."""
    destino = ruta(usuario, sexo, tipo, n)
    # A un fichero temporal primero: si ffmpeg falla a medias, el audio que ya
    # estaba grabado sigue sirviendo en vez de quedarse a cero bytes.
    tmp = destino.with_suffix(".tmp.mp3")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(origen),
         "-ac", "1", "-ar", "44100", "-b:a", "192k", str(tmp)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"No se pudo convertir el audio: {proc.stderr[-300:]}")
    shutil.move(str(tmp), str(destino))
    on_log(f"[cuenta_piloto] audio {sexo}/{tipo}{n} guardado ({destino.stat().st_size} B)")
    return destino


def borrar(usuario: str, sexo: str, tipo: str, n: int) -> bool:
    f = ruta(usuario, sexo, tipo, n)
    if not f.is_file():
        return False
    f.unlink()
    return True


def elegir(usuario: str, sexo: str, tipo: str, *, semilla: str = "") -> Path | None:
    """Un audio del operador de ese tipo, o `None` si no ha grabado ninguno.

    Sortea entre los que tenga: con tres grabados de cinco, se reparten esos
    tres en vez de fallar. `semilla` hace el sorteo estable por vídeo.
    """
    import random

    hechos = [
        ruta(usuario, sexo, tipo, i + 1)
        for i in range(POR_TIPO)
        if ruta(usuario, sexo, tipo, i + 1).is_file()
    ]
    if not hechos:
        return None
    return random.Random(semilla or None).choice(hechos)


def resumen(usuario: str) -> dict[str, int]:
    """Cuántos lleva grabados por sexo. Para el aviso de la pantalla."""
    return {
        sexo: sum(1 for g in listar(usuario, sexo) if g["grabado"])
        for sexo in SEXOS
    }


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (texto or "").lower()).strip("_")
