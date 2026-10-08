# Une el OCR de las franjas en una transcripción con hablante y minuto
import glob, os, re, difflib
def norm(s): return re.sub(r'[^a-z0-9áéíóúñ ]','',s.lower()).strip()
nombre = re.compile(r'^\W*(\(\d\)\s*)?([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(\s+[A-ZÁÉÍÓÚÑ\w][\wáéíóúñ]*){0,3})\s*(\|.*)?$')
out = []  # (t, hablante, linea)
for f in sorted(glob.glob('ocr2/*.txt')):
    t = int(os.path.basename(f)[:-4]) - 1
    lines = [l.strip() for l in open(f, encoding='utf-8', errors='ignore') if l.strip()]
    quien = None; texto = []
    for l in lines:
        m = nombre.match(l)
        if ('TikTok Shop' in l or 'Jonny' in l) and len(l) < 40: quien = 'Jonny'; continue
        if m and len(l) < 30 and not re.search(r'[,.?¿!¡]', l) and quien is None: quien = m.group(2); continue
        if len(norm(l)) >= 4: texto.append(l)
    for l in texto:
        nl = norm(l); dup = False
        for i in range(max(0, len(out)-12), len(out)):
            pl = norm(out[i][2])
            if nl == pl or nl in pl or difflib.SequenceMatcher(None, nl, pl).ratio() > 0.85:
                dup = True; break
            if pl and nl.startswith(pl[:max(8, len(pl)-3)]) and len(nl) > len(pl):
                out[i] = (out[i][0], out[i][1], l); dup = True; break
        if not dup: out.append((t, quien or '?', l))
with open('transcript.txt', 'w') as fo:
    last = -999; lq = None
    for t, q, l in out:
        if t - last >= 60 or q != lq:
            fo.write(f'\n[{t//3600}:{t%3600//60:02d}:{t%60:02d}] {q}: '); last = t; lq = q
        fo.write(l + ' ')
print(len(out))
