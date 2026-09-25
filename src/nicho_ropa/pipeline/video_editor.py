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


def pegar(
    clips: list[Path], destino: Path, on_log: OnLog = _noop,
    guiones: list[str] | None = None,
) -> Path:
    """Pega los clips de un vídeo que se graba por partes, CON su audio.

    Los `concatenar` del POV BOF y del BOF Cine no valen: tiran el audio
    (`a=0`) y aquí los clips vienen hablados. Se hace como en el Nicho
    General: cada clip a la misma caja y códec, y luego concat por lista sin
    recodificar.

    `guiones` (lo que dice cada clip, en el mismo orden) sirve para cortar la
    palabra que el generador empieza DESPUÉS del guion y deja a medias al
    acabarse los 8 s: sin silencio al final, el recorte de silencio no la ve.
    """
    if len(clips) == 1:
        return Path(clips[0])
    from src.nicho_general.pipeline.video_editor import _silencio_inicial
    from src.nicho_pov_bof.pipeline.duration_match import probe_duration

    work = destino.parent / f"pegar_{destino.stem}"
    work.mkdir(parents=True, exist_ok=True)
    iguales = []
    for i, clip in enumerate(clips, start=1):
        trozo = work / f"parte{i}.mp4"
        # El hueco antes de hablar se quita en CADA clip (el prompt le pide
        # al generador un respiro al empezar, y sumado a lo que ya deja él
        # eran ~1 s por clip). Y el del final, en todos menos el último: ahí
        # es el hueco entre las dos mitades, que se oía como un corte. El
        # último conserva su cola, que es donde se ve la flecha.
        quitar_ini = _silencio_inicial(Path(clip))
        if i < len(clips):
            quitar_fin = _silencio_final(Path(clip))
        else:
            # El último: se le deja una cola corta (para la flecha) y se
            # recorta el resto del silencio.
            hueco = _silencio_final(Path(clip), margen=0.0, tope=_MAX_RECORTE_COLA_S)
            quitar_fin = max(0.0, hueco - _COLA_FINAL_S)
        dur = probe_duration(Path(clip))
        guion = (guiones or [])[i - 1] if guiones and len(guiones) == len(clips) else ""
        if guion:
            quitar_fin = max(quitar_fin, _palabra_a_medias(
                Path(clip), guion, dur, work, on_log, ultimo=i == len(clips),
            ))
        largo = max(0.5, dur - quitar_ini - quitar_fin)
        if quitar_ini or quitar_fin:
            on_log(
                f"[nicho_ropa] clip {i}: fuera {quitar_ini:.2f}s de silencio al "
                f"principio y {quitar_fin:.2f}s al final"
            )
        _run([
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{quitar_ini:.3f}", "-t", f"{largo:.3f}", "-i", str(clip),
            "-vf", (
                f"scale={pov_config.TARGET_W}:{pov_config.TARGET_H}"
                ":force_original_aspect_ratio=decrease,"
                f"pad={pov_config.TARGET_W}:{pov_config.TARGET_H}"
                ":(ow-iw)/2:(oh-ih)/2:color=black,"
                f"fps={pov_config.TARGET_FPS},setsar=1"
            ),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            str(trozo),
        ], on_log)
        iguales.append(trozo)
    lista = work / "clips.txt"
    lista.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in iguales) + "\n",
        encoding="utf-8",
    )
    _run([
        "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
        "-i", str(lista), "-c", "copy", "-movflags", "+faststart",
        str(destino),
    ], on_log)
    on_log(f"[nicho_ropa] {len(clips)} clips pegados con su voz")
    return destino


# Mismos umbrales que el silencio de entrada del Nicho General, y un margen
# algo mayor al final: cortar pegado a la última sílaba se la come.
_RUIDO_DB = -35
_MIN_SILENCIO_S = 0.15
_MARGEN_FINAL_S = 0.15
_MAX_RECORTE_FINAL_S = 1.5
# Al ÚLTIMO clip se le deja esta cola de silencio y se recorta lo que pase:
# ahí va la flecha al carrito, pero un vídeo que acaba con dos segundos de
# nadie hablando se abandona antes. Medido en un clip real de Omni: la voz
# acabó en 6,2 s de 8.
_COLA_FINAL_S = 1.2
_MAX_RECORTE_COLA_S = 3.0


# Aire que se deja tras la última palabra del guion al cortar lo que sobra.
_MARGEN_TRAS_GUION_S = 0.12


def _palabra_a_medias(
    clip: Path, guion: str, dur: float, work: Path, on_log: OnLog,
    ultimo: bool = False,
) -> float:
    """Segundos a quitar del final si, acabado el guion, el clip sigue hablando.

    Omni a veces empieza otra palabra tras la última del guion y los 8 s la
    cortan por la mitad. Se busca en Whisper la última palabra del guion y, si
    detrás hay voz (otra palabra, o el clip no acaba en silencio), se corta
    justo después de ella. Si no se encuentra la palabra, no se toca nada.
    En los clips de en medio basta con que no acabe en silencio (Whisper no
    siempre oye media sílaba); en el último hace falta oír la palabra de más.
    """
    import difflib

    from src.nicho_pov_bof.pipeline.video_editor import _norm_palabra, _transcribir_voz

    palabras_guion = [_norm_palabra(p) for p in guion.split()]
    palabras_guion = [p for p in palabras_guion if p]
    if not palabras_guion:
        return 0.0
    sub = work / f"fin_{clip.stem}"
    sub.mkdir(parents=True, exist_ok=True)
    words = _transcribir_voz(clip, sub, on_log) or []
    oidas = [_norm_palabra(w.get("word", "")) for w in words]
    ultima = None
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, palabras_guion, oidas, autojunk=False,
    ).get_opcodes():
        if op == "equal" and i2 == len(palabras_guion):
            ultima = j2 - 1
    if ultima is None:
        return 0.0
    fin_guion = float(words[ultima]["end"])
    sobran = words[ultima + 1:]
    corte = fin_guion + _MARGEN_TRAS_GUION_S
    if sobran:
        corte = min(corte, max(fin_guion, float(sobran[0]["start"]) - 0.03))
    elif ultimo or _silencio_final(clip, margen=0.0, tope=dur) > 0:
        # Acaba en silencio (de eso ya se encarga el recorte de silencio), o es
        # el último clip: su cola es la de la flecha y, sin otra palabra oída,
        # lo que queda puede ser solo ruido de la tienda.
        return 0.0
    quitar = dur - corte
    if quitar > 0.05:
        on_log(f"[nicho_ropa] {clip.name}: fuera {quitar:.2f}s tras el guion (palabra a medias)")
        return quitar
    return 0.0


def _silencio_final(
    clip: Path, margen: float = _MARGEN_FINAL_S, tope: float = _MAX_RECORTE_FINAL_S,
) -> float:
    """Cuánto dura el hueco del final, 0 si acaba hablando."""
    from src.nicho_pov_bof.pipeline.duration_match import probe_duration

    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(clip),
         "-af", f"silencedetect=noise={_RUIDO_DB}dB:d={_MIN_SILENCIO_S}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    ultimo_inicio, ultimo_fin = None, None
    for linea in proc.stderr.splitlines():
        if "silence_start:" in linea:
            try:
                ultimo_inicio = float(linea.split("silence_start:")[1].split()[0])
                ultimo_fin = None
            except (IndexError, ValueError):
                pass
        elif "silence_end:" in linea:
            try:
                ultimo_fin = float(linea.split("silence_end:")[1].split()[0])
            except (IndexError, ValueError):
                pass
    try:
        dur = probe_duration(clip)
    except Exception:  # noqa: BLE001
        return 0.0
    # Solo cuenta si el silencio llega hasta el FINAL: o el detector no lo
    # cierra, o lo cierra pegado al último fotograma. Uno que se cierra antes
    # es una pausa de la persona y ahí no se toca.
    if ultimo_inicio is None:
        return 0.0
    if ultimo_fin is not None and ultimo_fin < dur - 0.1:
        return 0.0
    hueco = dur - ultimo_inicio - margen
    return max(0.0, min(hueco, tope))


def _subtitular(video: Path, texto: str, on_log: OnLog) -> None:
    """Quema los subtítulos de lo que dice el clip, sobre el propio fichero.

    El texto es el guion escrito para la prenda (lo tenemos exacto) y Whisper
    solo pone los tiempos, igual que en el POV BOF — de ahí se reutilizan los
    helpers en vez de tener dos renderizadores de subtítulos.
    """
    from src.nicho_pov_bof.pipeline.duration_match import probe_duration
    from src.nicho_pov_bof.pipeline.video_editor import (
        _burn_subtitulos,
        _palabras_con_tiempo,
        _transcribir_voz,
        _trozos_subtitulos,
    )

    work = video.parent / f"subs_{video.stem}"
    work.mkdir(parents=True, exist_ok=True)
    palabras = _transcribir_voz(video, work, on_log)
    if not palabras:
        on_log("[nicho_ropa] sin transcripción — el vídeo se queda sin subtítulos")
        return
    trozos = _trozos_subtitulos(
        _palabras_con_tiempo(texto, palabras), probe_duration(video),
    )
    salida = work / "subtitulado.mp4"
    try:
        if _burn_subtitulos(video, trozos, salida, on_log) == salida and salida.is_file():
            salida.replace(video)
    finally:
        # Vive al lado del vídeo (en el Drive montado, para poder hacer
        # `replace` sin cruzar de sistema de ficheros): no se deja ahí.
        import shutil

        shutil.rmtree(work, ignore_errors=True)


def montar(
    video_in: Path,
    out_path: Path,
    *,
    voz: Path | None = None,
    conservar_audio: bool = False,
    # Lo que dice el clip, para quemarlo como subtítulos. Vacío = sin ellos,
    # que es lo de siempre en este nicho.
    texto_subs: str = "",
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
        _rematar(out_path, modo, semilla, on_log, texto_subs)
        return out_path

    if voz is None:
        _run([
            "ffmpeg", "-y", "-v", "error", "-i", str(video_in),
            "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-movflags", "+faststart", str(out_path),
        ], on_log)
        on_log("[nicho_ropa] vídeo mudo (sin voz ni música, a propósito)")
        _rematar(out_path, modo, semilla, on_log, texto_subs)
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
    _rematar(out_path, modo, semilla, on_log, texto_subs)
    return out_path


# La flecha al carrito sale los ÚLTIMOS segundos, no desde que se nombra el
# carrito como en el POV BOF: el guion de moda no lleva CTA hablada (el del
# curso no la tiene y no se toca), así que no hay palabra que la dispare.
FLECHA_SEGUNDOS = 4.0

# Qué flecha va con qué fondo. Se busca que case con el ESTILO del vídeo —una
# calle de otoño pide la amarilla, un parque la verde— y no un color fijo que
# desentona encima de un vídeo de moda.
# Estilos de flecha, y en qué fichero está cada uno para un color dado
# (`flecha_<estilo><color>.mov`). El color lo decide el fondo del vídeo; el
# estilo va ROTANDO por prenda, para que dos vídeos seguidos no lleven la misma
# flecha. Los estilos teñidos salen de `scripts/flechas_colores.sh` y el del
# círculo de `scripts/flechas_circulo.py`; la 3D solo existe en amarilla y roja,
# y se usa cuando toca ese color.
_ESTILOS_FLECHA = ("", "avanza_", "triple_", "abajo_triple_", "circulo_", "3d_")


def _elegir_flecha(color: str, semilla: str, carpeta: str) -> "Path | None":
    """Una flecha de ese color, en el estilo que le toque a esta prenda."""
    import hashlib

    existentes = [
        Path(carpeta) / f"flecha_{estilo}{color}.mov"
        for estilo in _ESTILOS_FLECHA
        if (Path(carpeta) / f"flecha_{estilo}{color}.mov").is_file()
    ]
    if not existentes:
        return None
    n = int(hashlib.md5((semilla or "").encode()).hexdigest(), 16)
    return existentes[n % len(existentes)]


def _color_del_fondo(video: Path, t: float) -> str:
    """El color de flecha que va con el vídeo en el segundo `t`.

    Matiz dominante PESADO por la saturación: el cielo gris o el asfalto no
    votan, y lo que da el tono (hojas, fachadas, vegetación) sí. Luego se mira
    lo oscuro o claro que es ESE matiz, que es lo que separa un naranja de un
    marrón o un rojo de un burdeos. Sin color de verdad, blanca sobre fondo
    oscuro, negra sobre claro y beige si lo que hay es un tono crema.
    """
    import cv2
    import numpy as np

    foto = video.with_name(f"_fondo_{video.stem}.jpg")
    try:
        _run([
            "ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, t):.2f}",
            "-i", str(video), "-frames:v", "1", "-vf", "scale=240:-1", str(foto),
        ], _noop)
        img = cv2.imread(str(foto))
    finally:
        foto.unlink(missing_ok=True)
    if img is None:
        return "blanca"
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(float)
    grados_px = hsv[:, 0] * 2
    sat = hsv[:, 1] / 255.0
    luz = hsv[:, 2] / 255.0

    hist, _ = np.histogram(grados_px, bins=36, range=(0, 360), weights=sat)
    grados = (int(hist.argmax()) + 0.5) * 10
    # Luz y saturación del matiz ganador, no de toda la imagen.
    cerca = np.abs(((grados_px - grados) + 180) % 360 - 180) <= 15
    s_tono = float(sat[cerca].mean()) if cerca.any() else float(sat.mean())
    v_tono = float(luz[cerca].mean()) if cerca.any() else float(luz.mean())

    if sat.mean() < 0.18:
        # Un crema (E8DCC4) tiene solo un 15% de saturación: poca para contar
        # como color, pero bastante para no ser gris. Un gris de verdad no
        # llega al 3%.
        if 15 <= grados < 60 and s_tono >= 0.08 and v_tono > 0.6:
            return "beige"
        return "negra" if luz.mean() > 0.62 else "blanca"
    if grados < 15 or grados >= 345:
        return "burdeos" if v_tono < 0.45 else "roja"
    if grados < 40:
        return "marron" if v_tono < 0.5 else "naranja"
    if grados < 70:
        return "amarilla"
    if grados < 170:
        return "verde"
    if grados < 200:
        return "cyan"
    if grados < 260:
        return "azul"
    if grados < 300:
        return "morada"
    return "rosa"


def _flecha(salida: Path, on_log: OnLog, semilla: str = "") -> None:
    """Pone la flecha al carrito los últimos segundos. Si falla, sin flecha."""
    from src.nicho_pov_bof.pipeline.duration_match import probe_duration
    from src.tiktok_shop.pipeline.ready_video import _arrows_dir, _pick_arrow

    try:
        dur = probe_duration(salida)
        t0 = max(0.0, dur - FLECHA_SEGUNDOS)
        color = _color_del_fondo(salida, t0 + FLECHA_SEGUNDOS / 2)
        carpeta = _arrows_dir()
        ruta = _elegir_flecha(color, semilla or salida.stem, carpeta) if carpeta else None
        if not ruta:
            elegida = _pick_arrow(0)
            ruta = Path(elegida) if elegida else None
        if not ruta:
            on_log("[nicho_ropa] sin flechas en disco — el vídeo sale sin ella")
            return
        ancho = int(pov_config.TARGET_W * pov_config.ARROW_SCALE_W)
        tmp = salida.with_name(salida.stem + "__flecha" + salida.suffix)
        # `setpts` desplaza la animación para que EMPIECE cuando aparece, y
        # `-t` acota el bucle infinito de la flecha (el vídeo lleva audio,
        # pero no hay que fiarse de `-shortest` con un `-stream_loop -1`).
        _run([
            "ffmpeg", "-y", "-v", "error", "-i", str(salida),
            "-stream_loop", "-1", "-i", str(ruta),
            "-filter_complex",
            f"[1:v]scale={ancho}:-2,format=rgba,setpts=PTS-STARTPTS+{t0:.3f}/TB[f];"
            f"[0:v][f]overlay=x=(main_w*{pov_config.ARROW_CX})-(overlay_w/2):"
            f"y=(main_h*{pov_config.ARROW_CY})-(overlay_h/2):"
            f"enable='between(t,{t0:.3f},{dur:.3f})'[v]",
            "-map", "[v]", "-map", "0:a?", "-c:a", "copy",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-t", f"{dur:.3f}", "-movflags", "+faststart", str(tmp),
        ], on_log)
        tmp.replace(salida)
        on_log(f"[nicho_ropa] flecha {ruta.stem} los últimos {FLECHA_SEGUNDOS:.0f}s")
    except Exception as e:  # noqa: BLE001 — la flecha es un extra
        on_log(f"[nicho_ropa] no se pudo poner la flecha ({str(e)[:160]}) — sale sin ella")


def _rematar(
    salida: Path, modo: str, semilla: str, on_log: OnLog, texto_subs: str = "",
) -> None:
    """Subtítulos, flecha y texto de temporada (si los lleva) y metadatos fuera."""
    if texto_subs.strip():
        _subtitular(salida, texto_subs, on_log)
    if modo and config.lleva_flecha(modo):
        _flecha(salida, on_log, semilla)
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
_TEXTO_CUERPO = 74
_TEXTO_BAJADA = 0.75      # de la línea de arriba (medido sobre las capturas)

# Variantes del rótulo: la MISMA idea con otros adornos. La cuenta tiene que
# verse coherente, pero cien vídeos con el rótulo calcado se leen como una
# plantilla. Se elige una por prenda y de forma determinista, así que un
# producto remontado sale igual y dos seguidos no repiten.
ADORNOS_TEXTO: tuple[dict, ...] = (
    {"titulo": ("🤎", "🤎"), "bajada": ("🍂", "🍂"),
     "fuente_titulo": "PTSerif-Bold.ttf",
     "fuente_bajada": "CormorantGaramond-LightItalic.ttf"},
    {"titulo": ("🍂", "🍂"), "bajada": ("🤎", "🤎"),
     "fuente_titulo": "PlayfairDisplay-Black.ttf",
     "fuente_bajada": "CormorantGaramond-LightItalic.ttf"},
    {"titulo": ("🍁", "🍁"), "bajada": ("✨", "✨"),
     "fuente_titulo": "PTSerif-Bold.ttf",
     "fuente_bajada": "CormorantGaramond-LightItalic.ttf"},
    {"titulo": ("🤎", "🤎"), "bajada": ("", ""),
     "fuente_titulo": "PlayfairDisplay-Black.ttf",
     "fuente_bajada": "CormorantGaramond-LightItalic.ttf"},
    {"titulo": ("", ""), "bajada": ("🍂", "🍂"),
     "fuente_titulo": "PTSerif-Bold.ttf",
     "fuente_bajada": "CormorantGaramond-LightItalic.ttf"},
)


def adorno_de(semilla: str) -> dict:
    """Qué variante le toca a esa prenda. Determinista: no cambia al remontar."""
    import hashlib

    h = hashlib.sha1(str(semilla or "").encode("utf-8")).digest()
    return ADORNOS_TEXTO[h[0] % len(ADORNOS_TEXTO)]


def _sombra_suave(im):
    """Pone una sombra desenfocada DETRÁS del texto.

    Es lo que hace que el blanco despegue del fondo sin recurrir a un contorno
    negro: sobre un plano claro el texto se lee igual de bien y sigue
    pareciendo una foto de moda y no una pegatina.
    """
    from PIL import Image, ImageFilter

    if im is None:
        return None
    margen = 18
    lienzo = Image.new(
        "RGBA", (im.width + margen * 2, im.height + margen * 2), (0, 0, 0, 0),
    )
    # La silueta del texto, en oscuro y borrosa. Dos pasadas: una ancha que
    # apaga el fondo y otra corta que marca el canto.
    for radio, alfa, desvio in ((9, 120, 3), (4, 150, 1)):
        sombra = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
        tinta = Image.new("RGBA", im.size, (26, 16, 10, alfa))
        sombra.paste(tinta, (margen + desvio, margen + desvio), im)
        lienzo.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(radio)))
    lienzo.alpha_composite(im, (margen, margen))
    return lienzo


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
        # Blanco PURO y SIN contorno: lo que separa el texto del fondo es la
        # sombra desenfocada de debajo (`_sombra_suave`) y el grosor de la
        # letra. Con borde negro se lee, pero parece una pegatina, y estos
        # vídeos van de parecer una foto de moda.
        im = _render_text_line(
            completo, font_size=cuerpo, max_w=ancho_max,
            fill=(255, 255, 255), stroke=None, max_lines=1,
            fuente=fuente, stroke_frac=0.0,
        )
        return _sombra_suave(_crop_visible(im)) if im is not None else None

    def _titulo(texto: str, par: tuple, fuente: str, cuerpo: int):
        """El título, espaciado letra a letra y con sus emojis a los lados.

        Cada PALABRA se pinta por separado y se pegan con un hueco mayor: el
        renderizador reparte por palabras y de paso normaliza los espacios
        (`split()`), así que dentro de una sola cadena "AUTUMN BOOTS" sale
        "AUTUMNBOOTS" da igual con qué espacio se separe.
        """
        izq, der = par
        trozos = [(" ".join(w), cuerpo * 0.85) for w in (texto or "").split()]
        if not trozos:
            return None
        if izq:
            trozos.insert(0, (izq, cuerpo * 0.22))
        if der:
            trozos.append((der, 0))
        ims = []
        for txt, hueco in trozos:
            im = _render_text_line(
                txt, font_size=cuerpo, max_w=ancho_max,
                fill=(255, 255, 255), stroke=None, max_lines=1,
                fuente=fuente, stroke_frac=0.0,
            )
            if im is not None:
                ims.append((_crop_visible(im), int(hueco)))
        if not ims:
            return None
        ancho = sum(i.width + h for i, h in ims) - ims[-1][1]
        alto = max(i.height for i, _ in ims)
        linea = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
        x = 0
        for im, hueco in ims:
            linea.paste(im, (x, (alto - im.height) // 2), im)
            x += im.width + hueco
        if linea.width > ancho_max:      # título largo: se encoge, no se parte
            escala = ancho_max / linea.width
            linea = linea.resize(
                (ancho_max, max(1, int(alto * escala))), Image.LANCZOS,
            )
        return _sombra_suave(linea)

    arriba = _titulo(titulo, ad["titulo"], ad["fuente_titulo"], _TEXTO_CUERPO)
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
