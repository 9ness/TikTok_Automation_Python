"""Montaje del vídeo de una prenda.

Es deliberadamente MÍNIMO comparado con el del Nicho POV BOF, porque este
nicho no lleva nada encima: ni gancho, ni título, ni CTA, ni flecha. La prenda
se enseña y ya. Lo único que se hace es:

1. Encuadrar a 1080x1920 (cover-fit), que es lo que pide TikTok, con la
   ampliación que se come la marca de agua del generador.
2. Quitar el audio. **Va mudo por defecto**: el operador le pone la música al
   publicar, y el audio que trae el vídeo generado no sirve para nada.
3. Opcionalmente, ponerle una voz del banco (hombre/mujer) si el operador la
   pide. Es la misma biblioteca de audios que usa el otro nicho.

La excepción es el catálogo de la web (Ropa Mujer/Hombre): ahí el clip sale de
VEO con el prompt del espejo, o sea que ya trae la voz de la creadora hablando
y sincronizada con los labios. Ese audio SÍ vale, y silenciarlo se carga el
vídeo entero — por eso existe `conservar_audio`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof import config as pov_config
from src.nicho_ropa import config

OnLog = Callable[[str], None]


def _noop(_: str) -> None:
    return None


def _run(cmd: list[str], on_log: OnLog) -> None:
    on_log("+ " + " ".join(str(c) for c in cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {proc.stderr[-500:]}")


def montar(
    video_in: Path,
    out_path: Path,
    *,
    voz: Path | None = None,
    conservar_audio: bool = False,
    # El modo de grabación. Los de marca personal llevan grado de color y el
    # texto de temporada quemado; el resto salen tal cual.
    modo: str = "",
    # Identifica la prenda: de ella sale QUÉ variante de rótulo le toca, para
    # que dos vídeos seguidos no lleven el mismo adorno.
    semilla: str = "",
    on_log: OnLog = _noop,
) -> Path:
    """Encuadra a 9:16 y deja el vídeo mudo (o con la voz que se le pase).

    `-an` no es un descuido: el vídeo que sale del generador trae un audio
    ambiente que no aporta nada, y el operador quiere ponerle la música él al
    publicar.

    `conservar_audio` es justo lo contrario, y es para el catálogo de la web:
    el clip ya viene hablado por la creadora, sincronizado con los labios. Una
    voz del banco manda sobre esto — no tiene sentido pisar una voz con otra.
    """
    # Mismo encuadre que el resto de nichos, con la ampliación que se come la
    # marca de agua del generador.
    vf = pov_config.filtro_encuadre()
    # El grado va PEGADO al encuadre: es un filtro más de la misma pasada, así
    # que no cuesta una recodificación extra.
    if modo and config.texto_de_modo(modo):
        vf = f"{vf},{FILTRO_MARCA}"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if voz is None and conservar_audio:
        # `-c:a aac` y no `copy`: el contenedor de salida cambia y algunos
        # clips llegan con audio en un códec que el MP4 de TikTok no traga.
        _run([
            "ffmpeg", "-y", "-v", "error", "-i", str(video_in),
            "-vf", vf, "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(out_path),
        ], on_log)
        on_log("[nicho_ropa] vídeo con SU audio (la voz que trae el clip)")
        _rematar(out_path, modo, semilla, on_log)
        return out_path

    if voz is None:
        _run([
            "ffmpeg", "-y", "-v", "error", "-i", str(video_in),
            "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-movflags", "+faststart", str(out_path),
        ], on_log)
        on_log("[nicho_ropa] vídeo mudo (sin voz ni música, a propósito)")
        _rematar(out_path, modo, semilla, on_log)
        return out_path

    # Con voz: el vídeo dura lo que dure la voz. `-shortest` corta por el más
    # corto de los dos, que es lo que evita quedarse con imagen congelada al
    # final si la voz acaba antes.
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video_in), "-i", str(voz),
        "-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-shortest",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(out_path),
    ], on_log)
    on_log(f"[nicho_ropa] vídeo con voz: {voz.name}")
    _rematar(out_path, modo, semilla, on_log)
    return out_path


def _rematar(salida: Path, modo: str, semilla: str, on_log: OnLog) -> None:
    """Texto de temporada (si el formato lo lleva) y metadatos fuera."""
    texto = config.texto_de_modo(modo) if modo else {}
    if texto.get("titulo"):
        _quemar_texto(salida, texto, semilla, on_log)
    _limpiar(salida, on_log)


def _quemar_texto(
    salida: Path, texto: dict, semilla: str, on_log: OnLog,
) -> None:
    """Pinta las dos líneas sobre el vídeo. Si falla, el vídeo se queda igual.

    `segundos` a 0 significa TODO el vídeo: el formato de vista POV lo lleva
    puesto de principio a fin, y el de espejo solo los primeros segundos.
    """
    import tempfile

    # El PNG puede vivir en /tmp, pero el MP4 de salida NO: se sustituye con
    # `replace`, que es un `rename`, y renombrar de /tmp al Drive montado da
    # "Invalid cross-device link". Va al lado del vídeo, como en la limpieza de
    # metadatos.
    work = Path(tempfile.mkdtemp(prefix="moda_txt_"))
    tmp = salida.with_name(salida.stem + "__texto" + salida.suffix)
    try:
        ad = adorno_de(semilla)
        png = _png_texto_moda(
            texto["titulo"], texto.get("bajada", ""), work, ad,
        )
        seg = float(texto.get("segundos") or 0)
        enable = f":enable='between(t,0,{seg:.2f})'" if seg > 0 else ""
        _run([
            "ffmpeg", "-y", "-v", "error", "-i", str(salida), "-i", str(png),
            "-filter_complex",
            f"[0:v][1:v]overlay=(main_w-overlay_w)/2:main_h*{_TEXTO_Y}{enable}[v]",
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "copy", "-movflags", "+faststart", str(tmp),
        ], on_log)
        tmp.replace(salida)
        on_log(
            f"[nicho_ropa] texto quemado: {texto['titulo']} "
            f"({ad['titulo'][0] or 'sin adorno'})"
            + (f" · {seg:.0f}s" if seg > 0 else " · todo el vídeo")
        )
    except Exception as e:  # noqa: BLE001 — un texto no tira un montaje
        tmp.unlink(missing_ok=True)
        on_log(f"[nicho_ropa] sin texto quemado ({str(e)[:120]})")
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)


def _limpiar(salida: Path, on_log: OnLog) -> None:
    """Deja el fichero sin la ficha técnica del generador.

    Lo mismo que hacen el POV BOF y el UGC desde sep 2026; aquí se olvidó al
    añadirlo. Es un remux, así que no toca la imagen.
    """
    try:
        from src.nicho_pov_bof.pipeline.video_editor import limpiar_metadatos

        limpiar_metadatos(salida, on_log)
    except Exception as e:  # noqa: BLE001 — el vídeo ya está montado
        on_log(f"[nicho_ropa] no se pudieron limpiar los metadatos ({str(e)[:100]})")


# ---------------------------------------------------------------------------
# Marca personal: color de película y texto de temporada
# ---------------------------------------------------------------------------
# El curso manda editar el clip en CapCut —bajar la exposición y meter un
# filtro de "Películas"— y poner el texto a mano. Aquí lo hace el montaje: son
# cientos de vídeos y a mano ni salen iguales ni salen a tiempo.
#
# El grado es una aproximación de ese filtro cálido: menos luz, algo más de
# contraste, la saturación justo por debajo y las sombras tiradas a ámbar. No
# se pasa de rosca a propósito — el vídeo tiene que seguir pareciendo grabado
# con un móvil, que es lo que vende el formato.
FILTRO_MARCA = (
    "eq=brightness=-0.045:contrast=1.07:saturation=0.94:gamma=0.98,"
    "curves=r='0/0 0.25/0.27 0.75/0.78 1/1':"
    "g='0/0 0.25/0.245 0.75/0.75 1/1':"
    "b='0/0.015 0.25/0.23 0.75/0.72 1/0.985'"
)
# El texto va centrado y a media altura, como en los vídeos de referencia.
_TEXTO_Y = 0.42
_TEXTO_CUERPO = 62
_TEXTO_BAJADA = 0.75      # de la línea de arriba (medido sobre las capturas)

# Variantes del rótulo: la MISMA idea con otros adornos. La cuenta tiene que
# verse coherente, pero cien vídeos con el rótulo calcado se leen como una
# plantilla. Se elige una por prenda y de forma determinista, así que un
# producto remontado sale igual y dos seguidos no repiten.
ADORNOS_TEXTO: tuple[dict, ...] = (
    {"titulo": ("🤎", "🤎"), "bajada": ("🍂", "🍂"),
     "fuente_titulo": "Italiana-Regular.ttf",
     "fuente_bajada": "CormorantGaramond-LightItalic.ttf"},
    {"titulo": ("🍂", "🍂"), "bajada": ("🤎", "🤎"),
     "fuente_titulo": "Italiana-Regular.ttf",
     "fuente_bajada": "CormorantGaramond-LightItalic.ttf"},
    {"titulo": ("🍁", "🍁"), "bajada": ("✨", "✨"),
     "fuente_titulo": "PlayfairDisplay-Black.ttf",
     "fuente_bajada": "CormorantGaramond-LightItalic.ttf"},
    {"titulo": ("🤎", "🤎"), "bajada": ("", ""),
     "fuente_titulo": "PlayfairDisplay-Black.ttf",
     "fuente_bajada": "CormorantGaramond-LightItalic.ttf"},
    {"titulo": ("", ""), "bajada": ("🍂", "🍂"),
     "fuente_titulo": "Italiana-Regular.ttf",
     "fuente_bajada": "CormorantGaramond-LightItalic.ttf"},
)


def adorno_de(semilla: str) -> dict:
    """Qué variante le toca a esa prenda. Determinista: no cambia al remontar."""
    import hashlib

    h = hashlib.sha1(str(semilla or "").encode("utf-8")).digest()
    return ADORNOS_TEXTO[h[0] % len(ADORNOS_TEXTO)]


def _png_texto_moda(
    titulo: str, bajada: str, work: Path, adorno: dict | None = None,
) -> Path:
    """Las dos líneas con sus adornos, como en los vídeos de referencia.

    Se pinta con el renderizador del POV BOF y no con PIL a pelo porque ese
    sabe meter EMOJIS en color (Noto) dentro de una línea de texto — y aquí los
    corazones y las hojas no son un adorno cualquiera: son lo que hace que el
    rótulo se lea como de moda y no como un subtítulo.
    """
    from PIL import Image

    from src.nicho_pov_bof.pipeline.video_editor import (
        _crop_visible,
        _render_text_line,
    )

    ad = adorno or ADORNOS_TEXTO[0]
    ancho_max = int(1080 * (pov_config.SAFE_X[1] - pov_config.SAFE_X[0]))

    def _linea(texto: str, par: tuple, fuente: str, cuerpo: int):
        izq, der = par
        completo = f"{izq} {texto} {der}".strip() if izq or der else texto
        im = _render_text_line(
            completo, font_size=cuerpo, max_w=ancho_max,
            fill=(255, 253, 250), stroke=(40, 26, 18), max_lines=1,
            fuente=fuente, stroke_frac=0.055,
        )
        return _crop_visible(im) if im is not None else None

    # El título espaciado letra a letra, como en la referencia.
    espaciado = " ".join((titulo or "").strip())
    arriba = _linea(espaciado, ad["titulo"], ad["fuente_titulo"], _TEXTO_CUERPO)
    abajo = (
        _linea(bajada, ad["bajada"], ad["fuente_bajada"],
               int(_TEXTO_CUERPO * _TEXTO_BAJADA))
        if bajada else None
    )
    piezas = [x for x in (arriba, abajo) if x is not None]
    if not piezas:
        raise ValueError("texto vacío")

    gap = 8
    ancho = max(x.width for x in piezas)
    alto = sum(x.height for x in piezas) + gap * (len(piezas) - 1)
    im = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    y = 0
    for parte in piezas:
        im.paste(parte, ((ancho - parte.width) // 2, y), parte)
        y += parte.height + gap
    ruta = work / "texto_moda.png"
    im.save(ruta)
    return ruta
