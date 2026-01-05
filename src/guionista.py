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
             
        # Listar carpetas reales y limpiarlas para que la IA las entienda mejor
        folders = [f for f in os.listdir(full_path) if os.path.isdir(os.path.join(full_path, f))]
        
        if not folders:
            return "Cualquier presidente de USA (Sin restricción)"
            
        # Limpieza Avanzada (CamelCase -> Spaced)
        # Ej: GeorgeWBush -> George W Bush
        # Ej: WarrenGHarding -> Warren G Harding
        clean_names = []
        print("\n🔎 TRADUCCIÓN DE NOMBRES DETECTADA:")
        for name in folders:
            # 1. Si ya tiene espacios, respetar. Si no, aplicar split por mayúsculas.
            if " " in name:
                clean = name
            else:
                 # Regex: Insertar espacio antes de cualquier Mayúscula que NO sea la primera letra
                clean = re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
            
            clean_names.append(clean)
            print(f"  - {name} \t-> {clean}")
            
        print(f"✅ Total procesados: {len(clean_names)}\n")
        return ", ".join(clean_names)
        
    except Exception as e:
        print(f"⚠️ Error listando assets: {e}")
        return "Cualquier presidente de USA"

def generate_script(user_topic=None, creative_mode=False, app_mode="PRESIDENTS_TOP5"):
    """
    Genera un guion usando Google Gemini.
    - user_topic: String con el tema específico o None para aleatorio.
    - creative_mode: Bool. Si True, usa prompts dinámicos. Si False, usa prompts estrictos (Legacy).
    - app_mode: "PRESIDENTS_TOP5" o "MYSTERY_AI".
    """
    print("🤖 Iniciando Motor de Guiones (Gemini)...")
    
    # 1. Configuración de API
    api_key = os.getenv("GOOGLE_GEMINI_KEY")
    if not api_key:
        raise ValueError("GOOGLE_GEMINI_KEY not found in environment variables.")

    genai.configure(api_key=api_key)
    
    # 2. Cargar Prompts
    config = load_config()
    prompts = config.get("prompts", {})
    
    # 3. Obtener Whitelist de Personajes
    available_chars = get_available_assets()
    print(f"📋 Whitelist DETALLADA inyectada a Gemini ({len(available_chars.split(','))} personajes detectados):")
    print(f"LISTA COMPLETA: {available_chars}")
    
    # 3.5 DETECTAR MODO (Argumento Prioritario)
    # app_mode viene pasad desde main.py que tiene el estado real de la UI
    
    if app_mode == "MYSTERY_AI":
        print(f"🕵️‍♂️ MODO MYSTERY AI DETECTADO")
        base_prompt = prompts.get("mystery_viral_prompt", "")
        
        if not user_topic or not user_topic.strip():
            # TREND HUNTER MODE
            print("   -> Input vacío. Activando modo 'Trend Hunter'")
            topic_str = "NO TOPIC PROVIDED. Your task is to research or select a highly viral, mysterious, or breaking news topic currently trending in the US. Focus on something that would captivate an adult audience (40-50 years old)."
        else:
            # USER TOPIC MODE
            print(f"   -> Input recibido: {user_topic}")
            # Injecting forceful expansion instruction directly into the topic slot
            topic_str = f"{user_topic}. (CRITICAL COMMAND: You MUST expand this specific topic into EXACTLY 12 distinct scenes/images. Do not summarize. If the topic is simple, break it down into smaller chronological details to fill 12 scenes.)"
            
        if not base_prompt:
             # Fallback
            final_prompt = "Generate a viral script about: " + str(topic_str) + ". Return JSON with 'scenes'."
        else:
            final_prompt = base_prompt.replace("{{TEMA}}", topic_str)
            
    else:
        # MODO CLÁSICO (PRESIDENTS_TOP5)
        if user_topic and user_topic.strip():
            # Modo Específico
            key = "script_specific_creative" if creative_mode else "script_specific_topic"
            base_prompt = prompts.get(key, "")
            if not base_prompt:
                 # Fallback simple
                final_prompt = f"Genera un guion de debate presidencial divertido sobre: {user_topic}. Devuelve JSON."
            else:
                final_prompt = base_prompt.replace("{{TEMA}}", user_topic)
        else:
            # Modo Aleatorio
            key = "script_random_creative" if creative_mode else "script_random_topic"
            base_prompt = prompts.get(key, "")
            if not base_prompt:
                final_prompt = "Genera un guion de debate presidencial divertido sobre un tema viral aleatorio. Devuelve JSON."
            else:
                final_prompt = base_prompt
            
        # INYECCIÓN FINAL DE WHITELIST
        if "{{AVAILABLE_CHARACTERS}}" in final_prompt:
            final_prompt = final_prompt.replace("{{AVAILABLE_CHARACTERS}}", available_chars)

        # INYECCIÓN FINAL DE ESTILO GLOBAL
        if "{{GLOBAL_STYLE}}" in final_prompt:
            global_style = prompts.get("global_viral_style", "")
            final_prompt = final_prompt.replace("{{GLOBAL_STYLE}}", global_style)

    # 4. Llamada a Gemini
    try:
        model = genai.GenerativeModel('gemini-3-flash-preview') # Modelo confirmado disponible
        
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

def save_scripts_to_txt(script_data, output_base_folder="inputs_generados", app_mode="PRESIDENTS_TOP5"):
    """
    Guarda el script_data en archivos individuales .txt con estructura ESTRICTA.
    Soporta PRESIDENTS_TOP5 y MYSTERY_AI.
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
        
        # Robustez: Si Gemini devuelve una lista (ej: por líneas), la unimos.
        if isinstance(content, list):
            content = "\n".join([str(line) for line in content])
        
        # Asegurar que sea string
        if not isinstance(content, str):
            content = str(content)
            
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        saved_files.append(path)

    # --- MODO MYSTERY AI ---
    if "scenes" in script_data:
        # Estructura: "full_script_txt" y "scenes".
        # ESTRATEGIA: Guardamos por ESCENAS individuales para que el editor pueda sincronizar
        # imagen exacta con audio exacto.
        
        scenes = script_data.get("scenes", [])
        
        for sc in scenes:
            order = sc.get("order", 0)
            text = sc.get("narration_segment", "")
            if not text: continue
            
            # Nombre: 01_scene, 02_scene...
            filename = f"{int(order):02d}_scene.txt"
            write_file(filename, text)
            
        print(f"✅ [MYSTERY_AI] Guion desplegado en {len(saved_files)} escenas en: {full_path}")
        return full_path

    # --- MODO PRESIDENTS TOP5 (LEGACY) ---
    
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
    # Usar el texto generado por la IA (Dynamic CTA)
    text_1 = item_1_data.get("text", "")
    if not text_1:
         # Fallback solo si la IA falló
         text_1 = "Who do you think occupies the first place? Leave your answer on the comments."

    safe_name_1 = normalize_filename(name_1)
    filename_1 = f"1_{safe_name_1}.txt"
    write_file(filename_1, text_1)
            
    print(f"✅ Guion desplegado en {len(saved_files)} archivos en: {full_path}")
    return full_path
