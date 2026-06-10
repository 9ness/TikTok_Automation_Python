import json
from src.api.dependencies import get_queue

q = get_queue()
js = [j for j in q.get_all() if str(getattr(j.mode, "value", j.mode)) == "editor_auto"]
js.sort(key=lambda j: getattr(j, "enqueued_at", 0) or 0, reverse=True)

print("==== TOTAL editor_auto jobs:", len(js), "====\n")

# 1) Estructura completa del diagnostic del job mas reciente
if js:
    j0 = js[0]
    diag0 = getattr(j0, "diagnostic", None) or {}
    print("=== DIAG KEYS del job mas reciente", str(j0.id)[:8], "===")
    print("keys:", list(diag0.keys()))
    print(json.dumps(diag0, default=str, indent=1)[:2500])
    print("\n=== PARAMS keys:", list((getattr(j0,'params',{}) or {}).keys()))

# 2) Buscar score en cualquier parte del diag de cada job + identificar usuario
def find_scores(d, path=""):
    out = []
    if isinstance(d, dict):
        for k, v in d.items():
            if "score" in str(k).lower() and isinstance(v, (int, float)):
                out.append((path + "/" + str(k), v))
            out += find_scores(v, path + "/" + str(k))
    return out

print("\n\n==== SCORES + USUARIO por job ====")
for j in js[:14]:
    diag = getattr(j, "diagnostic", None) or {}
    params = getattr(j, "params", {}) or {}
    uid = params.get("web_user_id") or params.get("user_id") or ""
    sub = params.get("output_subdir") or params.get("output_folder") or ""
    title = (getattr(j, "title", "") or "")[:40]
    scores = find_scores(diag)
    print("{} | {} | uid={} sub={} | scores={} | {}".format(
        str(j.id)[:8], str(getattr(j.status,"value",j.status)), uid[:12], sub, scores, title))
