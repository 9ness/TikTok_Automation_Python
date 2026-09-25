"""Ficheros entre el agente y la app: bandeja del Drive, subidas por HTTP,
descargas por URL, miniaturas para que el agente MIRE y fotogramas de clips.
"""

from __future__ import annotations

import io
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import quote

import httpx

from src.agente_mcp import config
from src.agente_mcp.interno import ErrorApp

_EXT_IMG = (".jpg", ".jpeg", ".png", ".webp")
_EXT_VID = (".mp4", ".mov", ".webm", ".mkv")


def slug(texto: str, largo: int = 40) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s[:largo].rstrip("_") or "producto"


# ---------------------------------------------------------------------------
# Bandeja
# ---------------------------------------------------------------------------
def dir_carpeta(usuario: str, menu: str, carpeta: str) -> Path:
    d = config.bandeja_dir(usuario) / menu / slug(carpeta.split("__")[-1], 60)
    d.mkdir(parents=True, exist_ok=True)
    return d


def dir_producto(usuario: str, menu: str, carpeta: str, producto: str, titulo: str) -> Path:
    base = dir_carpeta(usuario, menu, carpeta)
    # Si ya existe una del producto (con otro título), se reutiliza.
    for d in base.glob(f"{slug(producto, 12)}_*"):
        if d.is_dir():
            return d
    d = base / f"{slug(producto, 12)}_{slug(titulo, 40)}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ruta_en_bandeja(usuario: str, relativa: str) -> Path:
    """Resuelve una ruta relativa a la bandeja del usuario, sin salirse de ella."""
    base = config.bandeja_dir(usuario).resolve()
    p = (base / (relativa or "").lstrip("/")).resolve()
    if base != p and base not in p.parents:
        raise ErrorApp("Esa ruta está fuera de tu bandeja.")
    return p


def relativa(usuario: str, p: Path) -> str:
    return str(p.resolve().relative_to(config.bandeja_dir(usuario).resolve()))


# ---------------------------------------------------------------------------
# Leer lo que manda el agente: url, archivo_id (subido por HTTP) o bandeja
# ---------------------------------------------------------------------------
def guardar_subida(usuario: str, datos: bytes, nombre: str) -> str:
    ext = Path(nombre or "").suffix.lower()
    aid = uuid.uuid4().hex[:16] + (ext if ext in _EXT_IMG + _EXT_VID else "")
    (config.subidas_dir(usuario) / aid).write_bytes(datos)
    return aid


def _no_interna(url: str) -> None:
    """Que una url no sirva para que el servidor se pida cosas a sí mismo o a
    la red interna (la API, Redis, el host)."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    host = urlparse(url).hostname or ""
    try:
        ips = {i[4][0] for i in socket.getaddrinfo(host, None)}
    except OSError as e:
        raise ErrorApp(f"No se resuelve {host!r}.") from e
    for ip in ips:
        a = ipaddress.ip_address(ip)
        if a.is_private or a.is_loopback or a.is_link_local or a.is_reserved:
            raise ErrorApp("Esa url apunta a una red interna.")


async def leer_origen(usuario: str, *, url: str = "", archivo_id: str = "",
                      ruta_bandeja: str = "") -> tuple[bytes, str]:
    """(bytes, nombre). Exactamente UNA de las tres fuentes."""
    fuentes = [x for x in (url, archivo_id, ruta_bandeja) if x]
    if len(fuentes) != 1:
        raise ErrorApp("Indica UNA fuente: `url`, `archivo_id` o `ruta_bandeja`.")
    tope = config.MAX_FICHERO_MB * 1024 * 1024
    if ruta_bandeja:
        p = ruta_en_bandeja(usuario, ruta_bandeja)
        if not p.is_file():
            raise ErrorApp(f"No existe {ruta_bandeja!r} en tu bandeja (¿aún sincronizando el Drive?).")
        return p.read_bytes(), p.name
    if archivo_id:
        if not re.fullmatch(r"[a-f0-9]{16}(\.[a-z0-9]+)?", archivo_id):
            raise ErrorApp("archivo_id inválido.")
        p = config.subidas_dir(usuario) / archivo_id
        if not p.is_file():
            raise ErrorApp("Ese archivo_id no existe (o ya caducó).")
        return p.read_bytes(), p.name
    if not url.startswith(("http://", "https://")):
        raise ErrorApp("La url tiene que ser http(s).")
    async def _revisar(req: httpx.Request) -> None:  # también en cada redirección
        _no_interna(str(req.url))

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=300, event_hooks={"request": [_revisar]},
    ) as c:
        async with c.stream("GET", url) as r:
            if r.status_code >= 400:
                raise ErrorApp(f"No se pudo bajar la url (HTTP {r.status_code}).")
            buf = bytearray()
            async for trozo in r.aiter_bytes():
                buf.extend(trozo)
                if len(buf) > tope:
                    raise ErrorApp(f"Pasa de {config.MAX_FICHERO_MB} MB.")
    nombre = Path(url.split("?")[0]).name or "descarga"
    return bytes(buf), nombre


# ---------------------------------------------------------------------------
# Para que el agente MIRE: imágenes reducidas y fotogramas de un clip
# ---------------------------------------------------------------------------
def reducir_imagen(datos: bytes, lado: int = 1024) -> bytes:
    from PIL import Image as PILImage

    img = PILImage.open(io.BytesIO(datos))
    img = img.convert("RGB")
    img.thumbnail((lado, lado))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


def es_video(nombre: str, datos: bytes) -> bool:
    if Path(nombre or "").suffix.lower() in _EXT_VID:
        return True
    return datos[4:8] in (b"ftyp", b"moov") or datos[:4] == b"\x1aE\xdf\xa3"


def fotogramas(datos: bytes, n: int = 4, lado: int = 640) -> tuple[list[bytes], float]:
    """`n` fotogramas repartidos por el clip (JPEG) y su duración en segundos."""
    n = max(1, min(int(n or 4), 8))
    with tempfile.TemporaryDirectory() as tmp:
        vid = Path(tmp) / "clip.mp4"
        vid.write_bytes(datos)
        try:
            dur = float(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(vid)],
                capture_output=True, text=True, timeout=60, check=True,
            ).stdout.strip() or 0)
        except (subprocess.SubprocessError, ValueError) as e:
            raise ErrorApp(f"No se pudo leer el vídeo: {e}") from e
        fotos: list[bytes] = []
        for i in range(n):
            t = dur * (i + 0.5) / n
            out = Path(tmp) / f"f{i}.jpg"
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(vid),
                 "-frames:v", "1", "-vf", f"scale={lado}:-2", str(out)],
                capture_output=True, timeout=60,
            )
            if out.is_file():
                fotos.append(out.read_bytes())
    return fotos, dur


# ---------------------------------------------------------------------------
# Enlaces de descarga para el agente (pasan por el proxy del MCP)
# ---------------------------------------------------------------------------
def enlace_interno(usuario: str, ruta_api: str) -> str:
    """URL pública que sirve un GET interno de la API con el token del MCP."""
    if not ruta_api:
        return ""
    return f"{config.url_mcp(usuario)}/archivo?r={quote(ruta_api, safe='')}"


def enlace_bandeja(usuario: str, rel: str) -> str:
    return f"{config.url_mcp(usuario)}/archivo?b={quote(rel, safe='')}"
