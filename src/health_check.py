
import os
import requests
import json
import google.generativeai as genai
import openai
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def check_api_health(ui_callback=None):
    """
    Realiza una validación de salud de las APIs críticas (Gemini y MiniMax)
    antes de iniciar cualquier proceso de producción.
    
    Args:
        ui_callback: Función opcional para actualizar la UI (recibe un string).
        
    Retorna:
        True si todo está OK.
        False si alguna API falla (imprimiendo mensaje de error y abortando).
    """
    msg_start = "🩺 Iniciando CHECK_API_HEALTH (Pre-Flight Check)..."
    print(f"\n{msg_start}")
    if ui_callback: ui_callback(msg_start)
    
    # -------------------------------------------------------------------------
    # 1. TEST GOOGLE GEMINI (GENAI) - REQUERIDO PARA IMÁGENES
    # -------------------------------------------------------------------------
    if ui_callback: ui_callback("🔎 Verificando Google Gemini (Imágenes)...")
    gemini_key = os.getenv("GOOGLE_GEMINI_KEY")
    if not gemini_key:
        print("❌ ADVERTENCIA: No se encontró GOOGLE_GEMINI_KEY. Las imágenes fallarán.")
        if ui_callback: ui_callback("⚠️ Advertencia: Falta GOOGLE_GEMINI_KEY")
    else:
        try:
            genai.configure(api_key=gemini_key)
            # Hacemos una llamada ligera para listar modelos
            models = list(genai.list_models())
            print("   ✅ Google Gemini: ONLINE (Auth OK)")
        except Exception as e:
            print(f"❌ ERROR: Fallo en Google Gemini. Error: {e}")
            if ui_callback: ui_callback(f"❌ Error Gemini: {str(e)}")

    # -------------------------------------------------------------------------
    # 1.5. TEST OPENAI (GUIONES)
    # -------------------------------------------------------------------------
    if ui_callback: ui_callback("🤖 Verificando OpenAI (Guiones)...")
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("❌ ABORTANDO: No se encontró OPENAI_API_KEY en .env")
        if ui_callback: ui_callback("❌ Error: Falta clave OPENAI_API_KEY")
        return False
        
    try:
        client = openai.OpenAI(api_key=openai_key)
        # Llamada ligera
        client.models.list()
        print("   ✅ OpenAI: ONLINE (Auth OK)")
    except Exception as e:
        print(f"❌ ABORTANDO: Fallo crítico en OpenAI. Error: {e}")
        if ui_callback: ui_callback(f"❌ Error OpenAI: {str(e)}")
        return False

    # -------------------------------------------------------------------------
    # 2. TEST MINIMAX (VOZ) - PING REAL
    # -------------------------------------------------------------------------
    if ui_callback: ui_callback("🎙️ Verificando MiniMax (Ping Real)...")
    minimax_key = os.getenv("MINIMAX_API_KEY")
    minimax_group_id = os.getenv("MINIMAX_GROUP_ID")
    
    if not minimax_key or not minimax_group_id:
        print("❌ ABORTANDO: Faltan claves de MiniMax en .env")
        if ui_callback: ui_callback("❌ Error: Faltan claves MiniMax")
        return False
        
    # URL T2A V2 (La misma que usa producción)
    url = "https://api.minimax.io/v1/t2a_v2"
    
    headers = {
        "Authorization": f"Bearer {minimax_key}",
        "Content-Type": "application/json"
    }
    
    # Payload mínimo para ping ("Hi")
    payload = {
        "model": "speech-2.5-turbo-preview",
        "text": "Hi", 
        "stream": False,
        "group_id": minimax_group_id,
        "voice_setting": {
            "voice_id": "female-shaonv", # Voz genérica válida cualquiera
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1
        }
    }
    
    try:
        # Timeout corto de 10s para el check
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        # Analizar respuesta
        if response.status_code != 200:
             print(f"❌ ABORTANDO: MiniMax server error HTTP {response.status_code}")
             if ui_callback: ui_callback(f"❌ Error MiniMax HTTP: {response.status_code}")
             return False
             
        data = response.json()
        base_resp = data.get("base_resp", {})
        
        # Verificar código interno de MiniMax
        # 0 = OK, 1001 = Timeout, Otros = Error
        status_code = base_resp.get("status_code")
        
        if status_code == 0:
            print("   ✅ MiniMax Voice: ONLINE (Ping OK)")
            if ui_callback: ui_callback("✅ MiniMax: ONLINE")
        elif status_code == 1001:
            print(f"❌ ABORTANDO: MiniMax responde con TIMEOUT (1001). Servicios saturados.")
            if ui_callback: ui_callback("⚠️ MiniMax SATURADO (Timeout)")
            return False
        else:
            print(f"❌ ABORTANDO: Error MiniMax desconocido: {base_resp}")
            if ui_callback: ui_callback(f"❌ Error MiniMax: {status_code}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ ABORTANDO: MiniMax Ping Timeout (>10s). La API está caída o muy lenta.")
        if ui_callback: ui_callback("❌ MiniMax Timeout (API Lenta)")
        return False
    except Exception as e:
        print(f"❌ ABORTANDO: Excepción conectando a MiniMax: {e}")
        if ui_callback: ui_callback(f"❌ Excepción MiniMax: {str(e)}")
        return False

    print("🚀 SISTEMAS OK. Iniciando producción...\n")
    if ui_callback: ui_callback("🚀 SISTEMAS OK. Arrancando...")
    return True
