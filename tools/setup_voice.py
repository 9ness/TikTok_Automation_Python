import os
import glob
import requests
import json
from dotenv import load_dotenv
from moviepy.editor import AudioFileClip, concatenate_audioclips

# Cargar variables de entorno
load_dotenv()

# Configuración
API_KEY = os.getenv("MINIMAX_API_KEY")
GROUP_ID = os.getenv("MINIMAX_GROUP_ID")
BASE_URL = "https://api.minimax.io/v1"

SAMPLES_FOLDER = "voice_samples"
MERGED_FILENAME = "temp_merged_source.mp3"

def main():
    print("🎙️ INICIANDO CONFIGURACIÓN DE VOZ (MINIMAX)...")

    # 0. Validaciones Previas
    if not API_KEY:
        print("❌ ERROR: No se encontró MINIMAX_API_KEY en el archivo .env")
        return
    
    if not os.path.exists(SAMPLES_FOLDER):
        os.makedirs(SAMPLES_FOLDER)
        print(f"❌ La carpeta '{SAMPLES_FOLDER}' no existía. Se ha creado automáticamente.")
        print(f"👉 Por favor, coloca tus archivos .mp3 de muestra en '{SAMPLES_FOLDER}' y vuelve a ejecutar este script.")
        return

    # 1. PREPARACIÓN (Fusión de Audio)
    mp3_files = glob.glob(os.path.join(SAMPLES_FOLDER, "*.mp3"))
    
    if not mp3_files:
        print(f"❌ ERROR: No se encontraron archivos .mp3 en '{SAMPLES_FOLDER}'.")
        return

    print(f"📂 Se encontraron {len(mp3_files)} archivos de audio. Fusionando...")

    try:
        clips = [AudioFileClip(f) for f in mp3_files]
        if not clips:
            print("❌ No se pudieron cargar los clips de audio.")
            return
            
        final_clip = concatenate_audioclips(clips)
        final_clip.write_audiofile(MERGED_FILENAME, logger=None) # logger=None para menos ruido
        print(f"✅ Audio fusionado creado: {MERGED_FILENAME}")
        
    except Exception as e:
        print(f"❌ Error al procesar audios con MoviePy: {e}")
        return

    # 2. SUBIDA A MINIMAX (File Upload)
    print("\n⬆️ Subiendo archivo a MiniMax...")
    
    upload_url = f"{BASE_URL}/files/upload"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    
    # Según documentación habitual de MiniMax, group_id a veces va en query o body. 
    # El usuario indicó data={'purpose': 'voice_clone'}. Seguiremos esa instrucción.
    data = {
        "purpose": "voice_clone"
    }
    
    files = {
        'file': open(MERGED_FILENAME, 'rb')
    }

    try:
        # Nota: requests calcula automáticamente el Content-Type para multipart/form-data si files está presente
        response = requests.post(upload_url, headers=headers, data=data, files=files)
        
        # Cerrar el archivo
        files['file'].close()
        
        if response.status_code != 200:
            print(f"❌ Error en la subida (Status {response.status_code}): {response.text}")
            return
            
        resp_json = response.json()
        
        # Intentar obtener file_id. La estructura puede variar, adaptamos a respuesta estándar de MiniMax/T2S
        # Usualmente response: {"file_id": "...", ...} o nested
        file_id = resp_json.get("file_id") or resp_json.get("data", {}).get("file_id")
        
        if not file_id:
            print(f"❌ No se pudo extraer 'file_id' de la respuesta: {resp_json}")
            return
            
        print(f"✅ Archivo subido con éxito. File ID: {file_id}")
        
    except Exception as e:
        print(f"❌ Excepción durante la subida: {e}")
        return

    # 3. REGISTRO DE VOZ (Voice Clone)
    print("\n🧬 Clonando voz...")
    
    clone_url = f"{BASE_URL}/voice_clone"
    
    # Headers para JSON
    headers_clone = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Payload solicitado por el usuario
    payload = {
        "file_id": file_id,
        "voice_id": "voz_clonada_tiktok_v1", # ID sugerido fijo
        "model": "speech-2.5-turbo-preview" # Específico
    }
    
    if GROUP_ID:
        payload["group_id"] = GROUP_ID # Por si es necesario en esta versión de la API

    try:
        response_clone = requests.post(clone_url, headers=headers_clone, json=payload)
        
        if response_clone.status_code != 200:
            print(f"❌ Error en la clonación (Status {response_clone.status_code}): {response_clone.text}")
            return
        
        # Si llegamos aquí, asumimos éxito si es 200, aunque conviene chequear el body
        # MiniMax suele devolver el objeto creado
        print("\n" + "="*50)
        print("✅ ÉXITO. Tu Voice ID es: voz_clonada_tiktok_v1")
        print("Copia este ID y pégalo en tu archivo .env en MINIMAX_VOICE_ID")
        print("="*50)
        
    except Exception as e:
        print(f"❌ Excepción durante la clonación: {e}")

if __name__ == "__main__":
    main()
