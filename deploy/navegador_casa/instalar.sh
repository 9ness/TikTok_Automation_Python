#!/bin/bash
# Instala el navegador remoto en el PC de casa (WSL Ubuntu, usuario normal, SIN sudo).
# Requisitos ya instalados con apt: xvfb x11vnc novnc websockify fluxbox xdotool google-chrome-stable.
# Se ejecuta desde el VPS: scp -r deploy/navegador_casa ness@<pc>:/tmp/ && ssh ness@<pc> bash /tmp/navegador_casa/instalar.sh
set -e
D=$(cd "$(dirname "$0")" && pwd)
mkdir -p ~/.config/systemd/user ~/.local/bin ~/.local/share/navegador/web ~/.navegador-agente/perfil ~/.navegador-agente/cache ~/.config/navegador ~/.vnc
cp "$D"/navegador-*.service "$D"/navegador-auto.timer "$D"/navegador.target ~/.config/systemd/user/
install -m 755 "$D"/navegador ~/.local/bin/navegador
# Visor web: noVNC del sistema + nuestro visor (sin sudo, en el home).
cp -r /usr/share/novnc/. ~/.local/share/navegador/web/
[ -f "$D"/visor.html ] && cp "$D"/visor.html ~/.local/share/navegador/web/visor.html
# Contraseña de la pantalla: aleatoria, solo la lee este usuario (el VPS la pide para el botón «Copiar»).
if [ ! -s ~/.config/navegador/clave ]; then
  umask 077; head -c 12 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 8 > ~/.config/navegador/clave
fi
chmod 600 ~/.config/navegador/clave
x11vnc -storepasswd "$(cat ~/.config/navegador/clave)" ~/.vnc/passwd >/dev/null
systemctl --user daemon-reload
systemctl --user enable --now navegador-auto.timer
echo "instalado: ~/.local/bin/navegador on|off|json"
