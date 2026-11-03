# Navegador del PC de casa (3/11/2026)

El mismo montaje que `deploy/navegador/` (Chrome + pantalla virtual + noVNC + CDP),
pero en el PC de sobremesa del operador: Windows + WSL `Ubuntu-24.04`, usuario `ness`,
nodo Tailscale `9ness-casa-1` (`100.125.167.31`). Sirve para **repartir**: unos agentes
generan en el Chrome del VPS y otros en este, que además sale por la IP de casa
(residencial, sin proxy).

- **Servicios de USUARIO** (`systemctl --user`, sin sudo; `loginctl enable-linger ness`):
  `navegador-{pantalla,chrome,vnc}.service`, `navegador.target`, `navegador-auto.timer`
  (se apaga a los 45 min sin VNC ni CDP). Script `~/.local/bin/navegador on|off|json|clave`.
- Perfil en `~/.navegador-agente/perfil` (**no borrar**: guarda las sesiones). Contraseña
  de la pantalla en `~/.config/navegador/clave` (aleatoria, 600).
- CDP solo en `127.0.0.1:9222` del PC. noVNC (websockify) solo en la IP de Tailscale `:6080`.
- Web: Accesos › «🏠 Navegador remoto · PC de casa» → `/navegador-casa/` (Caddy, misma
  puerta de admin que `/navegador/`). El listener del host lo maneja por
  `ssh ness@100.125.167.31 .local/bin/navegador …` (`NAVEGADOR_CASA_SSH`). Si el PC
  no responde, la tarjeta dice «PC sin conexión».
- Arranque: `Startup/ubuntu-worker.vbs` de Windows lanza `wsl -d Ubuntu-24.04 --exec
  sleep infinity` al iniciar sesión; sin sesión de Windows no hay PC.

**Instalar / actualizar** (desde el VPS; antes, en el PC, `sudo apt install -y xvfb x11vnc
novnc websockify fluxbox xdotool fonts-noto-color-emoji google-chrome-stable`):
```bash
cp deploy/navegador/visor.html deploy/navegador_casa/ && scp -r deploy/navegador_casa ness@100.125.167.31:/tmp/
ssh ness@100.125.167.31 bash /tmp/navegador_casa/instalar.sh
```

**Gotcha WSL:** `/tmp/.X11-unix` es de WSLg y Xvfb no deja ahí `X99` (solo el socket
abstracto), así que `navegador-vnc` espera a que `:99` responda con `xdotool`, no al fichero.
