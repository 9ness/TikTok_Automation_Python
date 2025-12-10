import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

# 1. Configuración
api_key = os.getenv("MINIMAX_API_KEY")
group_id = os.getenv("MINIMAX_GROUP_ID")

# TU FILE ID (Sacado de tus capturas anteriores)
FILE_ID_RECUPERADO = 343252823626113

print(f"🔑 API Key: {api_key[:5]}...")
print(f"📂 Usando File ID original: {FILE_ID_RECUPERADO}")

url = "https://api.minimax.io/v1/voice_clone"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# Payload para crear la voz de nuevo y ver qué ID nos da
payload = {
    "file_id": FILE_ID_RECUPERADO,
    "voice_id": "voz_final_tiktok_v2", # Intentamos este nombre
    "model": "speech-2.6-hd" # El modelo HD
}

try:
    print("\n⏳ Registrando voz y esperando ID real...")
    response = requests.post(url, headers=headers, json=payload)
    
    print(f"Status Code: {response.status_code}")
    data = response.json()
    
    # Imprimimos TODO para ver el ID real
    print("\n👇 RESPUESTA DEL SERVIDOR (Busca aquí el 'voice_id'):")
    print(json.dumps(data, indent=4))
    
    if response.status_code == 200 and "voice_id" in data:
         print("\n✅ ¡LO TENEMOS!")
         print("========================================")
         print(f"TU VOICE ID REAL ES: {data['voice_id']}")
         print("========================================")
         print("Copia ese valor a tu .env")

except Exception as e:
    print(f"❌ Error: {e}")