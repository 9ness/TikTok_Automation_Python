import json
import os
import glob
from dotenv import load_dotenv, find_dotenv

import re
import random
import difflib

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

def find_best_match_folder(character_name_raw, assets_base_path):
    """
    Busca la carpeta más parecida ignorando guiones, mayúsculas e iniciales intermedias.
    Ej: 'Harry_S_Truman' -> Match con carpeta 'Harry Truman'
    """
    if not os.path.exists(assets_base_path):
        return None
        
    # 1. Limpieza del nombre que viene del TXT/Gemini
    # Quitamos prefijos numéricos '2_' y extensiones
    clean_input = character_name_raw.replace("_", " ").lower()
    clean_input = "".join([c for c in clean_input if c.isalpha() or c.isspace()])
    input_tokens = set(clean_input.split())
    
    try:
        available_folders = [f for f in os.listdir(assets_base_path) if os.path.isdir(os.path.join(assets_base_path, f))]
    except Exception:
        return None
    
    best_match = None
    highest_score = 0
    
    for folder in available_folders:
        folder_clean = folder.replace("_", " ").lower()
        folder_tokens = set(folder_clean.split())
        
        # A. Coincidencia Exacta (normalizada)
        if clean_input == folder_clean:
            return os.path.join(assets_base_path, folder)
        
        # B. Coincidencia de Palabras Clave (Tokens)
        common = input_tokens.intersection(folder_tokens)
        score = len(common)
        
        # Penalizamos si la carpeta tiene palabras que NO están en el input
        # Pero permitimos que el input tenga extras (la 'S' de Truman).
        # Ajuste: Si la carpeta es subset del input, es un buen candidato.
        if len(folder_tokens) > 0 and score >= len(folder_tokens): 
             # ¡Match perfecto de subconjunto!
             return os.path.join(assets_base_path, folder)
             
        # C. Difflib (Parecido visual para typos)
        similarity = difflib.SequenceMatcher(None, clean_input, folder_clean).ratio()
        if similarity > highest_score:
            highest_score = similarity
            best_match = folder

    # Umbral de seguridad para difflib
    if best_match and highest_score > 0.6:
        print(f"   🔍 Match Inteligente: '{character_name_raw}' -> '{best_match}' ({highest_score:.2f})")
        return os.path.join(assets_base_path, best_match)
        
    return None

def get_president_assets(base_path, president_name, config):
    # 1. Definir la raíz de búsqueda correcta
    # Si es "Intro", el usuario lo tiene en TIKTOK_ASSETS/BIBLIOTECA_INTRO/Intro
    if president_name.lower() == "intro":
        root_search = config["paths"]["intro_library"]
    else:
        # Si es normal (Presidente), buscar en BIBLIOTECA_PRESIDENTES
        root_search = base_path
        
    # 2. Búsqueda UNIFICADA
    # 2. Búsqueda UNIFICADA con Inteligencia Difusa
    target_folder = find_best_match_folder(president_name, root_search)
    
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

def find_president_folder(base_path, keyword):
    """
    Busca la carpeta de un presidente usando lógica fuzzy (nombre contiene keyword ignorando mayúsculas).
    Retorna la ruta completa si la encuentra, o None si no.
    """
    if not os.path.exists(base_path):
        return None
    
    # Normalizamos la palabra clave
    keyword_norm = keyword.strip().lower()
    
    try:
        # Listamos todos los directorios en base_path
        all_folders = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
        
        for folder_name in all_folders:
            # Comparamos ignorando mayúsculas/minúsculas
            if keyword_norm in folder_name.lower():
                return os.path.join(base_path, folder_name)
                
    except Exception as e:
        print(f"Error en find_president_folder: {e}")
        return None
        
    return None