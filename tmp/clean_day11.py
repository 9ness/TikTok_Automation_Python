# Limpia los 3 registros rotos del dia 2026-06-11 (uploads muertos por el
# deploy): quita sus entradas de webday_jobs + webday_sentfiles para que el
# usuario pueda re-subirlos limpio. NO usa get_queue (sin workers rogue).
from src.editor_auto.repos.redis_base import get_editor_redis

UID = "6fb39fe857784fd3b02bb05fedfc4522"
DAY = "2026-06-11"
BROKEN = [
    "1781176776_buga_1.MOV",
    "1781176798_buga_2.mp4",
    "1781176867_clienta_2.MOV",
]

r = get_editor_redis()
jk = f"webday_jobs:{UID}:{DAY}"
sk = f"webday_sentfiles:{UID}:{DAY}"

jobs = r.get_json(jk) or []
print("ANTES jobs:", [(j.get("filename"), j.get("job_id", "")[:8]) for j in jobs])
keep = [j for j in jobs if j.get("filename") not in BROKEN]
r.set_json(jk, keep)
print("DESPUES jobs:", [(j.get("filename"), j.get("job_id", "")[:8]) for j in keep])

try:
    sent = r.smembers(sk)
except Exception:
    sent = set()
print("ANTES sent:", sent)
for f in BROKEN:
    try:
        r.srem(sk, f)
    except Exception as e:
        print("srem err", f, e)
try:
    print("DESPUES sent:", r.smembers(sk))
except Exception:
    pass
