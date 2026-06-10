import os, json, glob
from src.api.dependencies import get_queue
from src.tiktok_shop.repos.redis_base import get_shop_redis

UID = "6fb39fe857784fd3b02bb05fedfc4522"
DAY = "2026-06-10"
q = get_queue()
r = get_shop_redis()

# job mas reciente del dia
jobs = [j for j in q.get_all() if str(getattr(j.mode, "value", j.mode)) == "editor_auto"]
jobs.sort(key=lambda j: getattr(j, "enqueued_at", 0) or 0, reverse=True)

# webday_jobs apunta a...
wkey = f"editor_auto:webday_jobs:{UID}:{DAY}"
raw = r.get(wkey)
print("webday_jobs raw:", raw)

# el job 12ee0b74
for j in jobs:
    if str(j.id).startswith("12ee0b74"):
        print("\n=== JOB 12ee0b74 ===")
        print("status:", str(getattr(j.status, "value", j.status)))
        print("result_path:", getattr(j, "result_path", None))
        out = os.path.basename(getattr(j, "result_path", "") or "")
        print("out_name:", out)
        cands = glob.glob(f"/app/temp_work/editor_diagnostic_{str(j.id)}*.json")
        if cands:
            aud = (json.load(open(cands[0], encoding="utf-8")).get("audit") or {})
            print("score:", aud.get("quality_score"), "| n_word_fallos:", aud.get("n_word_fallos"),
                  "| needs_requeue:", aud.get("needs_requeue"))
        break

# approved set + sent files
akey = f"editor_auto:webday_approved:{UID}:{DAY}"
print("\napproved set:", r.smembers(akey))
print("manual_approval gate:", r.get("editor_auto:settings:manual_approval"))
# que archivos existen en salida del dia
sal = f"/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_EDITOR/Usuarios"
import subprocess
fns = subprocess.run(["bash","-lc", f"ls -1 '{sal}'/*/salida/{DAY}/ 2>/dev/null | head -20"], capture_output=True, text=True)
print("\narchivos en salida/" + DAY + ":\n", fns.stdout or "(ninguno / otra estructura)")
