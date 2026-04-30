import os
import json
import math
import re
import random
from datetime import datetime
import openai
from dotenv import load_dotenv

# Constantes para calcular palabras por ítem que den >=60s de vídeo con margen.
# Velocidad de narración medida con MiniMax: ~3.0 palabras/segundo (más rápido del esperado).
# Target = 195 palabras para asegurar ~65s a velocidad rápida (5s de margen sobre 60s).
TARGET_TOTAL_WORDS = 195  # objetivo con margen (~65s a 3.0 wps; ~78s a 2.5 wps)
INTRO_WORDS_WITH_HOOK = 21   # título (~5) + hook (~14) + "Number N:" (~2)
INTRO_WORDS_NO_HOOK = 7      # título (~5) + "Number N:" (~2)
OUTRO_WORDS = 20             # texto fijo del Top 1 (20 palabras exactas)

# Pool de ángulos controvertidos para modo aleatorio.
# Audiencia objetivo: hombres 45+ interesados en poder, dinero, historia oculta, desconfiados de medios.
# Patrón GANADOR confirmado por el usuario: superlativos + daño a entidad específica + rankings por trait medible.
# Cada llamada random pica uno distinto para forzar variedad y evitar repeticiones.
RANDOM_ANGLES = [
    # === PATRÓN GANADOR #1: "caused the most damage to X" ===
    "US Presidents who caused the most damage to the United States",
    "US Presidents who caused the most damage to the world",
    "US Presidents who caused the most damage to the US economy",
    "US Presidents who caused the most damage to the American middle class",
    "US Presidents who caused the most damage to the US working class",
    "US Presidents who caused the most damage to US global reputation",
    "US Presidents who caused the most damage to the US Constitution",
    "US Presidents who caused the most damage to the US dollar",
    "US Presidents who caused the most damage to American democracy",
    "US Presidents who caused the most damage to US foreign alliances",
    "US Presidents who caused the most damage to US national security",
    "US Presidents who caused the most damage to the American military",
    "US Presidents who caused the most damage to American jobs",
    # === PATRÓN GANADOR #2: rankings por trait medible ===
    "US Presidents ranked by IQ — from highest to lowest",
    "US Presidents with the highest IQ",
    "US Presidents with the lowest IQ",
    "Most narcissistic US Presidents in history",
    "Most corrupt US Presidents ever recorded",
    "Most manipulative US Presidents the country ever had",
    "US Presidents who lied the most to the American public",
    "US Presidents with the worst decision-making of all",
    "Most incompetent US Presidents the media tried to protect",
    # === PATRÓN GANADOR #3: worst + pattern classic ===
    "Worst US Presidents of the last 100 years",
    "Worst US Presidents of the 20th century",
    "Worst US Presidents in modern history",
    # === Power plays / abuse ===
    "US Presidents who bent the Constitution to keep power",
    "US Presidents who acted like dictators inside the Oval Office",
    # === Money & insider ===
    "US Presidents who secretly got rich off Wall Street",
    "US Presidents who built hidden fortunes while in office",
    "US Presidents who sold out America to corporate donors",
    "US Presidents who sold out America to foreign powers",
    # === Conspiracy / classified ===
    "Classified CIA programs US Presidents personally approved",
    "Covert wars and black ops US Presidents hid from voters",
    # === Health / hidden ===
    "US Presidents who hid serious mental decline while in office",
    "Addiction and substance abuse US Presidents never admitted",
    # === Scandal / cover-up ===
    "Major scandals the press helped bury for sitting US Presidents",
    "Affairs and blackmail material mainstream history buried",
    # === Pre-presidency dark past ===
    "Crimes US Presidents committed BEFORE office — never prosecuted",
    # === Betrayal ===
    "US Presidents who betrayed their voters the moment they took power",
    "Campaign promises US Presidents killed within weeks of inauguration",
    # === Foreign / dictator ===
    "Secret friendships between US Presidents and foreign dictators",
    # === Race / dark history ===
    "Racist beliefs of US Presidents the textbooks never mention",
    # === Near misses ===
    "How close US Presidents came to triggering World War III",
]


def _pick_random_angle():
    return random.choice(RANDOM_ANGLES)


# Pools de variedad para el modo CREATIVO (creative_mode=True).
# Sortea uno por llamada para que cada vídeo creativo tenga fraseo distinto.

# Estilos de hook de 12-15 palabras — se pasa como directriz al modelo.
CREATIVE_HOOK_STYLES = [
    "RHETORICAL QUESTION — Start with 'Why did...' / 'What if...' / 'How did...' targeting the seed topic. 12-15 words.",
    "IMPOSSIBLE CLAIM — Make an outrageous but documented claim. Start with 'You have been lied to about...' or similar. 12-15 words.",
    "DARK REVELATION — Use declassified / buried / hidden language. Example tone: 'What I'm about to show you was classified for decades.' 12-15 words.",
    "DIRECT CONFRONTATION — Accuse the establishment: 'The media never wanted you to know...' / 'They erased this from history class...'. 12-15 words.",
    "CHALLENGE THE VIEWER — 'Bet you don't know which President did this.' Invite them to test their knowledge. 12-15 words.",
    "TIME-WARP HOOK — Tie past decision to present consequence: 'One choice in 1968 still haunts America today.' 12-15 words.",
    "NUMBERED SHOCK — Percussive staccato: 'Five Presidents. One decision each. Millions ruined.' 12-15 words.",
    "INSIDER LANGUAGE — 'Declassified files just dropped. Here's what Washington didn't want leaked.' 12-15 words.",
    "STAKES HOOK — Put a number on the damage: 'These five men cost America trillions — and nobody was punished.' 12-15 words.",
    "PERSONAL ATTACK ON NARRATIVE — 'Everything you learned in school about these Presidents is wrong.' 12-15 words.",
]

# Frases de engagement para el 2º ítem narrado — 8-10 palabras, petición de like/share.
CREATIVE_ENGAGEMENT_SEEDS = [
    "Hit like if you already knew this one.",
    "Share this with someone still asleep about US history.",
    "Double tap if this made your blood boil.",
    "Send this to someone who trusts Washington too much.",
    "Like if you saw this coming — most people didn't.",
    "Save this video before it disappears from the platform.",
    "Tag a history buff who needs to see number one.",
    "Drop a like if this changes how you see America.",
    "Smash that like if you're already angry at number four.",
    "Share this with your father — he'll thank you later.",
    "Like if this should be taught in every school.",
    "Save this one — you'll want to rewatch number one.",
]

# Frases challenge/comment para el cierre del item_1 (mystery reveal) — 15-20 palabras.
CREATIVE_MYSTERY_SEEDS = [
    "I bet you can't guess who takes number one. Drop your answer in the comments before I reveal it.",
    "Only real history buffs guess this correctly. Comment your pick and I'll reply to everyone who nails it.",
    "The real number one will shock you. Comment your guess before the algorithm buries this clip.",
    "Think you know American history? Prove it. Drop number one's name in the comments right now.",
    "Who do you think is number one? Leave a name in the comments before the reveal surprises you.",
    "Here's a challenge: guess number one. Comment your answer and I'll tell you if you got it right.",
    "Number one ruined more lives than every other name combined. Who is it? Comment now.",
    "You will not believe number one. But first, guess. Drop a name in the comments below.",
    "Comment who you think number one is before watching the reveal. Let's see who's paying attention.",
    "Only one percent guess number one correctly. Think you're part of that one percent? Comment now.",
]


def _pick_creative_seeds():
    return {
        "hook": random.choice(CREATIVE_HOOK_STYLES),
        "engagement": random.choice(CREATIVE_ENGAGEMENT_SEEDS),
        "mystery": random.choice(CREATIVE_MYSTERY_SEEDS),
    }


def _calc_word_range(top_count, include_hook):
    """Devuelve (low, high) palabras por ítem de contenido para cuadrar ~1min."""
    intro = INTRO_WORDS_WITH_HOOK if include_hook else INTRO_WORDS_NO_HOOK
    num_content = top_count - 1  # ítems N..2; el 1 es el reveal de misterio
    avg = (TARGET_TOTAL_WORDS - intro - OUTRO_WORDS) / num_content
    low = math.floor(avg) - 1
    high = math.ceil(avg) + 1
    return low, high


def _build_items_spec(top_count, words_low, words_high, creative_mode, engagement_seed=None):
    """Genera el bloque completo 'ITEMS N, N-1, ..., 2' con closings dinámicos.
    Si creative_mode, usa engagement_seed (frase de like/share sorteada) en el 2º ítem narrado."""
    items_numbers = list(range(top_count, 1, -1))  # [5,4,3,2] para top_count=5
    items_list = ", ".join(str(n) for n in items_numbers)
    first = top_count

    lines = [f"ITEMS {items_list} (txt_{first}_text through txt_2_text):"]

    if creative_mode:
        lines.append("START FORMAT: Text MUST begin with the president's full name (first and last) followed by a period.")
    else:
        lines.append("START FORMAT: Text MUST begin with the president's full name (first and last) followed by a period. Example: 'James K. Polk. He was known for...' Example: 'William Howard Taft. His secret life was...'")

    lines.append(f"LENGTH: EXACTLY {words_low}-{words_high} words per item. CRITICAL for ~1 minute video duration.")
    lines.append("CLOSINGS:")

    for idx, k in enumerate(items_numbers):
        is_second_spoken = (idx == 1)
        if creative_mode and is_second_spoken:
            seed = engagement_seed or "Hit like if you knew this secret."
            lines.append(f"Item {k} ends with an 8-10 WORD LIKE/SHARE engagement phrase (use this seed verbatim, or adapt it only to reference the video's topic): '{seed}' — then append ' Number {k-1}:'")
        elif is_second_spoken:
            lines.append(f"Item {k} ends with: 'If you dare to learn more, drop a like. Number {k-1}:'")
        else:
            lines.append(f"Item {k} ends with: 'Number {k-1}:'")

    return "\n".join(lines)


def _build_json_items(top_count):
    """'item_5 (object with name, text), item_4, item_3, item_2' dinámico."""
    parts = [f"item_{top_count} (object with name, text)"]
    for k in range(top_count - 1, 1, -1):
        parts.append(f"item_{k}")
    return ", ".join(parts)

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
        for name in folders:
            # 1. Si ya tiene espacios, respetar. Si no, aplicar split por mayúsculas.
            if " " in name:
                clean = name
            else:
                 # Regex: Insertar espacio antes de cualquier Mayúscula que NO sea la primera letra
                clean = re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
            
            clean_names.append(clean)
            
        # --- NOVEDAD: BARAJADO ALEATORIO ---
        # Barajamos la lista para que la IA no siempre vea los mismos nombres al principio
        random.shuffle(clean_names)
        
        # Logs más robustos para Windows (sin emojis si hay riesgo de error, o usando safe prints)
        try:
            print(f"\n--- ASSETS DETECTADOS ({len(clean_names)}) ---")
            print(f"Muestra barajada: {', '.join(clean_names[:5])}...")
        except UnicodeEncodeError:
            pass # Si falla el print por codificación, seguimos adelante para no romper el flujo
            
        return ", ".join(clean_names)
        
    except Exception as e:
        try:
            print(f"Error listando assets: {e}")
        except:
            pass
        return "Cualquier presidente de USA"

def generate_script(user_topic=None, creative_mode=False, title_prefix="The 5", include_history=True, include_hook=True, top_count=5):
    """
    Genera un guion de Top N Presidentes USA usando OpenAI.
    - user_topic: String con el tema específico o None para aleatorio.
    - creative_mode: Bool. Si True, usa prompts dinámicos. Si False, usa prompts estrictos (Legacy).
    - title_prefix: "The N" o "Top N" — fuerza el inicio del título del video.
    - include_history: Bool. Si True añade " in US history" al final; si False, sin sufijo.
    - include_hook: Bool. Si True añade línea de hook ("Save this video..." / hook dinámico creativo).
    - top_count: 3, 4 o 5 — número de presidentes en el ranking. Ajusta automáticamente palabras/ítem para ~1min.
    """
    print("🤖 Iniciando Motor de Guiones (OpenAI)...")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables.")

    client = openai.OpenAI(api_key=api_key)

    config = load_config()
    prompts = config.get("prompts", {})

    available_chars = get_available_assets()
    print(f"📋 Whitelist DETALLADA inyectada a Gemini ({len(available_chars.split(','))} personajes detectados):")
    print(f"LISTA COMPLETA: {available_chars}")

    history_suffix = " in US history" if include_history else ""

    if user_topic and user_topic.strip():
        key = "script_specific_creative" if creative_mode else "script_specific_topic"
        base_prompt = prompts.get(key, "")
        if not base_prompt:
            final_prompt = f"Generate a TikTok Top 5 US Presidents script about: {user_topic}. Title must start with '{title_prefix}' and end with '{history_suffix}'. Return JSON."
        else:
            final_prompt = base_prompt.replace("{{TEMA}}", user_topic)
    else:
        key = "script_random_creative" if creative_mode else "script_random_topic"
        base_prompt = prompts.get(key, "")
        if not base_prompt:
            final_prompt = f"Generate a TikTok Top 5 US Presidents script about a random viral topic. Title must start with '{title_prefix}' and end with '{history_suffix}'. Return JSON."
        else:
            final_prompt = base_prompt

    # En modo creativo, sortea semillas para hook / engagement / mystery (variedad forzada)
    creative_seeds = _pick_creative_seeds() if creative_mode else None

    if include_hook:
        if creative_mode:
            hook_style = creative_seeds["hook"]
            hook_line = f"HOOK LINE (12-15 WORDS — write it in this STYLE for this specific video): {hook_style} FORBIDDEN: 'Today we talk about', 'Hello guys', 'In this video'.\n"
        else:
            hook_line = "HOOK LINE: 'Save this video before they delete it. The government doesn't want you to see this.'\n"
    else:
        hook_line = ""

    words_low, words_high = _calc_word_range(top_count, include_hook)
    engagement_seed = creative_seeds["engagement"] if creative_mode else None
    items_spec = _build_items_spec(top_count, words_low, words_high, creative_mode, engagement_seed=engagement_seed)
    json_items = _build_json_items(top_count)

    final_prompt = final_prompt.replace("{{TITLE_PREFIX}}", title_prefix)
    final_prompt = final_prompt.replace("{{HISTORY_SUFFIX}}", history_suffix)
    final_prompt = final_prompt.replace("{{HOOK_LINE}}", hook_line)
    final_prompt = final_prompt.replace("{{OPENING_NUMBER}}", str(top_count))
    final_prompt = final_prompt.replace("{{ITEMS_SPEC}}", items_spec)
    final_prompt = final_prompt.replace("{{JSON_ITEMS}}", json_items)

    # Si es modo creativo, inyecta semilla de cierre misterio (item_1)
    if creative_mode and "{{CREATIVE_MYSTERY_SEED}}" in final_prompt:
        final_prompt = final_prompt.replace("{{CREATIVE_MYSTERY_SEED}}", creative_seeds["mystery"])
    if creative_mode:
        print(f"🎨 Creative seeds → hook: {creative_seeds['hook'][:40]}... | engagement: {creative_seeds['engagement'][:40]}... | mystery: {creative_seeds['mystery'][:40]}...")

    # Si es modo aleatorio, inyecta un ángulo controvertido distinto cada vez (variedad forzada)
    if "{{RANDOM_ANGLE}}" in final_prompt:
        random_angle = _pick_random_angle()
        print(f"🎲 Ángulo aleatorio inyectado: {random_angle}")
        final_prompt = final_prompt.replace("{{RANDOM_ANGLE}}", random_angle)

    if "{{AVAILABLE_CHARACTERS}}" in final_prompt:
        final_prompt = final_prompt.replace("{{AVAILABLE_CHARACTERS}}", available_chars)

    if "{{GLOBAL_STYLE}}" in final_prompt:
        global_style = prompts.get("global_viral_style", "")
        final_prompt = final_prompt.replace("{{GLOBAL_STYLE}}", global_style)

    # 4. Llamada a OpenAI
    try:
        # Recomendación: gpt-5.4-mini es el modelo más eficiente y moderno (Lanzamiento Marzo 2026).
        model = "gpt-5.4-mini"
        
        # Forzar respuesta JSON en la instrucción si no está
        if "json" not in final_prompt.lower():
            final_prompt += "\n\nIMPORTANTE: Responde ÚNICAMENTE con un JSON válido."

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a specialized TikTok viral scriptwriter. You must always return a valid JSON response."},
                {"role": "user", "content": final_prompt}
            ],
            response_format={ "type": "json_object" }
        )
        
        text_response = response.choices[0].message.content
        
        # 4. Limpieza y Parseo de JSON
        script_data = json.loads(text_response)
        return script_data
        
    except json.JSONDecodeError:
        print("❌ Error: OpenAI no devolvió un JSON válido.")
        print(f"Respuesta cruda: {text_response}")
        raise ValueError("La IA generó texto, pero no en formato JSON. Inténtalo de nuevo.")
    except Exception as e:
        print(f"❌ Error conectando con OpenAI: {e}")
        raise e

def save_scripts_to_txt(script_data, output_base_folder="inputs_generados", top_count=5):
    """
    Guarda el script_data de Presidents Top N en archivos .txt con estructura estricta.
    top_count determina cuántos ítems de contenido (N..2) se esperan antes del reveal (item_1).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"guion_{timestamp}"
    full_path = os.path.join(output_base_folder, folder_name)

    if not os.path.exists(full_path):
        os.makedirs(full_path, exist_ok=True)

    saved_files = []

    def write_file(filename, content):
        path = os.path.join(full_path, filename)
        if isinstance(content, list):
            content = "\n".join([str(line) for line in content])
        if not isinstance(content, str):
            content = str(content)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        saved_files.append(path)

    # 2. Guardar Intro
    intro_data = script_data.get("intro", {})
    intro_text = intro_data.get("text", "")
    if intro_text:
        write_file("0_intro.txt", intro_text)
        
    # 3. Guardar Items (N al 2) — dinámico según top_count
    items = [f"item_{n}" for n in range(top_count, 1, -1)]

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
