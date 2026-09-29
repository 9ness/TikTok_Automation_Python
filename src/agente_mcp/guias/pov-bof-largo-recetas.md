# POV BOF Largo — recetas probadas de punta a punta (sep 2026)

> Para el agente que **continúa el trabajo desde el VPS** con el Chrome de
> pantalla virtual ([`comun/navegador-vps.md`](comun/navegador-vps.md)). Es lo
> que se hizo a mano con Claude in Chrome en el PC el 28-29/9/2026 (≈50
> productos de ness y Mauro, 3 carpetas de Tareas, 1 de Muestras). Lee antes
> [`pov-bof-largo.md`](pov-bof-largo.md) (reglas) y
> [`comun/revision-calidad.md`](comun/revision-calidad.md) (qué se rechaza).
> Aquí van los **cómos** exactos y las trampas que costaron horas.

## 0. Mapa del trabajo (el bucle)

1. `productos` de la carpeta → mira `textos`, `guion`, `subido_a_tiktok`,
   `video_montado` y `para_rehacer(menu)`. **Solo se toca lo que se pide:**
   nunca rehagas un producto marcado «Subido» (ya está publicado) ni uno que el
   operador no ha marcado. Ante una corrección de prompt, aplícala solo a lo
   pendiente.
2. `preparar_carpeta(..., modo, clip_s=8, estilo_guion)` → textos y guiones (cola,
   minutos). `preparar_bandeja(productos=[…])` deja `foto_limpia.jpg` + ficha.
3. **Mira la ficha y la foto de CADA producto** antes de escribir la escena.
4. **Imágenes** en Google Flow (2 por producto, sitios distintos) → revisar.
5. **Clips** en GenAI Pro / Magnific (Kling) desde esas imágenes → revisar.
6. `subir_clip(clip=1|2, voz="auto")` (con el último se monta solo) → esperar
   «montado» → comprobar. No marcar Subido/Escaparate; carpeta «Pendiente» solo
   si se pide.
7. Informe: qué se hizo, qué se descartó y por qué, qué falta.

## 1. Preparar las escenas (una por imagen)

- Una imagen **por clip**, cada una en un sitio distinto. Texto = «Es UN … como en
  la foto, [sitio]. Sin ningún niño ni persona aparte de UNA sola mano adulta
  (nunca dos manos ni otro brazo), que lo señala con el dedo índice desde unos
  20 cm SIN tocarlo.»
- Pantallas/luces: «pantalla NEGRA y APAGADA, sin números ni luz».
- **Productos infantiles/de bebé: la escena sin personas.** Ni niños, ni bebés,
  ni fotos de niños. Se hizo así con un organizador de pañales (cuna vacía).
- Kits de muchas piezas: pide «fotografía REAL con relieve, sombras propias,
  ángulo 45°, piezas colocadas de forma natural, NO vista cenital ni collage»;
  si no, sale un recorte plano («parece un póster pegado» — el operador lo
  rechazó).
- Si la foto de la ficha trae **dos vistas** del producto (dos mochilas, dos
  estuches), el generador las copia: pide «UN SOLO …, ningún otro».
- Nada de texto inventado: «NINGÚN texto, rótulo ni palabra que no esté en la foto».
- Quita de la foto medidas, flechas, «TOP PICKS», móviles de comparación.

## 2. Google Flow (imágenes) — cómo automatizarlo

Proyecto: `https://flow.google.com/project/68b224ad-cb74-4aae-b1f4-755a23739b91`
(Nano Banana 2, 9:16, x1, 0 puntos: repetir es gratis). La pestaña tiene que
estar **visible** (`document.visibilityState==='visible'`); oculta, Flow se
cuelga y no descarga en alta.

Ayudantes que se pegan en la página (`evalf`) — el prompt base (`window.P`) es el
«Prompt imagen» de la app (`GET /api/v1/nicho-pov-bof/prompts`):

```js
// parche: que el <input type=file> quede accesible para subir ficheros
if(!window.__patched){const o=HTMLInputElement.prototype.click;
 HTMLInputElement.prototype.click=function(){if(this.type==='file'){this.setAttribute('aria-label','flowfile');
 this.style.display='block';if(!this.isConnected)document.body.appendChild(this);return;}return o.call(this)};window.__patched=1}
window.setP=(extra)=>{const el=[...document.querySelectorAll('[contenteditable="true"]')].pop();
 el.focus();document.execCommand('selectAll');
 document.execCommand('insertText',false,window.P+(extra?'\n\n'+extra:''));return el.innerText.length};
window.openPicker=async()=>{const s=ms=>new Promise(r=>setTimeout(r,ms));
 for(let k=0;k<3;k++){if([...document.querySelectorAll('.cdk-overlay-pane input')].some(i=>(i.placeholder||'').startsWith('Buscar')))return true;
 document.querySelector('button[aria-label="Añadir ingredientes a ventana para peticiones"]').click();await s(1500)}return false};
window.attach=async(name)=>{const s=ms=>new Promise(r=>setTimeout(r,ms));
 if(!await openPicker())return 'no picker';
 const inp=[...document.querySelectorAll('.cdk-overlay-pane input')].find(i=>(i.placeholder||'').startsWith('Buscar'));
 Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(inp,name);
 inp.dispatchEvent(new Event('input',{bubbles:true}));
 let btn;for(let k=0;k<8;k++){await s(1000);btn=[...document.querySelectorAll('button.asset-item')].find(b=>b.querySelector('.asset-title')?.textContent.trim()===name);if(btn)break}
 if(!btn)return 'no item';btn.click();await s(1000);
 const b=[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='Añadir a petición');if(b){b.click();await s(800)}return 'ok'};
window.go=async(name,extra)=>{const r=await attach(name);
 return r==='ok'?[r,setP(extra)]:[r,0]};
```

Flujo por imagen:
1. **Subir la foto limpia** (una vez, con nombre único tipo `tn_t9p3.jpg`): abrir el
   picker, botón «Subir archivo», `upload` al `input[aria-label=flowfile]`.
2. `await go('tn_t9p3.jpg', '<escena>')` → **clic en la caja de texto y tecla Return**
   (Flow solo envía así; el botón de la flecha no siempre responde).
3. Esperar ~40 s. Las tiles son `flow-image-tile`; la más nueva es la primera.
4. **Descargar en grande:** la `<img>` viene a `…=s512-rw`; cambia el sufijo:
   `im.src.replace(/=s\d+-rw$/,'=s1600-rw')` y `fetch(...).blob()` + `<a download>` →
   768×1376. Si solo saca 286 px es que la pestaña estaba oculta.
5. Al recargar la página se pierden `window.*`: guarda el arranque en
   `localStorage` o vuelve a pegarlo.

Trampas:
- **«Flow está recibiendo un gran número de solicitudes… no se te ha cobrado»**:
  saturación. Espera 5-10 min y reintenta de una en una; no lances 10 seguidas.
- Lanzar 7+ seguidas con la pestaña visible funciona; oculta, solo 1-2.
- El picker a veces no encuentra el fichero recién subido: espera 4-5 s.
- Editar una imagen ya buena (alejar la mano, etc.) funciona adjuntándola y
  pidiendo «edita esta imagen manteniendo TODO idéntico, pero…». Adjunta **solo**
  esa imagen (un ingrediente sobrante la contamina: salió una tienda de campaña).

## 3. Clips — GenAI Pro (`genaipro.io/video-image-ai?ws=video&mode=frames`)

- Ajustes: **Video · Veo · Frames · solo start frame · Portrait 9:16 · 1 vídeo ·
  «Original»**. **Nunca 1080p**: sale 1920×1080 horizontal (bug reconfirmado
  29/9/2026). Recortar a **7,3 s** (`ffmpeg -t 7.3`): los últimos ~0,5 s hacen
  un fundido raro de vuelta al primer fotograma.
- Sube la imagen con `upload` al «Start frame», pon el prompt, «Generate video».
- **Prompt (¡no lo cambies!)**: el base del curso dice «The person gestures with
  the visible hand as if explaining the product… Only the hand moves». Si lo
  sustituyes por «la mano se queda señalando quieta», el dedo tiembla (pasó el
  29/9). Solo AÑADE al final, por producto: «Exactly one hand, never a second
  one», «switched off / nothing lights up», «no steam, no smoke», «the workbench
  stays EMPTY», lo que no debe moverse, y `Avoid: …`.
- Va de 3 en 3 (más → «Generation failed», se reembolsa). ~3-6 min cada uno.
  Tras «Generar» espera 8-10 s antes de subir la siguiente imagen.
- Leer resultados: los `<video>` de la lista llevan `src=files.genaipro.io/video_<uuid>.mp4`
  → se bajan con `curl` sin pulsar Download. Los más nuevos van arriba; hay
  paginación (botones 1-5) abajo.
- Con la pestaña oculta el renderer se congela (timeouts de CDP de 45 s): trae
  la pestaña al frente.

## 4. Clips — Magnific · Kling 2.5 (respaldo)

Space «Foto con IA a Video 2»: `https://www.magnific.com/app/spaces/a285a2e7-03d4-426c-9053-4ef927673519`
(prompt anti-movimiento ya dentro; 720p ilimitado, 1080p gasta créditos).
Pasos (coordenadas en ventana 1568×726): clic nodo lista (600,92) → «⋯» (730,342)
→ «Clear list» (797,436) → pasa el ratón por «Add media» (646,208) y clic (647,243)
→ **repite el gesto** hasta que aparezca el `input[type=file]` → `upload` de las
imágenes → «Add N» (1413,652) → Run (888,132). **Tandas de ≤5.**
- La cola es **de la cuenta**: si hay OTRO agente o sesión generando a la vez (el
  29/9 lo había, y se colaron clips ajenos y esperas largas), los clips que salen
  pueden no ser tuyos. Con la cuenta solo para ti no pasa: el operador confirmó
  que la cola es suya. Kling ~8 min/clip en serie, ~35 min para 4.
- Resultados sin descargar: `fetch('/app/api/creations?limit=8')` desde la
  pestaña de Magnific → cada `creation` trae en su JSON
  `https://pikaso.cdnpk.net/private/production/<id>/video.mp4?token=…` (regex
  `https:[^"\\]+video\.mp4[^"\\]*`) → `curl`. Salen 716×1284 y 10 s: recortar a 7,3-8 s.
- No mezclar con `zoom/scale` del navegador.

## 5. Emparejar clip ↔ imagen y revisar (scripts)

Los clips bajados no traen nombre. Se emparejan por el **primer fotograma** contra
las imágenes de entrada (error cuadrático en 36×64 grises; < ~60 = mío; miles = de
otro). Snippets mínimos (en `~/work/` del VPS):

```python
# match.py: id|url por stdin -> baja, empareja con pick/*.jpg, guarda cand/<clave>.mp4
import sys,os,subprocess,glob,numpy as np
from PIL import Image
refs={os.path.basename(f)[:-4]:np.asarray(Image.open(f).convert('L').resize((36,64)),float) for f in glob.glob('pick/*.jpg')}
for l in sys.stdin:
    cid,url=l.strip().split('|',1); v=f'kl/{cid}.mp4'
    subprocess.run(['curl','-s','-o',v,url]); subprocess.run(['ffmpeg','-y','-loglevel','error','-ss','0.05','-i',v,'-frames:v','1','z0.jpg'])
    a=np.asarray(Image.open('z0.jpg').convert('L').resize((36,64)),float)
    sc=sorted((float(((a-r)**2).mean()),k) for k,r in refs.items()); k=sc[0][1]
    dst=f'cand/{k}.mp4'; dst=dst if not os.path.exists(dst) else f'cand/{k}__{cid}.mp4'
    subprocess.run(['ffmpeg','-y','-loglevel','error','-i',v,'-c:v','libx264','-crf','17','-an',dst]); print(cid,'->',dst,int(sc[0][0]))
```

**Revisión** (imprescindible; con la cuenta al límite un detalle = sanción):
- Tira de 10 fotogramas (`ffmpeg -ss t -frames:v 1` a t=0,1…7,2 pegados en una hoja)
  **y** primer/medio/último fotograma en grande. Mira **el último segundo**.
- Rechaza: dos manos; la mano coge/mueve/gira el producto; algo aparece o
  desaparece (humo, un metro, un objeto rosa, USB, LEDs); **luz o pantalla que se
  enciende**; el producto flota o se descoloca (un auricular «volando»); texto
  inventado; niños; contornos blancos/artefactos; el producto deforma.
- **Rozar/apoyar el dedo NO es motivo** si el producto no se mueve ni se deforma
  (criterio del operador). Luces de un espejo LED que cambian: tampoco.
- Mide el movimiento medio entre fotogramas (`fps=4, scale=90:160`, media de
  |a−b|): los sanos andan en 2-3; un clip casi foto ronda 1-1,5. Es una pista,
  no una regla (la sanción «contenido estático» del 29/9 se apeló y se ganó).
- Los clips «aceptables por separado» pueden no valer juntos: mira que las dos
  escenas sean distintas.

## 6. Subir y montar

```bash
# subir el fichero al MCP y luego subir_clip (hacer con el token del usuario correcto)
id=$(curl -s -F file=@clip.mp4 "$MCP/subir" | python -c "import sys,json;print(json.load(sys.stdin)['archivo_id'])")
# subir_clip: menu=pov_bof_largo, catalogo, carpeta, producto, clip=N, archivo_id, modo, voz=auto
```

- **Token por usuario** (`ness`, `mauro`…): cada uno tiene su progreso, su modo
  (`precio`/`dolor`) y sus marcas «Rehacer». Súbelo al usuario que toca.
- El primer `subir_clip` responde «Falta el clip 2»; con el segundo dice «locutando
  y montando» y devuelve un `job_id` → `estado(job_id)`.
- **Si el montaje sale `failed`, los clips ya se borraron del hueco: hay que volver
  a subirlos** (guarda siempre los `.mp4` finales, recortados).
- **Fish «Reference not found» (400)**: una voz del banco (`config.VOCES`) fue
  retirada por Fish (29/9: «Joven Relajado»). Arreglado en `voz.py`: cambia de voz
  solo ante 400/404 «reference». Si aun así falla, reintenta y prueba
  `config.VOCES` una a una (script en el chat del 29/9: POST a
  `https://api.fish.audio/v1/tts` con cada `reference_id`).
- Un reinicio de la API (deploy de otra sesión) da 502 unos minutos y corta subidas
  a medias: espera a `/api/health`=200, mira `clips_subidos` y resube lo que falte.
- La marca «Rehacer» **se quita sola al montarse OK** el vídeo nuevo; si sigue
  puesta es que el montaje falló.

## 7. Cifras y ritmos reales (para planificar)

| Cosa | Medido |
|---|---|
| Flow imagen | ~40 s; 2×15 productos ≈ 1 h con saturaciones |
| GenAI Pro clip | 3-6 min; falla a menudo con >3 a la vez |
| Kling clip | ~8 min en serie, cola compartida |
| Montaje (voz+subs+flecha) | 2-4 min por producto, 4 en paralelo OK |
| Repeticiones típicas | 1 de cada 3 clips; mochilas, kits de piezas, aparatos con luz y productos con manos cerca son los peores |

## 8. Errores de estos días que no hay que repetir

- Regenerar lo que el operador ya subió a TikTok.
- Sustituir el gesto de la mano del prompt (temblor).
- Aprobar un clip mirando solo la mano: **mira el producto** en todos los planos.
- Dejar la pestaña de Flow en segundo plano.
- Dar por tuyo un clip de la cola de Magnific sin emparejarlo (si hay otro agente
  generando, se cuelan clips ajenos).
- Escenas con dos vistas del producto o con textos de la ficha.
