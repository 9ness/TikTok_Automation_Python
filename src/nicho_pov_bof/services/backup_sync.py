"""Backup versionado del Drive compartido "Productos España".

El admin del Drive de origen avisa y borra todo cada cierto tiempo, así que
necesitamos (a) una copia íntegra en nuestro Drive y (b) detectar qué ha
cambiado desde la última copia sin volver a copiarlo todo.

Dos decisiones que no son obvias:

1. **La identidad de un fichero es su file ID, no su ruta.** En este Drive hay
   ~388 objetos con nombre duplicado dentro de la misma carpeta (`2.PNG` dos
   veces). Si el snapshot se indexara por ruta, esos pares se pisarían y cada
   diff mentiría. Indexado por ID, los duplicados son objetos distintos y el
   diff es exacto.

2. **`rclone copy` DESCARTA duplicados** ("Duplicate object found in source -
   ignoring") porque no puede representar dos ficheros con el mismo nombre en
   una carpeta. Por eso toda copia (completa o delta) pasa por
   `rclone backend copyid`, que copia por ID a un nombre desambiguado.

Las copias son server-side (Drive → Drive): no bajan al disco del VPS.
El origen NUNCA se modifica.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof import config

OnLog = Callable[[str], None]
_noop: OnLog = lambda _: None

# Origen como connection-string: convierte "Compartido conmigo" en la raíz sin
# afectar al destino (que vive en "Mi unidad" del mismo remote).
SRC_REMOTE = "gdrive,shared_with_me=true:"
SRC_PATH = f"{SRC_REMOTE}{config.SHARED_ROOT}"

# Destino: hermano de TIKTOK_SHOP_AI_PRO bajo la raíz del proyecto en Drive.
#
# Todas las copias cuelgan de UNA carpeta (`BACKUP_DIR`) en vez de quedarse
# sueltas en la raíz. Se hace una copia casi cada día y en un mes la raíz del
# proyecto eran quince carpetas de backup y tres de trabajo: encontrar
# `TIKTOK_SHOP_AI_PRO` en el móvil obligaba a bajar media pantalla.
BACKUP_PARENT = "NEBULABS_AUTOMATED_TIKTOK"
BACKUP_DIR = "BACKUPS_Productos_Espana"
BACKUP_PREFIX = "BACKUP_Productos_Espana"


# Ruta (sin remote) de la carpeta que guarda todas las copias. La usa también
# la fuente "🗄️ Copia" para poder LEER de ahí cuando el Drive del curso borra
# una carpeta.
BACKUP_ROOT = f"{BACKUP_PARENT}/{BACKUP_DIR}"


def _destino(nombre: str) -> str:
    """Ruta rclone de una copia, ya dentro de la carpeta de backups."""
    return f"gdrive:{BACKUP_ROOT}/{nombre}"


def copias() -> list[str]:
    """Nombres de las copias guardadas, de la más nueva a la más vieja.

    Van en NUESTRO Drive, así que se listan SIN `--drive-shared-with-me`: con
    el flag puesto, "Mi unidad" no existe para rclone.
    """
    try:
        out = _rclone(["lsjson", _destino("").rstrip("/"), "--dirs-only"], timeout=120)
        return sorted(
            (d.get("Name", "") for d in json.loads(out or "[]") if d.get("Name")),
            reverse=True,
        )
    except Exception:  # noqa: BLE001
        return []


def ultima_completa() -> str:
    """La copia COMPLETA más reciente (las `_delta_` solo traen lo que cambió)."""
    return next(
        (c for c in copias() if c.startswith(BACKUP_PREFIX) and "_delta_" not in c),
        "",
    )


def _copias_utiles() -> list[str]:
    """Las copias que hay que mirar para reconstruir el archivo, de nueva a vieja.

    La completa NO basta: una carpeta que el curso subió y borró después solo
    está en el delta de aquel día (pasó con "10 Agosto 2026", que se copió el
    12 de agosto y ya no existe en el origen). Y los deltas tampoco bastan,
    porque solo traen lo que cambió. Así que se miran todas, de la más reciente
    a la más antigua, y gana la primera versión que aparece.

    Se corta en la última COMPLETA porque esa ya lo contenía todo *ese día*.
    Ojo: lo que el curso borró ANTES de esa copia no está en ninguna de las de
    aquí — para eso está `_copias_antiguas()`, que se mira solo cuando hace
    falta (listar carpetas y rescatar una que no aparezca).
    """
    todas = copias()
    completa = ultima_completa()
    if not completa:
        return todas
    return todas[: todas.index(completa) + 1]


def _copias_antiguas() -> list[str]:
    """Las anteriores a la última completa, de nueva a vieja.

    Guardan lo que el curso ya había borrado cuando se hizo esa copia completa:
    carpetas enteras que si no, desaparecían del navegador aunque siguieran
    guardadas en nuestro Drive.
    """
    todas = copias()
    completa = ultima_completa()
    if not completa or completa not in todas:
        return []
    return todas[todas.index(completa) + 1:]


def _limpiar_nombre(nombre: str) -> str:
    """Quita el `__<id>` que el backup añade a los nombres duplicados."""
    return re.sub(r"__[0-9A-Za-z_-]{8}(\.[^.]*)?$", lambda m: m.group(1) or "", nombre)


def carpetas_de(fuente: str) -> list[str]:
    """Carpetas de producto que hay en la copia, de una fuente del curso.

    Se miran TODAS las copias, también las anteriores a la última completa: una
    carpeta que el curso borró antes de aquel día no está en ninguna copia
    posterior, y aun así la tenemos guardada. Mirando solo desde la completa
    hacia acá, esas carpetas no salían en el navegador y parecía que la copia
    tenía menos cosas que el original.

    En orden NATURAL (1, 2, 10…), no alfabético: ordenando como texto, "10
    Agosto" se colaba entre "1 Pront Flow" y "2 Pront Flow".
    """
    from src.nicho_pov_bof import config as pov_config

    vistas: dict[str, None] = {}
    for copia in _copias_utiles() + _copias_antiguas():
        try:
            out = _rclone(
                ["lsjson", f"gdrive:{BACKUP_ROOT}/{copia}/{fuente}", "--dirs-only"],
                timeout=120,
            )
        except Exception:  # noqa: BLE001
            continue  # esa copia no llegó a tener esta fuente
        for d in json.loads(out or "[]"):
            if d.get("Name"):
                vistas.setdefault(d["Name"], None)
    return sorted(vistas, key=pov_config.natural_sort_key)


def fotos_de(fuente: str, carpeta: str) -> list[dict]:
    """Fotos de una carpeta en la copia, con el shape de `drive_client`.

    Gana la copia más reciente: si un fichero se modificó, la versión buena es
    la última que se guardó.
    """
    from src.nicho_pov_bof import config as pov_config

    salida: dict[str, dict] = {}

    def _mirar(copias_a_mirar: list[str]) -> None:
        for copia in copias_a_mirar:
            try:
                out = _rclone(
                    [
                        "lsjson",
                        f"gdrive:{BACKUP_ROOT}/{copia}/{fuente}/{carpeta}",
                        "--files-only",
                    ],
                    timeout=120,
                )
            except Exception:  # noqa: BLE001
                continue
            for it in json.loads(out or "[]"):
                nombre, fid = it.get("Name") or "", it.get("ID") or ""
                if not nombre or not fid or nombre in salida:
                    continue
                limpio = _limpiar_nombre(nombre)
                if not pov_config.is_image(limpio, it.get("MimeType", "")):
                    continue
                salida[nombre] = {
                    "id": fid,
                    "name": limpio,
                    "size": int(it.get("Size") or 0),
                    "mime": it.get("MimeType", ""),
                    "mtime": it.get("ModTime", ""),
                }

    _mirar(_copias_utiles())
    # Solo si la carpeta no aparecía en las copias recientes: entonces es de
    # las que el curso borró ANTES de la última completa y hay que ir a buscarla
    # más atrás. Mirar siempre en todas serían decenas de llamadas a rclone cada
    # vez que se abre una carpeta.
    if not salida:
        _mirar(_copias_antiguas())

    fotos = list(salida.values())
    fotos.sort(key=lambda p: pov_config.natural_sort_key(p["name"]))
    return fotos

# Si cambia más de esta fracción del archivo, sale más a cuenta una copia
# completa nueva que un delta gigante.
FULL_COPY_RATIO = float(os.getenv("NICHO_POV_BOF_FULL_COPY_RATIO") or 0.40)


def _rclone(args: list[str], *, timeout: float = 1800, on_log: OnLog = _noop) -> str:
    cmd = ["rclone", *args]
    conf = config.rclone_config_path()
    if conf:
        cmd += ["--config", conf]
    on_log("+ " + " ".join(cmd[:6]) + (" …" if len(cmd) > 6 else ""))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise RuntimeError("rclone no está instalado en este entorno.") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"rclone excedió {timeout:.0f}s: {' '.join(args[:2])}") from None
    if proc.returncode != 0:
        raise RuntimeError(f"rclone falló ({' '.join(args[:2])}): {proc.stderr[-400:]}")
    return proc.stdout


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------
def snapshot_dir() -> Path:
    root = os.getenv("API_TEMP_ROOT") or "temp_work"
    d = Path(root) / "nicho_pov_bof_backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _id_copiable(fid: str) -> str:
    """ID que entiende `backend copyid`.

    Para los ACCESOS DIRECTOS de Drive, rclone devuelve en `lsjson` un ID
    compuesto `idAtajo\tidDestino`. Pasarlo tal cual a `copyid` falla
    ("failed copyid"), y en `Productos España` hay dos atajos, así que el
    backup diario moría con 2 fallos de 2. Lo que hay que copiar es el
    fichero al que apunta el atajo, o sea el trozo de después del tabulador.

    El snapshot SÍ se sigue indexando por el ID compuesto: identifica al
    objeto tal y como lo ve el origen y así el diff no se confunde.
    """
    return fid.rsplit("\t", 1)[-1]


def take_snapshot(*, on_log: OnLog = _noop) -> dict:
    """Listado completo del origen indexado por file ID."""
    on_log("[backup] listando el origen (recursivo)…")
    raw = _rclone(["lsjson", SRC_PATH, "--recursive", "--files-only"], on_log=on_log)
    items = json.loads(raw or "[]")
    snap: dict[str, dict] = {}
    for it in items:
        fid = it.get("ID")
        if not fid:
            continue
        snap[fid] = {
            "path": it.get("Path", ""),
            "size": int(it.get("Size") or 0),
            "mtime": it.get("ModTime", ""),
        }
    on_log(f"[backup] {len(snap)} objetos en el origen")
    return snap


def save_snapshot(snap: dict, tag: str) -> Path:
    p = snapshot_dir() / f"snapshot_{tag}.json"
    p.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return p


def load_latest_snapshot() -> tuple[str | None, dict]:
    """(tag, snapshot) del snapshot más reciente, o (None, {}) si no hay."""
    snaps = sorted(snapshot_dir().glob("snapshot_*.json"))
    if not snaps:
        return None, {}
    latest = snaps[-1]
    tag = latest.stem.replace("snapshot_", "")
    try:
        return tag, json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, {}


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------
def diff_snapshots(old: dict, new: dict) -> dict:
    """Qué ha cambiado entre dos snapshots (identidad = file ID).

    `deleted` es informativo: en un backup los ficheros borrados en el origen
    se CONSERVAN — precisamente de eso va tener una copia.
    """
    old_ids, new_ids = set(old), set(new)
    added = sorted(new_ids - old_ids)
    deleted = sorted(old_ids - new_ids)
    modified = sorted(
        i for i in (old_ids & new_ids)
        if old[i].get("size") != new[i].get("size")
        or old[i].get("mtime") != new[i].get("mtime")
    )
    changed = len(added) + len(modified)
    total = max(len(new_ids), 1)
    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "n_added": len(added),
        "n_modified": len(modified),
        "n_deleted": len(deleted),
        "n_total_source": len(new_ids),
        "change_ratio": changed / total,
        "has_changes": bool(added or modified or deleted),
    }


# ---------------------------------------------------------------------------
# Copia
# ---------------------------------------------------------------------------
def _dest_name(path: str, file_id: str, dup_paths: set[str]) -> str:
    """Nombre destino; desambigua solo si esa ruta está duplicada en origen."""
    if path not in dup_paths:
        return path
    parent, _, name = path.rpartition("/")
    stem, dot, ext = name.rpartition(".")
    if not stem:
        stem, dot, ext = name, "", ""
    new_name = f"{stem}__{file_id[:8]}{dot}{ext}"
    return f"{parent}/{new_name}" if parent else new_name


def _duplicated_paths(snap: dict) -> set[str]:
    seen: dict[str, int] = {}
    for meta in snap.values():
        p = meta.get("path", "")
        seen[p] = seen.get(p, 0) + 1
    return {p for p, n in seen.items() if n > 1}


def copy_by_ids(
    file_ids: list[str],
    snap: dict,
    dest_root: str,
    *,
    on_log: OnLog = _noop,
    on_progress: Callable[[float, str], None] | None = None,
) -> dict:
    """Copia server-side los IDs dados a `dest_root`, preservando rutas."""
    dup_paths = _duplicated_paths(snap)
    ok = failed = 0
    errors: list[str] = []
    fallidos: list[str] = []
    total = max(len(file_ids), 1)

    for i, fid in enumerate(file_ids, 1):
        meta = snap.get(fid) or {}
        path = meta.get("path") or fid
        dest = f"{dest_root}/{_dest_name(path, fid, dup_paths)}"
        try:
            _rclone(
                ["backend", "copyid", SRC_REMOTE, _id_copiable(fid), dest],
                timeout=900, on_log=_noop,
            )
            ok += 1
        except RuntimeError as e:
            failed += 1
            fallidos.append(fid)
            if len(errors) < 10:
                errors.append(f"{path}: {e}")
        if on_progress and (i % 10 == 0 or i == len(file_ids)):
            on_progress(i / total, f"copiando {i}/{len(file_ids)}")
        if i % 100 == 0:
            on_log(f"[backup] {i}/{len(file_ids)} · {ok} ok · {failed} fallos")

    return {"copied": ok, "failed": failed, "errors": errors, "fallidos": fallidos}


def run_sync(
    *,
    force_full: bool = False,
    on_log: OnLog = _noop,
    on_progress: Callable[[float, str], None] | None = None,
) -> dict:
    """Comprueba cambios y copia lo que falte.

    - Sin snapshot previo, o cambio > FULL_COPY_RATIO, o `force_full`:
      copia COMPLETA a `BACKUP_Productos_Espana_<fecha>`.
    - Si no: copia solo added+modified a `..._delta_<fecha>`.
    """
    prog = on_progress or (lambda *_: None)
    tag = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    fecha = tag.split("_")[0]

    prog(0.05, "Listando el origen…")
    new_snap = take_snapshot(on_log=on_log)
    old_tag, old_snap = load_latest_snapshot()

    d = diff_snapshots(old_snap, new_snap)
    on_log(
        f"[backup] vs snapshot {old_tag or '(ninguno)'}: "
        f"+{d['n_added']} nuevos · ~{d['n_modified']} modificados · "
        f"-{d['n_deleted']} borrados en origen ({d['change_ratio']:.0%} del archivo)"
    )

    if not old_snap:
        reason = "no había copia previa"
        full = True
    elif force_full:
        reason = "copia completa forzada"
        full = True
    elif d["change_ratio"] > FULL_COPY_RATIO:
        reason = f"cambió el {d['change_ratio']:.0%} (> {FULL_COPY_RATIO:.0%})"
        full = True
    else:
        reason = "cambios acotados"
        full = False

    if not d["has_changes"] and old_snap:
        on_log("[backup] sin cambios — no se copia nada")
        save_snapshot(new_snap, tag)
        prog(1.0, "Sin cambios")
        return {
            "mode": "none", "reason": "sin cambios", "tag": tag,
            "dest": None, "copied": 0, "failed": 0, **_counts(d),
        }

    if full:
        dest = _destino(f"{BACKUP_PREFIX}_{fecha}")
        ids = sorted(new_snap)
        on_log(f"[backup] copia COMPLETA ({reason}) → {dest}")
    else:
        dest = _destino(f"{BACKUP_PREFIX}_delta_{fecha}")
        ids = d["added"] + d["modified"]
        on_log(f"[backup] copia DELTA ({reason}, {len(ids)} ficheros) → {dest}")

    prog(0.15, f"Copiando {len(ids)} ficheros…")
    res = copy_by_ids(ids, new_snap, dest, on_log=on_log, on_progress=lambda f, m: prog(0.15 + f * 0.8, m))

    # Los que fallaron NO entran en el snapshot: si entrasen quedarían
    # marcados como copiados y la siguiente ejecución ya no los vería como
    # nuevos, así que no se reintentarían JAMÁS. Pasó de verdad — el backup
    # del 30/07 no supo copiar dos accesos directos y aun así los dio por
    # guardados. Dejándolos fuera, mañana vuelven a salir como pendientes.
    a_guardar = {k: v for k, v in new_snap.items() if k not in set(res["fallidos"])}
    save_snapshot(a_guardar, tag)
    prog(1.0, f"{res['copied']} copiados, {res['failed']} fallos")

    if res["failed"]:
        on_log(f"[backup] ⚠️ {res['failed']} ficheros fallaron: {res['errors'][:5]}")

    return {
        "mode": "full" if full else "delta",
        "reason": reason,
        "tag": tag,
        "dest": dest,
        **_counts(d),
        **res,
    }


_ULTIMA = "backup:ultima"


def guardar_ultima(result: dict) -> None:
    """Deja constancia de la última copia para poder enseñarla.

    Interesa sobre todo `n_deleted`: es la única señal de que el admin del
    Drive del curso ha borrado cosas, y hasta ahora solo se veía en el log del
    job (que nadie mira). Nunca lanza: es informativo.
    """
    try:
        from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis
        import time as _time

        get_nicho_pov_bof_redis().set_json(_ULTIMA, {
            "ts": _time.time(),
            "mode": result.get("mode", ""),
            "n_added": int(result.get("n_added") or 0),
            "n_modified": int(result.get("n_modified") or 0),
            "n_deleted": int(result.get("n_deleted") or 0),
            "copied": int(result.get("copied") or 0),
            "failed": int(result.get("failed") or 0),
        })
    except Exception:  # noqa: BLE001
        pass


def ultima() -> dict:
    """Lo que hizo la última copia. `{}` si no hay ninguna registrada."""
    try:
        from src.nicho_pov_bof.repos.redis_base import get_nicho_pov_bof_redis

        return get_nicho_pov_bof_redis().get_json(_ULTIMA) or {}
    except Exception:  # noqa: BLE001
        return {}


def _counts(d: dict) -> dict:
    return {
        "n_added": d["n_added"],
        "n_modified": d["n_modified"],
        "n_deleted": d["n_deleted"],
        "n_total_source": d["n_total_source"],
        "change_ratio": round(d["change_ratio"], 4),
    }


# ---------------------------------------------------------------------------
# Paquete para DEVOLVER el material
# ---------------------------------------------------------------------------
# Nuestro archivo son una copia completa + los deltas de cada día: sirve para
# trabajar, pero no para DAR. Si el dueño del Drive de origen lo pierde (pasó
# el 19-08-2026: le entraron en el correo y se quedó sin acceso), lo que hay
# que poder pasarle es UNA carpeta con la estructura tal y como estaba.
#
# Se vuelca de la copia más VIEJA a la más nueva para que, cuando un fichero
# esté en varias, gane la última versión.
PAQUETE_PREFIX = "PAQUETE_Productos_Espana"


def _paquete_root(tag: str = "") -> str:
    nombre = f"{PAQUETE_PREFIX}_{tag}" if tag else PAQUETE_PREFIX
    return f"{BACKUP_PARENT}/{nombre}"


def paquetes() -> list[str]:
    """Paquetes ya montados, del más nuevo al más viejo."""
    try:
        out = _rclone(["lsjson", f"gdrive:{BACKUP_PARENT}", "--dirs-only"], timeout=120)
        return sorted(
            (str(d["Name"]) for d in json.loads(out or "[]")
             if str(d.get("Name", "")).startswith(PAQUETE_PREFIX)),
            reverse=True,
        )
    except Exception:  # noqa: BLE001
        return []


def paquete_actual() -> dict:
    """El último paquete montado: `{carpeta, ficheros, bytes}`. Vacío si no hay."""
    todos = paquetes()
    if not todos:
        return {}
    ruta = f"{BACKUP_PARENT}/{todos[0]}"
    try:
        datos = json.loads(_rclone(["size", f"gdrive:{ruta}", "--json"], timeout=600) or "{}")
    except Exception:  # noqa: BLE001
        datos = {}
    return {
        "carpeta": ruta,
        "ficheros": int(datos.get("count") or 0),
        "bytes": int(datos.get("bytes") or 0),
    }


def construir_paquete(
    *, on_log: OnLog = _noop, on_progress: Callable[[float, str], None] | None = None,
) -> dict:
    """Junta todas las copias en UNA carpeta con el árbol original."""
    prog = on_progress or (lambda *_: None)
    tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    destino = f"gdrive:{_paquete_root(tag)}"
    todas = sorted(copias())
    if not todas:
        raise RuntimeError("No hay ninguna copia guardada todavía.")
    for i, copia in enumerate(todas, 1):
        on_log(f"[paquete] volcando {copia} ({i}/{len(todas)})…")
        prog(i / (len(todas) + 1), f"volcando {copia}")
        _rclone(
            ["copy", f"gdrive:{BACKUP_ROOT}/{copia}", destino,
             "--transfers", "8", "--checkers", "8"],
            timeout=7200, on_log=_noop,
        )
    prog(0.98, "contando lo copiado")
    datos = json.loads(_rclone(["size", destino, "--json"], timeout=600) or "{}")
    on_log(
        f"[paquete] listo: {datos.get('count', 0)} ficheros, "
        f"{(datos.get('bytes') or 0) / 2**30:.2f} GiB en {destino}"
    )
    return {
        "carpeta": _paquete_root(tag),
        "ficheros": int(datos.get("count") or 0),
        "bytes": int(datos.get("bytes") or 0),
        "copias_volcadas": len(todas),
    }


# rclone solo sabe hacer enlaces públicos, y esto no es para publicarlo: es
# para dárselo a UNA persona. Se llama a la API de Drive con el mismo token
# que ya usa el backup (`rclone config dump`), que tiene scope `drive`.
def _token_drive() -> str:
    # Con `--config`: dentro del contenedor la configuración de rclone está
    # montada en `/app/secrets/`, no en el HOME, y sin decírselo `config dump`
    # devuelve `{}` y esto fallaba con "no hay token".
    cmd = ["rclone", "config", "dump"]
    conf = config.rclone_config_path()
    if conf:
        cmd += ["--config", conf]
    salida = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if salida.returncode != 0:
        raise RuntimeError("No se pudo leer la configuración de rclone.")
    cfg = json.loads(salida.stdout or "{}").get("gdrive") or {}
    tok = json.loads(cfg.get("token") or "{}")
    if not tok.get("access_token"):
        raise RuntimeError("La cuenta de Drive no tiene token; reconecta rclone.")
    return str(tok["access_token"])


def id_de_carpeta(ruta: str) -> str:
    """ID de una carpeta de NUESTRO Drive (`lsjson --stat` no lo trae)."""
    padre, _, nombre = ruta.rpartition("/")
    out = _rclone(["lsjson", f"gdrive:{padre}", "--dirs-only"], timeout=300)
    for d in json.loads(out or "[]"):
        if d.get("Name") == nombre:
            return str(d.get("ID") or "")
    return ""


def id_de_enlace(enlace: str) -> str:
    """El identificador de carpeta que lleva dentro un enlace de Drive.

    Se acepta el enlace entero porque es lo que se copia del navegador; si ya
    viene el identificador suelto, se devuelve tal cual.
    """
    texto = (enlace or "").strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]{10,})", texto)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", texto)
    if m:
        return m.group(1)
    return texto if re.fullmatch(r"[A-Za-z0-9_-]{10,}", texto) else ""


def volcar_paquete(
    enlace: str, *, on_log: OnLog = _noop,
    on_progress: Callable[[float, str], None] | None = None,
) -> dict:
    """Copia el paquete DENTRO de una carpeta que nos hayan compartido.

    Es la forma sencilla de devolverle el material a alguien sin que tenga que
    autorizar nada raro: crea una carpeta vacía en SU Drive, nos la comparte
    como editor y pega aquí el enlace. Lo que se copia nace siendo suyo, no es
    un acceso compartido que pueda perder.
    """
    prog = on_progress or (lambda *_: None)
    fid = id_de_enlace(enlace)
    if not fid:
        raise RuntimeError(f"De ahí no sale ningún enlace de carpeta: {enlace!r}")
    actual = paquete_actual()
    if not actual.get("carpeta"):
        raise RuntimeError("No hay paquete montado todavía.")

    prog(0.05, "comprobando la carpeta de destino")
    try:
        _rclone(["lsf", f"gdrive,root_folder_id={fid}:", "--max-depth", "1"], timeout=300)
    except RuntimeError as e:
        raise RuntimeError(
            "No puedo abrir esa carpeta. Que la compartan con esta cuenta "
            f"como EDITOR y vuelve a intentarlo. ({e})"
        ) from e

    on_log(f"[paquete] volcando {actual['carpeta']} en la carpeta {fid}…")
    prog(0.1, "copiando (servidor a servidor)")
    _rclone(
        ["copy", f"gdrive:{actual['carpeta']}", f"gdrive,root_folder_id={fid}:",
         "--drive-server-side-across-configs", "--transfers", "8", "--checkers", "8"],
        timeout=14400, on_log=_noop,
    )
    datos = json.loads(
        _rclone(["size", f"gdrive,root_folder_id={fid}:", "--json"], timeout=600) or "{}"
    )
    on_log(f"[paquete] en destino hay ya {datos.get('count', 0)} ficheros")
    return {
        "destino": fid,
        "ficheros": int(datos.get("count") or 0),
        "bytes": int(datos.get("bytes") or 0),
        "enlace": f"https://drive.google.com/drive/folders/{fid}",
    }


def compartir(ruta: str, correo: str, *, rol: str = "reader") -> dict:
    """Da acceso a un correo a una carpeta nuestra. Devuelve el enlace."""
    import urllib.error
    import urllib.request

    correo = (correo or "").strip()
    if "@" not in correo:
        raise RuntimeError(f"Eso no es un correo: {correo!r}")
    if rol not in ("reader", "writer"):
        rol = "reader"
    fid = id_de_carpeta(ruta)
    if not fid:
        raise RuntimeError(f"No encuentro la carpeta {ruta!r} en el Drive.")
    req = urllib.request.Request(
        f"https://www.googleapis.com/drive/v3/files/{fid}/permissions"
        "?sendNotificationEmail=true&supportsAllDrives=true",
        data=json.dumps({"role": rol, "type": "user", "emailAddress": correo}).encode(),
        headers={
            "Authorization": f"Bearer {_token_drive()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Drive no dejó compartir ({e.code}): {e.read().decode()[:200]}"
        ) from e
    return {
        "carpeta": ruta,
        "correo": correo,
        "rol": rol,
        "enlace": f"https://drive.google.com/drive/folders/{fid}",
    }


def check_only(*, on_log: OnLog = _noop) -> dict:
    """Diff sin copiar nada (para el botón "comprobar cambios")."""
    new_snap = take_snapshot(on_log=on_log)
    old_tag, old_snap = load_latest_snapshot()
    d = diff_snapshots(old_snap, new_snap)
    return {
        "last_snapshot": old_tag,
        "has_changes": d["has_changes"] or not old_snap,
        "would_be_full": (not old_snap) or d["change_ratio"] > FULL_COPY_RATIO,
        "full_copy_ratio": FULL_COPY_RATIO,
        **_counts(d),
    }
