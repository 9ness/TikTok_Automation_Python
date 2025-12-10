import os
import json
import re
import random
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def load_config(config_path="config/config.json"):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def normalize_filename(name):
    """
    Limpia el nombre para que sea seguro como archivo en Windows.
    Quita acentos y caracteres raros.
    """
    # 1. Normalización básica caracteres latinos
    replacements = (
        ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
        ("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"),
        ("ñ", "n"), ("Ñ", "N")
    )
    for a, b in replacements:
        name = name.replace(a, b)
        
    # 2. Dejar solo alfanuméricos, guiones y espacios
    name = re.sub(r'[^a-zA-Z0-9_\-\s]', '', name)
    # 3. Espacios a guiones bajos
    name = name.replace(' ', '_')
    return name

def get_available_assets():
    """
    Lista dinámicamente las carpetas de presidentes disponibles para restringir a Gemini.
    """
    try:
        config = load_config()
        # Construimos la ruta asumiendo estructura: root/presidents_folder
        # Ojo: load_config ya nos da 'paths', podemos reusarlo si instanciamos o leemos el json raw
        # Para ser seguros y rápidos, leemos la variable de entorno y json crudo
        root = os.getenv("TIKTOK_ROOT_PATH")
        if not root: return "Cualquier presidente de USA (Sin restricción)"
        
        folders_cfg = config.get("folder_structure", {})
        presis_folder = folders_cfg.get("presidents_folder", "BIBLIOTECA_PRESIDENTES")
        full_path = os.path.join(root, presis_folder)
        
        if not os.path.exists(full_path):
             return "Cualquier presidente de USA (Sin restricción)"
             
        # Listar carpetas reales
        folders = [f for f in os.listdir(full_path) if os.path.isdir(os.path.join(full_path, f))]
        
        if not folders:
            return "Cualquier presidente de USA (Sin restricción)"
            
        return ", ".join(folders)
        
    except Exception as e:
        print(f"⚠️ Error listando assets: {e}")
        return "Cualquier presidente de USA"

def generate_script(user_topic=None):
    """
    Genera un guion usando Google Gemini.
    - user_topic: String con el tema específico o None para aleatorio.
    """
    print("🤖 Iniciando Motor de Guiones (Gemini)...")
    
    # 1. Configuración de API
    api_key = os.getenv("GOOGLE_GEMINI_KEY")
    if not api_key:
        raise ValueError("❌ Faltan las API KEYS. Configura GOOGLE_GEMINI_KEY en .env")

    genai.configure(api_key=api_key)
    
    # 2. Cargar Prompts
    config = load_config()
    prompts = config.get("prompts", {})
    
    # 3. Obtener Whitelist de Personajes
    available_chars = get_available_assets()
    print(f"📋 Whitelist inyectada a Gemini ({len(available_chars.split(','))} personajes)")
    
    if user_topic and user_topic.strip():
        # Modo Específico
        base_prompt = prompts.get("script_specific_topic", "")
        if not base_prompt:
             # Fallback simple
            final_prompt = f"Genera un guion de debate presidencial divertido sobre: {user_topic}. Devuelve JSON."
        else:
            final_prompt = base_prompt.replace("{{TEMA}}", user_topic)
    else:
        # Modo Aleatorio
        base_prompt = prompts.get("script_random_topic", "")
        if not base_prompt:
            final_prompt = "Genera un guion de debate presidencial divertido sobre un tema viral aleatorio. Devuelve JSON."
        else:
            final_prompt = base_prompt
            
    # INYECCIÓN FINAL DE WHITELIST
    if "{{AVAILABLE_CHARACTERS}}" in final_prompt:
        final_prompt = final_prompt.replace("{{AVAILABLE_CHARACTERS}}", available_chars)

    # 4. Llamada a Gemini
    try:
        model = genai.GenerativeModel('gemini-2.5-flash') # Modelo confirmado disponible
        
        # Forzar respuesta JSON en la instrucción si no está
        if "json" not in final_prompt.lower():
            final_prompt += "\n\nIMPORTANTE: Responde ÚNICAMENTE con un JSON válido."

        response = model.generate_content(final_prompt)
        text_response = response.text
        
        # 4. Limpieza y Parseo de JSON
        # A veces Gemini envuelve en ```json ... ```
        clean_text = re.sub(r'```json\s*|\s*```', '', text_response).strip()
        
        script_data = json.loads(clean_text)
        return script_data
        
    except json.JSONDecodeError:
        print("❌ Error: Gemini no devolvió un JSON válido.")
        print(f"Respuesta cruda: {text_response}")
        raise ValueError("La IA generó texto, pero no en formato JSON. Inténtalo de nuevo.")
    except Exception as e:
        print(f"❌ Error conectando con Gemini: {e}")
        raise e

def save_scripts_to_txt(script_data, output_base_folder="inputs_generados"):
    """
    Guarda el script_data en archivos individuales .txt con estructura ESTRICTA.
    """
    # 1. Crear carpeta con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"guion_{timestamp}"
    full_path = os.path.join(output_base_folder, folder_name)
    
    if not os.path.exists(full_path):
        os.makedirs(full_path, exist_ok=True)
        
    saved_files = []

    # Helper para guardar
    def write_file(filename, content):
        path = os.path.join(full_path, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        saved_files.append(path)

    # 2. Guardar Intro
    intro_data = script_data.get("intro", {})
    intro_text = intro_data.get("text", "")
    if intro_text:
        write_file("0_intro.txt", intro_text)
        
    # 3. Guardar Items (5 al 2)
    # Lista de claves a procesar en orden inverso para claridad, pero guardamos por nombre
    items = ["item_5", "item_4", "item_3", "item_2"]
    
    for key in items:
        item_data = script_data.get(key, {})
        name = item_data.get("name", f"Unknown_{key}")
        text = item_data.get("text", "")
        
        # Extraer número del key (ej: item_5 -> 5)
        num = key.split('_')[1]
        
        safe_name = normalize_filename(name)
        filename = f"{num}_{safe_name}.txt"
        
        if text:
            write_file(filename, text)

    # 4. Guardar Item 1 (Especial)
    # Nombre viene del JSON, Texto es FIJO (misterio)
    item_1_data = script_data.get("item_1", {})
    name_1 = item_1_data.get("name", "Unknown_1")
    # El texto misterioso debería venir del prompt, pero lo forzamos aquí por seguridad si así se pide
    # O confiamos en que el prompt lo trajo. El usuario pidió: "fuerza el texto misterioso para el audio"
    text_1_fixed = "Who do you think occupies the first place? Leave your answer on the comments, and be surprised with the answer."
    
    safe_name_1 = normalize_filename(name_1)
    filename_1 = f"1_{safe_name_1}.txt"
    write_file(filename_1, text_1_fixed)
            
    print(f"✅ Guion desplegado en {len(saved_files)} archivos en: {full_path}")
    return full_path
