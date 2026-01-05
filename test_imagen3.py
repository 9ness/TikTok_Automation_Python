import os
import shutil
from src.ai_image_gen import generate_images_from_list
from dotenv import load_dotenv

load_dotenv()

def test_imagen_module():
    print("🚀 Testing src.ai_image_gen module...")
    
    # Dummy data
    scenes = [
        {
            "order": 999,
            "image_prompt_en": "A cute robot holding a sign that says 'IT WORKS', 3d render, high quality"
        }
    ]
    
    output_folder = "test_output_images"
    
    # Clean prev
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)
        
    try:
        paths = generate_images_from_list(scenes, output_folder, quality_mode="fast")
        
        if paths:
            print(f"✅ SUCCESS! Generated {len(paths)} images.")
            print(f"Path: {paths[0]}")
        else:
            print("❌ FAILED. No images generated.")
            
    except Exception as e:
        print(f"❌ Runtime Error: {e}")

if __name__ == "__main__":
    test_imagen_module()
