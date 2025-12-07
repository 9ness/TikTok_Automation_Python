import json
import os
import glob

def load_config(config_path="config/config.json"):
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_president_assets(base_path, president_name, config):
    target_folder = os.path.join(base_path, president_name)
    
    if not os.path.exists(target_folder):
        return None, None, None

    img_ext = ['*.jpg', '*.jpeg', '*.png']
    vid_ext = ['*.mp4', '*.mov']
    
    all_files = []
    for ext in img_ext + vid_ext:
        all_files.extend(glob.glob(os.path.join(target_folder, ext)))

    photos = []
    videos = []
    silhouette = None
    
    suffix_video = config["naming_convention"]["video_suffix"] 
    key_silueta = config["naming_convention"]["silhouette_keyword"]

    for f in all_files:
        filename = os.path.basename(f).lower()
        name_no_ext = os.path.splitext(filename)[0]

        if key_silueta in filename:
            silhouette = f
            continue

        if suffix_video in name_no_ext or f.endswith(('.mp4', '.mov')):
            videos.append(f)
        else:
            photos.append(f)

    return photos, videos, silhouette