"""Mantener el catálogo común de flechas y subtítulos (src/catalogo_edicion).

    python scripts/catalogo_edicion.py pendientes
        Ficheros de Assets/flechas/ que NO están en el catálogo (no se ofrecen).
    python scripts/catalogo_edicion.py aprobar flecha_x.mov --grupo simple --color roja [--nombre Roja] [--tiktok-shop]
    python scripts/catalogo_edicion.py ocultar flecha_x.mov          (deja de ofrecerse en el Editor Auto)
    python scripts/catalogo_edicion.py navidad --salida DIR [--segundos 6]
        Renderiza las animaciones de Navidad del POV BOF (regalo.py) como .mov
        con transparencia en DIR y las apunta en el catálogo con su colocación.
        Luego se copian a Assets/flechas/ del Drive.
    python scripts/catalogo_edicion.py web --repo ~/proyectos/nebulabs-media [--flechas DIR]
        Exporta a la web lo aprobado para el Editor Auto: lib/catalogo-edicion.json
        + vistas previas WebP animadas en public/arrows/ (solo las que falten).

Lo nuevo nunca entra solo: aprobar es la revisión a mano.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.catalogo_edicion import cargar, guardar  # noqa: E402

COLORES = {
    "amarilla": "Amarilla", "azul": "Azul", "beige": "Beige", "blanca": "Blanca",
    "burdeos": "Burdeos", "cyan": "Cyan", "marron": "Marrón", "morada": "Morada",
    "naranja": "Naranja", "negra": "Negra", "roja": "Roja", "rosa": "Rosa", "verde": "Verde",
}


def _carpeta_flechas() -> str:
    from src.editor_auto.config import arrows_folder
    return arrows_folder()


def cmd_pendientes(_a) -> None:
    cat = {f["fichero"] for f in cargar()["flechas"]}
    try:
        en_disco = sorted(os.listdir(_carpeta_flechas()))
    except OSError as e:
        sys.exit(f"No puedo leer Assets/flechas: {e}")
    fuera = [f for f in en_disco if f not in cat]
    print("\n".join(fuera) if fuera else "Nada pendiente.")


def cmd_aprobar(a) -> None:
    cat = cargar()
    f = next((x for x in cat["flechas"] if x["fichero"] == a.fichero), None)
    if f is None:
        if not a.grupo or not a.color:
            sys.exit("Flecha nueva: indica --grupo y --color.")
        f = {"fichero": a.fichero, "nombre": a.nombre or COLORES.get(a.color, a.color.title()),
             "grupo": a.grupo, "color": a.color, "animacion": "bucle",
             "editor_auto": True, "tiktok_shop": bool(a.tiktok_shop), "inteligente": True}
        cat["flechas"].append(f)
    else:
        f["editor_auto"] = True
        if a.tiktok_shop:
            f["tiktok_shop"] = True
    guardar(cat)
    print(f"Aprobada: {f}")


def cmd_ocultar(a) -> None:
    cat = cargar()
    for f in cat["flechas"]:
        if f["fichero"] == a.fichero:
            f["editor_auto"] = False
            guardar(cat)
            print(f"Oculta en el Editor Auto: {a.fichero}")
            return
    sys.exit("No está en el catálogo.")


# ---------------------------------------------------------------------------
# Navidad: las animaciones de cierre del acabado «regalo» como .mov
# ---------------------------------------------------------------------------
def _render_navidad(anim: str, paleta: dict, destino: Path, segundos_quieta: float) -> dict:
    from src.nicho_pov_bof.pipeline import regalo as R

    variante = {"anim": anim, "paleta": paleta}
    semilla = f"catalogo|{anim}|{paleta['nombre']}"
    an = R._Animador(variante, semilla)
    n = int(math.ceil((an.fin_movimiento + segundos_quieta) * R.FPS))
    ciclo = int(round(2 * math.pi / 7 * R.FPS))
    cache: dict[int, object] = {}

    def frame(i: int):
        t = i / R.FPS
        if t >= an.fin_movimiento:
            k = int(round((t - an.fin_movimiento) * R.FPS)) % ciclo
            if k not in cache:
                cache[k] = an.fotograma(t)
            return cache[k]
        return an.fotograma(t)

    # 1ª pasada: caja que contiene TODA la animación (para recortar el lienzo).
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    for i in range(n):
        bb = frame(i).getchannel("A").getbbox()
        if bb:
            x0, y0 = min(x0, bb[0]), min(y0, bb[1])
            x1, y1 = max(x1, bb[2]), max(y1, bb[3])
    # Pares (ProRes/yuv) y un margen de 4 px.
    x0, y0 = max(0, x0 - 4) & ~1, max(0, y0 - 4) & ~1
    x1, y1 = min(R.W, x1 + 4), min(R.REG_H, y1 + 4)
    w, h = (x1 - x0) & ~1, (y1 - y0) & ~1

    nombre = f"navidad_{anim}_{paleta['nombre']}.mov"
    out = destino / nombre
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
           "-s", f"{w}x{h}", "-r", str(R.FPS), "-i", "pipe:0",
           # RLE de QuickTime: con tanto transparente pesa una fracción de ProRes.
           "-c:v", "qtrle", "-pix_fmt", "argb", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(frame(i).crop((x0, y0, x0 + w, y0 + h)).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg falló con {nombre}")

    # Colocación por defecto = donde la pinta el POV BOF (flecha al carrito).
    return {
        "fichero": nombre,
        "colocacion": {
            "x": round((x0 + w / 2) / R.W * 100, 1),
            "y": round((R.REG_Y0 + y0 + h / 2) / R.H * 100, 1),
            "ancho": round(w / R.W * 100, 1),
        },
    }


NOMBRES_ANIM = {"caja_flecha": "Caja", "lluvia": "Nieve", "lazo": "Lazo"}
NOMBRES_PALETA = {"rojo_oro": "roja y oro", "verde_oro": "verde y oro", "blanco_rojo": "blanca y roja",
                  "azul_plata": "azul y plata", "burdeos_oro": "burdeos y oro"}


def cmd_navidad(a) -> None:
    from src.nicho_pov_bof.pipeline import regalo as R

    destino = Path(a.salida)
    destino.mkdir(parents=True, exist_ok=True)
    cat = cargar()
    por_fichero = {f["fichero"]: f for f in cat["flechas"]}
    for anim in R.ANIMACIONES:
        for pal in R.PALETAS:
            r = _render_navidad(anim, pal, destino, a.segundos)
            f = por_fichero.get(r["fichero"]) or {}
            f.update({
                "fichero": r["fichero"],
                "nombre": f"{NOMBRES_ANIM.get(anim, anim)} {NOMBRES_PALETA.get(pal['nombre'], pal['nombre'])}",
                "grupo": "navidad", "color": pal["nombre"], "animacion": "entrada",
                "editor_auto": f.get("editor_auto", True), "tiktok_shop": False,
                "inteligente": False, "colocacion": r["colocacion"],
            })
            if r["fichero"] not in por_fichero:
                cat["flechas"].append(f)
                por_fichero[r["fichero"]] = f
            print(f"{r['fichero']}  {r['colocacion']}")
    guardar(cat)


# ---------------------------------------------------------------------------
# Exportar a la web de Nebulabs Media
# ---------------------------------------------------------------------------
def _preview_webp(src: Path, dst: Path, entrada: bool) -> None:
    # Vista previa ligera: 160 px de ancho, 15 fps. Las de entrada en bucle
    # también (la web enseña cómo se mueve; el vídeo la reproduce una vez).
    vf = "fps=15,scale=160:-2:flags=lanczos,format=rgba"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", vf,
                    "-c:v", "libwebp_anim", "-lossless", "0", "-quality", "70",
                    "-loop", "0", str(dst)], check=True)


def cmd_web(a) -> None:
    repo = Path(a.repo).expanduser()
    if not (repo / "lib").is_dir():
        sys.exit(f"{repo} no parece el repo de nebulabs-media")
    carpeta = Path(a.flechas or _carpeta_flechas())
    cat = cargar()
    pub = repo / "public" / "arrows"
    pub.mkdir(parents=True, exist_ok=True)
    flechas = []
    for f in cat["flechas"]:
        if not f.get("editor_auto"):
            continue
        img = pub / (Path(f["fichero"]).stem + ".webp")
        if not img.exists():
            src = carpeta / f["fichero"]
            if not src.exists():
                print(f"  ⚠️ sin fichero, no se exporta: {f['fichero']}")
                continue
            _preview_webp(src, img, f.get("animacion") == "entrada")
            print(f"  + vista previa {img.name}")
        e = {"id": f["fichero"], "name": f["nombre"], "group": f["grupo"],
             "img": f"/arrows/{img.name}", "intro": f.get("animacion") == "entrada"}
        if f.get("colocacion"):
            e["placement"] = f["colocacion"]
        flechas.append(e)
    grupos_usados = {f["group"] for f in flechas}
    out = {
        "_leeme": "GENERADO por scripts/catalogo_edicion.py web (repo TikTok_Automation_Python). No editar a mano.",
        "arrowGroups": [{"id": g["id"], "name": g["nombre"]} for g in cat["grupos_flecha"] if g["id"] in grupos_usados],
        "arrows": flechas,
        "subPresets": [
            {"id": s["id"], "name": s["nombre"], "fontId": s["fuente"], "defaultMode": s["modo"],
             "css": s["web"]["css"], **({"activeCss": s["web"]["activo"]} if s["web"].get("activo") else {})}
            for s in cat["subtitulos"] if s.get("editor_auto")
        ],
    }
    (repo / "lib" / "catalogo-edicion.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Exportadas {len(flechas)} flechas y {len(out['subPresets'])} estilos a {repo}/lib/catalogo-edicion.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pendientes").set_defaults(fn=cmd_pendientes)
    p = sub.add_parser("aprobar")
    p.add_argument("fichero")
    p.add_argument("--grupo")
    p.add_argument("--color")
    p.add_argument("--nombre")
    p.add_argument("--tiktok-shop", action="store_true")
    p.set_defaults(fn=cmd_aprobar)
    p = sub.add_parser("ocultar")
    p.add_argument("fichero")
    p.set_defaults(fn=cmd_ocultar)
    p = sub.add_parser("navidad")
    p.add_argument("--salida", required=True)
    p.add_argument("--segundos", type=float, default=6.0, help="segundos de flecha rebotando tras la animación")
    p.set_defaults(fn=cmd_navidad)
    p = sub.add_parser("web")
    p.add_argument("--repo", required=True)
    p.add_argument("--flechas", help="carpeta con los .mov (por defecto Assets/flechas)")
    p.set_defaults(fn=cmd_web)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
