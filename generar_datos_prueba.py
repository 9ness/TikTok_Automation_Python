
import os
import requests
from PIL import Image
from moviepy.editor import AudioClip
import numpy as np
from src.utils import load_config

def generate_test_data():
    print("Iniciando generacion de datos de prueba...")

    # 1. Leer configuración
    try:
        config = load_config()
        print("Configuracion cargada correctamente.")
    except Exception as e:
        print(f"Error al cargar configuracion: {e}")
        return

    library_base = config["paths"]["library_base"]
    test_folder = os.path.join(library_base, "_TEST_PRESIDENT")

    # Crear carpeta si no existe
    if not os.path.exists(test_folder):
        os.makedirs(test_folder)
        print(f"Carpeta creada: {test_folder}")
    else:
        print(f"La carpeta ya existe: {test_folder}")

    # 2. Descargar 4 imágenes aleatorias
    print("Descargando imagenes de prueba...")
    for i in range(1, 5):
        filename = f"foto{i}.jpg"
        filepath = os.path.join(test_folder, filename)
        if not os.path.exists(filepath):
            try:
                response = requests.get('https://picsum.photos/1080/1920', timeout=10)
                if response.status_code == 200:
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    print(f"  Guardada: {filename}")
                else:
                    print(f"  Error descargando {filename}: Status {response.status_code}")
            except Exception as e:
                print(f"  Excepcion descargando {filename}: {e}")
        else:
            print(f"  {filename} ya existe.")

    # 3. Crear imagen negra (silueta)
    silhouette_path = os.path.join(test_folder, "silueta_test.jpg")
    if not os.path.exists(silhouette_path):
        try:
            img = Image.new('RGB', (1080, 1920), color='black')
            img.save(silhouette_path)
            print("Silueta creada: silueta_test.jpg")
        except Exception as e:
            print(f"Error creando silueta: {e}")
    else:
        print("silueta_test.jpg ya existe.")

    # 4. Crear archivo dummy de video
    video_path = os.path.join(test_folder, "dummy_video.mp4")
    if not os.path.exists(video_path):
        try:
            with open(video_path, 'w') as f:
                f.write("DUMMY VIDEO CONTENT")
            print("Dummy video creado: dummy_video.mp4")
        except Exception as e:
            print(f"Error creando dummy video: {e}")
    else:
         print("dummy_video.mp4 ya existe.")

    # 5. Generar audio de silencio (5 segundos)
    audio_path = "5_TEST.mp3"
    if not os.path.exists(audio_path):
        try:
            # Crear audio de silencio usando numpy y moviepy
            # 5 segundos de silencio
            duration = 5
            make_frame = lambda t: np.array([0, 0])
            clip = AudioClip(make_frame, duration=duration)
            clip.write_audiofile(audio_path, fps=44100, verbose=False, logger=None)
            print(f"Audio de silencio creado: {audio_path}")
        except Exception as e:
             print(f"Error creando audio: {e}")
    else:
        print(f"{audio_path} ya existe.")

    print("Generacion de datos de prueba finalizada.")

if __name__ == "__main__":
    generate_test_data()
