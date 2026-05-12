# Frontend Next.js — TikTok Automation

Reemplazo del UI Streamlit. Coexiste con `main.py` durante toda la migración.

## Arrancar

```bash
cd frontend
npm install
cp .env.local.example .env.local   # ajusta NEXT_PUBLIC_API_URL si hace falta
npm run dev
```

URL local: http://localhost:3000

El backend FastAPI debe estar corriendo en paralelo:

```bash
# en otra terminal, desde la raíz del repo
uvicorn src.api.main:app --reload --port 8000
```

## Stack
- Next.js 14 (App Router)
- TypeScript estricto (`noUncheckedIndexedAccess`)
- Tailwind CSS + shadcn/ui (componentes locales)
- next-themes (claro/oscuro)
- lucide-react

## Estructura
```
frontend/
├── app/                    # rutas (App Router)
├── components/
│   ├── layout/             # Sidebar, ThemeToggle, PagePlaceholder
│   └── ui/                 # shadcn (Button, Card)
├── lib/
│   ├── api.ts              # cliente HTTP de la API
│   ├── theme.tsx           # ThemeProvider
│   └── utils.ts            # cn()
└── tailwind.config.ts
```

## Roadmap
- ✅ 2A — Setup + sidebar + páginas placeholder
- ⏳ 2B — Dashboard global
- ⏳ 2C — Páginas Creator Reward
- ⏳ 2D — Páginas Productos TT Shop
- ⏳ 2E — Usuarios + Voces TT Shop
- ⏳ 2F — Generador + Histórico TT Shop
- ⏳ 2G — Cola flotante real-time global
