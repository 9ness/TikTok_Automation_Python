import os
import requests
import json
import glob
from dotenv import load_dotenv, find_dotenv
from datetime import datetime

load_dotenv(find_dotenv())

def generate_audios_from_text_folder(txt_folder_path, output_base_path):
    print(f"🎙️ Iniciando locución PREMIUM (HD T2A V2) para: {os.path.abspath(txt_folder_path)}")

    # 1. Configuración
    API_KEY = os.getenv("MINIMAX_API_KEY")
    VOICE_ID = os.getenv("MINIMAX_VOICE_ID")
    GROUP_ID = os.getenv("MINIMAX_GROUP_ID")
    # URL OBLIGATORIA PARA VOCES HD
    URL = "https://api.minimax.io/v1/t2a_v2"
    
    if not API_KEY or not VOICE_ID:
        raise ValueError("❌ Faltan claves en .env")
        
    # 2. Carpeta Salida
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_folder_name = f"audios_input_{timestamp}"
    full_output_path = os.path.join(output_base_path, output_folder_name)
    os.makedirs(full_output_path, exist_ok=True)
    
    # 3. Buscar Textos
    txt_files = glob.glob(os.path.join(txt_folder_path, "*.txt"))
    if not txt_files:
        print("⚠️ No hay archivos .txt")
        return None
        
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    print(f"⏳ Procesando {len(txt_files)} archivos con speech-2.6-turbo...")
    
    for txt_file in txt_files:
        filename = os.path.basename(txt_file)
        name_no_ext = os.path.splitext(filename)[0]
        
        with open(txt_file, 'r', encoding='utf-8') as f:
            text_content = f.read().strip()
            
        if not text_content: continue
        
        # PAYLOAD ESPECIAL V2
        payload = {
            "model": "speech-2.6-turbo",
            "text": text_content,
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
            response = requests.post(URL, headers=headers, json=payload)
            response_data = response.json()
            
            # MANEJO DE RESPUESTA V2 (Viene en HEX dentro del JSON, no binary stream directo)
            if response_data.get("base_resp", {}).get("status_code") == 0:
                if "data" in response_data and "audio" in response_data["data"]:
                    hex_audio = response_data["data"]["audio"]
                    audio_bytes = bytes.fromhex(hex_audio)
                    
                    mp3_path = os.path.join(full_output_path, f"{name_no_ext}.mp3")
                    with open(mp3_path, "wb") as f_out:
                        f_out.write(audio_bytes)
                    print(f"   ✅ Generado: {filename}")
                else:
                    print(f"⚠️ JSON incompleto: {response_data}")
            else:
                print(f"❌ Error API: {response_data}")
                raise Exception(f"Fallo MiniMax: {response_data.get('base_resp')}")
                
        except Exception as e:
            print(f"❌ Excepción: {e}")
            raise e
            
    print(f"✅ Locución finalizada en: {full_output_path}")
    return full_output_path
