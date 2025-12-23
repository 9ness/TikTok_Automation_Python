
import os
import math
import numpy as np
from moviepy.editor import *
from moviepy.audio.fx.all import audio_fadeout
from PIL import Image, ImageFilter, ImageOps
import random
import math
import glob

# ==========================================
# EASING FUNCTIONS
# ==========================================

def ease_out_quad(t): return t * (2 - t)
def ease_in_quad(t): return t * t
def smoothstep(t): return t * t * (3 - 2 * t)
def lerp(a, b, t): return a + (b - a) * t

# ==========================================
# CONSTANTS
# ==========================================
DIR_RIGHT = 1
DIR_LEFT = 2
DIR_UP = 3
DIR_DOWN = 4
DIR_CENTER = 5

# ==========================================
# 🔒 LÓGICA V1 ESTABLE - NO TOCAR - (Flow corregido, Zoom solo inicio, Cero bordes negros)
# ==========================================
def create_smart_combo_clip_v1_stable(image_path, total_dur, resolution, prev_exit_dir, is_first_clip=False):
    W, H = resolution
    
    # 1. READ & EXIF FIX
    try:
        pil_img = Image.open(image_path)
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception as e:
        print(f"Error {e}")
        return ColorClip(size=resolution, color=(0,0,0), duration=total_dur), prev_exit_dir

    # 2. ALGORITMO 'COVER' 1.28x
    img_w, img_h = pil_img.size
    
    ratio_w = W / img_w
    ratio_h = H / img_h
    
    max_ratio = max(ratio_w, ratio_h)
    
    # Safety Factor 1.28
    final_scale = max_ratio * 1.28
    
    new_w = int(img_w * final_scale)
    new_h = int(img_h * final_scale)
    
    pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    base_clip = ImageClip(np.array(pil_img)).set_duration(total_dur)
    
    # 3. CALCULATE EXCESS
    excess_x = new_w - W
    excess_y = new_h - H
    
    min_x = -excess_x
    max_x = 0
    min_y = -excess_y
    max_y = 0
    center_x = min_x / 2
    center_y = min_y / 2
    
    # DEFINE BOUNCE LOGIC (Only for First Clip now)
    def create_bounce_clip(clip, duration):
        clip = clip.set_position("center")
        def bounce_func(t):
            if duration == 0: return 1.0
            p = min(t / duration, 1.0)
            boost = 0.35
            if p < 0.5:
                local_p = p * 2.0
                val = local_p * (2.0 - local_p)
                return lerp(1.0 + boost, 1.0, val)
            else:
                local_p = (p - 0.5) * 2.0
                val = local_p * local_p
                return lerp(1.0, 1.0 + boost, val)
        zoomed = clip.resize(bounce_func)
        return CompositeVideoClip([zoomed], size=resolution).set_duration(duration)

    # SPECIAL: FIRST CLIP (Apply Bounce)
    if is_first_clip:
        final_clip = create_bounce_clip(base_clip, total_dur)
        return final_clip, DIR_CENTER

    # 4. START POINT (CONTINUITY - CORRECTED)
    if prev_exit_dir == DIR_RIGHT:
        start_pos = (max_x, center_y) 
    elif prev_exit_dir == DIR_LEFT:
        start_pos = (min_x, center_y) 
    elif prev_exit_dir == DIR_UP:
        start_pos = (center_x, max_y) 
    elif prev_exit_dir == DIR_DOWN:
        start_pos = (center_x, min_y)
    else:
        start_pos = random.choice([
            (min_x, center_y), (max_x, center_y),
            (center_x, min_y), (center_x, max_y)
        ])

    # 5. END POINT (RANDOM COMBO - LINEAR ONLY)
    modes = ["EXIT_RIGHT", "EXIT_LEFT", "EXIT_UP", "EXIT_DOWN"]
    mode = random.choice(modes)
    
    end_pos = (center_x, center_y)
    exit_choice = DIR_CENTER
    
    if mode == "EXIT_RIGHT":
        end_pos = (min_x, center_y)
        exit_choice = DIR_RIGHT
    elif mode == "EXIT_LEFT":
        end_pos = (max_x, center_y)
        exit_choice = DIR_LEFT
    elif mode == "EXIT_UP":
        end_pos = (center_x, max_y)
        exit_choice = DIR_UP
    elif mode == "EXIT_DOWN":
        end_pos = (center_x, min_y)
        exit_choice = DIR_DOWN

    mid_pos = (center_x, center_y)

    # 6. ANIMATION FUNC (2 PHASES: RELAY)
    def pos_func(t):
        if total_dur == 0: return start_pos
        p = min(t / total_dur, 1.0)
        
        if p < 0.5:
            local_p = p * 2.0
            val = local_p * (2.0 - local_p)
            curr_x = lerp(start_pos[0], mid_pos[0], val)
            curr_y = lerp(start_pos[1], mid_pos[1], val)
        else:
            local_p = (p - 0.5) * 2.0
            val = local_p * local_p
            curr_x = lerp(mid_pos[0], end_pos[0], val)
            curr_y = lerp(mid_pos[1], end_pos[1], val)
            
        # FINAL CLAMP
        curr_x = max(min_x, min(max_x, curr_x))
        curr_y = max(min_y, min(max_y, curr_y))
            
        return int(curr_x), int(curr_y)
        
    final_clip = CompositeVideoClip([base_clip.set_position(pos_func)], size=resolution).set_duration(total_dur)
    
    return final_clip, exit_choice

# ==========================================
# 🧪 LÓGICA V2 BETA - EXPERIMENTAL (Para futuras mejoras)
# ==========================================
def create_smart_combo_clip_v2_estable(image_path, total_dur, resolution, prev_exit_dir, is_first_clip=False, is_last_clip=False):
    """
    MOTOR V2 (HYBRID OPT - 2025):
    - First/Last Clips (Zoom): FULL 3x3 GRID to ensure safe coverage during scale changes.
    - Middle Clips (Slide): DYNAMIC GRID (Optimized) based on flow.
    - Safety: Auto-fill vertical bounds for landscape images.
    """
    W, H = resolution
    
    # 1. CARGA
    try:
        pil_img = Image.open(image_path)
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception as e:
        print(f"Error loading {image_path}: {e}")
        return ColorClip(size=resolution, color=(0,0,0), duration=total_dur), prev_exit_dir

    img_w, img_h = pil_img.size

    # ===============================
    # DEFINIR ESCALA 1.0 (Ancho de Pantalla)
    # ===============================
    master_scale = W / img_w
    final_w = int(img_w * master_scale)
    final_h = int(img_h * master_scale)
    
    base_img = pil_img.resize((final_w, final_h), Image.Resampling.LANCZOS)
    
    # ===============================
    # DECISIÓN DE DIRECCIONES
    # ===============================
    
    # 1. INPUT
    enter_dir = DIR_RIGHT # Default
    if prev_exit_dir == DIR_LEFT: enter_dir = DIR_RIGHT
    elif prev_exit_dir == DIR_RIGHT: enter_dir = DIR_LEFT
    elif prev_exit_dir == DIR_UP: enter_dir = DIR_DOWN
    elif prev_exit_dir == DIR_DOWN: enter_dir = DIR_UP
    
    # 2. OUTPUT
    possible_exits = [DIR_LEFT, DIR_RIGHT, DIR_UP, DIR_DOWN]
    next_exit = random.choice(possible_exits)
    
    if is_last_clip:
        next_exit = "ZOOM_EXIT"

    # ===============================
    # GENERACIÓN DE GRID (HYBRID LOGIC)
    # ===============================
    # Coordenadas Grid Abstracto 3x3: x[0..2], y[0..2]. Center es (1,1).
    active_cols = {1}
    active_rows = {1}
    
    # REGLA 1: SI HAY ZOOM (First/Last) -> FULL 3x3 (Seguridad Máxima)
    if is_first_clip or is_last_clip:
        active_cols = {0, 1, 2}
        active_rows = {0, 1, 2}
    else:
        # OPS TIEMPO REAL (Slide Only) -> OPTIMIZACIÓN
        
        # A) Dirección de Entrada
        if enter_dir == DIR_LEFT: active_cols.add(2)
        elif enter_dir == DIR_RIGHT: active_cols.add(0)
        elif enter_dir == DIR_UP: active_rows.add(2)
        elif enter_dir == DIR_DOWN: active_rows.add(0)
            
        # B) Dirección de Salida
        if next_exit == DIR_LEFT: active_cols.add(2)
        elif next_exit == DIR_RIGHT: active_cols.add(0)
        elif next_exit == DIR_UP: active_rows.add(2)
        elif next_exit == DIR_DOWN: active_rows.add(0)
        
        # C) SAFETY: Landscape Images (Altura insuficiente)
        # Si la imagen escalada es más baja que la pantalla, necesitamos tiles verticales
        # para rellenar el fondo (efecto espejo).
        if final_h < H:
            active_rows = {0, 1, 2}

    min_col, max_col = min(active_cols), max(active_cols)
    min_row, max_row = min(active_rows), max(active_rows)
    
    grid_cols = max_col - min_col + 1
    grid_rows = max_row - min_row + 1
    
    # Dimensiones del Lienzo
    canvas_w = final_w * grid_cols
    canvas_h = final_h * grid_rows
    
    grid_img = Image.new('RGB', (canvas_w, canvas_h))
    
    # Preparar Variaciones
    tile_normal = base_img
    tile_mirror_h = ImageOps.mirror(base_img)
    
    # Populate function
    def get_tile(c, r):
        # Lógica de Espejos Original
        base_t = tile_normal
        if c == 0 or c == 2: base_t = tile_mirror_h
        if r == 0 or r == 2: return ImageOps.flip(base_t)
        return base_t

    # Pintar Grid
    for c in range(min_col, max_col + 1):
        for r in range(min_row, max_row + 1):
            tile = get_tile(c, r)
            paste_x = (c - min_col) * final_w
            paste_y = (r - min_row) * final_h
            grid_img.paste(tile, (paste_x, paste_y))
    
    super_clip = ImageClip(np.array(grid_img)).set_duration(total_dur)
    
    # ===============================
    # 3. ANIMACIÓN DE POSICIÓN
    # ===============================
    
    # PIVOTE DINÁMICO
    local_center_col = 1 - min_col
    local_center_row = 1 - min_row
    
    center_x = ((W - final_w) / 2) - (local_center_col * final_w)
    center_y = ((H - final_h) / 2) - (local_center_row * final_h)
    
    start_x, start_y = center_x, center_y
    offset_in_w = final_w * 0.7
    offset_in_h = final_h * 0.7
    
    if is_first_clip:
        pass 
    else:
        if enter_dir == DIR_LEFT: start_x = center_x - offset_in_w
        elif enter_dir == DIR_RIGHT: start_x = center_x + offset_in_w
        elif enter_dir == DIR_UP: start_y = center_y - offset_in_h
        elif enter_dir == DIR_DOWN: start_y = center_y + offset_in_h
    
    end_x, end_y = center_x, center_y
    offset_out_w = final_w * 0.7
    offset_out_h = final_h * 0.7
    
    if is_last_clip:
        pass
    else:
         if next_exit == DIR_LEFT: end_x = center_x - offset_out_w
         elif next_exit == DIR_RIGHT: end_x = center_x + offset_out_w
         elif next_exit == DIR_UP: end_y = center_y - offset_out_h
         elif next_exit == DIR_DOWN: end_y = center_y + offset_out_h

    # ZOOM FUNCTION
    t_mid = total_dur * 0.5
    
    def zoom_func(t):
        if is_last_clip and t >= t_mid:
            dur_part = total_dur - t_mid
            p = (t - t_mid) / dur_part
            p = pow(p, 2)
            return 1.0 + (0.3 * p)
        elif is_first_clip and t < t_mid:
            dur_part = t_mid
            p = t / dur_part
            p = 1 - pow(1 - p, 2)
            return 1.3 - (0.3 * p)
        return 1.0 

    def pos_func(t):
        s = zoom_func(t)
        
        # PIVOTE REAL (Centro de la imagen central en el canvas)
        pivot_x_in_img = (local_center_col + 0.5) * final_w
        pivot_y_in_img = (local_center_row + 0.5) * final_h
        
        dynamic_center_x = (W / 2) - (pivot_x_in_img * s)
        dynamic_center_y = (H / 2) - (pivot_y_in_img * s)
        
        if is_first_clip:
            if t < t_mid: return (int(dynamic_center_x), int(dynamic_center_y))
            else:
                p = (t - t_mid) / (total_dur - t_mid)
                p = pow(p, 3) 
                curr_x = center_x + (end_x - center_x) * p
                curr_y = center_y + (end_y - center_y) * p
                return (int(curr_x), int(curr_y))
                
        elif is_last_clip:
            if t < t_mid:
                p = t / t_mid
                p = 1 - pow(1 - p, 3) 
                curr_x = start_x + (center_x - start_x) * p
                curr_y = start_y + (center_y - start_y) * p
                return (int(curr_x), int(curr_y))
            else:
                return (int(dynamic_center_x), int(dynamic_center_y))
                
        else:
            if t < t_mid:
                p = t / t_mid
                p = 1 - pow(1 - p, 3) 
                curr_x = start_x + (center_x - start_x) * p
                curr_y = start_y + (center_y - start_y) * p
                return (int(curr_x), int(curr_y))
            else:
                p = (t - t_mid) / (total_dur - t_mid)
                p = pow(p, 3) 
                curr_x = center_x + (end_x - center_x) * p
                curr_y = center_y + (end_y - center_y) * p
                return (int(curr_x), int(curr_y))

    # APLICAR
    if is_first_clip or is_last_clip:
        final_clip = super_clip.resize(zoom_func).set_position(pos_func)
    else:
        final_clip = super_clip.set_position(pos_func)
    
    return CompositeVideoClip([final_clip], size=resolution).set_duration(total_dur), next_exit

# ==========================================
# DISPATCHER
# ==========================================
def create_smart_combo_clip(image_path, total_dur, resolution, prev_exit_dir, is_first_clip=False, is_last_clip=False, version="v1_estable"):
    if version == "v2_estable":
        return create_smart_combo_clip_v2_estable(image_path, total_dur, resolution, prev_exit_dir, is_first_clip, is_last_clip)
    else:
        return create_smart_combo_clip_v1_stable(image_path, total_dur, resolution, prev_exit_dir, is_first_clip)


# ==========================================
# DYNAMIC INTRO GENERATOR
# ==========================================
def generate_dynamic_intro(audio_clip, config, candidate_videos, log_callback=None):
    target_duration = audio_clip.duration
    
    # Use provided candidates (found by get_president_assets)
    candidates = candidate_videos if candidate_videos else []
                
    if not candidates:
        if log_callback: log_callback("⚠️ No se encontraron videos de intro.")
        return None, "NEUTRAL"

    if log_callback: log_callback(f"✅ Generando Intro Dinámica ({target_duration:.1f}s) con {len(candidates)} clips...")

    # 2. Smart Fill Loop with Distributed Trimming
    selected_clips_data = [] # List of tuples (clip, final_duration)
    
    attempts = 0
    max_attempts = 20
    
    W, H = tuple(config["video_settings"]["resolution"])
    
    import random
    
    while attempts < max_attempts:
        current_selection = []
        current_dur = 0.0
        
        # Shuffle/Random pick
        random.shuffle(candidates)
        pool_idx = 0
        
        # Build chain: Add clips until we exceed target
        possible_chain = [] # List of VideoFileClip
        chain_dur = 0.0
        
        while chain_dur < target_duration:
            if pool_idx >= len(candidates):
                # Repopulate
                pool_idx = 0
                random.shuffle(candidates)
            
            vid_path = candidates[pool_idx]
            pool_idx += 1
            
            try:
                clip = VideoFileClip(vid_path)
                # Validation: If raw clip is < 2.0s, it's useless for our constraints. Skip it.
                if clip.duration < 2.0:
                    clip.close()
                    continue
                    
                possible_chain.append(clip)
                chain_dur += clip.duration
            except:
                continue
                
        # Now we have a chain where sum(durations) >= target_duration
        # Optimization: Check if it's statistically possible to fit.
        # Constraint: Each clip must be >= 2.0s
        min_needed = len(possible_chain) * 2.0
        
        if min_needed > target_duration:
            # Too many clips / clips too short to cover target effectively.
            # Close and retry shuffle
            for c in possible_chain: c.close()
            attempts += 1
            continue
            
        # Optimization: Distribute Cuts
        # Strategy 1: Proportional Shrinker
        # scale = target / chain_dur
        # proposed = [d * scale]
        # If all proposed >= 2.0 -> Winner.
        
        scale = target_duration / chain_dur
        proposed_durs = [c.duration * scale for c in possible_chain]
        
        if min(proposed_durs) >= 2.0:
            # Plan A Success: Proportional
            final_durs = proposed_durs
        else:
            # Plan B: Backwards Squeeze
            # Cut excess from end to start, adhering to 2.0 floor.
            excess = chain_dur - target_duration
            current_durs = [c.duration for c in possible_chain]
            valid_squeeze = True
            
            for i in range(len(current_durs)-1, -1, -1):
                can_cut = current_durs[i] - 2.0
                take = min(can_cut, excess)
                current_durs[i] -= take
                excess -= take
                if excess <= 0.001: break
            
            if excess > 0.001:
                # Still have excess and hit all floors. Impossible combo.
                for c in possible_chain: c.close()
                attempts += 1
                continue
            
            final_durs = current_durs

        # If we got here, we have a valid plan (possible_chain + final_durs)
        # Apply cuts
        processed_intro = []
        running_time = 0.0
        
        for i, clip in enumerate(possible_chain):
            desired_dur = final_durs[i]
            
            # Mute & Resize Logic SAME AS BEFORE
            clip = clip.without_audio()
            
            if clip.h != H:
               clip = clip.resize(height=H)
            if clip.w > W:
                clip = clip.crop(x1=(clip.w - W)/2, width=W, height=H)
            elif clip.w < W:
                clip = clip.resize(width=W)
                clip = clip.crop(y1=(clip.h - H)/2, width=W, height=H)
                
            # SUBCLIP TO EXACT DURATION
            # Random subclip? Or start from 0? 
            # Start from 0 is safer for continuity/intros, but random could be fun.
            # Let's keep 0 for stability as per user request ("recorta el ultimo...").
            clip = clip.subclip(0, desired_dur)
            
            processed_intro.append(clip)
            
        # ALL GOOD
        final_intro_video = concatenate_videoclips(processed_intro, method="compose")
        final_intro_video = final_intro_video.set_audio(audio_clip)
        
        return final_intro_video, "NEUTRAL"
        
    print("⚠️ Intro generator max attempts reached. Returning simple fallback.")
    return None, "NEUTRAL"



def get_mystery_silhouette_image(top1_name, list_previous_presidents, library_path, specific_folder):
    """
    Selecciona la imagen para el audio del Top 1 (Bait/Pregunta).
    Prioridad:
    1. Silueta específica en la carpeta del presidente (*silueta*, *silhouette*)
    2. Comodín 'Viral' (Si Trump NO ha salido antes)
    3. Comodín 'Genérico' (Si Trump YA salió antes)
    """
    
    # 1. Buscar silueta específica
    # Buscamos patrones en español e inglés
    specific_silhouettes = []
    if specific_folder and os.path.exists(specific_folder):
        specific_silhouettes = glob.glob(os.path.join(specific_folder, "*silueta*")) + \
                               glob.glob(os.path.join(specific_folder, "*silhouette*"))
    
    # Filtrar solo archivos de imagen (evitar carpetas o basura)
    valid_exts = ('.jpg', '.jpeg', '.png')
    specific_silhouettes = [f for f in specific_silhouettes if f.lower().endswith(valid_exts)]

    if specific_silhouettes:
         # SI EXISTE: Úsala.
         return random.choice(specific_silhouettes)

    # 2. Lógica de Comodines (Si no hay silueta específica)
    # Analiza si Trump ya salió en los puestos previos.
    trump_revealed = False
    if list_previous_presidents:
        trump_revealed = any(("trump" in str(p).lower() or "donald" in str(p).lower()) for p in list_previous_presidents)
    
    if trump_revealed:
         # CASO 1: Trump ya salió. Usar genérica.
         # BIBLIOTECA_RECURSOS/comodin_silueta_2.png
         return os.path.join(library_path, "comodin_silueta_2.png")
    else:
         # CASO 2: Trump NO ha salido. Usar cebo viral.
         # BIBLIOTECA_RECURSOS/comodin_silueta_1.png
         return os.path.join(library_path, "comodin_silueta_1.png")


def create_video_segment(audio_path, puesto, president_name, config, video_token_used, log_callback=None, engine_version="v1_estable", revealed_presidents=None):
    from src.utils import get_president_assets, find_best_match_folder
    
    paths = config["paths"]
    res = tuple(config["video_settings"]["resolution"])
    W, H = res
    
    photos, videos, silhouettes = get_president_assets(paths["library_base"], president_name, config)
    
    if log_callback:
        n_p = len(photos) if photos else 0
        n_v = len(videos) if videos else 0
        n_s = len(silhouettes) if silhouettes else 0
        log_callback(f"🔍 Buscando recursos para '{president_name}' -> Fotos: {n_p}, Videos: {n_v}, Siluetas: {n_s}")
        
    if not photos and not videos and not silhouettes: 
        if log_callback: log_callback(f"⚠️ No se encontraron recursos para {president_name}")
        return None, video_token_used

    # Manual Volume Reduction REMOVED due to instability
    audio = AudioFileClip(audio_path)
    
    # AGGRESSIVE GLITCH REMOVAL
    # Cortamos las últimas décimas donde suele estar el ruido/palabra fantasma
    # y aplicamos un fadeout rápido para suavizar el corte.
    if audio.duration > 0.2:
        new_dur = audio.duration - 0.15 # Hard Trim de 0.15s
        audio = audio.subclip(0, new_dur)
        audio = audio.fx(audio_fadeout, 0.05) # Suavizado final
    
    audio_clip = audio
    # No .fx, no .fl, no Arrays on Stack. Just pure audio.
    dur_total = audio_clip.duration
    
    # --- INTRO LOGIC (DYNAMIC) ---
    # --- INTRO LOGIC (DYNAMIC) ---
    if "intro" in os.path.basename(audio_path).lower():
         if log_callback: log_callback("✅ Detectado archivo INTRO. Generando montaje visual...")
         dynamic_intro, exit_state = generate_dynamic_intro(audio_clip, config, videos, log_callback)
         if dynamic_intro:
             return dynamic_intro, video_token_used

    # --- SILHOUETTE LOGIC (TOP 1 MYSTERY) ---
    is_silhouette_mode = False
    
    # Nueva lista de siluetas forzadas por la nueva lógica
    forced_silhouettes = []
    
    if puesto == 1:
        # Lógica mejorada para Top 1
        
        # 1. Recuperar carpeta específica para buscar siluetas a fondo
        target_folder = find_best_match_folder(president_name, paths["library_base"])
        
        # 2. Obtener la silueta "Ideal" (Específica o Comodín Inteligente)
        mystery_image = get_mystery_silhouette_image(
            top1_name=president_name,
            list_previous_presidents=revealed_presidents,
            library_path=paths["resources_library"],
            specific_folder=target_folder
        )
        
        # 3. Verificar si la imagen existe
        if mystery_image and os.path.exists(mystery_image):
            is_silhouette_mode = True
            forced_silhouettes = [mystery_image]
            if log_callback: log_callback(f"👤 Modo Silueta Activado (Top 1) - Imagen: {os.path.basename(mystery_image)}")
        else:
             # Fallback si fallan los comodines (ej: no existen los archivos .jpg)
             # Usamos lo que encontró get_president_assets originalmente
             if silhouettes:
                is_silhouette_mode = True
                forced_silhouettes = silhouettes
                if log_callback: log_callback("👤 Modo Silueta Activado (Top 1) - Fallback a siluetas detectadas")

    # --- PREPARE CLIPS ---
    
    intro_dur = 0
    # No "Intro Clips" prefix needed if we use main loop for silhouettes.
    # We will just treat selected_files as the silhouettes.

    remaining_dur = dur_total - intro_dur
    if remaining_dur < 1.0: remaining_dur = 1.0 
    
    # SELECTION LOGIC
    selected_files = []
    
    if is_silhouette_mode:
        if forced_silhouettes:
             selected_files = [forced_silhouettes[0]]
        elif len(silhouettes) > 1:
            # Rule: "Si encuentras más de 1 silueta: Elige aleatoriamente 2 distinct."
            # "Si solo 1: Úsala para toda la duración."
            selected_files = random.sample(silhouettes, min(len(silhouettes), 2))
        else:
            selected_files = [silhouettes[0]]
            
        num_clips_body = len(selected_files)
        # Note: Loop below calculates clip_dur based on num_clips_body if we set it right.
        # If we have 2 clips, clip_dur will be duration/2.
    else:
        # Normal Mode with Narrative Selection
        num_clips_body = max(2, int(remaining_dur / 3.0)) 
        
        # 1. CLASSIFICATION
        list_intro = [f for f in photos if os.path.basename(f).lower().startswith('i')]
        list_normal = [f for f in photos if not os.path.basename(f).lower().startswith('i')]
        
        selected_files = []
        
        # 2. SELECT SLOT 1
        slot1_img = None
        if list_intro:
             slot1_img = random.choice(list_intro)
             # Intro picks don't deplete list_normal
        elif list_normal:
             slot1_img = random.choice(list_normal)
             # CRITICAL: Consumed from normal list
             list_normal.remove(slot1_img)
             
        if slot1_img:
            selected_files.append(slot1_img)
             
        # 3. SELECT REST (Adapt dynamic count to avoid repeats)
        # We want approx 3.0s per clip, but NO REPEATS.
        # So max clips = available unique photos.
        
        available_count = len(list_normal)
        
        # Ideal count based on time
        ideal_num_rest = max(1, int(remaining_dur / 3.0)) - 1
        
        if ideal_num_rest <= 0 and available_count > 0:
            # At least one more if we have space and photos? 
            # If duration is short (e.g. 4s), 1 clip is enough. 
            # But let's try to fit 2 if we have photos.
            if remaining_dur > 4.0: ideal_num_rest = 1
            else: ideal_num_rest = 0

        # Cap by available (Strict No-Repeat Rule)
        # If we have shortage, we reduce clips (longer duration per clip).
        num_rest = min(ideal_num_rest, available_count)
        
        if num_rest > 0:
            picked_rest = random.sample(list_normal, num_rest)
            selected_files.extend(picked_rest)
            
        # Fallback: If after all logic we have 0 clips (e.g. only 1 photo total and it was used in slot1),
        # selected_files already has slot1.
        # If selected_files is empty (0 photos total), handled above.

        
    clip_dur = remaining_dur / max(1, len(selected_files))
    
    processed_clips = []
    
    # --- STATE TRACKING ---
    prev_exit = DIR_CENTER # Default start
    
    # Pre-calculate indices of actual images to apply First/Last logic correctly
    image_indices = [idx for idx, f in enumerate(selected_files) if not f.lower().endswith(('.mp4', '.mov'))]
    
    for i, file_path in enumerate(selected_files):
        # VIDEO Handling (Pass-through)
        if file_path.lower().endswith(('.mp4', '.mov')):
            try:
                vid = VideoFileClip(file_path).resize(height=H) # Crude fit
                vid = vid.crop(x1=(vid.w - W)/2, width=W, height=H)
                vid = vid.set_duration(clip_dur)
                processed_clips.append(vid)
                # prev_exit remains UNCHANGED
            except:
                pass
            continue
            
        # PHOTO Handling (Dynamic)
        # Apply Bounce Zoom only for the very first/last PHOTO of the sequence
        is_first = (i == image_indices[0]) if image_indices else False
        is_last = (i == image_indices[-1]) if image_indices else False
        
        clip, new_exit = create_smart_combo_clip(file_path, clip_dur, res, prev_exit, is_first_clip=is_first, is_last_clip=is_last, version=engine_version)
        processed_clips.append(clip)
        
        # Update State
        prev_exit = new_exit
        
    final_body = None
    if processed_clips:
        final_body = concatenate_videoclips(processed_clips, method="compose")
        
    # Simplify concatenation logic as we removed intro_clips list
    full_visual = final_body
    
    if not full_visual:
        return None, video_token_used
        
    full_visual = full_visual.set_audio(audio_clip)
    return full_visual, video_token_used
