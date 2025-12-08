
import random
import math
import numpy as np
from moviepy.editor import *
from PIL import Image, ImageFilter

# ==========================================
# CONSTANTES DE MOVIMIENTO (COMBO)
# ==========================================
MOVE_UP    = "UP"
MOVE_DOWN  = "DOWN"
MOVE_LEFT  = "LEFT"
MOVE_RIGHT = "RIGHT"
MOVE_ZOOM  = "ZOOM" # Zoom In/Out variations
MOVE_STATIC = "STATIC"

# MAPPING: Exit Direction -> Required Entry Direction for PUSH effect
# Example: If Clip A Exits UP (0 -> -H), Clip B Must Enter FROM BOTTOM (H -> 0)
LINKED_ENTRY = {
    MOVE_UP:    MOVE_DOWN,  # Exit UP -> Enter FROM DOWN
    MOVE_DOWN:  MOVE_UP,    # Exit DOWN -> Enter FROM UP
    MOVE_LEFT:  MOVE_RIGHT, # Exit LEFT -> Enter FROM RIGHT
    MOVE_RIGHT: MOVE_LEFT,  # Exit RIGHT -> Enter FROM LEFT
    MOVE_ZOOM:  MOVE_ZOOM,  # Keep Zoom flow
    MOVE_STATIC: MOVE_STATIC
}

POSSIBLE_MOVES = [MOVE_UP, MOVE_DOWN, MOVE_LEFT, MOVE_RIGHT, MOVE_ZOOM]

def get_blurred_background(image_path, total_dur, resolution):
    W, H = resolution
    try:
        pil_img = Image.open(image_path)
        # Zoom 150% (1.5x) to ensure coverage
        ratio = max(W / pil_img.width, H / pil_img.height)
        new_size = (int(pil_img.width * ratio * 1.5), int(pil_img.height * ratio * 1.5))
        
        pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Center Crop
        left = (new_size[0] - W) / 2
        top = (new_size[1] - H) / 2
        pil_img = pil_img.crop((left, top, left + W, top + H))
        
        # Heavy Blur
        pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=40))
        
        img_array = np.array(pil_img)
        return ImageClip(img_array).set_duration(total_dur)
    except Exception as e:
        print(f"Error BG Blur: {e}")
        return ColorClip(size=resolution, color=(20,20,20), duration=total_dur)

def create_combo_clip(image_path, total_dur, entry_type, exit_type, resolution):
    """
    Creates a CompositeVideoClip with internal 'Combo' animation.
    Fases:
      0.0s - 0.5s: ENTRY (Move from OUT to 0)
      0.5s - End-0.5s: SUSTAIN (Zoom gently)
      End-0.5s - End: EXIT (Move from 0 to OUT)
    """
    W, H = resolution
    TRANSITION_TIME = 0.5 
    
    # 1. Prepare Background
    bg_clip = get_blurred_background(image_path, total_dur, resolution)
    
    # 2. Prepare Foreground Image (Aspect Fill)
    raw_img = ImageClip(image_path).set_duration(total_dur)
    img_w, img_h = raw_img.size
    scale = max(W / img_w, H / img_h)
    new_w, new_h = int(img_w * scale), int(img_h * scale)
    raw_img = raw_img.resize((new_w, new_h))
    raw_img = raw_img.crop(x1=(new_w-W)/2, y1=(new_h-H)/2, width=W, height=H)
    
    # 3. Animation Logic (Lambda)
    def pos_func(t):
        x, y = 0, 0
        
        # ENTRY PHASE (0 -> 0.5)
        if t < TRANSITION_TIME:
            p = t / TRANSITION_TIME # 0 -> 1
            ease = 1 - (1 - p)**3   # Cubic Ease Out
            
            if entry_type == MOVE_DOWN:   y = int(H * (1 - ease)) # From Bottom (H) to 0
            elif entry_type == MOVE_UP:   y = int(-H * (1 - ease)) # From Top (-H) to 0
            elif entry_type == MOVE_RIGHT:x = int(W * (1 - ease)) # From Right (W) to 0
            elif entry_type == MOVE_LEFT: x = int(-W * (1 - ease)) # From Left (-W) to 0
            # Zoom In/Out entry handled by resize? Or just static 0,0
            
        # EXIT PHASE (End-0.5 -> End)
        elif t > (total_dur - TRANSITION_TIME):
            time_left = total_dur - t
            p = (TRANSITION_TIME - time_left) / TRANSITION_TIME # 0 -> 1
            ease = p**3 # Cubic Ease In
            
            if exit_type == MOVE_UP:      y = int(-H * ease) # To Top (-H)
            elif exit_type == MOVE_DOWN:  y = int(H * ease)  # To Bottom (H)
            elif exit_type == MOVE_LEFT:  x = int(-W * ease) # To Left (-W)
            elif exit_type == MOVE_RIGHT: x = int(W * ease)  # To Right (W)
            
        return (x, y)
    
    # 4. Zoom Logic (Always active for sustain)
    # Gentle zoom 1.0 -> 1.15
    anim_clip = raw_img.resize(lambda t: 1.0 + 0.15 * (t / total_dur))
    anim_clip = anim_clip.set_position(pos_func)
    
    # 5. Composite
    return CompositeVideoClip([bg_clip, anim_clip], size=resolution).set_duration(total_dur)

def create_video_segment(audio_path, puesto, president_name, config, video_token_used):
    from src.utils import get_president_assets
    
    # Config Unpacking
    paths = config["paths"]
    res = tuple(config["video_settings"]["resolution"])
    
    photos, videos, silhouette = get_president_assets(paths["library_base"], president_name, config)
    if not photos and not videos: return None, video_token_used

    audio_clip = AudioFileClip(audio_path)
    dur_total = audio_clip.duration
    
    # --- PLANIFICACIÓN DE CLIPS ---
    
    # 1. Silueta (Intro) - Tratamiento especial
    intro_dur = 0
    intro_clips = []
    if puesto == 1 and silhouette:
        intro_dur = 2.0
        sil_img = ImageClip(silhouette).set_duration(intro_dur).resize(height=res[1]).set_position("center")
        # Silueta sobre negro (sin blur para destacar forma)
        sil_comp = CompositeVideoClip([sil_img], size=res).set_duration(intro_dur)
        intro_clips.append(sil_comp)
        
    # 2. Fotos (Body)
    remaining_dur = dur_total - intro_dur
    if remaining_dur < 1.0: remaining_dur = 1.0 # Safety
    
    # Cuántos clips? ~2.5s por clip
    num_clips_body = max(3, int(remaining_dur / 2.5))
    
    # Ajuste por Overlap (-0.5s por unión)
    # Total Visual Time = Sum(clips) - (N-1)*0.5
    # We want Total Visual Time = remaining_dur
    # remaining_dur = N*clip_dur - (N-1)*0.5
    # clip_dur = (remaining_dur + (N-1)*0.5) / N
    
    OVERLAP = 0.5
    clip_dur = (remaining_dur + (num_clips_body - 1) * OVERLAP) / num_clips_body
    
    # Selección de assets
    pool = random.sample(photos, min(len(photos), 10))
    while len(pool) < num_clips_body: pool += pool
    selected_files = pool[:num_clips_body]
    
    processed_clips = []
    prev_exit = MOVE_STATIC # Silueta acaba estática
    
    for i, file_path in enumerate(selected_files):
        # Decidir Salida (Random)
        exit_move = random.choice(POSSIBLE_MOVES)
        
        # Decidir Entrada (Linked)
        if i == 0:
            # First photo after silhouette -> Enter from Bottom usually looks good or simple Zoom
            entry_move = MOVE_DOWN # "From Bottom"
        else:
            entry_move = LINKED_ENTRY.get(prev_exit, MOVE_STATIC)
            
        clip = create_combo_clip(file_path, clip_dur, entry_move, exit_move, res)
        processed_clips.append(clip)
        
        prev_exit = exit_move
        
    # --- ENSAMBLAJE ---
    final_body = None
    if processed_clips:
        # Concatenate with Negative Padding for Push Effect
        final_body = concatenate_videoclips(processed_clips, method="compose", padding=-OVERLAP)
        
    # Unir Intro + Body (Corte seco o sin overlap complejo para silueta)
    if intro_clips and final_body:
        full_visual = concatenate_videoclips([intro_clips[0], final_body], method="compose")
    elif final_body:
        full_visual = final_body
    elif intro_clips:
        full_visual = intro_clips[0]
    else:
        return None, video_token_used
        
    full_visual = full_visual.set_audio(audio_clip)
    return full_visual, video_token_used