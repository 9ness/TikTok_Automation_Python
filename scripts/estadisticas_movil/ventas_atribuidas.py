#!/usr/bin/env python3
"""Qué producto y qué formato vende en una cuenta de TikTok Shop.

Solo lectura. Las ventas de la Factory son TOTALES POR DÍA (no por producto),
así que la atribución es por exposición: las ventas de un día D se reparten
entre los vídeos subidos en [D-ventana+1, D] con peso decreciente por
antigüedad (peso = decaimiento**edad_en_días). Es una pista, no una prueba.

Uso:  python scripts/estadisticas_movil/ventas_atribuidas.py nestor2 [--json]
          [--ventana 4] [--decaimiento 0.6] [--sin-informe]
Lógica pura: atribuir() / ranking() / recomendar(). Lectura: leer_fuentes().
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Madrid")
except Exception:  # pragma: no cover
    TZ = None

OUT_DIR = Path("/mnt/HC_Volume_106974679/agentes/trabajo/ana_nestor2")

_CODIGO = r"""
import json
from src.estadisticas import repo
from src.mis_tandas import servicio
t = servicio.tandas(%r, todas=True)
items = [i for x in t['tandas'] for i in x['items']]
print('@@JSON@@' + json.dumps({'ventas': repo.leer(%r), 'items': items}, ensure_ascii=False, default=str))
"""


# ---------------------------------------------------------------- lectura
def leer_fuentes(usuario: str) -> tuple[dict, list[dict]]:
    cmd = ["docker", "exec", "-w", "/app", "-e", "PYTHONPATH=/app", "tiktok-api",
           "python", "-c", _CODIGO % (usuario, usuario)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    linea = [l for l in r.stdout.splitlines() if l.startswith("@@JSON@@")][-1]
    d = json.loads(linea[len("@@JSON@@"):])
    return d["ventas"], d["items"]


# ---------------------------------------------------------------- lógica pura
def fecha_subida(ts, tz=TZ) -> str | None:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz).strftime("%Y-%m-%d")
    except Exception:
        return None


def videos_subidos(items: list[dict]) -> list[dict]:
    """Normaliza los items subidos: producto, formato y día."""
    out = []
    for i in items:
        if not i.get("uploaded"):
            continue
        dia = fecha_subida(i.get("uploaded_at"))
        if not dia:
            continue
        titulo = (i.get("titulo") or i.get("producto") or "?").strip()
        modo = i.get("modo") or i.get("formato") or ""
        formato = f"{i.get('nicho') or '?'}/{modo}" if modo else str(i.get("nicho") or "?")
        epoca = i.get("epoca") or "neutro"
        out.append({"id": i.get("id"), "producto": titulo[:70], "formato": formato,
                    "epoca": epoca, "dia": dia,
                    "semaforo": (i.get("semaforo") or {}).get("color") if isinstance(i.get("semaforo"), dict) else None})
    return out


def _d(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()


def atribuir(videos: list[dict], dias: list[dict], ventana: int = 4,
             decaimiento: float = 0.6) -> tuple[list[dict], dict]:
    """Devuelve (videos con ventas/gmv atribuidos, resumen con lo no atribuido)."""
    for v in videos:
        v["ventas"] = 0.0
        v["gmv"] = 0.0
    sin_atribuir = {"ventas": 0, "gmv": 0.0, "dias": []}
    for dia in dias:
        ventas = float(dia.get("ventas") or 0)
        gmv = float(dia.get("gmv") or 0)
        if ventas <= 0 and gmv <= 0:
            continue
        f = _d(dia["fecha"])
        cand = []
        for v in videos:
            edad = (f - _d(v["dia"])).days
            if 0 <= edad < ventana:
                cand.append((v, decaimiento ** edad))
        tot = sum(w for _, w in cand)
        if not tot:
            sin_atribuir["ventas"] += ventas
            sin_atribuir["gmv"] += gmv
            sin_atribuir["dias"].append(dia["fecha"])
            continue
        for v, w in cand:
            v["ventas"] += ventas * w / tot
            v["gmv"] += gmv * w / tot
    return videos, sin_atribuir


def ranking(videos: list[dict], clave: str) -> list[dict]:
    g: dict = defaultdict(lambda: {"videos": 0, "dias": set(), "ventas": 0.0, "gmv": 0.0})
    for v in videos:
        x = g[v[clave]]
        x["videos"] += 1
        x["dias"].add(v["dia"])
        x["ventas"] += v["ventas"]
        x["gmv"] += v["gmv"]
    filas = []
    for k, x in g.items():
        filas.append({"clave": k, "videos": x["videos"], "dias": len(x["dias"]),
                      "ventas": round(x["ventas"], 2), "gmv": round(x["gmv"], 2),
                      "ventas_por_video": round(x["ventas"] / x["videos"], 3)})
    filas.sort(key=lambda r: (-r["ventas_por_video"], -r["ventas"], -r["videos"]))
    return filas


def recomendar(filas: list[dict], min_videos: int = 4) -> list[dict]:
    """Marca cada fila: producir más / dejar / pocos datos."""
    tot_v = sum(f["videos"] for f in filas)
    media = (sum(f["ventas"] for f in filas) / tot_v) if tot_v else 0
    for f in filas:
        if f["videos"] < min_videos:
            f["veredicto"] = "producir más" if f["ventas"] > 0 and f["ventas_por_video"] >= media else "pocos datos"
        elif f["ventas_por_video"] >= media * 1.2 and f["ventas"] > 0:
            f["veredicto"] = "producir más"
        elif f["ventas"] == 0 or f["ventas_por_video"] < media * 0.5:
            f["veredicto"] = "dejar"
        else:
            f["veredicto"] = "mantener"
    return filas


def analizar(ventas: dict, items: list[dict], ventana: int = 4, decaimiento: float = 0.6) -> dict:
    vids = videos_subidos(items)
    dias = ventas.get("dias") or []
    vids, sin = atribuir(vids, dias, ventana, decaimiento)
    return {
        "videos_subidos": len(vids),
        "ventas_total": sum(float(d.get("ventas") or 0) for d in dias),
        "gmv_total": round(sum(float(d.get("gmv") or 0) for d in dias), 2),
        "sin_atribuir": {"ventas": sin["ventas"], "gmv": round(sin["gmv"], 2), "dias": sin["dias"]},
        "por_producto": recomendar(ranking(vids, "producto")),
        "por_formato": recomendar(ranking(vids, "formato")),
        "por_epoca": recomendar(ranking(vids, "epoca")),
        "ventana_dias": ventana, "decaimiento": decaimiento,
    }


# ---------------------------------------------------------------- salida
def _tabla(titulo: str, filas: list[dict], top: int | None = None) -> str:
    l = [f"### {titulo}", "", "| clave | vídeos | días | ventas~ | GMV~ | v/vídeo | veredicto |",
         "|---|--:|--:|--:|--:|--:|---|"]
    for f in filas[:top]:
        l.append(f"| {f['clave']} | {f['videos']} | {f['dias']} | {f['ventas']:.1f} | "
                 f"{f['gmv']:.0f} | {f['ventas_por_video']:.2f} | {f['veredicto']} |")
    return "\n".join(l)


def informe(usuario: str, r: dict, top_prod: int = 25) -> str:
    sa = r["sin_atribuir"]
    p = [f"# Qué vende en {usuario}", "",
         f"Vídeos subidos: {r['videos_subidos']} · ventas del panel: {r['ventas_total']:.0f} · GMV {r['gmv_total']:.0f}. "
         f"Atribución por exposición (ventana {r['ventana_dias']} d, decaimiento {r['decaimiento']}); "
         f"sin atribuir: {sa['ventas']:.0f} ventas / {sa['gmv']:.0f} GMV (días {', '.join(sa['dias']) or '-'}). "
         "Las ventas son por día, no por producto: es una pista, no una prueba.", "",
         _tabla("Por formato", r["por_formato"]), "", _tabla("Por época", r["por_epoca"]), "",
         _tabla(f"Por producto (top {top_prod})", r["por_producto"], top_prod), ""]
    mas = [f["clave"] for f in r["por_formato"] + r["por_producto"] if f["veredicto"] == "producir más"]
    dej = [f["clave"] for f in r["por_formato"] + r["por_producto"] if f["veredicto"] == "dejar"]
    p += ["### Producir más"] + ([f"- {x}" for x in mas] or ["- (nada claro)"]) + [""]
    p += ["### Dejar"] + ([f"- {x}" for x in dej] or ["- (nada)"]) + [""]
    return "\n".join(p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("usuario")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ventana", type=int, default=4)
    ap.add_argument("--decaimiento", type=float, default=0.6)
    ap.add_argument("--sin-informe", action="store_true")
    a = ap.parse_args(argv)
    ventas, items = leer_fuentes(a.usuario)
    r = analizar(ventas, items, a.ventana, a.decaimiento)
    txt = informe(a.usuario, r)
    if not a.sin_informe:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / f"que_vende_{a.usuario}.md").write_text(txt, encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
