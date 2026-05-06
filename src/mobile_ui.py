"""
CSS responsive global. Una única función `inject_responsive_css()` que
se llama en main.py justo tras `st.set_page_config`. Cero cambios de
lógica — solo presentación. El objetivo es que toda la app sea cómoda
en móvil (TikTok-friendly): columnas que se apilan, paddings reducidos,
inputs que no provocan auto-zoom en iOS, vídeos a ancho completo, tabs
con scroll horizontal, sidebar overlay nítido, y zonas de toque grandes.
"""

import streamlit as st


_CSS = """
<style>
/* ============================================================
   GLOBAL — base compacta para desktop también (sin pasarse)
   ============================================================ */
.block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 2rem !important;
    padding-left: 1.2rem !important;
    padding-right: 1.2rem !important;
    max-width: 1400px;
}

/* Headings ligeramente más compactos en general */
h1 { font-size: 1.85rem !important; line-height: 1.2 !important; margin: 0.2rem 0 0.6rem !important; }
h2 { font-size: 1.4rem !important;  line-height: 1.25 !important; margin: 0.5rem 0 0.4rem !important; }
h3 { font-size: 1.15rem !important; line-height: 1.3 !important; margin: 0.4rem 0 0.3rem !important; }
h4 { font-size: 1.0rem  !important; line-height: 1.3 !important; margin: 0.3rem 0 0.2rem !important; }

/* Divider menos invasivo */
hr { margin: 0.8rem 0 !important; opacity: 0.4; }

/* Captions un pelín más legibles */
[data-testid="stCaptionContainer"] { font-size: 0.82rem; opacity: 0.85; }

/* Botones: padding cómodo + fuente coherente */
.stButton > button,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button {
    border-radius: 8px;
    font-weight: 600;
    transition: transform 0.05s ease;
}
.stButton > button:active { transform: scale(0.98); }

/* Sidebar: ancho razonable en desktop */
[data-testid="stSidebar"] {
    min-width: 280px;
    max-width: 320px;
}

/* Toolbar superior limpio */
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] { right: 0.5rem; }

/* Vídeo / imágenes nunca desbordan */
.stVideo, .stVideo video { max-width: 100% !important; height: auto !important; }
[data-testid="stImage"] img { max-width: 100% !important; height: auto !important; }

/* Status / expanders: bordes suaves y aire */
[data-testid="stExpander"] {
    border-radius: 8px;
}
[data-testid="stExpander"] details summary {
    padding: 0.55rem 0.8rem !important;
    font-weight: 500;
}

/* Métricas más compactas */
[data-testid="stMetric"] { padding: 0.3rem 0.6rem; }
[data-testid="stMetricLabel"] p { font-size: 0.78rem !important; }
[data-testid="stMetricValue"] { font-size: 1.25rem !important; }

/* Tabs: si no caben, scroll horizontal en lugar de wrap raro */
[data-testid="stTabs"] [role="tablist"] {
    overflow-x: auto !important;
    scrollbar-width: thin;
}
[data-testid="stTabs"] [role="tab"] { white-space: nowrap !important; }

/* Radio horizontal: no romper layout cuando hay muchas opciones */
[data-testid="stRadio"] [role="radiogroup"] {
    flex-wrap: wrap !important;
    gap: 0.35rem 0.8rem !important;
}

/* File uploader: zona drop más compacta */
[data-testid="stFileUploadDropzone"] {
    padding: 0.8rem !important;
    min-height: 5rem !important;
}

/* ============================================================
   TABLET — entre 769px y 1024px
   ============================================================ */
@media (min-width: 769px) and (max-width: 1024px) {
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    [data-testid="stSidebar"] {
        min-width: 240px;
        max-width: 280px;
    }
    h1 { font-size: 1.6rem !important; }
}

/* ============================================================
   MÓVIL — < 768px (núcleo del trabajo)
   ============================================================ */
@media (max-width: 768px) {
    /* Padding mínimo sin que el contenido toque el borde */
    .block-container {
        padding: 0.6rem 0.7rem 4.5rem 0.7rem !important;
    }

    /* Header fino y deploy oculto (ahorra espacio) */
    [data-testid="stHeader"] { height: 2.4rem; }
    [data-testid="stToolbar"] { right: 0.3rem; }
    [data-testid="stToolbar"] [data-testid="stDeployButton"],
    [data-testid="stDecoration"] { display: none !important; }

    /* TIPOGRAFÍA — TikTok-friendly */
    h1 { font-size: 1.35rem !important; margin-top: 0 !important; }
    h2 { font-size: 1.1rem  !important; }
    h3 { font-size: 1.0rem  !important; }
    h4 { font-size: 0.95rem !important; }
    p, li, label, .stMarkdown { font-size: 0.92rem !important; }
    [data-testid="stCaptionContainer"] { font-size: 0.78rem !important; }

    /* ============================================================
       FORZAR STACKING VERTICAL DE TODAS LAS COLUMNAS
       — la pieza clave: en móvil ningún st.columns([...])
       se ve a 2/3/4 columnas; todo apilado a 100% de ancho
       ============================================================ */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 0.5rem !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        flex: 1 1 100% !important;
        min-width: 100% !important;
        width: 100% !important;
    }

    /* Botones: ancho completo y zona de toque grande */
    .stButton > button,
    [data-testid="stDownloadButton"] button,
    [data-testid="stFormSubmitButton"] button {
        width: 100% !important;
        padding: 0.7rem 1rem !important;
        font-size: 0.95rem !important;
        min-height: 2.6rem !important;
    }

    /* Inputs tamaño 16px = NO auto-zoom en iOS Safari */
    .stTextInput input,
    .stTextArea textarea,
    .stNumberInput input,
    .stDateInput input,
    .stTimeInput input,
    [data-baseweb="select"] input,
    [data-baseweb="select"] div[role="combobox"] {
        font-size: 16px !important;
    }

    /* Selects / multiselect cómodos */
    [data-baseweb="select"] > div { min-height: 2.6rem !important; }

    /* Sidebar: cuando se abre, casi pantalla completa para no agobiar */
    [data-testid="stSidebar"] {
        min-width: 88vw !important;
        max-width: 88vw !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding: 0.6rem 0.7rem !important;
    }
    /* Botón de cerrar sidebar más visible */
    [data-testid="stSidebarCollapseButton"] button { padding: 0.5rem !important; }

    /* Expanders: padding reducido, texto del header un poco más pequeño */
    [data-testid="stExpander"] details summary {
        padding: 0.5rem 0.65rem !important;
        font-size: 0.92rem !important;
    }
    [data-testid="stExpander"] details > div { padding: 0.5rem 0.65rem !important; }

    /* Métricas — st.columns(4) con st.metric pasa a 2x2 en móvil
       (legible y compacto). En pantallas muy estrechas (<420px) se
       apila a 1 por fila — ver bloque de abajo. */
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has([data-testid="stMetric"]) {
        flex: 1 1 48% !important;
        min-width: 48% !important;
        width: 48% !important;
    }

    /* Excepción: contenedores marcados con key="compact_row_*" mantienen
       sus columnas internas en horizontal (50/50) en móvil. Útil para
       pares Top+Prefijo, etc. donde el stacking forzado deja widgets
       cortos como Selectbox a 100% y desperdicia altura. */
    [class*="st-key-compact_row_"] [data-testid="stColumn"] {
        flex: 1 1 calc(50% - 0.3rem) !important;
        min-width: calc(50% - 0.3rem) !important;
        width: calc(50% - 0.3rem) !important;
    }
    /* Padding interno + tipografía agresiva (selectores específicos
       para ganar a las clases auto-generadas de emotion) */
    [data-testid="stMetric"] {
        padding: 0.4rem 0.55rem !important;
        background: rgba(255,255,255,0.025);
        border-radius: 8px;
    }
    [data-testid="stMetric"] [data-testid="stMetricLabel"],
    [data-testid="stMetric"] [data-testid="stMetricLabel"] p,
    [data-testid="stMetric"] [data-testid="stMetricLabel"] div {
        font-size: 0.72rem !important;
        line-height: 1.1 !important;
        opacity: 0.85;
    }
    /* El valor: Streamlit lo renderiza dentro de un div anidado con
       font-size grande aplicado por clases generadas. Forzamos en
       cascada todos los descendientes de stMetricValue. */
    [data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="stMetric"] [data-testid="stMetricValue"] > div,
    [data-testid="stMetric"] [data-testid="stMetricValue"] * {
        font-size: 1.05rem !important;
        line-height: 1.2 !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricDelta"],
    [data-testid="stMetric"] [data-testid="stMetricDelta"] * {
        font-size: 0.72rem !important;
    }

    /* Sliders: track un pelín más alto para tocar mejor */
    [data-testid="stSlider"] [role="slider"] { width: 1.2rem !important; height: 1.2rem !important; }

    /* Checkbox / radio: mayor target */
    [data-testid="stCheckbox"] label,
    [data-testid="stRadio"] label { padding: 0.2rem 0 !important; }

    /* st.video / imágenes ocupan el ancho del bloque */
    .stVideo, .stVideo video {
        width: 100% !important;
        max-height: 70vh !important;
    }
    [data-testid="stImage"] img { width: 100% !important; }

    /* Status box / progress: padding fino */
    [data-testid="stStatusWidget"] { padding: 0.4rem 0.6rem !important; }
    [data-testid="stProgress"] { padding: 0.3rem 0 !important; }

    /* File uploader: drop zone aún más compacta */
    [data-testid="stFileUploadDropzone"] {
        padding: 0.7rem !important;
        min-height: 4rem !important;
        font-size: 0.85rem !important;
    }

    /* Code / paths que no se salgan */
    code, pre {
        word-break: break-all !important;
        white-space: pre-wrap !important;
        font-size: 0.78rem !important;
    }

    /* Tabs scroll y target táctil mayor */
    [data-testid="stTabs"] [role="tab"] {
        padding: 0.55rem 0.8rem !important;
        font-size: 0.88rem !important;
    }

    /* st.toast: que no cubra controles */
    [data-testid="stToast"] { font-size: 0.85rem !important; }

    /* Color pickers en línea (los presets 🔵 🔴) */
    [data-testid="stColorPicker"] > div { width: 100% !important; }

    /* Reduce gap vertical entre widgets — densidad TikTok */
    [data-testid="stVerticalBlock"] { gap: 0.45rem !important; }

    /* Markdown info/warning/error con menos padding interno */
    [data-testid="stAlert"] { padding: 0.55rem 0.7rem !important; }
    [data-testid="stAlert"] p { font-size: 0.85rem !important; line-height: 1.35 !important; }
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] { font-size: 0.85rem !important; }

    /* Labels de widgets (encima de cada input/selectbox/slider/textarea):
       en móvil quedaban demasiado grandes y agrandaban toda la pantalla. */
    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] label,
    .stTextInput label,
    .stTextArea label,
    .stNumberInput label,
    .stSelectbox label,
    .stMultiSelect label,
    .stDateInput label,
    .stRadio label > div:first-child,
    .stCheckbox label > div:first-child,
    .stSlider label,
    .stColorPicker label,
    .stFileUploader label {
        font-size: 0.82rem !important;
        line-height: 1.25 !important;
        margin-bottom: 0.2rem !important;
        opacity: 0.92;
    }

    /* Texto dentro de selects/multiselect (tags) */
    [data-baseweb="select"] *,
    [data-baseweb="tag"] * {
        font-size: 0.85rem !important;
    }

    /* Textarea: fuente más legible y altura por defecto razonable */
    .stTextArea textarea {
        line-height: 1.4 !important;
    }

    /* Subheaders (st.subheader) un pelín más pequeños */
    [data-testid="stHeading"] h3,
    [data-testid="stSubheader"] {
        font-size: 1.0rem !important;
        margin-bottom: 0.3rem !important;
    }

    /* "Ver picks" y otros expandidos con texto interno markdown */
    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] p {
        font-size: 0.85rem !important;
        line-height: 1.35 !important;
        margin-bottom: 0.3rem !important;
    }

    /* Toolbar (3 puntos / "File change" / Rerun) — un pelín más pequeño
       para no robar tanto espacio de header en móvil */
    [data-testid="stStatusWidget"] * { font-size: 0.78rem !important; }

    /* ============================================================
       POPOVER (st.popover) — usado por el widget de cola para meter
       acciones secundarias en un menú desplegable mobile-friendly
       ============================================================ */
    [data-testid="stPopover"] button { min-height: 2.4rem !important; }
    [data-testid="stPopoverBody"] {
        max-width: 92vw !important;
        padding: 0.7rem !important;
    }
    [data-testid="stPopoverBody"] .stButton > button {
        font-size: 0.9rem !important;
        padding: 0.55rem 0.8rem !important;
        min-height: 2.5rem !important;
    }
    [data-testid="stPopoverBody"] [data-testid="stCaptionContainer"] {
        font-size: 0.78rem !important;
    }
}

/* ============================================================
   MÓVIL ESTRECHO — < 420px (iPhone SE / Android pequeños)
   ============================================================ */
@media (max-width: 420px) {
    .block-container { padding: 0.5rem 0.55rem 4rem 0.55rem !important; }
    h1 { font-size: 1.2rem !important; }
    h2 { font-size: 1.0rem !important; }
    h3 { font-size: 0.95rem !important; }

    /* En pantallas muy estrechas, las métricas en 2x2 horizontales
       (no 1 por fila). Más denso pero legible. */
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has([data-testid="stMetric"]) {
        flex: 1 1 48% !important;
        min-width: 48% !important;
        width: 48% !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="stMetric"] [data-testid="stMetricValue"] > div,
    [data-testid="stMetric"] [data-testid="stMetricValue"] * {
        font-size: 0.95rem !important;
    }
    [data-testid="stMetric"] [data-testid="stMetricLabel"],
    [data-testid="stMetric"] [data-testid="stMetricLabel"] p {
        font-size: 0.65rem !important;
    }
    [data-testid="stMetric"] { padding: 0.3rem 0.4rem !important; }

    /* Botones aún más compactos */
    .stButton > button { padding: 0.55rem 0.8rem !important; font-size: 0.88rem !important; }
}
</style>
"""


def inject_responsive_css() -> None:
    """Inyecta el CSS responsive global. Llamar una sola vez justo tras
    `st.set_page_config`."""
    st.markdown(_CSS, unsafe_allow_html=True)
