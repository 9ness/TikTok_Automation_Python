"""Paths y constantes del programa Editor Auto.

Decisiones:
- TIKTOK_EDITOR es HERMANO de TIKTOK_CR y TIKTOK_SHOP en Drive:
    Mi unidad/NEBULABS_AUTOMATED_TIKTOK/
    ├── TIKTOK_CR/TIKTOK_ASSETS/   (Programa 1)
    ├── TIKTOK_SHOP/                (Programa 2)
    └── TIKTOK_EDITOR/              (Programa 3 — éste)
- Dentro de TIKTOK_EDITOR/ vive `Usuarios/<nombre>/{entrada,salida}/`.
- Redis prefix `editor_auto:` (aislado de CR `betai:` y Shop `tiktok_shop:`).
"""

from __future__ import annotations

import os
import string
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_TIKTOK_EDITOR_RELATIVE_CANDIDATES = (
    os.path.join("Mi unidad", "NEBULABS_AUTOMATED_TIKTOK", "TIKTOK_EDITOR"),
    os.path.join("NEBULABS_AUTOMATED_TIKTOK", "TIKTOK_EDITOR"),
)
_TIKTOK_PARENT_RELATIVE_CANDIDATES = (
    os.path.join("Mi unidad", "NEBULABS_AUTOMATED_TIKTOK"),
    "NEBULABS_AUTOMATED_TIKTOK",
)


def _scan_roots() -> list[str]:
    """Raíces de unidades / mounts donde buscar Drive."""
    if os.name == "nt":
        return [f"{letter}:\\" for letter in string.ascii_uppercase]
    home = os.path.expanduser("~")
    roots = [
        os.path.join(home, "gdrive"),
        "/mnt/gdrive",
        "/srv/gdrive",
        "/mnt/drive",     # mount estándar del docker-compose
        home,
        "/",
    ]
    media_root = "/media"
    if os.path.isdir(media_root):
        try:
            for sub in os.listdir(media_root):
                p = os.path.join(media_root, sub, "gdrive")
                if os.path.isdir(p):
                    roots.append(p)
        except OSError:
            pass
    return roots


def _autodetect_editor_root() -> str | None:
    """Busca una carpeta TIKTOK_EDITOR YA existente."""
    for root in _scan_roots():
        if not os.path.exists(root):
            continue
        for relative in _TIKTOK_EDITOR_RELATIVE_CANDIDATES:
            candidate = os.path.join(root, relative)
            if os.path.isdir(candidate):
                return candidate
    return None


def _autodetect_parent() -> str | None:
    """Busca la carpeta PADRE `NEBULABS_AUTOMATED_TIKTOK` aunque TIKTOK_EDITOR
    aún no exista. Si la encontramos, TIKTOK_EDITOR se creará dentro como
    HERMANA de TIKTOK_CR/TIKTOK_SHOP (auto-creación lazy)."""
    for root in _scan_roots():
        if not os.path.exists(root):
            continue
        for relative in _TIKTOK_PARENT_RELATIVE_CANDIDATES:
            candidate = os.path.join(root, relative)
            if os.path.isdir(candidate):
                return candidate
    return None


def resolve_editor_root() -> str:
    """Devuelve la ruta raíz de `TIKTOK_EDITOR/`.

    Orden de resolución:
      1) `TIKTOK_EDITOR_ROOT_PATH` env si apunta a una carpeta existente.
      2) Auto-detección de carpeta TIKTOK_EDITOR ya creada.
      3) Auto-detección del PADRE `NEBULABS_AUTOMATED_TIKTOK` y creación
         lazy de TIKTOK_EDITOR dentro (hermana de TIKTOK_CR/TIKTOK_SHOP).
      4) Fallback `./TIKTOK_EDITOR_FALLBACK/` (dev local sin Drive).
    """
    env_path = os.getenv("TIKTOK_EDITOR_ROOT_PATH")
    if env_path:
        if os.path.isdir(env_path):
            return env_path
        # La carpeta aún no existe (primera ejecución en el server, p. ej.).
        # Intentamos crearla si su PADRE existe (NEBULABS_AUTOMATED_TIKTOK
        # del Drive montado) — así el deploy no necesita pre-crear la
        # carpeta manualmente.
        parent_of_env = os.path.dirname(env_path)
        if parent_of_env and os.path.isdir(parent_of_env):
            try:
                Path(env_path).mkdir(parents=True, exist_ok=True)
                return env_path
            except OSError as e:
                print(
                    f"[editor_auto.config] TIKTOK_EDITOR_ROOT_PATH apunta a "
                    f"'{env_path}' pero no se pudo crear: {e}"
                )

    detected = _autodetect_editor_root()
    if detected:
        os.environ["TIKTOK_EDITOR_ROOT_PATH"] = detected
        return detected

    # NUEVO: si el padre existe, creamos TIKTOK_EDITOR como hermana de
    # TIKTOK_CR / TIKTOK_SHOP en lugar de caer al fallback local.
    parent = _autodetect_parent()
    if parent:
        candidate = os.path.join(parent, "TIKTOK_EDITOR")
        try:
            Path(candidate).mkdir(parents=True, exist_ok=True)
            os.environ["TIKTOK_EDITOR_ROOT_PATH"] = candidate
            return candidate
        except OSError as e:
            print(f"[editor_auto.config] No se pudo crear TIKTOK_EDITOR en {parent}: {e}")

    return os.path.abspath("./TIKTOK_EDITOR_FALLBACK")


def editor_root_path() -> Path:
    return Path(resolve_editor_root())


def ensure_editor_root() -> str:
    """Garantiza la existencia de la raíz + carpeta `Usuarios/`."""
    root = resolve_editor_root()
    Path(root).mkdir(parents=True, exist_ok=True)
    Path(root, "Usuarios").mkdir(exist_ok=True)
    return root


def assets_folder() -> str:
    """Carpeta `Assets/` global del Editor Auto. Aloja recursos compartidos
    entre usuarios (stickers, logos, fuentes, etc.) que no son output de
    un job ni input subido por el usuario."""
    return os.path.join(resolve_editor_root(), "Assets")


def arrows_folder() -> str:
    """Subcarpeta `Assets/flechas/` con los stickers de flecha disponibles
    (MOV/WebM/GIF con alpha). El operador deposita aquí sus assets a mano,
    la tool `sticker_arrow` los lista vía API y el frontend deja al usuario
    elegir uno por su nombre de archivo."""
    return os.path.join(assets_folder(), "flechas")


def user_folder(username: str) -> str:
    """Carpeta del usuario (sin crear)."""
    return os.path.join(resolve_editor_root(), "Usuarios", username)


def user_output_folder(username: str) -> str:
    """Carpeta de salida (donde se copia el MP4 final)."""
    return os.path.join(user_folder(username), "salida")


def user_input_folder(username: str) -> str:
    """Carpeta de entrada — el cliente deposita sus vídeos crudos aquí.
    El admin los ve listados en la UI y los encola desde ahí."""
    return os.path.join(user_folder(username), "entrada")


def is_valid_day(day: str) -> bool:
    """Valida que `day` sea una fecha YYYY-MM-DD (defensa path-traversal)."""
    import re
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or ""):
        return False
    from datetime import datetime
    try:
        datetime.strptime(day, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def user_input_day_folder(username: str, day: str) -> str:
    """Subcarpeta de `entrada/` por DÍA de publicación (`entrada/<YYYY-MM-DD>/`).

    Los clientes de la web suben aquí sus vídeos para un día concreto. El
    watcher de auto-encolado NO escanea subcarpetas, así que estos vídeos
    quedan en "borrador" hasta que el cliente pulsa "Mandar a edición" (que
    los encola explícitamente). Lanza ValueError si `day` no es una fecha."""
    if not is_valid_day(day):
        raise ValueError(f"Día inválido (esperado YYYY-MM-DD): {day!r}")
    return os.path.join(user_input_folder(username), day)


def user_output_day_folder(username: str, day: str) -> str:
    """Subcarpeta de `salida/` por DÍA (`salida/<YYYY-MM-DD>/`) — espejo de
    `entrada/<día>/`. El cliente ve sus vídeos editados agrupados por día.
    Lanza ValueError si `day` no es una fecha."""
    if not is_valid_day(day):
        raise ValueError(f"Día inválido (esperado YYYY-MM-DD): {day!r}")
    return os.path.join(user_output_folder(username), day)


def user_queue_folder(username: str) -> str:
    """Carpeta de cola — al encolar un vídeo desde `entrada/`, se MUEVE
    aquí para `lockearlo` (el cliente no debería tocar archivos en
    procesamiento). Tras éxito → `recuperacion/`. Tras fallo → `entrada/`."""
    return os.path.join(user_folder(username), "cola")


def user_recovery_folder(username: str) -> str:
    """Carpeta de recuperación — guarda los ORIGINALES tras procesado OK,
    por si el operador necesita re-editar (mover de vuelta a `entrada/`)
    o borrarlos cuando no los necesita."""
    return os.path.join(user_folder(username), "recuperacion")


_VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")


def count_output_videos_today(username: str) -> int | None:
    """Cuenta los vídeos en `salida/` MODIFICADOS hoy (fecha local).

    Sirve para el aviso "vídeos del día listos": refleja lo realmente editado
    HOY, ignorando archivos que se quedaran de días anteriores sin borrar.
    Devuelve el nº, o None si la carpeta no existe / no se puede leer.
    """
    from datetime import datetime
    folder = user_output_folder(username)
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    today = datetime.now().date()
    n = 0
    for name in names:
        if os.path.splitext(name)[1].lower() not in _VIDEO_EXTS:
            continue
        try:
            mtime = datetime.fromtimestamp(
                os.path.getmtime(os.path.join(folder, name))
            ).date()
        except OSError:
            continue
        if mtime == today:
            n += 1
    return n


# Slugs canónicos de las 4 carpetas — el frontend los usa como IDs en
# las URLs y los validamos contra esta whitelist en el backend.
USER_FOLDERS = ("entrada", "cola", "recuperacion", "salida")


def user_subfolder(username: str, folder: str) -> str:
    """Resuelve una subcarpeta del usuario por nombre (`entrada`/`cola`/
    `recuperacion`/`salida`). Lanza `ValueError` si `folder` no está en
    la whitelist — defensa contra path traversal."""
    if folder not in USER_FOLDERS:
        raise ValueError(
            f"Carpeta no permitida: {folder!r} (válidas: {USER_FOLDERS})"
        )
    return os.path.join(user_folder(username), folder)


def ensure_user_folders(username: str) -> tuple[str, str, str, str, str]:
    """Crea las carpetas del usuario si no existen.

    Devuelve `(base, entrada, cola, recuperacion, salida)`. Idempotente —
    se invoca al crear/editar el usuario y también al ejecutar un job
    (defensivo). Las carpetas vacías no rompen Drive sync.
    """
    base = user_folder(username)
    Path(base).mkdir(parents=True, exist_ok=True)
    inp = user_input_folder(username)
    queue = user_queue_folder(username)
    recovery = user_recovery_folder(username)
    out = user_output_folder(username)
    for p in (inp, queue, recovery, out):
        Path(p).mkdir(parents=True, exist_ok=True)
    return base, inp, queue, recovery, out


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
def redis_prefix() -> str:
    """Prefijo Redis del programa. Default `editor_auto:`."""
    return os.getenv("EDITOR_AUTO_REDIS_PREFIX") or "editor_auto:"


# ---------------------------------------------------------------------------
# Herramientas — slugs canónicos (registry los expone con su impl)
# ---------------------------------------------------------------------------
TOOL_SUBS_AUTO = "subs_auto"
TOOL_SILENCE_CUTTER = "silence_cutter"
TOOL_SILENCE_CUTTER_SCRIPTED = "silence_cutter_scripted"
TOOL_STICKER_ARROW = "sticker_arrow"
TOOL_PHOTO_INSERT = "photo_insert"

# Grupos de herramientas mutuamente excluyentes — el validador del repo
# rechaza un `tool_flow` que tenga dos tools del mismo grupo. Ambos
# silence cutters ocupan el mismo slot semántico (cortar audio/vídeo) y
# tener los dos en el flujo no tiene sentido: la primera mutila el input
# de la segunda.
TOOL_EXCLUSIVE_GROUPS: list[set[str]] = [
    {TOOL_SILENCE_CUTTER, TOOL_SILENCE_CUTTER_SCRIPTED},
]

# Orden fijo por position_weight: lower = se ejecuta antes.
# El orchestrator usa estos pesos para reordenar el flujo independientemente
# del orden en que el usuario añade las herramientas en la UI.
#
# Razonamiento:
# - `silence_cutter` (10): TIENE que ir antes que cualquier overlay porque
#   corta el vídeo (audio+vídeo) y modifica timestamps. Si va después de
#   subs, los subs quedan colgando sobre fotogramas eliminados.
# - `subs_auto` (90): SIEMPRE al final — overlay puro, no toca timestamps.
TOOL_POSITION_WEIGHTS: dict[str, int] = {
    TOOL_SILENCE_CUTTER: 10,
    TOOL_SILENCE_CUTTER_SCRIPTED: 10,
    # 80: sticker overlay después de cortes (timestamps ya estables) y
    # antes de subs (90) para que los subtítulos queden ENCIMA del sticker
    # si colisionan — la legibilidad del texto prima sobre la flecha.
    # 70: fotos de famosos/marcas después de cortes (timestamps estables) y
    # antes de flecha (80) y subs (90) para que esos queden ENCIMA de la foto.
    TOOL_PHOTO_INSERT: 70,
    TOOL_STICKER_ARROW: 80,
    TOOL_SUBS_AUTO: 90,
}
DEFAULT_TOOL_WEIGHT = 50
