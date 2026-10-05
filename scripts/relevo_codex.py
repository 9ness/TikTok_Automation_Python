#!/usr/bin/env python3
"""Aviso (y relevo SOLO si Néstor lo elige) cuando un agente de vídeo se queda sin cuota.

    relevo_codex.py vigilar        → (timer, cada 2 min) busca agentes parados y AVISA
    relevo_codex.py lanzar <sesion> <motor>   → lo llama el bot al pulsar el botón
    relevo_codex.py estado         → relevos en marcha

Y de vuelta: cuando pasa la hora a la que vuelve la cuota de Claude, el relevo
ha parado y el agente sigue parado, avisa UNA vez de que ya se le puede decir
«sigue» (una sesión de Claude no se reanuda desde aquí: se pisaría con la
que está abierta).

Nada arranca solo: `vigilar` solo detecta y manda por Telegram (bot de Néstor)
un mensaje con botones — un respaldo por cada uno instalado (hoy Codex) y
«Esperar». El bot (`~/asistentes-telegram/bot.py › on_relevo`) llama a `lanzar`
cuando se pulsa.

Cómo se detecta, sin configuración:
- PARADO POR CUOTA = la última entrada de su transcripción es el mensaje
  sintético de límite (`"error": "rate_limit"`) de hace < `VENTANA_MIN`.
- Su RELEVO.md es el último que escribió: `…/_agente/<usuario>/<menú>/RELEVO.md`
  (guía `src/agente_mcp/guias/README.md › 8`). Sin RELEVO.md se avisa igual,
  pero sin botón de relevo.

Claude y Codex nunca a la vez: el relevo trabaja con `RELEVO.lock` (con su pid)
y los agentes lo miran antes de seguir. El MCP de la app se le pasa con
`-c mcp_servers.app.url=…` (URL del usuario en `MCP_URLS.local.md`, que no sale
de aquí).
"""
from __future__ import annotations

import calendar
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path("/home/nebulabsai")
REPO = HOME / "proyectos" / "TikTok_Automation_Python"
TRANSCRIPCIONES = HOME / ".claude" / "projects" / "-home-nebulabsai-proyectos-TikTok-Automation-Python"
BOTS = HOME / "asistentes-telegram"
DATOS = HOME / ".relevo_codex"
CODEX = str(HOME / ".local" / "bin" / "codex")
VENTANA_MIN = 45
RECIENTES_H = 8
RELEVO_RE = re.compile(r"(/[^\"'\s\\]*?/_agente/([^/\"'\s\\]+)/[^\"'\s\\]*?RELEVO\.md)")

MOTORES = {"codex": "Codex (ChatGPT)"}   # OpenCode: añadir aquí y en `_comando`


# ----------------------------------------------------------------- utilidades
def _estado() -> dict:
    try:
        return json.loads((DATOS / "estado.json").read_text())
    except (OSError, ValueError):
        return {"avisados": {}, "pendientes": {}}


def _guardar(e: dict) -> None:
    DATOS.mkdir(parents=True, exist_ok=True)
    (DATOS / "estado.json").write_text(json.dumps(e, indent=1, ensure_ascii=False))


def telegram(texto: str, botones: list[list[dict]] | None = None) -> None:
    env = dict(l.split("=", 1) for l in (BOTS / ".env").read_text().split() if "=" in l)
    cfg = json.loads((BOTS / "personas.json").read_text())["nestor"]
    cuerpo = {"chat_id": cfg["permitidos"][0], "text": texto}
    if botones:
        cuerpo["reply_markup"] = {"inline_keyboard": botones}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{env[cfg['token_env']]}/sendMessage",
        data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30)


def lock_activo(relevo: Path) -> int | None:
    try:
        pid = int(relevo.with_name("RELEVO.lock").read_text().split()[1])
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError, IndexError):
        return None


def _ultima_entrada(jsonl: Path) -> dict | None:
    with jsonl.open("rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 400_000))
        lineas = f.read().decode(errors="replace").splitlines()
    for linea in reversed(lineas):
        try:
            ev = json.loads(linea)
        except ValueError:
            continue
        if ev.get("type") in ("user", "assistant"):
            return ev
    return None


def _es_limite(ev: dict) -> bool:
    return ev.get("type") == "assistant" and ev.get("error") == "rate_limit"


def _resetea(ev: dict) -> str:
    texto = json.dumps(ev.get("message", {}).get("content", ""), ensure_ascii=False)
    m = re.search(r"resets ([^\"\\]+)", texto)
    return m.group(1).strip() if m else "en unas horas"


def _ts_vuelve(vuelve: str) -> float:
    """«5:10pm (UTC)» → timestamp de la próxima vez que sea esa hora. Sin hora: 5 h."""
    h = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", vuelve or "", re.I)
    if not h:
        return time.time() + 5 * 3600
    hora = int(h.group(1)) % 12 + (12 if h.group(3).lower() == "pm" else 0)
    g = time.gmtime()
    ts = calendar.timegm((g.tm_year, g.tm_mon, g.tm_mday, hora, int(h.group(2) or 0), 0))
    return ts if ts > time.time() - 3600 else ts + 86400


def _quien(p: dict) -> str:
    return f"el agente de {p['usuario']} ({Path(p['relevo']).parent.name})"


def _relevo_de(jsonl: Path) -> tuple[Path, str] | None:
    ultimo = None
    with jsonl.open(errors="replace") as f:
        for linea in f:
            if "RELEVO.md" in linea:
                for m in RELEVO_RE.finditer(linea):
                    ultimo = m
    return (Path(ultimo.group(1)), ultimo.group(2)) if ultimo else None


def _url_mcp(usuario: str) -> str | None:
    try:
        texto = (REPO / "MCP_URLS.local.md").read_text()
    except OSError:
        return None
    m = re.search(rf"^- {re.escape(usuario)}\b[^:]*:\s*(https://\S+)", texto, re.M)
    return m.group(1) if m else None


# ----------------------------------------------------------------- vigilar
def vigilar() -> None:
    e = _estado()
    desde = time.time() - RECIENTES_H * 3600
    for jsonl in TRANSCRIPCIONES.glob("*.jsonl"):
        if jsonl.stat().st_mtime < desde:
            continue
        ev = _ultima_entrada(jsonl)
        if not ev or not _es_limite(ev):
            continue
        sesion, marca = jsonl.stem, ev.get("uuid", "")
        if e["avisados"].get(sesion) == marca:
            continue
        try:
            cuando = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            continue
        if time.time() - cuando > VENTANA_MIN * 60:
            continue
        relevo = _relevo_de(jsonl)
        if not relevo and "_agente/" not in jsonl.read_text(errors="replace"):
            continue  # no es un agente de vídeo
        e["avisados"][sesion] = marca
        vuelve = _resetea(ev)
        if not relevo:
            _guardar(e)
            telegram(f"⏸️ Un agente de vídeo (sesión {sesion[:8]}) se ha quedado sin cuota de "
                     f"Claude (vuelve: {vuelve}). No tiene RELEVO.md, así que nadie puede seguirle.")
            continue
        ruta, usuario = relevo
        p = {"sesion": sesion, "relevo": str(ruta), "usuario": usuario,
             "vuelve": vuelve, "vuelve_ts": _ts_vuelve(vuelve)}
        e["pendientes"][sesion[:8]] = p
        e.setdefault("vuelta", {})[sesion] = p
        _guardar(e)
        botones = [[{"text": f"🔁 Seguir con {n}", "callback_data": f"relevo|{sesion[:8]}|{m}"}]
                   for m, n in MOTORES.items()]
        botones.append([{"text": f"⏳ Esperar a Claude ({vuelve})",
                         "callback_data": f"relevo|{sesion[:8]}|esperar"}])
        telegram(f"⏸️ El agente de {usuario} ({ruta.parent.name}) se ha quedado sin cuota de "
                 f"Claude (vuelve: {vuelve}). ¿Sigue otro con su RELEVO.md?", botones)
    avisar_vuelta(e)


def avisar_vuelta(e: dict) -> None:
    """Claude ya tiene cuota: avisa de que se le puede decir «sigue» al agente."""
    for sesion, p in list(e.get("vuelta", {}).items()):
        if time.time() < p.get("vuelve_ts", 0) or lock_activo(Path(p["relevo"])):
            continue
        e["vuelta"].pop(sesion)
        _guardar(e)
        ev = _ultima_entrada(TRANSCRIPCIONES / f"{sesion}.jsonl")
        if ev and not _es_limite(ev):
            continue  # ya lo ha retomado alguien
        telegram(f"✅ Claude ya tiene cuota otra vez. Escríbele «sigue» a {_quien(p)}: "
                 "relee su RELEVO.md y continúa desde ahí.")


# ----------------------------------------------------------------- lanzar
PROMPT = """Eres el RELEVO de un agente (Claude) que hace vídeos de la app y se ha quedado
sin cuota. Néstor ha elegido que sigas tú. Su cuota vuelve: {vuelve}. Usuario de la
app: {usuario}.

1. Lee `AGENTS.md`, `src/agente_mcp/guias/README.md` (sobre todo «8. Relevo») y la guía
   del menú que nombre el RELEVO.
2. Lee `{relevo}`: qué hacía, por qué producto iba, qué falta, qué está AUTORIZADO
   por Néstor y cuántos créditos lleva. Sigue EXACTAMENTE desde ahí.
3. Usa el MCP `app` (ya conectado, es el de {usuario}) para todo lo de la app. El
   navegador del VPS con las normas de `src/agente_mcp/guias/comun/navegador-vps.md`:
   pestaña PROPIA y registro en ~/navegador_turnos.log.
4. Solo gastas lo que el RELEVO diga que Néstor ya autorizó. Si hace falta un «sí»
   nuevo, apúntalo en el RELEVO y PARA.
5. Al terminar CADA producto, actualiza el RELEVO («Lo lleva: Codex» y la hora).
6. Cuando pase la hora a la que vuelve Claude, termina el producto que tengas entre
   manos, deja el RELEVO al día y PARA: Claude retoma desde ahí.
7. Al acabar, resume en una línea qué has hecho (eso le llega a Néstor).
"""


def _comando(motor: str, p: dict, final: Path) -> list[str]:
    prompt = PROMPT.format(**p)
    if motor == "codex":
        return [CODEX, "exec", "--json", "--dangerously-bypass-approvals-and-sandbox",
                "-C", str(REPO), "-c", f'mcp_servers.app.url="{_url_mcp(p["usuario"])}"',
                "-o", str(final), prompt]
    raise ValueError(motor)


def lanzar(corta: str, motor: str) -> str:
    """Lo llama el bot al pulsar el botón. Devuelve el texto para el mensaje."""
    e = _estado()
    p = e["pendientes"].pop(corta, None)
    _guardar(e)
    if not p:
        return "Ese aviso ya no está pendiente."
    if motor not in MOTORES:
        return (f"⏳ Vale, el agente de {p['usuario']} espera a Claude ({p['vuelve']}). "
                "Te aviso cuando puedas decirle «sigue».")
    ruta = Path(p["relevo"])
    if lock_activo(ruta):
        return "Ya hay un relevo trabajando en ese RELEVO.md."
    if not _url_mcp(p["usuario"]):
        return f"No encuentro la URL del MCP de {p['usuario']} en MCP_URLS.local.md."
    subprocess.Popen([sys.executable, __file__, "_correr", motor, json.dumps(p)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, cwd=str(REPO))
    return (f"🔁 Sigue {MOTORES[motor]} con el RELEVO de {p['usuario']} hasta que vuelva "
            f"Claude ({p['vuelve']}). Revisa sus vídeos antes de publicar.")


def _correr(motor: str, p: dict) -> None:
    ruta = Path(p["relevo"])
    lock = ruta.with_name("RELEVO.lock")
    lock.write_text(f"{motor} {os.getpid()} {datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}\n")
    logs = DATOS / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    base = logs / f"{datetime.now():%Y%m%d_%H%M}_{p['usuario']}_{motor}"
    final = base.with_suffix(".final.txt")
    rc = -1
    try:
        with base.with_suffix(".jsonl").open("w") as salida:
            rc = subprocess.run(_comando(motor, {**p, "relevo": ruta}, final),
                                stdin=subprocess.DEVNULL, stdout=salida,
                                stderr=subprocess.STDOUT, cwd=str(REPO)).returncode
    finally:
        lock.unlink(missing_ok=True)
    resumen = final.read_text().strip()[-600:] if final.exists() else ""
    vuelta = ("Claude ya tiene cuota: te aviso enseguida para que le digas «sigue»."
              if time.time() >= p.get("vuelve_ts", 0) else
              f"Claude vuelve a las {p['vuelve']}: entonces te aviso para que le digas «sigue».")
    telegram(f"{'✅' if rc == 0 else '⚠️'} {MOTORES[motor]} ha parado el relevo de "
             f"{p['usuario']}. " + (resumen or f"Sin resumen (log: {base.name}).") + "\n\n" + vuelta)


def estado() -> None:
    raiz = HOME / "gdrive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_SHOP_AI_PRO/_agente"
    for relevo in raiz.glob("*/*/RELEVO.md"):
        pid = lock_activo(relevo)
        print((f"🔁 relevo pid {pid} · " if pid else "· ") + str(relevo))


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else "vigilar"
    if orden == "vigilar":
        vigilar()
    elif orden == "lanzar":
        print(lanzar(sys.argv[2], sys.argv[3]))
    elif orden == "_correr":
        _correr(sys.argv[2], json.loads(sys.argv[3]))
    elif orden == "estado":
        estado()
    else:
        sys.exit(__doc__)
