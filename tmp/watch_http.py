import os, json, glob, time
import requests  # NO importa get_queue → NO arranca workers. Solo HTTP + lectura de fichero.

K = os.getenv("API_KEY")
UID = "6fb39fe857784fd3b02bb05fedfc4522"
JID = "eb24d096"
URL = f"http://localhost:8000/api/v1/editor-auto/web/admin/user-pipeline?user_id={UID}"

term = {"delivered", "review", "requeue", "failed"}
for i in range(70):
    try:
        d = requests.get(URL, headers={"X-API-Key": K}, timeout=15).json()
    except Exception as e:
        print(f"[{i}] http err {e}"); time.sleep(20); continue
    ip = d.get("in_process", []) or []
    rd = d.get("ready", []) or []
    state = (ip[0].get("state") if ip else ("delivered" if rd else "none"))
    print(f"[{i}] state={state} | en_proceso={d.get('n_in_process')} entregados={d.get('n_ready')}")
    if state in term:
        print("=== TERMINAL:", state, "===")
        break
    time.sleep(20)
else:
    print("timeout")

# Leer diagnostic del job (SOLO lectura de fichero, sin get_queue)
fs = glob.glob(f"/app/temp_work/editor_diagnostic_{JID}*.json")
if fs:
    diag = json.load(open(fs[0], encoding="utf-8"))
    a = diag.get("audit") or {}
    deep = a.get("deep") or {}
    print("\n=== DIAGNOSTIC", JID, "===")
    print("input_repaired:", diag.get("input_repaired"))
    print("score:", a.get("quality_score"), "| n_word_fallos:", a.get("n_word_fallos"),
          "| needs_requeue:", a.get("needs_requeue"))
    print("inserted:", len(deep.get("inserted_blocks") or []),
          "missing:", len(deep.get("missing_blocks") or []),
          "| silencios:", a.get("n_internal_silences"))
    for b in (deep.get("missing_blocks") or [])[:5]:
        print("   PERDIDA:", repr(b.get("text")))
    for b in (deep.get("inserted_blocks") or [])[:5]:
        print("   SOBRANTE:", repr(b.get("text")))
    sh = diag.get("self_heal") or {}
    for h in sh.get("history", []):
        print("   heal", h.get("kind"), "accepted", h.get("accepted"),
              "fallos", h.get("word_fallos_before"), "->", h.get("word_fallos_after"),
              "score", h.get("score_before"), "->", h.get("score_after"))
else:
    print("\nsin diagnostic todavía")
