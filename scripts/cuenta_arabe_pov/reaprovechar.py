#!/usr/bin/env python3
"""Reaprovechar clips ya en verde de otras cuentas para la cuenta árabe.

Un producto del banco árabe que otra cuenta (ness, nestor2, ana) ya tiene montado y
en VERDE no necesita imágenes de Flow ni clips nuevos: sus clips brutos (sin texto,
sin voz, sin CTA) siguen en la bandeja del agente en el Drive. Con ellos el vídeo
árabe solo pide guion darija, voz, cabecera en árabe y montaje — los pasos de
siempre desde `voz8.py`.

    reaprovechar.py cruce                      # qué sale hoy: tabla + REAPROVECHAR.json
    reaprovechar.py traer --ronda DIR --numero N --fila "largo|…"   # deja los brutos en la ronda

Mismo producto = mismo id de ficha (nunca por parecido del nombre). Solo cuentan
filas en verde. `traer` deja el clip con `aceptado: false`: la regla de la cuenta
(«nunca se usa metraje que no se revisó») sigue valiendo, se revisa la hoja a 2 fps
contra la ficha y entonces se acepta a mano en `CONTROL_CALIDAD.json`.

No genera nada, no gasta créditos y no escribe en el Drive ni en la app.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

TRABAJO = Path(os.getenv("ARABE_TRABAJO", "/mnt/HC_Volume_106974679/navegador/trabajo"))
BANDEJAS = Path(os.getenv(
    "AGENTE_BANDEJA_DIR",
    str(Path.home() / "gdrive/Nebulabs/TikTok/TikTok Shop/_agente"),
))
SUBIDOS = Path(os.getenv(
    "ARABE_CLIPS_SUBIDOS",
    "/mnt/HC_Volume_106974679/api_temp/api_uploads/nicho_pov_bof_largo",
))
USUARIOS = ("ness", "nestor2", "ana")
CONTENEDOR = os.getenv("ARABE_CONTENEDOR_API", "tiktok-api")

# Los enlaces cortos acaban en `/view/product/<id>` o en `shop.tiktok.com/es/pdp/<id>`.
_ID_EN_URL = re.compile(r"/(?:view/product|pdp)/(\d{10,})")

_VOLCADO = r'''
import json
from src.mis_tandas import servicio as s
from src.nicho_pov_bof.repos import product_repo as pr
out = []
_carpetas = {}
def _pid(u, f):
    """Id guardado en la ficha (filas largo sin enlace: Mis Productos, Tareas…)."""
    if f.get("nicho") != "largo" or not f.get("source") or not f.get("carpeta"):
        return ""
    k = (f["source"], f["carpeta"], u)
    if k not in _carpetas:
        try:
            _carpetas[k] = pr.load_folder_para(f["source"], f["carpeta"], u).get("productos") or {}
        except Exception:
            _carpetas[k] = {}
    return str((_carpetas[k].get(str(f.get("producto"))) or {}).get("product_id") or "")
for u in %r:
    sem = s.semaforos(u)
    for f in s.filas(u):
        out.append({
            "product_id": _pid(u, f),
            "usuario": u, "id": f.get("id") or "",
            "color": (sem.get(f.get("id")) or {}).get("color") or "",
            "titulo": f.get("titulo") or "", "product_url": f.get("product_url") or "",
            "video_path": f.get("video_path") or "",
            "video_listo_at": f.get("video_listo_at") or 0,
        })
print(json.dumps(out, ensure_ascii=False))
'''


# ---------------------------------------------------------------------------
# Piezas puras (las que prueba tests/test_arabe_reaprovechar.py)
# ---------------------------------------------------------------------------
def id_en_url(url: str) -> str:
    """El id de ficha que lleva escrito el enlace. Vacío si es un enlace corto."""
    m = _ID_EN_URL.search(url or "")
    return m.group(1) if m else ""


def slug(texto: str, largo: int = 40) -> str:
    """Igual que `src/agente_mcp/archivos.py::slug` (así se llaman las carpetas de la bandeja)."""
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s[:largo].rstrip("_") or "producto"


def partes_fila(fila_id: str) -> dict | None:
    """`largo|fuente|carpeta|producto|modo` → sus partes. Otras filas (pov, mm, rv…): None.

    Solo el POV BOF Largo guarda los brutos en un sitio que se puede deducir de la fila.
    """
    p = (fila_id or "").split("|")
    if len(p) < 4 or p[0] != "largo":
        return None
    return {"fuente": p[1], "carpeta": p[2], "producto": p[3], "modo": p[4] if len(p) > 4 else ""}


def _numero_clip(ruta: Path) -> int:
    m = re.search(r"clip_?(\d+)", ruta.name)
    return int(m.group(1)) if m else 0


def brutos_bandeja(bandejas: Path, usuario: str, carpeta: str, producto: str) -> list[Path]:
    """`_agente/<usuario>/pov_bof_largo/<Carpeta>/<N>_<título>/clip_K.mp4`, en orden."""
    base = bandejas / usuario / "pov_bof_largo" / slug(carpeta.split("__")[-1], 60)
    if not base.is_dir():
        return []
    for d in sorted(base.glob(f"{slug(producto, 12)}_*")):
        clips = sorted(d.glob("clip_*.mp4"), key=_numero_clip)
        if clips:
            return clips
    return []


def brutos_subidos(subidos: Path, fuente: str, carpeta: str, producto: str,
                   listo_at: float) -> list[Path]:
    """Los clips que la web recibió para ese vídeo (`api_uploads`, duran ~2 días).

    Por cada número de clip, la última subida ANTERIOR a que el vídeo quedara listo:
    una subida posterior es de otro montaje y no es la que se revisó.
    """
    if not subidos.is_dir():
        return []
    stub = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{fuente}_{carpeta}_{producto}")
    por_clip: dict[int, tuple[int, Path]] = {}
    for f in subidos.glob(f"{stub}_clip*_*.mp4"):
        m = re.fullmatch(re.escape(stub) + r"_clip(\d+)_(\d+)\.mp4", f.name)
        if not m:
            continue
        k, ts = int(m.group(1)), int(m.group(2))
        if listo_at and ts > listo_at:
            continue
        if k not in por_clip or ts > por_clip[k][0]:
            por_clip[k] = (ts, f)
    return [por_clip[k][1] for k in sorted(por_clip)]


def cruzar(filas: list[dict], banco: dict[str, dict], hechos: dict[str, list[str]],
           ids_cortos: dict[str, str], *, bandejas: Path = BANDEJAS,
           subidos: Path = SUBIDOS) -> list[dict]:
    """Candidatos: una entrada por fila EN VERDE cuyo producto está en el banco árabe."""
    out: list[dict] = []
    for f in filas:
        if f.get("color") != "verde":
            continue
        url = f.get("product_url") or ""
        pid = id_en_url(url) or ids_cortos.get(url, "") or str(f.get("product_id") or "")
        if not pid or pid not in banco:
            continue
        cand = {
            "product_id": pid,
            "producto": banco[pid].get("producto") or "",
            "precio": banco[pid].get("precio"),
            "ya_hecho": hechos.get(pid, []),
            "usuario": f["usuario"], "fila": f["id"], "titulo": f.get("titulo") or "",
            "video": f.get("video_path") or "", "video_listo_at": f.get("video_listo_at") or 0,
            "brutos": [], "origen_brutos": "", "aviso": "",
        }
        p = partes_fila(f["id"])
        if not p:
            cand["aviso"] = "fila sin brutos localizables (no es POV BOF Largo)"
        else:
            listo = float(cand["video_listo_at"] or 0)
            clips = brutos_bandeja(bandejas, f["usuario"], p["carpeta"], p["producto"])
            if clips:
                cand["origen_brutos"] = "bandeja"
                if listo and max(c.stat().st_mtime for c in clips) > listo + 60:
                    cand["aviso"] = ("los clips de la bandeja son POSTERIORES al vídeo en verde: "
                                     "compáralos con el vídeo antes de usarlos")
            else:
                clips = brutos_subidos(subidos, p["fuente"], p["carpeta"], p["producto"], listo)
                cand["origen_brutos"] = "subidos" if clips else ""
            cand["brutos"] = [str(c) for c in clips]
            if not clips:
                cand["aviso"] = "en verde pero sin clips brutos guardados (ni bandeja ni subidos)"
        out.append(cand)
    out.sort(key=lambda c: (not c["brutos"], bool(c["ya_hecho"]), c["product_id"], c["fila"]))
    return out


def resumen(cands: list[dict]) -> dict:
    con = [c for c in cands if c["brutos"]]
    nuevos = {c["product_id"] for c in con if not c["ya_hecho"]}
    return {
        "productos_en_verde": len({c["product_id"] for c in cands}),
        "productos_con_brutos": len({c["product_id"] for c in con}),
        "productos_con_brutos_sin_hacer": len(nuevos),
        "juegos_de_clips": len(con),
    }


# ---------------------------------------------------------------------------
# Lecturas (banco, rondas, app)
# ---------------------------------------------------------------------------
def leer_banco(trabajo: Path = TRABAJO) -> dict[str, dict]:
    """Todos los productos que la cuenta árabe ha apuntado en sus rondas."""
    banco: dict[str, dict] = {}
    for nombre in ("BANCO.json", "PRODUCTOS_POV.json"):
        for f in sorted(trabajo.glob(f"hmizat_ronda*/{nombre}")):
            try:
                datos = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            for x in datos if isinstance(datos, list) else []:
                pid = str((x or {}).get("product_id") or "")
                if pid:
                    banco.setdefault(pid, x)
    return banco


def leer_hechos(trabajo: Path = TRABAJO) -> dict[str, list[str]]:
    """`{product_id: ["hmizat_ronda9:4", …]}` de los PLAN.json: lo que la cuenta ya montó."""
    hechos: dict[str, list[str]] = {}
    for f in sorted(trabajo.glob("hmizat_ronda*/PLAN.json")):
        try:
            datos = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        for r in datos if isinstance(datos, list) else []:
            pid = str((r or {}).get("product_id") or "") if isinstance(r, dict) else ""
            if pid:
                hechos.setdefault(pid, []).append(f"{f.parent.name}:{r.get('numero')}")
    return hechos


def volcar_filas() -> list[dict]:
    """Filas y semáforos de Mis tandas, leídos dentro del contenedor de la API (solo lee)."""
    r = subprocess.run(
        ["docker", "exec", "-i", "-e", "PYTHONPATH=/app", CONTENEDOR, "python", "-"],
        input=_VOLCADO % (USUARIOS,), capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0:
        raise SystemExit(f"no pude leer Mis tandas del contenedor {CONTENEDOR}:\n{r.stderr[-800:]}")
    return json.loads(r.stdout[r.stdout.index("["):])


def resolver_cortos(urls: list[str], cache: Path, pausa: float = 0.4) -> dict[str, str]:
    """Id de cada enlace corto siguiendo su redirect. De uno en uno y con caché: se pide una vez."""
    ids: dict[str, str] = {}
    if cache.exists():
        try:
            ids = json.loads(cache.read_text())
        except ValueError:
            ids = {}
    pend = [u for u in urls if not ids.get(u)]
    if pend:
        import requests

        for u in pend:
            try:
                r = requests.get(u, timeout=15, allow_redirects=True)
                cadena = [h.headers.get("location", "") for h in r.history] + [str(r.url)]
            except Exception:  # noqa: BLE001 - sin id la fila no cruza, nada más
                cadena = []
            ids[u] = next((i for i in map(id_en_url, cadena) if i), "")
            time.sleep(pausa)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(ids, ensure_ascii=False, indent=0))
    return ids


# ---------------------------------------------------------------------------
# Órdenes
# ---------------------------------------------------------------------------
def cmd_cruce(a: argparse.Namespace) -> int:
    salida = Path(a.salida)
    filas = json.loads(Path(a.filas).read_text()) if a.filas else volcar_filas()
    verdes = [f for f in filas if f.get("color") == "verde"]
    cortos = sorted({f["product_url"] for f in verdes
                     if f.get("product_url") and not id_en_url(f["product_url"])})
    ids = resolver_cortos(cortos, salida / "ids_enlaces.json")
    cands = cruzar(filas, leer_banco(), leer_hechos(), ids)
    res = resumen(cands)
    res.update({"filas_en_verde": len(verdes),
                "verdes_sin_id": sum(1 for f in verdes
                                     if not (id_en_url(f.get("product_url") or "")
                                             or ids.get(f.get("product_url") or "")
                                             or f.get("product_id"))),
                "banco": len(leer_banco())})
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "REAPROVECHAR.json").write_text(
        json.dumps({"resumen": res, "candidatos": cands}, ensure_ascii=False, indent=1))
    print(json.dumps(res, ensure_ascii=False))
    for c in cands:
        estado = f"{len(c['brutos'])} clips ({c['origen_brutos']})" if c["brutos"] else "SIN BRUTOS"
        hecho = f" · ya hecho {','.join(c['ya_hecho'])}" if c["ya_hecho"] else ""
        print(f"{c['product_id']} {c['producto'][:38]:38} {c['usuario']:8} {estado:22} {c['fila']}{hecho}")
        if c["aviso"] and c["brutos"]:
            print(f"    ⚠ {c['aviso']}")
    print(f"→ {salida / 'REAPROVECHAR.json'}")
    return 0


def _medidas(clip: Path) -> tuple[int, int, float]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(clip)],
        capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return int(s["width"]), int(s["height"]), float(d["format"]["duration"])


def _hoja_2fps(clip: Path, destino: Path, dur: float) -> None:
    """Todos los fotogramas a 2 fps en una hoja de 8 por fila: lo que se mira antes de aceptar."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    filas = max(1, -(-int(dur * 2 + 0.5) // 8))
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf",
         f"fps=2,scale=270:-2,tile=8x{filas}", "-frames:v", "1", "-q:v", "3", str(destino)],
        check=True)


def _lleva_marca(clip: Path) -> bool | None:
    """¿Lleva la estrella del generador (Flow/Omni)? None si no se puede mirar desde aquí."""
    try:
        raiz = Path(__file__).resolve().parents[2]
        if (raiz / "src").is_dir() and str(raiz) not in sys.path:
            sys.path.insert(0, str(raiz))
        from src.nicho_pov_bof.config import es_clip_omni
    except Exception:  # noqa: BLE001 - copiado a la ronda sin PYTHONPATH del repo
        return None
    return bool(es_clip_omni(str(clip)))


def cmd_traer(a: argparse.Namespace) -> int:
    ronda = Path(a.ronda)
    datos = json.loads(Path(a.cruce).read_text())
    cand = next((c for c in datos["candidatos"] if c["fila"] == a.fila), None)
    if not cand:
        raise SystemExit(f"esa fila no está en {a.cruce}: pasa antes `cruce`")
    if not cand["brutos"]:
        raise SystemExit(f"esa fila no tiene clips brutos: {cand['aviso']}")
    n = int(a.numero)
    f_ctl, f_plan = ronda / "CONTROL_CALIDAD.json", ronda / "PLAN.json"
    ctl = json.loads(f_ctl.read_text()) if f_ctl.exists() else {}
    plan = json.loads(f_plan.read_text()) if f_plan.exists() else []
    if str(n) in ctl and not a.pisar:
        raise SystemExit(f"el número {n} ya tiene clips en CONTROL_CALIDAD.json (usa --pisar)")
    fila_plan = next((r for r in plan if isinstance(r, dict) and r.get("numero") == n), None)
    otro = fila_plan is not None and str(fila_plan.get("product_id")) != cand["product_id"]
    if otro and not a.pisar:
        raise SystemExit(f"el número {n} es de otro producto en PLAN.json (usa --pisar)")
    # solo lo que dejó un `traer` anterior de este número (un juego de 3 clips pisado por uno de 2)
    for viejo in [*ronda.glob(f"brutos/{n:02d}_*_r.mp4"), *ronda.glob(f"revision/{n:02d}_*_bruto.jpg")]:
        viejo.unlink()

    brutos, durs, marcas = [], [], []
    for k, origen in enumerate(cand["brutos"], 1):
        ancho, alto, dur = _medidas(Path(origen))
        if ancho * 16 != alto * 9:
            raise SystemExit(f"{origen}: {ancho}x{alto} no es 9:16, no vale para la cuenta")
        rel = f"brutos/{n:02d}_{k}_r.mp4"
        (ronda / "brutos").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, ronda / rel)
        _hoja_2fps(ronda / rel, ronda / "revision" / f"{n:02d}_{k}_bruto.jpg", dur)
        marcas.append(_lleva_marca(ronda / rel))
        brutos.append(rel)
        # el último cuarto de segundo de un clip generado suele traer el salto de cierre
        durs.append(round(max(dur - 0.3, 1.0), 1))

    ctl[str(n)] = {
        "aceptado": False,
        "modelo": f"Reaprovechado de {cand['usuario']} · {cand['fila']}",
        "brutos": brutos, "inicios": [0] * len(brutos), "duraciones": durs,
        # con la estrella en UN clip, el vídeo entero se encuadra para quitarla (como en la app)
        "omni": any(marcas),
        "fotogramas": 0,
        "detalle": ("PENDIENTE de revisar a 2 fps contra la ficha (hojas en revision/NN_K_bruto.jpg). "
                    "El vídeo de origen está en verde, pero aquí se acepta clip a clip."),
        "reaprovechado": {"usuario": cand["usuario"], "fila": cand["fila"],
                          "video": cand["video"], "origen": cand["brutos"]},
    }
    f_ctl.write_text(json.dumps(ctl, ensure_ascii=False, indent=1))

    if fila_plan is None or otro:
        plan = [r for r in plan if r is not fila_plan]
        nombre = slug(cand["producto"], 28).lower()
        plan.append({
            "numero": n, "producto": nombre, "product_id": cand["product_id"],
            "nombre_enlace": cand["producto"], "precio": cand["precio"],
            "archivo": f"videos/{n:02d}_{nombre}.mp4",
            "bloques": [], "idioma_pantalla": "ar", "voz": True, "caption": "",
            "referencia": f"https://www.tiktok.com/view/product/{cand['product_id']}",
        })
        plan.sort(key=lambda r: r.get("numero", 0))
        f_plan.write_text(json.dumps(plan, ensure_ascii=False, indent=1))

    print(f"{n:02d}: {len(brutos)} clips en {ronda / 'brutos'} · hojas en {ronda / 'revision'}")
    if None in marcas:
        print("  ⚠ no pude mirar si llevan la estrella del generador (ejecuta con PYTHONPATH del "
              "repo): mírala en la hoja y pon `omni: true` si sale")
    elif any(marcas):
        print("  estrella del generador detectada → `omni: true` (el montaje la saca del encuadre)")
    print("Falta: revisar las hojas, aceptar en CONTROL_CALIDAD.json, cabecera y caption en "
          "PLAN.json, guion en audio/guiones.json → voz8 → subs8 → alinear8 → montar10.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="orden", required=True)
    c = sub.add_parser("cruce", help="banco árabe ↔ vídeos en verde de las otras cuentas")
    c.add_argument("--salida", default=str(TRABAJO / "hmizat_reaprovechar"))
    c.add_argument("--filas", help="JSON de filas ya volcado (para no entrar al contenedor)")
    c.set_defaults(fn=cmd_cruce)
    t = sub.add_parser("traer", help="copia los brutos de una fila a la ronda")
    t.add_argument("--ronda", required=True)
    t.add_argument("--numero", required=True, type=int)
    t.add_argument("--fila", required=True)
    t.add_argument("--cruce", default=str(TRABAJO / "hmizat_reaprovechar" / "REAPROVECHAR.json"))
    t.add_argument("--pisar", action="store_true")
    t.set_defaults(fn=cmd_traer)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
