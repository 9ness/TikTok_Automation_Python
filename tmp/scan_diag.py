import os, json, glob

tf = "/app/temp_work"
files = glob.glob(os.path.join(tf, "editor_diagnostic_*.json"))
files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

print("==== {} diagnostics encontrados ====\n".format(len(files)))
for p in files[:16]:
    try:
        diag = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        print(p, "ERROR", e); continue
    jid = os.path.basename(p).replace("editor_diagnostic_", "").replace(".json", "")
    aud = diag.get("audit") or {}
    sh = diag.get("self_heal") or {}
    score = aud.get("quality_score")
    ib = aud.get("inserted_blocks") or []
    mb = aud.get("missing_blocks") or []
    n_cuts = len(diag.get("cuts") or diag.get("removed_intervals") or [])
    mt = os.path.getmtime(p)
    import time as _t
    ts = _t.strftime("%m-%d %H:%M", _t.localtime(mt))
    print("[{}] {} | score={} | ins={} miss={} | cuts={} | model={}".format(
        ts, jid[:8], score, len(ib), len(mb), n_cuts, diag.get("ai_model") or aud.get("model")))
    if sh:
        for h in sh.get("history", []):
            print("      heal #{}: {} -> {} | residuo={} guard={} restaura={}".format(
                h.get("attempt"), h.get("score_before"), h.get("score_after"),
                h.get("n_residue_cuts"), h.get("n_guarded_cuts"), h.get("n_restores")))
