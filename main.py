import streamlit as st
import os
import shutil
import time
from datetime import datetime
import winsound # For audio notification (Windows)
import sys
import PIL.Image
import glob
import traceback
from dotenv import load_dotenv
from src.health_check import check_api_health

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
from proglog import ProgressBarLogger
from src.utils import load_config, validate_system_requirements
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

try:
    from src.video_remover import VideoRemover as CopyrightCleaner
except Exception as e:
    CopyrightCleaner = None
    cleaner_error = str(e)
else:
    cleaner_error = None



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

# Auto-limpieza de temp_work (archivos > N días). Throttle por marker file
# para no repetir en cada rerun de Streamlit.
try:
    from src.temp_cleanup import cleanup_temp_files
    _cleanup_cfg = CFG.get("temp_cleanup", {}) if CFG else {}
    _n, _freed = cleanup_temp_files(
        CFG["paths"]["temp_folder"],
        max_age_days=_cleanup_cfg.get("max_age_days", 3),
        throttle_hours=_cleanup_cfg.get("throttle_hours", 12),
    )
    if _n > 0:
        print(f"[temp_cleanup] temp_work: {_n} archivos / {_freed / 1024 / 1024:.1f} MB liberados")
except Exception as _e:
    print(f"[temp_cleanup] Auto-limpieza falló: {_e}")

st.set_page_config(page_title="TikTok Creator Reward Auto", layout="wide")

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
if cleaner_error:
    st.error(f"❌ ERROR al cargar el módulo 'CopyrightCleaner': {cleaner_error}")



st.title("🏭 TikTok Creator Reward Auto")

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

def generate_video_pipeline(src_folder, output_folder, config, status_container, log_callback, engine_version="v1_estable"):
    """
    Función central que orquesta la creación del video a partir de una carpeta de audios.
    Devuelve la ruta del video final generado.
    """
    if not os.path.exists(src_folder):
        raise FileNotFoundError(f"No existe la carpeta fuente: {src_folder}")

    # Cada nicho guarda en su subcarpeta dentro de VIDEOS_TERMINADOS
    output_folder = os.path.join(output_folder, "PRESIDENTES")
    os.makedirs(output_folder, exist_ok=True)

    local_audios = glob.glob(os.path.join(src_folder, "*.mp3"))
    if not local_audios:
        raise ValueError("No se encontraron archivos .mp3 en la carpeta indicada.")

    intro_file = None
    body_files = []
    for aud in local_audios:
        if "intro" in os.path.basename(aud).lower():
            intro_file = aud
        else:
            body_files.append(aud)

    try:
        body_files.sort(key=lambda x: int(os.path.basename(x).split('_')[0]), reverse=True)
    except:
        body_files.sort(key=lambda x: os.path.basename(x), reverse=True)

    final_audio_order = []
    if intro_file: final_audio_order.append(intro_file)
    final_audio_order.extend(body_files)

    clips = []
    token = False
    revealed_presidents = []

    for aud in final_audio_order:
        try:
            name = os.path.splitext(os.path.basename(aud))[0]
            try:
                parts = name.split('_')
                if "intro" in name.lower():
                    puesto = 1
                    presi = "Intro"
                elif len(parts) >= 2:
                    puesto = int(parts[0])
                    presi = "_".join(parts[1:])
                else:
                    puesto = 0
                    presi = name
            except:
                puesto = 0
                presi = name

            log_callback(f"⚙️ Procesando segmento: **{name}** (Personaje: {presi})")

            seg, token, _ = create_video_segment(
                aud, puesto, presi, config, token,
                log_callback=log_callback,
                engine_version=engine_version,
                revealed_presidents=revealed_presidents,
            )

            revealed_presidents.append(presi)
            if seg: clips.append(seg)
        except Exception as e:
            log_callback(f"❌ Error creando segmento {os.path.basename(aud)}: {e}")
            print(f"Error detallado: {e}")

    if not clips:
        raise RuntimeError("No se generaron clips válidos.")

    status_container.write(f"   ↳ ⚙️ Renderizando Montaje Final...")

    timer_ph = st.empty()
    render_bar = st.progress(0)
    logger = StreamlitLogger(render_bar, timer_ph)

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
# Orden: 1) Estrategia (siempre, primero) → 2) Resolución → 3) Bloques específicos del nicho
with st.sidebar:
    # --- ESTRATEGIA & NICHO (siempre visible, PRIMERO) ---
    with st.expander("🎯 Estrategia & Nicho", expanded=True):
        app_mode_label = st.radio(
            "Nicho",
            ["🏛️ Presidentes Top 5", "📊 Pronósticos Diarios", "🛡️ Quitar Copy"],
            index=0,
            label_visibility="collapsed"
        )
        sound_on = st.checkbox("🔔 Sonido al Finalizar", value=True)

    if "Quitar Copy" in app_mode_label:
        CFG["app_mode"] = "COPYRIGHT_CLEANER"
    elif "Pronósticos" in app_mode_label:
        CFG["app_mode"] = "PRONOSTICOS_DIARIOS"
    else:
        CFG["app_mode"] = "PRESIDENTS_TOP5"

    is_presidents = (CFG["app_mode"] == "PRESIDENTS_TOP5")
    is_pronosticos = (CFG["app_mode"] == "PRONOSTICOS_DIARIOS")
    is_copyright = (CFG["app_mode"] == "COPYRIGHT_CLEANER")

    st.caption(f"Modo Activo: {CFG['app_mode']}")

    # --- VISUALES (Resolución siempre, Motor solo Presidentes) ---
    with st.expander("🎥 Configuración de Video", expanded=True):
        res_options = {
            "1080p (Lento)": [1080, 1920],
            "720p (Medio)": [720, 1280],
            "480p (Rápido)": [480, 854],
            "240p (Ultra Rápido)": [240, 426]
        }
        selected_res_label = st.selectbox("Calidad", options=list(res_options.keys()), index=0)

        if is_presidents:
            st.markdown("**Motor Animación**")
            engine_version = st.selectbox("Motor", ["v2_estable", "v1_estable"], index=0, label_visibility="collapsed")
        else:
            engine_version = "v2_estable"  # default no usado fuera de Presidentes

    # ─────────────────────────────────────────────────────────────────
    # Bloques específicos de PRESIDENTES (subtítulos karaoke + hook box).
    # Pronósticos tiene sus propios controles en el área principal.
    # Copyright Cleaner gestiona internamente sus subtítulos/hook.
    # ─────────────────────────────────────────────────────────────────
    if not is_presidents:
        # Defaults para que las variables existan aunque los expanders no se rendericen.
        # NO se usan fuera del flow Presidentes pero las dejo para evitar NameError
        # si en el futuro algún flow compartido los referenciara.
        subs_enabled = False
        subs_highlight_color = "#BB0808"
        subs_text_color = "#FFFFFF"
        subs_stroke_color = "#000000"
        subs_stroke_width = 3
        subs_case = "UPPERCASE"
        subs_font_scale = 0.040
        subs_max_words = 4
        subs_y_position = 0.62
        hook_enabled = False
        hook_duration = 5.0
        hook_animation = "swipe_left"
        hook_y_position = 0.33
        hook_shadow_color = "#BB0808"
        hook_box_color = "#FFFFFF"
        hook_text_color = "#0B0B0B"
        hook_font_scale = 0.020

    if is_presidents:
        # --- PRESETS (guardar/cargar configs en Redis) ---
        # Lista de claves de session_state que viajan en cada preset
        _PRESET_KEYS = [
            "subs_enabled", "subs_highlight_color", "subs_text_color", "subs_stroke_color",
            "subs_stroke_width", "subs_case", "subs_font_scale", "subs_max_words", "subs_y_position",
            "hook_enabled", "hook_duration", "hook_animation", "hook_y_position",
            "hook_shadow_color", "hook_box_color", "hook_text_color", "hook_font_scale",
        ]
        _DEFAULT_PRESET_KEY = "__default"

        # Cargar preset __default automáticamente la PRIMERA vez en cada sesión
        # (solo afecta a session_state — los widgets lo recogen al renderizar)
        if "_default_preset_attempted" not in st.session_state:
            st.session_state._default_preset_attempted = True
            try:
                from src.configs_store import is_available as _cfg_av, load_config as _load_cfg
                if _cfg_av():
                    _autoloaded = _load_cfg(_DEFAULT_PRESET_KEY)
                    if _autoloaded:
                        for _k, _v in _autoloaded.items():
                            if _k in _PRESET_KEYS:
                                st.session_state[_k] = _v
            except Exception as _e:
                print(f"[preset autoload] {_e}")

        with st.expander("💾 Presets de configuración", expanded=False):
            try:
                from src.configs_store import (
                    is_available as _cfg_available,
                    list_configs, save_config, load_config, delete_config,
                )
                _redis_ok = _cfg_available()
            except Exception as _e:
                _redis_ok = False
                st.warning(f"Redis no disponible: {_e}")

            if not _redis_ok:
                st.info("Define `UPSTASH_REDIS_REST_URL` y `UPSTASH_REDIS_REST_TOKEN` en `.env` para guardar presets.")
            else:
                saved_names = list_configs()
                # __default lo mostramos siempre arriba con la estrella
                visible_names = [n for n in saved_names if n != _DEFAULT_PRESET_KEY]
                has_default = _DEFAULT_PRESET_KEY in saved_names
                if has_default:
                    st.caption("⭐ Hay un preset por defecto guardado — se carga automáticamente al abrir la app.")
                else:
                    st.caption("ℹ️ No hay preset por defecto. Usa el botón ⭐ para guardar la config actual como default.")
                st.caption("🔄 Auto-guardado activo: cualquier cambio se persiste como preset por defecto.")

                # Botón rápido: guardar como default
                if st.button("⭐ Guardar config actual como DEFAULT (auto-load al abrir)",
                             use_container_width=True, key="preset_save_default_btn"):
                    current_cfg = {k: st.session_state[k] for k in _PRESET_KEYS if k in st.session_state}
                    if save_config(_DEFAULT_PRESET_KEY, current_cfg):
                        st.toast("⭐ Default guardado — se cargará la próxima vez que abras la app")
                        st.rerun()
                    else:
                        st.error("Error guardando default.")

                st.divider()

                # Cargar otros presets
                load_col1, load_col2 = st.columns([3, 1])
                with load_col1:
                    selected_preset = st.selectbox(
                        "Cargar preset",
                        ["(ninguno)"] + visible_names,
                        index=0,
                        key="preset_load_select",
                    )
                with load_col2:
                    st.write("")
                    if st.button("📂 Cargar", use_container_width=True, key="preset_load_btn"):
                        if selected_preset != "(ninguno)":
                            cfg = load_config(selected_preset)
                            if cfg:
                                for k, v in cfg.items():
                                    if k in _PRESET_KEYS:
                                        st.session_state[k] = v
                                st.toast(f"✅ Preset '{selected_preset}' cargado")
                                st.rerun()
                            else:
                                st.error("No se pudo cargar el preset.")

                # Guardar nuevo preset / borrar seleccionado
                save_col1, save_col2, save_col3 = st.columns([3, 1, 1])
                with save_col1:
                    new_preset_name = st.text_input(
                        "Nombre del nuevo preset",
                        placeholder="ej: rojo-uppercase-top5",
                        key="preset_save_name",
                    )
                with save_col2:
                    st.write("")
                    if st.button("💾 Guardar", use_container_width=True, key="preset_save_btn"):
                        name = new_preset_name.strip()
                        if not name:
                            st.warning("Pon un nombre para el preset.")
                        elif name.startswith("__"):
                            st.warning("Los nombres que empiezan por '__' están reservados.")
                        else:
                            current_cfg = {k: st.session_state[k] for k in _PRESET_KEYS if k in st.session_state}
                            if save_config(name, current_cfg):
                                st.toast(f"✅ Preset '{name}' guardado")
                                st.rerun()
                            else:
                                st.error("Error guardando el preset.")
                with save_col3:
                    st.write("")
                    if st.button("🗑️ Borrar", use_container_width=True, key="preset_delete_btn",
                                 disabled=(selected_preset == "(ninguno)")):
                        if delete_config(selected_preset):
                            st.toast(f"🗑️ Preset '{selected_preset}' borrado")
                            st.rerun()

        # --- SUBTÍTULOS AUTOMÁTICOS (solo Presidentes) ---
        with st.expander("📝 Subtítulos automáticos (karaoke)", expanded=False):
            subs_enabled = st.checkbox(
                "Añadir subtítulos al vídeo final",
                value=True,
                key="subs_enabled",
                help="Transcribe el audio con Whisper local (gratis) y superpone subtítulos palabra-a-palabra estilo TikTok.",
            )

            if subs_enabled:
                # Preset rápido para el color de highlight (default: rojo)
                if "subs_highlight_color" not in st.session_state:
                    st.session_state.subs_highlight_color = "#BB0808"
                preset_col1, preset_col2, preset_col3 = st.columns([1, 1, 2])
                with preset_col1:
                    if st.button("🔵 Azul", help="#1E01C4", use_container_width=True, key="subs_preset_blue"):
                        st.session_state.subs_highlight_color = "#1E01C4"
                with preset_col2:
                    if st.button("🔴 Rojo", help="#BB0808", use_container_width=True, key="subs_preset_red"):
                        st.session_state.subs_highlight_color = "#BB0808"
                with preset_col3:
                    st.caption("Presets rápidos de color highlight")

                # Colores
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    subs_highlight_color = st.color_picker(
                        "🎨 Color highlight (pill)",
                        key="subs_highlight_color",
                        help="Color de la píldora detrás de la palabra actual. Presets: 🔵 #1E01C4 / 🔴 #BB0808",
                    )
                    subs_text_color = st.color_picker("Color del texto", value="#FFFFFF", key="subs_text_color")
                with col_c2:
                    subs_stroke_color = st.color_picker("Color del borde", value="#000000", key="subs_stroke_color")
                    subs_stroke_width = st.slider("Grosor del borde", 0, 6, 3, key="subs_stroke_width")

                subs_case = st.selectbox(
                    "Formato del texto",
                    ["UPPERCASE", "lowercase", "Title Case", "original"],
                    index=0,
                    key="subs_case",
                )

                subs_font_scale = st.slider(
                    "Tamaño de fuente (relativo al alto del vídeo)",
                    min_value=0.03, max_value=0.08, value=0.040, step=0.005,
                    key="subs_font_scale",
                )

                subs_max_words = st.slider("Palabras por bloque (chunk)", 1, 5, 4, key="subs_max_words")

                # Posición Y (dentro de zona segura TikTok)
                subs_y_position = st.slider(
                    "Posición vertical (% del alto del vídeo)",
                    min_value=0.15, max_value=0.75, value=0.62, step=0.01,
                    key="subs_y_position",
                    help="0.40 = bajo el hook (muy arriba) · 0.62 = recomendado (margen amplio bajo el hook) · 0.75 = casi abajo. "
                         "Rango limitado a la zona segura que evita los iconos, descripción y sonido.",
                )

                # Preview
                try:
                    from src.subtitles import render_preview_image, DEFAULT_STYLE

                    preview_style = {
                        **DEFAULT_STYLE,
                        "highlight_color": subs_highlight_color,
                        "text_color": subs_text_color,
                        "stroke_color": subs_stroke_color,
                        "stroke_width": subs_stroke_width,
                        "case_mode": subs_case,
                        "font_scale": subs_font_scale,
                        "max_words_per_chunk": subs_max_words,
                        "y_position_pct": subs_y_position,
                    }

                    preview_img = render_preview_image(
                        preview_style,
                        sample_text="MORE FRAGILE THAN EVER",
                        highlight_word_index=2,
                        video_size=(1080, 1920),
                    )
                    st.caption("Vista previa del estilo:")
                    st.image(preview_img, use_container_width=True)
                except Exception as e:
                    st.warning(f"⚠️ Preview no disponible: {e}")
            else:
                subs_highlight_color = "#BB0808"
                subs_text_color = "#FFFFFF"
                subs_stroke_color = "#000000"
                subs_stroke_width = 3
                subs_case = "UPPERCASE"
                subs_font_scale = 0.040
                subs_max_words = 4
                subs_y_position = 0.62

        # --- GANCHO DE TEXTO (HOOK BOX) — solo Presidentes ---
        with st.expander("🎣 Gancho de texto (hook box)", expanded=False):
            hook_enabled = st.checkbox(
                "Añadir gancho de texto al inicio del vídeo",
                value=True,
                key="hook_enabled",
                help="Caja con el título del vídeo estilo noticia, centrada sobre el clip.",
            )

            if hook_enabled:
                hook_duration = st.slider("Duración (segundos)", 2.0, 10.0, 5.0, 0.5, key="hook_duration")

                hook_animation = st.selectbox(
                    "Animación de salida/entrada",
                    ["swipe_left", "slide_in_out", "news_flash", "fade"],
                    index=0,
                    key="hook_animation",
                    format_func=lambda x: {
                        "swipe_left": "Swipe left (sale hacia la izquierda)",
                        "slide_in_out": "Slide in/out (entra y sale por la izquierda)",
                        "news_flash": "News flash (pop + vibración + swipe)",
                        "fade": "Fade (fundido entrada/salida)",
                    }[x],
                )

                hook_y_position = st.slider(
                    "Posición vertical (% del alto)",
                    min_value=0.20, max_value=0.75, value=0.33, step=0.01,
                    key="hook_y_position",
                    help="0.33 = recomendado (arriba del subtítulo, sin invadir UI TikTok). Respeta zona segura.",
                )

                # Presets de color de sombra (default: rojo)
                if "hook_shadow_color" not in st.session_state:
                    st.session_state.hook_shadow_color = "#BB0808"
                hp1, hp2, hp3 = st.columns([1, 1, 2])
                with hp1:
                    if st.button("🔵 Azul", help="#1E01C4", use_container_width=True, key="hook_preset_blue"):
                        st.session_state.hook_shadow_color = "#1E01C4"
                with hp2:
                    if st.button("🔴 Rojo", help="#BB0808", use_container_width=True, key="hook_preset_red"):
                        st.session_state.hook_shadow_color = "#BB0808"
                with hp3:
                    st.caption("Presets de sombra del hook")

                hc1, hc2 = st.columns(2)
                with hc1:
                    hook_shadow_color = st.color_picker(
                        "Color sombra (3D)",
                        key="hook_shadow_color",
                    )
                    hook_box_color = st.color_picker("Color de la caja", value="#FFFFFF", key="hook_box_color")
                with hc2:
                    hook_text_color = st.color_picker("Color del texto", value="#0B0B0B", key="hook_text_color")
                    hook_font_scale = st.slider("Tamaño de fuente", 0.014, 0.040, 0.020, 0.002, key="hook_font_scale")

                # Preview
                try:
                    from src.text_hook import render_preview_image as _hook_preview, DEFAULT_HOOK_STYLE as _HS

                    hook_style_preview = {
                        **_HS,
                        "duration": hook_duration,
                        "y_position_pct": hook_y_position,
                        "shadow_color": hook_shadow_color,
                        "box_color": hook_box_color,
                        "text_color": hook_text_color,
                        "font_scale": hook_font_scale,
                        "animation": hook_animation,
                    }

                    preview_hook = _hook_preview(
                        "Ranked By Damage Done",
                        hook_style_preview,
                        video_size=(1080, 1920),
                    )
                    st.caption("Vista previa (texto de muestra; en el render real la IA genera un teaser de 3-6 palabras según el ángulo del vídeo):")
                    st.image(preview_hook, use_container_width=True)
                except Exception as e:
                    st.warning(f"⚠️ Preview no disponible: {e}")
            else:
                hook_duration = 5.0
                hook_animation = "swipe_left"
                hook_y_position = 0.33
                hook_shadow_color = "#BB0808"
                hook_box_color = "#FFFFFF"
                hook_text_color = "#0B0B0B"
                hook_font_scale = 0.020

        # --- AUTO-GUARDADO de la configuración en Redis (preset __default) ---
        # Cualquier cambio en los widgets de arriba (subtítulos, hook, presets)
        # se persiste como preset por defecto. La próxima sesión lo recarga
        # automáticamente. Solo escribe a Redis cuando el snapshot cambia.
        try:
            from src.configs_store import (
                is_available as _autosave_av,
                save_config as _autosave_save,
            )
            if _autosave_av():
                _autosave_snap = {
                    k: st.session_state[k]
                    for k in _PRESET_KEYS
                    if k in st.session_state
                }
                _autosave_key = repr(sorted(_autosave_snap.items()))
                if st.session_state.get("_autosave_last_key") != _autosave_key:
                    if _autosave_save(_DEFAULT_PRESET_KEY, _autosave_snap):
                        st.session_state._autosave_last_key = _autosave_key
                        st.session_state._autosave_done_once = True
        except Exception as _autosave_err:
            print(f"[autosave preset] {_autosave_err}")

# ---------------------------------------------------------
# INTERFAZ COPYRIGHT CLEANER (MODO EXCLUSIVO)
# ---------------------------------------------------------
if CFG["app_mode"] == "COPYRIGHT_CLEANER":
    st.header("🛡️ Master Copyright Cleaner")
    st.info("Sube un video con subtítulos originales. El sistema detectará automáticamente su posición, los ocultará con una máscara profesional y pondrá nuevos subtítulos con estilo viral.")
    
    clean_upload = st.file_uploader("📂 Subir Video para Limpiar (MP4/MOV)", type=["mp4", "mov"])
    
    if clean_upload:
        col1, col2 = st.columns([0.5, 1.5])
        with col1:
            st.subheader("📺 Original")
            st.video(clean_upload)
            
        with col2:
            st.subheader("⚙️ Opciones")
            clean_mode = st.radio("🛡️ Modo de Limpieza", ["Subtítulos Virales", "Camuflaje Geométrico (Sin Subtítulos)"], index=0, horizontal=True)
            auto_render = st.checkbox("🚀 Auto-renderizado Directo", value=True, help="Si se desactiva, podrás ver un borrador y confirmar antes de renderizar el video completo.")
            
            # Inicializar estado
            if 'cleaner_data' not in st.session_state or st.session_state.get('last_upload') != clean_upload.name:
                st.session_state.cleaner_data = None
                st.session_state.last_upload = clean_upload.name
            
            # Selector de Posición (Nuevo Sistema Robusto)
            hook_pos_opt = st.selectbox(
                "📍 Posición Vertical del Gancho (Hook)",
                ["Superior (Seguridad TikTok)", "Centro (Enfrentamiento)", "Inferior (Subtítulos)"],
                index=0,
                help="Elige dónde aparecerá el título inicial antes de generar el borrador."
            )
            mapping_y = {
                "Superior (Seguridad TikTok)": 0.20,
                "Centro (Enfrentamiento)": 0.45,
                "Inferior (Subtítulos)": 0.75
            }
            st.session_state.hook_y_pct = mapping_y[hook_pos_opt]

            # Selector de Color
            hook_col_opt = st.radio(
                "🎨 Color del Gancho",
                ["Amarillo (GTA)", "Blanco (Clásico)"],
                horizontal=True,
                help="Elige el impacto visual deseado para el título inicial."
            )
            st.session_state.hook_color = "#FDD002" if "Amarillo" in hook_col_opt else "#FFFFFF"

            # Paso 1: Analizar / Auto-render
            btn_label = "🚀 INICIAR LIMPIEZA MAESTRA" if auto_render else "📝 GENERAR BORRADOR (PREVIEW)"
            if st.button(btn_label, type="primary"):
                # ... (Proceso de guardado de input)
                temp_dir = CFG["paths"]["temp_folder"]
                os.makedirs(temp_dir, exist_ok=True)
                input_path = os.path.join(temp_dir, f"clean_in_{int(time.time())}.mp4")
                with open(input_path, "wb") as f:
                    f.write(clean_upload.getbuffer())

                with st.status("🛠️ Procesando etapa inicial...", expanded=True) as status:
                    try:
                        cleaner = CopyrightCleaner(CFG)
                        log_slot = st.empty()
                        ui_log = lambda m: log_slot.write(m)
                        
                        # PASO 1: Obtener datos
                        traj_data = cleaner.map_text_trajectory(input_path, log_callback=ui_log)
                        words_data = cleaner.transcribe_video(input_path, log_callback=ui_log)
                        
                        # GUARDADO CRÍTICO EN SESSION STATE
                        st.session_state.cleaner_data = {
                            'input_path': input_path,
                            'words': words_data,
                            'trajectory': traj_data
                        }
                        
                        if auto_render:
                            st_pb = st.progress(0)
                            st_timer = st.empty()
                            final_video = cleaner.process(
                                input_path, CFG["paths"]["output_folder"], 
                                words=words_data, trajectory=traj_data,
                                log_callback=ui_log, logger=StreamlitLogger(st_pb, st_timer),
                                clean_mode=clean_mode,
                                hook_y_pct=st.session_state.hook_y_pct,
                                hook_color=st.session_state.hook_color
                            )
                            status.update(label="✨ Proceso Completado", state="complete")
                            st.success(f"🎉 ¡Video Listo! Guardado en: {os.path.basename(final_video)}")
                            _, center_col, _ = st.columns([0.2, 0.6, 0.2])
                            with center_col: st.video(final_video)
                        else:
                            status.update(label="✅ Borrador Preparado", state="complete")
                            time.sleep(1)
                            st.rerun()
                    except Exception as e:
                        err_trace = traceback.format_exc()
                        status.error(f"❌ Error en etapa inicial: {e}")
            
            # Si hay borrador listo, mostrar preview estándar
            if st.session_state.get('cleaner_data') and not auto_render:
                data = st.session_state.cleaner_data
                st.divider()
                st.subheader("🖼️ Galería de Borrador")
                
                try:
                    cleaner = CopyrightCleaner(CFG)
                    with st.spinner("Actualizando miniaturas..."):
                        previews = cleaner.get_preview_frames(
                            data['input_path'], data['words'], data['trajectory'],
                            clean_mode=clean_mode, 
                            hook_y_pct=st.session_state.hook_y_pct,
                            hook_color=st.session_state.hook_color
                        )

                    cols = st.columns(3)
                    for idx, img in enumerate(previews):
                        cols[idx].image(img, caption=f"Muestra {idx+1}")
                    
                except Exception as e:
                    st.error(f"Error al generar preview: {e}")

                if st.button("🔥 CONFIRMAR RENDERIZADO FINAL", type="primary"):
                    with st.status("🎬 Renderizando Video Completo...", expanded=True) as status:
                        try:
                            cleaner = CopyrightCleaner(CFG)
                            st_pb = st.progress(0)
                            st_timer = st.empty()
                            
                            final_video = cleaner.process(
                                data['input_path'], CFG["paths"]["output_folder"], 
                                words=data['words'], trajectory=data['trajectory'],
                                log_callback=lambda m: status.write(m),
                                logger=StreamlitLogger(st_pb, st_timer),
                                clean_mode=clean_mode,
                                hook_y_pct=st.session_state.hook_y_pct,
                                hook_color=st.session_state.hook_color
                            )
                            status.update(label="✨ Proceso Completado", state="complete")
                            st.success(f"🎉 ¡Video Finalizado!")
                            _, center_col, _ = st.columns([0.2, 0.6, 0.2])
                            with center_col: st.video(final_video)
                        except Exception as e:
                            err_trace = traceback.format_exc()
                            print(f"\n❌ [ERROR CRÍTICO RENDERADO]\n{err_trace}")
                            status.error(f"❌ Error Final: {e}")
                            st.expander("🔍 Detalle técnico del error").code(err_trace)
                            st.error(f"Detalle técnico: {str(e)}")

    st.stop()

# ---------------------------------------------------------
# INTERFAZ PRONÓSTICOS DIARIOS (NICHO TIKTOK FACTORY)
# ---------------------------------------------------------
if CFG["app_mode"] == "PRONOSTICOS_DIARIOS":
    from datetime import date as _date, timedelta as _td

    st.header("📊 Pronósticos Diarios — TikTok Factory")
    st.info(
        "El guion **YA viene hecho** desde Redis (`daily_bets_tiktok_video`), "
        "lo escribe el workflow `tiktok_video_script.yml` de bet-ai-master sobre las 18:05 "
        "hora Madrid con OpenAI gpt-5.4 + datos verificables de API-Sports. "
        "Aquí solo: TTS (MiniMax) → Whisper → carruseles + stock → MP4 9:16 con "
        "`perfil.png` durante el CTA."
    )

    # Validación de claves Redis
    _missing_redis = [k for k in ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN")
                      if not os.getenv(k)]
    if _missing_redis:
        st.error(f"❌ Faltan variables en .env: {', '.join(_missing_redis)}")
        st.stop()

    col_cfg, col_action = st.columns([2, 1])
    with col_cfg:
        # Aplicar override pendiente ANTES de instanciar el widget
        if "pron_pending_date" in st.session_state:
            st.session_state["pron_date_input_key"] = st.session_state.pop("pron_pending_date")
        if "pron_date_input_key" not in st.session_state:
            st.session_state["pron_date_input_key"] = _date.today() + _td(days=1)
        target_date = st.date_input(
            "📅 Fecha objetivo",
            key="pron_date_input_key",
            help="Por defecto = mañana. Tiene que existir el field "
                 "`betai:daily_bets_tiktok_video:YYYY-MM[YYYY-MM-DD]` en Redis "
                 "(disponible tras las 18:10 hora Madrid).",
        )
        target_date_str = target_date.strftime("%Y-%m-%d")

        publish_redis = st.checkbox(
            "📤 Publicar URL del MP4 en Redis (`betai:tiktokfactory_video_tomorrow`)",
            value=False,
            help="Solo guarda la ruta local — para publicar en Vercel Blob añade ese paso aparte.",
        )

        # Voces favoritas seleccionadas tras audicionar el catálogo (todas Standard
        # Spanish del sistema, suenan latino-neutras al pronunciar 'c'/'z' como /s/).
        FAVORITE_VOICES = {
            "💪 Strong-Willed (mature, firme)": "Spanish_Strong-WilledBoy",
            "⚡ Energetic (joven, viral)":      "Spanish_EnergeticBoy",
            "🔥 Passionate Warrior (intenso)":   "Spanish_PassionateWarrior",
            "🎚️ Custom (escribir ID)":           "__CUSTOM__",
        }
        env_default = os.getenv("PRONOSTICOS_VOICE_ID", "")
        # Si el .env tiene una de las favoritas, preselecciónala
        default_label = next(
            (lbl for lbl, vid in FAVORITE_VOICES.items() if vid == env_default),
            list(FAVORITE_VOICES.keys())[0],
        )
        voice_label = st.selectbox(
            "🗣️ Voz para la narración",
            options=list(FAVORITE_VOICES.keys()),
            index=list(FAVORITE_VOICES.keys()).index(default_label),
            help="Las 3 primeras son favoritas tras audicionar el catálogo de MiniMax. "
                 "'Custom' permite escribir cualquier voice_id (otras del sistema o clonadas).",
        )
        if FAVORITE_VOICES[voice_label] == "__CUSTOM__":
            voice_override = st.text_input(
                "Voice ID custom",
                value=env_default if env_default not in FAVORITE_VOICES.values() else "",
                placeholder="Spanish_Deep-tonedMan / moss_audio_xxx / voz_final_tiktok_v2",
                help="ID exacto de la voz MiniMax (sistema o clonada).",
            )
        else:
            voice_override = FAVORITE_VOICES[voice_label]
            st.caption(f"`{voice_override}`")

        add_subtitles = st.checkbox(
            "🔤 Quemar subtítulos karaoke",
            value=True,
            help="Whisper transcribe el audio del TTS y se queman subtítulos palabra a palabra.",
        )

        use_intro_folder = st.checkbox(
            "🎬 Usar carpeta `intro/` para la intro",
            value=True,
            help="Si está activo, durante los segundos antes del primer 'Empezamos con' "
                 "el pipeline busca clips en BIBLIOTECA_PRONOSTICOS_CLIPS/intro/. "
                 "Si está apagado o la carpeta está vacía, hereda los clips del pick 1.",
        )

        show_pick_carousel = st.checkbox(
            "🎴 Mostrar card del partido al inicio de cada pick (4s)",
            value=False,
            help="Si está activo, los primeros ~4s de cada pick muestran una imagen "
                 "generada con el partido + el pick + cuota (fondo azul). "
                 "Recomendado OFF: deja que el vídeo de stock fluya sin parar.",
        )

        with st.expander("🔊 Efectos de sonido", expanded=False):
            st.caption("Todos los SFX viven en `BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/`. "
                       "Si el archivo no existe, ese SFX se omite con un log informativo.")

            add_money_sfx = st.checkbox(
                "💰 Dinero al pronunciar la cifra del bote",
                value=True,
                help="Cha-ching/caja registradora cuando arranca la primera palabra-número "
                     "de la intro. Archivos aceptados: money.mp3 / cha-ching.mp3 / dinero.mp3",
            )
            sfx_volume = st.slider(
                "Volumen dinero", min_value=0.2, max_value=1.0,
                value=0.55, step=0.05, key="vol_money",
            )

            add_clink_sfx = st.checkbox(
                "🔔 Clink al inicio de cada pick",
                value=True,
                help="Notificación corta cuando arranca el pronóstico textual "
                     "('*más* de 6 disparos', '*ambos* anotan'...). "
                     "Archivos aceptados: clink.mp3 / notification.mp3 / pick.mp3",
            )
            clink_volume = st.slider(
                "Volumen clink", min_value=0.1, max_value=0.8,
                value=0.35, step=0.05, key="vol_clink",
                help="Más bajo que dinero porque suena 3-5 veces. 0.35 recomendado.",
            )

            add_camera_sfx = st.checkbox(
                "📸 Cámara cuando aparecen fotos (perfil + ligas)",
                value=True,
                help="Disparador de cámara/shutter cuando aparece perfil.png durante el "
                     "CTA midroll Y cuando aparecen los escudos de ligas en la intro. "
                     "Archivos aceptados: camera.mp3 / shutter.mp3 / foto.mp3",
            )
            camera_volume = st.slider(
                "Volumen cámara", min_value=0.2, max_value=1.0,
                value=0.45, step=0.05, key="vol_camera",
            )

            st.divider()

            add_background_music = st.checkbox(
                "🎵 Música de fondo durante todo el vídeo",
                value=True,
                help="Mezcla un MP3 de fondo bajo la voz. Si la canción dura más que el "
                     "vídeo, se recorta + fade-out 0.5s. Archivo esperado: "
                     "BIBLIOTECA_PRONOSTICOS_CLIPS/sfx/fondo.mp3 (también vale en /musica/ "
                     "o /bgm/, y nombres background.mp3 / bgm.mp3).",
            )
            bgm_volume = st.slider(
                "Volumen música fondo", min_value=0.05, max_value=0.50,
                value=0.20, step=0.05, key="vol_bgm",
                help="0.20 (20%) recomendado: la voz queda nítida por encima. "
                     "Si tu fondo.mp3 tiene volumen ya alto en el archivo, "
                     "considera 0.10-0.15.",
            )

        with st.expander("🏆 Overlay de logos de ligas", expanded=False):
            st.caption("Cuando la narración pronuncia 'ligas/champions/europa/copa' en la "
                       "intro, aparecen los logos de las ligas de los picks del día (1-3 max). "
                       "Assets en `BIBLIOTECA_PRONOSTICOS_CLIPS/fotos/`.")

            add_league_overlay = st.checkbox(
                "Activar overlay de logos",
                value=True,
            )
            league_overlay_duration = st.slider(
                "Duración del overlay (segundos)",
                min_value=1.5, max_value=5.0, value=3.0, step=0.5,
            )

        saturation = st.slider(
            "🎨 Saturación de color",
            min_value=1.0, max_value=1.6, value=1.25, step=0.05,
            help="1.0 = sin cambios. 1.2-1.3 recomendado: colores más vivos sin "
                 "que se note artificial. >1.4 puede saturar excesivamente.",
        )

    with col_action:
        st.markdown("### 🚦 Estado APIs")
        _has_pexels = bool(os.getenv("PEXELS_API_KEY"))
        _has_pixabay = bool(os.getenv("PIXABAY_API_KEY"))
        st.write(f"Pexels: {'✅' if _has_pexels else '⚠️ no key'}")
        st.write(f"Pixabay: {'✅' if _has_pixabay else '⚠️ no key'}")
        if not _has_pexels and not _has_pixabay:
            st.caption("Sin stock APIs los segmentos usarán fondo sólido.")

        from src.pronosticos.stock_search import CACHE_BASE
        st.markdown("### 📂 Carpeta clips manuales")
        st.code(str(CACHE_BASE), language=None)
        st.caption("Subcarpetas por equipo / liga / 'general'. "
                   "Mete `fotos/perfil.png` ahí dentro para el CTA.")

    # ── Preview del guion del día ──
    st.divider()
    st.markdown("### 📝 Guion del día")
    st.caption("El guion ya viene escrito por bet-ai-master. Si hay varias versiones del día "
               "(cron + manuales) puedes elegir cuál usar o generarlas todas en cola.")

    def _load_guion(date_str: str) -> bool:
        """Carga el guion en session_state. Devuelve True si OK, False si error
        (ya muestra los toasts apropiados)."""
        try:
            from src.pronosticos.data_loader import (
                load_raw_payload, list_versions,
            )
            payload = load_raw_payload(date_str)
            if not payload:
                raise ValueError(f"No hay payload en Redis para {date_str}.")
            versions = list_versions(payload)
            if not versions:
                raise ValueError("Payload sin versiones ni script raíz.")
            st.session_state["pron_versions"] = versions
            st.session_state["pron_date"] = date_str
            st.session_state["pron_selected_version_idx"] = next(
                (i for i, v in enumerate(versions) if v.get("is_selected")), 0
            )
            st.success(f"✅ {len(versions)} versión(es) encontrada(s) para {date_str}")
            return True
        except Exception as e:
            st.error(f"❌ {e}")
            st.session_state.pop("pron_versions", None)
            return False

    col_load_today, col_load_latest = st.columns([2, 1])
    with col_load_today:
        if st.button("🔄 Cargar guion del día seleccionado", use_container_width=True):
            _load_guion(target_date_str)
    with col_load_latest:
        if st.button("🕐 Cargar último disponible", use_container_width=True,
                     help="Busca en Redis la fecha más reciente con guion publicado "
                          "(hoy / ayer / antesdeayer / hasta 14 días atrás). "
                          "Útil para hacer pruebas mientras el guion del día siguiente "
                          "aún no está disponible (se publica ~18:05 hora Madrid)."):
            from src.pronosticos.data_loader import find_latest_available_date
            latest = find_latest_available_date()
            if not latest:
                st.error("❌ No se encontró ningún guion en los últimos 14 días.")
            elif _load_guion(latest):
                # Sincroniza el date_input con la fecha cargada (vía key intermedio
                # para que el override se aplique ANTES de que el widget se instancie
                # en el siguiente render)
                from datetime import datetime as _dtparse
                st.session_state["pron_pending_date"] = _dtparse.strptime(
                    latest, "%Y-%m-%d"
                ).date()
                st.rerun()

    versions_loaded = st.session_state.get("pron_versions") or []
    chosen_version: dict | None = None
    selected_versions: list[dict] = []
    if versions_loaded and st.session_state.get("pron_date") == target_date_str:
        from src.pronosticos.data_loader import get_picks

        # Selector múltiple de versiones (1, varias o todas)
        labels = []
        for i, v in enumerate(versions_loaded):
            star = "⭐ " if v.get("is_selected") else ""
            label = (
                f"{star}v{v.get('id', '?')} "
                f"· {v.get('trigger', '?')} "
                f"· {v.get('mode', '?')} "
                f"· {v.get('word_count', '?')} pal · "
                f"~{v.get('estimated_duration_s', 0):.0f}s"
            )
            labels.append(label)

        default_idx = next(
            (i for i, v in enumerate(versions_loaded) if v.get("is_selected")), 0
        )
        sel_indices = st.multiselect(
            "Versiones a generar (marca 1 o varias)",
            options=list(range(len(versions_loaded))),
            default=[default_idx],
            format_func=lambda i: labels[i],
            help="Por defecto va marcada la versión ⭐ (selected_version_id de Redis). "
                 "Marca varias para generarlas en cola, una tras otra.",
        )
        selected_versions = [versions_loaded[i] for i in sel_indices]
        # Para preview: la primera de la selección actúa de "actual"
        sel_idx = sel_indices[0] if sel_indices else 0
        chosen_version = versions_loaded[sel_idx] if sel_indices else None

        # Metadatos de la versión elegida
        m1, m2, m3, m4 = st.columns(4)
        with m1: st.metric("Modo", chosen_version.get("mode", "?"))
        with m2: st.metric("Picks", len(get_picks(chosen_version)))
        with m3: st.metric("Palabras", chosen_version.get("word_count", "?"))
        with m4: st.metric("Duración est.", f"{chosen_version.get('estimated_duration_s', 0):.0f}s")

        if chosen_version.get("competition_focus"):
            st.info(f"🏆 competition_focus: **{chosen_version['competition_focus']}** "
                    f"(picks restringidos a esa competición)")

        with st.expander("📋 Ver picks"):
            for i, p in enumerate(get_picks(chosen_version), 1):
                st.markdown(f"**#{i}** — {p.get('match', '?')} · "
                            f"`{p.get('league', '?')}` → **{p.get('pick', '?')}**")

        # Guion editable (efímero — NO se guarda en Redis)
        original_script = chosen_version.get("script", "")
        edit_key = f"script_edit_{target_date_str}_{chosen_version.get('id', 'x')}"
        edited_script = st.text_area(
            "📜 Guion (editable solo en memoria — no se guarda en Redis)",
            value=original_script,
            height=240,
            key=edit_key,
            help="Edita el texto si quieres ajustar palabras, números o cambiar una frase. "
                 "Los cambios SOLO afectan al vídeo que generes ahora — no se persiste nada. "
                 "Si pulsas 'Cola TODAS' los cambios se ignoran (cada versión usa su original).",
        )
        is_edited = edited_script.strip() != original_script.strip()
        if is_edited:
            new_words = len(edited_script.split())
            old_words = len(original_script.split())
            delta = new_words - old_words
            st.info(f"✏️ Guion editado · {new_words} palabras "
                    f"({delta:+d} vs original) · NO se guardará en Redis")
        st.caption(f"Title: {chosen_version.get('title', '—')}")
    else:
        st.info("👆 Pulsa 'Cargar guion del día' para previsualizar y elegir versión.")
        edited_script = ""
        original_script = ""
        is_edited = False

    # Botón único: genera N versiones (cola si N>1)
    n_selected = len(selected_versions)
    btn_label = (
        f"🚀 GENERAR {n_selected} VERSIÓN" if n_selected == 1 else
        f"🧵 GENERAR EN COLA ({n_selected} versiones)" if n_selected > 1 else
        "🚀 GENERAR (selecciona al menos 1)"
    )
    btn_run = st.button(
        btn_label, type="primary",
        disabled=n_selected == 0,
        use_container_width=True,
    )

    if btn_run:
        try:
            from src.pronosticos.pipeline import run_pronosticos_pipeline
        except Exception as e:
            st.error(f"❌ No se pudo cargar el pipeline de pronósticos: {e}")
            st.stop()

        # Determinar la cola de version_ids a procesar (lo elegido en el multiselect)
        queue_ids = [str(v.get("id")) for v in selected_versions
                     if v.get("id") is not None]
        if not queue_ids:
            queue_ids = [None]
        is_queue = len(queue_ids) > 1
        queue_label = (f"COLA de {len(queue_ids)} versiones" if is_queue
                       else f"versión v{queue_ids[0]}")

        with st.status(f"🏭 Pipeline — {queue_label}", expanded=True) as status:
            # Barra de progreso global de la cola + ETA
            queue_bar = st.progress(0.0, text="Iniciando...")
            eta_slot = st.empty()
            log_slot = st.empty()
            logs_buffer = []

            def _ui_log(msg):
                logs_buffer.append(msg)
                log_slot.markdown("\n".join(f"- {l}" for l in logs_buffer[-15:]))

            t0 = time.time()
            n_total = len(queue_ids)

            def _make_progress_cb(idx_in_queue: int, vid: str):
                """Construye el callback de progreso para la versión `idx_in_queue`."""
                def cb(pct: float, msg: str):
                    # Progreso global = (versiones_completadas + pct_versión_actual) / total
                    global_pct = (idx_in_queue + pct) / n_total
                    label = (f"v{vid} — {msg}" if is_queue
                             else msg) + f" ({global_pct*100:.0f}%)"
                    queue_bar.progress(global_pct, text=label)
                    elapsed = time.time() - t0
                    if global_pct > 0.05:
                        total_est = elapsed / global_pct
                        remaining = max(0, total_est - elapsed)
                        eta_slot.caption(
                            f"⏱️ {format_seconds(elapsed)} transcurridos · "
                            f"queda ~{format_seconds(remaining)} "
                            f"(estimado total ~{format_seconds(total_est)})"
                        )
                return cb

            results: list[tuple[str, str]] = []  # [(version_id, mp4_path)]
            errors: list[tuple[str, str]] = []

            for idx, vid in enumerate(queue_ids):
                try:
                    _ui_log(f"\n━━━ versión v{vid or 'auto'} ({idx+1}/{n_total}) ━━━")
                    # script_override: solo aplica si hay 1 sola versión + fue editada
                    use_override = (
                        not is_queue
                        and is_edited
                        and chosen_version is not None
                        and str(chosen_version.get("id")) == str(vid)
                    )
                    # Resolución del selector de la sidebar (con safety pares)
                    _res = res_options[selected_res_label]
                    _w = _res[0] if _res[0] % 2 == 0 else _res[0] - 1
                    _h = _res[1] if _res[1] % 2 == 0 else _res[1] - 1
                    final_path = run_pronosticos_pipeline(
                        target_date=target_date_str,
                        output_folder=CFG["paths"]["output_folder"],
                        log_callback=_ui_log,
                        video_size=(_w, _h),
                        voice_id_override=(voice_override.strip() or None),
                        publish_to_redis=publish_redis,
                        add_subtitles=add_subtitles,
                        use_intro_folder=use_intro_folder,
                        add_money_sfx=add_money_sfx,
                        sfx_volume=float(sfx_volume),
                        add_clink_sfx=add_clink_sfx,
                        clink_volume=float(clink_volume),
                        add_camera_sfx=add_camera_sfx,
                        camera_volume=float(camera_volume),
                        add_league_overlay=add_league_overlay,
                        league_overlay_duration=float(league_overlay_duration),
                        saturation=float(saturation),
                        show_pick_carousel=show_pick_carousel,
                        version_id=vid if vid != "legacy" else None,
                        script_override=edited_script if use_override else None,
                        add_background_music=add_background_music,
                        bgm_volume=float(bgm_volume),
                        progress_callback=_make_progress_cb(idx, vid or "auto"),
                    )
                    results.append((vid or "auto", final_path))
                except Exception as e:
                    errors.append((vid or "auto", str(e)))
                    _ui_log(f"❌ v{vid}: {e}")

            elapsed = time.time() - t0
            ok_n = len(results)
            err_n = len(errors)

            if err_n == 0:
                status.update(
                    label=f"✅ {ok_n}/{ok_n} generado(s) en {format_seconds(elapsed)}",
                    state="complete",
                )
            elif ok_n > 0:
                status.update(
                    label=f"⚠️ {ok_n} OK / {err_n} fallo(s) en {format_seconds(elapsed)}",
                    state="error",
                )
            else:
                status.update(label="❌ Pipeline abortado (todas fallaron)", state="error")

            # Render del/los resultado(s)
            if results:
                if len(results) == 1:
                    vid, final_path = results[0]
                    col_video, col_meta = st.columns([1, 2])
                    with col_video:
                        st.video(final_path)
                    with col_meta:
                        st.success(f"🎉 ¡Vídeo v{vid} listo para {target_date_str}!")
                        st.text_input("Archivo:", value=os.path.basename(final_path),
                                      disabled=True)
                        st.caption(f"📂 `{final_path}`")
                        if st.button("📂 Abrir Carpeta", key=f"open_{vid}"):
                            try:
                                os.startfile(os.path.dirname(final_path))
                            except Exception:
                                st.warning("No se pudo abrir la carpeta automáticamente.")
                else:
                    st.success(f"🎉 {len(results)} vídeos listos para {target_date_str}")
                    cols = st.columns(min(len(results), 3))
                    for idx, (vid, final_path) in enumerate(results):
                        with cols[idx % len(cols)]:
                            st.markdown(f"**v{vid}**")
                            st.video(final_path)
                            st.caption(os.path.basename(final_path))

            if errors:
                with st.expander(f"❌ Errores ({err_n})"):
                    for vid, msg in errors:
                        st.write(f"**v{vid}**: {msg}")

            if sound_on:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    pass

    st.stop()

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
    
    st.divider()
    
    # Inputs Dinámicos en Grid (2 columnas) para ahorrar espacio
    queue_inputs = []
    st.write("⬇️ **Configura los temas de los videos:** (Deja vacío para tema aleatorio)")

    grid_cols = st.columns(2)
    for i in range(cantidad):
        col_idx = i % 2
        with grid_cols[col_idx]:
            st.markdown(f"**🎬 Video {i+1}**")

            # Fila 1: opciones de título
            opt1, opt2, opt3, opt4 = st.columns([1.2, 1.4, 2.4, 1.8])
            with opt1:
                top_count = st.selectbox(
                    "Nº Top",
                    [5, 4, 3],
                    key=f"top_count_{i}",
                    help="Número de presidentes en el ranking. Ajusta palabras/ítem para ~1min.",
                )
            with opt2:
                prefix_word = st.selectbox(
                    "Palabra",
                    ["The", "Top"],
                    key=f"prefix_word_{i}",
                )
            with opt3:
                include_history = st.checkbox(
                    "Añadir \"in US history\"",
                    value=True,
                    key=f"history_{i}",
                )
            with opt4:
                include_hook = st.checkbox(
                    "Incluir hook",
                    value=True,
                    key=f"hook_{i}",
                    help="Añade la frase 'Save this video before they delete it...' tras el título.",
                )

            # Prefijo combinado: "The 5", "Top 4", etc.
            title_prefix = f"{prefix_word} {top_count}"

            # Fila 2: título en línea con prefijo y sufijo bloqueados
            suffix_display = "in US history" if include_history else ""
            st.caption("Título final (edita solo el centro, lo gris es fijo):")
            p_col, t_col, s_col = st.columns([2, 4, 4])
            with p_col:
                st.text_input(
                    "prefix_lock",
                    value=title_prefix,
                    disabled=True,
                    key=f"prefix_lock_{i}",
                    label_visibility="collapsed",
                )
            with t_col:
                topic = st.text_input(
                    "topic",
                    key=f"topic_{i}",
                    placeholder="worst / corruption / richest",
                    label_visibility="collapsed",
                )
            with s_col:
                st.text_input(
                    "suffix_lock",
                    value=suffix_display,
                    disabled=True,
                    key=f"suffix_lock_{i}",
                    label_visibility="collapsed",
                )

            queue_inputs.append({
                "topic": topic,
                "prefix": title_prefix,
                "top_count": top_count,
                "include_history": include_history,
                "include_hook": include_hook,
            })

    # Botón de Acción
    if st.button("✨ INICIAR FÁBRICA DE VIDEOS"):
        # 0. PRE-FLIGHT CHECK (CON FEEDBACK VISUAL)
        check_ph = st.empty()
        with check_ph.status("🩺 Verificando estado de APIs...", expanded=True) as status:
            def ui_cb(msg): st.write(msg)
            
            if not check_api_health(ui_callback=ui_cb):
                status.update(label="❌ Error en comprobaciones", state="error")
                st.error("⚠️ ABORTANDO: Una o más APIs no responden. No se ha consumido cuota.")
                st.stop()
            else:
                status.update(label="✅ Sistemas TIKTOK_AUTOMATION ONLINE", state="complete")
                time.sleep(1.0)
        
        check_ph.empty() # Limpiar mensajes visuales después de éxito
            
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
            
            for idx, video_cfg in enumerate(queue_inputs):
                user_topic = video_cfg["topic"]
                current_prefix = video_cfg["prefix"]
                current_top_count = video_cfg["top_count"]
                current_include_history = video_cfg["include_history"]
                current_include_hook = video_cfg["include_hook"]
                # Limpieza y Lógica de Tópico
                current_topic = user_topic.strip() if user_topic and user_topic.strip() else None
                topic_display = current_topic if current_topic else "🎲 Tema Aleatorio (Sorpréndeme)"
                
                st.divider()
                st.markdown(f"### ▶️ Procesando Video {idx+1}/{total_jobs} | {topic_display}")
                status.update(label=f"Trabajando en {idx+1}/{total_jobs}: {topic_display}...", state="running")
                
                # Init cleanup vars
                txt_output = None
                audio_output_folder = None
                
                try:
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

                    # --- BARRA GLOBAL DE PROGRESO POR VÍDEO ---
                    overall_start_t = time.time()
                    # Pesos por paso (subs/hook = 0 si están desactivados)
                    _w = [
                        0.05,                              # guion
                        0.15,                              # audio
                        0.50,                              # video render
                        0.20 if subs_enabled else 0.0,     # subs
                        0.10 if hook_enabled else 0.0,     # hook
                    ]
                    _total_w = sum(_w) or 1.0
                    _w = [x / _total_w for x in _w]
                    _step_pct = []
                    _cum = 0.0
                    for x in _w:
                        _cum += x
                        _step_pct.append(_cum)
                    # _step_pct[0..4] = pct acumulado tras: guion, audio, video, subs, hook

                    overall_progress = st.progress(0, text="🔄 Iniciando...")
                    overall_time_ph = st.empty()

                    def _update_overall(pct: float, label: str):
                        pct = max(0.0, min(1.0, pct))
                        overall_progress.progress(pct, text=f"{label} · {int(pct*100)}%")
                        elapsed = time.time() - overall_start_t
                        emins, esecs = divmod(int(elapsed), 60)
                        if pct > 0.05:
                            eta_left = max(0.0, (elapsed / pct) - elapsed)
                            rmins, rsecs = divmod(int(eta_left), 60)
                            eta_str = f" · ⏳ Restante ~{rmins:02d}:{rsecs:02d}"
                        else:
                            eta_str = ""
                        overall_time_ph.markdown(f"⏱️ Transcurrido {emins:02d}:{esecs:02d}{eta_str}")

                    _update_overall(0.0, "📝 Generando guion")

                    # --- PASO 1: GUIONISTA ---
                    st_script_status.info("🔄 Generando Guion...")
                    t0 = time.time()

                    script_data = guionista.generate_script(
                        user_topic=current_topic,
                        creative_mode=use_creative_mode,
                        title_prefix=current_prefix,
                        include_history=current_include_history,
                        include_hook=current_include_hook,
                        top_count=current_top_count,
                    )

                    txt_output = guionista.save_scripts_to_txt(script_data, top_count=current_top_count)

                    t1 = time.time()
                    st_script_status.success(f"✅ Guion OK ({format_seconds(t1-t0)})")
                    _update_overall(_step_pct[0], "🎙️ Generando audio")

                    # --- PASO 2: LOCUTOR ---
                    st_audio_status.info("🔄 Clonando Voz...")
                    t2 = time.time()
                    
                    resources_base = CFG["paths"]["resources_library"]
                    # Nota: generate_audios_from_text_folder es agnóstico, lee lo que haya en la carpeta txt
                    audio_output_folder = locutor.generate_audios_from_text_folder(txt_output, resources_base)
                    
                    if not audio_output_folder:
                        raise Exception("No se generaron audios. Abortando este video.")
                    
                    t3 = time.time()
                    st_audio_status.success(f"✅ Audios OK ({format_seconds(t3-t2)})")
                    _update_overall(_step_pct[1], "🎬 Renderizando vídeo")

                    # --- PASO 3: EDITOR DE VIDEO ---
                    st_edit_status.info("🔄 Renderizando...")
                    t4 = time.time()
                    
                    final_video_path = generate_video_pipeline(
                        audio_output_folder,
                        CFG["paths"]["output_folder"],
                        CFG,
                        status,
                        log_cb,
                        engine_version
                    )

                    t5 = time.time()
                    st_edit_status.success(f"✅ Video OK ({format_seconds(t5-t4)})")
                    _next_label_after_video = (
                        "🔤 Generando subtítulos" if subs_enabled
                        else ("🎣 Añadiendo gancho de texto" if hook_enabled else "✨ Finalizando")
                    )
                    _update_overall(_step_pct[2], _next_label_after_video)

                    # --- PASO 4 (opcional): SUBTÍTULOS KARAOKE ---
                    if subs_enabled:
                        st_subs_status = st.empty()
                        st_subs_status.info("🔄 Generando subtítulos...")
                        t_subs_0 = time.time()
                        try:
                            from src.subtitles import transcribe, render_karaoke_on_video, DEFAULT_STYLE

                            # 1. Extraer audio del vídeo final
                            from moviepy.editor import VideoFileClip as _VFC
                            _tmp_audio_dir = CFG["paths"]["temp_folder"]
                            os.makedirs(_tmp_audio_dir, exist_ok=True)
                            tmp_audio = os.path.join(_tmp_audio_dir, f"subs_audio_{int(time.time())}.mp3")
                            _vc = _VFC(final_video_path)
                            _vc.audio.write_audiofile(tmp_audio, logger=None)
                            _vc.close()

                            # 2. Transcribir con faster-whisper
                            st_subs_status.info("🔄 Transcribiendo audio (Whisper local)...")
                            words = transcribe(tmp_audio, model_size="base", language="en")

                            if not words:
                                st_subs_status.warning("⚠️ Whisper no detectó palabras — se omite overlay.")
                            else:
                                # 3. Renderizar overlay a un archivo temporal y reemplazar el original
                                st_subs_status.info(f"🔄 Componiendo overlay ({len(words)} palabras)...")
                                subs_style = {
                                    **DEFAULT_STYLE,
                                    "highlight_color": subs_highlight_color,
                                    "text_color": subs_text_color,
                                    "stroke_color": subs_stroke_color,
                                    "stroke_width": subs_stroke_width,
                                    "case_mode": subs_case,
                                    "font_scale": subs_font_scale,
                                    "max_words_per_chunk": subs_max_words,
                                    "y_position_pct": subs_y_position,
                                }
                                tmp_out = final_video_path + ".tmp.mp4"
                                render_karaoke_on_video(
                                    final_video_path, words, subs_style, tmp_out,
                                    log_callback=lambda m: status.write(m),
                                )
                                # Sustituir el archivo original por el que tiene subs (sin crear _SUBS.mp4)
                                os.replace(tmp_out, final_video_path)

                            # Limpiar audio temporal
                            try: os.remove(tmp_audio)
                            except: pass

                            t_subs_1 = time.time()
                            st_subs_status.success(f"✅ Subtítulos OK ({format_seconds(t_subs_1-t_subs_0)})")
                        except Exception as e:
                            st_subs_status.error(f"❌ Error subtítulos: {e}")
                            print(f"[SUBS ERROR] {traceback.format_exc()}")
                        _update_overall(
                            _step_pct[3],
                            "🎣 Añadiendo gancho de texto" if hook_enabled else "✨ Finalizando",
                        )

                    # --- PASO 5 (opcional): GANCHO DE TEXTO ---
                    if hook_enabled:
                        st_hook_status = st.empty()
                        st_hook_status.info("🔄 Añadiendo gancho de texto...")
                        t_hook_0 = time.time()
                        try:
                            from src.text_hook import add_text_hook_to_video, DEFAULT_HOOK_STYLE as _HS

                            # Prioridad: hook_box_text generado por la IA (3-6 palabras, estilo chapter title).
                            # Fallback: video_title (por si la IA no devolvió hook_box_text).
                            hook_text = (
                                (script_data.get("hook_box_text") or "").strip()
                                or (script_data.get("video_title") or "").strip()
                                or "Top 5 US Presidents"
                            )
                            st.caption(f"🎣 Hook de texto: \"{hook_text}\"")
                            hook_style = {
                                **_HS,
                                "duration": hook_duration,
                                "animation": hook_animation,
                                "y_position_pct": hook_y_position,
                                "shadow_color": hook_shadow_color,
                                "box_color": hook_box_color,
                                "text_color": hook_text_color,
                                "font_scale": hook_font_scale,
                            }
                            tmp_out = final_video_path + ".tmp.mp4"
                            add_text_hook_to_video(
                                final_video_path, hook_text, hook_style, tmp_out,
                                log_callback=lambda m: status.write(m),
                            )
                            # Sustituir el archivo original por el que tiene hook (sin crear _HOOK.mp4)
                            os.replace(tmp_out, final_video_path)

                            t_hook_1 = time.time()
                            st_hook_status.success(f"✅ Hook OK ({format_seconds(t_hook_1-t_hook_0)})")
                        except Exception as e:
                            st_hook_status.error(f"❌ Error hook: {e}")
                            print(f"[HOOK ERROR] {traceback.format_exc()}")
                        _update_overall(_step_pct[4], "🎉 Vídeo completado")

                    # Asegurar que la barra termina al 100% incluso si subs/hook estaban OFF
                    _update_overall(1.0, "🎉 Vídeo completado")
                    
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
                        
                        # Mostrar Título Sugerido (Si existe)
                        if "video_title" in script_data:
                            st.markdown(f"### 📢 {script_data['video_title']}")

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

                    
                except Exception as e:
                    st.error(f"❌ FALLÓ el video '{topic_display}'. Motivo: {e}")
                    st.warning("⚠️ Saltando al siguiente video de la cola...")
                    continue # VITAL: No parar la fábrica
                
                finally:
                    # Limpieza Automática (Siempre corre)
                    try:
                        if txt_output and os.path.exists(txt_output): shutil.rmtree(txt_output)
                        if audio_output_folder and os.path.exists(audio_output_folder): shutil.rmtree(audio_output_folder)
                        for f in os.listdir():
                            if f.endswith(".mp3") and "TEMP" in f:
                                try: os.remove(f)
                                except: pass
                    except: pass
                
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