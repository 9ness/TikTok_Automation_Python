import streamlit as st
import os
import shutil
import time
from datetime import datetime
import sys
import PIL.Image

# winsound es Windows-only. En Linux (VPS) usamos un no-op para que el código
# de notificación sonora siga compilando sin tocar las llamadas existentes.
if sys.platform.startswith("win"):
    import winsound  # noqa: F401  (lo usan partes del código más abajo)
else:
    class _WinSoundShim:
        """Stub no-op de winsound en Linux/macOS. Define solo lo que el
        código existente referencia (MB_ICONASTERISK + MessageBeep)."""
        MB_ICONASTERISK = 0x40
        MB_OK = 0x00
        MB_ICONHAND = 0x10
        MB_ICONQUESTION = 0x20
        MB_ICONEXCLAMATION = 0x30

        @staticmethod
        def MessageBeep(_type=0):
            return None

        @staticmethod
        def Beep(_freq, _dur):
            return None

        @staticmethod
        def PlaySound(*_args, **_kwargs):
            return None

    winsound = _WinSoundShim()  # type: ignore[assignment]
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

st.set_page_config(
    page_title="TikTok Creator Reward Auto",
    layout="wide",
    initial_sidebar_state="auto",  # Streamlit colapsa la sidebar en móvil automáticamente
)

# CSS responsive global (móvil-first). Cero cambios de lógica.
from src.mobile_ui import inject_responsive_css
inject_responsive_css()

# ---------------------------------------------------------
# AUTH GATE — bloqueante. Si AUTH_COOKIE_KEY + USERNAME_*/PASSWORD_HASH_*
# están definidos en .env, muestra login screen antes de cargar nada más.
# Si NO hay auth configurada (dev local), se salta sin pedir nada.
# ---------------------------------------------------------
from src.auth import require_login
_current_user = require_login()

# Cola unificada de generación (compartida entre los 4 modos).
from src.queue import JobMode, get_queue, render_queue_widget

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



# Header: título + botón de cola (popover) alineados horizontalmente.
# La cola ya no ocupa espacio vertical inline — se abre on-demand.
_QUEUE_PERSIST_DIR = CFG["paths"].get("temp_folder") if CFG else None
_hcol_title, _hcol_queue = st.columns([4, 1], vertical_alignment="bottom")
with _hcol_title:
    st.title("🏭 TikTok Creator Reward Auto")
with _hcol_queue:
    render_queue_widget(_QUEUE_PERSIST_DIR)

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
            ["🏛️ Presidentes Top 5", "📊 Pronósticos Diarios", "🛡️ Quitar Copy", "🎬 Subs sobre Vídeo"],
            index=0,
            label_visibility="collapsed"
        )
        sound_on = st.checkbox("🔔 Sonido al Finalizar", value=True)

    if "Quitar Copy" in app_mode_label:
        CFG["app_mode"] = "COPYRIGHT_CLEANER"
    elif "Pronósticos" in app_mode_label:
        CFG["app_mode"] = "PRONOSTICOS_DIARIOS"
    elif "Subs sobre Vídeo" in app_mode_label:
        CFG["app_mode"] = "SUBS_AUTO"
    else:
        CFG["app_mode"] = "PRESIDENTS_TOP5"

    is_presidents = (CFG["app_mode"] == "PRESIDENTS_TOP5")
    is_pronosticos = (CFG["app_mode"] == "PRONOSTICOS_DIARIOS")
    is_copyright = (CFG["app_mode"] == "COPYRIGHT_CLEANER")
    is_subs_auto = (CFG["app_mode"] == "SUBS_AUTO")

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
            #
            # Auto-render = encolar a la cola global (ahora todos los modos van por la cola).
            # Borrador = sigue siendo síncrono porque requiere preview interactivo antes
            # de confirmar (el usuario ve miniaturas y decide).
            btn_label = "➕ ENCOLAR LIMPIEZA" if auto_render else "📝 GENERAR BORRADOR (PREVIEW)"
            if st.button(btn_label, type="primary", use_container_width=True):
                # Guardamos el input ANTES de encolar (luego el worker lo lee del disco)
                temp_dir = CFG["paths"]["temp_folder"]
                os.makedirs(temp_dir, exist_ok=True)
                input_path = os.path.join(temp_dir, f"clean_in_{int(time.time())}.mp4")
                with open(input_path, "wb") as f:
                    f.write(clean_upload.getbuffer())

                if auto_render:
                    queue = get_queue(CFG["paths"]["temp_folder"])
                    queue.enqueue(
                        JobMode.COPYRIGHT,
                        title=f"{clean_upload.name} · {clean_mode}",
                        params={
                            "input_path": input_path,
                            "config": CFG,
                            "clean_mode": clean_mode,
                            "hook_y_pct": st.session_state.hook_y_pct,
                            "hook_color": st.session_state.hook_color,
                        },
                    )
                    st.toast("➕ Limpieza encolada — puedes seguir trabajando.", icon="🧵")
                    time.sleep(0.4)
                    st.rerun()
                else:
                    # Borrador síncrono (preview interactivo)
                    with st.status("🛠️ Generando borrador…", expanded=True) as status:
                        try:
                            cleaner = CopyrightCleaner(CFG)
                            log_slot = st.empty()
                            ui_log = lambda m: log_slot.write(m)
                            traj_data = cleaner.map_text_trajectory(input_path, log_callback=ui_log)
                            words_data = cleaner.transcribe_video(input_path, log_callback=ui_log)
                            st.session_state.cleaner_data = {
                                'input_path': input_path,
                                'words': words_data,
                                'trajectory': traj_data,
                            }
                            status.update(label="✅ Borrador Preparado", state="complete")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
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

                # Tras revisar el borrador → encolar el render final
                if st.button("➕ ENCOLAR RENDER FINAL", type="primary", use_container_width=True):
                    queue = get_queue(CFG["paths"]["temp_folder"])
                    queue.enqueue(
                        JobMode.COPYRIGHT,
                        title=f"{os.path.basename(data['input_path'])} · {clean_mode}",
                        params={
                            "input_path": data['input_path'],
                            "config": CFG,
                            "clean_mode": clean_mode,
                            "hook_y_pct": st.session_state.hook_y_pct,
                            "hook_color": st.session_state.hook_color,
                        },
                    )
                    st.toast("➕ Render encolado — se procesará tras los anteriores.", icon="🧵")
                    st.session_state.pop('cleaner_data', None)
                    time.sleep(0.4)
                    st.rerun()

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

        # Botones para audicionar cada voz favorita (cacheado en disco — la 2ª
        # vez no consume créditos MiniMax). Click → genera/reproduce muestra ~4s.
        # El hash del texto en el filename invalida la caché si cambias la frase.
        import hashlib as _hashlib
        _SAMPLE_TEXT = "4500 es lo que nos vamos a llevar con las ligas europeas."
        _sample_hash = _hashlib.md5(_SAMPLE_TEXT.encode("utf-8")).hexdigest()[:8]
        _samples_dir = os.path.join(CFG["paths"]["temp_folder"], "voice_samples")
        _favorites_only = [(lbl, vid) for lbl, vid in FAVORITE_VOICES.items()
                           if vid != "__CUSTOM__"]
        st.caption(f"🔊 Audicionar — frase de muestra: *\"{_SAMPLE_TEXT}\"* "
                   "(cacheado: 1ª vez consume crédito, después instantáneo)")
        cols_audicion = st.columns(len(_favorites_only))
        for idx_v, (lbl, vid) in enumerate(_favorites_only):
            short_lbl = lbl.split(" ")[1] if len(lbl.split(" ")) > 1 else lbl
            with cols_audicion[idx_v]:
                if st.button(
                    f"🔊 {short_lbl}",
                    key=f"voice_sample_btn_{vid}",
                    use_container_width=True,
                    help=f"Generar/reproducir muestra de {vid}",
                ):
                    sample_path = os.path.join(_samples_dir, f"{vid}_{_sample_hash}.mp3")
                    try:
                        from src.locutor import generate_voice_sample
                        with st.spinner(f"Generando muestra de {short_lbl}…"
                                        if not os.path.exists(sample_path)
                                        else f"Cargando {short_lbl}…"):
                            generate_voice_sample(vid, sample_path, sample_text=_SAMPLE_TEXT)
                        st.session_state["_pron_voice_sample_path"] = sample_path
                        st.session_state["_pron_voice_sample_name"] = short_lbl
                    except Exception as _se:
                        st.error(f"❌ Error muestra: {_se}")

        # Reproductor (autoplay) — solo se muestra cuando hay muestra preparada
        if st.session_state.get("_pron_voice_sample_path"):
            _sp = st.session_state["_pron_voice_sample_path"]
            if os.path.exists(_sp):
                st.audio(_sp, format="audio/mp3", autoplay=True)
                st.caption(f"▶️ Sonando: **{st.session_state.get('_pron_voice_sample_name','?')}** "
                           f"· `{os.path.basename(_sp)}`")

        add_subtitles = st.checkbox(
            "🔤 Quemar subtítulos karaoke",
            value=True,
            help="Whisper transcribe el audio del TTS y se queman subtítulos palabra a palabra.",
        )

        use_intro_folder = st.checkbox(
            "🎬 Usar carpeta `intro/` para la intro",
            value=False,
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

        # ── Editores de guion (uno por versión seleccionada — efímeros) ──
        # edited_scripts_map: vid (str) → texto editado actual
        # edits_status: vid (str) → bool (si difiere del original)
        edited_scripts_map: dict[str, str] = {}
        edits_status: dict[str, bool] = {}

        if len(selected_versions) <= 1:
            # Caso single: un solo text_area (igual que antes)
            v = chosen_version
            vid_key = str(v.get("id", "x"))
            original_script = v.get("script", "")
            edit_key = f"script_edit_{target_date_str}_{vid_key}"
            edited_script = st.text_area(
                "📜 Guion (editable solo en memoria — no se guarda en Redis)",
                value=original_script,
                height=240,
                key=edit_key,
                help="Edita el texto si quieres ajustar palabras, números o cambiar una frase. "
                     "Los cambios SOLO afectan al vídeo que generes ahora — no se persiste nada.",
            )
            edited_scripts_map[vid_key] = edited_script
            edits_status[vid_key] = (edited_script.strip() != original_script.strip())
            if edits_status[vid_key]:
                new_words = len(edited_script.split())
                old_words = len(original_script.split())
                delta = new_words - old_words
                st.info(f"✏️ Guion editado · {new_words} palabras "
                        f"({delta:+d} vs original) · NO se guardará en Redis")
            st.caption(f"Title: {v.get('title', '—')}")
        else:
            # Caso multi: una pestaña por versión, cada una con su propio text_area
            st.markdown(f"📜 **{len(selected_versions)} guiones seleccionados** — "
                        "edita cada uno en su pestaña (cambios efímeros, no se guardan en Redis):")
            tab_labels = [
                f"v{v.get('id', '?')} · {v.get('mode', '?')} · {v.get('word_count', '?')} pal"
                for v in selected_versions
            ]
            tabs = st.tabs(tab_labels)
            for tab, v in zip(tabs, selected_versions):
                with tab:
                    vid_key = str(v.get("id", "x"))
                    v_original = v.get("script", "")
                    v_edit_key = f"script_edit_{target_date_str}_{vid_key}"
                    v_edited = st.text_area(
                        f"Guion v{vid_key} (editable solo para esta generación)",
                        value=v_original,
                        height=220,
                        key=v_edit_key,
                    )
                    edited_scripts_map[vid_key] = v_edited
                    edits_status[vid_key] = (v_edited.strip() != v_original.strip())
                    if edits_status[vid_key]:
                        new_words = len(v_edited.split())
                        old_words = len(v_original.split())
                        delta = new_words - old_words
                        st.caption(f"✏️ Editado · {new_words} pal "
                                   f"({delta:+d} vs original) · solo en memoria")
                    else:
                        st.caption(f"Sin cambios · {len(v_original.split())} pal · "
                                   f"Title: {v.get('title', '—')}")

        # Compat con código de abajo: la primera versión sigue exponiendo
        # `edited_script` / `original_script` / `is_edited` para preview / metadatos.
        _first_v = selected_versions[0] if selected_versions else chosen_version
        _first_vid = str(_first_v.get("id", "x"))
        original_script = _first_v.get("script", "")
        edited_script = edited_scripts_map.get(_first_vid, original_script)
        is_edited = edits_status.get(_first_vid, False)
    else:
        st.info("👆 Pulsa 'Cargar guion del día' para previsualizar y elegir versión.")
        edited_script = ""
        original_script = ""
        is_edited = False
        edited_scripts_map = {}
        edits_status = {}

    # Botón único: encola N versiones a la cola global
    n_selected = len(selected_versions)
    btn_label = (
        f"➕ ENCOLAR {n_selected} VERSIÓN" if n_selected == 1 else
        f"➕ ENCOLAR {n_selected} VERSIONES" if n_selected > 1 else
        "➕ ENCOLAR (selecciona al menos 1)"
    )
    btn_run = st.button(
        btn_label, type="primary",
        disabled=n_selected == 0,
        use_container_width=True,
    )

    if btn_run:
        # Resolución (con safety pares)
        _res = res_options[selected_res_label]
        _w = _res[0] if _res[0] % 2 == 0 else _res[0] - 1
        _h = _res[1] if _res[1] % 2 == 0 else _res[1] - 1

        queue = get_queue(CFG["paths"]["temp_folder"])
        enqueued_count = 0
        for v in selected_versions:
            vid = v.get("id")
            _vid_key = str(vid) if vid is not None else "x"
            use_override = (
                edits_status.get(_vid_key, False)
                and edited_scripts_map.get(_vid_key)
            )
            _override_script = (
                edited_scripts_map.get(_vid_key) if use_override else None
            )
            title = (
                f"{target_date_str} · v{_vid_key} · {v.get('mode','?')}"
                + (" · ✏️ editado" if use_override else "")
            )
            params = {
                "target_date": target_date_str,
                "output_folder": CFG["paths"]["output_folder"],
                "video_size": (_w, _h),
                "voice_id_override": (voice_override.strip() or None),
                "publish_to_redis": publish_redis,
                "add_subtitles": add_subtitles,
                "use_intro_folder": use_intro_folder,
                "add_money_sfx": add_money_sfx,
                "sfx_volume": float(sfx_volume),
                "add_clink_sfx": add_clink_sfx,
                "clink_volume": float(clink_volume),
                "add_camera_sfx": add_camera_sfx,
                "camera_volume": float(camera_volume),
                "add_league_overlay": add_league_overlay,
                "league_overlay_duration": float(league_overlay_duration),
                "saturation": float(saturation),
                "show_pick_carousel": show_pick_carousel,
                "version_id": vid if vid != "legacy" else None,
                "script_override": _override_script,
                "add_background_music": add_background_music,
                "bgm_volume": float(bgm_volume),
            }
            queue.enqueue(JobMode.PRONOSTICOS, title, params)
            enqueued_count += 1

        st.toast(
            f"➕ {enqueued_count} pronóstico(s) encolado(s) — "
            "puedes cambiar de modo y encolar más, se procesarán en orden.",
            icon="🧵",
        )
        time.sleep(0.4)
        st.rerun()

    st.stop()

# ---------------------------------------------------------
# INTERFAZ SUBS AUTO (NICHO 4 — SUBTÍTULOS SOBRE VÍDEO INPUT)
# ---------------------------------------------------------
if CFG["app_mode"] == "SUBS_AUTO":
    st.header("🎬 Subtítulos Automáticos sobre Vídeo")
    st.info(
        "Sube un vídeo (cualquier aspect ratio), Whisper transcribe el audio palabra-a-palabra "
        "y se quema un overlay karaoke. Opcionalmente puedes pasar el guion / letra de la "
        "canción como referencia para guiar la transcripción (mejora vocabulario raro, nombres y letras musicales)."
    )

    subs_in_upload = st.file_uploader(
        "📂 Subir vídeo (MP4 / MOV / WEBM)",
        type=["mp4", "mov", "webm", "mkv"],
        key="subs_auto_upload",
    )

    if subs_in_upload:
        # Persistimos el upload a un fichero temporal una vez por upload (para
        # poder leer frames sin re-escribir en cada rerun de Streamlit).
        _upload_key = f"{subs_in_upload.name}_{subs_in_upload.size}"
        if st.session_state.get("sa_cached_upload_key") != _upload_key:
            _temp_dir = CFG["paths"]["temp_folder"]
            os.makedirs(_temp_dir, exist_ok=True)
            _cached_path = os.path.join(_temp_dir, f"sa_input_{int(time.time())}.mp4")
            with open(_cached_path, "wb") as _f:
                _f.write(subs_in_upload.getbuffer())
            st.session_state.sa_cached_input_path = _cached_path
            st.session_state.sa_cached_upload_key = _upload_key
        sa_cached_input_path = st.session_state.sa_cached_input_path

        col_prev, col_cfg = st.columns([0.7, 1.3])
        with col_prev:
            st.subheader("📺 Vídeo original")
            st.video(subs_in_upload)

        with col_cfg:
            st.subheader("⚙️ Transcripción")
            sa_model_size = st.selectbox(
                "🧠 Modelo Whisper",
                ["tiny", "base", "small", "medium", "large-v3"],
                index=2,
                help="Más grande = más preciso pero más lento. 'small' va fino para la mayoría de casos. "
                     "'medium' / 'large-v3' recomendado para letras de canciones o audio difícil.",
                key="sa_model_size",
            )

            sa_lang_label = st.selectbox(
                "🌍 Idioma",
                ["Auto-detectar", "Español (es)", "English (en)", "Français (fr)", "Português (pt)",
                 "Italiano (it)", "Deutsch (de)", "日本語 (ja)", "한국어 (ko)"],
                index=1,
                help="Si lo sabes, fíjalo: la transcripción es más rápida y precisa.",
                key="sa_lang_label",
            )
            _lang_map = {
                "Auto-detectar": None, "Español (es)": "es", "English (en)": "en",
                "Français (fr)": "fr", "Português (pt)": "pt", "Italiano (it)": "it",
                "Deutsch (de)": "de", "日本語 (ja)": "ja", "한국어 (ko)": "ko",
            }
            sa_language = _lang_map[sa_lang_label]

            sa_audio_type_label = st.radio(
                "🎚️ Tipo de audio",
                ["🗣️ Voz hablada", "🎵 Música / canción"],
                index=0,
                horizontal=True,
                key="sa_audio_type_label",
                help=("• **Voz hablada**: VAD activo (corta silencios largos), Whisper usa "
                      "contexto previo. Bueno para podcasts, vídeos hablados, entrevistas.\n\n"
                      "• **Música / canción**: VAD DESACTIVADO + sin condicionamiento previo. "
                      "Imprescindible para canciones — si no, los interludios musicales "
                      "se interpretan como silencio y Whisper deja de transcribir a mitad."),
            )
            sa_audio_type = "music" if "Música" in sa_audio_type_label else "speech"

            sa_pause_for_edit = st.checkbox(
                "✏️ Pausar tras transcribir para editar palabras",
                value=False,
                key="sa_pause_for_edit",
                help="Si está activo, después de transcribir verás un editor donde "
                     "puedes corregir manualmente las palabras que Whisper haya pillado mal. "
                     "Los timestamps se preservan (1:1 si no cambias el nº de palabras; "
                     "se redistribuyen proporcionalmente si añades/quitas).",
            )

            sa_use_reference = st.checkbox(
                "📖 Pasarle el guion / letra como referencia",
                value=False,
                help=("Whisper usará el texto como `initial_prompt` para sesgar la transcripción.\n\n"
                      "✅ **Mejora**: ortografía, nombres propios, jerga específica.\n\n"
                      "⚠️ **Trade-off para canciones**: a veces hace que Whisper *anticipe* "
                      "palabras y los timestamps se adelanten. Si notas la marca llegando "
                      "antes de la palabra cantada, prueba a desactivarlo o usa el slider "
                      "'Sync offset' para corregir.\n\n"
                      "NO es alineación forzada — Whisper sigue escuchando y puede añadir/"
                      "quitar palabras si difieren mucho."),
                key="sa_use_reference",
            )
            if sa_use_reference:
                sa_reference_text = st.text_area(
                    "Guion / letra de referencia",
                    placeholder="Pega aquí el guion o la letra de la canción tal cual se pronuncia…",
                    height=140,
                    key="sa_reference_text",
                )
            else:
                sa_reference_text = ""

        st.divider()

        # Aplicar preset PENDIENTE antes de renderizar los widgets de estilo
        # (se setea en session_state desde la galería de presets más abajo).
        if "_sa_pending_preset" in st.session_state:
            from src.subtitles_only import (
                FONT_OPTIONS as _APPLY_FONTS,
                HIGHLIGHT_MODES as _APPLY_HMODES,
            )
            _font_to_label = {v: k for k, v in _APPLY_FONTS.items()}
            _hmode_to_label = {v: k for k, v in _APPLY_HMODES.items()}
            _pending = st.session_state.pop("_sa_pending_preset")
            for _k, _v in _pending.items():
                if _k == "font_path":
                    # Selectbox guarda el label, no el path
                    if _v in _font_to_label:
                        st.session_state["sa_font_label"] = _font_to_label[_v]
                elif _k == "highlight_mode":
                    if _v in _hmode_to_label:
                        st.session_state["sa_hmode_label"] = _hmode_to_label[_v]
                else:
                    st.session_state[f"sa_{_k}"] = _v

        # ---------- ESTILO + POSICIÓN (sliders + preview live) ----------
        st.subheader("🎨 Estilo y posición de subtítulos")

        from src.subtitles_only import FONT_OPTIONS as _SA_FONTS, HIGHLIGHT_MODES as _SA_HMODES

        # Fila superior: tipografía + modo de marcado de la palabra activa
        col_top1, col_top2 = st.columns(2)
        with col_top1:
            sa_font_label = st.selectbox(
                "🔤 Tipografía",
                list(_SA_FONTS.keys()),
                index=0,
                key="sa_font_label",
                help="Fuentes TTF instaladas en Windows. Cambia el carácter visual completo del subtítulo.",
            )
            sa_font_path = _SA_FONTS[sa_font_label]
        with col_top2:
            sa_hmode_label = st.selectbox(
                "✨ Modo de marcado de la palabra activa",
                list(_SA_HMODES.keys()),
                index=0,
                key="sa_hmode_label",
                help="Cómo se distingue visualmente la palabra que se está pronunciando: "
                     "píldora rellena, cambio de color, subrayado, recuadro hueco, halo glow o sin marca.",
            )
            sa_highlight_mode = _SA_HMODES[sa_hmode_label]

        col_st1, col_st2, col_st3 = st.columns(3)
        with col_st1:
            sa_highlight_color = st.color_picker(
                "Color highlight", value="#1E01C4", key="sa_highlight_color",
                help="Color del marcado (píldora / subrayado / recuadro / glow / palabra activa en color_swap).",
            )
            sa_text_color = st.color_picker(
                "Color del texto", value="#FFFFFF", key="sa_text_color")
            sa_pill_enabled = st.checkbox(
                "Píldora detrás (legacy)", value=True, key="sa_pill_enabled",
                help="Compat antigua. El selector '✨ Modo de marcado' de arriba tiene prioridad.",
            )
        with col_st2:
            sa_stroke_color = st.color_picker(
                "Color del borde", value="#000000", key="sa_stroke_color")
            sa_stroke_width = st.slider(
                "Grosor del borde", 0, 8, 3, key="sa_stroke_width")
            sa_case = st.selectbox(
                "Formato del texto",
                ["UPPERCASE", "lowercase", "Title Case", "original"],
                index=0,
                key="sa_case",
            )
        with col_st3:
            sa_font_scale = st.slider(
                "Tamaño de fuente (% del alto del vídeo)",
                0.025, 0.100, 0.045, 0.005,
                key="sa_font_scale",
            )
            sa_max_words = st.slider(
                "Palabras por bloque (chunk)", 1, 6, 3, key="sa_max_words",
                help="Cuántas palabras se ven A LA VEZ en pantalla. La transcripción "
                     "se trocea en grupos de N (o menos si hay pausa larga >2.5s entre palabras). "
                     "↓ Bajar = más cambios rápidos, mejor sincronía con la voz. "
                     "↑ Subir = más texto a la vez, menos cambios. El preview también lo respeta.",
            )
            sa_y_position = st.slider(
                "Posición vertical (% del alto)",
                0.05, 0.95, 0.78, 0.01,
                key="sa_y_position",
                help="0.10 = casi arriba · 0.50 = centro · 0.78 = recomendado para 9:16 "
                     "(zona inferior tipo TikTok) · 0.90 = muy abajo.",
            )
            sa_max_width = st.slider(
                "Ancho máximo del texto (% del ancho)",
                0.30, 1.00, 0.85, 0.05,
                key="sa_max_width",
                help="Limita lo ancho que puede crecer el bloque de subtítulos. "
                     "Si la frase no cabe, salta a la línea siguiente. "
                     "0.50 = muy estrecho (más líneas) · 0.85 = recomendado · "
                     "1.00 = casi todo el ancho del vídeo. Margen lateral = (1 - este valor) / 2 a cada lado.",
            )
            sa_sync_offset = st.slider(
                "🎯 Sync offset (ms)",
                -800, 800, 0, 25,
                key="sa_sync_offset",
                help=("Desplaza TODOS los subtítulos en el tiempo para corregir desincronización.\n\n"
                      "• **Negativo (-)** → adelantar el highlight (aparece antes).\n"
                      "• **Positivo (+)** → retrasar el highlight (aparece después).\n\n"
                      "Si ves la palabra marcada *antes* de cantarla → usa **+150 a +300 ms** "
                      "(típico con canciones + letra de referencia).\n"
                      "Si llega *tarde* → usa valores negativos.\n\n"
                      "Whisper estima los timestamps por atención, no son exactos: en música "
                      "se suelen adelantar 100-300ms. Modelos `medium`/`large-v3` tienen "
                      "timestamps más precisos que `base`/`small`."),
            )

        # ---------- PREVIEW WYSIWYG sobre un frame real del vídeo ----------
        st.markdown("**👀 Vista previa sobre el vídeo**")
        try:
            from src.subtitles_only import (
                render_video_frame_with_subtitle,
                get_video_duration,
            )

            sa_video_dur = get_video_duration(sa_cached_input_path) or 1.0
            col_pv1, col_pv2 = st.columns([3, 2])
            with col_pv1:
                sa_preview_time = st.slider(
                    "⏱️ Momento del vídeo (segundos)",
                    min_value=0.0,
                    max_value=max(0.5, sa_video_dur - 0.1),
                    value=min(1.0, sa_video_dur / 2),
                    step=0.5,
                    key="sa_preview_time",
                    help="Mueve para ver el subtítulo sobre distintos frames del vídeo.",
                )
            with col_pv2:
                sa_preview_text = st.text_input(
                    "Texto de muestra",
                    value="HELLO FROM THE OTHER SIDE",
                    key="sa_preview_text",
                    help="Frase de muestra para previsualizar — la real saldrá de la transcripción.",
                )

            sa_preview_style = {
                "font_path": sa_font_path,
                "highlight_mode": sa_highlight_mode,
                "highlight_color": sa_highlight_color,
                "text_color": sa_text_color,
                "stroke_color": sa_stroke_color,
                "stroke_width": sa_stroke_width,
                "case_mode": sa_case,
                "font_scale": sa_font_scale,
                "max_words_per_chunk": sa_max_words,
                "y_position_pct": sa_y_position,
                "pill_enabled": sa_pill_enabled,
                "max_width_pct": sa_max_width,
            }
            sa_words_count = max(1, len((sa_preview_text or "PREVIEW").split()))
            sa_highlight_idx = min(sa_words_count // 2, sa_words_count - 1)

            sa_preview_img = render_video_frame_with_subtitle(
                sa_cached_input_path,
                sa_preview_style,
                sample_text=sa_preview_text or "PREVIEW",
                highlight_word_index=sa_highlight_idx,
                frame_time=sa_preview_time,
                draw_width_guides=True,
            )
            _, col_show, _ = st.columns([1, 2, 1])
            with col_show:
                st.image(
                    sa_preview_img, use_container_width=True,
                    caption=(f"t = {sa_preview_time:.1f}s · resolución original · "
                             f"📐 líneas amarillas = ancho máximo {int(sa_max_width*100)}%"),
                )
        except Exception as e:
            st.warning(f"⚠️ Preview no disponible: {e}")

        # ---------- GALERÍA DE PRESETS DE ESTILO ----------
        with st.expander("🎨 Comparar estilos rápidos (clic en 'Aplicar' para usar uno)", expanded=True):
            try:
                from src.subtitles_only import STYLE_PRESETS as _SA_PRESETS

                preset_items = list(_SA_PRESETS.items())
                # 3 cols × 2 rows
                cols_a = st.columns(3)
                cols_b = st.columns(3)
                all_cols = list(cols_a) + list(cols_b)

                _gal_text = sa_preview_text or "GOL DE LOCURA"
                _gal_words = max(1, len(_gal_text.split()))
                _gal_hl = min(_gal_words // 2, _gal_words - 1)
                _gal_t = sa_preview_time

                for i, (preset_name, preset_style) in enumerate(preset_items):
                    target_col = all_cols[i] if i < len(all_cols) else cols_b[i % 3]
                    with target_col:
                        try:
                            gal_img = render_video_frame_with_subtitle(
                                sa_cached_input_path,
                                preset_style,
                                sample_text=_gal_text,
                                highlight_word_index=_gal_hl,
                                frame_time=_gal_t,
                            )
                            st.image(gal_img, use_container_width=True, caption=preset_name)
                        except Exception as _ge:
                            st.caption(f"{preset_name} · ⚠️ {_ge}")

                        def _apply_preset(p=preset_style):
                            st.session_state._sa_pending_preset = p

                        st.button(
                            "📝 Aplicar",
                            key=f"sa_apply_preset_{i}",
                            on_click=_apply_preset,
                            use_container_width=True,
                        )
            except Exception as _e:
                st.warning(f"Galería no disponible: {_e}")

        st.divider()

        # ---------- ESTADO PARA FLUJO PAUSAR-Y-EDITAR ----------
        st.session_state.setdefault("sa_pending_edit", None)

        # Logger custom: mapea progreso de moviepy a una franja [lo, hi] de una pb global
        class _ScaledRenderLogger(ProgressBarLogger):
            def __init__(self, pb, timer_ph, lo: int = 0, hi: int = 100):
                super().__init__(init_state=None, bars=None, ignored_bars=None,
                                 logged_bars='all', min_time_interval=0, ignore_bars_under=0)
                self.pb = pb
                self.timer_ph = timer_ph
                self.lo = lo
                self.hi = hi
                self.start_time = time.time()

            def callback(self, **changes):
                elapsed = int(time.time() - self.start_time)
                mins, secs = divmod(elapsed, 60)
                self.timer_ph.markdown(f"⏱️ **Render:** {mins:02d}:{secs:02d}")
                for bar in changes.get('bars', []):
                    if 'total' in self.bars[bar]:
                        cur = self.bars[bar]['index']
                        tot = self.bars[bar]['total']
                        if tot > 0:
                            frac = max(0.0, min(1.0, cur / tot))
                            overall = self.lo + int((self.hi - self.lo) * frac)
                            self.pb.progress(
                                overall,
                                text=f"🎞️ Renderizando overlay… {int(frac * 100)}%",
                            )

        # ---------- HELPER: corre solo el render + muestra resultado ----------
        # Lee estilos/calidad de los widgets actuales (permite tweaking entre transcribir y renderizar).
        def _sa_run_render(input_path: str, words: list, out_path: str, out_name: str, t_start: float):
            from src.subtitles_only import (
                QUALITY_FROM_SIDEBAR as _SA_QMAP,
                render_subtitles_on_video,
            )
            sa_quality_settings = _SA_QMAP.get(
                selected_res_label,
                {"preset": "medium", "crf": 20, "max_long_side": 1280},
            )
            sa_style = {
                "font_path": sa_font_path,
                "highlight_mode": sa_highlight_mode,
                "highlight_color": sa_highlight_color,
                "text_color": sa_text_color,
                "stroke_color": sa_stroke_color,
                "stroke_width": sa_stroke_width,
                "case_mode": sa_case,
                "font_scale": sa_font_scale,
                "max_words_per_chunk": sa_max_words,
                "y_position_pct": sa_y_position,
                "pill_enabled": sa_pill_enabled,
                "max_width_pct": sa_max_width,
                "sync_offset_ms": sa_sync_offset,
            }

            sa_pb = st.progress(0, text=f"🎞️ Preparando overlay ({selected_res_label})…")
            sa_render_timer = st.empty()

            with st.status("🎬 Renderizando…", expanded=True) as status:
                try:
                    status.write(
                        f"🎞️ Calidad sidebar: {selected_res_label} → "
                        f"preset={sa_quality_settings['preset']}, crf={sa_quality_settings['crf']}"
                    )
                    t2 = time.time()
                    render_subtitles_on_video(
                        input_path, words, sa_style, out_path,
                        quality_settings=sa_quality_settings,
                        log_callback=lambda m: status.write(f"   ↳ {m}"),
                        logger=_ScaledRenderLogger(sa_pb, sa_render_timer, lo=0, hi=100),
                    )
                    status.write(f"   ↳ ✅ Render completo ({format_seconds(time.time()-t2)})")
                    sa_pb.progress(100, text="✨ Vídeo con subtítulos listo")
                    sa_render_timer.empty()

                    status.update(label="✨ ¡Vídeo con subtítulos listo!", state="complete")

                    st.success(f"🎉 Guardado: `{out_path}`")
                    col_v, col_d = st.columns([1, 1])
                    with col_v:
                        st.video(out_path)
                    with col_d:
                        st.text_input("Archivo:", value=out_name, disabled=True,
                                      key=f"sa_outname_{out_name}")
                        st.write(f"⏱️ Tiempo total: {format_seconds(time.time()-t_start)}")
                        st.write(f"📂 Ruta: `{out_path}`")
                        if st.button("📂 Abrir carpeta", key=f"sa_open_{out_name}"):
                            try:
                                os.startfile(os.path.dirname(out_path))
                            except Exception:
                                st.warning("No se pudo abrir la carpeta.")

                    if sound_on:
                        try: winsound.MessageBeep(winsound.MB_ICONASTERISK)
                        except Exception: pass
                except Exception as e:
                    status.update(label=f"❌ Error: {e}", state="error")
                    st.expander("🔍 Detalle técnico").code(traceback.format_exc())

        # ---------- HELPERS PARA ENCOLAR ----------
        def _sa_build_params(input_path: str, out_path: str,
                             quality_label: str, edited_text: str | None = None) -> dict:
            """Construye el dict de params para el runner subs_auto."""
            return {
                "input_path": input_path,
                "out_path": out_path,
                "config": CFG,
                "quality_label": quality_label,
                "model_size": sa_model_size,
                "language": sa_language,
                "audio_type": sa_audio_type,
                "reference_text": sa_reference_text,
                "edited_text": edited_text,
                "font_path": sa_font_path,
                "highlight_mode": sa_highlight_mode,
                "highlight_color": sa_highlight_color,
                "text_color": sa_text_color,
                "stroke_color": sa_stroke_color,
                "stroke_width": sa_stroke_width,
                "case_mode": sa_case,
                "font_scale": sa_font_scale,
                "max_words": sa_max_words,
                "y_position": sa_y_position,
                "pill_enabled": sa_pill_enabled,
                "max_width": sa_max_width,
                "sync_offset": sa_sync_offset,
            }

        # ---------- BOTÓN PRINCIPAL ----------
        st.markdown("")
        # Si pause_for_edit está ON, primero hay que transcribir síncrono para
        # mostrar el editor; el render final se encolará después.
        # Si está OFF, encolamos directamente (worker transcribe + render).
        if sa_pause_for_edit:
            btn_label = "🎙️ TRANSCRIBIR PARA EDITAR PALABRAS"
        else:
            btn_label = "➕ ENCOLAR SUBTÍTULOS"

        if st.button(btn_label, type="primary", use_container_width=True, key="sa_generate"):
            temp_dir = CFG["paths"]["temp_folder"]
            os.makedirs(temp_dir, exist_ok=True)
            ts_label = int(time.time())
            input_path = os.path.join(temp_dir, f"subs_in_{ts_label}.mp4")
            with open(input_path, "wb") as f:
                f.write(subs_in_upload.getbuffer())

            output_folder = os.path.join(CFG["paths"]["output_folder"], "SUBS_AUTO")
            os.makedirs(output_folder, exist_ok=True)
            out_name = f"SUBS_AUTO_{ts_label}.mp4"
            out_path = os.path.join(output_folder, out_name)

            if not sa_pause_for_edit:
                # Encolar directo: worker hace todo
                queue = get_queue(CFG["paths"]["temp_folder"])
                queue.enqueue(
                    JobMode.SUBS_AUTO,
                    title=f"{subs_in_upload.name} · {sa_model_size}",
                    params=_sa_build_params(input_path, out_path, selected_res_label),
                )
                st.toast("➕ Subtítulos encolados.", icon="🧵")
                time.sleep(0.4)
                st.rerun()
            else:
                # Transcribir síncrono para que el usuario pueda editar palabras
                from src.subtitles_only import (
                    extract_audio_from_video, transcribe_with_reference,
                )
                tmp_audio = os.path.join(temp_dir, f"subs_audio_{ts_label}.mp3")
                with st.status("🎙️ Transcribiendo para editar…", expanded=True) as status:
                    try:
                        t0 = time.time()
                        status.write("🔊 Extrayendo audio…")
                        extract_audio_from_video(input_path, tmp_audio)
                        status.write(f"🎙️ Whisper '{sa_model_size}'…")
                        sa_words = transcribe_with_reference(
                            tmp_audio,
                            reference_script=sa_reference_text if sa_reference_text.strip() else None,
                            model_size=sa_model_size,
                            language=sa_language,
                            audio_type=sa_audio_type,
                        )
                        if not sa_words:
                            raise RuntimeError("Whisper no detectó palabras")
                        status.update(label=f"✅ {len(sa_words)} palabras", state="complete")
                    except Exception as e:
                        status.update(label=f"❌ {e}", state="error")
                        st.expander("🔍 Detalle").code(traceback.format_exc())
                        sa_words = None
                    finally:
                        try: os.remove(tmp_audio)
                        except Exception: pass

                if sa_words:
                    st.session_state.sa_pending_edit = {
                        "input_path": input_path,
                        "out_path": out_path,
                        "out_name": out_name,
                        "words": sa_words,
                        "quality_label": selected_res_label,
                    }
                    if "sa_edit_text" in st.session_state:
                        del st.session_state["sa_edit_text"]
                    st.toast("✏️ Edita las palabras y pulsa Encolar render.")
                    st.rerun()

        # ---------- EDITOR DE PALABRAS (se muestra si hay edit pendiente) ----------
        if st.session_state.get("sa_pending_edit"):
            pe = st.session_state["sa_pending_edit"]
            st.divider()
            st.subheader("✏️ Editar transcripción antes de renderizar")
            st.caption(
                f"Whisper detectó **{len(pe['words'])} palabras**. Corrige las que estén mal "
                "(typos, palabras inventadas en música, jerga). Si conservas el mismo número "
                "de palabras, los timestamps se mantienen exactos. Si añades o quitas, se "
                "redistribuyen proporcionalmente sobre el rango temporal original."
            )

            # Inicializar textarea desde la transcripción al primer render del editor
            if "sa_edit_text" not in st.session_state:
                st.session_state["sa_edit_text"] = " ".join(w["word"] for w in pe["words"])

            edited_text = st.text_area(
                "Transcripción (edita las palabras incorrectas)",
                height=240,
                key="sa_edit_text",
            )
            new_count = len([w for w in (edited_text or "").split() if w.strip()])
            orig_count = len(pe["words"])
            if new_count == orig_count:
                st.success(f"✅ {new_count} palabras (igual que el original) — timestamps preservados 1:1.")
            else:
                delta = new_count - orig_count
                st.warning(
                    f"⚠️ {new_count} palabras vs {orig_count} originales (Δ {delta:+d}) — "
                    "los timestamps se redistribuirán proporcionalmente."
                )

            col_ea, col_eb, col_ec = st.columns([2, 1, 1])
            with col_ea:
                go_render = st.button(
                    "➕ ENCOLAR RENDER",
                    type="primary", use_container_width=True, key="sa_render_after_edit",
                )
            with col_eb:
                if st.button("↩️ Restaurar original", use_container_width=True, key="sa_restore_text"):
                    st.session_state["sa_edit_text"] = " ".join(w["word"] for w in pe["words"])
                    st.rerun()
            with col_ec:
                if st.button("🗑️ Cancelar", use_container_width=True, key="sa_cancel_edit"):
                    st.session_state.sa_pending_edit = None
                    if "sa_edit_text" in st.session_state:
                        del st.session_state["sa_edit_text"]
                    st.rerun()

            if go_render:
                # Encolamos el render con edited_text. El runner transcribirá
                # de nuevo (rápido en local) y aplicará el merge con la
                # edición. Trabajo redundante mínimo a cambio de tener
                # toda la cola unificada.
                queue = get_queue(CFG["paths"]["temp_folder"])
                queue.enqueue(
                    JobMode.SUBS_AUTO,
                    title=f"{os.path.basename(pe['input_path'])} · ✏️ editado",
                    params=_sa_build_params(
                        pe["input_path"], pe["out_path"],
                        pe.get("quality_label", selected_res_label),
                        edited_text=edited_text,
                    ),
                )
                st.toast("➕ Render encolado.", icon="🧵")
                st.session_state.sa_pending_edit = None
                if "sa_edit_text" in st.session_state:
                    del st.session_state["sa_edit_text"]
                time.sleep(0.4)
                st.rerun()

    st.stop()

# ---------------------------------------------------------
# MODO PRESIDENTES — único flujo (Auto IA). El antiguo modo Manual
# (subir carpetas de audios manualmente) se eliminó: nunca se usaba
# y duplicaba lógica con el flow Auto.
# ---------------------------------------------------------
if True:
    # 1. CONFIGURACIÓN DE LOTE — fila compacta
    c1, c2 = st.columns([1, 2])
    with c1:
        cantidad = st.number_input(
            "Vídeos", min_value=1, max_value=10, value=1, step=1,
            help="Cuántos vídeos generar en este lote.",
        )
    with c2:
        st.write("")  # alinear vertical con el number_input
        use_creative_mode = st.checkbox(
            "✨ Modo creativo",
            value=False,
            help="Hooks y CTAs dinámicos variados por IA.",
        )

    # Inputs dinámicos: 2 columnas en desktop, apiladas en móvil
    queue_inputs = []
    grid_cols = st.columns(2)
    for i in range(cantidad):
        col_idx = i % 2
        with grid_cols[col_idx]:
            st.markdown(f"**🎬 Vídeo {i+1}**")

            # Fila compacta: Top + Prefijo (50/50). Wrapper con key para
            # que el CSS móvil mantenga estas 2 cols en línea — la regla
            # global de mobile_ui.py apilaría ambos al 100% si no.
            with st.container(key=f"compact_row_{i}"):
                s1, s2 = st.columns(2)
                with s1:
                    top_count = st.selectbox(
                        "Top",
                        [5, 4, 3],
                        key=f"top_count_{i}",
                        help="Nº de presidentes del ranking.",
                    )
                with s2:
                    prefix_word = st.selectbox(
                        "Prefijo",
                        ["The", "Top"],
                        key=f"prefix_word_{i}",
                    )

            # Tema (input principal, full-width)
            topic = st.text_input(
                "Tema",
                key=f"topic_{i}",
                placeholder="worst / corruption / richest (vacío = aleatorio)",
                label_visibility="collapsed",
            )

            # Checkboxes opcionales
            include_history = st.checkbox(
                'Añadir "in US history"',
                value=True,
                key=f"history_{i}",
            )
            include_hook = st.checkbox(
                "Incluir hook",
                value=True,
                key=f"hook_{i}",
                help='Frase "Save this video before they delete it..." tras el título.',
            )

            # Preview del título completo construido (caption pequeña)
            title_prefix = f"{prefix_word} {top_count}"
            suffix_display = " in US history" if include_history else ""
            preview_topic = (topic.strip() or "[aleatorio]")
            st.caption(
                f"📢 *{title_prefix} {preview_topic} Presidents{suffix_display}*"
            )

            queue_inputs.append({
                "topic": topic,
                "prefix": title_prefix,
                "top_count": top_count,
                "include_history": include_history,
                "include_hook": include_hook,
            })

    # Botón de Acción — encola N vídeos a la cola global
    if st.button(f"➕ ENCOLAR {len(queue_inputs)} VÍDEO(S)",
                 type="primary", use_container_width=True):
        # Pre-flight check rápido (las APIs deben estar arriba)
        with st.status("🩺 Verificando APIs…", expanded=False) as _ck:
            ok = check_api_health(ui_callback=lambda m: _ck.write(m))
            if not ok:
                _ck.update(label="❌ APIs no disponibles", state="error")
                st.error("⚠️ ABORTANDO encolado: una o más APIs no responden.")
                st.stop()
            _ck.update(label="✅ APIs OK", state="complete")

        # Resolución (con safety pares)
        target_res = res_options[selected_res_label]
        w_safe = target_res[0] if target_res[0] % 2 == 0 else target_res[0] - 1
        h_safe = target_res[1] if target_res[1] % 2 == 0 else target_res[1] - 1
        CFG["video_settings"]["resolution"] = [w_safe, h_safe]

        queue = get_queue(CFG["paths"]["temp_folder"])
        for video_cfg in queue_inputs:
            user_topic = video_cfg["topic"]
            current_topic = (
                user_topic.strip() if user_topic and user_topic.strip() else None
            )
            topic_display = current_topic or "🎲 Aleatorio"
            title = (
                f"{video_cfg['prefix']} · {topic_display} · "
                f"top {video_cfg['top_count']}"
            )
            params = {
                "config": CFG,
                "topic": current_topic,
                "creative_mode": use_creative_mode,
                "title_prefix": video_cfg["prefix"],
                "top_count": video_cfg["top_count"],
                "include_history": video_cfg["include_history"],
                "include_hook": video_cfg["include_hook"],
                "engine_version": engine_version,
                "subs_enabled": subs_enabled,
                "subs_highlight_color": subs_highlight_color,
                "subs_text_color": subs_text_color,
                "subs_stroke_color": subs_stroke_color,
                "subs_stroke_width": subs_stroke_width,
                "subs_case": subs_case,
                "subs_font_scale": subs_font_scale,
                "subs_max_words": subs_max_words,
                "subs_y_position": subs_y_position,
                "hook_enabled": hook_enabled,
                "hook_duration": hook_duration,
                "hook_animation": hook_animation,
                "hook_y_position": hook_y_position,
                "hook_shadow_color": hook_shadow_color,
                "hook_box_color": hook_box_color,
                "hook_text_color": hook_text_color,
                "hook_font_scale": hook_font_scale,
            }
            queue.enqueue(JobMode.PRESIDENTS, title, params)

        st.toast(
            f"➕ {len(queue_inputs)} vídeo(s) de Presidentes encolado(s) — "
            "se procesarán en orden FIFO. Puedes cambiar de modo y encolar más.",
            icon="🧵",
        )
        time.sleep(0.4)
        st.rerun()