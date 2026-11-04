#!/usr/bin/env python3
"""Pasa a RELATIVAS (`drive:…`) las rutas del Drive guardadas en el Redis local de la fábrica.

Ver `src/rutas_drive.py`. Se ejecuta en el HOST de vps-trabajo, desde la raíz del repo:

    python3 scripts/redis_rutas_relativas.py                 # simulación: cuenta qué cambiaría
    python3 scripts/redis_rutas_relativas.py --aplicar       # backup de Redis + cambia
    python3 scripts/redis_rutas_relativas.py --restaurar <originales.json>   # vuelta atrás

Con `NEBULABS_DRIVE_DIR` / `AI_PRO_DRIVE_DIR` / `DRIVE_ALIAS_JSON` en el entorno, las rutas
viejas se reescriben ya a su sitio nuevo (lo mismo que hace la app al leer).

Seguridad:
- Antes de cambiar nada: `SAVE` + copia fechada del dump (`--backup-dir`) y un JSON con el
  valor ORIGINAL de cada clave tocada (es lo que usa `--restaurar`).
- Cada escritura es un compare-and-set en Lua: si la app cambió la clave entre la lectura y
  la escritura, esa clave se deja como está (y se cuenta como «cambiada por la app»).
- Solo toca claves `string` (JSON o texto) y `set`; otros tipos se listan y no se tocan.
- No toca las claves de Upstash compartido (Editor Auto, Pronósticos): este Redis es el local.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.rutas_drive import a_relativa, relativizar  # noqa: E402

MARCAS = ("/mnt/drive", "/home/nebulabsai/gdrive", "drive:", "NEBULABS_AUTOMATED_TIKTOK", "TIKTOK_SHOP_AI_PRO")

LUA_BUSCAR = """
local out = {}
local cur = "0"
local marcas = ARGV
repeat
  local res = redis.call("SCAN", cur, "COUNT", 1000)
  cur = res[1]
  for _, k in ipairs(res[2]) do
    local t = redis.call("TYPE", k)["ok"]
    local v = nil
    if t == "string" then v = redis.call("GET", k)
    elseif t == "set" then v = table.concat(redis.call("SMEMBERS", k), "\\n")
    elseif t == "hash" then v = table.concat(redis.call("HGETALL", k), "\\n")
    elseif t == "list" then v = table.concat(redis.call("LRANGE", k, 0, -1), "\\n")
    end
    if v then
      for _, m in ipairs(marcas) do
        if string.find(v, m, 1, true) then
          if t == "string" then table.insert(out, {k, t, v})
          elseif t == "set" then table.insert(out, {k, t, cjson.encode(redis.call("SMEMBERS", k))})
          else table.insert(out, {k, t, ""}) end
          break
        end
      end
    end
  end
until cur == "0"
return cjson.encode(out)
"""

# CAS de un string: solo escribe si sigue valiendo lo que leímos.
LUA_CAS = """
if redis.call("GET", KEYS[1]) == ARGV[1] then redis.call("SET", KEYS[1], ARGV[2]) redis.call("INCR", "_rutas_drive:ok") return 1 end
redis.call("INCR", "_rutas_drive:saltadas") return 0
"""
# Cambia un miembro de un set si sigue estando.
LUA_SWAP = """
if redis.call("SISMEMBER", KEYS[1], ARGV[1]) == 1 then
  redis.call("SREM", KEYS[1], ARGV[1]) redis.call("SADD", KEYS[1], ARGV[2]) redis.call("INCR", "_rutas_drive:ok") return 1 end
redis.call("INCR", "_rutas_drive:saltadas") return 0
"""


def cli(contenedor: str, *args: str, stdin: bytes | None = None) -> str:
    r = subprocess.run(["docker", "exec", "-i", contenedor, "redis-cli", *args],
                       input=stdin, capture_output=True, check=True)
    return r.stdout.decode("utf-8")


def resp(*partes: str) -> bytes:
    out = [f"*{len(partes)}\r\n".encode()]
    for p in partes:
        b = p.encode("utf-8")
        out.append(b"$%d\r\n%s\r\n" % (len(b), b))
    return b"".join(out)


def buscar(contenedor: str) -> list[tuple[str, str, str]]:
    crudo = cli(contenedor, "--raw", "EVAL", LUA_BUSCAR, "0", *MARCAS)
    return [tuple(x) for x in json.loads(crudo)]


def nuevo_string(v: str) -> str:
    try:
        datos = json.loads(v)
    except (json.JSONDecodeError, ValueError):
        return a_relativa(v)
    if not isinstance(datos, (dict, list)):
        return a_relativa(v) if isinstance(datos, str) and datos == v else v
    nuevo = relativizar(datos)
    if nuevo == datos:
        return v
    # Mismo formato que la app (`json.dumps(..., ensure_ascii=False)`).
    return json.dumps(nuevo, ensure_ascii=False)


def plan(entradas):
    cambios, otros = [], []
    for k, t, v in entradas:
        if t == "string":
            n = nuevo_string(v)
            if n != v:
                cambios.append({"k": k, "t": t, "orig": v, "nuevo": n})
        elif t == "set":
            miembros = json.loads(v) if v else []
            pares = [(m, a_relativa(m)) for m in miembros]
            pares = [(a, b) for a, b in pares if a != b]
            if pares:
                cambios.append({"k": k, "t": t, "pares": pares})
        else:
            otros.append((k, t))
    return cambios, otros


def backup(contenedor: str, backup_dir: Path, sello: str) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    cli(contenedor, "SAVE")
    destino = backup_dir / f"redis-antes-rutas-{sello}.rdb"
    with open(destino, "wb") as f:
        subprocess.run(["docker", "exec", contenedor, "cat", "/data/dump.rdb"], stdout=f, check=True)
    if destino.stat().st_size < 1024:
        raise SystemExit(f"Backup sospechoso (muy pequeño): {destino}")
    return destino


def aplicar(contenedor: str, cambios) -> tuple[int, int]:
    cmds = []
    for c in cambios:
        if c["t"] == "string":
            cmds.append(resp("EVAL", LUA_CAS, "1", c["k"], c["orig"], c["nuevo"]))
        else:
            for a, b in c["pares"]:
                cmds.append(resp("EVAL", LUA_SWAP, "1", c["k"], a, b))
    if not cmds:
        return 0, 0
    return _pipe(contenedor, cmds)


def _pipe(contenedor: str, cmds: list[bytes]) -> tuple[int, int]:
    """Manda los EVAL en modo `--pipe` (protocolo crudo) y lee los contadores que dejan."""
    cli(contenedor, "DEL", "_rutas_drive:ok", "_rutas_drive:saltadas")
    salida = cli(contenedor, "--pipe", stdin=b"".join(cmds))
    if "errors: 0" not in salida:
        raise SystemExit(f"redis-cli --pipe con errores: {salida[-300:]}")
    ok = int(cli(contenedor, "--raw", "GET", "_rutas_drive:ok").strip() or 0)
    saltadas = int(cli(contenedor, "--raw", "GET", "_rutas_drive:saltadas").strip() or 0)
    cli(contenedor, "DEL", "_rutas_drive:ok", "_rutas_drive:saltadas")
    return ok, saltadas


def restaurar(contenedor: str, fichero: Path) -> None:
    cambios = json.loads(fichero.read_text(encoding="utf-8"))
    cmds = []
    for c in cambios:
        if c["t"] == "string":
            cmds.append(resp("EVAL", LUA_CAS, "1", c["k"], c["nuevo"], c["orig"]))
        else:
            for a, b in c["pares"]:
                cmds.append(resp("EVAL", LUA_SWAP, "1", c["k"], b, a))
    ok, saltadas = _pipe(contenedor, cmds) if cmds else (0, 0)
    print(f"Restaurado: {ok} · ya distinto (no tocado): {saltadas}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contenedor", default=os.getenv("REDIS_CONTENEDOR", "tiktok-redis"))
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--restaurar", type=Path)
    ap.add_argument("--backup-dir", type=Path,
                    default=Path("/mnt/HC_Volume_106974679/agentes/trabajo/drive-nebulabs/backups"))
    ap.add_argument("--sin-backup", action="store_true", help="solo para pruebas en un Redis de usar y tirar")
    a = ap.parse_args()

    if a.restaurar:
        restaurar(a.contenedor, a.restaurar)
        return

    entradas = buscar(a.contenedor)
    cambios, otros = plan(entradas)
    por_prefijo: dict[str, int] = {}
    for c in cambios:
        p = c["k"].split(":")[0]
        por_prefijo[p] = por_prefijo.get(p, 0) + 1
    print(f"Claves con marcas de ruta: {len(entradas)} · a cambiar: {len(cambios)}")
    for p, n in sorted(por_prefijo.items(), key=lambda x: -x[1]):
        print(f"  {n:6}  {p}")
    if otros:
        print(f"Otros tipos (no se tocan): {otros[:10]}")
    if cambios:
        ej = cambios[0]
        print("Ejemplo:", ej["k"], (ej.get("nuevo") or str(ej.get("pares")))[:200])
    if not a.aplicar:
        print("Simulación: no se ha cambiado nada (usa --aplicar).")
        return

    sello = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    a.backup_dir.mkdir(parents=True, exist_ok=True)
    if not a.sin_backup:
        print("Backup:", backup(a.contenedor, a.backup_dir, sello))
    originales = a.backup_dir / f"rutas-originales-{sello}.json"
    originales.write_text(json.dumps(cambios, ensure_ascii=False), encoding="utf-8")
    print("Originales (para --restaurar):", originales)
    ok, saltadas = aplicar(a.contenedor, cambios)
    print(f"Hecho: {ok} escrituras · {saltadas} saltadas (la app las cambió mientras tanto)")


if __name__ == "__main__":
    main()
