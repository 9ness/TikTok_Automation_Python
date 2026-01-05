import google.generativeai as genai
import os
from dotenv import load_dotenv

# 1. Cargar configuración desde el archivo .env
load_dotenv()
api_key = os.getenv("GOOGLE_GEMINI_KEY")

if not api_key:
    print("❌ ERROR: No se encontró GOOGLE_GEMINI_KEY en el archivo .env")
    exit()

print(f"🔑 Usando clave: {api_key[:5]}...{api_key[-3:]}")

try:
    # 2. Configurar la librería
    genai.configure(api_key=api_key)
    print("📡 Conectando con Google AI Studio...\n")
    
    print("--- 🔎 BUSCANDO MODELOS DISPONIBLES (TODOS) ---")
    
    all_models = list(genai.list_models())
    image_models = []

    for m in all_models:
        # Imprimimos información básica de cada modelo para inspección manual
        capabilities = ", ".join(m.supported_generation_methods)
        print(f"📍 ID: {m.name}")
        print(f"   └ Capacidad: {capabilities}")

        # Filtramos los que probablemente sean de Imagen 3 (Nanobanana)
        if 'image' in m.name.lower() or 'imagen' in m.name.lower() or 'predict' in m.supported_generation_methods:
            image_models.append(m.name)
            print("   🌟 [POTENCIAL MODELO DE IMAGEN]")
        print("-" * 50)

    # 3. Resumen final para el usuario
    if image_models:
        print("\n🚀 MODELOS DE IMAGEN DETECTADOS:")
        for img_m in image_models:
            print(f" ✅ {img_m}")
        print("\n💡 INSTRUCCIÓN PARA TU AGENTE:")
        print(f"Dile: 'Usa exactamente este ID de modelo: {image_models[0]}'")
    else:
        print("\n⚠️ No se detectaron modelos con la palabra 'image' o 'predict'.")
        print("Si ves modelos en la lista de arriba que crees que son de imagen,")
        print("copia el ID y pásaselo al agente manualmente.")

except Exception as e:
    print(f"❌ Error durante la conexión: {e}")
    print("\nSugerencia: Revisa si tu API Key tiene permisos de 'Pago' (Paid Service)")
    print("o si el proyecto en Google AI Studio tiene habilitado Imagen 3.")