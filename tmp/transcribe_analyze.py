import json, glob
from src.editor_auto.tools.silence_cutter import _transcribe  # import seguro, NO llama get_queue

d = json.load(open(glob.glob("/app/temp_work/editor_diagnostic_eb24d096*.json")[0], encoding="utf-8"))
inp = d["input_path"]
keeps = [(float(x["start"]), float(x["end"])) for x in (d.get("final") or {}).get("preview_keep_intervals", [])]
print("input:", inp)
print("keeps:", [(round(a,2),round(b,2)) for a,b in keeps])

# extraer audio + transcribir input
import tempfile, subprocess, os
wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",inp,"-ac","1","-ar","16000","-vn",wav], timeout=300)
words = _transcribe(wav, model_size="large-v3", language="es", on_progress=None, timeout_s=900, primary_threads=2)
os.remove(wav)
print("n_words:", len(words))

def in_keep(t):
    return any(a <= t <= b for a,b in keeps)
def out_time(t):
    acc=0.0
    for a,b in keeps:
        if t < a-0.001: return None
        if t <= b+0.001: return acc+(t-a)
        acc += b-a
    return None

print("\n=== TRANSCRIPT input vs cortes (centro de palabra) ===")
prev=None
for w in words:
    s,e=float(w["start"]),float(w["end"]); c=(s+e)/2
    kept=in_keep(c)
    # ¿la palabra CRUZA un borde de keep? (parte dentro, parte fuera) → residuo/sobrecorte
    straddle=""
    for a,b in keeps:
        if (s < a < e) or (s < b < e):
            straddle=f"  *** CRUZA BORDE {round(a,2) if s<a<e else round(b,2)} ***"
            break
    ot=out_time(s)
    ots=f"{ot:6.2f}" if ot is not None else "  --  "
    mk="KEEP" if kept else "  cut"
    edge="  <--borde" if (prev is not None and kept!=prev) else ""
    print(f"{mk} out={ots} in[{s:6.2f}-{e:6.2f}] {w['word']!r}{edge}{straddle}")
    prev=kept
