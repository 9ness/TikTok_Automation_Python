import os
import requests
import json
import glob
from dotenv import load_dotenv, find_dotenv
from datetime import datetime
import time

load_dotenv(find_dotenv())

def generate_audios_from_text_folder(txt_folder_path, output_base_path, voice_id_override=None):
    print(f"🎙️ Iniciando locución PREMIUM (HD T2A V2) para: {os.path.abspath(txt_folder_path)}")

    # 1. Configuración
    API_KEY = os.getenv("MINIMAX_API_KEY")
    VOICE_ID = voice_id_override or os.getenv("MINIMAX_VOICE_ID")
    GROUP_ID = os.getenv("MINIMAX_GROUP_ID")
    if voice_id_override:
        print(f"🗣️ Override de voz activado: {VOICE_ID}")
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
    
    print(f"⏳ Procesando {len(txt_files)} archivos con speech-2.5-turbo-preview...")

    for txt_file in txt_files:
        filename = os.path.basename(txt_file)
        name_no_ext = os.path.splitext(filename)[0]
        
        with open(txt_file, 'r', encoding='utf-8') as f:
            text_content = f.read().strip()
            
        if not text_content: continue
        
        # PAYLOAD ESPECIAL V2
        payload = {
            "model": "speech-2.5-turbo-preview",
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
            
        # RETRY LOGIC for Timeout Handling (Failed MiniMax: 1001)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(URL, headers=headers, json=payload, timeout=120) # Added timeout=120s
                response_data = response.json()
                
                # Check for explicit API error
                base_resp = response_data.get("base_resp", {})
                if base_resp.get("status_code") == 1001: # Timeout specifically
                    print(f"⚠️ MiniMax Timeout (1001). Reintentando {attempt+1}/{max_retries} en {2**(attempt+1)}s...")
                    time.sleep(2**(attempt+1))
                    continue # Retry loop
                
                # MANEJO DE RESPUESTA V2 (Viene en HEX dentro del JSON, no binary stream directo)
                if base_resp.get("status_code") == 0:
                    if "data" in response_data and "audio" in response_data["data"]:
                        hex_audio = response_data["data"]["audio"]
                        audio_bytes = bytes.fromhex(hex_audio)

                        mp3_path = os.path.join(full_output_path, f"{name_no_ext}.mp3")
                        with open(mp3_path, "wb") as f_out:
                            f_out.write(audio_bytes)
                        print(f"   ✅ Generado: {filename}")
                        # Cost tracking — no rompe el flow si Redis no está
                        try:
                            from src import cost_tracking
                            cost_tracking.record_minimax_tts(
                                chars=len(text_content), voice=VOICE_ID,
                            )
                        except Exception:
                            pass
                        break # Success, break retry loop!
                    else:
                        print(f"⚠️ JSON incompleto: {response_data}")
                        raise Exception("JSON Incompleto")
                else:
                    print(f"❌ Error API: {response_data}")
                    raise Exception(f"Fallo MiniMax: {response_data.get('base_resp')}")

            except Exception as e:
                print(f"❌ Excepción (Intento {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2**(attempt+1))
                else:
                    raise e # Fail finally if retries exhausted
            
    print(f"✅ Locución finalizada en: {full_output_path}")
    return full_output_path


def generate_single_audio(text, output_mp3_path, voice_id_override=None):
    """Sintetiza un texto largo a un único MP3 (sin trocear).

    Útil cuando ya tienes el guion completo en una sola pieza (por ejemplo, el
    guion de vídeo del nicho Pronósticos viene de Redis con todas las
    transiciones y CTA insertados).
    """
    print(f"🎙️ TTS single (T2A V2) → {os.path.abspath(output_mp3_path)}")

    API_KEY = os.getenv("MINIMAX_API_KEY")
    VOICE_ID = voice_id_override or os.getenv("MINIMAX_VOICE_ID")
    GROUP_ID = os.getenv("MINIMAX_GROUP_ID")
    URL = "https://api.minimax.io/v1/t2a_v2"

    if not API_KEY or not VOICE_ID:
        raise ValueError("❌ Faltan claves en .env (MINIMAX_API_KEY / MINIMAX_VOICE_ID).")

    if voice_id_override:
        print(f"🗣️ Override de voz activado: {VOICE_ID}")

    payload = {
        "model": "speech-2.5-turbo-preview",
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": VOICE_ID,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }
    if GROUP_ID:
        payload["group_id"] = GROUP_ID

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    os.makedirs(os.path.dirname(os.path.abspath(output_mp3_path)) or ".", exist_ok=True)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(URL, headers=headers, json=payload, timeout=180)
            response_data = response.json()
            base_resp = response_data.get("base_resp", {})
            if base_resp.get("status_code") == 1001:
                print(f"⚠️ MiniMax Timeout (1001). Reintentando {attempt+1}/{max_retries}...")
                time.sleep(2 ** (attempt + 1))
                continue
            if base_resp.get("status_code") == 0:
                if "data" in response_data and "audio" in response_data["data"]:
                    audio_bytes = bytes.fromhex(response_data["data"]["audio"])
                    with open(output_mp3_path, "wb") as f_out:
                        f_out.write(audio_bytes)
                    print(f"✅ TTS OK ({len(audio_bytes)} bytes)")
                    try:
                        from src import cost_tracking
                        cost_tracking.record_minimax_tts(chars=len(text), voice=VOICE_ID)
                    except Exception:
                        pass
                    return output_mp3_path
                raise Exception(f"JSON incompleto: {response_data}")
            raise Exception(f"Fallo MiniMax: {base_resp}")
        except Exception as e:
            print(f"❌ Excepción intento {attempt+1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                raise

    raise RuntimeError("MiniMax TTS agotó reintentos.")


def generate_voice_sample(
    voice_id: str,
    output_path: str,
    sample_text: str | None = None,
) -> str:
    """Genera (o devuelve cacheada) una muestra ~3-5s de la voz indicada.

    Si `output_path` ya existe, NO llama a la API y devuelve la ruta directamente
    (cache hit). Si no, llama a MiniMax con un texto corto fijo y la guarda.

    Útil para audicionar voces en la UI sin consumir créditos en cada click.
    """
    if os.path.exists(output_path):
        return output_path

    text = sample_text or "4500 es lo que nos vamos a llevar con las ligas europeas."

    API_KEY = os.getenv("MINIMAX_API_KEY")
    GROUP_ID = os.getenv("MINIMAX_GROUP_ID")
    if not API_KEY:
        raise ValueError("❌ Falta MINIMAX_API_KEY en .env")
    if not voice_id:
        raise ValueError("❌ voice_id vacío")

    URL = "https://api.minimax.io/v1/t2a_v2"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "speech-2.5-turbo-preview",
        "text": text,
        "stream": False,
        "voice_setting": {"voice_id": voice_id, "speed": 1.0, "vol": 1.0, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
    }
    if GROUP_ID:
        payload["group_id"] = GROUP_ID

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

    response = requests.post(URL, headers=headers, json=payload, timeout=60)
    data = response.json()
    base = data.get("base_resp", {})
    if base.get("status_code") != 0:
        raise RuntimeError(f"MiniMax sample error: {base.get('status_msg', 'unknown')} ({base})")
    if "data" not in data or "audio" not in data["data"]:
        raise RuntimeError(f"MiniMax respuesta sin audio: {data}")

    audio_bytes = bytes.fromhex(data["data"]["audio"])
    with open(output_path, "wb") as f:
        f.write(audio_bytes)
    return output_path
