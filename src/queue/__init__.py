"""Sistema de cola unificada de generación de vídeos.

Permite encolar trabajos desde cualquier modo (Presidentes, Pronósticos,
Subs, Quitar Copy) y procesarlos secuencialmente en background. La UI
muestra un widget global con el estado de la cola en cualquier modo.

Diseño:
- `JobQueue` es un singleton vivo entre reruns de Streamlit (vía
  `@st.cache_resource`). Mantiene una lista de Jobs y un thread daemon
  que procesa el primero pendiente.
- Los runners (`runners.py`) son funciones puras que reciben `params` y
  callbacks de log/progreso. NO tocan `st.*`. Esto permite migrar a
  procesos separados (cloud) cambiando solo el manager.
- Persistencia: estado serializado a JSON en `temp_work/queue_state.json`
  para sobrevivir a reinicios de la app local. En cloud se sustituirá
  por Redis/SQLite sin tocar el resto.
"""

from .models import Job, JobMode, JobStatus
from .manager import get_queue
from .ui import render_queue_widget

__all__ = ["Job", "JobMode", "JobStatus", "get_queue", "render_queue_widget"]
