
import os
import json
import time
import random
import hashlib
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, ColorClip
import easyocr
import openai
from dotenv import load_dotenv

load_dotenv()

class VideoRemover:
    def __init__(self, config):
        self.config = config
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY no encontrada en el entorno.")
        self.client = openai.OpenAI(api_key=self.api_key)
        self.reader = None
        # Path Windows; resolve_font() lo traduce a la ruta válida en Linux
        # cada vez que se llama a ImageFont.truetype con esta cadena.
        from src.font_resolver import resolve_font
        self.font_path = resolve_font("C:\\Windows\\Fonts\\impact.ttf")
        if not os.path.exists(self.font_path):
            self.font_path = resolve_font("C:\\Windows\\Fonts\\arialbd.ttf")
            
        self.trajectory = []
        self.cached_hook = None # Caché para previsualización
        self.temp_folder = config.get("paths", {}).get("temp_folder", "temp")
        os.makedirs(self.temp_folder, exist_ok=True)

    def get_hook_text(self, words):
        """Genera y cachea el gancho viral en inglés usando IA."""
        if self.cached_hook: return self.cached_hook
        
        intro_text = " ".join([w['word'] for w in words if w['start'] < 6.0])
        if len(intro_text.strip()) < 5: return "MIRA ESTO"
        
        try:
            res_en = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": f"Summarize this into a VIRAL HOOK phrase in ENGLISH (max 5 words, clear, uppercase): '{intro_text}'"}]
            )
            try:
                from src import cost_tracking
                usage = getattr(res_en, "usage", None)
                if usage:
                    cost_tracking.record_openai_chat(
                        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                        model="gpt-4o-mini",
                        detail="hook copyright",
                    )
            except Exception:
                pass
            self.cached_hook = res_en.choices[0].message.content.strip().replace('"', '').upper()
            return self.cached_hook
        except:
            return "MIRA ESTO"

    def _get_reader(self):
        if self.reader is None:
            self.reader = easyocr.Reader(['es', 'en'], gpu=True) 
        return self.reader

    def get_video_hash(self, video_path):
        file_stats = os.stat(video_path)
        hasher = hashlib.md5()
        hasher.update(video_path.encode())
        hasher.update(str(file_stats.st_size).encode())
        return hasher.hexdigest()

    def map_text_trajectory(self, video_path, fps_sample=6, log_callback=None):
        """Mapeo CEÑIDO de subtítulos para evitar cuadros gigantes."""
        reader = self._get_reader()
        cap = cv2.VideoCapture(video_path)
        fps_vid = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_step = int(fps_vid / fps_sample)
        if frame_step < 1: frame_step = 1
        
        trajectory = []
        processed_count = 0
        total_samples = len(range(0, total_frames, frame_step))
        
        for frame_idx in range(0, total_frames, frame_step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret: break
            processed_count += 1
            if log_callback and processed_count % 10 == 0:
                log_callback(f"🖼️ Escaneando: {processed_count}/{total_samples} fragmentos...")
            
            timestamp = frame_idx / fps_vid
            h_orig, w_orig = frame.shape[:2]
            scale = 720 / w_orig if w_orig > 720 else 1.0
            small_frame = cv2.resize(frame, (0,0), fx=scale, fy=scale)
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            results = reader.readtext(rgb_frame)
            if results is None: results = []
            
            frame_boxes = []
            for (bbox, text, prob) in results:
                if prob > 0.2 and len(text.strip()) > 1:
                    xs = [p[0] / scale for p in bbox]
                    ys = [p[1] / scale for p in bbox]
                    frame_boxes.append([min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)])
            
            if frame_boxes:
                # Unión ceñida
                x_min = min([b[0] for b in frame_boxes])
                y_min = min([b[1] for b in frame_boxes])
                x_max = max([b[0] + b[2] for b in frame_boxes])
                y_max = max([b[1] + b[3] for b in frame_boxes])
                
                # LÓGICA DE SOMBRA ORGÁNICA (Se funde como sombra del texto)
                h_detected = (y_max - y_min)
                w_detected = (x_max - x_min)
                
                if h_detected < 55: # MODO DISCRETO (1 línea)
                    margin_y_up = 15
                    margin_y_down = 15
                    margin_x = 40
                else: # MODO PROTECCIÓN (2+ líneas)
                    margin_y_up = 40
                    margin_y_down = 30
                    margin_x = 60
                    
                # Ancho dinámico elegante
                box_w = min(w_orig * 0.9, w_detected + (margin_x * 2))
                box_x = max(0, (w_orig - box_w) // 2)
                
                # CONVERSIÓN EXPLÍCITA A TIPOS NATIVOS (Evita errores de serialización)
                box = [
                    float(box_x),
                    float(max(0, y_min - margin_y_up)),
                    float(box_w),
                    float(min(h_orig - y_min, h_detected + margin_y_up + margin_y_down))
                ]
                trajectory.append((float(timestamp), box))
        
        cap.release()
        self.trajectory = trajectory
        return trajectory

    def transcribe_video(self, video_path, log_callback=None):
        v_hash = self.get_video_hash(video_path)
        cache_path = os.path.join(self.temp_folder, f"transcription_{v_hash}.json")
        if os.path.exists(cache_path):
            if log_callback: log_callback("♻️ Usando transcripción guardada (Gratis).")
            with open(cache_path, 'r', encoding='utf-8') as f: return json.load(f)
        
        if log_callback: log_callback("🎙️ Generando nueva transcripción...")
        temp_audio = os.path.join(self.temp_folder, f"audio_{v_hash}.mp3")
        try:
            video = VideoFileClip(video_path)
            video.audio.write_audiofile(temp_audio, logger=None)
            video.close()
            
            with open(temp_audio, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-1",
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )

            # Cost tracking — Whisper se factura por segundo de audio
            try:
                from src import cost_tracking
                duration = float(getattr(response, "duration", 0) or 0)
                if duration > 0:
                    cost_tracking.record_openai_whisper(
                        audio_seconds=duration, detail="whisper-1 transcribe",
                    )
            except Exception:
                pass

            if not response or not hasattr(response, 'words') or response.words is None:
                raise ValueError("La API de Whisper devolvió una respuesta vacía o sin palabras.")
                
            words_data = []
            for w in response.words:
                words_data.append({
                    'word': getattr(w, 'word', ''), 
                    'start': getattr(w, 'start', 0), 
                    'end': getattr(w, 'end', 0)
                })
            
            with open(cache_path, 'w', encoding='utf-8') as f: 
                json.dump(words_data, f, indent=2)
            return words_data
            
        except Exception as e:
            if log_callback: log_callback(f"⚠️ Error en transcripción: {e}")
            return [] # Devolver lista vacía para evitar fallos de iteración descendente

    def _apply_pro_blur(self, frame, box):
        """Difuminado suave, sin oscurecer bruscamente."""
        if box is None: return frame
        
        h_f, w_f = frame.shape[:2]
        x, y, w, h = [int(v) for v in box]
        y_end, x_end = min(h_f, y+h), min(w_f, x+w)
        roi = frame[y:y_end, x:x_end].copy()
        if roi.size == 0: return frame
        
        # Blur Cinematográfico suave
        roi = cv2.GaussianBlur(roi, (51, 51), 0)
        
        # Degradado Elíptico Ultra-suave
        mask = np.ones((roi.shape[0], roi.shape[1]), dtype=np.float32)
        f_h = int(roi.shape[0]*0.25)
        f_w = int(roi.shape[1]*0.2)
        if f_h > 0:
            mask[:f_h, :] *= np.linspace(0, 1, f_h)[:, None]
            mask[-f_h:, :] *= np.linspace(1, 0, f_h)[:, None]
        if f_w > 0:
            mask[:, :f_w] *= np.linspace(0, 1, f_w)
            mask[:, -f_w:] *= np.linspace(1, 0, f_w)
            
        mask = cv2.GaussianBlur(mask, (81, 81), 0)
        
        # Oscurecimiento super ligero para legibilidad (ya no es un rectángulo negro del 99%)
        roi = (roi * 0.7).astype(np.uint8)
            
        frame_roi = frame[y:y_end, x:x_end]
        for c in range(3):
            frame[y:y_end, x:x_end, c] = (roi[:,:,c]*mask + frame_roi[:,:,c]*(1-mask)).astype(np.uint8)
        return frame

    def create_text_clip(self, text, duration, size, color="yellow", with_box=False):
        w, h = size
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        fontsize_base = int(h * 0.45) # Tamaño base
        if fontsize_base < 35: fontsize_base = 40
        
        # DETERMINACIÓN DE LÍNEAS (Priorizando puntuación para un split natural)
        current_text = text
        is_vs = " VS " in text.upper()
        
        # Intento 1: Ajustar en una sola línea
        fs_single = fontsize_base
        while fs_single > 15:
            try: font_test = ImageFont.truetype(self.font_path, fs_single)
            except: font_test = ImageFont.load_default()
            tw = draw.textbbox((0, 0), text, font=font_test)[2]
            if tw < w * 0.90: break
            fs_single -= 2
        
        # Si no cabe bien en una línea o queremos forzar el split por puntuación
        has_sep = any(s in text for s in [":", "!", "?", " - "])
        
        if (fs_single < 30 or has_sep) and len(text.split()) > 3:
            # Intentamos split inteligente por puntuación
            if ":" in text:
                parts = text.split(":", 1)
                current_text = parts[0].strip() + ":\n" + parts[1].strip()
            elif " - " in text:
                parts = text.split(" - ", 1)
                current_text = parts[0].strip() + "\n" + parts[1].strip()
            elif "!" in text and not text.endswith("!"):
                parts = text.split("!", 1)
                current_text = parts[0].strip() + "!\n" + parts[1].strip()
            else:
                # Split por la mitad (Legacy)
                words_list = text.split()
                mid = len(words_list) // 2
                current_text = "\n".join([" ".join(words_list[:mid]), " ".join(words_list[mid:])])
            
            # Re-calculamos fontsize para multilínea
            fontsize = fontsize_base
            while fontsize > 15:
                try: font = ImageFont.truetype(self.font_path, fontsize)
                except: font = ImageFont.load_default()
                # Añadimos spacing para evitar que los trazos se solapen
                mw = draw.multiline_textbbox((0, 0), current_text, font=font, align="center", spacing=25)[2]
                if mw < w * 0.9: break
                fontsize -= 2
        else:
            fontsize = fs_single
            font = ImageFont.truetype(self.font_path, fontsize)

        x, y = w // 2, h // 2
        
        if with_box:
            # Estilo GANCHO (Legacy) - Añadido spacing
            bbox = draw.multiline_textbbox((x, y), current_text, font=font, anchor="mm", align="center", spacing=25)
            pad_x, pad_y = 25, 15
            box_rect = [bbox[0]-pad_x, bbox[1]-pad_y, bbox[2]+pad_x, bbox[3]+pad_y]
            draw.rounded_rectangle(box_rect, radius=15, fill=(0, 0, 0, 180))
            draw.multiline_text((x, y), current_text, font=font, fill="white", anchor="mm", align="center", spacing=25)
        else:
            # CORRECCIÓN DEFINITIVA: Dibujado línea a línea para bordes perfectos
            lines = current_text.split('\n')
            
            # Calcular alturas para centrado vertical manual
            line_heights = []
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_heights.append(bbox[3] - bbox[1])
            
            total_text_height = sum(line_heights) + (len(lines) - 1) * 10 # Spacing base
            start_y = (h - total_text_height) // 2
            
            current_y = start_y
            for i, line in enumerate(lines):
                # Dibujamos cada línea de forma independiente (Stroke + Fill en un solo paso por línea)
                # Esto garantiza que el borde negro rodee toda la línea sin solapamientos
                draw.text((w // 2, current_y + line_heights[i]//2), line, font=font, 
                          fill=color, stroke_width=5, stroke_fill="black", anchor="mm")
                current_y += line_heights[i] + 10 # Incremento para la siguiente línea
        
        return ImageClip(np.array(img)).set_duration(duration)

    def get_preview_frames(self, video_path, words, trajectory, clean_mode="Subtítulos Virales", hook_y_pct=0.20, hook_color="#FDD002"):
        video = VideoFileClip(video_path)
        W, H = video.size
        is_camuflaje = "Camuflaje" in clean_mode
        zoom = 1.15 if is_camuflaje else 1.10
        times = [1.0, video.duration/2, video.duration-2.0]
        previews = []
        
        # Obtener gancho si es camuflaje para la preview
        hook_txt = self.get_hook_text(words) if is_camuflaje else None
        
        for t in times:
            frame = video.get_frame(t).copy()
            curr_box = None
            if trajectory:
                best = 999
                for ts, b in trajectory:
                    if abs(ts-t) < best and abs(ts-t) < 1.0:
                        best, curr_box = abs(ts-t), b
            
            # Aplicar Blur solo en modo estándar
            if curr_box and not is_camuflaje: 
                frame = self._apply_pro_blur(frame, curr_box)
            
            # Zoom/Crop (Simulando el render final)
            pil_frame = Image.fromarray(frame).resize((int(W*zoom), int(H*zoom)), Image.LANCZOS)
            frame = np.array(pil_frame.crop(((int(W*zoom)-W)//2, (int(H*zoom)-H)//2, (int(W*zoom)-W)//2 + W, (int(H*zoom)-H)//2 + H)))
            
            # Renderizado de Texto en Preview
            if is_camuflaje and t == 1.0 and hook_txt:
                # Previsualización del GANCHO IA en el primer frame
                pil = Image.fromarray(frame)
                draw = ImageDraw.Draw(pil)
                
                # Sincronización de Lógica de Split Inteligente
                f_size_base = int(H * 0.10 * 0.45)
                hook_w_limit = W * 0.8
                
                # Probar unilínea primero
                f_single = f_size_base
                while f_single > 15:
                    font_test = ImageFont.truetype(self.font_path, f_single)
                    if draw.textbbox((0,0), hook_txt, font=font_test)[2] < hook_w_limit * 0.9: break
                    f_single -= 2
                
                current_hook = hook_txt
                has_sep = any(s in hook_txt for s in [":", "!", "?", " - "])
                
                if (f_single < 30 or has_sep) and len(hook_txt.split()) > 3:
                    if ":" in hook_txt:
                        p = hook_txt.split(":", 1)
                        current_hook = p[0].strip() + ":\n" + p[1].strip()
                    elif " - " in hook_txt:
                        p = hook_txt.split(" - ", 1)
                        current_hook = p[0].strip() + "\n" + p[1].strip()
                    elif "!" in hook_txt and not hook_txt.endswith("!"):
                        p = hook_txt.split("!", 1)
                        current_hook = p[0].strip() + "!\n" + p[1].strip()
                    else:
                        words_list = hook_txt.split()
                        mid = len(words_list) // 2
                        current_hook = "\n".join([" ".join(words_list[:mid]), " ".join(words_list[mid:])])
                    
                    f_final = f_size_base
                    while f_final > 15:
                        font_final = ImageFont.truetype(self.font_path, f_final)
                        if draw.multiline_textbbox((0,0), current_hook, font=font_final, align="center", spacing=25)[2] < hook_w_limit * 0.9: break
                        f_final -= 2
                else:
                    font_final = ImageFont.truetype(self.font_path, f_single)

                x_txt = W // 2
                lines_hook = current_hook.split("\n")
                
                # Calcular alturas para centrado manual
                line_hs = []
                for lh in lines_hook:
                    bb = draw.textbbox((0, 0), lh, font=font_final)
                    line_hs.append(bb[3] - bb[1])
                
                total_h = sum(line_hs) + (len(lines_hook) - 1) * 10
                curr_y = int(H * hook_y_pct) - (total_h // 2)
                
                for i, l_text in enumerate(lines_hook):
                    # Dibujado independiente por línea para asegurar bordes 360º
                    draw.text((x_txt, curr_y + line_hs[i]//2), l_text, font=font_final, 
                              fill=hook_color, stroke_width=5, stroke_fill="black", anchor="mm")
                    curr_y += line_hs[i] + 10
                    
                frame = np.array(pil)
            elif not is_camuflaje:
                # Previsualización de subtítulos estándar
                txt_now = ""
                for i in range(0, len(words), 2):
                    if words[i]['start'] <= t <= (words[i+1]['end'] if i+1 < len(words) else words[i]['end']+0.5):
                        txt_now = (words[i]['word'] + " " + (words[i+1]['word'] if i+1 < len(words) else "")).upper().strip()
                        break
                if txt_now:
                    pil = Image.fromarray(frame)
                    font = ImageFont.truetype(self.font_path, int(H*0.075))
                    x_txt = W // 2
                    if curr_box:
                        center_y_box = (curr_box[1] + curr_box[3]/2)
                        center_y = center_y_box * zoom - (H * (zoom - 1)) / 2
                        y_txt = int(center_y - (H * 0.015))
                    else:
                        y_txt = int(H * 0.8)
                    
                    pil_rgba = pil.convert("RGBA")
                    shadow_img = Image.new("RGBA", pil.size, (0, 0, 0, 0))
                    shadow_draw = ImageDraw.Draw(shadow_img)
                    shadow_draw.text((x_txt, y_txt), txt_now, font=font, fill="black", stroke_width=8, stroke_fill="black", anchor="mm")
                    shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(10))
                    pil_rgba.alpha_composite(shadow_img)
                    draw = ImageDraw.Draw(pil_rgba)
                    draw.text((x_txt, y_txt), txt_now, font=font, fill="yellow", stroke_width=3, stroke_fill="black", anchor="mm")
                    frame = np.array(pil_rgba.convert("RGB"))
            
            previews.append(frame)
        video.close()
        return previews

    def process(self, input_path, output_folder, words=None, trajectory=None, log_callback=None, logger=None, clean_mode="Subtítulos Virales", hook_y_pct=0.20, hook_color="#FDD002", upscale_1080p=False, font_path=None):
        # 4 modos:
        #  - "Subtítulos Virales"      → blur subs originales + zoom 1.10 + subs nuevos
        #  - "Camuflaje Geométrico…"   → sin blur + zoom 1.15/pulsos/firma + gancho IA
        #  - "Solo Limpiar…"           → blur subs originales + zoom 1.10, SIN texto
        #  - "Limpiar Metadata…"       → sin blur (no toca subs) + zoom 1.15/pulsos/firma, SIN texto
        is_camuflaje = "Camuflaje" in clean_mode
        add_subs = (clean_mode == "Subtítulos Virales")
        clean_keep_subs = (clean_mode == "Limpiar Metadata (Sin Tocar Subtítulos)")
        clean_mask_subs = (clean_mode == "Solo Limpiar (Sin Subtítulos)")
        # Pipeline "geométrico" (zoom 1.15 + pulsos + micro-firma, sin blur):
        # camuflaje y "limpiar metadata". El gancho IA solo en camuflaje.
        use_geometric = is_camuflaje or clean_keep_subs
        add_hook = is_camuflaje
        clean_only = clean_keep_subs or clean_mask_subs  # ningún texto añadido

        # Requisitos por modo: los subs nuevos necesitan palabras + trayectoria;
        # el gancho de camuflaje necesita palabras; los modos "limpiar" no
        # necesitan nada (trayectoria opcional solo para tapar subs originales).
        if add_subs and (not words or not trajectory):
            raise ValueError("No se puede renderizar: faltan palabras o trayectoria para los subtítulos.")
        if is_camuflaje and not words:
            raise ValueError("No se puede renderizar: faltan palabras para el gancho.")
        words = words or []
        trajectory = trajectory or []

        video_original = VideoFileClip(input_path)
        W, H = video_original.size

        # Override de la fuente del runner: el path llega desde el registry
        # universal (`/api/v1/fonts`). Si no llega nada, se respeta el default
        # resuelto en __init__ (Impact / Arial Bold como fallback).
        if font_path:
            try:
                from src.font_resolver import resolve_font
                resolved = resolve_font(font_path)
                if resolved and os.path.exists(resolved):
                    self.font_path = resolved
            except Exception as e:
                if log_callback:
                    log_callback(f"⚠️ font_path inválida ({font_path}): {e} — uso default.")

        # INICIALIZACIÓN CRÍTICA (Evita NameError)
        clips = []

        if use_geometric:
            # 1. GENERACIÓN DE GANCHO VIRAL (IA Centralizada) — solo camuflaje.
            # "Limpiar Metadata" usa el mismo tratamiento anti-copy pero SIN texto.
            hook_text = self.get_hook_text(words) if add_hook else None

            # 2. Zoom Dinámico con Pulsos Aleatorios
            pulse_times = [1.5] + [t for t in range(8, int(video_original.duration), 10)]
            
            def zoom_func(t):
                if t < 1.5: return 1.15 + 0.15 * np.sin(np.pi * t / 1.5)
                for pt in pulse_times[1:]:
                    if pt <= t <= pt + 0.6: return 1.18 + 0.08 * np.sin(np.pi * (t-pt) / 0.6)
                return 1.15 + (0.05 * (t / video_original.duration))
                
            v_trans = video_original.resize(zoom_func)
            v_trans = v_trans.crop(x_center=W*1.15/2, y_center=H*1.15/2, width=W, height=H)
            
            # 3. Micro-Firma Digital
            v_trans = v_trans.fl(lambda gf, t: np.clip(gf(t) * (1.04 if any(pt <= t <= pt + 0.6 for pt in pulse_times) else 1.01), 0, 255).astype(np.uint8))
            if v_trans.audio: v_trans.audio = v_trans.audio.volumex(0.99)
                
            # 4. Clip del Gancho IA (Traducido a INGLÉS y con tamaño de seguridad reducido)
            if hook_text:
                # Tamaño de clip optimizado (80% ancho, 10% alto)
                hook_clip = self.create_text_clip(hook_text, 4.0, (int(W * 0.8), int(H * 0.10)), color=hook_color, with_box=False)
                # Posición dinámica (Elegida por el usuario)
                hook_clip = hook_clip.set_start(0).set_position(('center', int(H * hook_y_pct)))
                clips.append(hook_clip)
        else:
            # Modo estándar (blur de subs originales + zoom). Los subtítulos
            # amarillos nuevos SOLO se añaden en "Subtítulos Virales"; en
            # "Solo Limpiar" se deja el vídeo limpio sin texto.
            zoom = 1.10
            v_blurred = video_original.fl(lambda gf, t: self._apply_pro_blur(gf(t).copy(), next((b for ts, b in trajectory if abs(ts-t) < 0.4), None)))
            v_trans = v_blurred.resize(zoom).crop(x_center=(W*zoom)/2, y_center=(H*zoom)/2, width=W, height=H)

            if add_subs:
                for i in range(0, len(words), 2):
                    w1 = words[i]
                    w2 = words[i+1] if i+1 < len(words) else None
                    txt = (w1['word'] + " " + (w2['word'] if w2 else "")).upper().strip()
                    start, end = w1['start'], (w2['end'] if w2 else w1['end'] + 0.5)
                    mid_time = (start + end) / 2
                    box = next((b for ts, b in trajectory if abs(ts-mid_time) < 0.5), None)
                    if box:
                        center_y_box = (box[1] + box[3]/2)
                        center_y = center_y_box * 1.10 - (H * (1.10 - 1)) / 2
                        final_y = int(center_y - (H*0.15 / 2) - (H * 0.015))
                    else:
                        final_y = int(H * 0.8)
                    # En subs mode reusamos hook_color como color de los subs nuevos
                    # (matches el control "Color de los subtítulos" del frontend).
                    c = self.create_text_clip(txt, end-start, (W, int(H * 0.15)), color=hook_color)
                    clips.append(c.set_start(start).set_position((0, final_y)))

        # Renderizado Final
        final = CompositeVideoClip([v_trans] + clips)
        if is_camuflaje:
            _prefix = "CAMOUFLAGE_"
        elif clean_keep_subs:
            _prefix = "CLEAN_META_"
        elif clean_mask_subs:
            _prefix = "CLEAN_"
        else:
            _prefix = "ULTRA_RENDER_"
        out = os.path.join(output_folder, f"{_prefix}{os.path.basename(input_path)}")
        
        # ELIMINACIÓN DE METADATOS (ffmpeg_params para limpiar autoría, creación, etc)
        ffmpeg_params = [
            "-map_metadata", "-1",        # Eliminar todos los metadatos globales
            "-map_chapters", "-1",        # Eliminar capítulos
            "-flags", "+bitexact",        # Forzar bitexact para no dejar rastro de encoder
            "-fflags", "+bitexact"
        ]

        # Upscale opcional a 1080p (lado mayor = 1920) con Lanczos durante el
        # encode. Solo sube si el vídeo es menor que 1080 de ancho — evita
        # downscale accidental. Lanczos en CPU añade ~5-15s para un vídeo de
        # 1 min, sin coste API. Cambia los hashes de píxel → ayuda a evadir
        # detección de copyright basada en hashing visual.
        if upscale_1080p and W < 1080:
            ffmpeg_params += ["-vf", "scale=1080:-2:flags=lanczos"]
            target_bitrate = '6500k'  # bump bitrate para no perder calidad al escalar
            if log_callback:
                log_callback(f"⬆️ Upscale a 1080p activo ({W}x{H} → 1080p Lanczos).")
        else:
            target_bitrate = '4500k'

        final.write_videofile(out, fps=video_original.fps, codec='libx264', audio_codec='aac', threads=12, preset='medium', bitrate=target_bitrate, logger=logger, ffmpeg_params=ffmpeg_params)
        video_original.close()
        return out
