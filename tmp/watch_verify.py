import os, json, glob, time
import requests
from src.editor_auto.tools.silence_cutter import _transcribe  # NO get_queue

K = os.getenv("API_KEY")
UID = "6fb39fe857784fd3b02bb05fedfc4522"
JID = "ff37e967"
URL = f"http://localhost:8000/api/v1/editor-auto/web/admin/user-pipeline?user_id={UID}"
term = {"delivered", "review", "requeue", "failed"}

for i in range(70):
    try:
        d = requests.get(URL, headers={"X-API-Key": K}, timeout=15).json()
    except Exception as e:
        print(f"[{i}] http err {e}"); time.sleep(20); continue
    ip = d.get("in_process", []) or []
    state = (ip[0].get("state") if ip else ("delivered" if d.get("ready") else "none"))
    print(f"[{i}] state={state}")
    if state in term:
        print("=== TERMINAL:", state, "==="); break
    time.sleep(20)

# diagnostic (lectura de fichero)
fs = glob.glob(f"/app/temp_work/editor_diagnostic_{JID}*.json")
if fs:
    diag = json.load(open(fs[0], encoding="utf-8"))
    a = diag.get("audit") or {}
    print("score:", a.get("quality_score"), "| n_word_fallos:", a.get("n_word_fallos"),
          "| needs_requeue:", a.get("needs_requeue"))
    sh = diag.get("self_heal") or {}
    for h in sh.get("history", []):
        print("  heal", h.get("kind"), "accepted", h.get("accepted"),
              "fallos", h.get("word_fallos_before"), "->", h.get("word_fallos_after"))

# re-transcribir el OUTPUT final (el editado mas reciente) para ver slivers
sal = "/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_EDITOR/Usuarios/nueveness/salida/2026-06-10"
vids = sorted(glob.glob(f"{sal}/*_editado*.mp4"), key=os.path.getmtime, reverse=True)
if vids:
    out = vids[0]
    print("\n=== RE-TRANSCRIBO OUTPUT:", os.path.basename(out), "===")
    import tempfile, subprocess
    wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",out,"-ac","1","-ar","16000","-vn",wav], timeout=120)
    w = _transcribe(wav, model_size="large-v3", language="es", on_progress=None, timeout_s=600, primary_threads=2)
    os.remove(wav)
    print("texto completo del output:")
    print(" ".join(x.get("word","").strip() for x in w))
    print("\npalabras con timestamp:")
    for x in w:
        print(f"  {float(x['start']):6.2f}-{float(x['end']):6.2f} {x['word']!r}")
