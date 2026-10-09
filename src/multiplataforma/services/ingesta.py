"""Ingesta automática desde las carpetas del Drive montado.

Por cuenta: `<raíz Multiplataforma>/<slug>/viralizacion/` → `prueba_viral` y
`<slug>/producto/` → `producto`. Cada vídeo (.mp4/.mov) nuevo se encola con
la programación que le toca según el `ritmo` (vídeos/día por tipo) y las
`horas` de la cuenta, continuando tras la última ya programada. Orden natural
por nombre de fichero (`2.mp4` antes que `10.mp4`).

Texto y enlace: un `.json` o `.txt` con el MISMO nombre del vídeo, si existe.
- `.json`: `titulo`, `caption`, `hashtags`, `asin`, `enlace`, `plataformas`,
  `trial_graduation`, `producto_ref` (todo opcional).
- `.txt`: una línea que sea solo una URL → enlace; una línea solo de
  `#hashtags` → hashtags; el resto → caption.
Sin enlace se publica sin enlace.

No se ingesta dos veces: SET Redis `ingestadas:<slug>` con las rutas ya
encoladas. Tras publicar en TODAS las plataformas, `mover_a_publicados` lo
pasa a `<carpeta>/publicados/` (lo llama el publicador).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import time
import zoneinfo
from pathlib import Path
from typing import Callable, Iterator

from src.multiplataforma import config
from src.multiplataforma.models import CuentaDestino, Publicacion
from src.multiplataforma.repos import cuentas_repo, publicaciones_repo, redis_base
from src.multiplataforma.services import enlaces, textos

ORIGEN = "ingesta"
_URL_RE = re.compile(r"^https?://\S+$")


def _noop(_: str) -> None:
    return None


def _key_ingestadas(slug: str) -> str:
    return f"ingestadas:{slug}"


def carpeta_cuenta(slug: str) -> Path:
    return config.raiz_drive() / slug


def asegurar_carpetas(slug: str, log: Callable[[str], None] = _noop) -> Path:
    """mkdir -p de las carpetas de la cuenta. Defensivo: si falla, solo log."""
    base = carpeta_cuenta(slug)
    for carpeta in config.CARPETAS_INGESTA:
        try:
            (base / carpeta / config.CARPETA_PUBLICADOS).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log(f"[multiplataforma] no se pudo crear {base / carpeta}: {e}")
    return base


def _orden_natural(nombre: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", nombre)]


def _videos(carpeta: Path) -> list[Path]:
    if not carpeta.is_dir():
        return []
    vids = [p for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() in config.EXTENSIONES_INGESTA
            and not p.name.startswith(".")]
    return sorted(vids, key=lambda p: _orden_natural(p.name))


# ---- metadatos del vídeo ----
def _titulo_de_nombre(video: Path) -> str:
    t = re.sub(r"^[\d\s._-]+", "", video.stem)  # «03_lampara» → «lampara»
    t = re.sub(r"[_-]+", " ", t or video.stem).strip()
    return t[:1].upper() + t[1:]


TEXTO_CARPETA = "_texto.txt"


def leer_metadatos(video: Path) -> dict:
    """Lee el `.json`/`.txt` hermano. Devuelve claves de `PublicacionIn`."""
    meta: dict = {}
    js = video.with_suffix(".json")
    txt = video.with_suffix(".txt")
    if js.is_file():
        d = json.loads(js.read_text(encoding="utf-8") or "{}")
        if not isinstance(d, dict):
            raise ValueError(f"{js.name}: tiene que ser un objeto JSON")
        meta.update(d)
    else:
        if not txt.is_file():
            # sin .txt propio: el `_texto.txt` de la carpeta (texto común, p. ej.
            # el de todos los virales de Pablo Motos)
            txt = video.parent / TEXTO_CARPETA
    if not js.is_file() and txt.is_file():
        caption, hashtags = [], []
        texto = txt.read_text(encoding="utf-8")
        if txt.name == TEXTO_CARPETA:
            # varias variantes separadas por una línea `---`: cada vídeo coge
            # una fija (por su nombre) para que no salgan todos iguales
            variantes = [v for v in re.split(r"(?m)^\s*---\s*$", texto) if v.strip()]
            if variantes:
                n = int(hashlib.sha1(video.name.encode()).hexdigest(), 16)
                texto = variantes[n % len(variantes)]
        for linea in texto.splitlines():
            s = linea.strip()
            if _URL_RE.match(s) and not meta.get("enlace"):
                meta["enlace"] = s
            elif s and all(w.startswith("#") for w in s.split()):
                hashtags.extend(s.split())
            else:
                caption.append(linea.rstrip())
        meta["caption"] = "\n".join(caption).strip()
        if hashtags:
            meta["hashtags"] = hashtags
        if txt.name == TEXTO_CARPETA and meta["caption"]:
            # texto común: el nombre del fichero («pablo1_2») no es un título
            meta.setdefault("titulo", "")
    meta.setdefault("titulo", _titulo_de_nombre(video))
    return meta


def _publicacion(cuenta: CuentaDestino, video: Path, tipo: str, programada_en: float) -> Publicacion:
    meta = leer_metadatos(video)
    plataformas = [p for p in (meta.get("plataformas") or config.PLATAFORMAS) if p in config.PLATAFORMAS]
    enlace = enlaces.resolver(asin=str(meta.get("asin") or ""), enlace=str(meta.get("enlace") or ""),
                              amazon_tag=cuenta.afiliado_amazon_tag)
    producto_ref = str(meta.get("producto_ref") or "")
    if not enlace and producto_ref:
        # El enlace del producto guardado por el agente (enlaces_repo).
        from src.multiplataforma.repos import enlaces_repo

        enlace = enlaces_repo.enlace_de(cuenta.slug, producto_ref)
    caption = str(meta.get("caption") or "")
    hashtags = [str(h) for h in (meta.get("hashtags") or [])]
    t = textos.construir(titulo=str(meta.get("titulo") or ""), caption=caption,
                         enlace=enlace, hashtags=hashtags, plataformas=plataformas)
    return Publicacion(
        cuenta=cuenta.slug, video_path=str(video), tipo=tipo, producto_ref=producto_ref,
        titulo=t["titulo_pin"], caption=caption, hashtags=hashtags,
        textos=t["textos"], comentario=t["comentario"], enlace=enlace,
        plataformas=plataformas or list(config.PLATAFORMAS), programada_en=programada_en,
        trial_graduation=str(meta.get("trial_graduation") or "MANUAL").upper(), origen=ORIGEN,
    )


# ---- programación ----
def _parse_hora(h: str) -> tuple[int, int]:
    hh, _, mm = str(h).strip().partition(":")
    return max(0, min(23, int(hh))), max(0, min(59, int(mm or 0)))


def horas_del_dia(ritmo: int, horas: list[str]) -> list[tuple[int, int]]:
    """`ritmo` huecos al día. Si hay menos horas que ritmo, los que faltan van
    cada hora tras la última (sin pasar de las 23:59)."""
    if ritmo <= 0:
        return []
    base = sorted({_parse_hora(h) for h in (horas or [])}) or [(12, 0)]
    out = base[:ritmo]
    h, m = out[-1]
    while len(out) < ritmo:
        h += 1
        out.append((h, m) if h <= 23 else (23, 59))  # más de lo que cabe: se apilan a las 23:59
    return out


def huecos(ritmo: int, horas: list[str], desde: float, tz: str = config.ZONA_HORARIA) -> Iterator[float]:
    """Timestamps de publicación posteriores a `desde`, `ritmo` por día."""
    if ritmo <= 0:
        return
    zona = zoneinfo.ZoneInfo(tz)
    dia = dt.datetime.fromtimestamp(desde, zona).date()
    franjas = horas_del_dia(ritmo, horas)
    while True:
        for h, m in franjas:
            ts = dt.datetime(dia.year, dia.month, dia.day, h, m, tzinfo=zona).timestamp()
            if ts > desde:
                yield ts
        dia += dt.timedelta(days=1)


def _ultima_programada(slug: str, tipo: str) -> float:
    pubs = [p.programada_en for p in publicaciones_repo.pendientes() if p.cuenta == slug and p.tipo == tipo]
    return max(pubs, default=0.0)


# ---- ingesta ----
def ingestar(cuenta: str | CuentaDestino, ahora: float | None = None, *,
             log: Callable[[str], None] = _noop) -> dict:
    """Encola los vídeos nuevos de las carpetas de la cuenta. Devuelve el informe."""
    c = cuentas_repo.get(cuenta) if isinstance(cuenta, str) else cuenta
    slug = cuenta if isinstance(cuenta, str) else cuenta.slug
    informe: dict = {"cuenta": slug, "encoladas": [], "errores": []}
    if not c:
        informe["omitida"] = f"la cuenta {slug!r} no existe"
        return informe
    ahora = time.time() if ahora is None else ahora
    base = asegurar_carpetas(c.slug, log)
    r = redis_base.get_redis()
    ya = set(r.smembers(_key_ingestadas(c.slug)))

    for carpeta, tipo in config.CARPETAS_INGESTA.items():
        ritmo = int((c.ritmo or {}).get(tipo, config.RITMO_DEFAULT.get(tipo, 1)))
        nuevos = [v for v in _videos(base / carpeta) if str(v) not in ya]
        if not nuevos:
            continue
        if ritmo <= 0:
            log(f"[multiplataforma] {c.slug}/{carpeta}: ritmo 0, {len(nuevos)} vídeo(s) sin ingestar")
            continue
        horas = (c.horas or {}).get(tipo) or config.HORAS_DEFAULT.get(tipo, ["12:00"])
        reloj = huecos(ritmo, horas, max(ahora, _ultima_programada(c.slug, tipo)))
        for video in nuevos:
            try:
                pub = _publicacion(c, video, tipo, 0.0)
            except (ValueError, OSError) as e:  # JSON roto, enlace inválido…: se reintenta en el próximo tick
                informe["errores"].append({"video": str(video), "error": str(e)})
                log(f"[multiplataforma] {video.name}: {e}")
                continue
            pub.programada_en = next(reloj)
            pub, creada = publicaciones_repo.encolar(pub)
            r.sadd(_key_ingestadas(c.slug), str(video))
            informe["encoladas"].append({"id": pub.id, "video": str(video), "tipo": tipo,
                                         "programada_en": pub.programada_en, "creada": creada})
            log(f"[multiplataforma] {c.slug}: {video.name} → {tipo} "
                f"{dt.datetime.fromtimestamp(pub.programada_en, zoneinfo.ZoneInfo(config.ZONA_HORARIA)):%Y-%m-%d %H:%M}")
    return informe


def ingestar_todas(ahora: float | None = None, *, log: Callable[[str], None] = _noop) -> list[dict]:
    out = []
    for c in cuentas_repo.listar():
        if not c.activa:
            continue
        try:
            out.append(ingestar(c, ahora, log=log))
        except Exception as e:  # noqa: BLE001 — una cuenta rota no para el tick
            out.append({"cuenta": c.slug, "error": f"{type(e).__name__}: {e}"})
            log(f"[multiplataforma] ingesta {c.slug}: {e}")
    return out


def mover_a_publicados(pub: Publicacion, log: Callable[[str], None] = _noop) -> str | None:
    """Mueve el vídeo (y su .json/.txt) a `<carpeta>/publicados/`. Si falla, solo log.
    Devuelve la ruta nueva o None."""
    origen = Path(pub.video_path)
    if pub.origen != ORIGEN or not origen.is_file():
        return None
    if origen.parent.name == config.CARPETA_PUBLICADOS:
        return None  # ya movido (se volvió a pasar una publicación terminada)
    destino_dir = origen.parent / config.CARPETA_PUBLICADOS
    try:
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / origen.name
        if destino.exists():
            destino = destino_dir / f"{origen.stem}_{pub.id}{origen.suffix}"
        shutil.move(str(origen), str(destino))
        for ext in (".json", ".txt"):
            hermano = origen.with_suffix(ext)
            if hermano.is_file():
                shutil.move(str(hermano), str(destino.with_suffix(ext)))
    except OSError as e:
        log(f"[multiplataforma] no se pudo mover {origen} a publicados: {e}")
        return None
    # fuera del SET: si mañana entra otro vídeo con el mismo nombre, es nuevo
    redis_base.get_redis().srem(_key_ingestadas(pub.cuenta), str(origen))
    log(f"[multiplataforma] {origen.name} → {destino}")
    return str(destino)
