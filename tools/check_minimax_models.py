import requests
import json
import os
from dotenv import load_dotenv, find_dotenv

# Cargar entorno
load_dotenv(find_dotenv())

def check_minimax_models():
    print("🕵️  MINIMAX MODEL CHECKER")
    print("=========================")
    
    API_KEY = os.getenv("MINIMAX_API_KEY")
    GROUP_ID = os.getenv("MINIMAX_GROUP_ID")
    
    # Usaremos una voz genérica o la del .env para probar
    VOICE_ID = os.getenv("MINIMAX_VOICE_ID") or "speech-01-turbo" 

    if not API_KEY:
        print("❌ Error: No tienes MINIMAX_API_KEY en el .env")
        return

    print(f"🔑 API Key detectada: {API_KEY[:5]}...{API_KEY[-3:]}")
    print(f"🆔 Group ID: {GROUP_ID}")
    
    # Endpoint T2A v2
    URL = "https://api.minimax.io/v1/t2a_v2"
    
    # Lista de Candidatos a Probar (Basado en Docs + Probing)
    candidates = [
        # SÉRIE TURBO (Rápidos)
        "speech-01-turbo",          # Turbo 2.5 (Standard)
        "speech-2.6-turbo",         # Turbo 2.6 (New)
        "speech-02-turbo",          # Turbo 02 (Newer)
        "speech-2.5-turbo-preview", # Preview

        # SÉRIE HD (Calidad)
        "speech-01-hd",             # HD 01 (Standard)
        "speech-2.6-hd",            # HD 2.6 (High Quality)
        "speech-02-hd",             # HD 02 (Newer)
        "speech-2.5-hd-preview",    # Preview
        
        # LEGACY / INVALIDOS COMUNES
        "speech-2.5-turbo",         # Invalid commerce name
        "speech-01",                # Legacy
    ]
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    print("\n🧪 Probando modelos candidatos con una petición mínima...")
    print("-------------------------------------------------------")
    
    valid_models = []
    
    for model in candidates:
        print(f"👉 Probando ID: '{model}'...", end=" ")
        
        # Payload mínimo de prueba
        payload = {
            "model": model,
            "text": "Hello", # Texto corto
            "stream": False,
            "voice_setting": {
                "voice_id": VOICE_ID,
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
        
        if GROUP_ID:
            payload["group_id"] = GROUP_ID
            
        try:
            response = requests.post(URL, headers=headers, json=payload, timeout=10)
            data = response.json()
            
            # Análisis de respuesta
            code = data.get("base_resp", {}).get("status_code")
            msg = data.get("base_resp", {}).get("status_msg", "Unknown")
            
            if code == 0:
                print("✅ DISPONIBLE")
                valid_models.append(model)
            elif code == 2013: # Invalid param (model not found)
                print("❌ NO EXISTE")
            else:
                print(f"⚠️ ERROR ({code}): {msg}")
                
        except Exception as e:
            print(f"💥 EXCEPCIÓN: {str(e)}")

    print("\n📋 RESUMEN DE MODELOS VÁLIDOS")
    print("============================")
    if valid_models:
        for m in valid_models:
            print(f"✅ {m}")
        print("\n💡 Usa uno de los nombres anteriores en tu configuración.")
    else:
        print("⚠️ No se encontró ningún modelo válido. Revisa tu API Key o conexión.")

if __name__ == "__main__":
    check_minimax_models()
