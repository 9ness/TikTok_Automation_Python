import streamlit as st
import os
import shutil
import time
import random
from datetime import datetime
import winsound # For audio notification (Windows)
import sys
import PIL.Image 
import glob
from dotenv import load_dotenv

# ---------------------------------------------------------
# CARGA DE ENTORNO
# ---------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------
# ZONA DE PARCHES (HACKS) PARA PYTHON MODERNO
# ---------------------------------------------------------

# 1. Arreglo para Pillow (El error ANTIALIAS que te salía en rojo)
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# 2. Arreglo para Python 3.13+ (Por si acaso tu versión es muy nueva)
if 'imghdr' not in sys.modules:
    import types
    sys.modules['imghdr'] = types.ModuleType('imghdr')
    def what(file, h=None): return 'jpeg'
    sys.modules['imghdr'].what = what

# ---------------------------------------------------------

from moviepy.editor import concatenate_videoclips, AudioFileClip, CompositeAudioClip
from moviepy.audio.fx.all import audio_fadeout
from proglog import ProgressBarLogger
from src.utils import load_config, get_president_assets, validate_system_requirements
from src.logic import create_video_segment

# Importación de módulos nuevos con captura de errores
guionista_error = None
try:
    import src.guionista as guionista
except Exception as e:
    guionista = None
    guionista_error = str(e)

locutor_error = None
try:
    import src.locutor as locutor
except Exception as e:
    locutor = None
    locutor_error = str(e)

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

# ---------------------------------------------------------
# VALIDACIÓN DE ARRANQUE (CONTROL DE DAÑOS)
# ---------------------------------------------------------
if CFG:
    startup_errors = validate_system_requirements(CFG)
    if startup_errors:
        for err in startup_errors:
            st.error(err)
        st.warning("⚠️ El sistema puede no funcionar correctamente debido a los errores anteriores.")

if guionista_error:
    st.error(f"❌ ERROR CRÍTICO al cargar el módulo 'guionista': {guionista_error}")
if locutor_error:
    st.error(f"❌ ERROR CRÍTICO al cargar el módulo 'locutor': {locutor_error}")


st.title("🏭 Fábrica de TikToks")

# ---------------------------------------------------------
# ---------------------------------------------------------
# FUNCIÓN CORE DE GENERACIÓN DE VIDEO (REUTILIZABLE)
# ---------------------------------------------------------

def format_seconds(seconds):
    """Formatea segundos a 'Xm Ys' si >60, o 'Xs' si no."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"

def generate_video_pipeline(src_folder, output_folder, config, status_container, log_callback, engine_version="v1_estable", sound_enabled=True):
    """
    Función central que orquesta la creación del video a partir de una carpeta de audios.
    Devuelve la ruta del video final generado.
    """
    # 1. Recopilar audios
    if not os.path.exists(src_folder):
        raise FileNotFoundError(f"No existe la carpeta fuente: {src_folder}")
        
    local_audios = glob.glob(os.path.join(src_folder, "*.mp3"))
    if not local_audios:
        raise ValueError("No se encontraron archivos .mp3 en la carpeta indicada.")
        
    # 2. Ordenar (Intro primero, luego resto reverso numérico)
    intro_file = None
    body_files = []
    
    for aud in local_audios:
        if "intro" in os.path.basename(aud).lower():
            intro_file = aud
        else:
            body_files.append(aud)
            
    # Ordenar numéricamente inverso (5, 4, 3, 2, 1)
    # Asumimos que empiezan con número N_Name.mp3
    try:
        body_files.sort(key=lambda x: int(os.path.basename(x).split('_')[0]), reverse=True)
    except:
        # Fallback por nombre si no cumple formato
        body_files.sort(key=lambda x: os.path.basename(x), reverse=True)
    
    final_audio_order = []
    if intro_file: final_audio_order.append(intro_file)
    final_audio_order.extend(body_files)
    
    clips = []
    token = False
    
    # 3. Generar segmentos
    revealed_presidents = []
    for aud in final_audio_order:
        try:
            name = os.path.splitext(os.path.basename(aud))[0]
            # Extraer info
            try:
                parts = name.split('_')
                if "intro" in name.lower():
                    puesto = 1 
                    presi = "Intro"
                elif len(parts) >= 2:
                    puesto = int(parts[0])
                    # Reconstruir nombre si tenía espacios o guiones
                    presi = "_".join(parts[1:]) 
                else:
                    puesto = 0
                    presi = name
            except:
                puesto = 0
                presi = name

            log_callback(f"⚙️ Procesando segmento: **{name}** (Personaje: {presi})")

            seg, token = create_video_segment(aud, puesto, presi, config, token, log_callback=log_callback, engine_version=engine_version, revealed_presidents=revealed_presidents)
            # Agregar a lista de ya revelados para lógica de siluetas
            revealed_presidents.append(presi)
            if seg: clips.append(seg)
        except Exception as e:
            log_callback(f"❌ Error creando segmento {os.path.basename(aud)}: {e}")
            print(f"Error detallado: {e}")

    if not clips:
        raise RuntimeError("No se generaron clips válidos.")

    # 4. Renderizado Final
    status_container.write(f"   ↳ ⚙️ Renderizando Montaje Final...")
    
    timer_ph = st.empty()
    render_bar = st.progress(0)
    logger = StreamlitLogger(render_bar, timer_ph)
    
    # Transiciones de Audio
    path_pagina = os.path.join(config["paths"]["resources_library"], "pagina.mp3")
    sound_effect = None
    if os.path.exists(path_pagina):
        try:
            sound_effect = AudioFileClip(path_pagina)
        except: pass
    
    final = concatenate_videoclips(clips, method="compose")
    
    if len(clips) > 1 and sound_effect:
        sfx_clips = []
        current_time = 0
        for i in range(len(clips) - 1):
            current_time += clips[i].duration
            start_t = max(0, current_time - 0.2)
            sfx_clips.append(sound_effect.set_start(start_t))
        
        if sfx_clips:
            global_audio = CompositeAudioClip([final.audio] + sfx_clips)
            global_audio = global_audio.set_duration(final.duration)
            final = final.set_audio(global_audio)
            
    if final.audio:
        final_audio = final.audio.set_duration(final.duration)
        # ELIMINADO FADEOUT GLOBAL DE 1s POR PETICIÓN DE USUARIO
        # final_audio = final_audio.fx(audio_fadeout, 1.0)
        final = final.set_audio(final_audio)

    # NAMING CONVENTION (V2 - Sequential)
    try:
        current_mp4s = [f for f in os.listdir(output_folder) if f.endswith(".mp4") and "TikTok_AUTO_" in f]
        count = len(current_mp4s)
        out_name = f"TikTok_AUTO_{count + 1}.mp4"
    except:
        timestamp = datetime.now().strftime("%H%M%S")
        out_name = f"TikTok_AUTO_{timestamp}.mp4"

    # Fallback de Seguridad (Si existe, apendice Timestamp)
    if os.path.exists(os.path.join(output_folder, out_name)):
        timestamp = datetime.now().strftime("%H%M%S")
        name_no_ext = os.path.splitext(out_name)[0]
        out_name = f"{name_no_ext}_{timestamp}.mp4"
        
    out_path = os.path.join(output_folder, out_name)
    
    sets = config["video_settings"]
    
    # Resize final para seguridad (pares)
    safe_w, safe_h = tuple(sets["resolution"])
    if safe_w % 2 != 0: safe_w -= 1
    if safe_h % 2 != 0: safe_h -= 1
    
    if final.w != safe_w or final.h != safe_h:
        final = final.resize(newsize=(safe_w, safe_h))

    final.write_videofile(
        out_path, 
        fps=sets["fps"], 
        codec='libx264', 
        audio_codec='aac', 
        logger=logger, 
        threads=8, 
        preset='ultrafast',
        remove_temp=True, # Limpieza temporales ffmpeg
        ffmpeg_params=['-pix_fmt', 'yuv420p']
    )
    
    render_bar.empty()
    timer_ph.empty()
    
    return out_path
 



# ---------------------------------------------------------
# INTERFAZ PRINCIPAL
# ---------------------------------------------------------

# SIDEBAR CONFIGURATION (Optimización de Espacio)
with st.sidebar:
    st.header("⚙️ Configuración Global")
    
    res_options = {
        "1080p (Producción) - Lento": [1080, 1920],
        "720p (HD) - Medio": [720, 1280],
        "480p (Borrador) - Rápido": [480, 854],
        "240p (Test Lógica) - Ultra Rápido": [240, 426]
    }
    
    selected_res_label = st.radio(
        "Calidad de Renderizado",
        options=list(res_options.keys()),
        index=0
    )
    
    st.divider()
    
    engine_version = st.selectbox(
        "Motor de Animación",
        ["v2_estable", "v1_estable"],
        index=0
    )
    
    st.divider()
    
    sound_on = st.checkbox("🔔 Sonido al Finalizar", value=True)

# SELECTOR DE MODO (Por defecto Automático)
# ---------------------------------------------------------
mode = st.radio("Modo de Generación", ["Automático (IA)", "Manual (Carpetas)"], index=0, horizontal=True) # Index 0 es Auto ahora

st.markdown("---")


if mode == "Manual (Carpetas)":
    # ---------------------------------------------------------
    # MODO MANUAL
    # ---------------------------------------------------------
    num_videos = st.number_input("Cantidad de videos:", 1, 10, 1)
    uploads = {}
    cols = st.columns(num_videos)
    for i in range(num_videos):
        with cols[i]:
            st.subheader(f"Video {i+1}")
            files = st.file_uploader(f"Audios V{i+1}", accept_multiple_files=True, key=f"up_{i}")
            if files: uploads[i] = files

    col_btn1, col_btn2, _, _ = st.columns([1, 1, 1, 5])
    with col_btn1:
        btn_start = st.button("🚀 GENERAR (MANUAL)")
    with col_btn2:
        if st.button("⛔ CANCELAR"):
            st.stop()
            
    if btn_start:
        target_res = res_options[selected_res_label]
        w_safe = target_res[0] if target_res[0] % 2 == 0 else target_res[0] - 1
        h_safe = target_res[1] if target_res[1] % 2 == 0 else target_res[1] - 1
        CFG["video_settings"]["resolution"] = [w_safe, h_safe]
        
        temp_dir = CFG["paths"]["temp_folder"]
        if os.path.exists(temp_dir): 
            try: shutil.rmtree(temp_dir)
            except: pass
        os.makedirs(temp_dir, exist_ok=True)
        
        with st.status("🏭 Procesando Manual...", expanded=True) as status:
             # Pre-procesar uploads para convertirlos en carpetas físicas
             total = len(uploads)
             progress = st.progress(0)
             logs = []
             def log_manual(msg): logs.append(msg)
             
             for idx, (vid_id, file_list) in enumerate(uploads.items()):
                 status.write(f"🎞️ Video {vid_id+1}/{total}")
                 path_lote = os.path.join(temp_dir, f"v{vid_id}")
                 os.makedirs(path_lote, exist_ok=True)
                 for f in file_list:
                     with open(os.path.join(path_lote, f.name), "wb") as w: w.write(f.getbuffer())
                     
                 # LLAMADA AL NUEVO PIPELINE CON LA CARPETA
                 try:
                     out_video = generate_video_pipeline(
                         path_lote, 
                         CFG["paths"]["output_folder"], 
                         CFG, 
                         status, 
                         log_manual, 
                         engine_version
                     )
                     status.write(f"✅ Video {vid_id+1} OK: {os.path.basename(out_video)}")
                 except Exception as e:
                     status.error(f"Error en video {vid_id+1}: {e}")
                 
                 progress.progress((idx+1)/total)
                 
             if sound_on: 
                 try: winsound.MessageBeep(winsound.MB_ICONASTERISK)
                 except: pass
             status.update(label="✨ Completado", state="complete", expanded=False)
             
             with st.expander("Logs"):
                 for l in logs: st.write(l)


elif mode == "Automático (IA)":
    # ---------------------------------------------------------
    # MODO AUTOMÁTICO
    # ---------------------------------------------------------
    st.markdown("### ✨ Automatización con Inteligencia Artificial")
    st.info("Este modo genera guiones y audios automáticamente usando Gemini y Minimax.")
    
    # 1. CONFIGURACIÓN DE LOTE (NUEVA UI COMPACTA)
    st.markdown("### 🏭 Fábrica de Vídeos (Batch Mode)")

    # Fila de configuración principal
    c1, c2, c3 = st.columns([1, 2, 1])
    
    with c1:
        cantidad = st.number_input("Cantidad de videos:", min_value=1, max_value=10, value=1, step=1)
    
    with c2:
        st.write("") # Spacer
        st.write("") 
        use_creative_mode = st.checkbox("✨ Activar Modo Creativo", value=False, help="Hooks y CTAs dinámicos variados por IA.")
        
    with c3:
        st.write("") # Spacer
        if st.button("📋 Ver Whitelist"):
            assets = guionista.get_available_assets()
            st.toast(f"✅ Whitelist: {len(assets.split(','))} personajes detectados.")
            # Opcional: Mostrar en un expander si se quiere
            # with st.expander("Ver lista"): st.write(assets)
    
    st.divider()
    
    # Inputs Dinámicos en Grid (2 columnas) para ahorrar espacio
    queue_inputs = []
    st.write("⬇️ **Configura los temas de los videos:** (Deja vacío para tema aleatorio)")
    
    grid_cols = st.columns(2)
    for i in range(cantidad):
        col_idx = i % 2
        with grid_cols[col_idx]:
            topic = st.text_input(f"🎬 Video {i+1}: Título/Tema", key=f"topic_{i}", placeholder="Ej: Curiosidades de Lincoln")
            queue_inputs.append(topic)

    # Botón de Acción
    if st.button("✨ INICIAR FÁBRICA DE VIDEOS"):
        # Configurar resolución global una sola vez
        target_res = res_options[selected_res_label]
        w_safe = target_res[0] if target_res[0] % 2 == 0 else target_res[0] - 1
        h_safe = target_res[1] if target_res[1] % 2 == 0 else target_res[1] - 1
        CFG["video_settings"]["resolution"] = [w_safe, h_safe]
        
        logs_auto = []
        def log_cb(msg): logs_auto.append(msg)
        
        # CONTENEDOR PRINCIPAL DE ESTADO
        total_jobs = len(queue_inputs)
        
        with st.status("🏭 Arrancando Fábrica...", expanded=True) as status:
            
            for idx, user_topic in enumerate(queue_inputs):
                # Limpieza y Lógica de Tópico
                current_topic = user_topic.strip() if user_topic and user_topic.strip() else None
                topic_display = current_topic if current_topic else "🎲 Tema Aleatorio (Sorpréndeme)"
                
                st.divider()
                st.markdown(f"### ▶️ Procesando Video {idx+1}/{total_jobs} | {topic_display}")
                status.update(label=f"Trabajando en {idx+1}/{total_jobs}: {topic_display}...", state="running")
                
                try:
                    # --- DASHBOARD DE PROCESO (3 COLUMNAS PARALELAS) ---
                    col_script, col_audio, col_edit = st.columns(3)
                    
                    with col_script:
                        st_script_status = st.empty()
                        st_script_status.info("⏳ 1. Guion: En espera...")
                    
                    with col_audio:
                        st_audio_status = st.empty()
                        st_audio_status.info("⏳ 2. Audio: En espera...")
                        
                    with col_edit:
                        st_edit_status = st.empty()
                        st_edit_status.info("⏳ 3. Edición: En espera...")

                    # --- PASO 1: GUIONISTA ---
                    st_script_status.info("🔄 Generando Guion...")
                    t0 = time.time()
                    
                    script_data = guionista.generate_script(current_topic, creative_mode=use_creative_mode)
                    txt_output = guionista.save_scripts_to_txt(script_data)
                    
                    t1 = time.time()
                    st_script_status.success(f"✅ Guion OK ({format_seconds(t1-t0)})")

                    # --- PASO 2: LOCUTOR ---
                    st_audio_status.info("🔄 Clonando Voz...")
                    t2 = time.time()
                    
                    resources_base = CFG["paths"]["resources_library"]
                    audio_output_folder = locutor.generate_audios_from_text_folder(txt_output, resources_base)
                    
                    if not audio_output_folder:
                        raise Exception("No se generaron audios. Abortando este video.")
                    
                    t3 = time.time()
                    st_audio_status.success(f"✅ Audios OK ({format_seconds(t3-t2)})")
                    
                    # --- PASO 3: EDITOR DE VIDEO ---
                    st_edit_status.info("🔄 Renderizando...")
                    t4 = time.time()
                    
                    final_video_path = generate_video_pipeline(
                        audio_output_folder,
                        CFG["paths"]["output_folder"],
                        CFG,
                        status,  # Status container global para logs de ffmpeg si fuera necesario
                        log_cb,
                        engine_version
                    )
                    
                    t5 = time.time()
                    st_edit_status.success(f"✅ Video OK ({format_seconds(t5-t4)})")
                    
                    # --- RESULTADO FINAL (Layout Optimizado) ---
                    st.divider()
                    # Ratio 1:2 para que el video sea más pequeño (ocupa 1/3 de ancho)
                    col_video, col_details = st.columns([1, 2])
                    
                    video_name = os.path.basename(final_video_path)
                    
                    with col_video:
                        st.subheader("📺 Video")
                        st.video(final_video_path)
                    
                    with col_details:
                        st.subheader("📊 Detalles")
                        st.success(f"🎉 ¡VIDEO COMPLETADO!")
                        st.text_input("Archivo:", value=video_name, disabled=True, key=f"v_name_{idx}")
                        st.write(f"⏱️ Tiempo Total: {format_seconds(t5-t0)}")
                        st.write(f"📂 Ruta Local: `{final_video_path}`")
                        st.info("ℹ️ El archivo ya se guardó automáticamente.")
                        
                        # Botón único de abrir carpeta
                        if st.button("📂 Abrir Carpeta de Salida", key=f"btn_open_{idx}"):
                            # Intento de abrir explorador (Windows)
                            try:
                                folder_p = os.path.dirname(final_video_path)
                                os.startfile(folder_p)
                            except:
                                st.warning("No se pudo abrir la carpeta automáticamente.")

                    
                    # Limpieza Automática
                    try:
                        if os.path.exists(txt_output): shutil.rmtree(txt_output)
                        if os.path.exists(audio_output_folder): shutil.rmtree(audio_output_folder)
                        for f in os.listdir():
                            if f.endswith(".mp3") and "TEMP" in f:
                                try: os.remove(f)
                                except: pass
                    except: pass
                    
                except Exception as e:
                    st.error(f"❌ FALLÓ el video '{topic_display}'. Motivo: {e}")
                    st.warning("⚠️ Saltando al siguiente video de la cola...")
                    continue # VITAL: No parar la fábrica
                
            status.update(label="✨ ¡Fábrica Finalizó la Cola!", state="complete", expanded=False)
            
            if sound_on: 
                try: winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except: pass
        
        # BOTÓN DE REINICIO
        st.markdown("---")
        col_reset, _ = st.columns([1, 2])
        with col_reset:
            if st.button("🔄 REINICIAR / GENERAR NUEVO LOTE", type="primary"):
                st.rerun()
                
        with st.expander("📝 Detalle de Logs Globales"):
            for l in logs_auto: st.write(l)