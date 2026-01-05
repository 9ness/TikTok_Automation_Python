import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

def list_models():
    api_key = os.getenv("GOOGLE_GEMINI_KEY")
    if not api_key:
        print("❌ GOOGLE_GEMINI_KEY not found.")
        return

    genai.configure(api_key=api_key)

    print("🔍 Listing available models...")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                pass # Text models
            if 'image' in m.name or 'imagen' in m.name:
                print(f"🎨 Found Image Model: {m.name}")
                print(f"   Display Name: {m.display_name}")
                print(f"   Methods: {m.supported_generation_methods}")
                print("-" * 20)
            else:
                 # Print all just in case
                 pass
                 
        print("\nFull List for reference:")
        for m in genai.list_models():
            print(f"- {m.name}")
            
    except Exception as e:
        print(f"❌ Error listing models: {e}")

if __name__ == "__main__":
    list_models()
