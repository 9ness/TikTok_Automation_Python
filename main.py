import streamlit as st
import os
import shutil
from moviepy.editor import concatenate_videoclips
from src.utils import load_config
from src.logic import create_video_segment

CFG = load_config()

st.set_page_config(page_title="TikTok Creator", layout="wide")
st.title("🏭 Fábrica de TikToks")

num_videos = st.number_input("Cantidad de videos:", 1, 10, 1)
uploads = {}
cols = st.columns(num_videos)

for i in range(num_videos):
    with cols[i]:
        st.subheader(f"Video {i+1}")
        files = st.file_uploader(f"Audios V{i+1}", accept_multiple_files=True, key=f"up_{i}")
        if files: uploads[i] = files

if st.button("🚀 GENERAR"):
    temp_dir = CFG["paths"]["temp_folder"]
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    status = st.empty()
    
    for idx, (vid_id, file_list) in enumerate(uploads.items()):
        status.text(f"Procesando Video {vid_id+1}...")
        
        # Guardar audios temporalmente
        local_audios = []
        path_lote = os.path.join(temp_dir, f"v{vid_id}")
        os.makedirs(path_lote, exist_ok=True)
        
        for f in file_list:
            path = os.path.join(path_lote, f.name)
            with open(path, "wb") as w: w.write(f.getbuffer())
            if "intro" not in f.name.lower():
                local_audios.append(path)
        
        local_audios.sort(key=lambda x: os.path.basename(x), reverse=True)
        clips = []
        token = False
        
        for aud in local_audios:
            try:
                # Nombre esperado: "5_Trump.mp3"
                name = os.path.splitext(os.path.basename(aud))[0]
                puesto = int(name.split('_')[0])
                presi = name.split('_')[1]
                
                seg, token = create_video_segment(aud, puesto, presi, CFG, token)
                if seg: clips.append(seg)
            except Exception as e:
                st.error(f"Error en {os.path.basename(aud)}: {e}")

        if clips:
            final = concatenate_videoclips(clips, method="compose")
            out = os.path.join(CFG["paths"]["output_folder"], f"TikTok_{vid_id+1}.mp4")
            sets = CFG["video_settings"]
            final.write_videofile(out, fps=sets["fps"], codec=sets["codec"], audio_codec=sets["audio_codec"])
            st.success(f"Video {vid_id+1} guardado en Drive.")
            
    st.balloons()