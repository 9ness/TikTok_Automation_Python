import json
import os
import glob
from dotenv import load_dotenv, find_dotenv

import re
import random

# Cargar el archivo .env al inicio, buscando explícitamente
load_dotenv(find_dotenv())

def normalize_name(name):
    """Elimina caracteres no alfanuméricos y pasa a minúsculas."""
    return re.sub(r'[^a-zA-Z0-9]', '', name).lower()

def load_config(config_path="config/config.json"):
    # 1. Cargar el JSON (Estructura)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"❌ ERROR: No se encontró el archivo de configuración en {config_path}")
    except json.JSONDecodeError:
        raise ValueError(f"❌ ERROR: El archivo {config_path} no es un JSON válido")
    
    # 2. Obtener la ruta base del sistema (.env)
    # Si no existe, usa una por defecto o lanza error
    root_path = os.getenv("TIKTOK_ROOT_PATH")
    
    if not root_path:
        raise EnvironmentError("❌ ERROR: No se encontró la variable TIKTOK_ROOT_PATH en el archivo .env. Asegúrate de tener un archivo .env correctamente configurado.")
        
    if not os.path.exists(root_path):
        raise FileNotFoundError(f"❌ ERROR: La ruta definida en TIKTOK_ROOT_PATH no existe: {root_path}")

    # 3. Construir las rutas completas dinámicamente
    # Creamos una nueva sección 'paths' en memoria para que el resto del código siga funcionando igual
    folders = config["folder_structure"]
    
    config["paths"] = {
        "library_base": os.path.join(root_path, folders["presidents_folder"]),
        "intro_library": os.path.join(root_path, folders["intro_folder"]),
        "output_folder": os.path.join(root_path, folders["output_folder"]),
        "resources_library": os.path.join(root_path, folders.get("resources_folder", "BIBLIOTECA_RECURSOS")),
        "temp_folder": folders["temp_folder"]
    }
    
    return config

def get_president_assets(base_path, president_name, config):
    # 1. Definir la raíz de búsqueda correcta
    # Si es "Intro", el usuario lo tiene en TIKTOK_ASSETS/BIBLIOTECA_INTRO/Intro
    if president_name.lower() == "intro":
        root_search = config["paths"]["intro_library"]
    else:
        # Si es normal (Presidente), buscar en BIBLIOTECA_PRESIDENTES
        root_search = base_path
        
    # 2. Búsqueda UNIFICADA
    target_folder = None
    
    # Intento directo
    candidate = os.path.join(root_search, president_name)
    if os.path.exists(candidate):
        target_folder = candidate
    else:
        # Intento flexible
        norm_input = normalize_name(president_name)
        
        try:
            # Listar carpetas en la raíz seleccionada
            available_folders = [d for d in os.listdir(root_search) if os.path.isdir(os.path.join(root_search, d))]
        except Exception:
            available_folders = []
            
        for folder in available_folders:
            if normalize_name(folder) == norm_input:
                target_folder = os.path.join(root_search, folder)
                break
    
    if target_folder is None or not os.path.exists(target_folder):
        print(f"Combinación no encontrada para: {president_name} (Buscado en {root_search})")
        return None, None, None

    img_ext = ['*.jpg', '*.jpeg', '*.png']
    vid_ext = ['*.mp4', '*.mov']
    
    all_files = []
    # Buscar recursivamente o solo en la carpeta
    for ext in img_ext + vid_ext:
        all_files.extend(glob.glob(os.path.join(target_folder, ext)))

    photos = []
    videos = []
    silhouette_candidates = []
    
    suffix_video = config["naming_convention"]["video_suffix"] 
    key_silueta = config["naming_convention"]["silhouette_keyword"]

    for f in all_files:
        filename = os.path.basename(f).lower()
        name_no_ext = os.path.splitext(filename)[0]

        if key_silueta in filename:
            silhouette_candidates.append(f)
            continue

        if suffix_video in name_no_ext or f.endswith(('.mp4', '.mov')):
            videos.append(f)
        else:
            photos.append(f)
    
    # Return the full list of candidates to handle "Max 2" logic upstream
    return photos, videos, silhouette_candidates