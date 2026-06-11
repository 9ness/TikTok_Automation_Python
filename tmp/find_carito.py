import subprocess, tempfile, os
from src.editor_auto.tools.silence_cutter import _transcribe

IN = "/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_EDITOR/Usuarios/nueveness/salida/2026-06-11/1781176798_buga_2_editado.mp4"
dur = float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",IN], capture_output=True, text=True).stdout.strip() or 0)
print("duracion output:", round(dur,2), "s | mitad =", round(dur/2,2), "s")
wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",IN,"-ac","1","-ar","16000","-vn",wav], timeout=120)
w = _transcribe(wav, model_size="large-v3", language="es", on_progress=None, timeout_s=600, primary_threads=2)
os.remove(wav)
print("palabras con 'car'/'compr'/'link'/'perfil'/'enlace'/'aqui':")
for x in w:
    wl = str(x.get("word","")).lower()
    if any(k in wl for k in ("car","compr","link","perfil","enlace","aqu","abajo","tienda")):
        t=float(x["start"])
        print(f"  {t:6.2f}s  {x['word']!r}   {'(1a mitad → NO se busca)' if t < dur/2 else '(2a mitad → SI se busca)'}")
