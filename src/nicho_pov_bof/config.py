"""Config del Nicho POV BOF (Programa 4 — Tiktok Shop AI Pro).

FASE 1: solo lectura del Drive compartido "Productos España" + tracking de
carpetas ya completadas. Todavía NO genera vídeos.

Decisiones:
- El Drive de productos está COMPARTIDO CONMIGO (shared-with-me), no vive en
  "Mi unidad" → NO se ve por el mount FUSE de `gdrive-mount.service`. Hay que
  leerlo por CLI con `--drive-shared-with-me` (ver `services/drive_client.py`).
- "Productos España" es SOLO LECTURA. El pipeline nunca escribe ahí.
- El estado "completada" vive en Redis (prefijo `nicho_pov_bof:`), NO en Drive
  — así no ensuciamos un Drive de terceros.
- Las fotos tienen NOMBRES DUPLICADOS reales dentro de una misma carpeta
  (`2.PNG` dos veces, `10.PNG` vs `10.png`). Por eso el identificador canónico
  de una foto es su **file ID de Drive**, nunca su nombre.
- Las salidas futuras (fase 2) irán bajo TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF/,
  mismo patrón que VIRALIZACION.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil

# ---------------------------------------------------------------------------
# Drive de origen (SOLO LECTURA)
# ---------------------------------------------------------------------------
DRIVE_REMOTE = "gdrive:"

# Carpeta raíz compartida. Ojo: lleva tilde, es el nombre real en Drive.
SHARED_ROOT = "Productos España"

# Flag de backend rclone que convierte "Compartido conmigo" en la raíz del
# remote. Sin esto la carpeta no existe para rclone.
SHARED_WITH_ME_FLAG = "--drive-shared-with-me"

# Fuentes de producto (las 2 que pidió el usuario). El `slug` es lo que viaja
# por la API; el `folder` es el nombre literal en Drive.
SOURCES: dict[str, dict[str, str]] = {
    "aleatorios_1": {
        "label": "1 Prod Aleatorios",
        "folder": "1 Prod Aleatorios",
    },
    "aleatorios_2": {
        "label": "2 Prod Aleatorios 2",
        "folder": "2 Prod Aleatorios 2",
    },
    # Los productos que sube el OPERADOR, no los del Drive del curso. Viven en
    # SU Drive (el montado), no en el compartido, así que se leen del mount y
    # no por rclone: `propia` es lo que activa esa rama en `drive_client`.
    #
    # Las fotos se guardan con el MISMO convenio de nombres que el Drive
    # compartido (`3.png` = limpia, `3(1).png` = ficha). Gracias a eso, todo lo
    # de después —emparejado, textos, ficha, escaparate, vendidos, montaje—
    # funciona sin una sola línea extra.
    "mis_productos": {
        "label": "Mis productos",
        "folder": "mis_productos",
        "propia": "1",
    },
    # Los que YA vendieron, copiados aquí desde su carpeta de origen para
    # volver a grabarlos. También es "propia" (vive en el Drive montado) y usa
    # el mismo convenio de nombres, así que no necesita nada especial.
    "top_vendidos": {
        "label": "Top vendidos",
        "folder": "top_vendidos",
        "propia": "1",
    },
    # La COPIA de seguridad del Drive del curso, de solo lectura. El admin de
    # aquel Drive borra carpetas cada cierto tiempo y entonces sus productos
    # desaparecen de la pantalla aunque estén guardados en nuestro Drive: estas
    # dos fuentes los vuelven a hacer accesibles: leen la última copia completa
    # MÁS los deltas posteriores (ver `backup_sync._copias_utiles`), porque una
    # carpeta que se subió y se borró después solo está en un delta.
    "backup_1": {
        "label": "🗄️ Copia · 1 Prod Aleatorios",
        "folder": "1 Prod Aleatorios",
        "backup": "1",
        # El progreso NO es de esta fuente: es la misma carpeta del curso.
        "canonica": "aleatorios_1",
    },
    "backup_2": {
        "label": "🗄️ Copia · 2 Prod Aleatorios 2",
        "folder": "2 Prod Aleatorios 2",
        "backup": "1",
        "canonica": "aleatorios_2",
    },
}

# Cuántos productos entran en cada carpeta de "Mis productos". Diez, como las
# del curso: pasada de ahí se abre la siguiente, para no acabar con una carpeta
# de 200 imposible de mirar.
MIS_PRODUCTOS_POR_CARPETA = 10
MIS_PRODUCTOS_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF/mis_productos"

# "Top vendidos" — mismas reglas (diez por carpeta) y raíz propia. NO lleva
# subcarpeta por usuario porque el ranking de vendidos tampoco: es único y
# global, y el progreso ya se separa por usuario dentro de Redis.
TOP_VENDIDOS_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Top_Vendidos"
TOP_VENDIDOS_PREFIJO = "Top"


def es_fuente_propia(source: str) -> bool:
    """True si la fuente son productos subidos por el operador (no del curso)."""
    return bool((SOURCES.get(source) or {}).get("propia"))


def fuente_canonica(source: str) -> str:
    """La fuente con la que se guarda el progreso de un producto.

    Las fuentes "🗄️ Copia" NO son otro catálogo: son las MISMAS carpetas del
    curso leídas de nuestro backup. Si guardaran su progreso aparte, una
    carpeta ya trabajada aparecería sin empezar al abrirla desde la copia, y lo
    que se marcara ahí no contaría en la original. Se apunta todo en la fuente
    de verdad.
    """
    meta = SOURCES.get(source) or {}
    if not meta.get("backup"):
        return source
    destino = meta.get("canonica") or ""
    return destino or source


def fuente_copia_de(source: str) -> str:
    """La fuente "🗄️ Copia" que corresponde a una del curso (o vacío)."""
    for slug, meta in SOURCES.items():
        if meta.get("backup") and meta.get("canonica") == source:
            return slug
    return ""


def fuentes_a_barrer() -> list[str]:
    """Fuentes que valen para BARRIDOS (buscador, recuperados, resúmenes).

    Deja fuera las de la copia de seguridad: son las mismas carpetas del curso
    —así que saldrían duplicadas— y listarlas cuesta varias llamadas a rclone
    (mira todas las copias), que en un buscador que se dispara al teclear se
    notaba en forma de "no encuentra nada".
    """
    return [s for s in SOURCES if not es_fuente_backup(s)]


def es_fuente_backup(source: str) -> bool:
    """True si la fuente es la copia de seguridad del Drive del curso.

    Importa para leerla: la copia vive en NUESTRO Drive ("Mi unidad"), no en
    "Compartido conmigo", así que rclone NO puede llevar el flag
    `--drive-shared-with-me` o no la encuentra.
    """
    return bool((SOURCES.get(source) or {}).get("backup"))


# Ruta ya resuelta y creada. Se recuerda porque el `mkdir` de abajo va contra
# el Drive MONTADO y en frío cuesta 45 SEGUNDOS medidos: rclone tiene que ir a
# Google a resolver los cuatro niveles de la ruta. Como esta función la llaman
# todas las demás de "Mis productos" (listar carpetas, listar fotos, contar
# productos…), una sola carga de la pantalla lo pagaba varias veces y la
# pantalla tardaba más de medio minuto en salir, frente a los 0,45s de las
# carpetas del Drive compartido.
#
# Dentro del proceso la ruta no cambia nunca, así que se calcula una vez. Si el
# Drive se desmonta hay que reiniciar la API — que es justo lo que ya pasa
# cuando se desmonta, porque no hay nada que leer.
_MIS_PRODUCTOS_DIR: Path | None = None


def mis_productos_dir() -> Path:
    """Raíz de "Mis productos" en el Drive MONTADO (no el compartido)."""
    global _MIS_PRODUCTOS_DIR
    if _MIS_PRODUCTOS_DIR is not None:
        return _MIS_PRODUCTOS_DIR

    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    destino = (
        raiz / MIS_PRODUCTOS_ROOT if raiz
        else Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "mis_productos"
    )
    destino.mkdir(parents=True, exist_ok=True)
    _MIS_PRODUCTOS_DIR = destino
    return destino


_TOP_VENDIDOS_DIR: Path | None = None


def top_vendidos_dir() -> Path:
    """Raíz de "Top vendidos" en el Drive MONTADO.

    Se recuerda por lo mismo que `mis_productos_dir`: resolver una ruta honda
    del mount en frío cuesta decenas de segundos.
    """
    global _TOP_VENDIDOS_DIR
    if _TOP_VENDIDOS_DIR is not None:
        return _TOP_VENDIDOS_DIR

    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    destino = (
        raiz / TOP_VENDIDOS_ROOT if raiz
        else Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "top_vendidos"
    )
    destino.mkdir(parents=True, exist_ok=True)
    _TOP_VENDIDOS_DIR = destino
    return destino


def source_path(source: str) -> str:
    """Path rclone completo de una fuente. Lanza si el slug no existe."""
    meta = SOURCES.get(source)
    if not meta:
        raise ValueError(
            f"Fuente desconocida: {source!r}. Válidas: {sorted(SOURCES)}"
        )
    if meta.get("backup"):
        # Import perezoso: `backup_sync` importa este módulo.
        from src.nicho_pov_bof.services import backup_sync

        copia = backup_sync.ultima_completa()
        if not copia:
            raise ValueError(
                "Todavía no hay ninguna copia completa del Drive del curso. "
                "Pulsa 'Forzar copia completa nueva' en la copia de seguridad."
            )
        return f"{DRIVE_REMOTE}{backup_sync.BACKUP_ROOT}/{copia}/{meta['folder']}"
    return f"{DRIVE_REMOTE}{SHARED_ROOT}/{meta['folder']}"


# ---------------------------------------------------------------------------
# Fotos
# ---------------------------------------------------------------------------
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def is_image(name: str, mime: str = "") -> bool:
    """¿Es una foto? Por extensión o, si no la tiene, por el tipo que da Drive.

    El `mime` NO es un adorno: en estas carpetas hay fotos guardadas SIN
    extensión — el fichero se llama `1`, `2`, `3` a secas — y mirando solo el
    nombre se descartaban enteras. De las cuatro carpetas de
    "2 Prod Aleatorios 2", dos salían con CERO productos en la web y otra con
    dos, cuando en Drive las cuatro tienen sus diez productos. `rclone lsjson`
    ya trae el `MimeType` real (`image/png`, `image/jpeg`), así que no cuesta
    nada preguntárselo.
    """
    if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
        return True
    return str(mime or "").lower().startswith("image/")


def natural_sort_key(name: str) -> tuple:
    """Orden natural: 1, 2, 10 (no 1, 10, 2).

    Las carpetas se llaman "1 Pront Flow", "10 Pront Flow"... y las fotos
    "1.PNG", "10.PNG". Un sort lexicográfico las descoloca.
    """
    parts = re.split(r"(\d+)", name)
    return tuple(int(p) if p.isdigit() else p.lower() for p in parts)


# ---------------------------------------------------------------------------
# Caché de listados
# ---------------------------------------------------------------------------
# `rclone lsjson` sobre el Drive compartido tarda segundos. Cacheamos en
# memoria del proceso API para que la UI no se arrastre. Refrescable a mano
# desde el endpoint con `?refresh=true`.
LISTING_TTL_S = float(os.getenv("NICHO_POV_BOF_LISTING_TTL_S") or 300)

# Timeout de cada invocación de rclone.
RCLONE_TIMEOUT_S = float(os.getenv("NICHO_POV_BOF_RCLONE_TIMEOUT_S") or 120)


_SECRETS_RCLONE_CONF = "/app/secrets/rclone.conf"


def _copia_escribible(origen: str) -> str:
    """Copia de `origen` en un sitio donde rclone PUEDA escribir.

    El token de Google caduca cada hora y rclone lo renueva y lo reescribe en
    el config. Con el config montado read-only no puede: reintenta el guardado
    DIEZ veces con backoff antes de rendirse, y eso son ~5s tirados en CADA
    invocación (una lista de carpetas pasaba de 1,4s en el host a 6-9s aquí).
    Peor aún, al no persistirlo vuelve a pedir un token nuevo la próxima vez.

    Se copia a un sitio escribible y se re-siembra si el operador actualiza el
    original. rclone se encarga solo de mantener el token al día ahí.
    """
    destino_dir = os.getenv("API_TEMP_ROOT") or "temp_work"
    destino = os.path.join(destino_dir, "rclone_nicho.conf")
    try:
        if (
            not os.path.isfile(destino)
            or os.path.getmtime(origen) > os.path.getmtime(destino)
        ):
            os.makedirs(destino_dir, exist_ok=True)
            shutil.copyfile(origen, destino)
            os.chmod(destino, 0o600)
        return destino
    except OSError:
        # Sin sitio escribible se sigue con el original: lento, pero funciona.
        return origen


def rclone_config_path() -> str:
    """Ruta del rclone.conf a usar, o "" para el default de rclone.

    En el container la API corre como uid 999 y el `rclone.conf` canónico del
    host es 600 del uid 1000 → ilegible. El operador deja una copia legible en
    `secrets/rclone.conf`, que el compose monta read-only en `/app/secrets`.
    """
    explicit = os.getenv("NICHO_POV_BOF_RCLONE_CONFIG")
    if explicit:
        return explicit
    if os.path.isfile(_SECRETS_RCLONE_CONF):
        return _copia_escribible(_SECRETS_RCLONE_CONF)
    return ""


# Cuántos días se conserva la copia local de un vídeo ya publicado.
VIDEO_CACHE_DIAS = 10


def video_cache_dir() -> str:
    """Dir local con una copia de los vídeos ya montados.

    El vídeo bueno vive en Drive, pero servir la descarga DESDE el mount es
    lentísimo la primera vez: si el fichero no está en la caché de rclone,
    hay que bajarlo entero de Google antes del primer byte — medido, 36
    segundos para 17 MB. El operador lo notaba al descargar varios seguidos.

    Con una copia local la descarga es instantánea. Se limpia sola pasados
    `VIDEO_CACHE_DIAS` para que no engorde el disco del VPS.
    """
    root = os.getenv("API_TEMP_ROOT") or "temp_work"
    return os.path.join(root, "nicho_pov_bof_videos")


def video_cache_path(folder: str, producto: str, usuario: str = "") -> str:
    """Ruta de la copia local de un vídeo. Nombre plano y saneado.

    Lleva el usuario porque cada uno monta SU vídeo del mismo producto: sin
    esto, Ana se descargaría el de ness.
    """
    quien = usuario or "ness"
    seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{quien}__{producto}__{folder}")
    return os.path.join(video_cache_dir(), f"{seguro}.mp4")


def limpiar_video_cache(dias: int = VIDEO_CACHE_DIAS) -> int:
    """Borra copias locales viejas. Devuelve cuántas."""
    import time

    carpeta = video_cache_dir()
    if not os.path.isdir(carpeta):
        return 0
    limite = time.time() - dias * 86400
    borrados = 0
    for nombre in os.listdir(carpeta):
        ruta = os.path.join(carpeta, nombre)
        try:
            if os.path.isfile(ruta) and os.path.getmtime(ruta) < limite:
                os.unlink(ruta)
                borrados += 1
        except OSError:
            continue
    return borrados


def photo_cache_dir() -> str:
    """Dir local donde se cachean las fotos descargadas por file ID.

    Vive bajo API_TEMP_ROOT (volumen persistido del container) para no
    re-descargar la misma foto en cada scroll de la UI.
    """
    root = os.getenv("API_TEMP_ROOT") or "temp_work"
    return os.path.join(root, "nicho_pov_bof_photos")


# ---------------------------------------------------------------------------
# Vídeo (fase 2)
# ---------------------------------------------------------------------------
TARGET_W, TARGET_H, TARGET_FPS = 1080, 1920, 30

# Zonas seguras de TikTok — mismas que el resto del proyecto
# (`src/subtitles.py`): fuera de aquí la UI de TikTok tapa el texto.
SAFE_X = (0.05, 0.78)
SAFE_Y = (0.15, 0.75)

# Bloque de texto: gancho arriba, título del producto en medio, CTA debajo.
TEXT_BLOCK_Y = 0.17          # centro del bloque, dentro de la zona segura
# Jerarquía clara: el gancho manda, el CTA le sigue y el nombre del producto
# va notablemente más pequeño. Antes los tres rondaban 60px y el bloque salía
# plano ("parece muy básico", dixit el operador).
HOOK_FONT_SIZE = 72
CTA_FONT_SIZE = 60
TITLE_FONT_SIZE = 46

# Flecha .mov: abajo a la izquierda, justo encima de la etiqueta naranja de la
# tienda que pinta TikTok. Mismos valores que `ready_video.py`.
ARROW_CX, ARROW_CY = 0.22, 0.82
ARROW_SCALE_W = 0.16
# La flecha entra este margen ANTES de que se diga la palabra clave.
ARROW_LEAD_S = 1.0
ARROW_DURATION_S = 3.5

# Palabra que dispara la flecha. Las 5 frases locutadas dicen todas
# "carrito naranja", así que basta con "carrito"; el resto son variantes por
# si en el futuro se graban frases nuevas.
ARROW_KEYWORDS = ("carrito", "naranja", "cupones", "cupón", "enlace", "tienda")

# Duración objetivo del vídeo. Los audios rondan 12-14s, así que lo normal es
# que el audio sea MÁS LARGO y haya que alargar el vídeo.
VIDEO_TARGET_S = 10.0
# Si el audio es más largo, el vídeo se alarga rebobinando su tramo final
# (ida y vuelta). No se ralentiza: deformaría el gesto de la mano.
REVERSE_TAIL_MAX_S = 4.0


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------
def redis_prefix() -> str:
    """Prefijo Redis del módulo. Default `nicho_pov_bof:`. Override por env."""
    return os.getenv("NICHO_POV_BOF_REDIS_PREFIX") or "nicho_pov_bof:"


# ---------------------------------------------------------------------------
# Salida (FASE 2 — todavía sin usar)
# ---------------------------------------------------------------------------
# Mismo patrón que VIRALIZACION: todo cuelga de TIKTOK_SHOP_AI_PRO.
DRIVE_UPLOAD_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF"


# ---------------------------------------------------------------------------
# Guion de plazos (Klarna)
# ---------------------------------------------------------------------------
# Klarna financia a partir de 30 €, pero aquí el listón se pone más alto: con
# cupones el pedido baja y un producto de 32 € puede quedarse por debajo de los
# 30, dejando el guion mintiendo. 40 € deja margen.
PRECIO_MIN_PLAZOS = float(os.getenv("PRECIO_MIN_PLAZOS", "40"))


def precio_num(valor) -> float:
    """Pasa a número el precio leído de la ficha. 0 si no hay nada legible.

    Llega escrito como le da la gana al vendedor: `45,90`, `45.90`, `€45`,
    `1.299,00`, `45,90 €`. Con un `float()` a secas se caían el símbolo y, peor,
    los miles: un sofá de `1.299,00` daba 0 y se iba al guion de siempre, que es
    justo el producto que MÁS pide el de plazos.
    """
    txt = re.sub(r"[^0-9.,]", "", str(valor or ""))
    if not txt:
        return 0.0
    coma, punto = txt.rfind(","), txt.rfind(".")
    if coma >= 0 and punto >= 0:
        # Manda el ÚLTIMO: el otro es separador de miles.
        decimal, miles = (",", ".") if coma > punto else (".", ",")
        txt = txt.replace(miles, "").replace(decimal, ".")
    elif coma >= 0 or punto >= 0:
        sep = "," if coma >= 0 else "."
        # Un solo separador con TRES cifras detrás y ninguna más es de miles
        # (`1.299`); con dos o menos es decimal (`45,90`).
        cuerpo, _, cola = txt.rpartition(sep)
        txt = (
            cuerpo + cola
            if len(cola) == 3 and sep not in cuerpo and cuerpo
            else txt.replace(sep, ".")
        )
    try:
        return max(0.0, float(txt))
    except ValueError:
        return 0.0


def guiones_plazos() -> list[str]:
    """Los guiones del documento del curso, uno por línea. Se sortea uno."""
    ruta = Path(__file__).resolve().parent / "prompts" / "guiones_plazos.md"
    return [
        linea[2:].strip()
        for linea in ruta.read_text(encoding="utf-8").splitlines()
        if linea.startswith("- ") and len(linea) > 40
    ]
