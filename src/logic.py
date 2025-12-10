
import os
import math
import numpy as np
from moviepy.editor import *
from moviepy.audio.fx.all import audio_fadeout
from PIL import Image, ImageFilter, ImageOps
import random
import math

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
def create_smart_combo_clip_v2_beta(image_path, total_dur, resolution, prev_exit_dir, is_first_clip=False):
    # Por ahora es una copia exacta de la V1
    return create_smart_combo_clip_v1_stable(image_path, total_dur, resolution, prev_exit_dir, is_first_clip)

# ==========================================
# DISPATCHER
# ==========================================
def create_smart_combo_clip(image_path, total_dur, resolution, prev_exit_dir, is_first_clip=False, version="v1_estable"):
    if version == "v2_beta":
        return create_smart_combo_clip_v2_beta(image_path, total_dur, resolution, prev_exit_dir, is_first_clip)
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

    # 2. Smart Fill Loop
    selected_clips = []
    attempts = 0
    max_attempts = 10
    
    W, H = tuple(config["video_settings"]["resolution"])
    
    while attempts < max_attempts:
        current_selection = []
        current_dur = 0.0
        
        # Shuffle/Random pick
        random.shuffle(candidates)
        pool_idx = 0
        
        valid_combo = False
        
        # Build chain
        while current_dur < target_duration:
            # Need more clips
            if pool_idx >= len(candidates):
                # Run out of clips, reshuffle or reuse?
                # Just loop back
                pool_idx = 0
                random.shuffle(candidates)
                
            vid_path = candidates[pool_idx]
            pool_idx += 1
            
            try:
                # Load clip
                clip = VideoFileClip(vid_path)
                current_selection.append(clip)
                current_dur += clip.duration
            except Exception as e:
                print(f"Error loading intro clip {vid_path}: {e}")
                # If a clip fails to load, remove it from candidates for this attempt
                candidates.pop(pool_idx - 1) # Adjust index as one was just popped
                if not candidates: # If no more candidates, break
                    break
                continue
                
            # Check if we passed target
            if current_dur >= target_duration:
                 # Check remainder
                 # We will trim the LAST clip.
                 # Duration needed from last clip:
                 dur_others = current_dur - clip.duration
                 needed_from_last = target_duration - dur_others
                 
                 # Constraint: "Si tiempo_faltante < 2.0 segundos: DESCARTAR"
                 if needed_from_last >= 2.0:
                     # Valid!
                     valid_combo = True
                     break
                 else:
                     # Invalid tail.
                     break
        
        if valid_combo:
            selected_clips = current_selection
            break
            
        attempts += 1
        # Close clips to free resources if retrying
        for c in current_selection: 
            try: c.close()
            except: pass
            
    if not selected_clips:
        print("⚠️ Used fallback intro (Could not find valid combo).")
        return None, "NEUTRAL"
        
    # 3. Process Visuals (Crop/Resize/Mute)
    processed_intro = []
    
    running_time = 0.0
    
    for i, raw_clip in enumerate(selected_clips):
        # Mute
        clip = raw_clip.without_audio()
        
        # Resize Height -> H (Preserve aspect ratio relative to height is implicit in some scenarios but we force)
        # We need to fill W, H.
        # If we resize height=H, width might be >W (if 16:9). Then crop center.
        
        if clip.h != H:
           clip = clip.resize(height=H) # Resize keeping aspect ratio
           
        # Crop center
        if clip.w > W:
            clip = clip.crop(x1=(clip.w - W)/2, width=W, height=H)
        elif clip.w < W:
            # If still smaller, resize by width
            clip = clip.resize(width=W) # Might crop top/bottom
            clip = clip.crop(y1=(clip.h - H)/2, width=W, height=H)
            
        # Ensure exact size
        # clip.resize(newsize=(W,H)) forces distortion. Avoid.
        
        # Trim Logic
        # If it's the last one, trim to exact fit
        if i == len(selected_clips) - 1:
            dur_others = running_time
            needed = target_duration - dur_others
            clip = clip.subclip(0, needed)
            
        processed_intro.append(clip)
        running_time += clip.duration
        
    # 4. Concatenate
    final_intro_video = concatenate_videoclips(processed_intro, method="compose")
    final_intro_video = final_intro_video.set_audio(audio_clip)
    
    return final_intro_video, "NEUTRAL" # Intro ends neutrally



def create_video_segment(audio_path, puesto, president_name, config, video_token_used, log_callback=None, engine_version="v1_estable"):
    from src.utils import get_president_assets
    
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
    if puesto == 1:
        # Check if we have dynamic intro? If above block returned, we're done.
        # If not, we are here.
        if silhouettes:
            is_silhouette_mode = True
            if log_callback: log_callback("👤 Modo Silueta Activado (Top 1) - Animado")
            
    # --- PREPARE CLIPS ---
    
    intro_dur = 0
    # No "Intro Clips" prefix needed if we use main loop for silhouettes.
    # We will just treat selected_files as the silhouettes.

    remaining_dur = dur_total - intro_dur
    if remaining_dur < 1.0: remaining_dur = 1.0 
    
    # SELECTION LOGIC
    selected_files = []
    
    if is_silhouette_mode:
        # Rule: "Si encuentras más de 1 silueta: Elige aleatoriamente 2 distinct."
        # "Si solo 1: Úsala para toda la duración."
        if len(silhouettes) > 1:
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
        
        slot1_img = None
        
        # 2. SELECTION SLOT 1
        if list_intro:
             slot1_img = random.choice(list_intro)
             # Unused intros are discarded (not added back to list_normal)
        elif list_normal:
             slot1_img = random.choice(list_normal)
             
        # 3. SELECTION REST (Slots 2..N)
        # Fill strictly from list_normal
        needed = num_clips_body - 1
        rest_imgs = []
        
        if list_normal and needed > 0:
            # If we need more than we have, start repeating
            pool = list_normal[:]
            while len(pool) < needed:
                pool += list_normal
            rest_imgs = random.sample(pool, needed)
            
        selected_files = []
        if slot1_img: selected_files.append(slot1_img)
        selected_files.extend(rest_imgs)
        
    clip_dur = remaining_dur / max(1, len(selected_files))
    
    processed_clips = []
    
    # --- STATE TRACKING ---
    prev_exit = DIR_CENTER # Default start
    
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
        # Apply Bounce Zoom only for the very first clip of the sequence (i==0)
        is_first = (i == 0)
        clip, new_exit = create_smart_combo_clip(file_path, clip_dur, res, prev_exit, is_first_clip=is_first, version=engine_version)
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
