import os, json, glob, time
from src.api.dependencies import get_queue

UID = "6fb39fe857784fd3b02bb05fedfc4522"
q = get_queue()

# job 12ee0b74 detalle
for j in q.get_all():
    if str(j.id).startswith("12ee0b74"):
        print("\nid:", j.id, "status:", str(getattr(j.status,"value",j.status)))
        for attr in ("started_at","finished_at","enqueued_at","resume_count","attempts","retries"):
            print("  ", attr, "=", getattr(j, attr, "—"))
        params = getattr(j,"params",{}) or {}
        print("  params keys:", list(params.keys()))
        print("  output_subdir:", params.get("output_subdir"), "| tools_used:", params.get("tools_used"))

# diagnostic mtime
for f in glob.glob("/app/temp_work/editor_diagnostic_12ee0b74*.json"):
    print("\ndiag", f, "mtime:", time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(f))))
    d = json.load(open(f, encoding="utf-8"))
    print("  config_used tools:", d.get("config_used"))
    sh = d.get("self_heal") or {}
    print("  self_heal attempts:", sh.get("attempts"), [(h.get("kind"),h.get("accepted"),h.get("score_before"),h.get("score_after")) for h in sh.get("history",[])])

# archivos step de este job en temp_work
print("\nstep files de 12ee0b74 en temp_work:")
for f in glob.glob("/app/temp_work/editor_step_12ee0b74*") + glob.glob("/app/temp_work/editor_clean_12ee0b74*"):
    print("  ", f, os.path.getsize(f))
