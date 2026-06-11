# Re-transcribe el render mas reciente de salida (solo lectura + whisper local).
import glob, os, subprocess, tempfile
from src.editor_auto.tools.silence_cutter import _transcribe

sal = "/mnt/drive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_EDITOR/Usuarios/nueveness/salida/2026-06-10"
vids = sorted(glob.glob(f"{sal}/*_editado*.mp4"), key=os.path.getmtime, reverse=True)
out = vids[0]
print("OUTPUT:", os.path.basename(out))
wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",out,"-ac","1","-ar","16000","-vn",wav], timeout=120)
w = _transcribe(wav, model_size="large-v3", language="es", on_progress=None, timeout_s=600, primary_threads=2)
os.remove(wav)
print("TEXTO:")
print(" ".join(x.get("word","").strip() for x in w))
