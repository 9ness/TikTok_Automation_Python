"""Copia las claves de la FÁBRICA de un Redis REST a otro (Upstash ⇄ local ⇄ otro).

python migrar.py <url_destino> <token_destino> [--solo-faltan] [--simular]
    origen = Upstash (UPSTASH_SHARED_REST_URL/_TOKEN, o UPSTASH_REDIS_REST_*)
python migrar.py <url_destino> <token_destino> --desde <url_origen> <token_origen>
    cualquier origen: p. ej. del Redis local (http://redis-rest:8080) a un Upstash
    o Redis gestionado nuevo, para sacar la fábrica del VPS. Ambos lados hablan la
    API REST de Upstash (un Redis cualquiera, con deploy/redis-rest delante).

Solo los prefijos de la fábrica (MOVER). Lo compartido con otras apps se queda
en Upstash: editor_auto/nebulabs (nebulabs-media), betai* y user_push_tokens
(Master Picks), fitlife, trip/viajes/session/username/usertrips (planificador),
fiesta, openai_latencies. Conserva tipo (string/hash/set/list/zset) y TTL.
--solo-faltan: no pisa lo que ya exista en local (segunda pasada tras el corte).
"""
import os
import sys

import requests

MOVER = ("tiktok_shop", "nicho_", "cuotas", "viralizacion", "tiktokCR", "plantillas", "cuenta_piloto")

if "--desde" in sys.argv:
    _i = sys.argv.index("--desde")
    up_url, up_tok = sys.argv[_i + 1].rstrip("/"), sys.argv[_i + 2]
else:
    up_url = (os.getenv("UPSTASH_SHARED_REST_URL") or os.environ["UPSTASH_REDIS_REST_URL"]).rstrip("/")
    up_tok = os.getenv("UPSTASH_SHARED_REST_TOKEN") or os.environ["UPSTASH_REDIS_REST_TOKEN"]
lo_url, lo_tok = sys.argv[1].rstrip("/"), sys.argv[2]
SOLO_FALTAN = "--solo-faltan" in sys.argv
SIMULAR = "--simular" in sys.argv


def pipe(url, tok, cmds):
    out = []
    for i in range(0, len(cmds), 200):
        r = requests.post(f"{url}/pipeline", headers={"Authorization": f"Bearer {tok}"},
                          json=cmds[i:i + 200], timeout=60)
        r.raise_for_status()
        out += r.json()
    return out


def es_fabrica(k: str) -> bool:
    return k.startswith(MOVER)


# 1) todas las claves de Upstash
claves, cur = [], "0"
while True:
    r = requests.post(up_url, headers={"Authorization": f"Bearer {up_tok}"},
                      json=["SCAN", cur, "COUNT", "1000"], timeout=60).json()["result"]
    cur, lote = r[0], r[1]
    claves += [k for k in lote if es_fabrica(k)]
    if str(cur) == "0":
        break
print(f"claves de la fábrica en Upstash: {len(claves)}")

if SOLO_FALTAN:
    ex = pipe(lo_url, lo_tok, [["EXISTS", k] for k in claves])
    claves = [k for k, e in zip(claves, ex) if not e.get("result")]
    print(f"  que faltan en local: {len(claves)}")

# 2) tipo y TTL
tipos = [x["result"] for x in pipe(up_url, up_tok, [["TYPE", k] for k in claves])]
ttls = [x["result"] for x in pipe(up_url, up_tok, [["PTTL", k] for k in claves])]
LEER = {"string": lambda k: ["GET", k], "hash": lambda k: ["HGETALL", k], "set": lambda k: ["SMEMBERS", k],
        "list": lambda k: ["LRANGE", k, "0", "-1"], "zset": lambda k: ["ZRANGE", k, "0", "-1", "WITHSCORES"]}
validas = [(k, t, p) for k, t, p in zip(claves, tipos, ttls) if t in LEER]
raros = [(k, t) for k, t in zip(claves, tipos) if t not in LEER and t != "none"]
if raros:
    print("tipos no soportados (no se copian):", raros[:10])
valores = [x.get("result") for x in pipe(up_url, up_tok, [LEER[t](k) for k, t, _ in validas])]

# 3) escribir en local
cmds, n = [], 0
for (k, t, p), v in zip(validas, valores):
    if v is None or (isinstance(v, list) and not v):
        continue
    cmds.append(["DEL", k])
    if t == "string":
        cmds.append(["SET", k, v])
    elif t == "hash":
        cmds.append(["HSET", k, *v])
    elif t == "set":
        cmds.append(["SADD", k, *v])
    elif t == "list":
        cmds.append(["RPUSH", k, *v])
    elif t == "zset":
        pares = []
        for i in range(0, len(v), 2):
            pares += [v[i + 1], v[i]]  # ZADD espera puntuación, miembro
        cmds.append(["ZADD", k, *pares])
    if isinstance(p, int) and p > 0:
        cmds.append(["PEXPIRE", k, str(p)])
    n += 1
print(f"a copiar: {n} claves ({len(cmds)} comandos locales)")
if not SIMULAR:
    res = pipe(lo_url, lo_tok, cmds)
    errores = [r for r in res if "error" in r]
    print("errores al escribir:", len(errores), errores[:3])
    # 4) comprobar
    ex = pipe(lo_url, lo_tok, [["EXISTS", k] for k, _, _ in validas])
    faltan = [k for (k, _, _), e in zip(validas, ex) if not e.get("result")]
    print(f"comprobación: {len(validas) - len(faltan)}/{len(validas)} presentes en local")
