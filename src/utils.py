import json
import os
import glob
import string
from dotenv import load_dotenv, find_dotenv

import re
import random
import difflib

# Cargar el archivo .env al inicio, buscando explícitamente
load_dotenv(find_dotenv())

# Cola de rutas relativas (dentro del Google Drive) donde buscar TIKTOK_ASSETS
# si TIKTOK_ROOT_PATH no está definido o no existe. La primera coincidencia gana.
#
# - "Mi unidad/..." aplica a Drive Desktop en Windows (estructura local)
# - Las rutas SIN "Mi unidad/" aplican a rclone mount en Linux (en el mount,
#   el contenido de "Mi unidad" se ve directo desde la raíz)
_TIKTOK_ASSETS_RELATIVE_CANDIDATES = (
    os.path.join("Mi unidad", "NEBULABS_AUTOMATED_TIKTOK", "TIKTOK_CR", "TIKTOK_ASSETS"),
    os.path.join("Mi unidad", "COUSAS NESTOR", "TIKTOK10K", "TIKTOK_ASSETS"),
    os.path.join("NEBULABS_AUTOMATED_TIKTOK", "TIKTOK_CR", "TIKTOK_ASSETS"),
    os.path.join("COUSAS NESTOR", "TIKTOK10K", "TIKTOK_ASSETS"),
)


def _autodetect_tiktok_root():
    """Escanea las unidades del sistema en busca de la carpeta TIKTOK_ASSETS
    dentro de Google Drive ("Mi unidad"). Devuelve la primera ruta encontrada
    o None si no se encuentra ninguna.

    Soporta:
    - Windows: todas las letras de unidad C:\\..Z:\\
    - Linux (VPS con rclone mount): puntos de montaje típicos:
      ~/gdrive, /mnt/gdrive, /media/<user>/gdrive, /srv/gdrive
    """
    if os.name == "nt":
        roots = [f"{letter}:\\" for letter in string.ascii_uppercase]
    else:
        # Puntos de montaje típicos en Linux. El primero (~/gdrive) es el que
        # usa nuestro despliegue VPS por convención (ver deploy/README.md).
        home = os.path.expanduser("~")
        roots = [
            os.path.join(home, "gdrive"),
            "/mnt/gdrive",
            "/srv/gdrive",
            home,
            "/",
        ]
        # Añadir /media/<user>/gdrive y /run/user/<uid>/gvfs (alguna distro)
        media_root = "/media"
        if os.path.isdir(media_root):
            try:
                for sub in os.listdir(media_root):
                    p = os.path.join(media_root, sub, "gdrive")
                    if os.path.isdir(p):
                        roots.append(p)
            except OSError:
                pass
    for root in roots:
        if not os.path.exists(root):
            continue
        for relative in _TIKTOK_ASSETS_RELATIVE_CANDIDATES:
            candidate = os.path.join(root, relative)
            if os.path.isdir(candidate):
                return candidate
    return None


def resolve_tiktok_root():
    """Devuelve la ruta raíz de TIKTOK_ASSETS resolviendo en este orden:
    1) TIKTOK_ROOT_PATH del entorno si existe en disco.
    2) Auto-detección escaneando unidades por la ruta relativa conocida.
    Si encuentra una ruta por auto-detección, exporta TIKTOK_ROOT_PATH al
    entorno para que el resto de módulos (que leen os.getenv) la vean."""
    env_path = os.getenv("TIKTOK_ROOT_PATH")
    if env_path and os.path.isdir(env_path):
        return env_path
    detected = _autodetect_tiktok_root()
    if detected:
        os.environ["TIKTOK_ROOT_PATH"] = detected
        return detected
    return env_path  # puede ser None o ruta inexistente; el llamador decide

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
    
    # 2. Obtener la ruta base del sistema (auto-detecta unidad si hace falta)
    root_path = resolve_tiktok_root()

    if not root_path:
        raise EnvironmentError(
            "❌ ERROR: No se encontró TIKTOK_ASSETS. Define TIKTOK_ROOT_PATH en .env "
            "o asegúrate de que la carpeta exista en alguna unidad bajo "
            "'Mi unidad/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_CR/TIKTOK_ASSETS'."
        )

    if not os.path.exists(root_path):
        print(f"⚠️ ADVERTENCIA: La ruta TIKTOK_ROOT_PATH no existe ({root_path}). Usando fallback temporal.")
        root_path = os.path.abspath("./TIKTOK_ASSETS_FALLBACK")
        os.makedirs(root_path, exist_ok=True)

    # 3. Construir las rutas completas dinámicamente
    # Creamos una nueva sección 'paths' en memoria para que el resto del código siga funcionando igual
    folders = config["folder_structure"]
    
    # Output folder: por defecto va al subdir de Drive (uso local en Windows).
    # En el VPS queremos que MoviePy escriba en SSD local y un timer
    # systemd sincronice contra Drive (más rápido y robusto). Para esto se
    # puede definir TIKTOK_OUTPUT_LOCAL en el .env del VPS apuntando a una
    # ruta local — si existe, sobrescribe output_folder.
    default_output = os.path.join(root_path, folders["output_folder"])
    output_override = os.getenv("TIKTOK_OUTPUT_LOCAL")
    if output_override:
        os.makedirs(output_override, exist_ok=True)
        output_folder = output_override
    else:
        output_folder = default_output

    config["paths"] = {
        "library_base": os.path.join(root_path, folders["presidents_folder"]),
        "intro_library": os.path.join(root_path, folders["intro_folder"]),
        "output_folder": output_folder,
        "resources_library": os.path.join(root_path, folders.get("resources_folder", "BIBLIOTECA_RECURSOS")),
        "pronosticos_clips": os.path.join(root_path, folders.get("pronosticos_clips_folder", "BIBLIOTECA_PRONOSTICOS_CLIPS")),
        "temp_folder": folders["temp_folder"],
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

def validate_system_requirements(config, check_api=True):
    """
    Realiza validaciones críticas al inicio.
    Devuelve una lista de strings con los errores encontrados.
    Si la lista está vacía, todo ok.
    """
    errors = []

    # 1. Validar API Key de Gemini
    if check_api:
        api_key = os.getenv("GOOGLE_GEMINI_KEY")
        if not api_key:
            errors.append("❌ ERROR CRÍTICO: No se encontró la variable 'GOOGLE_GEMINI_KEY' en el archivo .env")

    # 2. Validar Carpeta de Assets (BIBLIOTECA_PRESIDENTES)
    # Obtenemos la ruta final calculada en load_config/paths
    presidents_path = config.get("paths", {}).get("library_base")
    
    if not presidents_path:
         # Fallback por si la config viene rara
         errors.append("❌ ERROR CONFIG: No se pudo determinar la ruta de 'library_base'.")
    else:
        if not os.path.exists(presidents_path):
            errors.append(f"❌ ERROR PATH: La carpeta de presidentes no existe en: {presidents_path}")
        else:
            # Chequear si está vacía (o casi vacía)
            # Listamos carpetas dentro, pues se espera estructura: library/Trump, library/Obama...
            try:
                subfolders = [f for f in os.listdir(presidents_path) if os.path.isdir(os.path.join(presidents_path, f))]
                if not subfolders:
                     errors.append(f"❌ ERROR ASSETS: La carpeta de assets está vacía (sin subcarpetas de personajes) en: {presidents_path}")
            except Exception as e:
                 errors.append(f"❌ ERROR LECTURA: No se pudo leer la carpeta de assets: {e}")

    return errors
