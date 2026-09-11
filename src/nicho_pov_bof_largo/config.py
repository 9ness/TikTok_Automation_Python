"""Nicho POV BOF Largo (Programa 4 — Tiktok Shop AI Pro).

Es el Nicho POV BOF con UNA diferencia de fondo: la voz no sale de un banco de
frases grabadas, sino de un **guion escrito para ESE producto** por la IA y
locutado con Fish Audio. Como el guion habla del producto concreto, dura más
que las frases genéricas (~20s en vez de ~11), y por eso el vídeo son **varios
clips pegados** en vez de uno: con los clips de 8s de la plataforma nueva, un
guion de veinte segundos son tres (ver `clips_necesarios`).

Todo lo demás es idéntico y se reutiliza tal cual: mismas carpetas de Drive,
mismas fotos, mismos textos extraídos, mismo bloque de gancho/título/CTA, misma
flecha y el mismo montador.

**La duración la manda el audio.** Se pegan los clips y se recorta a
la duración exacta de la voz con `match_video_to_audio`, que ya hace las dos
cosas: si sobra vídeo lo corta y si falta lo alarga rebobinando. O sea que un
guion de 18s deja un vídeo de 18s, sin tocar la velocidad.

**Por qué su propio progreso y no el del POV BOF**: haber hecho un producto
allí no significa haberlo hecho aquí — son vídeos distintos del mismo producto.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REDIS_PREFIX = os.getenv("NICHO_POV_BOF_LARGO_REDIS_PREFIX", "nicho_pov_bof_largo:")

# Las MISMAS fuentes del Nicho POV BOF: mismo Drive, mismas carpetas, mismas
# fotos. Se importan para que añadir una fuente valga para los dos.
from src.nicho_pov_bof.config import SOURCES, source_path  # noqa: E402,F401

# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------
# Dos clips de ~10s. Hasta que no están todos los que hacen falta no se encola
# nada: con uno solo no hay vídeo que montar (mismo criterio que el BOF
# Cinematográfico).
CLIPS_POR_VIDEO = 1
# Cuánto dura un clip generado, por defecto. Se elige por carpeta y por
# producto desde la pantalla; esto es con lo que arrancan los que no lo tengan
# puesto. OCHO, que es con lo que se genera hoy y para lo que está medido el
# formato: el guion se escribe para 16s y eso son justo dos clips de 8. Estuvo
# en diez, que era lo que daba el vídeo del POV BOF en un solo clip. De aquí
# sale todo lo demás: cuántos clips pedir y cuánto guion cabe.
CLIP_TARGET_S = float(os.getenv("POV_BOF_LARGO_CLIP_S", "8"))
# Más de cuatro deja de parecer una toma continua.
CLIPS_MAXIMOS = 4
# Hasta dónde se puede estirar un clip. Ojo con la palabra: el montaje NO
# ralentiza, RELLENA — `match_video_to_audio` pega el tramo final marcha atrás
# (`_build_pingpong`) hasta cubrir la voz. Así que este número es cuánto
# rebobinado se acepta, y por eso no se sube alegremente.
#
# Estuvo en 1.2 y luego en 1.3 para que cupieran más voces con la CTA larga.
# El precio de eso se veía: con dos clips de 8s (16s de material) se aceptaba
# una voz de hasta 20,3s, o sea 4,3s de vídeo yendo hacia atrás — un 27% del
# vídeo. Y no era una excepción, era el caso normal, porque el guion se dejaba
# llegar a 356 caracteres (ver `GUION_OBJETIVO_S`).
#
# Ahora es al revés: el guion se escribe para que quepa (~16s) y el estirado
# solo cubre el resto. Con 1.1 el peor caso son 1,1s repetidos (7%), que no se
# ve, y siguen entrando 11 de las 15 voces del banco — solo dos necesitan
# acelerón. Bajar a 1.05 dejaría 0,3s pero obligaría a acelerar la mitad.
ESTIRADO_CLIP = float(os.getenv("POV_BOF_ESTIRADO_CLIP", "1.1"))
CLIP_MAX_S = round(CLIP_TARGET_S * ESTIRADO_CLIP, 1)
# Duraciones que el operador puede elegir. La plataforma de vídeo ha dado clips
# de 8 y de 10 según la época y la herramienta, y de eso depende cuántos pedir:
# el mismo guion de 20s son 3 clips de 8s o 2 de 10s.
CLIPS_DURACIONES = (8, 10)


def clip_max_s(clip_s: float = 0.0) -> float:
    """Cuánta voz cubre un clip de esa duración, estirado incluido."""
    if clip_s and clip_s > 0:
        return round(float(clip_s) * ESTIRADO_CLIP, 1)
    return CLIP_MAX_S

# ---------------------------------------------------------------------------
# Guion
# ---------------------------------------------------------------------------
# El prompt es del operador y va LITERAL, sin resumir (`prompts/guion.md`).
#
# OJO con el tope de caracteres: el documento original pide 260 "para un vídeo
# de 15 segundos", pero su PROPIO ejemplo tiene 357 y a 18 car/s eso son 20s,
# no 15. Forzar los 260 con reintentos deja el guion telegráfico ("¿Piel grasa?
# ¿Residuo blanco?"). Así que el tope es la DURACIÓN que se quiere, no lo que
# quepa en los clips.
# Velocidad de locución, MEDIDA sobre vídeos ya montados (guion / duración del
# audio de Fish). No es un detalle: con el mismo guion, "audio hombre vendedor"
# corre a 23,6 car/s y "influencer" a 15,4 — 20s con una son 30s con la otra, y
# de eso depende cuántos clips hay que generar.
CARACTERES_POR_SEGUNDO = 17.8      # media de los 20 medidos, sin acelerar
# Para decidir CUÁNTOS CLIPS se usa la voz LENTA, no la media: la voz se sortea
# después de escribir el guion, así que hay que ponerse en lo peor. Quedarse
# corto obliga a estirar el vídeo y deforma el gesto de la mano; sobrar medio
# clip no se nota, porque el montaje recorta a la duración de la voz.
CARACTERES_POR_SEGUNDO_LENTA = 15.4
# Lo que tiene que DURAR el guion. No se calcula como "lo que quepa en los
# clips" (al pasar a clips de 8s habría dado 683 caracteres, guiones del doble
# de largos sin que nadie lo pidiera): es una decisión del formato.
#
# DIECISÉIS y no veinte, que es lo que estaba: el vídeo son dos clips de 8s, o
# sea 16s de material, y todo lo que la voz pase de ahí lo rellena el montaje
# rebobinando. A 20s el guion se iba a 356 caracteres y el peor caso eran 4,3s
# repetidos; a 16s son ~284 caracteres y como mucho 1,1s. De propina, 284 está
# mucho más cerca de los 260 que pide el prompt del curso —que llevábamos
# dejando pasar— y el vídeo sigue por encima de `DURACION_MINIMA_S`.
GUION_OBJETIVO_S = 16.0
# Mínimo del reto en el que se usa este nicho. Ver `DURACION_MINIMA_S` del POV
# BOF: mismo criterio, otro número.
DURACION_MINIMA_S = float(os.getenv("POV_BOF_LARGO_DURACION_MINIMA_S", "15"))
GUION_MAX_CARACTERES = int(GUION_OBJETIVO_S * CARACTERES_POR_SEGUNDO)  # ~356


def segundos_de(guion: str, voz: str = "") -> float:
    """Cuánto va a durar ese guion locutado, en segundos.

    Con `voz` (el `reference_id` o su etiqueta) se usa SU velocidad medida; sin
    ella, la media. Las medidas se van afinando solas con cada vídeo que se
    monta (ver `services/velocidad_voz.py`).
    """
    n = len((guion or "").strip())
    if not n:
        return 0.0
    from src.nicho_pov_bof_largo.services import velocidad_voz

    return n / velocidad_voz.caracteres_por_segundo(voz)


def clips_necesarios(guion: str, voz: str = "", clip_s: float = 0.0) -> int:
    """Cuántos clips hacen falta para que quepa ese guion.

    La voz manda: si dura más de lo que dan los clips, el montaje tiene que
    estirarlos y el gesto de la mano se deforma. Se calcula por caracteres
    porque hay que saberlo ANTES de locutar, cuando aún no hay audio que medir.

    Sin voz elegida se cuenta con la más lenta del banco: es lo que evita
    quedarse corto justo cuando toca la que más se alarga.

    `clip_s` es la duración de los clips que va a generar el operador (8 o 10
    segundos). Cambia la cuenta entera: el mismo guion de 20s son tres clips de
    8s o dos de 10s. Sin él se usa el valor de `.env`.
    """
    n = len((guion or "").strip())
    if not n:
        return CLIPS_POR_VIDEO
    if voz:
        from src.nicho_pov_bof_largo.services import velocidad_voz

        segundos = n / velocidad_voz.caracteres_por_segundo(voz)
    else:
        segundos = n / CARACTERES_POR_SEGUNDO_LENTA
    cabe = clip_max_s(clip_s)
    hacen_falta = -(-int(segundos * 100) // int(cabe * 100))  # techo
    return max(CLIPS_POR_VIDEO, min(CLIPS_MAXIMOS, hacen_falta))


def prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


# Los dos ESTILOS de guion que publica el curso para el vídeo de 20s. Cambian
# por dónde
# EMPIEZA el guion, que es lo que decide si alguien se queda:
#   precio → "Han ajustado el precio de…" y el dolor va en medio.
#   dolor  → tres a cinco problemas dirigidos al espectador y el precio al final.
# No confundir con el "gancho" del vídeo, que es el texto quemado de arriba.
# Lo demás (duración, tope de caracteres, salida) es igual en los dos, así que
# el resto del nicho no se entera de cuál se usó.
# Por debajo de esto, el pedido no suele llevar envío gratis, así que la CTA
# se queda sin esa parte: es el mismo criterio que con el pago a plazos, y por
# el mismo motivo — un vídeo que promete algo que el comprador no se encuentra
# es lo que trae infracciones.
PRECIO_MIN_ENVIO_GRATIS = float(os.getenv("PRECIO_MIN_ENVIO_GRATIS", "10"))


def hay_envio_gratis(textos: dict) -> bool:
    """¿Este producto lleva envío gratis de verdad?

    Lo que manda es lo que pone la FICHA (`envio`, que lee el extractor):
    "gratis" a secas es gratis, y "condicionado" —el típico "envío gratis en
    pedidos de más de 20 €" o "hasta 3,99 € en el envío"— NO lo es, por caro
    que sea el producto.

    Solo cuando la captura no dice nada se cae al precio, que es una
    aproximación: por debajo del mínimo casi nunca lo hay.
    """
    from src.nicho_pov_bof import config as pov_config

    dice = str(textos.get("envio") or "").strip().lower()
    if dice == "gratis":
        return True
    if dice:
        return False
    return pov_config.precio_num(textos.get("precio")) >= PRECIO_MIN_ENVIO_GRATIS


# Las dos CTA. Las dos cumplen lo que pide el curso —carrito naranja y aplicar
# los cupones—; lo que cambia es si además se nombra el envío gratis.
CTA_CUPONES = "Ve al carrito naranja y aplica tus cupones."
CTA_CUPONES_ENVIO = (
    "Ve al carrito naranja, aplica tus cupones y revisa el envío gratis."
)
# A partir de qué tamaño de guion cabe la CTA larga. En un guion de 284
# caracteres los 67 de la CTA con envío son el 24% del vídeo: casi cuatro
# segundos de los dieciséis gastados en el cierre, y lo que se queda fuera son
# las características del producto, que es lo que vende. En uno de 30s (534
# car) los mismos 67 son el 12%, y ahí sí sobra sitio.
CTA_ENVIO_MIN_CARACTERES = 400


def cta_final(plazos: bool, envio: bool, caracteres: int = 0) -> str:
    """La última frase del guion, con solo lo que ese producto cumple y lo que
    le CABE.

    **Cada promesa se dice UNA vez.** Los plazos ya los cuenta el cuerpo del
    guion —el bloque de `guion_plazos.md` pide una frase de financiación justo
    antes del cierre—, así que la CTA no los repite: decir "puedes pagarlo en
    cómodos plazos" y tres segundos después "revisa el pago a plazos" era la
    misma promesa dos veces, y en un guion de 284 caracteres eso son 25 que no
    se pueden gastar en vender.

    Y el envío gratis solo entra si el guion da para ello (`caracteres`): es la
    promesa MENOS importante de las tres —los cupones son lo que de verdad hay
    que decir— y en el vídeo corto se lleva un cuarto del tiempo. En los de 30s
    o más se dice, porque ahí no le quita sitio a nada. Sin `caracteres` se
    asume que cabe.

    `plazos` se sigue recibiendo porque las dos condiciones se leen juntas en
    todo el nicho y quitarlo de la firma obligaría a tocar cada llamada por un
    parámetro que puede volver el día que los plazos salgan del cuerpo.
    """
    if not envio:
        return CTA_CUPONES
    if caracteres and caracteres < CTA_ENVIO_MIN_CARACTERES:
        return CTA_CUPONES
    return CTA_CUPONES_ENVIO


# La ESCALERA de cierres, de corta a larga. El cierre es la pieza con la que se
# cuadra la duración del vídeo: el cuerpo lo escribe Gemini y no se toca, pero
# la CTA es un literal nuestro y cambiarla no cuesta una llamada.
#
# Todas dicen lo obligatorio —carrito naranja y aplicar los cupones—; lo que
# sube por la escalera son las promesas de más y la coletilla del curso. Solo
# se ofrece lo que el producto CUMPLE (`plazos` / `envio`): prometer un envío
# gratis que el comprador no se encuentra es lo que trae infracciones.
CTA_CUPONES = "Ve al carrito naranja y aplica tus cupones."
CTA_CUPONES_BARATO = (
    "Ve al carrito naranja y aplica tus cupones para llevártelo aún más barato."
)
CTA_ENVIO = "Ve al carrito naranja, aplica tus cupones y revisa el envío gratis."
CTA_PLAZOS = (
    "Ve al carrito naranja, aplica tus cupones y revisa el pago a plazos."
)
CTA_ENVIO_BARATO = (
    "Haz click en el carrito naranja y aplica tus cupones para llevártelo aún "
    "más barato y con envío gratis."
)
CTA_TODO = (
    "Haz click en el carrito naranja y aplica tus cupones para llevártelo aún "
    "más barato, con envío gratis y pudiendo pagarlo en cómodos plazos."
)


def ctas_posibles(plazos: bool, envio: bool) -> tuple[str, ...]:
    """Los cierres que ese producto puede decir, de corto a largo.

    Los plazos van al final de la escalera a propósito: el cuerpo del guion ya
    lleva su frase de financiación (`guion_plazos.md`), así que nombrarlos en
    el cierre es decir la misma promesa dos veces. Se acepta solo cuando el
    guion se ha quedado corto y hay que rellenar — antes que dejar el vídeo por
    debajo del mínimo, mejor repetir la promesa.
    """
    escalera = [CTA_CUPONES, CTA_CUPONES_BARATO]
    if envio:
        escalera += [CTA_ENVIO, CTA_ENVIO_BARATO]
    if plazos:
        escalera.append(CTA_PLAZOS)
    if plazos and envio:
        escalera.append(CTA_TODO)
    return tuple(sorted(dict.fromkeys(escalera), key=len))


def cuerpo_sin_cta(guion: str) -> str:
    """El guion sin su última frase (el cierre). Vacío si no se reconoce."""
    if not guion or not _CTA_FINAL_RE.search(guion):
        return ""
    return re.sub(r"\s{2,}", " ", _CTA_FINAL_RE.sub("", guion, count=1)).strip()


def cambiar_cta(guion: str, nueva: str) -> str:
    """El mismo guion con otro cierre. Devuelve el original si no lo reconoce."""
    if not guion or not _CTA_FINAL_RE.search(guion):
        return guion
    # Con `lambda` y no con el texto suelto: un cierre con una barra invertida
    # la interpretaría `re.sub` como grupo. Y con espacio delante, que el patrón
    # se come el que separaba la frase anterior.
    pegado = _CTA_FINAL_RE.sub(lambda _m: " " + nueva, guion, count=1)
    return re.sub(r"\s{2,}", " ", pegado).strip()


def ventana_video(segundos_pedidos: float = 0, metraje: float = 0) -> tuple[float, float]:
    """Entre qué dos duraciones tiene que caer el vídeo.

    El suelo es lo que se prometió: los 15s del reto, o los 30/40/60 que se
    hayan pedido.

    El techo son DOS cosas a la vez, y manda la más pequeña:

    - la duración del formato (`GUION_OBJETIVO_S`, 16s), porque el vídeo se
      quiere de 15-16s y no de los 20 que darían dos clips de 10;
    - el metraje que hay de verdad, porque pasarse de ahí es rebobinar clip.

    Un segundo por encima no se nota —lo tolera `VENTANA_TOLERANCIA_S`—, pero
    no es a lo que se apunta.
    """
    pedidos = float(segundos_pedidos or 0)
    suelo = pedidos if pedidos > 0 else DURACION_MINIMA_S
    # El vídeo normal va de 15 a 16: un 6,7% de holgura sobre el suelo. Los
    # pedidos de 30/40/60 se tratan igual (30 → 32) en vez de dejarles medio
    # segundo, que no da para mover el cierre de sitio.
    objetivo = suelo * (GUION_OBJETIVO_S / DURACION_MINIMA_S)
    techo = min(objetivo, float(metraje)) if metraje and metraje > 0 else objetivo
    return (round(suelo, 1), round(max(techo, suelo + 0.5), 1))


# Cuánto se tolera pasarse del techo antes de dar el encaje por malo.
VENTANA_TOLERANCIA_S = 1.0


ESTILOS_GUION: dict[str, dict[str, str]] = {
    "precio": {"label": "Urgencia de precio", "fichero": "guion.md"},
    "dolor": {"label": "Punto de dolor", "fichero": "guion_dolor.md"},
}
ESTILO_GUION_DEFECTO = "precio"


# La CTA final de un guion ya escrito, para poder cambiarla sin volver a
# llamar a la IA: un producto de 9,71 € no tiene envío gratis y uno de 20 € no
# llega al mínimo de los plazos, y el guion se queda prometiéndolo.
#
# Se sustituye la FRASE ENTERA en vez de recortar trozos: quitando solo "el
# pago a plazos" se llevaba por delante el "revisa" y quedaba "…y el envío
# gratis", que suena raro. La CTA empieza siempre por el carrito naranja.
# La frase entera que habla del carrito naranja, empiece como empiece. Estuvo
# atada a los verbos del curso ("Ve al…", "Haz click en el…") y se escapaban las
# que Gemini escribe por su cuenta —"Clica el carrito naranja para aplicar
# cupones…"—: con el cierre sin reconocer, ni se le quitaba la promesa que el
# producto no cumple ni se podía usar para cuadrar la duración.
_CTA_FINAL_RE = re.compile(
    r"[^.!?]*\bcarrito\s+naranja\b[^.!?]*[.!?]",
    re.IGNORECASE,
)


# El mínimo de pedido que el curso metía en la frase de los plazos ("en
# pedidos superiores a 30 euros"). Ya no es cierto —TikTok los ofrece en
# pedidos pequeños: capturado uno de 20,99 € con tres pagos— y los guiones
# escritos antes lo siguen diciendo. Se quita del texto, que es una condición
# suelta: sin ella la frase sigue entera ("y podrás financiarlo en cómodos
# plazos"). Reescribirlos con IA costaría una llamada por producto.
_MINIMO_PLAZOS_RE = re.compile(
    r"\s*,?\s*(?:"
    r"(?:en|para)\s+(?:los\s+)?pedidos?\s+(?:superiores?\s+a|de\s+m[áa]s\s+de|"
    r"por\s+encima\s+de|a\s+partir\s+de)"
    r"|si\s+(?:tu|el)\s+pedido\s+(?:supera|pasa\s+de|es\s+superior\s+a)"
    r"|(?:en\s+)?compras\s+(?:superiores?\s+a|de\s+m[áa]s\s+de)"
    r")\s+(?:los\s+)?\d+[\d.,]*\s*(?:€|euros?)",
    re.IGNORECASE,
)


def sin_minimo_plazos(guion: str) -> str:
    """Quita del guion la condición de importe de los plazos. Idempotente."""
    if not guion:
        return ""
    limpio = _MINIMO_PLAZOS_RE.sub("", guion)
    return re.sub(r"\s{2,}", " ", limpio).strip()


def recortar_cta(guion: str, *, plazos: bool, envio: bool) -> str:
    """El guion con la CTA que le toca a ese precio. Idempotente."""
    if not guion:
        return ""
    guion = sin_minimo_plazos(guion)
    # El tamaño del guion ES el que decide si el envío gratis cabe: un guion de
    # 30s lo dice y uno de 16s no. Se mide el guion entero (CTA vieja incluida)
    # porque las dos CTA se diferencian en 24 caracteres y el umbral está a 116
    # de distancia: ninguna decisión cambia por ese matiz.
    nueva = cta_final(plazos, envio, len(guion.strip()))
    if not _CTA_FINAL_RE.search(guion):
        return guion          # sin CTA reconocible no se toca nada
    return cambiar_cta(guion, nueva)


def cta_desfasada(guion: str, *, plazos: bool, envio: bool) -> bool:
    """¿Este guion promete algo que su precio no cumple?"""
    bajo = (guion or "").lower()
    return (not plazos and "plazos" in bajo) or (
        not envio and ("envío gratis" in bajo or "envio gratis" in bajo)
    )


# Duraciones que se pueden pedir a mano, como en el POV BOF. `0` = la del
# curso (~20s), que es lo normal; las demás son para los productos con
# requisitos ("dos vídeos de 30 segundos" a cambio de la muestra).
SEGUNDOS_GUION_OPCIONES = (0, 30, 40, 60)

# Acabado del bloque de texto. Desde sep 2026 el de serie es el BLANCO LISO
# (tres líneas iguales, sin color ni destello), que es el que usan los POV de
# 20s nuevos. El defecto vive AQUÍ y no en la pantalla: la APK cachea el
# bundle, así que un móvil con la versión vieja no manda el campo y el vídeo
# salía con el estilo clásico sin que nadie lo hubiera pedido.
#
# Por eso "" no significa "clásico" sino "no me lo han dicho": para pedir el
# clásico a propósito hay que mandar "clasico".
ESTILO_TEXTO_DEFECTO = "blanco"
# Los dos acabados, como los eligen desde la pantalla.
ESTILOS_TEXTO = ("blanco", "clasico")
# Cuál le toca a cada gancho cuando nadie ha dicho nada. No es un capricho: el
# de punto de dolor abre con preguntas al espectador y el bloque blanco liso
# (tres líneas iguales, sin color) es el que usan los POV de 20s para eso; el
# de urgencia de precio va con el clásico de color, que llama más y es lo que
# pega con una oferta.
ESTILO_TEXTO_POR_GANCHO = {"dolor": "blanco", "precio": "clasico"}


def estilo_texto_de(estilo_guion: str = "") -> str:
    """El acabado que le toca a ese gancho si nadie ha elegido."""
    return ESTILO_TEXTO_POR_GANCHO.get(
        (estilo_guion or "").strip().lower(), ESTILO_TEXTO_DEFECTO,
    )


def estilo_texto_valido(valor: str = "", estilo_guion: str = "") -> str:
    """Lo que hay que pasarle al montador: "blanco" o "" (el clásico).

    Con `estilo_guion` (precio / dolor), el vacío deja de ser un único valor de
    serie y pasa a ser el que le toca a ESE gancho.
    """
    v = (valor or "").strip().lower()
    if v == "clasico":
        return ""
    if v == "blanco":
        return "blanco"
    elegido = estilo_texto_de(estilo_guion)
    return "" if elegido == "clasico" else elegido


def caracteres_guion(segundos: float = 0) -> int:
    """Tope de caracteres para ese guion. Sin `segundos`, el del curso."""
    if segundos and segundos > 0:
        return int(round(segundos * CARACTERES_POR_SEGUNDO))
    return GUION_MAX_CARACTERES


def prompt_guion(
    plazos: bool = False,
    estilo: str = ESTILO_GUION_DEFECTO,
    envio_gratis: bool = True,
    segundos: float = 0,
) -> str:
    """El prompt del curso, con el bloque de plazos pegado si toca.

    Va LITERAL y nunca se toca. Lo de plazos es un añadido al final
    (`guion_plazos.md`), no una versión aparte: así el guion de un producto
    caro es el mismo de siempre con una frase más, y cualquier cambio del curso
    se sigue aplicando a los dos ganchos.
    """
    # OJO con el nombre: en este nicho "gancho" es el TEXTO QUEMADO de arriba
    # del vídeo (`con_gancho`). Esto es otra cosa: por dónde empieza lo que
    # dice la voz.
    meta = ESTILOS_GUION.get(estilo) or ESTILOS_GUION[ESTILO_GUION_DEFECTO]
    base = (prompts_dir() / meta["fichero"]).read_text(encoding="utf-8").strip()
    # El de dolor lleva nota de cabecera para quien lo lea en el repo.
    if base.startswith("<!--"):
        base = base.split("-->", 1)[1].strip()
    base = base.replace(
        "{{CTA_FINAL}}", cta_final(plazos, envio_gratis, caracteres_guion(segundos))
    )
    if plazos:
        extra = (prompts_dir() / "guion_plazos.md").read_text(encoding="utf-8")
        # El fichero lleva una cabecera para quien lo lea en el repo; a Gemini
        # solo se le manda lo que va después del separador.
        _, _, cuerpo = extra.partition("\n---\n")
        base = f"{base}\n\n{cuerpo.strip()}"
    return _alargar(base, segundos) + _caracteristicas(segundos) + _epoca()


# Por debajo de qué parte del tope se considera que el guion se quedó corto.
# Gemini apunta al máximo y se queda lejos: midiendo cinco productos salieron
# 228, 240, 284, 287 y 410 caracteres para topes de 284 y 534, o sea vídeos de
# 14,4s cuando el mínimo del reto son 15. Decirle el suelo es gratis; un
# reintento por quedarse corto costaría una llamada por producto.
GUION_MINIMO_RATIO = 0.93


def _caracteristicas(segundos: float = 0) -> str:
    """Añadido NUESTRO: cuánto tiene que medir el guion y en qué se gasta.

    El cierre se recortó a propósito (`cta_final`) para que el hueco fuera a
    contar el producto, y eso hay que pedirlo: si no, Gemini rellena los
    caracteres que sobran estirando la urgencia de precio con otras palabras
    ("a un precio increíble, aprovéchalo ahora"), que es exactamente lo que
    hace que el vídeo suene a anuncio desde la primera frase.

    Concretar es lo que vende y además es lo que no da problemas: una medida o
    un material salen de la ficha, mientras que "lo soluciona todo" es una
    promesa definitiva de las que el curso prohíbe.
    """
    tope = caracteres_guion(segundos)
    minimo = int(tope * GUION_MINIMO_RATIO)
    return (
        f"\n\nOTRO APUNTE: el guion tiene que MEDIR entre {minimo} y {tope} "
        "caracteres. El máximo ya lo sabes; el mínimo es igual de importante, "
        "porque el vídeo dura lo que dure la voz y un guion corto deja el "
        "vídeo por debajo de lo que hace falta. "
        "Y el cierre es corto a propósito: todo el sitio que "
        "queda va a CARACTERÍSTICAS CONCRETAS del producto que se vean en las "
        "fotos o estén en la ficha (de qué es, qué medidas o capacidad tiene, "
        "qué trae, cómo se usa). No rellenes repitiendo lo del precio con "
        "otras palabras ni alargando el cierre: una característica de verdad "
        "vende más que un adjetivo."
        "\n\nCÓMO SUENA: esto no se lee, lo DICE una persona grabándose con "
        "el móvil en su casa. Frases completas y con verbo, como se habla. "
        "Nada de titulares sin verbo ('Precio mejorado en estas zapatillas'), "
        "nada de frases sueltas de tres palabras ('El impacto frustra.') y "
        "nada de lengua de ficha de producto: no digas 'ofrece', 'cuenta "
        "con', 'permite', 'proporciona' ni 'dispone de' — di lo que hace el "
        "producto como se lo contarías a un amigo ('amortiguan un montón', "
        "'agarran bien'). Y empieza con una de las aperturas de precio que se "
        "te han dado ARRIBA, copiada tal cual: son verbales a propósito."
    )


def _epoca() -> str:
    """Añadido NUESTRO: en qué época del año se va a publicar.

    El prompt del curso no sabe la fecha, así que para una tumbona escribe «si
    te vas a la playa» aunque sea noviembre. Es la misma frase que lleva el
    prompt de imagen y con la misma salvaguarda: al producto al que la época le
    da igual no se le cambia nada.
    """
    from src.nicho_pov_bof import config as pov_config

    return (
        "\n\nÚLTIMO APUNTE: el vídeo se publica en "
        f"{pov_config.epoca_actual()}. Si el producto es de temporada, habla "
        "de usarlo en esta época y no en otra. Si le da igual la época, no "
        "cambies nada por esto." + ' Esto cambia solo el CONTEXTO en el que se habla del producto, nunca lo que hace: no le atribuyas usos, materiales, resistencias ni capacidades de temporada que no estén en la ficha.'
    )


def _alargar(prompt: str, segundos: float) -> str:
    """Pone en el prompt del curso el tope que de verdad se quiere.

    Los dos prompts llevan sus cifras metidas en la prosa —y distintas: el de
    precio habla de 260 caracteres y el de dolor de 360—, así que no vale con
    pegar una línea al final: se contradiría con lo que ya pone. Se sustituyen
    las cifras.

    Se hace SIEMPRE, no solo cuando se pide un vídeo más largo. Con el objetivo
    en 284 caracteres, el prompt de punto de dolor seguiría pidiendo 360: se
    pasaría en casi todos los productos y cada uno gastaría la llamada extra de
    la reescritura (`guionista._acortar`). Pedirlo bien a la primera es gratis.

    Con `segundos` se pide además lo que de verdad cambia en un vídeo largo, que
    no es el número sino QUÉ se cuenta: en dieciséis segundos cabe el titular y
    en treinta hay que hablar del producto.
    """
    import re

    objetivo = segundos if segundos and segundos > 0 else GUION_OBJETIVO_S
    # `caracteres_guion(0)` es el tope de serie, y es el mismo con el que se
    # comprueba el guion después (`guionista.escribir`). Calcularlo aquí a
    # partir de los segundos daría 285 contra un tope de 284, y ese carácter de
    # diferencia dispara una reescritura entera.
    tope = caracteres_guion(segundos)
    prompt = re.sub(r"\b\d{3} caracteres", f"{tope} caracteres", prompt)
    prompt = re.sub(r"\b\d{1,3} segundos", f"{round(objetivo)} segundos", prompt)
    # El bloque de plazos dice su tope de otra forma ("no debe pasar de 360"),
    # sin la palabra "caracteres" detrás. Si no se cambia también, el prompt se
    # contradice: el cuerpo pide 284 y el añadido de plazos permite 360.
    prompt = re.sub(r"(?<=pasar de )\d{3}", str(tope), prompt)
    if not segundos or segundos <= 0:
        return prompt

    return prompt + (
        "\n\nEste vídeo es MÁS LARGO de lo habitual: "
        f"{round(segundos)} segundos, unos {tope} caracteres. Mantén la "
        "estructura y el orden que se te piden arriba, pero desarróllalos: usa "
        "TODAS las fotos que te mando para contar características concretas "
        "(materiales, medidas, qué trae, cómo se usa, para quién es) y, si el "
        "guion empieza por puntos de dolor, da más y más concretos. No repitas "
        "lo del precio con otras palabras para llenar."
    )


# ---------------------------------------------------------------------------
# Voces (Fish Audio)
# ---------------------------------------------------------------------------
# Banco elegido por el operador escuchando muestras. El operador solo elige
# SEXO; la voz concreta se sortea, igual que en el POV BOF con sus mp3.
#
# Son `reference_id` de la biblioteca pública de Fish. Se eligieron de título
# genérico a propósito: las voces más usadas del catálogo español son clones de
# personas identificables (Farid Dieck, Mario Castañeda…) y usarlas en vídeos
# de afiliación es suplantación.
#
# SEP 2026 — el banco se cambió ENTERO. Las veinte de antes se habían buscado
# por título ("vendedor", "locutor", "publicidad", "influencer") y sonaban a
# anuncio: el espectador sabe que le van a vender en la primera frase, que es
# justo lo que hay que evitar. Estas se buscaron al revés —etiquetas
# `conversational`, `friendly`, `relaxed`, `casual`, y fuera todo lo
# `advertisement`/`announcer`/`narration`— y son gente hablando a cámara.
# Las velocidades de las viejas siguen en `velocidad_voz.MEDIDAS_INICIALES`
# porque hay vídeos ya montados con ellas.
VOCES: dict[str, list[dict[str, str]]] = {
    # Las diez las eligió el operador escuchándolas DECIR un guion nuestro
    # (281/294 car, con su CTA), no la muestra del catálogo de Fish.
    "hombre": [
        {"id": "1584879dbfe1457c96b516aa14dcaac1", "label": "Joven Conversador Relajado"},
        {"id": "fa2683f51e2443ff9928e8ebfe997c83", "label": "Joven Relajado"},
        {"id": "712fb96185f646fda4849288e7f93585", "label": "Amigo con Humor"},
        {"id": "292a1a41081342988b816d8d7d79dbf8", "label": "Hombre Relajado"},
        {"id": "f2f858d51e8e4422acf0a4d838d85aa3", "label": "Chico"},
    ],
    "mujer": [
        {"id": "049dbfa772814ec88d030b6a4b9cc578", "label": "Voz Dulce y Cercana"},
        {"id": "429c4e4dbfa246d8a2cf7ee034aad518", "label": "Voz Dulce Femenina"},
        {"id": "1b3aceb9964445f1883b9a71eb335766", "label": "Amiga Cercana"},
        {"id": "039303edce924eb08c35580705d9bfcf", "label": "Compania Suave"},
        {"id": "86151fb1bf8b4dc4a2f35e79e6c2ffd5", "label": "Voz Joven Natural"},
    ],
}

SEXOS = tuple(VOCES)

# Modelo gratuito de Fish. El de pago es el mismo motor con licencia comercial
# plena; se cambia aquí (ver `services/voz.py` para la tarifa).
FISH_MODEL = os.getenv("FISH_MODEL", "s2.1-pro-free")
FISH_TTS_URL = "https://api.fish.audio/v1/tts"


def fish_api_key() -> str:
    return (os.getenv("FISH_API_KEY") or "").strip()


# ---------------------------------------------------------------------------
# Nivelado de la voz
# ---------------------------------------------------------------------------
# El operador la quiere "rozando la línea roja sin distorsionar". La cadena es
# la del POV BOF pero con MÁS margen de pico: con `TP=-1.5` y limitador 0.9
# —los valores de allí— una voz de Fish salió a +0,20 dBTP, o sea recortando.
# Los audios de Fish tienen picos distintos a las grabaciones humanas.
# Medido con TP=-2.0 y 0.89: -13,1/-13,6 LUFS con picos en -1,1/-1,6 dBTP.
VOZ_CADENA = (
    "acompressor=threshold=-20dB:ratio=4:attack=5:release=120:makeup=2,"
    "speechnorm=e=8:r=0.0008:l=1"
)
VOZ_LUFS = -11.0
VOZ_TP = -2.0
VOZ_LIMITER = 0.89

# ---------------------------------------------------------------------------
# Recorte de silencios (para que el vídeo no quede más largo de la cuenta)
# ---------------------------------------------------------------------------
# Fish a veces deja aire muerto al principio/final y alguna pausa larga entre
# frases. Se recorta, pero SIN dejarlo telegráfico:
#   - Principio: se quita el silencio de entrada dejando una pizca (0,08s) para
#     que no empiece cortado de golpe.
#   - Medio y final (`stop_periods=-1`): las pausas de más de `stop_duration`
#     se capan a `stop_silence` (~0,3s) en vez de eliminarse; así una pausa de
#     1,5s baja a 0,3s pero SIGUE habiendo pausa — respira, no atropella.
# `detection=peak` es conservador: solo cuenta como silencio lo que baje de
# -40 dB de pico, así que no se come el arranque suave de una palabra.
# Cuánto se puede acelerar la voz. No es capricho: con el guion de 223 caracteres del POV
# BOF, a velocidad normal solo DOS voces del banco caben en un clip de 10s
# (12s con el estirado), así que todos los vídeos sonarían igual. Con +10%
# entran siete, y en voz hablada un 10% no se percibe como acelerón — sí a
# partir del 15%, donde empieza a sonar atropellado.
#
# Va en la cadena ANTES del nivelado. Las velocidades de `velocidad_voz` se
# guardan NATURALES (allí se descuenta el tempo usado), porque ya no es fijo.
#
# Y hay un suelo además del techo: los retos de TikTok piden vídeos de 10s o
# 15s mínimo, y el vídeo dura lo que dura la voz. Así que una voz demasiado
# rápida para el mínimo se descarta en vez de acelerarla (ver `DURACION_MINIMA`
# de cada nicho).
# TOPE del acelerón, no el acelerón: se acelera lo JUSTO para que la voz quepa
# en los clips, y nunca más de esto. A partir del 15% suena atropellado; el 10%
# está comprobado a oído.
VOZ_TEMPO_MAX = float(os.getenv("VOZ_TEMPO", "1.10"))

# OJO con los dos números: la pausa que QUEDA es `stop_duration + stop_silence`,
# no `stop_silence`. ffmpeg no sabe que hay silencio hasta que han pasado
# `stop_duration` segundos, y ese trozo se queda en el audio. Medido con un wav
# de pausas conocidas: 0.4+0.3 dejaba pausas de 0,70s (y una de 1,2s también
# acababa en 0,70s, o sea que "capar" capaba poco).
#
# Con 0.25+0.18 quedan en 0,43s: sigue habiendo pausa —la voz respira antes de
# la CTA, no atropella— pero se recortan ~0,27s en cada una. En un guion de 20s
# con dos o tres pausas largas eso es medio segundo largo menos de vídeo, que es
# medio segundo menos de rebobinado en los clips.
VOZ_SILENCIO = (
    "silenceremove="
    "start_periods=1:start_silence=0.08:start_threshold=-40dB:"
    "stop_periods=-1:stop_duration=0.25:stop_silence=0.18:stop_threshold=-40dB:"
    "detection=peak"
)


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------
DRIVE_UPLOAD_ROOT = "NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/Nicho_POV_BOF_Largo"


def video_dir() -> Path:
    """Dónde quedan los vídeos montados. Al Drive montado, como el resto del
    Programa 4; si no hay mount (dev local), a `API_TEMP_ROOT`."""
    from src.nicho_pov_bof.services.audio_bank import mount_root

    raiz = mount_root()
    if raiz:
        destino = raiz / DRIVE_UPLOAD_ROOT / "videos"
    else:
        destino = Path(os.getenv("API_TEMP_ROOT", "/tmp")) / "nicho_pov_bof_largo" / "videos"
    destino.mkdir(parents=True, exist_ok=True)
    return destino
