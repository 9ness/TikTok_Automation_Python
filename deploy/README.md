# Despliegue en VPS Hetzner — TikTok Automation Python

Guía completa paso a paso para correr la app en un servidor en la nube
y acceder desde el móvil vía Tailscale Funnel.

**Stack final**: Hetzner CX32 (€8,47/mes) + rclone (Drive mount) +
Tailscale Funnel (HTTPS privado) + systemd (servicios 24/7).

---

## Resumen de fases

| # | Fase | Quién | Tiempo |
|---|---|---|---|
| 1 | Crear cuenta Hetzner + clave SSH desde Windows | Tú | 15 min |
| 2 | Crear servidor CX32 con Ubuntu 24.04 | Tú | 5 min |
| 3 | Conexión SSH + ejecutar `setup.sh` | Tú | 10 min |
| 4 | Configurar `rclone` con Google Drive | Tú | 5 min |
| 5 | Clonar repo + `install_app.sh` + subir `.env` | Tú | 10 min |
| 6 | Registrar servicios systemd | Tú | 2 min |
| 7 | Configurar Tailscale Funnel | Tú | 10 min |
| 8 | Probar desde el móvil | Tú | 2 min |

**Total ~1 hora** de trabajo manual.

---

## Fase 1 — Cuenta Hetzner + clave SSH

### 1.1. Generar clave SSH en Windows

Abre **Windows Terminal** (PowerShell o CMD da igual). Si nunca lo has
hecho antes, ejecuta:

```powershell
ssh-keygen -t ed25519 -C "tiktok-vps@nebulabs"
```

Pulsa Enter en todas las preguntas (acepta defaults; sin passphrase para
no tener que escribirla cada vez que conectes).

Esto crea dos archivos en `C:\Users\TU_USER\.ssh\`:
- `id_ed25519` — privada (NUNCA la compartas)
- `id_ed25519.pub` — pública (la que sube a Hetzner)

Mira tu clave pública (la copiarás luego al panel de Hetzner):

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub
```

Te dará algo como:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI...XYZ tiktok-vps@nebulabs
```

Cópialo entero al portapapeles.

### 1.2. Registrar cuenta Hetzner Cloud

1. Ve a https://accounts.hetzner.com/signUp
2. Crea cuenta con email + contraseña
3. **Verificación**: Hetzner suele pedir verificación de identidad
   con DNI/pasaporte y a veces una pequeña verificación con tarjeta
   (te cobran 0,01€ y te lo devuelven). **Puede tardar de minutos a
   varias horas** según carga. Si te pide subir foto del DNI, hazlo.
4. Mientras esperas, abre https://console.hetzner.cloud/ y crea un
   **proyecto nuevo** llamado `TikTok-Automation`.

### 1.3. Subir tu clave SSH al panel

En el proyecto:
1. Menú lateral izquierdo → **Security** → **SSH Keys** → **Add SSH Key**
2. Pega el contenido de `id_ed25519.pub`
3. Nómbrala `windows-pc` (o lo que quieras)
4. **Add SSH Key**

✋ **Para antes de seguir**: dime cuando tengas la cuenta verificada y la
clave subida. Confirmo el siguiente paso.

---

## Fase 2 — Crear el servidor CX32

En el proyecto Hetzner:

1. **Servers** → **Add Server**
2. **Location**: Falkenstein (EU-Central) — más stock y buena latencia desde España
3. **Image**: Ubuntu 24.04
4. **Type**: pestaña **Shared vCPU** → **CX32** (4 vCPU x86, 8 GB RAM, 80 GB SSD)
5. **Networking**: dejar IPv4 + IPv6 (default)
6. **SSH Keys**: marca la que acabas de subir (`windows-pc`)
7. **Name**: `tiktok-factory`
8. **Create & Buy now**

Hetzner tarda ~30s en provisionar. Te dará una **IP pública**, anótala
(ejemplo: `49.12.34.56`).

---

## Fase 3 — Primer SSH y `setup.sh`

### 3.1. Conectar por SSH

En Windows Terminal:

```powershell
ssh root@49.12.34.56
```

(reemplaza con tu IP). Acepta el fingerprint la primera vez (`yes`).

### 3.2. Ejecutar setup.sh

Estás logueado como `root`. Descarga y ejecuta el script:

```bash
wget https://raw.githubusercontent.com/9ness/TikTok_Automation_Python/main/deploy/setup.sh
chmod +x setup.sh
./setup.sh
```

Qué hace (~5-10 min):
- `apt update && upgrade`
- Instala FFmpeg, Python 3.12, Redis, rclone, Tailscale, ImageMagick, fuentes
- Crea usuario `nebulabsai` con sudo NOPASSWD
- Copia tu clave SSH al usuario nuevo
- Hardeniza SSH (deshabilita login root con contraseña)
- Configura UFW (solo permite SSH)
- Habilita Redis

Cuando acabe, **cierra la sesión SSH y vuelve a entrar como `nebulabsai`**:

```powershell
exit  # cierra root
ssh nebulabsai@49.12.34.56
```

---

## Fase 4 — Configurar rclone con Google Drive

Como `nebulabsai`:

```bash
rclone config
```

Te lanza un asistente interactivo:

| Pregunta | Respuesta |
|---|---|
| `n/s/q>` | `n` (new remote) |
| `name>` | `gdrive` |
| `Storage>` | busca `drive` y pon su número (suele ser **18** — Google Drive) |
| `client_id>` | (vacío, Enter) |
| `client_secret>` | (vacío, Enter) |
| `scope>` | `1` (Full access) |
| `service_account_file>` | (vacío, Enter) |
| `Edit advanced config?` | `n` |
| `Use auto config?` | **`n`** ← muy importante, el VPS no tiene navegador |

Cuando dices `n`, te da una URL larga (`https://accounts.google.com/o/oauth2/auth?...`).

1. Cópiala completa
2. Pégala en tu navegador local (PC o móvil)
3. Login con `nebulabsaimedia@gmail.com`
4. Autoriza rclone (saldrá warning "app no verificada", pulsa Avanzado → Continuar)
5. Te dará un código tipo `4/0AfJ...XYZ`
6. Vuélvelo a pegar en la terminal del VPS donde te lo pide

| Pregunta | Respuesta |
|---|---|
| `Configure this as a Shared Drive?` | `n` |
| `Yes this is OK` | `y` |
| `n/s/q>` | `q` (quit) |

Verifica que funciona:

```bash
rclone lsd gdrive:
# Debe listar las carpetas de tu Drive (Mi unidad, etc.)
```

---

## Fase 5 — Clonar repo + instalar app + subir .env

### 5.1. Clonar y ejecutar install_app.sh

```bash
cd ~
git clone https://github.com/9ness/TikTok_Automation_Python.git
cd TikTok_Automation_Python
bash deploy/install_app.sh
```

Tarda ~5-10 min (instala torch + faster-whisper + descarga modelo Whisper base).

### 5.2. Subir .env desde tu PC local

**Desde tu Windows Terminal (no en el VPS)**:

```powershell
# Sube tu .env actual al VPS
scp -i $env:USERPROFILE\.ssh\id_ed25519 `
    "D:\Proyectos_Personales\TikTok_Automation_Python\.env" `
    nebulabsai@49.12.34.56:/home/nebulabsai/TikTok_Automation_Python/.env
```

### 5.3. Editar .env en el VPS

Vuelve al VPS y añade/modifica estas variables:

```bash
nano ~/TikTok_Automation_Python/.env
```

Añade al final (o ajusta si ya existen):

```env
# Path del mount rclone — apunta directo al subdirectorio TIKTOK_ASSETS
# dentro de NEBULABS_AUTOMATED_TIKTOK. En el mount Linux NO aparece "Mi unidad"
# como subcarpeta (eso es solo cosa de Drive Desktop en Windows); el contenido
# de "Mi unidad" se ve directamente desde la raíz del mount.
TIKTOK_ROOT_PATH=/home/nebulabsai/gdrive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_CR/TIKTOK_ASSETS
```

Los outputs (vídeos finales) se escriben directos al mount (subcarpeta
`BIBLIOTECA_VIDEOS_TERMINADOS/`) y rclone los sube a Drive en background
gracias a `--vfs-cache-mode full`. **No definas `TIKTOK_OUTPUT_LOCAL` en el VPS**
(esa variable solo se usa en Windows local cuando se quiere separar SSD/Drive).

Guarda (Ctrl+O, Enter, Ctrl+X). Asegura permisos:

```bash
chmod 600 ~/TikTok_Automation_Python/.env
```

---

## Fase 6 — Registrar servicios systemd

```bash
sudo bash ~/TikTok_Automation_Python/deploy/register_services.sh
```

Esto:
1. Pre-crea `/var/log/rclone.log` con permisos correctos
2. Copia los `.service` a `/etc/systemd/system/`
3. Monta el Drive en `~/gdrive` (servicio `gdrive-mount`)
4. Arranca Streamlit en `localhost:8501` (servicio `tiktok-factory`)

Verifica:

```bash
systemctl status tiktok-factory     # debe estar 'active (running)'
systemctl status gdrive-mount        # debe estar 'active (running)'
ls ~/gdrive/                         # debe listar Drive

# Logs en vivo (Ctrl+C para salir)
journalctl -u tiktok-factory -f
```

---

## Fase 7 — Tailscale Funnel (acceso HTTPS desde móvil)

### 7.1. Crear cuenta Tailscale (gratis)

1. Ve a https://login.tailscale.com/start
2. Login con Google (usa la misma cuenta `nebulabsaimedia@gmail.com` para que tu compañero pueda añadirse fácil)
3. Llamará a tu tailnet algo como `tail-12345.ts.net`

### 7.2. Conectar el VPS a la tailnet

En el VPS:

```bash
sudo tailscale up
```

Te dará una URL larga `https://login.tailscale.com/a/...`. Ábrela en
cualquier navegador donde estés logueado en Tailscale, autoriza el
device. El VPS aparecerá como `tiktok-factory` en tu admin panel.

### 7.3. Activar HTTPS Funnel

```bash
# Habilita HTTPS interno (certificado de Tailscale)
sudo tailscale serve --bg --https=443 http://localhost:8501

# Expone públicamente (¡pero solo a tu tailnet, no es público de verdad!)
sudo tailscale funnel --bg 443
```

`tailscale funnel status` debe mostrar:

```
https://tiktok-factory.tail-12345.ts.net (Funnel on)
|-- / proxy http://127.0.0.1:8501
```

**Esa URL es la que abrirás en el móvil**. Apúntala.

⚠️ **Limitación importante de Funnel**: tu compañero NECESITA tener
Tailscale instalado y estar en tu tailnet para que la URL le funcione
en privado. Si quieres que se acceda sin Tailscale (totalmente público,
solo HTTPS), Funnel también lo permite — pero entonces cualquiera con
la URL puede entrar. **Recomiendo: que tu compañero instale Tailscale**.

### 7.4. Añadir tu compañero a la tailnet

1. En https://login.tailscale.com/admin/users → **Invite users**
2. Pon el email de tu compañero, le llega un link
3. Acepta, instala Tailscale en su iPhone (App Store)
4. Login → ya está en tu tailnet

---

## Fase 8 — Pruebas finales desde móvil

### 8.1. Instalar Tailscale en tu Oppo

1. Play Store → **Tailscale**
2. Login con la misma cuenta Google
3. Activar VPN

### 8.2. Abrir la app

En Chrome del móvil: `https://tiktok-factory.tail-12345.ts.net`

Deberías ver tu interfaz Streamlit con el modo elegido (Pronósticos /
Presidentes / Subs / Quitar Copy) y el widget de cola arriba.

### 8.3. Test render

1. Modo Pronósticos → carga el guion del día → ENCOLAR
2. El widget de cola muestra el progreso
3. Cierra el navegador → ABRE la app de **Drive** en el móvil
4. Espera 5-15 min (el render sigue en el VPS aunque cierres todo)
5. El MP4 final aparece en `BIBLIOTECA_VIDEOS_TERMINADOS/PRONOSTICOS/`

---

## Auto-deploy con webhook GitHub (opcional, recomendado)

Configura un webhook en GitHub para que cada `git push` a `main` haga
automáticamente `git pull + restart` en el VPS, **esperando a que la
cola de renders esté vacía** antes de reiniciar (no rompe vídeos a
medias).

### Componentes
- `deploy/webhook_listener.py` — servidor HTTP stdlib en puerto 9000
- `deploy/deploy_safe.sh` — script que espera-cola + git pull + restart
- `tiktok-webhook.service` — systemd unit que mantiene el listener vivo

### Setup paso a paso

#### 1. Generar un secret token (en el VPS)

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Guarda el output (algo como `a3b8c9...64chars`). Lo usarás en dos sitios.

#### 2. Añadirlo al .env del VPS

```bash
echo "WEBHOOK_SECRET=PEGA_AQUI_EL_TOKEN" >> ~/TikTok_Automation_Python/.env
chmod 600 ~/TikTok_Automation_Python/.env
```

#### 3. Abrir puerto 9000 en UFW (si no estaba ya)

```bash
sudo ufw allow 9000/tcp comment 'GitHub webhook'
sudo ufw reload
```

#### 4. Arrancar el listener

Si ya ejecutaste `register_services.sh` con WEBHOOK_SECRET en el .env,
ya está activo. Si no:

```bash
sudo bash ~/TikTok_Automation_Python/deploy/register_services.sh
# o solo el webhook:
sudo systemctl enable --now tiktok-webhook
```

Verifica:
```bash
systemctl status tiktok-webhook --no-pager -n 10
curl http://127.0.0.1:9000/health   # → {"status":"ok"}
```

#### 5. Configurar el webhook en GitHub

1. Ve a https://github.com/9ness/TikTok_Automation_Python/settings/hooks
2. **Add webhook**
3. **Payload URL**: `http://62.238.19.31:9000/deploy`
4. **Content type**: `application/json`
5. **Secret**: pega el token del paso 1 (debe coincidir EXACTAMENTE con WEBHOOK_SECRET del .env)
6. **Which events?**: "Just the push event"
7. **Active**: ✅ marcado
8. **Add webhook**

GitHub envía un `ping` event al crear el webhook. Si todo está bien, en
"Recent Deliveries" verás un ✅ verde con `200 pong`. Si ves rojo:
- 401 → secret no coincide entre GitHub y `.env`
- 500 → el listener no se levantó (revisa `journalctl -u tiktok-webhook`)
- Connection timeout → puerto 9000 cerrado en UFW o firewall del cloud

#### 6. Probar el flujo completo

Desde tu PC haz un cambio cualquiera, commit y push. En el VPS:

```bash
journalctl -u tiktok-webhook -f
# y en otra ventana:
tail -f ~/TikTok_Automation_Python/logs/deploy.log
```

Verás:
1. webhook recibe el push, valida HMAC, lanza `deploy_safe.sh`
2. deploy_safe espera si hay cola activa (cada 30s logea)
3. cuando la cola está vacía: `git pull` + `systemctl restart tiktok-factory`

### Seguridad
- HMAC-SHA256 con secret compartido — solo GitHub puede triggerar deploy
- Solo acepta `push` events sobre rama `main` (resto se ignora con 200)
- Si secret está mal, devuelve 401 sin más
- Lock con `flock` evita 2 deploys concurrentes si llegan 2 pushes seguidos
- El listener corre como `nebulabsai`, no como root; el restart vía sudo
  está permitido por NOPASSWD configurado en setup.sh

### Logs útiles
```bash
journalctl -u tiktok-webhook -f                       # listener (recibos de webhooks)
tail -f ~/TikTok_Automation_Python/logs/deploy.log    # deploy script (git pull, restart)
```

---

## Comandos útiles del día a día

### Estado de servicios
```bash
systemctl status tiktok-factory gdrive-mount
```

### Logs
```bash
journalctl -u tiktok-factory -f                    # streamlit
journalctl -u gdrive-mount -n 100                  # mount
tail -f /var/log/rclone.log                        # actividad rclone (subidas, fetches)
```

### Reiniciar la app
```bash
sudo systemctl restart tiktok-factory
```

### Actualizar código del repo
```bash
cd ~/TikTok_Automation_Python
git pull
sudo systemctl restart tiktok-factory
```

### Pausar todo (vacaciones)
```bash
sudo systemctl stop tiktok-factory gdrive-mount
```

### Apagar el VPS (en panel Hetzner)
- Hetzner cobra incluso si lo apagas. Para no pagar, hay que **borrarlo**.
- Mejor opción para vacaciones largas: snapshot (€0,01/GB/mes) + delete server. Recreas desde snapshot al volver.

---

## Troubleshooting

### "El mount de Drive no está activo"
```bash
journalctl -u gdrive-mount -n 50
# Causa común: rclone token expirado. Reconfigurar:
rclone config reconnect gdrive:
sudo systemctl restart gdrive-mount
```

### "Streamlit no responde"
```bash
sudo systemctl restart tiktok-factory
# Si sigue sin ir:
journalctl -u tiktok-factory -n 100
```

### "Los vídeos no aparecen en Drive"
```bash
# Verifica que el archivo existe en el mount (caché local rclone):
ls -la ~/gdrive/NEBULABS_AUTOMATED_TIKTOK/TIKTOK_CR/TIKTOK_ASSETS/BIBLIOTECA_VIDEOS_TERMINADOS/
# Mira logs de subida de rclone (cualquier upload pendiente o error):
tail -100 /var/log/rclone.log | grep -iE "upload|error"
# Forzar flush de caché a Drive ahora mismo:
rclone rc vfs/refresh recursive=true
# Si rclone está colgado, reiniciar el mount:
sudo systemctl restart gdrive-mount
```

### "La cola se quedó en RUNNING tras un crash"
El JobQueue marca automáticamente como FAILED los jobs que estaban
RUNNING al reiniciar. Si no, edita manualmente:

```bash
nano ~/TikTok_Automation_Python/temp_work/queue_state.json
# Cambia "status": "running" por "status": "failed"
sudo systemctl restart tiktok-factory
```

---

## Coste mensual real

| Concepto | €/mes |
|---|---|
| Hetzner CX32 + IPv4 | 8,47 |
| Hetzner snapshots (opcional, 80 GB × 0,0119€) | 0,95 |
| Tailscale Free | 0 |
| Total | **~9,4 €/mes** |

Si quieres apretar más, el snapshot es opcional (sin él pierdes el
estado en caso de necesitar recrear el VPS).
