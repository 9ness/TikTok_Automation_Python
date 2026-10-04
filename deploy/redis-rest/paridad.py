"""Compara respuesta a respuesta el Upstash real con este redis-rest.
python paridad.py <url_local> <token_local>   (lee Upstash del .env de la fábrica)
Usa claves `zz_shimtest:*` y las borra al acabar en los dos."""
import json
import sys
import urllib.parse as up

import requests
from dotenv import dotenv_values

e = dotenv_values("/home/nebulabsai/TikTok_Automation_Python/.env")
SRV = {"upstash": (e["UPSTASH_REDIS_REST_URL"].strip('"'), e["UPSTASH_REDIS_REST_TOKEN"].strip('"')),
       "local": (sys.argv[1], sys.argv[2])}
enc = lambda s: up.quote(s, safe="")
P = "zz_shimtest:"
k = P + "Productos España/27 Pront Flow ñandú"
big = json.dumps({"x": "é€😀" * 3000, "l": list(range(300))}, ensure_ascii=False)


def J(r):
    try:
        return r.json()
    except ValueError:
        return ("NOJSON", r.text[:60])


def pasos(u, t):
    H = {"Authorization": f"Bearer {t}"}
    out = []
    g = lambda path: out.append((path[:30], *(lambda r: (r.status_code, J(r)))(requests.get(f"{u}/{path}", headers=H, timeout=20))))
    p = lambda path, body=None: out.append((path[:30], *(lambda r: (r.status_code, J(r)))(requests.post(f"{u}/{path}", headers={**H, "Content-Type": "text/plain"}, data=body, timeout=20))))
    j = lambda cmd: out.append((cmd[0], *(lambda r: (r.status_code, J(r)))(requests.post(u, headers=H, json=cmd, timeout=20))))
    try:
        p(f"set/{enc(k)}", big.encode()); g(f"get/{enc(k)}"); g(f"get/{enc(P+'noexiste')}")
        p(f"set/{enc(P+'a')}", "hola"); g(f"mget/{enc(P+'a')}/{enc(k)}/{enc(P+'nada')}")
        p(f"sadd/{enc(P+'s')}/m1"); p(f"sadd/{enc(P+'s')}/m1"); g(f"smembers/{enc(P+'s')}")
        g(f"sismember/{enc(P+'s')}/m1"); g(f"sismember/{enc(P+'s')}/zz"); p(f"srem/{enc(P+'s')}/m1")
        g(f"incr/{enc(P+'c')}"); g(f"expire/{enc(P+'c')}/100")
        p(f"lpush/{enc(P+'l')}/x"); p(f"lpush/{enc(P+'l')}/y"); g(f"lrange/{enc(P+'l')}/0/-1"); g(f"ltrim/{enc(P+'l')}/0/0")
        j(["SET", P+"j", "v", "EX", "60"]); j(["GET", P+"j"]); j(["MGET", P+"j", P+"nada"])
        j(["SET", P+"lock", "1", "NX", "EX", "10"]); j(["SET", P+"lock", "1", "NX", "EX", "10"])
        j(["HSET", P+"h", "a", "1", "b", "2"]); j(["HGETALL", P+"h"]); j(["HGET", P+"h", "a"])
        j(["EXISTS", P+"j", P+"nada"]); j(["NOEXISTE"])
        j(["ZADD", P+"z", "1", "a", "2", "b"]); j(["ZRANGE", P+"z", "0", "-1", "WITHSCORES"])
        j(["SCARD", P+"s"]); j(["INCRBY", P+"c", "5"]); j(["SCAN", "0", "MATCH", P+"zzz*", "COUNT", "10"])
        g(f"keys/{enc(P+'s*')}"); g(f"del/{enc(P+'a')}")
        r = requests.get(f"{u}/get/{enc(P+'j')}", headers={"Authorization": "Bearer mal"}, timeout=20)
        out.append(("token malo", r.status_code, None))
    finally:
        ks = requests.post(u, headers=H, json=["KEYS", P+"*"], timeout=20).json().get("result") or []
        if ks:
            requests.post(u, headers=H, json=["DEL", *ks], timeout=20)
    return out


a, b = pasos(*SRV["upstash"]), pasos(*SRV["local"])
dif = 0
for x, y in zip(a, b):
    igual = x[1] == y[1] and (x[2] == y[2] or (x[0] in ("NOEXISTE", "SCAN") and isinstance(x[2], dict)
                                               and (("error" in x[2] and "error" in y[2]) or x[0] == "SCAN")))
    if not igual:
        dif += 1
        print("DIFERENTE:", str(x)[:160], "|", str(y)[:160])
print(f"{len(a)} comprobaciones, {dif} diferencias")
