"""De qué producto es cada vídeo que sube el operador.

El vídeo se genera FUERA (Magnific, Veo3, Kling) a partir de la foto limpia del
producto, así que al volver son diez ficheros con nombres que no dicen nada y
hay que ir subiéndolos de uno en uno a su ficha. Esto los reparte solos: saca
unos fotogramas de cada vídeo y le pregunta a Gemini cuál del catálogo es.

Lo que hace que funcione, medido con un vídeo real del operador (un carro de
jardín, en una carpeta donde había otros DOS carritos parecidos):

- **Se pregunta por todos los vídeos a la vez**, no uno por uno, y se le pide un
  reparto SIN REPETIR. Dos vídeos no pueden ser del mismo producto, y saberlo
  descarta la mayoría de las confusiones entre productos gemelos.
- **Varios fotogramas por vídeo.** En el primero la mano suele tapar medio
  producto.
- **El operador elige antes a qué productos sube**, así que el catálogo a
  comparar son cinco cosas y no treinta.

Nunca decide solo: devuelve la propuesta y la ficha la enseña para confirmar.
Una asignación equivocada se ve de un vistazo (miniatura del vídeo al lado de
la foto) y se corrige con un toque; colarla en el montaje sería mucho peor.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

OnLog = Callable[[str], None]
_noop: OnLog = lambda _m: None

# Fotogramas por vídeo. Tres bastan: el producto sale en plano casi todo el
# rato y cada uno que se añade encarece la llamada.
FOTOGRAMAS = 3
ANCHO = 540


def _fotogramas(video: Path, destino: Path, etiqueta: str) -> list[str]:
    try:
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, check=True,
        ).stdout.strip())
    except Exception:
        dur = 10.0
    salidas = []
    for i in range(FOTOGRAMAS):
        # Ni el primer instante ni el último: ahí la mano entra o sale y el
        # producto se ve a medias.
        t = dur * (i + 1) / (FOTOGRAMAS + 1)
        f = destino / f"{etiqueta}_{i}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", "-vf", f"scale={ANCHO}:-1", str(f)],
            capture_output=True,
        )
        if f.is_file() and f.stat().st_size > 0:
            salidas.append(str(f))
    return salidas


def _letras(productos: list[str]) -> dict[str, str]:
    """Una letra por producto para el prompt: A, B, C…

    Los productos se llaman 1, 2, 3… y las imágenes van numeradas, así que al
    pedirle "el número del producto" contestaba con el NÚMERO DE IMAGEN: dijo
    "Producto 12" para un catálogo que llegaba al 8, habiendo reconocido bien
    el producto. Con letras no hay dos numeraciones que confundir.
    """
    abecedario = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return {p: (abecedario[i] if i < len(abecedario) else f"P{i}") for i, p in enumerate(productos)}


def _prompt(
    n_videos: int, fotos_por_video: list[int], productos: list[str],
    dobles: set[str] | None = None,
) -> str:
    bloques = []
    i = 1
    for v, cuantos in enumerate(fotos_por_video, start=1):
        bloques.append(f"- Vídeo {v}: las siguientes {cuantos} imágenes")
        i += cuantos
    dobles = dobles or set()
    letra = _letras(productos)
    catalogo = "\n".join(
        f"- Producto {letra[p]}"
        + (" (DE DOS CLIPS: puede salir en dos vídeos)" if p in dobles else "")
        for p in productos
    )
    return (
        f"Te paso {i - 1 + len(productos)} imágenes en orden: primero los "
        f"fotogramas de los vídeos y después el catálogo.\n\n"
        f"FOTOGRAMAS DE {n_videos} VÍDEO(S):\n" + "\n".join(bloques) + "\n\n"
        f"CATÁLOGO DE PRODUCTOS:\n{catalogo}\n\n"
        "Cada vídeo se generó a partir de la foto de UNO de esos productos. "
        "Dime de cuál es cada vídeo.\n\n"
        "Reglas:\n"
        + (
            "- Cada producto sale en UN solo vídeo, salvo los marcados como DE "
            "DOS CLIPS, que salen en DOS.\n"
            "- Esos dos clips son DOS PLANOS DEL MISMO PRODUCTO y pueden verse "
            "muy distintos entre sí: otro ángulo, más cerca, otra luz, otra "
            "habitación, la mano tapando una parte. Que no se parezcan ENTRE "
            "ELLOS no significa que sean productos distintos; compara cada uno "
            "con el catálogo por separado.\n"
            if dobles else
            "- Un producto no puede repetirse en dos vídeos: reparte.\n"
        )
        + "- Puede haber productos parecidos (varios carritos, varios colchones). "
        "Fíjate en la forma exacta, el color, el material, las ruedas, el "
        "número de plazas y los detalles, no en el tipo genérico.\n"
        "- MUY IMPORTANTE: puede que el producto del vídeo NO esté en el "
        "catálogo. No es una lista donde haya que elegir por fuerza. Si el del "
        "vídeo no es NINGUNO de los de arriba —aunque se le parezca en tipo, "
        "color o estilo—, deja su producto en \"\". Un vídeo mal asignado "
        "estropea el montaje; decir que no está no cuesta nada.\n"
        "- Antes de dar un id, comprueba que coinciden los DETALLES concretos "
        "(mismo estampado, mismas etiquetas, mismo remate lateral), no solo "
        "que sean el mismo tipo de producto.\n\n"
        'Responde SOLO con la LETRA del producto: {"videos": [{"video": 1, '
        '"producto": "<letra> o vacío", "por_que": "6 palabras"}, ...]}'
    )


def _id_de(valor: object, ids: list[str]) -> str:
    """Saca el id del producto de lo que conteste el modelo.

    Se le pide el id a secas y contesta "Producto 2" la mitad de las veces.
    Rechazarlo por eso dejaba sin asignar un vídeo que había reconocido bien.
    Se acepta el id exacto o el que aparezca como palabra suelta dentro del
    texto; lo que no se hace nunca es adivinar (un "2" dentro de "12" no vale).
    """
    txt = str(valor or "").strip()
    if not txt:
        return ""
    if txt in ids:
        return txt
    piezas = re.split(r"[^0-9A-Za-z_]+", txt)
    for pid in sorted(ids, key=len, reverse=True):
        if pid in piezas:
            return pid
    return ""


def emparejar(
    source: str,
    folder: str,
    videos: list[Path],
    productos: list[str],
    *,
    dobles: set[str] | None = None,
    on_log: OnLog = _noop,
) -> list[dict]:
    """`[{video: <índice 0..n>, producto, por_que}]`, uno por vídeo.

    `dobles` son los productos que llevan DOS clips (los de plazos, y todos en
    el POV BOF Largo): esos pueden llevarse dos vídeos y el resto solo uno.

    `productos` son los candidatos. Si algo falla
    se devuelve la lista con `producto` vacío: la ficha la enseñará sin asignar
    y él la rellena, que es mejor que no poder subir nada.
    """
    from src.nicho_pov_bof.services import drive_client, photo_pairing
    from src.tiktok_shop.api.gemini import generate_json

    vacio = [{"video": i, "producto": "", "por_que": ""} for i in range(len(videos))]
    if not videos or not productos:
        return vacio

    trabajo = Path(tempfile.mkdtemp(prefix="emparejar_"))
    try:
        imagenes: list[str] = []
        por_video: list[int] = []
        for i, v in enumerate(videos):
            fr = _fotogramas(Path(v), trabajo, f"v{i}")
            if not fr:
                on_log(f"[emparejador] sin fotogramas del vídeo {i + 1}")
            por_video.append(len(fr))
            imagenes += fr
        if not imagenes:
            return vacio

        fotos = [
            drive_client.probe_dimensions(f)
            for f in drive_client.list_photos(source, folder)
        ]
        pares = {str(p["producto"]): p for p in photo_pairing.pair_folder(fotos)}
        from src.nicho_pov_bof.services import thumbs

        catalogo, ids = [], []
        for pid in productos:
            limpia = (pares.get(str(pid), {}).get("clean") or {}).get("id")
            if not limpia:
                continue
            foto = drive_client.fetch_photo(limpia, suffix=".jpg")
            # Encogidas: las del Drive vienen a 1-2 MB y diez a tamaño completo
            # hacían que Gemini devolviera 504. Al ancho del vídeo se distinguen
            # igual de bien (probado).
            catalogo.append(str(thumbs.miniatura(foto, ANCHO)))
            ids.append(str(pid))
        if not catalogo:
            on_log("[emparejador] ninguno de los productos elegidos tiene foto limpia")
            return vacio

        dobles = {str(d) for d in (dobles or set())} & set(ids)
        letra = _letras(ids)
        por_letra = {v: k for k, v in letra.items()}
        datos = generate_json(
            _prompt(len(videos), por_video, ids, dobles), "",
            images=imagenes + catalogo,
        )
        salida = {i: {"video": i, "producto": "", "por_que": ""} for i in range(len(videos))}
        # Cuántos vídeos admite cada producto: dos si lleva dos clips, uno el
        # resto. Sin este tope, un producto se quedaba con media carpeta.
        cupo = {pid: (2 if pid in dobles else 1) for pid in ids}
        for fila in (datos or {}).get("videos") or []:
            try:
                idx = int(fila.get("video", 0)) - 1
            except (TypeError, ValueError):
                continue
            # Contesta la letra; se traduce al id real. Se acepta también el
            # id a secas por si algún día contesta con él.
            bruto = str(fila.get("producto") or "").strip()
            pid = por_letra.get(bruto.upper(), "") or _id_de(bruto, ids)
            # Se ignora lo que no cuadre: un id inventado, uno fuera de los
            # elegidos o un producto repetido. Vale más dejarlo sin asignar que
            # meter el vídeo del colchón en el sofá.
            if idx not in salida or pid not in ids or cupo.get(pid, 0) <= 0:
                continue
            cupo[pid] -= 1
            salida[idx] = {
                "video": idx, "producto": pid,
                "por_que": str(fila.get("por_que") or "")[:80],
            }
        # Segunda pasada para los que se hayan quedado sueltos. El modelo no
        # es determinista: con los MISMOS vídeos a veces reconoce los tres y a
        # veces dos. Aquí se le vuelve a preguntar solo por los que faltan y
        # solo contra los productos que aún admiten otro vídeo, que es un
        # problema mucho más pequeño que el original.
        sueltos = [i for i, x in salida.items() if not x["producto"]]
        quedan = [pid for pid in ids if cupo.get(pid, 0) > 0]
        if sueltos and quedan and len(quedan) < len(ids):
            on_log(f"[emparejador] segunda pasada para {len(sueltos)} vídeo(s)")
            sub_imgs, sub_por_video = [], []
            for i in sueltos:
                desde = sum(por_video[:i])
                sub_imgs += imagenes[desde:desde + por_video[i]]
                sub_por_video.append(por_video[i])
            sub_cat = [catalogo[ids.index(pid)] for pid in quedan]
            sub_letra = _letras(quedan)
            sub_por_letra = {v: k for k, v in sub_letra.items()}
            datos2 = generate_json(
                _prompt(len(sueltos), sub_por_video, quedan, dobles & set(quedan)),
                "", images=sub_imgs + sub_cat,
            )
            for fila in (datos2 or {}).get("videos") or []:
                try:
                    n = int(fila.get("video", 0)) - 1
                except (TypeError, ValueError):
                    continue
                if not 0 <= n < len(sueltos):
                    continue
                bruto = str(fila.get("producto") or "").strip()
                pid = sub_por_letra.get(bruto.upper(), "") or _id_de(bruto, quedan)
                if not pid or cupo.get(pid, 0) <= 0:
                    continue
                cupo[pid] -= 1
                salida[sueltos[n]] = {
                    "video": sueltos[n], "producto": pid,
                    "por_que": str(fila.get("por_que") or "")[:80],
                }

        hechos = sum(1 for x in salida.values() if x["producto"])
        on_log(f"[emparejador] {hechos}/{len(videos)} vídeos reconocidos")
        return [salida[i] for i in range(len(videos))]
    except Exception as e:  # noqa: BLE001
        on_log(f"[emparejador] no se pudo emparejar ({e}); se subirán sin asignar")
        return vacio
    finally:
        import shutil

        shutil.rmtree(trabajo, ignore_errors=True)
