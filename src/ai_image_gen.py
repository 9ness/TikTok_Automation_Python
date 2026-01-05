import os
import requests
import json
import time
from dotenv import load_dotenv
import google.generativeai as genai
from PIL import Image
from io import BytesIO

load_dotenv()

def init_genai():
    api_key = os.getenv("GOOGLE_GEMINI_KEY")
    if not api_key:
        raise ValueError("❌ Faltan las API KEYS. Configura GOOGLE_GEMINI_KEY en .env")
    genai.configure(api_key=api_key)

def generate_images_from_list(scenes_data, output_folder, quality_mode="best"):
    """
    Recibe una lista de escenas (diccionarios con 'image_prompt_en' y 'order'),
    Genera imágenes con Google Imagen 3 (model='imagen-3.0-generate-001'),
    Las guarda en output_folder como scene_001.png, etc.
    quality_mode: "best" (1080p) -> 'imagen-3.0-generate-001'
                  "fast" (720p/480p) -> 'imagen-3.0-fast-generate-001'
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder, exist_ok=True)
        
    init_genai()
    
    # Modelo Imagen 3 (Oficialmente 'imagen-3.0-generate-001' o similar en REST)
    # En la lib python google-generativeai, a veces es 'models/imagen-3.0-generate-001'
    # Intentaremos usar el cliente de modelos de imagen si está disponible o fallback.
    
    # DEFINICIÓN DE MODELOS (SEGÚN RESOLUCIÓN)
    # DEFINICIÓN DE MODELOS PREFERIDOS (4.0)
    MODEL_FAST_V4 = "models/imagen-4.0-fast-generate-001"
    MODEL_ULTRA_V4 = "models/imagen-4.0-ultra-generate-001"
    
    # DEFINICIÓN DE MODELOS FALLBACK (Economical/Fast form 240p)
    # User requested to use the exact model ID used for 'FAST' mode.
    MODEL_FALLBACK_V3 = "models/imagen-4.0-fast-generate-001"

    if quality_mode == "fast":
        primary_model = MODEL_FAST_V4
        print(f"🍌 MODO 'NANO BANANA': Intentando {primary_model} (Fast 4.0)")
    elif quality_mode == "legacy":
        primary_model = MODEL_FALLBACK_V3
        print(f"📼 MODO 'LEGACY' (Imagen 2/3): Usando {primary_model}")
    else:
        primary_model = MODEL_ULTRA_V4
        print(f"🌟 MODO ULTRA PRODUCCIÓN: Intentando {primary_model} (High Definition 4.0)")

    print(f"🎨 Iniciando Generación de Imágenes ({len(scenes_data)} escenas)...")
    
    generated_paths = []

    # Helper interno para abstracción de llamada (SDK v Rest)
    def call_imagen_api(prompt, model_id, filepath):
        """Intenta generar imagen con SDK, fallback a REST. Retorna True/False."""
        api_key = os.getenv("GOOGLE_GEMINI_KEY")
        
        # 1. INTENTO CON SDK PYTHON
        try:
            from google.generativeai import ImageGenerationModel
            model = ImageGenerationModel.from_pretrained(model_id)
            images = model.generate_images(
                prompt=prompt,
                number_of_images=1,
                aspect_ratio="9:16",
                safety_filter_level="block_only_high",
                person_generation="allow_adult"
            )
            if images:
                images[0].save(location=filepath)
                return True
        except ImportError:
            pass # Vamos a REST
        except Exception as e:
            # Si hay error (Quota, etc), lanzamos excepción para que el bucle principal haga fallback
            # print(f"SDK Error: {e}") 
            raise e 

        # 2. FALLBACK A REST API
        try:
            if model_id.startswith("models/"):
                url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:predict"
            else:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:predict"
            
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
            data = {
                "instances": [{"prompt": prompt}],
                "parameters": {
                    "sampleCount": 1, 
                    "aspectRatio": "9:16", 
                    "personGeneration": "allow_adult"
                }
            }
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                import base64
                result = response.json()
                if "predictions" in result:
                    b64_data = result["predictions"][0]["bytesBase64Encoded"]
                    img_bytes = base64.b64decode(b64_data)
                    img = Image.open(BytesIO(img_bytes))
                    img.save(filepath)
                    return True
            else:
                raise RuntimeError(f"REST API Error {response.status_code}: {response.text}")
                
        except Exception as e:
            raise e
            
        return False


    for scene in scenes_data:
        order = scene.get("order", 0)
        prompt = scene.get("image_prompt_en", "")
        
        if not prompt: 
            print(f"⚠️ Salto escena {order}: Sin prompt.")
            continue
            
        filename = f"scene_{int(order):03d}.png"
        filepath = os.path.join(output_folder, filename)
        
        print(f"   generating scene {order} [{primary_model}]...")

        # INTENTO 1: Modelo Primario (v4.0)
        try:
            success = call_imagen_api(prompt, primary_model, filepath)
            if success:
                generated_paths.append(filepath)
                print(f"   ✅ Saved (v4): {filename}")
                time.sleep(1) 
                continue 
        except Exception as e:
            print(f"   ⚠️ Fallo Modelo 4.0 en escena {order}. Motivo: {e}")
            print(f"   🔄 ACTIVANDO FALLBACK A IMAGEN 3.0...")

            # INTENTO 2: Fallback (v3.0)
            try:
                success = call_imagen_api(prompt, MODEL_FALLBACK_V3, filepath)
                if success:
                    generated_paths.append(filepath)
                    print(f"   ✅ Saved (Fallback v3): {filename}")
                    time.sleep(1)
                    continue
            except Exception as e2:
                print(f"   ❌ Error Fallback v3 en escena {order}: {e2}")
        
        # SI LLEGAMOS AQUI, FALLÓ TODO
        print(f"❌ Error CRÍTICO generando escena {order}")

    return generated_paths
