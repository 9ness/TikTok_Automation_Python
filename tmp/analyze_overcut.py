import json, glob, subprocess, tempfile, os
from src.editor_auto.tools.silence_cutter import _transcribe

# diagnostic del job de bugallo
fs = glob.glob("/app/temp_work/editor_diagnostic_4b8369cb*.json")
d = json.load(open(fs[0], encoding="utf-8"))
inp = d["input_path"]
keeps = [(float(x["start"]), float(x["end"])) for x in (d.get("final") or {}).get("preview_keep_intervals", [])]
hol = (d.get("phases") or {}).get("ai_holistic") or (d.get("phases") or {}).get("holistic") or {}
print("input:", inp)
print("video_dur:", d.get("video_duration_s"), "| keeps:", len(keeps), "| kept_dur:", (d.get("final") or {}).get("kept_duration_s"))
print("holistico: kept", hol.get("kept_words"), "/", hol.get("total_words"), "palabras")
a = d.get("audit") or {}
print("score:", a.get("quality_score"), "| n_word_fallos:", a.get("n_word_fallos"))

# transcribir input completo
wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",inp,"-ac","1","-ar","16000","-vn",wav], timeout=300)
words = _transcribe(wav, model_size="large-v3", language="es", on_progress=None, timeout_s=900, primary_threads=2)
os.remove(wav)
print("n_words input:", len(words))

def in_keep(t):
    return any(a <= t <= b for a, b in keeps)

# Reconstruir lo que SOBREVIVE vs lo que se CORTA, en bloques
print("\n=== BLOQUES (KEEP = sobrevive / CUT = eliminado) ===")
cur = None; buf = []
for w in words:
    s, e = float(w["start"]), float(w["end"]); c = (s+e)/2
    k = in_keep(c)
    if cur is None: cur = k
    if k != cur:
        tag = "KEEP " if cur else "CUT  "
        txt = " ".join(x["word"].strip() for x in buf)
        print(f"{tag}[{float(buf[0]['start']):6.2f}-{float(buf[-1]['end']):6.2f}] {txt}")
        buf = []; cur = k
    buf.append(w)
if buf:
    tag = "KEEP " if cur else "CUT  "
    print(f"{tag}[{float(buf[0]['start']):6.2f}-{float(buf[-1]['end']):6.2f}] {' '.join(x['word'].strip() for x in buf)}")
