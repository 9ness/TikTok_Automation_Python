# Chrome con IP residencial de España (proxy) en el VPS

> Para webs que **bloquean la IP del VPS** (Hetzner, IP de datacenter): Social1,
> y cualquier otra que dé «acceso denegado», captcha infinito o pantalla en
> blanco desde el VPS. Si la web funciona con el Chrome normal, usa ese
> ([`navegador-vps.md`](navegador-vps.md)).
>
> **Social1 ya NO va aquí:** la cuenta de PAGO de Néstor está en el Chrome
> principal (9222, que desde el 20/10 también sale por IP española). Este 9223
> tiene un perfil SIN esa cuenta: si ves «Unlock Social1» o solo #61-72, estás
> en el sitio equivocado → pestaña propia en el 9222 (`www.social1.ai`).

## 1. Qué hay

- Un **segundo Chrome**, aparte del normal, que sale a internet por una **IP
  residencial española**.
  - **Puerto CDP 9223.** El 9222 es el Chrome normal, que es de los otros
    agentes (Flow, GenAI Pro, Magnific): no lo toques ni le cambies el proxy.
  - **Perfil propio:** `/mnt/HC_Volume_106974679/navegador/perfil_proxy_es`.
    Guarda las sesiones; no lo borres.
- **Un reenviador local en `127.0.0.1:8899`** (`~/.config/proxy_es/reenvio.py`).
  - Chrome no acepta `usuario:clave` en `--proxy-server`, así que el reenviador
    añade la autenticación y Chrome se conecta a él sin contraseña.
  - La credencial está en `~/.config/proxy_es/env`. **Nunca la imprimas, la
    copies a un chat o memoria ni la commitees.**
- Se ve por la **misma pantalla virtual `:99`** y el mismo noVNC que el Chrome
  normal (Accesos › Navegador remoto en la app).

## 2. Arrancarlo (paso a paso)

```bash
# 1. Pantalla virtual (se autoapaga a los 45 min sin uso)
sudo -n navegador on

# 2. Reenviador del proxy (si no está ya corriendo)
pgrep -f reenvio.py || nohup python3 ~/.config/proxy_es/reenvio.py >/tmp/reenvio.log 2>&1 &

# 3. Chrome con el proxy (sustituye <URL>)
export DISPLAY=:99; cd /tmp
nohup google-chrome \
  --user-data-dir=/mnt/HC_Volume_106974679/navegador/perfil_proxy_es \
  --remote-debugging-port=9223 \
  --proxy-server=http://127.0.0.1:8899 \
  --lang=es-ES --no-first-run "<URL>" >/tmp/chrome_proxy.log 2>&1 &
```

Para saber si ya estaba abierto: `curl -s 127.0.0.1:9223/json/version`. Si
contesta, no lances otro: abre una pestaña nueva en el que hay.

## 3. Comprobar que sale por España

```bash
curl -s -x http://127.0.0.1:8899 https://ipinfo.io/json | grep -E '"(ip|country|org)"'
```

Tiene que decir `"country": "ES"` y un operador doméstico, no Hetzner. Si da
error, el reenviador está caído (vuelve al paso 2) o el proxy residencial se ha
quedado sin saldo o ha caducado. En ese caso, avisa al operador; no busques otro
proxy por tu cuenta.

## 4. Controlarlo

- **Por CDP** en `127.0.0.1:9223`, con Playwright `connect_over_cdp` o puppeteer.
  - Usa el venv `~/nav-venv/bin/python`, que ya trae Playwright.
  - **No lances un Chromium de Playwright con el proxy:** Google no deja
    iniciar sesión en él. Por eso se usa el Chrome real con el reenviador.
- **Logins, códigos al correo y captchas** los hace el operador por noVNC. Tú
  le avisas de qué pantalla tiene delante.
- Si quieres usar EE. UU. u otro país dentro de la web (p. ej. el selector de
  Social1), se cambia en la web. La IP sigue siendo española.

## 5. Normas

1. **Apunta en `~/navegador_turnos.log`** cuándo ENTRAS y cuándo SALES
   (`fecha · agente · qué haces`), igual que con el Chrome normal.
2. **Gasta datos del proxy (los residenciales suelen cobrar por GB).** Nada de descargar vídeos ni
   ficheros grandes por él: bájalos con `curl` normal, sin proxy, si la web lo
   permite. Cierra las pestañas que no uses.
3. **Al terminar:** cierra tu pestaña. Si nadie más lo usa, mata el Chrome del
   proxy (`pkill -f perfil_proxy_es`) y el reenviador (`pkill -f reenvio.py`).
   Apunta SALE en el log.
4. Borra lo que hayas descargado a `/tmp` y ya no sirva.
