# Desarrollo local — Setup y troubleshooting

> Guía rápida para arrancar el proyecto en local con hot-reload tanto en
> backend como frontend, sin Docker. Docker solo se usa para producción
> (ver [`deploy/README.md`](deploy/README.md)).

## TL;DR — Arrancar en 2 terminales

```powershell
# Terminal 1 — API FastAPI (hot-reload con --reload)
cd d:\Proyectos_Personales\TikTok_Automation_Python
.\venv\Scripts\activate
uvicorn src.api.main:app --reload --port 8000

# Terminal 2 — Frontend Next.js (HMR nativo)
cd d:\Proyectos_Personales\TikTok_Automation_Python\frontend
npm run dev
```

Abre **http://localhost:3000**.

- Cambios en `frontend/**/*.tsx` → recarga automática del navegador (HMR).
- Cambios en `src/**/*.py` → uvicorn reinicia el server solo. Hace falta
  recarga manual del navegador (F5) si los cambios afectan a la respuesta
  de la API.

> **Streamlit legacy** (`main.py`) sigue funcionando en paralelo en el
> puerto 8501 con `streamlit run main.py`. No interfiere con la API.

---

## Variables de entorno

### Backend (`.env` en la raíz)

```env
# API auth — vacío = sin auth (modo dev cómodo)
API_KEY=

# Resto: ver CLAUDE.md
OPENAI_API_KEY=...
MINIMAX_API_KEY=...
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...
```

### Frontend (`frontend/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
# NEXT_PUBLIC_API_KEY=...  # solo si API_KEY está set en backend
```

---

## Errores comunes y soluciones

### ❌ `ModuleNotFoundError: No module named 'streamlit'` al arrancar API

**Causa**: `src/queue/__init__.py` importaba `render_queue_widget` (que usa
streamlit) en top-level, arrastrando streamlit como dep obligatoria de la
API. La API NO necesita streamlit.

**Fix aplicado**: el import es lazy en
[`src/queue/__init__.py`](src/queue/__init__.py). Solo se carga streamlit
cuando `main.py` (Streamlit legacy) lo invoca.

---

### ❌ WebSocket 404 + warning "No supported WebSocket library detected"

**Causa**: uvicorn por defecto no incluye `websockets`/`wsproto`. Sin
ellas, el endpoint `/ws/queue` devuelve 404 y la cola en tiempo real no
funciona (los endpoints HTTP sí funcionan).

**Síntomas**:
```
WARNING: No supported WebSocket library detected. Please use "pip install
'uvicorn[standard]'", or install 'websockets' or 'wsproto' manually.
INFO: 127.0.0.1:50663 - "GET /ws/queue HTTP/1.1" 404 Not Found
```

**Fix**:
```powershell
.\venv\Scripts\pip.exe install websockets wsproto httptools watchfiles
```

`websockets` está en `requirements.txt` desde el último push.

**⚠️ Cuidado con múltiples Python instalados**: si tienes Python global
+ venv, `pip install` puede ir al global mientras `uvicorn` corre desde el
venv. Verifica con:
```powershell
where uvicorn
where python
```
El PRIMER resultado es el que usa PowerShell. Asegúrate de instalar en el
mismo Python donde corre uvicorn:
```powershell
# Forzar usar el pip del venv
.\venv\Scripts\pip.exe install <paquete>
```

---

### ❌ Dashboard "Failed to fetch" o tarda 30+ segundos

**Causa**: el endpoint `/api/v1/dashboard/summary` escanea TODOS los
productos, usuarios y generaciones en Redis (Upstash REST API) cada vez.
Con datos reales tarda ~30s y el navegador timeout.

**Fix aplicado**: cache en memoria con TTL 60s en
[`src/api/routers/dashboard.py`](src/api/routers/dashboard.py). El primer
hit tras arrancar uvicorn tarda ~30s; los siguientes son instantáneos
durante 60s.

**Si vuelve a aparecer**:
- Verifica con `curl -m 30 http://localhost:8000/api/v1/dashboard/summary`
  que la API responde (puede tardar 30s)
- Hard refresh en navegador: `Ctrl + Shift + R` para limpiar el error
  obsoleto de React Query

---

### ❌ Frontend no coge cambios después de editar

1. **Cache `.next` corrupto**:
   ```powershell
   # Ctrl+C en la terminal de npm run dev
   Remove-Item -Recurse -Force d:\Proyectos_Personales\TikTok_Automation_Python\frontend\.next
   cd d:\Proyectos_Personales\TikTok_Automation_Python\frontend
   npm run dev
   ```

2. **Cache del navegador**: Ctrl + Shift + R, o abre en ventana incógnita.

3. **Service Worker** (raro en dev): F12 → Application → Service Workers
   → Unregister.

---

### ❌ Vídeos no aparecen como reproducibles desde la cola

El payload WebSocket no incluía `result_path`. **Fix aplicado** en
[`src/api/websockets/queue_ws.py:54`](src/api/websockets/queue_ws.py#L54)
— ahora cada job propaga `result_path`. Para verlo en jobs viejos
encolados antes del fix, reinicia uvicorn (el snapshot se reconstruye).

---

## Estructura de los 3 puertos en local

| Puerto | Servicio | Hot-reload | Necesario para |
|---|---|---|---|
| 3000 | Frontend Next.js (`npm run dev`) | ✅ HMR | Toda la UI nueva |
| 8000 | API FastAPI (`uvicorn --reload`) | ✅ `--reload` | Backend |
| 8501 | Streamlit legacy (`streamlit run main.py`) | ✅ nativo | UI vieja (no necesario para Next.js) |

---

## Producción (Docker)

Ver [`deploy/README.md`](deploy/README.md) — sección "Despliegue Docker
(FastAPI + Next.js + Caddy)". El stack Docker NO se usa en desarrollo.

```bash
# Solo cuando vayas a desplegar al servidor
docker compose --env-file .env up -d --build
```

---

## Comandos útiles de diagnóstico

```powershell
# Verificar que la API arranca
.\venv\Scripts\python.exe -c "from src.api.main import app; print('OK', len(app.routes))"

# Health check
curl http://localhost:8000/api/health

# Listar todas las rutas registradas
curl http://localhost:8000/api/openapi.json | python -c "import sys,json; [print(p) for p in json.load(sys.stdin)['paths']]"

# Test WS upgrade (debe devolver 101 si websockets está bien)
curl -s -o /dev/null -w "WS upgrade: HTTP %{http_code}\n" `
    -H "Connection: Upgrade" -H "Upgrade: websocket" `
    -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" `
    -H "Sec-WebSocket-Version: 13" `
    http://localhost:8000/ws/queue

# Frontend: verificar que typecheck pasa
cd frontend; npx tsc --noEmit
```

---

## Fixes recientes (post-migración Streamlit → Next.js)

- **2026-05-12**: Streamlit dep ya no obligatoria en API
  (`src/queue/__init__.py` lazy import).
- **2026-05-12**: Dashboard summary cacheado 60s (era 30s por request).
- **2026-05-12**: `result_path` propagado en payload WebSocket de la cola
  → botones Reproducir/Descargar/Drive aparecen en jobs completados.
- **2026-05-12**: `VideoModal` custom (sin Radix Dialog) garantiza ancho
  fijo 320px en TikTok Shop history + Queue dialog. Bypassa cualquier
  conflicto de clases Tailwind.
- **2026-05-12**: `websockets` añadido a `requirements.txt`.
- **2026-05-12**: Editor completo de Subs Auto (9 presets, 10 fuentes,
  6 highlight modes) + preview WYSIWYG con frame real del vídeo + drag
  vertical estilo CapCut.
- **2026-05-12**: Pronósticos con 12 controles nuevos (SFX completos,
  overlays, saturación, voces favoritas, resolución).
- **2026-05-12**: Quitar Copy con preview del vídeo subido + 2 colores
  predefinidos en chips.
