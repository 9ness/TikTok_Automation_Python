"""Comprobador de sonidos de los carruseles listos (#331, idea 4 de Fable · 10/11/2026).

Por la tarde, antes de la subida nocturna del móvil: abre en el Chrome del VPS (9222, sale por la IP
residencial de España) la página de TikTok del sonido de cada carrusel en verde, completo, con stock y
sin subir. Si TikTok dice «This sound isn't available in your country or region» (o la página no
carga el sonido), le deja elegido un SONIDO DE RESERVA del mismo estilo: uno que ya se usó en un
carrusel subido y que sí está disponible. `subir_carrusel_movil.py` lo lee de
`<SONIDOS_DIR>/reserva_<usuario>.json` y lo usa en vez del del viral, así la subida no se salta
el carrusel por «no encuentro Guardar» / «No veo Usar sonido».

No toca el móvil ni gasta créditos. Solo lee la app (mis_tandas) y abre/cierra UNA pestaña propia.

    MCP_USUARIO=ness python3 scripts/comprobar_sonidos_carruseles.py            # todo lo pendiente
    MCP_USUARIO=ness python3 scripts/comprobar_sonidos_carruseles.py --seco     # no escribe la reserva
    MAX=10 ...                                                                  # solo los 10 primeros
"""

from __future__ import annotations

import collections
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subir_carrusel_movil as scm  # noqa: E402  (mcp(), USUARIO; no toca el móvil al importarse)

DIR = Path(os.environ.get("SONIDOS_DIR", "/mnt/HC_Volume_106974679/agentes/trabajo/sonidos"))
ESTADO = DIR / "estado.json"             # id de sonido → {ok, visto_at, texto}; vale 3 días
RESERVA = DIR / f"reserva_{scm.USUARIO}.json"
VIGENCIA = 3 * 86400
NO_DISPONIBLE = ("isn't available", "isn’t available", "no está disponible", "couldn't find this sound",
                 "no se ha podido encontrar")
SECO = "--seco" in sys.argv
MAX = int(os.environ.get("MAX", "0"))
SIN_RESERVA: list[str] = []   # carruseles sin sonido disponible y sin reserva → «medias» en el panel


def _items(datos: dict):
    for t in datos["tandas"]:
        yield from t.get("items", t.get("carruseles", []))


def _snd(c: dict) -> dict:
    return ((c.get("musica") or {}).get("tiktok") or {})


def _estilo(c: dict) -> str:
    return (((c.get("musica") or {}).get("meta") or {}).get("estilo") or "chill").split("_")[0]


def pendientes(datos: dict) -> list[dict]:
    return [c for c in _items(datos)
            if (c.get("semaforo") or {}).get("color") == "verde" and c.get("completo")
            and not c.get("subido") and not c.get("sin_stock") and _snd(c).get("enlace")]


def candidatos_reserva(datos: dict) -> dict[str, list[dict]]:
    """Por estilo, los sonidos de catálogo (no «original sound») de carruseles ya SUBIDOS, más usados antes."""
    cuenta: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    por_id: dict[str, dict] = {}
    for c in _items(datos):
        s = _snd(c)
        if c.get("subido") and s.get("enlace") and s.get("id") and not s.get("original"):
            cuenta[_estilo(c)][s["id"]] += 1
            cuenta["*"][s["id"]] += 1
            por_id[s["id"]] = {"titulo": s.get("titulo"), "autor": s.get("autor"), "original": False,
                               "id": s["id"], "enlace": s["enlace"]}
    return {e: [por_id[i] for i, _ in n.most_common(8)] for e, n in cuenta.items()}


class Comprobador:
    def __init__(self, pw):
        self.b = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        self.pg = self.b.contexts[0].new_page()
        self.estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}

    def disponible(self, s: dict) -> bool:
        e = self.estado.get(s["id"])
        if e and time.time() - e["visto_at"] < VIGENCIA:
            return e["ok"]
        texto = ""
        for intento in range(2):
            try:
                self.pg.goto(s["enlace"], wait_until="domcontentloaded", timeout=45000)
                self.pg.wait_for_timeout(6000 + 4000 * intento)
                texto = self.pg.evaluate("document.body.innerText") or ""
            except Exception as ex:   # red o Chrome: no se decide nada con una página a medias
                texto = f"ERROR {ex}"
            if any(k in texto for k in NO_DISPONIBLE) or "videos" in texto.lower() or "vídeos" in texto.lower():
                break
        no = any(k in texto for k in NO_DISPONIBLE)
        cargado = no or "videos" in texto.lower() or "vídeos" in texto.lower()
        if not cargado:   # ni «no disponible» ni la lista de vídeos: no se sabe → se deja el del viral
            print(f"  ? {s['id']} sin decidir (la página no cargó)", flush=True)
            return True
        self.estado[s["id"]] = {"ok": not no, "visto_at": int(time.time()), "titulo": s.get("titulo")}
        return not no

    def cerrar(self):
        DIR.mkdir(parents=True, exist_ok=True)
        ESTADO.write_text(json.dumps(self.estado, ensure_ascii=False, indent=1))
        try:
            self.pg.close()
        except Exception:
            pass


def main() -> None:
    from playwright.sync_api import sync_playwright
    datos = scm.mcp("mis_tandas", {"fotos": True})
    lista = pendientes(datos)[: MAX or None]
    reservas_por_estilo = candidatos_reserva(datos)
    reserva = json.loads(RESERVA.read_text()) if RESERVA.exists() else {}
    vivos = {c["id"] for c in lista}
    reserva = {k: v for k, v in reserva.items() if k in vivos}   # lo ya subido o descartado sale solo
    print(f"{len(lista)} carruseles pendientes · {len({_snd(c)['id'] for c in lista})} sonidos distintos", flush=True)
    malos = 0
    with sync_playwright() as pw:
        ch = Comprobador(pw)
        try:
            for c in lista:
                s = _snd(c)
                if ch.disponible(s):
                    reserva.pop(c["id"], None)
                    continue
                malos += 1
                elegido = next((r for r in reservas_por_estilo.get(_estilo(c), []) + reservas_por_estilo.get("*", [])
                                if r["id"] != s["id"] and ch.disponible(r)), None)
                if not elegido:
                    SIN_RESERVA.append(c["id"])
                    print(f"✗ {c['id']} «{s.get('titulo')}» NO disponible y sin reserva", flush=True)
                    continue
                reserva[c["id"]] = {**elegido, "motivo": f"no disponible: {s.get('titulo')} ({s['id']})",
                                    "at": int(time.time())}
                print(f"✗ {c['id']} «{s.get('titulo')}» NO disponible → reserva «{elegido['titulo']}»", flush=True)
        finally:
            ch.cerrar()
    if not SECO:
        DIR.mkdir(parents=True, exist_ok=True)
        RESERVA.write_text(json.dumps(reserva, ensure_ascii=False, indent=1))
    print(f"FIN: {malos} de {len(lista)} sin sonido disponible · {len(reserva)} con reserva"
          f"{' (seco: no escrito)' if SECO else f' en {RESERVA}'}", flush=True)


def _cerrar_panel(inicio: int, res: str, txt: str) -> None:
    """10/11 (Admin): cierra la tarea 46 del panel si sigue pendiente/en curso (solo en el VPS, no en --seco)."""
    md = Path("/home/nebulabsai/rutinas/panel-viva-comprobador-sonidos.md")
    if SECO or not md.exists() or not os.path.exists("/usr/local/bin/rutina-panel-cerrar"):
        return
    import subprocess
    try:
        subprocess.run(["/usr/local/bin/rutina-panel-cerrar", "Comprobador sonidos Viva Shop", str(inicio), res,
                        str(md), txt], timeout=60)
    except Exception:
        pass


if __name__ == "__main__":
    _inicio = int(time.time())
    try:
        main()
    except BaseException as ex:
        _cerrar_panel(_inicio, "mal", f"error: {ex!r}"[:300])
        raise
    _cerrar_panel(_inicio, "medias" if SIN_RESERVA else "bien",
                  f"{len(SIN_RESERVA)} carruseles sin sonido disponible ni reserva" if SIN_RESERVA else "sonidos comprobados")
