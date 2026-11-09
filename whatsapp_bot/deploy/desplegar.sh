#!/bin/bash
# desplegar.sh — sube el bot de WhatsApp del Editor de esta copia (vps-trabajo) a vps-webs.
#   ./desplegar.sh --preparar  → crea ~/proyectos/whatsapp-bot/.env.local (tokens generados, sin imprimirlos)
#   ./desplegar.sh --estado    → qué variables faltan (solo nombres) y si el servicio responde
#   ./desplegar.sh             → despliega (copia antes la versión en marcha) y reinicia
#   ./desplegar.sh --enlazar   → apunta la API del editor al bot (añade 3 variables al .env de la fábrica)
#   ./desplegar.sh --volver    → vuelve a la última copia guardada
# Nunca toca datos/ (conversaciones): eso vive solo en vps-webs. Nunca imprime una clave.
# Lo ejecuta el chat del Editor con el sí de Néstor. No toca Caddy: imprime el bloque que hay que añadir.
set -euo pipefail
cd "$(dirname "$0")/.."                       # whatsapp_bot/
REPO=$(cd .. && pwd)
P=nebulabsai@100.83.196.101; IP=100.83.196.101; PUERTO=8093
R=/home/nebulabsai/whatsapp-bot
C=$HOME/proyectos/whatsapp-bot; F=$C/.env.local   # donde escribe `clave whatsapp-bot <VARIABLE>`
FABRICA=${FABRICA:-$HOME/proyectos/TikTok_Automation_Python}

valor() { grep -m1 "^$1=" "$2" 2>/dev/null | cut -d= -f2- || true; }
poner() { grep -q "^$1=" "$F" || printf '%s=%s\n' "$1" "$2" >> "$F"; }
faltan() {
  local prov; prov=$(valor WHATSAPP_PROVEEDOR "$F"); local lista
  if [ "$prov" = 360dialog ]; then lista="D360_API_KEY WHATSAPP_WEBHOOK_SECRETO"
  else lista="WHATSAPP_ACCESS_TOKEN WHATSAPP_APP_SECRET WHATSAPP_PHONE_NUMBER_ID WHATSAPP_WABA_ID WHATSAPP_VERIFY_TOKEN"; fi
  for k in $lista WHATSAPP_ADMIN_TOKEN WHATSAPP_INTERNO_TOKEN EDITOR_API_KEY ANTHROPIC_API_KEY PANEL_TOKEN; do
    [ -n "$(valor "$k" "$F")" ] || echo "  falta $k   →  clave whatsapp-bot $k"
  done
}

case "${1:-}" in
--preparar)
  mkdir -p "$C"; [ -f "$C/.gitignore" ] || printf '.env.local\n' > "$C/.gitignore"
  touch "$F"; chmod 600 "$F"
  poner WHATSAPP_PROVEEDOR meta
  poner WHATSAPP_URL_PUBLICA https://factory.nebulabsmedia.com/wa
  poner WHATSAPP_DB $R/datos/whatsapp.db
  poner EDITOR_API_URL http://100.96.125.108:8080
  poner PANEL_URL http://127.0.0.1:8800
  for k in WHATSAPP_VERIFY_TOKEN WHATSAPP_WEBHOOK_SECRETO WHATSAPP_ADMIN_TOKEN WHATSAPP_INTERNO_TOKEN; do
    poner "$k" "$(openssl rand -hex 24)"
  done
  k=$(valor API_KEY "$FABRICA/.env"); [ -z "$k" ] || poner EDITOR_API_KEY "$k"
  echo "Listo: $F (chmod 600). Con 360dialog: cambia WHATSAPP_PROVEEDOR a 360dialog."
  faltan; exit ;;
--estado)
  [ -f "$F" ] || { echo "No existe $F: ejecuta antes --preparar"; exit 1; }
  echo "Proveedor: $(valor WHATSAPP_PROVEEDOR "$F") · webhook: $(valor WHATSAPP_URL_PUBLICA "$F")/webhook"
  faltan
  ssh $P "systemctl is-active whatsapp-bot 2>/dev/null || true; curl -s -m 5 http://$IP:$PUERTO/salud || echo 'sin respuesta'"; echo
  exit ;;
--enlazar)
  E=$FABRICA/.env; [ -f "$E" ] || { echo "No encuentro $E"; exit 1; }
  t=$(valor WHATSAPP_INTERNO_TOKEN "$F"); [ -n "$t" ] || { echo "Falta WHATSAPP_INTERNO_TOKEN: ejecuta --preparar"; exit 1; }
  grep -q '^EDITOR_WHATSAPP_BOT_URL=' "$E" || printf '\nEDITOR_WHATSAPP_BOT_URL=http://%s:%s\n' "$IP" "$PUERTO" >> "$E"
  grep -q '^EDITOR_WHATSAPP_BOT_TOKEN=' "$E" || printf 'EDITOR_WHATSAPP_BOT_TOKEN=%s\n' "$t" >> "$E"
  grep -q '^EDITOR_WHATSAPP_AVISOS=' "$E" || printf 'EDITOR_WHATSAPP_AVISOS=1\n' >> "$E"
  echo "Añadidas al .env de la fábrica (si no estaban). Para que la API las lea hay que recrear su contenedor"
  echo "(deploy/deploy_safe.sh o docker compose up -d api): eso lo decide el Editor, este script no lo hace."
  exit ;;
--volver)
  ssh $P "u=\$(ls -t ~/whatsapp-bot-versiones/*.tgz | head -1); echo \"Vuelvo a \$u\"; tar xzf \$u -C $R && sudo systemctl restart whatsapp-bot && sleep 2 && systemctl is-active whatsapp-bot"
  exit ;;
"") ;;
*) echo "Opción desconocida: $1"; exit 1 ;;
esac

# ── Comprobaciones antes de subir
[ -f "$F" ] || { echo "No existe $F: ejecuta antes ./desplegar.sh --preparar"; exit 1; }
python3 -m py_compile ./*.py
python3 -c "import json,glob; [json.load(open(p)) for p in glob.glob('plantillas/*.json')]"
git -C "$REPO" diff --quiet -- whatsapp_bot && git -C "$REPO" diff --cached --quiet -- whatsapp_bot \
  || { echo "Hay cambios sin commit en whatsapp_bot/: haz commit antes de desplegar."; exit 1; }
[ -z "$(faltan)" ] || { echo "Aviso: aún faltan claves (el servicio arranca y la página dice cuáles):"; faltan; }

# ── Copia de la versión en marcha (se guardan las 20 últimas) y subida
ssh $P "mkdir -p $R/whatsapp_bot $R/datos ~/whatsapp-bot-versiones && cd $R && tar czf ~/whatsapp-bot-versiones/\$(date +%Y%m%d-%H%M%S).tgz --exclude=datos --exclude=venv --exclude=.env --exclude=__pycache__ . && ls -t ~/whatsapp-bot-versiones/*.tgz | tail -n +21 | xargs -r rm"
rsync -ai --delete --exclude __pycache__ --exclude datos --exclude deploy --exclude '.env*' --exclude README.md ./ $P:$R/whatsapp_bot/ | grep '^[<*]' || echo "Sin cambios de código"
rsync -a --chmod=600 "$F" $P:$R/.env
scp -q deploy/whatsapp-bot.service $P:$R/whatsapp-bot.service
ssh $P "set -e; cd $R
  [ -x venv/bin/uvicorn ] || { python3 -m venv venv || { echo 'Falta python3-venv: sudo apt install python3.12-venv'; exit 1; }; }
  venv/bin/pip install -q -r whatsapp_bot/requirements.txt
  cmp -s whatsapp-bot.service /etc/systemd/system/whatsapp-bot.service || { sudo cp whatsapp-bot.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable -q whatsapp-bot; }
  sudo systemctl restart whatsapp-bot; sleep 3; systemctl is-active whatsapp-bot"

c=$(ssh $P "curl -s -o /dev/null -w '%{http_code}' -m 10 http://$IP:$PUERTO/salud" || true)
echo "http://$IP:$PUERTO/salud → $c"
[ "$c" = 200 ] || { echo "¡OJO! El bot no responde 200 (journalctl -u whatsapp-bot -n 50). Vuelve atrás con ./desplegar.sh --volver"; exit 1; }
u=$(valor WHATSAPP_URL_PUBLICA "$F")
p=$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$u/webhook?hub.mode=subscribe&hub.verify_token=x&hub.challenge=1" || true)
if [ "$p" = 403 ]; then echo "Webhook público $u/webhook → responde (403 con token malo, correcto)"
else cat <<CADDY
Webhook público $u/webhook → $p. Falta publicarlo: añade en /etc/caddy/Caddyfile de vps-webs, dentro del
bloque de factory.nebulabsmedia.com y ANTES de «handle @grande», y recarga (sudo systemctl reload caddy):

	handle /wa/webhook {
		rewrite * /webhook
		reverse_proxy $IP:$PUERTO
	}

Solo se publica /webhook; /admin y /interno quedan dentro de Tailscale.
CADDY
fi
echo "Desplegado $(git -C "$REPO" log --oneline -1)"
