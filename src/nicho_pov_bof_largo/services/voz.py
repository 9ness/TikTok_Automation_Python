"""Locución del guion con Fish Audio + nivelado de volumen.

Dos cosas que no son obvias:

1. **La voz se sortea.** El operador solo elige sexo; cuál de las del banco
   suena lo decide el azar, igual que en el Nicho POV BOF con sus mp3 grabados.

2. **La cadena de nivelado NO es la del POV BOF.** Allí se usa `TP=-1.5` con el
   limitador a 0.9 y funciona porque los audios son grabaciones humanas. Con
   una voz de Fish, esos mismos valores dieron **+0,20 dBTP** — o sea recorte
   audible, justo lo que se quiere evitar. Con `TP=-2.0` y 0.89 queda en
   -13,1/-13,6 LUFS con picos en -1,1/-1,6 dBTP: alto y limpio.

3. **Se recortan silencios** (`config.VOZ_SILENCIO`) para que el vídeo no quede
   más largo de la cuenta: fuera el aire muerto del principio/final y las
   pausas internas largas se capan (~0,3s) sin eliminarlas, para que siga
   sonando orgánico. Va primero en la cadena para que el nivelado mida el audio
   ya ajustado.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from src.nicho_pov_bof_largo import config

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# Tarifa del plan de pago de Fish: $15 por millón de BYTES UTF-8. Con el modelo
# gratuito (`s2.1-pro-free`, el de por defecto) no se cobra, pero el consumo se
# registra igual para poder ver el volumen y para que el día que se cambie a
# pago el coste aparezca solo en el panel.
FISH_USD_PER_MILLON_BYTES = 15.0


# Colchón al descartar voces por velocidad. Las cifras de `velocidad_voz` se
# reajustan solas con cada vídeo, así que una voz que hoy cuadra justo puede
# bajar una décima mañana y colarse sin que quepa. Con medio segundo, la que
# entra cabe de verdad.
MARGEN_VOZ_S = 0.5


def tempo_para(caracteres: int, cps: float, segundos_max: float) -> float:
    """Cuánto hay que acelerar esta voz para que quepa. 1.0 = nada.

    Se acelera lo JUSTO, no siempre lo máximo: acelerar de más acorta el vídeo
    y los retos de TikTok piden un mínimo de duración.
    """
    if not segundos_max or cps <= 0:
        return 1.0
    natural = caracteres / cps
    return max(1.0, round(natural / segundos_max, 3))


def encaje_cta(
    cuerpo: str,
    cps: float,
    ctas,
    *,
    ventana: tuple[float, float],
    tempo_max: float = 0.0,
) -> tuple[str, float, float]:
    """Con qué cierre y qué acelerón cae este guion en la ventana de duración.

    El cuerpo del guion lo escribe Gemini y no se toca: cambiarlo cuesta una
    llamada y además es lo que vende. La pieza con la que se cuadra el vídeo es
    el CIERRE, que es un literal nuestro — de 43 caracteres ("carrito naranja y
    cupones") a 139 (el del curso entero, con envío y plazos). Entre las dos
    puntas hay unos cinco segundos de margen, más que de sobra para encajar.

    El orden de las dos palancas es el que pidió el operador:

    - **Guion largo**: se acorta el cierre, y lo que siga sobrando lo pone el
      acelerón (hasta `VOZ_TEMPO_MAX`; más allá suena atropellado).
    - **Guion corto**: PRIMERO se alarga el cierre, y solo si aun así no llega
      se deja la voz a tono normal. Un 10% de más se oye bien y de paso hace
      que no todos los vídeos suenen igual.

    Por eso, entre dos cierres que caen dentro, gana el MÁS LARGO: es más cosas
    dichas al comprador y deja el vídeo más cerca del metraje que hay.

    Devuelve `(cierre, tempo, duración estimada)`.
    """
    suelo, techo = float(ventana[0]), float(ventana[1])
    tope_tempo = tempo_max or config.VOZ_TEMPO_MAX
    cuerpo = (cuerpo or "").strip()
    mejor: tuple[tuple[float, int], str, float, float] | None = None
    for cta in ctas:
        total = len(f"{cuerpo} {cta}".strip())
        natural = total / cps if cps > 0 else 0.0
        if natural <= 0:
            continue
        # El acelerón JUSTO para no pasar del metraje, nunca más del tope.
        tempo = min(tope_tempo, max(1.0, round(natural / techo, 3))) if techo else 1.0
        dur = natural / tempo
        # Los dos lados no pesan igual. Quedarse corto ROMPE el reto (el vídeo
        # no puntúa), así que cuenta triple; pasarse un segundo del metraje no
        # se nota —es lo que rebobina el montaje— y casi no cuenta. Sin esta
        # asimetría, un cierre que dejaba el vídeo en 14,3s empataba con otro
        # que lo dejaba en 16,6 y ganaba el malo.
        tol = config.VENTANA_TOLERANCIA_S
        if dur < suelo:
            fuera = (suelo - dur) * 3
        elif dur > techo + tol:
            fuera = (dur - techo - tol) * 2
        elif dur > techo:
            fuera = (dur - techo) * 0.1
        else:
            fuera = 0.0
        clave = (round(fuera, 2), -len(cta))
        if mejor is None or clave < mejor[0]:
            mejor = (clave, cta, tempo, dur)
    if mejor is None:
        return ("", 1.0, 0.0)
    return (mejor[1], mejor[2], round(mejor[3], 2))


def clips_para(
    caracteres: int,
    clip_s: float,
    *,
    segundos_min: float = 0.0,
    maximos: int = 4,
    margen_s: float = MARGEN_VOZ_S,
) -> int:
    """Con cuántos clips de `clip_s` segundos se puede locutar ese guion.

    No se calcula con "la voz más lenta del banco" como en el Largo, porque
    aquí la voz ya no se sortea entre todas: se descartan las que no caben y
    las que dejarían el vídeo por debajo del mínimo. Preguntar por la más lenta
    daba dos clips cuando con once voces distintas cabía en uno.

    Así que la pregunta correcta es al revés: el número MÁS PEQUEÑO de clips
    con el que queda alguna voz sorteable.
    """
    from src.nicho_pov_bof_largo.services import velocidad_voz

    todas = [v for banco in config.VOCES.values() for v in banco]

    def _buscar(minimo: float) -> int:
        for n in range(1, max(1, maximos) + 1):
            tope = round(clip_s * n * config.ESTIRADO_CLIP, 1) - max(0.0, margen_s)
            for v in todas:
                cps = velocidad_voz.caracteres_por_segundo(v["id"])
                factor = tempo_para(caracteres, cps, tope)
                if factor > config.VOZ_TEMPO_MAX:
                    continue
                if minimo and (caracteres / cps) / factor < minimo:
                    continue
                return n
        return 0

    # Sin el mínimo si con él no lo cumple NINGUNA combinación. Pasa cuando el
    # guion se queda corto (Gemini escribió 209 caracteres de 284): entonces
    # ninguna voz llega a los 15s, y como poner más clips no alarga la voz, el
    # bucle terminaba devolviendo `maximos` — cuatro clips para un vídeo de
    # trece segundos. Con el mínimo fuera devuelve los que de verdad hacen
    # falta, y del vídeo corto ya avisa `elegir_voz` al locutar.
    return _buscar(segundos_min) or _buscar(0.0) or maximos


def duracion_estimada(
    caracteres: int,
    clip_s: float,
    n_clips: int,
    *,
    segundos_min: float = 0.0,
    margen_s: float = MARGEN_VOZ_S,
) -> tuple[float, float]:
    """Cuánto va a durar el vídeo: `(mínimo, máximo)` en segundos.

    No es una regla de tres con una velocidad media: el vídeo dura lo que dure
    la voz, y la voz sale sorteada entre las que CABEN en esos clips y llegan
    al mínimo. Así que el rango son las duraciones de esas voces, con su
    acelerón aplicado — que es lo que el operador va a ver de verdad.
    """
    from src.nicho_pov_bof_largo.services import velocidad_voz

    tope = round(clip_s * max(1, n_clips) * config.ESTIRADO_CLIP, 1) - max(0.0, margen_s)
    duraciones = []
    for banco in config.VOCES.values():
        for v in banco:
            cps = velocidad_voz.caracteres_por_segundo(v["id"])
            factor = tempo_para(caracteres, cps, tope)
            if factor > config.VOZ_TEMPO_MAX:
                continue
            d = (caracteres / cps) / factor
            if segundos_min and d < segundos_min:
                continue
            duraciones.append(d)
    if not duraciones:
        return (0.0, 0.0)
    return (round(min(duraciones), 1), round(max(duraciones), 1))


def duracion_con_encaje(
    cuerpo: str, ctas, *, ventana: tuple[float, float],
) -> tuple[float, float]:
    """`(mínimo, máximo)` contando con que el cierre se ajusta a cada voz.

    `duracion_estimada` responde a "cuánto duraría este texto tal cual", que es
    lo que valía cuando el guion se locutaba sin tocar. Con el encaje el texto
    ya no es fijo —el cierre lo elige cada voz—, así que el rango honesto es el
    de los vídeos que van a salir de verdad, y sale mucho más estrecho.
    """
    from src.nicho_pov_bof_largo.services import velocidad_voz

    duraciones = []
    for banco in config.VOCES.values():
        for v in banco:
            cps = velocidad_voz.caracteres_por_segundo(v["id"])
            _cta, _t, dur = encaje_cta(cuerpo, cps, ctas, ventana=ventana)
            if dur > 0:
                duraciones.append(dur)
    if not duraciones:
        return (0.0, 0.0)
    return (round(min(duraciones), 1), round(max(duraciones), 1))


def elegir_voz(
    sexo: str,
    rng: random.Random | None = None,
    *,
    caracteres: int = 0,
    segundos_max: float = 0.0,
    segundos_min: float = 0.0,
    margen_s: float = MARGEN_VOZ_S,
    on_log: OnLog = _noop,
) -> dict[str, str]:
    """Una voz al azar del banco del sexo pedido.

    Si se dice cuánto texto hay (`caracteres`) y cuánto vídeo cabe
    (`segundos_max`), se descartan las voces que NO quepan: cada una habla a su
    ritmo y la diferencia es enorme —de 14 a 23,6 caracteres por segundo—, así
    que el mismo guion son 15s con una y 25s con otra. Locutar con una lenta un
    guion medido para una media obliga al montaje a estirar el vídeo, y ahí es
    donde se deforma el gesto de la mano.

    Se puede filtrar porque cuando se locuta los clips YA están subidos: se sabe
    cuánto material hay. Antes se sorteaba a ciegas entre todas.

    Se descarta con un COLCHÓN (`margen_s`): las velocidades se reajustan solas
    con cada vídeo montado, así que una voz que cuadra por una décima hoy puede
    no cuadrar mañana.

    Si con el colchón no cabe ninguna se prueba sin él, y si aún así ninguna se
    sortea entre todas: quedarse sin voz sería peor que estirar un poco. Los
    dos escalones se dicen en el log, porque significan que el vídeo va a pedir
    un clip más de lo previsto.
    """
    sexo = (sexo or "").strip().lower()
    if sexo not in config.VOCES:
        raise ValueError(f"sexo debe ser {' o '.join(config.SEXOS)}, recibido: {sexo!r}")
    candidatas = list(config.VOCES[sexo])
    if caracteres > 0 and segundos_max > 0:
        from src.nicho_pov_bof_largo.services import velocidad_voz

        def _validas(tope: float, minimo: float) -> list[dict[str, str]]:
            salida = []
            for v in candidatas:
                cps = velocidad_voz.caracteres_por_segundo(v["id"])
                t = tempo_para(caracteres, cps, tope)
                if t > config.VOZ_TEMPO_MAX:
                    continue           # ni acelerando al máximo cabe
                if minimo and (caracteres / cps) / t < minimo:
                    continue           # tan rápida que el vídeo no llega al mínimo
                salida.append(v)
            return salida

        con_colchon = _validas(segundos_max - max(0.0, margen_s), segundos_min)
        if con_colchon:
            candidatas = con_colchon
        else:
            justas = _validas(segundos_max, segundos_min)
            if justas:
                on_log(
                    f"[voz] ninguna voz cabe con {margen_s}s de margen en "
                    f"{segundos_max:.1f}s; se sortea entre las {len(justas)} que "
                    "caben justas"
                )
                candidatas = justas
            elif segundos_min:
                sin_minimo = _validas(segundos_max, 0.0)
                if sin_minimo:
                    on_log(
                        f"[voz] ninguna voz llega al mínimo de {segundos_min:.0f}s; "
                        "se sortea entre las que caben y el vídeo saldrá más corto"
                    )
                    candidatas = sin_minimo
            else:
                on_log(
                    f"[voz] NINGUNA voz cabe: {caracteres} caracteres no entran "
                    f"en {segundos_max:.1f}s. Se sortea entre todas y el montaje "
                    "tendrá que estirar o pedir otro clip."
                )
    return (rng or random).choice(candidatas)


def sintetizar(
    texto: str,
    destino: Path,
    *,
    sexo: str = "hombre",
    voz: dict[str, str] | None = None,
    rng: random.Random | None = None,
    # Cuánto vídeo hay para esta voz. Sirve para no sortear una voz lenta que
    # no quepa (ver `elegir_voz`). 0 = no se sabe, se sortea entre todas.
    segundos_max: float = 0.0,
    # Suelo de duración: los retos de TikTok piden 10s o 15s mínimo y el vídeo
    # dura lo que dura la voz. Descarta las voces demasiado rápidas.
    segundos_min: float = 0.0,
    # Los segundos de vídeo que hay DE VERDAD, sin contar el estirado. Es a lo
    # que apunta el acelerón: `segundos_max` es lo máximo que se tolera (con
    # rebobinado incluido) y sirve para no descartar voces del sorteo, pero
    # cuadrar con esto deja el vídeo sin un solo fotograma repetido.
    segundos_ideal: float = 0.0,
    # Para audicionar a otra velocidad sin tocar la de producción.
    tempo: float | None = None,
    # Los cierres que este producto puede decir, de corto a largo
    # (`config.ctas_posibles`). Con ellos se activa el ENCAJE: se prueba cuál
    # deja el vídeo dentro de `ventana` con la voz que ha tocado, y si el audio
    # de verdad se desvía de la ficha se vuelve a locutar con el cierre bueno
    # (el modelo de Fish es gratuito). Sin ellos, el guion va tal cual.
    ctas: tuple[str, ...] = (),
    # `(suelo, techo)` de duración: lo prometido y el metraje que hay.
    ventana: tuple[float, float] = (0.0, 0.0),
    on_log: OnLog = _noop,
) -> dict:
    """Genera el mp3 crudo y lo deja nivelado en `destino`.

    Devuelve `{voz_id, voz_label, texto, caracteres, duracion, lufs, pico}`.
    """
    clave = config.fish_api_key()
    if not clave:
        raise RuntimeError(
            "Falta FISH_API_KEY en el entorno — no se puede locutar el guion."
        )
    texto = " ".join((texto or "").split())
    if not texto:
        raise ValueError("no hay texto que locutar")

    elegida = voz or elegir_voz(
        sexo, rng, caracteres=len(texto), segundos_max=segundos_max,
        segundos_min=segundos_min, on_log=on_log,
    )
    on_log(f"[nicho_pov_bof_largo] voz: {elegida['label']} ({sexo})")

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    crudo = destino.with_name(destino.stem + "_crudo.mp3")

    def _locutar(frase: str) -> None:
        cuerpo = json.dumps({
            "text": frase, "reference_id": elegida["id"], "format": "mp3",
        }).encode("utf-8")
        peticion = urllib.request.Request(config.FISH_TTS_URL, data=cuerpo, headers={
            "Authorization": f"Bearer {clave}",
            "Content-Type": "application/json",
            "model": config.FISH_MODEL,
        })
        try:
            with urllib.request.urlopen(peticion, timeout=180) as r:
                crudo.write_bytes(r.read())
        except urllib.error.HTTPError as e:
            detalle = ""
            try:
                detalle = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            raise RuntimeError(f"Fish Audio devolvió {e.code}: {detalle}") from e
        _registrar_coste(frase, elegida)

    # El ENCAJE: con qué cierre cae el vídeo donde tiene que caer. Esta primera
    # decisión va con la velocidad de FICHA de la voz; al medir el audio se
    # repasa con la de verdad.
    cuerpo_guion = config.cuerpo_sin_cta(texto) if ctas else ""
    encajando = bool(cuerpo_guion and ventana and ventana[1] > 0)
    if encajando:
        from src.nicho_pov_bof_largo.services import velocidad_voz

        cta, _t, _d = encaje_cta(
            cuerpo_guion, velocidad_voz.caracteres_por_segundo(elegida["id"]),
            ctas, ventana=ventana,
        )
        if cta:
            texto = f"{cuerpo_guion} {cta}".strip()
    _locutar(texto)
    # Lo justo para que quepa, nunca más del tope. Sin sitio que respetar
    # (`segundos_max`=0) no se acelera nada.
    # A qué duración se apunta. Son dos cosas distintas y por eso hay dos
    # parámetros:
    #
    #   `segundos_ideal` es el metraje que hay de verdad. Cuadrar con él deja el
    #   vídeo sin un fotograma repetido, y es lo que se busca.
    #   `segundos_max` es lo máximo tolerable (metraje + lo que el montaje puede
    #   rebobinar). Solo manda cuando no se sabe el metraje real.
    #
    # Y por debajo está el suelo del reto: antes de bajar de ahí es mejor que
    # se repita un trozo de clip, porque un vídeo corto no puntúa.
    if encajando:
        # Con encaje el objetivo es el techo de la ventana (el metraje que hay):
        # llegar ahí es el vídeo más largo posible sin repetir un fotograma.
        objetivo = max(ventana[1], segundos_min)
    elif segundos_ideal > 0:
        objetivo = max(segundos_ideal, segundos_min)
    elif segundos_max:
        objetivo = max(0.1, segundos_max - MARGEN_VOZ_S)
    else:
        objetivo = 0.0

    if encajando and tempo is None:
        # SEGUNDA VUELTA del encaje, ya con audio de verdad. La primera se
        # decidió con la velocidad de ficha de la voz, y esa se desvía: midiendo
        # cinco guiones, una voz de ficha 16,6 car/s locutó a 18,7. Aquí se
        # recalcula con la velocidad REAL y, si el cierre que toca es otro, se
        # vuelve a locutar — el modelo de Fish es gratuito, así que la segunda
        # llamada no cuesta nada y evita el vídeo de 13,5s.
        # Hasta dos correcciones. Fish no locuta igual dos veces el mismo texto,
        # así que la velocidad medida en un intento no clava la del siguiente y
        # con una sola pasada quedaban vídeos de 18s. Se repite hasta que el
        # cierre elegido coincide con el que ya está puesto. Cada vuelta es una
        # llamada más al TTS, que con el modelo gratuito no cuesta nada.
        natural = 0.0
        for _vuelta in range(3):
            medidas = _nivelar(crudo, destino, tempo=1.0, on_log=on_log)
            natural = float(medidas.get("duracion") or 0)
            cps_real = (len(texto) / natural) if natural > 0 else 0.0
            puesta = texto[len(cuerpo_guion):].strip()
            otra, _t2, _d2 = encaje_cta(
                cuerpo_guion, cps_real, ctas, ventana=ventana,
            )
            if not otra or otra == puesta or _vuelta == 2:
                break
            on_log(
                f"[voz] {elegida['label']} locuta a {cps_real:.1f} car/s: el "
                f"cierre de {len(puesta)} car deja el vídeo fuera de sitio, "
                f"pruebo con uno de {len(otra)}"
            )
            texto = f"{cuerpo_guion} {otra}".strip()
            _locutar(texto)
        tempo = 1.0
        if natural > objetivo + 0.05:
            tempo = min(config.VOZ_TEMPO_MAX, round(natural / objetivo, 3))
            medidas = _nivelar(crudo, destino, tempo=tempo, on_log=on_log)
        on_log(
            f"[voz] encaje: cierre de {len(texto) - len(cuerpo_guion) - 1} car "
            f"· x{tempo:.3f} · {medidas.get('duracion', 0):.1f}s "
            f"(ventana {ventana[0]:.0f}-{ventana[1]:.0f}s)"
        )
    elif tempo is None:
        from src.nicho_pov_bof_largo.services import velocidad_voz

        tempo = min(
            config.VOZ_TEMPO_MAX,
            tempo_para(
                len(texto),
                velocidad_voz.caracteres_por_segundo(elegida["id"]),
                objetivo,
            ),
        )
        if tempo > 1.0:
            on_log(f"[voz] acelerada x{tempo:.2f} para cuadrar con {objetivo:.1f}s")
    if not (encajando and tempo is None):
        # Con encaje ya se ha nivelado ahí arriba; aquí solo entra el camino de
        # siempre y el de audicionar con un tempo impuesto.
        medidas = _nivelar(crudo, destino, tempo=tempo, on_log=on_log)
    # Lo de arriba es una PREDICCIÓN (caracteres / velocidad de ficha de la
    # voz). Aquí ya hay audio de verdad, así que se comprueba: si se ha pasado
    # del sitio que hay, se vuelve a nivelar con el tempo que de verdad hacía
    # falta. Sin esto, una voz que ese día sale más lenta que su ficha alarga el
    # vídeo, y todo el exceso lo rellena el montaje rebobinando clip.
    if objetivo > 0 and not encajando:
        tempo, medidas = _encajar(
            crudo, destino,
            tempo=float(tempo or 1.0),
            medidas=medidas,
            tope=objetivo,
            minimo=segundos_min,
            on_log=on_log,
        )
    try:
        crudo.unlink()
    except OSError:
        pass

    return {
        "voz_id": elegida["id"],
        "voz_label": elegida["label"],
        # El texto que de verdad se ha locutado: con encaje el cierre puede no
        # ser el que traía el guion guardado.
        "texto": texto,
        "caracteres": len(texto),
        # Hace falta para apuntar la velocidad NATURAL de la voz.
        "tempo": float(tempo or 1.0),
        **medidas,
    }


# Por debajo de esto no se vuelve a codificar: rehacer el nivelado para ganar
# dos décimas es medio minuto de ffmpeg por un recorte que nadie ve.
_MERECE_LA_PENA_S = 0.25


def _encajar(
    crudo: Path,
    destino: Path,
    *,
    tempo: float,
    medidas: dict,
    tope: float,
    minimo: float = 0.0,
    on_log: OnLog = _noop,
) -> tuple[float, dict]:
    """Segunda pasada: si la voz ha salido más larga de lo previsto, se encaja.

    El tempo de la primera pasada se calcula con la velocidad de FICHA de la voz
    (`velocidad_voz`), que es una media de vídeos anteriores. El audio de verdad
    se desvía —el mismo guion no se locuta igual dos veces, y una voz recién
    metida en el banco arranca con la media del banco—, y cuando se desvía por
    arriba el vídeo dura más de lo que se anunció en la ficha del producto y el
    montaje rellena la diferencia rebobinando clip.

    Aquí ya está el mp3 medido, así que se corrige con una regla de tres sobre
    la duración REAL. Se respetan los dos límites de siempre: el tope de
    acelerón (`VOZ_TEMPO_MAX`, más allá suena atropellado) y el mínimo de
    duración del reto — es preferible un vídeo con algo de rebobinado a uno que
    no llega a los segundos que pide TikTok.
    """
    dur = float(medidas.get("duracion") or 0)
    if dur <= 0 or dur <= tope + 0.05:
        return tempo, medidas

    # Lo que hace falta para caber, sin bajar del mínimo del reto.
    objetivo = max(tope, minimo) if minimo else tope
    if dur <= objetivo + _MERECE_LA_PENA_S:
        return tempo, medidas
    nuevo = min(config.VOZ_TEMPO_MAX, round(tempo * dur / objetivo, 3))
    if nuevo <= tempo + 0.005:
        on_log(
            f"[voz] la voz ha salido en {dur:.1f}s y solo caben {tope:.1f}s, "
            f"pero ya va al máximo (x{tempo:.2f}): el montaje rebobinará "
            f"{dur - tope:.1f}s"
        )
        return tempo, medidas

    on_log(
        f"[voz] ha salido en {dur:.1f}s para {tope:.1f}s de sitio; "
        f"reajusto x{tempo:.2f} → x{nuevo:.2f}"
    )
    nuevas = _nivelar(crudo, destino, tempo=nuevo, on_log=on_log)
    return nuevo, nuevas


def _registrar_coste(texto: str, voz: dict) -> None:
    """Consumo de Fish. Con el modelo gratuito el coste es 0, pero el volumen
    se registra igual (ver la constante de tarifa)."""
    from src import cost_tracking

    bytes_utf8 = len(texto.encode("utf-8"))
    gratis = config.FISH_MODEL.endswith("-free")
    coste = 0.0 if gratis else bytes_utf8 / 1_000_000 * FISH_USD_PER_MILLON_BYTES
    try:
        cost_tracking.record_custom(
            kind="fish_tts",
            units=bytes_utf8,
            unit_label="bytes",
            cost_usd=coste,
            detail=f"{config.FISH_MODEL} · {voz['label']}",
        )
    except Exception:
        # Sin tracker activo (pruebas, scripts sueltos) no es motivo para
        # tirar abajo la locución.
        pass


def _medir(audio: Path, extra: str = "") -> dict[str, str]:
    """Primera pasada de `loudnorm`: mide para poder clavar el objetivo."""
    cadena = (f"{extra}," if extra else "") + (
        f"loudnorm=I={config.VOZ_LUFS}:TP={config.VOZ_TP}:LRA=7:print_format=json"
    )
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(audio), "-af", cadena, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    medidas: dict[str, str] = {}
    for clave in ("input_i", "input_tp", "input_lra", "input_thresh"):
        m = re.search(rf'"{clave}"\s*:\s*"?(-?[\d.]+)"?', r.stderr)
        if m:
            medidas[clave] = m.group(1)
    return medidas


def _nivelar(
    crudo: Path, destino: Path, *, tempo: float | None = None, on_log: OnLog = _noop,
) -> dict:
    # El recorte de silencios va PRIMERO y forma parte de la cadena, para que la
    # medición de sonoridad y el render final vean el mismo audio ya ajustado.
    # El acelerón va detrás del recorte y delante del resto: así el compresor y
    # el `speechnorm` ven ya el ritmo definitivo, y la duración que se mide al
    # final —la que se apunta como velocidad de la voz— lo incluye.
    factor = config.VOZ_TEMPO if tempo is None else tempo
    acelera = f",atempo={factor}" if factor != 1.0 else ""
    pre = f"{config.VOZ_SILENCIO}{acelera},{config.VOZ_CADENA}"
    med = _medir(crudo, pre)
    norm = f"loudnorm=I={config.VOZ_LUFS}:TP={config.VOZ_TP}:LRA=7"
    if len(med) == 4:
        norm += (
            f":measured_I={med['input_i']}:measured_TP={med['input_tp']}"
            f":measured_LRA={med['input_lra']}:measured_thresh={med['input_thresh']}"
        )
    else:
        on_log("[nicho_pov_bof_largo] ⚠️ no pude medir la sonoridad — se normaliza en una pasada")
    # `level=disabled` es IMPRESCINDIBLE: por defecto `alimiter` RE-NIVELA la
    # salida hacia el límite, así que bajar el límite SUBE el volumen.
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(crudo), "-af",
         f"{pre},{norm},alimiter=limit={config.VOZ_LIMITER}:level=disabled",
         str(destino)],
        check=True, capture_output=True,
    )
    final = _medir(destino)
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(destino)],
        capture_output=True, text=True,
    ).stdout.strip()
    salida = {
        "duracion": float(dur or 0),
        "lufs": float(final.get("input_i", 0) or 0),
        "pico": float(final.get("input_tp", 0) or 0),
    }
    on_log(
        f"[nicho_pov_bof_largo] voz {salida['duracion']:.1f}s · {salida['lufs']:.1f} LUFS · "
        f"pico {salida['pico']:.2f} dBTP"
    )
    return salida
