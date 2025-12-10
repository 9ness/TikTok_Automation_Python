import requests
import os
from dotenv import load_dotenv

# Cargar claves
load_dotenv()
api_key = os.getenv("MINIMAX_API_KEY")
group_id = os.getenv("MINIMAX_GROUP_ID")

if not api_key:
    print("❌ ERROR: No se encontró MINIMAX_API_KEY en el .env")
    exit()

# DATOS MANUALES (Sacados de tu captura de error)
FILE_ID_SUBIDO = 343252823626113  # <--- TU ID
NOMBRE_VOZ = "voz_clonada_tiktok_v1"

print(f"🚀 Registrando voz con File ID: {FILE_ID_SUBIDO}...")

url = "https://api.minimax.io/v1/voice_clone"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "file_id": FILE_ID_SUBIDO,
    "voice_id": NOMBRE_VOZ,
    "model": "speech-2.6-hd" # Modelo de alta calidad
}

try:
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status() # Lanzar error si falla
    
    print("\n✅ ¡ÉXITO TOTAL!")
    print("==========================================")
    print(f"TU VOICE ID ES: {NOMBRE_VOZ}")
    print("==========================================")
    print("👉 Ahora ve a tu archivo .env y pon:")
    print(f"MINIMAX_VOICE_ID={NOMBRE_VOZ}")
    
except Exception as e:
    print(f"❌ Error al clonar: {e}")
    print("Respuesta:", response.text if 'response' in locals() else "Sin respuesta")