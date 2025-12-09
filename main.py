import streamlit as st
import os
import shutil
import time
import random
from datetime import datetime
import winsound # For audio notification (Windows)
import sys
import PIL.Image  # <--- Necesario para el arreglo

# ---------------------------------------------------------
# ZONA DE PARCHES (HACKS) PARA PYTHON MODERNO
# ---------------------------------------------------------

# 1. Arreglo para Pillow (El error ANTIALIAS que te salía en rojo)
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# 2. Arreglo para Python 3.13+ (Por si acaso tu versión es muy nueva)
# Las versiones nuevas borraron 'imghdr', así que lo simulamos.
if 'imghdr' not in sys.modules:
    import types
    sys.modules['imghdr'] = types.ModuleType('imghdr')
    def what(file, h=None): return 'jpeg'
    sys.modules['imghdr'].what = what

# ---------------------------------------------------------

from moviepy.editor import concatenate_videoclips, AudioFileClip, CompositeAudioClip
from moviepy.audio.AudioClip import AudioArrayClip
from moviepy.audio.fx.all import audio_fadeout
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
        # Actualizar Timer (MM:SS)
        elapsed = int(time.time() - self.start_time)
        mins, secs = divmod(elapsed, 60)
        self.time_placeholder.markdown(f"⏱️ **Tiempo de renderizado:** {mins:02d}:{secs:02d}")

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


        if files: uploads[i] = files



# ---------------------------------------------------------
# UI OPTIONS
# ---------------------------------------------------------
st.markdown("---")
# Resolution Selector
res_options = {
    "1080p (Producción) - Lento": [1080, 1920],
    "720p (HD) - Medio": [720, 1280],
    "480p (Borrador) - Rápido": [480, 854],
    "240p (Test Lógica) - Ultra Rápido": [240, 426]
}
selected_res_label = st.radio(
    "Calidad de Renderizado / Modo de Prueba",
    options=list(res_options.keys()),
    index=0, # Default 1080p
    horizontal=True
)

# EXPERIMENTAL ENGINE SELECTOR
engine_version = st.sidebar.selectbox(
    "Motor de Animación",
    ["v1_estable", "v2_beta"],
    index=0,
    help="v1: Estable, sin bordes negros, zoom rebote intro. v2: Experimental."
)

if 'is_running' not in st.session_state:
    st.session_state['is_running'] = False

# Buttons Layout (Closer) + Sound Toggle
col_btn1, col_btn2, col_sound, col_spacer = st.columns([1, 1, 1, 5])
with col_btn1:
    btn_start = st.button("🚀 GENERAR")
with col_btn2:
    if st.button("⛔ CANCELAR"):
        st.session_state['is_running'] = False
        st.stop()
with col_sound:
    sound_on = st.checkbox("🔔 Sonido", value=True)

if btn_start:
    # 1. Limpieza inicial SOLO al pulsar el botón
    temp_dir = CFG["paths"]["temp_folder"]
    if os.path.exists(temp_dir): 
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            st.error(f"Error limpiando temporales: {e}")
    os.makedirs(temp_dir, exist_ok=True)
    
    # INJECT CONFIGURATION
    target_res = res_options[selected_res_label]
    # FORCE DIVISIBLE BY 2 (Critical for libx264 yuv420p)
    w_safe = target_res[0] if target_res[0] % 2 == 0 else target_res[0] - 1
    h_safe = target_res[1] if target_res[1] % 2 == 0 else target_res[1] - 1
    CFG["video_settings"]["resolution"] = [w_safe, h_safe]
    
    if target_res != [1080, 1920]:
         st.toast(f"⚠️ MODO BORRADOR: Renderizando en {target_res[1]}p para velocidad.", icon="🚀")
    
    st.session_state['is_running'] = True
    
if st.session_state['is_running']:
    temp_dir = CFG["paths"]["temp_folder"]
    # Removed rmtree from here to avoid crash on rerun
    
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
                local_audios.append(path)
            
            # Sort: Intro first, then others reverse
            intro_file = None
            body_files = []
            
            for aud in local_audios:
                if "intro" in os.path.basename(aud).lower():
                    intro_file = aud
                else:
                    body_files.append(aud)
                    
            body_files.sort(key=lambda x: os.path.basename(x), reverse=True)
            
            final_audio_order = []
            if intro_file: final_audio_order.append(intro_file)
            final_audio_order.extend(body_files)
            
            clips = []
            token = False
            
            for aud in final_audio_order:
                try:
                    name = os.path.splitext(os.path.basename(aud))[0]
                    # Default values for Intro
                    puesto = 0
                    presi = "Unknown"
                    
                    if "intro" in name.lower():
                        puesto = 1 # Treat as Top 1 logic (or special)
                        presi = "Intro"
                    else:
                        parts = name.split('_')
                        if len(parts) >= 2:
                            puesto = int(parts[0])
                            presi = parts[1]
                    
                    # Pass status.write as a lambda to handle args safely if needed, or direct
                    def log_status(msg):
                        now = datetime.now().strftime("%H:%M:%S")
                        formatted = f"`{now}` {msg}"
                        # status.write(formatted) # HIDDEN from main view as requested
                        logs.append(formatted)

                    log_status(f"⚙️ Procesando: **{name}** (Personaje: {presi})")

                    seg, token = create_video_segment(aud, puesto, presi, CFG, token, log_callback=log_status, engine_version=engine_version)
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
                
                # --- LOGICA DE SONIDO DE TRANSICION (PÁGINA) ---
                path_pagina = os.path.join(CFG["paths"]["resources_library"], "pagina.mp3")
                sound_effect = None
                
                if os.path.exists(path_pagina):
                    try:
                        # Clean Audio Load
                        sound_effect = AudioFileClip(path_pagina)
                    except Exception as e:
                        print(f"Error cargando pagina.mp3: {e}")
                else:
                    print(f"Warning: No se encontró {path_pagina}")
                
                # -----------------------------------------------
                
                final = concatenate_videoclips(clips, method="compose")
                
                # --- APPLY TRANSITION SOUNDS GLOBALLY ---
                # Nueva lógica: Mezcla global para evitar cortes (clipping) al final de los segmentos
                if len(clips) > 1 and sound_effect:
                    sfx_clips = []
                    current_time = 0
                    
                    # Calcular momentos de corte (excluyendo el final del video)
                    for i in range(len(clips) - 1): # Todos menos el último
                        current_time += clips[i].duration
                        
                        # Offset solicitado: -0.2s
                        start_t = max(0, current_time - 0.2)
                        sfx_clips.append(sound_effect.set_start(start_t))
                    
                    if sfx_clips:
                        # Mezclar audio original del video final con los efectos
                        global_audio = CompositeAudioClip([final.audio] + sfx_clips)
                        # CRITICAL FIX: Clamp audio to video duration to prevent "phantom" extensions
                        global_audio = global_audio.set_duration(final.duration)
                        final = final.set_audio(global_audio)
                
                # --- AUDIO POLISH (FIX PHANTOM SOUNDS) ---
                # Force strictly matched duration again just in case
                if final.audio:
                    final_audio = final.audio.set_duration(final.duration)
                    # Aggressive fadeout (0.1s)
                    final_audio = final_audio.fx(audio_fadeout, 0.1)
                    final = final.set_audio(final_audio)
                
                # Generar nombre único con timestamp
                timestamp = datetime.now().strftime("%H%M%S")
                out_name = f"TikTok_{vid_id+1}_{timestamp}.mp4"
                out = os.path.join(CFG["paths"]["output_folder"], out_name)
                
                sets = CFG["video_settings"]
                
                # Medir tiempo total de este render
                start_render = time.time()

                # FORCE FINAL RESIZE TO EVENS (Double Safety)
                safe_w, safe_h = tuple(CFG["video_settings"]["resolution"])
                if safe_w % 2 != 0: safe_w -= 1
                if safe_h % 2 != 0: safe_h -= 1
                
                # Check if resize needed
                if final.w != safe_w or final.h != safe_h:
                    print(f"⚠️ Resizing final from {final.w}x{final.h} to {safe_w}x{safe_h} for compatibility.")
                    final = final.resize(newsize=(safe_w, safe_h))

                # Compatibilidad Windows: pixel format yuv420p y aac
                final.write_videofile(
                    out, 
                    fps=sets["fps"], 
                    codec='libx264', 
                    audio_codec='aac', 
                    logger=logger, 
                    threads=8, 
                    preset='ultrafast',
                    ffmpeg_params=['-pix_fmt', 'yuv420p']
                )
                end_render = time.time()
                render_duration = int(end_render - start_render)
                
                render_bar.empty() # Remove bar after finish
                timer_ph.empty()   # Remove timer after finish
                mins, secs = divmod(render_duration, 60)
                status.write(f"   ↳ ✅ Video {vid_id+1} guardado como `{out_name}` (Tiempo: {mins:02d}:{secs:02d}).")
                # st.video(out) REMOVED for performance
            
            if not st.session_state.get('is_running', False):
                status.warning("⚠️ Proceso cancelado.")
                break

            progress_bar.progress((idx + 1) / total_videos)
            
        if st.session_state.get('is_running', False):
            status.update(label="🚀 ¡Generación completada con éxito!", state="complete", expanded=False)
            
            # 1. Custom Falling Dollars
            money_html = """
            <style>
            @keyframes fall { 0% { top: -10%; opacity: 1; } 100% { top: 110%; opacity: 0; } }
            .money { position: fixed; font-size: 2rem; animation: fall 4s linear infinite; z-index: 9999; }
            </style>
            """
            # Create 20 falling dollars with random positions/delays
            for i in range(20):
                left = random.randint(0, 95)
                delay = random.uniform(0, 2)
                money_html += f'<div class="money" style="left: {left}%; animation-delay: {delay}s;">💸</div>'
            for i in range(15):
                left = random.randint(0, 95)
                delay = random.uniform(0, 3)
                money_html += f'<div class="money" style="left: {left}%; animation-delay: {delay}s;">💲</div>'
                
            st.markdown(money_html, unsafe_allow_html=True)
            
            # 2. Audio Notification
            if sound_on:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except:
                    pass
            
        st.session_state['is_running'] = False
    
    with st.expander("📝 Ver detalles de la edición (Logs)"):
        for log in logs:
            st.markdown(log)