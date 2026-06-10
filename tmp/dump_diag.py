import os, json, sys

tf = "/app/temp_work"
for jid in ["3af84eed", "b731e00c"]:
    # encontrar el archivo (jid es prefijo)
    import glob
    cands = glob.glob(os.path.join(tf, "editor_diagnostic_{}*.json".format(jid)))
    if not cands:
        print("== {} : sin diagnostic ==".format(jid)); continue
    diag = json.load(open(cands[0], encoding="utf-8"))
    print("\n\n############### JOB {} ###############".format(jid))
    print("top-level keys:", list(diag.keys()))
    aud = diag.get("audit") or {}
    print("\n--- AUDIT keys:", list(aud.keys()))
    print("quality_score:", aud.get("quality_score"))
    print("match_ratio:", aud.get("match_ratio"))
    for k in ("penalties", "penalty_breakdown", "reasons", "notes", "issues", "details"):
        if k in aud:
            print("audit.{}: {}".format(k, json.dumps(aud[k], ensure_ascii=False)[:1200]))
    print("inserted_blocks:", json.dumps(aud.get("inserted_blocks"), ensure_ascii=False)[:800])
    print("missing_blocks:", json.dumps(aud.get("missing_blocks"), ensure_ascii=False)[:800])
    sh = diag.get("self_heal") or {}
    print("\n--- SELF_HEAL:", json.dumps({k: v for k, v in sh.items() if k != "history"}, ensure_ascii=False)[:300])
    for h in sh.get("history", []):
        print("  HEAL #{} {} -> {}".format(h.get("attempt"), h.get("score_before"), h.get("score_after")))
        print("     actions:", json.dumps(h.get("actions"), ensure_ascii=False)[:900])
    # estructura de cortes / keeps
    for k in ("keep_intervals", "cuts", "removed_intervals", "ai_holistic", "duration_in", "duration_out"):
        if k in diag:
            v = diag[k]
            if isinstance(v, list):
                print("\n{} (n={}): {}".format(k, len(v), json.dumps(v, ensure_ascii=False)[:500]))
            else:
                print("\n{}: {}".format(k, json.dumps(v, ensure_ascii=False)[:300]))
