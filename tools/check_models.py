import google.generativeai as genai
import os
from dotenv import load_dotenv

# Cargar entorno
load_dotenv()
api_key = os.getenv("GOOGLE_GEMINI_KEY")

if not api_key:
    print("❌ Error: No tienes la clave en el .env")
    exit()

print(f"🔑 Probando clave: {api_key[:5]}...{api_key[-3:]}")

try:
    genai.configure(api_key=api_key)
    print("📡 Conectando con Google...")
    
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
            print(f"   ✅ Disponible: {m.name}")

    if not available_models:
        print("⚠️ No se encontraron modelos compatibles con generación de texto.")
    else:
        print("\n👇 ÚSA ESTE NOMBRE EN TU CÓDIGO:")
        # Recomendamos el mejor de la lista
        recommended = next((m for m in available_models if 'flash' in m), None)
        if not recommended:
            recommended = next((m for m in available_models if 'pro' in m), available_models[0])
        
        print(f"MODELO = '{recommended.replace('models/', '')}'")

except Exception as e:
    print(f"❌ Error de conexión: {e}")