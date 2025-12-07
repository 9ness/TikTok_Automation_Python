# 🎬 TikTok Automation Factory

Herramienta automatizada para crear videos de "Tops" para TikTok usando Python (Streamlit + MoviePy).

## 🚀 Funcionalidades
- Generación masiva de videos verticales (9:16).
- Sincronización automática de audio y fotos.
- Inyección inteligente de videos y efectos "Ken Burns".
- Interfaz visual con Streamlit.

## 🛠️ Instalación
1. Clona el repositorio.
2. Crea un entorno virtual: `python -m venv venv`
3. Instala dependencias: `pip install -r requirements.txt`
4. Configura tus rutas en `config/config.json`.

## ▶️ Ejecución
Ejecuta la interfaz web:
streamlit run main.py

## 📂 Estructura de Carpetas (Drive)
![Infografía de Estructura](docs/estructura_drive.png)

### 1. Biblioteca de Presidentes (`library_base`)
Dentro de esta carpeta, crea una subcarpeta por cada presidente (el nombre debe coincidir con el del audio).

**Ejemplo dentro de la carpeta `/Trump`:**
Puedes tener tantos archivos como quieras. El script los clasificará automáticamente.

* **Fotos:** Nombres libres (ej: `trump_1.jpg`, `trump_2.png`, `trump_foto_oficial.jpeg`).
* **Silueta (Top 1):** Debe contener la palabra definida en el config (por defecto "silueta"). (ej: `trump_silueta.jpg`). Solo se usará una.
* **Videos (Inyección):** Pueden ser varios. El script elegirá uno al azar. (ej: `trump_video_1.mp4`, `trump_video_2.mov`).

---

## 🎤 Nomenclatura de Audios (Input)

Al arrastrar los audios a la interfaz web, el nombre le dice al script el puesto y la carpeta a usar:

* **`5_trump.mp3`** → Puesto 5, busca los archivos en la carpeta "trump".
* **`4_biden.mp3`** → Puesto 4, busca los archivos en la carpeta "biden".
* **`1_obama.mp3`** → Puesto 1, busca carpeta "obama" y usa la silueta.
* **`intro.mp3`** → Genera la introducción usando la biblioteca de intros.
