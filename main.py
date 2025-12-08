import streamlit as st
import os
import shutil
import time
from moviepy.editor import concatenate_videoclips
from proglog import ProgressBarLogger
from src.utils import load_config, get_president_assets
from src.logic import create_video_segment

class StreamlitLogger(ProgressBarLogger):
    def __init__(self, pb_object, time_placeholder):
        super().__init__(init_state=None, bars=None, ignored_bars=None, logged_bars='all', min_time_interval=0, ignore_bars_under=0)
        self.pb_object = pb_object
        self.time_placeholder = time_placeholder
        self.start_time = time.time()
    
    def callback(self, **changes):
        # Actualizar Timer
        elapsed = int(time.time() - self.start_time)
        self.time_placeholder.markdown(f"⏱️ **Tiempo de renderizado:** {elapsed}s")

        # Actualizar Progreso
        for bar in changes.get('bars', []):
            if 'total' in self.bars[bar]:
                current = self.bars[bar]['index']
                total = self.bars[bar]['total']
                if total > 0:
                    percent = current / total
                    self.pb_object.progress(min(max(percent, 0.0), 1.0))

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
    
    logs = []
    
    with st.status("🏭 Iniciando fábrica de videos...", expanded=True) as status:
        total_videos = len(uploads)
        progress_bar = st.progress(0)
    
        for idx, (vid_id, file_list) in enumerate(uploads.items()):
            status.write(f"🎞️ **Procesando Video {vid_id+1}/{total_videos}**...")
            
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
                    name = os.path.splitext(os.path.basename(aud))[0]
                    puesto = int(name.split('_')[0])
                    presi = name.split('_')[1]
                    
                    # Log info (Best effort)
                    ph, vi, sil = get_president_assets(CFG["paths"]["library_base"], presi, CFG)
                    n_ph = len(ph) if ph else 0
                    n_vi = len(vi) if vi else 0
                    logs.append(f"📌 **Video {vid_id+1}** | Audio: `{os.path.basename(aud)}` | Presidente: **{presi}** (Fotos disp: {n_ph}, Videos disp: {n_vi})")
                    
                    seg, token = create_video_segment(aud, puesto, presi, CFG, token)
                    if seg: clips.append(seg)
                except Exception as e:
                    status.error(f"❌ Error en {os.path.basename(aud)}: {e}")
                    logs.append(f"❌ **Error** en {os.path.basename(aud)}: {e}")
    
            if clips:
                status.write(f"   ↳ ⚙️ Renderizando TikTok {vid_id+1}...")
                
                # Elementos visuales del renderizado
                timer_ph = st.empty()
                render_bar = st.progress(0)
                
                logger = StreamlitLogger(render_bar, timer_ph)
                
                final = concatenate_videoclips(clips, method="compose")
                out = os.path.join(CFG["paths"]["output_folder"], f"TikTok_{vid_id+1}.mp4")
                sets = CFG["video_settings"]
                final.write_videofile(out, fps=sets["fps"], codec=sets["codec"], audio_codec=sets["audio_codec"], logger=logger)
                
                render_bar.empty() # Remove bar after finish
                timer_ph.empty()   # Remove timer after finish
                status.write(f"   ↳ ✅ Video {vid_id+1} guardado.")
                # st.video(out) REMOVED for performance
            
            progress_bar.progress((idx + 1) / total_videos)
            
        status.update(label="🚀 ¡Generación completada con éxito!", state="complete", expanded=False)
    
    st.balloons()
    
    with st.expander("📝 Ver detalles de la edición (Logs)"):
        for log in logs:
            st.markdown(log)