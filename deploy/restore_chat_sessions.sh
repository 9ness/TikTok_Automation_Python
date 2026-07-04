#!/usr/bin/env bash
#
# restore_chat_sessions.sh — activa Remote Control en todos los chats
# marcados como "always-on" (o los 10 más recientes si no hay pins aún),
# llamando al endpoint del Agent SDK:
#
#     POST http://172.18.0.1:8765/remote/start-all
#       Header: X-API-Key: <api_key del .env>
#
# El SDK internamente para cada UUID:
#   - kill-session rc_<uuid16>  (por si había residuo)
#   - tmux new-session -d ... claude --resume <uuid> --permission-mode acceptEdits
#   - send-keys "/remote-control" + Space + Enter → activa Remote Control
#   - captura la URL claude.ai/code/... para retorno
#
# Los chats aparecen no sólo "Conectado" sino con **Remote Control ACTIVO**
# en la app Claude, igual que si los hubieras abierto uno por uno.
#
# La lista "always-on" se gestiona desde la UI del chat web (botón 📌 pin
# per-chat). Persistente en ~/.claude/remote_state/always_on.json.
#
# Uso:
#   bash deploy/restore_chat_sessions.sh          # restaura todos los pinneados
#   bash deploy/restore_chat_sessions.sh --dry    # solo muestra qué haría
#
# Llamado automáticamente por `claude-restore-sessions.service` al bootear.
#
set -uo pipefail

SDK_HOST="${SDK_HOST:-172.18.0.1}"
SDK_PORT="${SDK_PORT:-8765}"
BASE="http://${SDK_HOST}:${SDK_PORT}"
ENV_FILE="${HOME}/TikTok_Automation_Python/.env"
DRY=0
[[ "${1:-}" == "--dry" ]] && DRY=1

# Leer API_KEY del .env que usa el SDK.
API_KEY=""
if [[ -f "$ENV_FILE" ]]; then
  API_KEY=$(grep -E "^API_KEY=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'"'')
fi

# Espera al SDK (si estamos en boot, tarda unos segundos en estar listo).
attempts=0
while ! curl -s --max-time 3 "${BASE}/health" >/dev/null 2>&1; do
  attempts=$((attempts + 1))
  if [[ $attempts -gt 60 ]]; then
    echo "[restore_chat_sessions] ❌ SDK no responde en ${BASE} tras 60s — abort"
    exit 1
  fi
  sleep 1
done

# Consulta primero cuántos hay marcados always-on (sólo para el mensaje log).
count=$(curl -s --max-time 5 "${BASE}/remote/always-on" \
          -H "X-API-Key: ${API_KEY}" 2>/dev/null \
          | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('uuids', [])))" 2>/dev/null || echo "?")
echo "[restore_chat_sessions] SDK vivo · ${count} chat(s) marcados always-on · dry=${DRY}"

if [[ $DRY -eq 1 ]]; then
  # Sólo mostrar la lista, no activarlos.
  curl -s --max-time 5 "${BASE}/remote/always-on" \
       -H "X-API-Key: ${API_KEY}" | python3 -m json.tool
  echo "[restore_chat_sessions] (dry) NO se activó nada"
  exit 0
fi

# Delegamos al endpoint que hace todo en paralelo con lógica interna.
# `--max-time 240`: 6-8 chats × ~24s en paralelo = ~30-40s peak, damos margen.
out=$(curl -s --max-time 240 -X POST "${BASE}/remote/start-all" \
        -H "X-API-Key: ${API_KEY}" 2>&1) || true

if [[ -z "$out" ]]; then
  echo "[restore_chat_sessions] ❌ endpoint devolvió vacío"
  exit 1
fi

# Parseamos y logueamos resumen + detalles.
python3 - <<PY
import json, sys
try:
    d = json.loads("""${out}""")
except Exception as e:
    print(f"[restore_chat_sessions] ❌ respuesta no-JSON: {e}")
    sys.exit(1)
print(f"[restore_chat_sessions] procesados={d.get('total_processed')} · "
      f"activados={d.get('started')} · ya activos={d.get('already_active')} · "
      f"fallidos={d.get('failed')}")
for r in d.get("results", []):
    icon = "✅" if r.get("remote") else "❌"
    reason = r.get("skipped_reason", "")
    reason_str = f" ({reason})" if reason else ""
    url = r.get("url", "")
    url_str = f" · {url}" if url else ""
    print(f"  {icon} project={r.get('project'):30s} uuid={r.get('uuid','')[:8]}"
          f"{reason_str}{url_str}")
PY
