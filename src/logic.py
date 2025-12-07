import random
from moviepy.editor import *

def create_video_segment(audio_path, puesto, president_name, config, video_token_used):
    from src.utils import get_president_assets
    
    paths = config["paths"]
    rules = config["editing_rules"]
    settings = config["video_settings"]
    res = tuple(settings["resolution"])

    photos, videos, silhouette = get_president_assets(paths["library_base"], president_name, config)
    
    if not photos and not videos:
        # Retornamos None si no hay archivos, para no romper el programa
        print(f"ERROR: No hay archivos para {president_name}")
        return None, video_token_used

    audio_clip = AudioFileClip(audio_path)
    duration_total = audio_clip.duration
    clips_visuales = []
    
    # 1. Silueta (Top 1)
    if puesto == 1 and silhouette:
        dur_silueta = 2.0
        c_sil = ImageClip(silhouette).set_duration(dur_silueta).resize(height=res[1]).set_position("center")
        clips_visuales.append(c_sil)
        duration_total -= dur_silueta

    # 2. Inyección de Video
    use_video = False
    selected_video = None
    
    if videos and not video_token_used:
        if puesto == 2 or random.random() < rules["probability_video_injection"]:
            use_video = True
            selected_video = random.choice(videos)
            video_token_used = True

    # 3. Selección de Fotos
    n_items = rules["photos_per_top"]
    pool_fotos = photos * (n_items // len(photos) + 1)
    selection = random.sample(pool_fotos, n_items)
    
    if use_video:
        idx = random.randint(0, len(selection)-1)
        selection[idx] = "VIDEO:" + selected_video

    # 4. Montaje
    duration_per_item = duration_total / len(selection)

    for item in selection:
        if isinstance(item, str) and item.startswith("VIDEO:"):
            v_path = item.replace("VIDEO:", "")
            clip = VideoFileClip(v_path).without_audio()
            # Crop simple para centrar verticalmente
            if clip.size[0] > clip.size[1]: # Si es horizontal
                 clip = clip.crop(x1=clip.size[0]/2 - res[0]/2, width=res[0], height=clip.size[1])
            
            clip = clip.resize(height=res[1])
            
            if clip.duration < duration_per_item:
                clip = clip.loop(duration=duration_per_item)
            else:
                start = random.uniform(0, clip.duration - duration_per_item)
                clip = clip.subclip(start, start + duration_per_item) 
            clips_visuales.append(clip)
        else:
            clip = ImageClip(item).set_duration(duration_per_item).resize(height=res[1])
            clip = clip.resize(lambda t: 1 + rules["zoom_speed"] * t).set_position("center")
            clips_visuales.append(clip)

    final_clip = concatenate_videoclips(clips_visuales, method="compose")
    final_clip = final_clip.set_audio(audio_clip)
    
    return final_clip, video_token_used