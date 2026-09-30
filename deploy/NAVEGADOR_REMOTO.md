# Navegador en el VPS — para que un agente genere en Flow / Magnific sin el PC

> **Estado (29-sep-2026): MONTADO, a demanda** en el VPS actual (CX33, 8 GB) como
> PRUEBA de si Google y Magnific dejan entrar desde la IP del servidor.
>
> **Sin terminal:** Ajustes › «🖥️ Navegador remoto» (solo admin) → Encender /
> Abrir navegador / Copiar contraseña / Apagar. «Abrir» va a `/navegador/`
> (Caddy `forward_auth` → `/api/v1/navegador/auth`, 200 solo si eres admin) y
> pide además la contraseña de la pantalla (segunda puerta). Se apaga solo tras
> 45 min sin cliente VNC ni agente por CDP (`navegador-auto.timer`).
>
> **Cómo funciona por dentro:**
> - Servicios systemd en `deploy/navegador/` (`navegador-{pantalla,chrome,vnc}`,
>   `navegador.target`, `navegador-auto.{service,timer}`) y el script
>   `/usr/local/bin/navegador on|off|estado|json|auto|clave`. NO arrancan al boot.
> - Chrome con tope de RAM (`MemoryHigh=2200M`, `MemoryMax=2800M`,
>   `OOMScoreAdjust=900`: si falta memoria muere Chrome, no la API). ~0,6-1 GB reales.
> - Perfil, caché y descargas en el disco extra:
>   `/mnt/HC_Volume_106974679/navegador/{perfil,cache,descargas}`. **No borrar `perfil`.**
> - x11vnc solo en 127.0.0.1:5900; websockify en `172.18.0.1:6080` (bridge docker;
>   ufw solo abre 172.18.0.0/16); CDP en 127.0.0.1:9222. Nada escucha en internet.
> - La API llama al `webhook_listener` del host (`/admin/navegador/*`, igual que el
>   panel Deploy) y este hace `sudo navegador …`.
> - Contraseña de la pantalla: `/root/navegador_vnc_password.txt` (aleatoria, solo
>   root; el botón «Copiar contraseña» la pone en el portapapeles, no se muestra).
> - Visor propio `deploy/navegador/visor.html` (sobre el `RFB` de noVNC): hay que copiarlo a
>   `/usr/share/novnc/visor.html` en el VPS (`scp` + `chmod 644`); `vnc.html` dejaba la pantalla
>   gris en Android. Se abre en `/navegador/visor.html#password=…` (barra: ⌨️ teclado, 📋 pegar, ↻).
> - Alternativa con terminal: `deploy/navegador_vps.ps1` (túnel SSH a `localhost:6080`).

## Para qué

Las imágenes y los clips se generan SIEMPRE en la web (Google Flow, GenAI Pro,
Magnific) con la cuenta del operador, nunca por API
(`src/agente_mcp/guias/README.md` › Reglas). Hoy eso exige un agente con el
Chrome del PC del operador (Claude in Chrome, Cowork, Atlas) y el PC encendido.

Con un Chrome **con pantalla virtual dentro del VPS**:
- el operador entra UNA vez en Google y en Magnific desde una pantalla remota
  (noVNC, en su navegador del móvil o del PC), y la sesión queda guardada en
  el perfil;
- el agente del VPS maneja ESE mismo Chrome por CDP (Playwright MCP) con la
  sesión ya abierta, con el PC apagado;
- lo que se descarga cae directamente en el disco del VPS, al lado de la
  bandeja del agente (`~/gdrive/.../_agente/<usuario>/`) y del MCP de la app.

## Pegas conocidas (decirlas antes de montarlo)

1. **Google desconfía de IPs de datacenter.** Al entrar desde el VPS suele
   pedir verificación (código al móvil) y de vez en cuando vuelve a pedirla.
   La hace el operador en la pantalla remota. Los CAPTCHA también: un agente
   NO los resuelve, avisa y espera.
2. **Memoria.** El VPS tiene 8 GB y 4 CPU. Flow en Chrome come 1–2 GB y los
   montajes de vídeo de la cola también. No generar mientras la cola está
   llena, y cerrar pestañas que no se usen.
3. **Seguridad.** Ese Chrome tiene la cuenta de Google del operador abierta.
   La pantalla remota y el puerto CDP NUNCA van a internet: noVNC solo por
   Tailscale o por túnel SSH, y CDP solo en `127.0.0.1`.
4. **Disco.** El disco raíz es de 75 GB y ha llegado a llenarse (ver
   `CLAUDE_REMOTE.md`). El perfil de Chrome y las descargas ocupan: mover los
   clips a la bandeja del Drive y borrar la copia local.
5. **Usar Google Chrome estable, no el Chromium de Playwright.** Con el
   Chromium de pruebas y banderas de automatización, Google bloquea el login
   («este navegador puede no ser seguro»).

## Montarlo (como root, ~20 min)

```bash
# 1. Pantalla virtual + VNC + noVNC + Chrome estable
apt-get update
apt-get install -y xvfb x11vnc novnc websockify fluxbox fonts-noto-color-emoji
wget -qO /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
apt-get install -y /tmp/chrome.deb

# 2. Contraseña del VNC (la elige el operador; no se escribe en ningún chat)
sudo -u nebulabsai x11vnc -storepasswd   # → ~/.vnc/passwd
```

Servicios systemd (usuario `nebulabsai`, display `:99`). Van en
`/etc/systemd/system/`:

```ini
# navegador-pantalla.service — pantalla virtual + gestor de ventanas
[Unit]
Description=Pantalla virtual :99 para el navegador remoto
[Service]
User=nebulabsai
ExecStart=/bin/sh -c 'Xvfb :99 -screen 0 1600x1000x24 & sleep 2; DISPLAY=:99 exec fluxbox'
Restart=on-failure
[Install]
WantedBy=multi-user.target

# navegador-chrome.service — Chrome con perfil persistente y CDP solo local
[Unit]
Description=Chrome del agente (perfil ~/.navegador-agente)
After=navegador-pantalla.service
Requires=navegador-pantalla.service
[Service]
User=nebulabsai
Environment=DISPLAY=:99
ExecStart=/usr/bin/google-chrome --user-data-dir=/home/nebulabsai/.navegador-agente \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 \
  --no-first-run --no-default-browser-check --disable-dev-shm-usage \
  --window-size=1600,1000 https://labs.google/fx/tools/flow
Restart=on-failure
[Install]
WantedBy=multi-user.target

# navegador-vnc.service — ver y usar la pantalla desde el navegador (noVNC)
[Unit]
Description=noVNC de la pantalla :99 (solo tailnet)
After=navegador-pantalla.service
[Service]
User=nebulabsai
ExecStart=/bin/sh -c 'x11vnc -display :99 -rfbauth /home/nebulabsai/.vnc/passwd -localhost -forever -shared -rfbport 5900 & exec websockify --web /usr/share/novnc 100.122.102.10:6080 localhost:5900'
Restart=on-failure
[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now navegador-pantalla navegador-chrome navegador-vnc
ufw allow in on tailscale0 to any port 6080 proto tcp comment 'noVNC navegador (solo tailnet)'
```

`100.122.102.10` es la IP de Tailscale del VPS (`tailscale ip -4`). noVNC NO se
publica en Caddy.

## Entrar el operador (una vez, y cuando caduque la sesión)

- **Con Tailscale** en el móvil o en el PC (misma cuenta que el VPS):
  `http://100.122.102.10:6080/vnc.html` → contraseña del VNC.
- **Sin Tailscale, desde el PC**: `ssh -L 6080:100.122.102.10:6080 root@62.238.19.31`
  y abrir `http://localhost:6080/vnc.html`.

Dentro: entrar en Google (Flow y GenAI Pro) y en Magnific, y aceptar lo que
pidan. El perfil `~/.navegador-agente` guarda las sesiones. **No borrarlo.**

## Cómo lo usa un agente del VPS

**Guía operativa completa para agentes:
[`src/agente_mcp/guias/comun/navegador-vps.md`](../src/agente_mcp/guias/comun/navegador-vps.md)**
(encender/apagar, controlarlo, cuidar CPU y RAM, limpieza de disco y el Space de
Magnific ya montado). Resumen:

- El agente **lo abre él solo** (`navegador on`) y lo controla por CDP con
  `/home/nebulabsai/cdp.py` (fuente `deploy/navegador/cdp.py`; venv
  `/home/nebulabsai/nav-venv` con `playwright`, sin descargar otro navegador). El
  operador no tiene que abrir nada; solo entra por **Accesos** si aparece un login.
- Se conecta al Chrome que YA está abierto (`connect_over_cdp`): un Chrome nuevo no
  tendría la sesión. El MCP de Playwright (`@playwright/mcp --cdp-endpoint
  http://127.0.0.1:9222`) también vale si el agente lo prefiere.
- Cuidado de recursos: una pestaña a la vez, cerrar el Space de Magnific entre
  tandas (1,5-2 GB), `navegador off` al acabar, y borrar fotos/clips descargados
  en cuanto el vídeo está subido (carpeta de trabajo en el disco extra).

Reglas que siguen valiendo igual: decir cuántas imágenes y clips se van a lanzar y
esperar el «sí» (cuestan créditos), revisar cada uno antes de subirlo, y no tocar
ajustes de las cuentas. Si aparece un login, una verificación o un CAPTCHA, parar y
pedir al operador que entre desde Accesos.

## Quitarlo

```bash
systemctl disable --now navegador-vnc navegador-chrome navegador-pantalla
rm /etc/systemd/system/navegador-*.service && systemctl daemon-reload
ufw delete allow in on tailscale0 to any port 6080 proto tcp
rm -rf /home/nebulabsai/.navegador-agente   # borra las sesiones guardadas
```

## Sesión de Claude Code del VPS (renovarla sin terminal)

La sesión de claude.ai del servidor caduca (≈ cada mes) o se cierra, y entonces Claude
remoto y el chat de la app dan **«failed to fetch»** (`claude auth status` → `loggedIn: false`;
el servicio `claude-remote@…` sale con «You must be logged in to use Remote Control»).

**Arreglo:** app › **Accesos › «Sesión de Claude en el VPS»** → «Iniciar sesión» → «Abrir
claude.com» (entra el operador con SU cuenta) → pega el código que da → «Conectar». El
servidor teclea el código en `claude auth login` (tmux `claude-login`) y reinicia las
`claude-remote@*` activadas y `claude-chat`. Script: `deploy/claude-login/claude-login`
(instalado en `/usr/local/bin/claude-login`); el código va por STDIN, nunca en argv ni logs.
Por terminal: `sudo -u nebulabsai -i claude auth login`.

**opencode y el bot de Telegram NO dependen de esto**: usan su propia clave de OpenCode Go
(`/home/nebulabsai/telegram-agent/.env`), que no caduca.
