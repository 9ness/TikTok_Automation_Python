import requests
import os
import json
from dotenv import load_dotenv

# Cargar entorno
load_dotenv()

# 1. Obtener claves
api_key = os.getenv("MINIMAX_API_KEY")
group_id = os.getenv("MINIMAX_GROUP_ID")

print(f"🔑 Usando API Key: {api_key[:5]}...")

# 2. Configurar URL y Headers
url = f"https://api.minimax.io/v1/voice_clone/list?group_id={group_id}"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# 3. Ejecutar consulta
try:
    print("\n📡 Consultando lista de voces clonadas...")
    response = requests.get(url, headers=headers)
    
    print(f"Status Code: {response.status_code}")
    data = response.json()
    
    # 4. Mostrar resultados
    if "files" in data and len(data["files"]) > 0:
        print("\n✅ ¡VOCES ENCONTRADAS! COPIA EL 'voice_id' EXACTO:")
        print("==============================================")
        
        for voice in data["files"]:
            v_id = voice.get("voice_id")
            v_name = voice.get("voice_name", "Sin Nombre")
            print(f"🎙️ NOMBRE: {v_name}")
            print(f"🆔 VOICE ID REAL: {v_id}")
            print("----------------------------------------------")
            
    else:
        print("⚠️ No se encontraron voces.")
        print("Respuesta cruda:", json.dumps(data, indent=2))

except Exception as e:
    print(f"❌ Error conectando: {e}")