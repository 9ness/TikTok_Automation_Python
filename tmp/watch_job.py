import time, os, json, glob
from src.api.dependencies import get_queue

q = get_queue()
JID = "c3f9b594"

def find():
    for j in q.get_all():
        if str(j.id).startswith(JID):
            return j
    return None

for i in range(75):
    j = find()
    if j is None:
        print("[{}] no encontrado".format(i)); time.sleep(20); continue
    st = str(getattr(j.status, "value", j.status))
    if st in ("completed", "failed", "cancelled"):
        print("=== FIN === status:", st)
        if st == "failed":
            print("error:", str(getattr(j, "error", ""))[:300]); break
        cands = glob.glob("/app/temp_work/editor_diagnostic_{}*.json".format(JID))
        if cands:
            diag = json.load(open(cands[0], encoding="utf-8"))
            aud = diag.get("audit") or {}
            sh = diag.get("self_heal") or {}
            deep = aud.get("deep") or {}
            nins = len(deep.get("inserted_blocks") or [])
            nmis = len(deep.get("missing_blocks") or [])
            print("input_repaired:", diag.get("input_repaired"))
            print("score FINAL:", aud.get("quality_score"), "| verdict:", aud.get("verdict"))
            print("n_word_fallos:", aud.get("n_word_fallos"), "(inserted={} missing={})".format(nins, nmis))
            print("needs_requeue:", aud.get("needs_requeue"), "-> ENTREGABLE:" , not aud.get("needs_requeue") and (aud.get("quality_score") or 0) >= 90)
            print("silencios:", aud.get("n_internal_silences"), "loose:", aud.get("n_loose_words"))
            for b in (deep.get("missing_blocks") or [])[:5]:
                print("   PERDIDA:", repr(b.get("text")))
            for b in (deep.get("inserted_blocks") or [])[:5]:
                print("   SOBRANTE:", repr(b.get("text")))
            for h in sh.get("history", []):
                print("   intento #{} ({}) accepted={}: fallos {}->{} score {}->{}".format(
                    h.get("attempt"), h.get("kind"), h.get("accepted"),
                    h.get("word_fallos_before"), h.get("word_fallos_after"),
                    h.get("score_before"), h.get("score_after")), h.get("actions"))
        break
    print("[{}] {}".format(i, st)); time.sleep(20)
else:
    print("timeout")
