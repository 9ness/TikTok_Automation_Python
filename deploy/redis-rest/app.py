"""Redis REST compatible con Upstash, sobre un Redis local.

La fábrica habla con Upstash por HTTP en tres formas, y las tres valen aquí sin
cambiar ni una línea de sus ~20 clientes:
  - ruta:     GET/POST /set/<clave>/<valor>   (cada segmento, url-decodificado)
  - ruta + cuerpo: POST /set/<clave>  con el valor en el cuerpo (texto)
  - JSON:     POST /  ["SET", "clave", "valor", "EX", "60"]
  - pipeline: POST /pipeline  [["SET","a","1"], ["GET","a"]]
Respuestas como Upstash: {"result": ...} o {"error": "..."} (400). Autenticación
con `Authorization: Bearer <REST_TOKEN>`.
"""
import hmac
import json
import os
from urllib.parse import unquote

import redis
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

TOKEN = os.environ["REST_TOKEN"]
R = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=False,
                         protocol=2)  # RESP2, el de Upstash (RESP3 agrupa pares y dobles)


def _py(v):
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8")
        except UnicodeDecodeError:
            return v.decode("latin-1")
    if isinstance(v, (list, tuple, set)):
        return [_py(x) for x in v]
    if isinstance(v, dict):  # no debería pasar sin decode, por si acaso
        out = []
        for k, x in v.items():
            out += [_py(k), _py(x)]
        return out
    if isinstance(v, bool):
        return 1 if v else 0
    return v


def _ejecutar(args: list) -> dict:
    if not args:
        return {"error": "ERR empty command"}
    args = [a if isinstance(a, (bytes, str, int, float)) else str(a) for a in args]
    # Directo a la conexión: la respuesta CRUDA del servidor (redis-py no la
    # reinterpreta: ni "OK"→True ni WITHSCORES→pares), igual que Upstash.
    conn = R.connection_pool.get_connection(str(args[0]))
    try:
        conn.send_command(*args)
        res = conn.read_response()
        return {"result": _py(res)}
    except redis.ResponseError as e:
        return {"error": str(e)}
    except (redis.ConnectionError, redis.TimeoutError):
        conn.disconnect()
        raise
    finally:
        R.connection_pool.release(conn)


def _autorizado(req: Request) -> bool:
    a = req.headers.get("authorization", "")
    tok = a[7:] if a.lower().startswith("bearer ") else req.query_params.get("_token", "")
    return hmac.compare_digest(tok.encode(), TOKEN.encode())


async def raiz(req: Request):
    if not _autorizado(req):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    if req.method == "GET":
        return JSONResponse({"result": "redis-rest ok"})
    try:
        args = json.loads(await req.body())
    except ValueError:
        return JSONResponse({"error": "ERR invalid JSON"}, status_code=400)
    r = _ejecutar(args)
    return JSONResponse(r, status_code=400 if "error" in r else 200)


async def pipeline(req: Request):
    if not _autorizado(req):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    cmds = json.loads(await req.body())
    return JSONResponse([_ejecutar(c) for c in cmds])


async def ruta(req: Request):
    if not _autorizado(req):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    crudo = req.scope.get("raw_path", b"").decode("latin-1").split("?", 1)[0]
    args = [unquote(s) for s in crudo.strip("/").split("/")]
    if req.method == "POST":
        cuerpo = await req.body()
        if cuerpo:
            args.append(cuerpo)  # el valor va en el cuerpo, tal cual (bytes)
    r = _ejecutar(args)
    return JSONResponse(r, status_code=400 if "error" in r else 200)


app = Starlette(routes=[
    Route("/", raiz, methods=["GET", "POST"]),
    Route("/pipeline", pipeline, methods=["POST"]),
    Route("/multi-exec", pipeline, methods=["POST"]),
    Route("/{resto:path}", ruta, methods=["GET", "POST"]),
])
