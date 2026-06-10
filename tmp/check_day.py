import os, json, glob
from src.api.dependencies import get_queue
from src.api.routers.editor_auto import web_upload as wu

UID = "6fb39fe857784fd3b02bb05fedfc4522"
DAY = "2026-06-10"
q = get_queue()
by_id = {str(j.id): j for j in q.get_all()}

print("=== _get_day_jobs ===")
jobs_meta = wu._get_day_jobs(UID, DAY)
for m in jobs_meta:
    jid = m.get("job_id")
    j = by_id.get(jid)
    st = str(getattr(j.status, "value", j.status)) if j else "NO-JOB"
    rp = os.path.basename(getattr(j, "result_path", "") or "") if j else ""
    sc = wu._job_score(j) if j else None
    deliv = wu._job_deliverable(j, sc) if j else None
    print(f"  job={jid[:8] if jid else None} status={st} out={rp} score={sc} deliverable={deliv} | meta_src={m.get('filename')}")

print("\n=== approved set ===")
print(wu._approved_set(UID, DAY))
print("\n=== gate manual_approval ===", wu._gate_on() if hasattr(wu, "_gate_on") else "?")

# el job 12ee0b74 esta en la lista del dia?
ids = [m.get("job_id","")[:8] for m in jobs_meta]
print("\n12ee0b74 en la lista del dia?:", any(i.startswith("12ee0b74") for i in ids))
