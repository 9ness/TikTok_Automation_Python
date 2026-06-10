import json, glob

# editproject tiene words (idx/word/start/end) + keep_intervals del input.  SOLO lectura de fichero.
fs = glob.glob("/app/temp_work/editproject_eb24d096*.json")
if not fs:
    print("sin editproject"); raise SystemExit
proj = json.load(open(fs[0], encoding="utf-8"))
words = proj.get("words") or []
keeps = [(float(a), float(b)) for a, b in (proj.get("keep_intervals") or [])]
print("video_duration:", proj.get("video_duration_s"), "| n_words:", len(words), "| n_keeps:", len(keeps))
print("keeps:", [(round(a,2), round(b,2)) for a, b in keeps])

def in_keep(t):
    return any(a <= t <= b for a, b in keeps)

# Mapear cada palabra a output-time (acumulado sobre los keeps) si su centro cae en un keep.
def out_time(t):
    acc = 0.0
    for a, b in keeps:
        if t < a:
            return None
        if t <= b:
            return acc + (t - a)
        acc += b - a
    return None

print("\n=== TRANSCRIPT con estado (KEEP/cut) y output-time ===")
prev_kept = None
for w in words:
    s, e = float(w["start"]), float(w["end"])
    c = (s + e) / 2
    kept = in_keep(c)
    ot = out_time(s)
    mark = "KEEP" if kept else "  cut"
    ots = f"out={ot:6.2f}" if ot is not None else "out=  --  "
    # marcar transición keep<->cut (borde de corte)
    edge = ""
    if prev_kept is not None and kept != prev_kept:
        edge = "  <-- BORDE"
    print(f"{mark} {ots} in[{s:6.2f}-{e:6.2f}] {w['word']!r}{edge}")
    prev_kept = kept
